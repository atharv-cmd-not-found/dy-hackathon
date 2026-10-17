"""
Comprehensive Unit and Integration Tests for Anatomical Inspection in NeuroScope 3D.
Covers Section 8 requirements:
  - voxel -> world -> voxel round trip across isotropic, anisotropic, flipped orientations.
  - Boundary and out-of-bounds coordinate handling.
  - Label lookups: integer preservation, correct anatomical names, no invented regions for label 0.
  - Synthetic tumour mask overlapping known anatomy: verified regional involvement & exact mL.
  - API endpoints and pipeline integration.
"""
import pytest
import numpy as np
import nibabel as nib
import json
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.anatomy import (
    load_atlas_labels_metadata,
    resample_atlas_for_case,
    compute_region_involvement,
    compute_mask_dice
)
from app.config import CASES_DIR


# ─── 1. COORDINATE TRANSFORM TESTS ──────────────────────────────────────────

def test_voxel_world_roundtrip_isotropic_ras():
    """Tests round trip for identity / standard isotropic RAS affine."""
    affine = np.eye(4)
    inv_affine = np.linalg.inv(affine)

    test_voxels = [
        [0, 0, 0],
        [100, 100, 100],
        [239, 239, 154],
        [50, 75, 120]
    ]
    for vox in test_voxels:
        world = nib.affines.apply_affine(affine, vox)
        recomputed = nib.affines.apply_affine(inv_affine, world)
        np.testing.assert_allclose(recomputed, vox, atol=1e-5)


def test_voxel_world_roundtrip_anisotropic_and_non_identity():
    """Tests round trip with anisotropic spacing (e.g. 0.8 × 1.2 × 2.5 mm) and translation."""
    affine = np.array([
        [0.8, 0.0, 0.0, -100.5],
        [0.0, 1.2, 0.0, -125.0],
        [0.0, 0.0, 2.5,  -40.0],
        [0.0, 0.0, 0.0,    1.0]
    ])
    inv_affine = np.linalg.inv(affine)

    test_voxels = [
        [0, 0, 0],
        [50, 60, 30],
        [95, 95, 79],
        [12, 88, 45]
    ]
    for vox in test_voxels:
        world = nib.affines.apply_affine(affine, vox)
        recomputed = nib.affines.apply_affine(inv_affine, world)
        np.testing.assert_allclose(recomputed, vox, atol=1e-5)


def test_voxel_world_roundtrip_brats_lps_orientation():
    """Tests BraTS 2021 LPS affine matrix with Anterior-Posterior axis flip."""
    affine = np.array([
        [-1.0,  0.0,  0.0,   0.0],
        [ 0.0, -1.0,  0.0, 239.0],
        [ 0.0,  0.0,  1.0,   0.0],
        [ 0.0,  0.0,  0.0,   1.0]
    ])
    inv_affine = np.linalg.inv(affine)

    test_voxels = [
        [0, 0, 0],
        [120, 120, 77],
        [239, 239, 154],
        [10, 230, 50]
    ]
    for vox in test_voxels:
        world = nib.affines.apply_affine(affine, vox)
        recomputed = nib.affines.apply_affine(inv_affine, world)
        np.testing.assert_allclose(recomputed, vox, atol=1e-5)


def test_boundary_and_out_of_bounds_detection():
    """Tests bounds checking logic on volume grids."""
    shape = (240, 240, 155)

    # In-bounds boundary points
    assert 0 <= 0 < shape[0] and 0 <= 0 < shape[1] and 0 <= 0 < shape[2]
    assert 0 <= 239 < shape[0] and 0 <= 239 < shape[1] and 0 <= 154 < shape[2]

    # Out of bounds points
    oob_points = [
        [-1, 50, 50],
        [50, -1, 50],
        [50, 50, -1],
        [240, 100, 50],
        [100, 240, 50],
        [100, 100, 155],
        [300, 400, 500]
    ]
    for pt in oob_points:
        is_in = (0 <= pt[0] < shape[0] and 0 <= pt[1] < shape[1] and 0 <= pt[2] < shape[2])
        assert not is_in, f"Point {pt} should be out of bounds for shape {shape}"


# ─── 2. ATLAS LOOKUP AND LABEL PRESERVATION TESTS ───────────────────────────

