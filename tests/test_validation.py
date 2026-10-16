"""
Unit tests for NeuroScope 3D validation engine.
Verifies failure pack inputs, missing sequences, and non-refusing sanity checks.
"""
from pathlib import Path
import pytest
import nibabel as nib
import numpy as np

from app.validation import (
    validate_set,
    validate_expert_mask,
    sanity_check,
    ValidationError,
    assign_slot_from_filename
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def get_base_paths():
    return {
        "t1": FIXTURES_DIR / "base_t1.nii.gz",
        "t1gd": FIXTURES_DIR / "base_t1gd.nii.gz",
        "t2": FIXTURES_DIR / "base_t2.nii.gz",
        "flair": FIXTURES_DIR / "base_flair.nii.gz",
    }


def test_valid_base_set():
    """Valid base scan set must pass validation with 4 loaded sequences."""
    paths = get_base_paths()
    loaded = validate_set(paths)
    assert len(loaded) == 4
    for slot in ["t1", "t1gd", "t2", "flair"]:
        assert slot in loaded
        img, data = loaded[slot]
        assert img.ndim == 3
        assert data.dtype == np.float32


def test_missing_sequence():
    """Missing sequence (e.g. FLAIR omitted) must raise MISSING_SEQUENCE."""
    paths = get_base_paths()
    del paths["flair"]
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code == "MISSING_SEQUENCE"
    assert "FLAIR" in exc_info.value.message


def test_fail_not_nifti():
    """Text file masquerading as NIfTI must raise NOT_NIFTI."""
    paths = get_base_paths()
    paths["flair"] = FIXTURES_DIR / "fail_notnifti.nii.gz"
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code == "NOT_NIFTI"
    assert exc_info.value.slot == "flair"


def test_fail_corrupt_gzip():
    """Truncated gzip must raise CORRUPT or NOT_NIFTI without unhandled crashes."""
    paths = get_base_paths()
    paths["t2"] = FIXTURES_DIR / "fail_corrupt_gzip.nii.gz"
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code in ["CORRUPT", "NOT_NIFTI"]
    assert exc_info.value.slot == "t2"


def test_fail_invalid_extension(tmp_path):
    """File without .nii or .nii.gz extension must raise INVALID_EXTENSION."""
    bad_ext = tmp_path / "scan.txt"
    bad_ext.write_text("dummy")
    paths = get_base_paths()
    paths["flair"] = bad_ext
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code == "INVALID_EXTENSION"
    assert exc_info.value.slot == "flair"


def test_fail_empty_file(tmp_path):
    """0-byte file must raise EMPTY_FILE."""
    empty_file = tmp_path / "empty.nii.gz"
    empty_file.write_bytes(b"")
    paths = get_base_paths()
    paths["t1gd"] = empty_file
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code == "EMPTY_FILE"
    assert exc_info.value.slot == "t1gd"


def test_fail_2d_image():
    """2D image must raise NOT_3D."""
    paths = get_base_paths()
    paths["t1gd"] = FIXTURES_DIR / "fail_2d.nii.gz"
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code == "NOT_3D"
    assert exc_info.value.slot == "t1gd"


def test_fail_all_zeros():
    """Constant/all-zeros scan must raise CONSTANT."""
    paths = get_base_paths()
    paths["t1"] = FIXTURES_DIR / "fail_zeros.nii.gz"
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code == "CONSTANT"
    assert exc_info.value.slot == "t1"


def test_fail_nan_values():
    """Scan containing NaN values must raise NOT_FINITE."""
    paths = get_base_paths()
    paths["t1"] = FIXTURES_DIR / "fail_nan.nii.gz"
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code == "NOT_FINITE"
    assert exc_info.value.slot == "t1"


def test_fail_shape_mismatch():
    """Mismatched sequence dimensions must raise MISMATCH."""
    paths = get_base_paths()
    paths["t2"] = FIXTURES_DIR / "fail_shape_mismatch.nii.gz"
    with pytest.raises(ValidationError) as exc_info:
        validate_set(paths)
    assert exc_info.value.code == "MISMATCH"
    assert exc_info.value.slot == "t2"


def test_expert_mask_valid():
    """Valid expert mask (BraTS codes {0, 1, 2, 4}) must pass."""
    ref_img = nib.load(str(FIXTURES_DIR / "base_t1.nii.gz"))
    mask_path = FIXTURES_DIR / "cube_label.nii.gz"
    img, data = validate_expert_mask(mask_path, ref_img)
    assert img.shape == ref_img.shape
    assert set(np.unique(data)).issubset({0, 1, 2, 4})


def test_expert_mask_invalid_code3():
    """Expert mask containing MSD code 3 must raise BAD_LABEL_CODE."""
    ref_img = nib.load(str(FIXTURES_DIR / "base_t1.nii.gz"))
    bad_mask = FIXTURES_DIR / "fail_code3.nii.gz"
    with pytest.raises(ValidationError) as exc_info:
        validate_expert_mask(bad_mask, ref_img)
    assert exc_info.value.code == "BAD_LABEL_CODE"
    assert "code 3" in exc_info.value.message


def test_sanity_check_non_refusing():
    """Sanity check must return warnings but never raise or crash."""
    paths = get_base_paths()
    loaded = validate_set(paths)
    warnings, stats = sanity_check(loaded)
    assert isinstance(warnings, list)
    assert "voxel_volume_mm3" in stats
    assert stats["voxel_volume_mm3"] > 0


def test_slot_assignment_helper():
    """Slot assignment correctly maps filenames."""
    assert assign_slot_from_filename("BraTS2021_00000_flair.nii.gz") == "flair"
    assert assign_slot_from_filename("patient_t1ce.nii.gz") == "t1gd"
    assert assign_slot_from_filename("patient_t1gd.nii.gz") == "t1gd"
    assert assign_slot_from_filename("patient_t2.nii.gz") == "t2"
    assert assign_slot_from_filename("patient_t1.nii.gz") == "t1"
    assert assign_slot_from_filename("ground_truth_seg.nii.gz") == "expert"
