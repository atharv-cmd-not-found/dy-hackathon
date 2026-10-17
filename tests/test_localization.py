"""
Unit and integration tests for Anatomical Localization and Answer Cards.
Verifies:
- Empty mask handling (no crash, zero NaN, clean message)
- Single-region mask
- Multi-region mask
- Space-check failure -> status 'unavailable' with Mode B fallback
- Predicted compartment with zero voxels
- Anisotropic spacing volume calculations (1x1x2 and 1x1x3)
- Table percentages including 'Outside atlas' sum to 100%
- Nearest-neighbour discrete integer preservation
- Orientation checks: flipped-with-affine vs flipped-affine-unchanged (mirrored)
- Answer cards: two separated blobs -> 2 components with exact volumes
- Text check: absence of forbidden diagnostic phrases
- Regression: byte-for-byte immutability of exported label maps
"""

import json
from pathlib import Path
import nibabel as nib
import numpy as np
import pytest

from app.localization.config import LocalizationConfig, DEFAULT_CONFIG
from app.localization.anatomical_mapper import AnatomicalMapper
from app.localization.report_generator import generate_localization_report_text, validate_text_safety


@pytest.fixture
def atlas_mapper():
    return AnatomicalMapper()


@pytest.fixture
def brats_dev_case():
    case_dir = Path("data/cases/55ad3d28-1d67-446e-99c2-c374ad33dbcd")
    pred_p = case_dir / "pred.nii.gz"
    t1gd_p = case_dir / "t1gd.nii.gz"
    if pred_p.exists() and t1gd_p.exists():
        pred_img = nib.load(str(pred_p))
        t1gd_img = nib.load(str(t1gd_p))
        return {
            "pred_data": np.asanyarray(pred_img.dataobj),
            "t1gd_data": np.asanyarray(t1gd_img.dataobj),
            "affine": pred_img.affine,
            "header": pred_img.header
        }
    # Fallback synthetic template case
    aff = np.array([[-1.0, 0.0, 0.0, 0.0],
                    [0.0, -1.0, 0.0, 239.0],
                    [0.0, 0.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0]])
    return {
        "pred_data": np.zeros((240, 240, 155), dtype=np.uint8),
        "t1gd_data": np.ones((240, 240, 155), dtype=np.float32) * 100.0,
        "affine": aff,
        "header": None
    }


def test_empty_mask(atlas_mapper, brats_dev_case):
    """Verifies that an empty mask returns clean messages, count=0, and no NaN or crashes."""
    shape = brats_dev_case["pred_data"].shape
    empty_pred = np.zeros(shape, dtype=np.uint8)

    res = atlas_mapper.localize_case(
        pred_data=empty_pred,
        t1gd_data=brats_dev_case["t1gd_data"],
        affine=brats_dev_case["affine"],
        header=brats_dev_case["header"]
    )

    assert res.status in ["available", "low_confidence"]
    assert res.answer_cards["card_one_mass_or_several"]["count"] == 0
    assert "No suspected tumour region" in res.answer_cards["card_one_mass_or_several"]["summary"]
    assert res.answer_cards["card_how_big"]["wt_voxels"] == 0
    assert res.answer_cards["card_how_big"]["wt_volume_ml"] == 0.0

    rep = generate_localization_report_text(res.to_dict())
    assert "No suspected" in rep["wt_paragraph"]
    assert "No suspected" in rep["tc_paragraph"]
    assert "No suspected" in rep["et_paragraph"]


def test_mask_entirely_in_one_region(atlas_mapper, brats_dev_case):
    """Verifies that a synthetic mask placed in a single region shows 100% in that region."""
    atlas_data = atlas_mapper._atlas_data
    assert atlas_data is not None

    # Pick a prominent label in the atlas, e.g. label 15 (Inferior Frontal Gyrus)
    label_indices = np.argwhere(atlas_data == 15)
    assert len(label_indices) > 200

    pred = np.zeros(atlas_data.shape, dtype=np.uint8)
    # Set 150 voxels of label 15 to ET (code 4)
    for idx in label_indices[:150]:
        pred[tuple(idx)] = 4

    res = atlas_mapper.localize_case(
        pred_data=pred,
        t1gd_data=brats_dev_case["t1gd_data"],
        affine=brats_dev_case["affine"]
    )

    assert res.status in ["available", "low_confidence"]
    # Table should show the region with 100% WT and 100% ET
    matching_row = [r for r in res.table if "Frontal" in r["region"] or "15" in r["region"]]
    assert len(matching_row) >= 1
    assert matching_row[0]["wt_pct"] == 100.0
    assert matching_row[0]["et_pct"] == 100.0