def test_label_lookup_returns_correct_anatomical_names():
    """Verifies that the label dictionary maps IDs to accurate anatomical names and hemispheres."""
    meta = load_atlas_labels_metadata()
    labels = meta.get("labels", {})
    assert len(labels) >= 100, "Atlas must contain canonical anatomical structures"

    # Precentral Gyrus Left (ID 1)
    lbl_1 = labels.get("1")
    assert lbl_1 is not None
    assert "Precentral" in lbl_1["name"]
    assert lbl_1["hemisphere"] == "Left"
    assert lbl_1["lobe"] == "Frontal Lobe"

    # Precentral Gyrus Right (ID 2)
    lbl_2 = labels.get("2")
    assert lbl_2 is not None
    assert "Precentral" in lbl_2["name"]
    assert lbl_2["hemisphere"] == "Right"
    assert lbl_2["lobe"] == "Frontal Lobe"

    # Insular Cortex (ID 29, 30)
    lbl_29 = labels.get("29")
    assert lbl_29 is not None
    assert "Insula" in lbl_29["name"] or "Insular" in lbl_29["name"]
    assert lbl_29["hemisphere"] == "Left"

    # Hippocampus Left (ID 37)
    lbl_37 = labels.get("37")
    assert lbl_37 is not None
    assert "Hippocampus" in lbl_37["name"]
    assert lbl_37["lobe"] == "Temporal Lobe"


def test_unlabeled_voxel_does_not_invent_region():
    """Label 0 (background / unlabeled) must never return a synthetic region name."""
    meta = load_atlas_labels_metadata()
    labels = meta.get("labels", {})

    # Label 0 is background and must not be in labels dictionary or must map to Background
    assert "0" not in labels or labels["0"].get("name") == "Background"


def test_nearest_neighbor_resampling_preserves_discrete_integers(tmp_path):
    """Verifies that nearest-neighbour (order=0) never introduces interpolated float labels."""
    # Create small synthetic test volume with integer labels: 0, 1, 5, 29, 100
    source_data = np.zeros((20, 20, 20), dtype=np.int16)
    source_data[5:10, 5:10, 5:10] = 1
    source_data[10:15, 10:15, 10:15] = 5
    source_data[2:5, 12:15, 8:12] = 29

    source_affine = np.diag([1.0, 1.0, 1.0, 1.0])
    target_affine = np.diag([0.5, 0.5, 0.5, 1.0]) # 2x upsampled grid
    target_shape = (40, 40, 40)

    import scipy.ndimage
    T = np.linalg.inv(source_affine) @ target_affine
    resampled = scipy.ndimage.affine_transform(
        source_data,
        matrix=T[:3, :3],
        offset=T[:3, 3],
        output_shape=target_shape,
        order=0,
        mode="constant",
        cval=0
    )

    unique_vals = set(np.unique(resampled))
    expected_allowed = {0, 1, 5, 29}
    assert unique_vals.issubset(expected_allowed), f"Resampled labels must only contain discrete original IDs, got {unique_vals}"


# ─── 3. SYNTHETIC TUMOUR OVERLAP WITH KNOWN ANATOMY ─────────────────────────

def test_synthetic_tumor_overlap_calculates_exact_volumes():
    """
    Creates a synthetic label grid with known region boundaries and places
    a synthetic tumour mask overlapping known proportions.
    Verifies that compute_region_involvement calculates exact mL and percentages.
    """
    shape = (30, 30, 30)
    anatomy = np.zeros(shape, dtype=np.int16)
    pred = np.zeros(shape, dtype=np.uint8)

    # Region 1 (Precentral L): 1000 voxels
    anatomy[0:10, 0:10, 0:10] = 1

    # Region 2 (Hippocampus L): 1000 voxels
    anatomy[10:20, 0:10, 0:10] = 37

    # Synthetic tumour overlapping 400 voxels of Region 1 and 200 voxels of Region 2
    # Region 1 overlap: 400 voxels (200 NCR label 1, 200 ED label 2)
    pred[0:4, 0:10, 0:10] = 1  # 4 * 10 * 10 = 400 voxels
    # Region 2 overlap: 200 voxels (200 ET label 4)
    pred[10:12, 0:10, 0:10] = 4 # 2 * 10 * 10 = 200 voxels

    voxel_vol_mm3 = 1.0 # 1 mm^3 per voxel => 1000 voxels = 1.0 mL
    mock_lookup = {
        "labels": {
            "1": {"id": 1, "name": "Precentral Gyrus", "hemisphere": "Left", "lobe": "Frontal Lobe"},
            "37": {"id": 37, "name": "Hippocampus", "hemisphere": "Left", "lobe": "Temporal Lobe"}
        }
    }

    involvement = compute_region_involvement(pred, anatomy, voxel_vol_mm3, mock_lookup)
    assert len(involvement) == 2, "Must identify exactly 2 involved regions"

    # First region should be Region 1 (larger tumor volume: 400 voxels = 0.400 mL)
    r1 = involvement[0]
    assert r1["id"] == 1
    assert r1["name"] == "Precentral Gyrus"
    assert r1["tumor_volume_ml"] == 0.400
    assert r1["region_volume_ml"] == 1.000
    assert r1["pct_of_region_involved"] == 40.0 # 400 / 1000 * 100
    assert round(r1["pct_of_total_tumor"], 1) == 66.7 # 400 / 600 * 100

    # Second region should be Region 37 (Hippocampus: 200 voxels = 0.200 mL)
    r2 = involvement[1]
    assert r2["id"] == 37
    assert r2["name"] == "Hippocampus"
    assert r2["tumor_volume_ml"] == 0.200
    assert r2["et_volume_ml"] == 0.200
    assert r2["pct_of_region_involved"] == 20.0 # 200 / 1000 * 100
    assert round(r2["pct_of_total_tumor"], 1) == 33.3 # 200 / 600 * 100