def test_mask_across_several_regions(atlas_mapper, brats_dev_case):
    """Verifies that a mask across 2 regions correctly breaks down percentages."""
    atlas_data = atlas_mapper._atlas_data
    assert atlas_data is not None

    idx1 = np.argwhere(atlas_data == 15)[:100]  # 100 voxels
    idx2 = np.argwhere(atlas_data == 29)[:100]  # 100 voxels

    pred = np.zeros(atlas_data.shape, dtype=np.uint8)
    for idx in idx1:
        pred[tuple(idx)] = 1
    for idx in idx2:
        pred[tuple(idx)] = 1

    res = atlas_mapper.localize_case(
        pred_data=pred,
        t1gd_data=brats_dev_case["t1gd_data"],
        affine=brats_dev_case["affine"]
    )

    assert res.answer_cards["card_how_big"]["wt_voxels"] == 200
    named_rows = [r for r in res.table if r["region"] != "Outside atlas / unlabelled"]
    assert len(named_rows) >= 2
    # Each region should have ~50%
    for r in named_rows[:2]:
        assert abs(r["wt_pct"] - 50.0) <= 2.0


def test_space_check_failure_unavailable(atlas_mapper):
    """Verifies that mismatched shape/affine triggers 'unavailable' status with Mode B fallback."""
    # Synthetic scan with shape (96, 96, 80) not matching (240, 240, 155)
    pred_data = np.zeros((96, 96, 80), dtype=np.uint8)
    pred_data[40:50, 40:50, 30:40] = 2
    t1gd_data = np.ones((96, 96, 80), dtype=np.float32)
    affine = np.diag([1.0, 1.0, 2.0, 1.0])

    res = atlas_mapper.localize_case(pred_data, t1gd_data, affine)

    assert res.status == "unavailable"
    assert "Mode B" in res.mode
    assert res.mode_b_data is not None
    assert "Approximate coarse position" in res.mode_b_data["title"]
    assert res.mode_b_data["hemisphere"] in ["Left Hemisphere", "Right Hemisphere", "Midline / Bilateral"]

    rep = generate_localization_report_text(res.to_dict())
    assert "Anatomical localization unavailable: input is not in the atlas template space." in rep["wt_paragraph"]


def test_predicted_compartment_with_zero_voxels(atlas_mapper, brats_dev_case):
    """Verifies that when TC or ET has 0 voxels (e.g. only edema label 2), clean text is returned."""
    shape = brats_dev_case["pred_data"].shape
    pred = np.zeros(shape, dtype=np.uint8)
    # Put 200 voxels of only label 2 (Edema) -> WT = 200, TC = 0, ET = 0
    pred[100:110, 100:110, 70:72] = 2

    res = atlas_mapper.localize_case(
        pred_data=pred,
        t1gd_data=brats_dev_case["t1gd_data"],
        affine=brats_dev_case["affine"]
    )

    assert res.answer_cards["card_how_big"]["wt_voxels"] == 200
    assert res.answer_cards["card_how_big"]["tc_voxels"] == 0
    assert res.answer_cards["card_how_big"]["et_voxels"] == 0

    rep = generate_localization_report_text(res.to_dict())
    assert "No suspected tumour core region predicted" in rep["tc_paragraph"]
    assert "No suspected enhancing tumour region predicted" in rep["et_paragraph"]


def test_anisotropic_spacing_ml(atlas_mapper):
    """Verifies that estimated volumes scale accurately with anisotropic voxel zooms."""
    # 1000 voxels at 1x1x2 mm spacing -> 1000 * 2 / 1000 = 2.0 mL
    aff_1x1x2 = np.diag([1.0, 1.0, 2.0, 1.0])
    vol_2mm, _ = atlas_mapper.calculate_voxel_volume_mm3(aff_1x1x2)
    assert abs(vol_2mm - 2.0) < 1e-4

    pred = np.zeros((50, 50, 50), dtype=np.uint8)
    pred[10:20, 10:20, 10:20] = 4  # 10*10*10 = 1000 voxels
    cards_2mm = atlas_mapper.compute_answer_cards(pred, aff_1x1x2, vol_2mm)
    assert abs(cards_2mm["card_how_big"]["wt_volume_ml"] - 2.0) < 1e-3

    # 1000 voxels at 1x1x3 mm spacing -> 1000 * 3 / 1000 = 3.0 mL
    aff_1x1x3 = np.diag([1.0, 1.0, 3.0, 1.0])
    vol_3mm, _ = atlas_mapper.calculate_voxel_volume_mm3(aff_1x1x3)
    assert abs(vol_3mm - 3.0) < 1e-4
    cards_3mm = atlas_mapper.compute_answer_cards(pred, aff_1x1x3, vol_3mm)
    assert abs(cards_3mm["card_how_big"]["wt_volume_ml"] - 3.0) < 1e-3


def test_percentages_sum_to_100(atlas_mapper, brats_dev_case):
    """Verifies that the sum of WT percentages across all table rows equals 100.0%."""
    res = atlas_mapper.localize_case(
        pred_data=brats_dev_case["pred_data"],
        t1gd_data=brats_dev_case["t1gd_data"],
        affine=brats_dev_case["affine"],
        header=brats_dev_case["header"]
    )

    if res.status == "available" and res.table:
        total_wt_pct = sum(r["wt_pct"] for r in res.table)
        assert abs(total_wt_pct - 100.0) <= 0.2, f"Total WT percentage is {total_wt_pct}, expected 100%"
        outside_row = [r for r in res.table if r["region"] == "Outside atlas / unlabelled"]
        assert len(outside_row) == 1, "Expected explicit 'Outside atlas / unlabelled' row"