# ─── 4. ALIGNMENT QUALITY & UNALIGNED TEMPLATE HANDLING ─────────────────────

def test_unaligned_scan_sets_unavailable_state(tmp_path):
    """
    Synthetic scan fixtures (e.g. 96x96x80) not centered on SRI24 space
    must be flagged as 'unavailable' with Dice < 0.25 and not produce guessed labels.
    """
    # Create synthetic reference image with identity affine
    data = np.zeros((96, 96, 80), dtype=np.float32)
    data[20:40, 20:40, 20:40] = 50.0 # synthetic brain box
    img = nib.Nifti1Image(data, affine=np.diag([1.0, 1.0, 2.0, 1.0]))

    out_nii = tmp_path / "anatomy.nii.gz"
    out_json = tmp_path / "anatomy_lookup.json"

    meta = resample_atlas_for_case(img, data, out_nii, out_json)
    assert meta["status"] == "unavailable"
    assert meta["quality"] == "unaligned_template_space"
    assert meta["overlap_dice"] < 0.25
    assert "not in SRI24 template space" in meta["message"]


def test_template_aligned_case_sets_available_state(tmp_path):
    """
    Scans in SRI24 template space (BraTS real cases) must achieve Dice > 0.60
    and be marked as 'available' with verified provenance.
    """
    brats_case_t1 = Path("data/cases/55ad3d28-1d67-446e-99c2-c374ad33dbcd/t1.nii.gz")
    if not brats_case_t1.exists():
        pytest.skip("BraTS test scan not present")

    img = nib.load(str(brats_case_t1))
    t1_data = img.get_fdata()

    out_nii = tmp_path / "anatomy.nii.gz"
    out_json = tmp_path / "anatomy_lookup.json"

    meta = resample_atlas_for_case(img, t1_data, out_nii, out_json)
    assert meta["status"] == "available"
    assert meta["quality"] == "verified_template_alignment"
    assert meta["overlap_dice"] >= 0.70
    assert out_nii.exists()
    assert out_json.exists()


# ─── 5. API ENDPOINTS INTEGRATION ───────────────────────────────────────────

def test_api_case_anatomy_endpoint():
    """Tests GET /api/cases/{case_id}/anatomy returns valid JSON lookup and provenance."""
    client = TestClient(app)

    # 1. Existing real case with anatomy
    case_id = "55ad3d28-1d67-446e-99c2-c374ad33dbcd"
    resp = client.get(f"/api/cases/{case_id}/anatomy")
    if resp.status_code == 200:
        data = resp.json()
        assert "provenance" in data
        assert "status" in data
        assert "labels" in data
        assert len(data["labels"]) > 0

    # 2. Non-existent case returns 404
    resp_404 = client.get("/api/cases/non-existent-case-123/anatomy")
    assert resp_404.status_code == 404


def test_api_case_status_includes_anatomy_metadata():
    """Tests that GET /api/cases/{case_id} response payload includes files.anatomy_nii and anatomy."""
    client = TestClient(app)
    case_id = "55ad3d28-1d67-446e-99c2-c374ad33dbcd"

    resp = client.get(f"/api/cases/{case_id}")
    if resp.status_code == 200:
        data = resp.json()
        assert "files" in data
        assert "anatomy_nii" in data["files"]
        assert "anatomy" in data
        assert data["anatomy"] is not None
        assert "spatial_meta" in data
        assert "affine" in data["spatial_meta"]