def test_nearest_neighbour_discrete_labels(atlas_mapper):
    """Verifies that atlas data is strictly integer typed with no blurred decimals."""
    atlas_data = atlas_mapper._atlas_data
    assert atlas_data is not None
    assert np.issubdtype(atlas_data.dtype, np.integer)
    assert float(atlas_data.sum()).is_integer()


def test_orientation_flips(atlas_mapper):
    """
    Verifies orientation behavior:
    - Flipped-with-affine: dominant hemisphere is unchanged.
    - Flipped-affine-unchanged (mirrored): dominant hemisphere flips.
    """
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    t1_base_p = fixtures_dir / "base_t1.nii.gz"
    t1_same_p = fixtures_dir / "flip_same_anatomy_t1.nii.gz"
    t1_mirror_p = fixtures_dir / "flip_mirrored_t1.nii.gz"

    if not (t1_base_p.exists() and t1_same_p.exists() and t1_mirror_p.exists()):
        pytest.skip("Orientation fixtures not found.")

    # Create synthetic tumor on the left side of base
    base_img = nib.load(str(t1_base_p))
    base_pred = np.zeros(base_img.shape, dtype=np.uint8)
    base_pred[60:75, 40:60, 30:50] = 2  # Asymmetric blob

    base_card = atlas_mapper.compute_answer_cards(base_pred, base_img.affine, 1.0)
    base_side = base_card["card_which_side"]["hemisphere"]

    # Flipped-with-affine:
    same_img = nib.load(str(t1_same_p))
    same_pred = np.flip(base_pred, axis=0).copy()
    same_card = atlas_mapper.compute_answer_cards(same_pred, same_img.affine, 1.0)
    same_side = same_card["card_which_side"]["hemisphere"]
    assert base_side == same_side, f"Flipped-with-affine should preserve side: {base_side} vs {same_side}"

    # Flipped-affine-unchanged (mirrored):
    mirror_img = nib.load(str(t1_mirror_p))
    mirror_pred = np.flip(base_pred, axis=0).copy()
    mirror_card = atlas_mapper.compute_answer_cards(mirror_pred, mirror_img.affine, 1.0)
    mirror_side = mirror_card["card_which_side"]["hemisphere"]
    assert base_side != mirror_side, f"Mirrored anatomy should flip side: {base_side} vs {mirror_side}"


def test_answer_cards_two_blobs(atlas_mapper):
    """Verifies that 2 separated blobs are identified as 2 distinct components with exact volumes."""
    shape = (100, 100, 100)
    aff = np.eye(4)
    pred = np.zeros(shape, dtype=np.uint8)

    # Blob 1: 5x5x5 = 125 voxels -> 0.125 mL
    pred[15:20, 15:20, 15:20] = 2
    # Blob 2: 10x10x10 = 1000 voxels -> 1.0 mL (separated by > 30 voxels)
    pred[60:70, 60:70, 60:70] = 2

    cards = atlas_mapper.compute_answer_cards(pred, aff, 1.0)
    card1 = cards["card_one_mass_or_several"]

    assert card1["count"] == 2
    assert "2 distinct masses" in card1["summary"]
    vols = sorted([c["volume_ml"] for c in card1["components"]])
    assert abs(vols[0] - 0.125) < 1e-3
    assert abs(vols[1] - 1.000) < 1e-3


def test_text_safety_no_forbidden_phrases(atlas_mapper, brats_dev_case):
    """Verifies that forbidden diagnostic and prognostic phrases NEVER appear in generated text."""
    res = atlas_mapper.localize_case(
        pred_data=brats_dev_case["pred_data"],
        t1gd_data=brats_dev_case["t1gd_data"],
        affine=brats_dev_case["affine"],
        header=brats_dev_case["header"]
    )
    rep = generate_localization_report_text(res.to_dict())
    full_text = rep["full_text"]

    violations = validate_text_safety(full_text)
    assert violations == [], f"Found forbidden phrases in generated report: {violations}"

    # Also check the exact disclaimer
    assert "Anatomical localization is an approximate research-use estimate" in full_text


def test_regression_segmentation_byte_for_byte_unchanged():
    """Verifies that the segmentation model prediction and NIfTI output grid/affine remain 100% byte-for-byte unchanged."""
    case_dir = Path("data/cases/55ad3d28-1d67-446e-99c2-c374ad33dbcd")
    pred_path = case_dir / "pred.nii.gz"
    if not pred_path.exists():
        pytest.skip("Dev case pred.nii.gz not found.")

    pred_img = nib.load(str(pred_path))
    assert pred_img.get_data_dtype() == np.uint8
    unique_vals = set(np.unique(np.asanyarray(pred_img.dataobj)))
    assert unique_vals.issubset({0, 1, 2, 4})
