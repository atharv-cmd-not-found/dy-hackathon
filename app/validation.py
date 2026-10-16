"""
Validation engine for NeuroScope 3D.
Implements multi-tier fail-fast hierarchy, header-only checking,
slot-level isolation, and non-refusing sanity diagnostics.
"""
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import nibabel as nib
from app.config import SLOTS, MAX_DECLARED_BYTES, BRATS_CODES


class ValidationError(Exception):
    """Custom exception raised when an MRI sequence fails validation."""
    def __init__(self, code: str, message: str, slot: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.slot = slot

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "slot": self.slot
        }


def assign_slot_from_filename(filename: str) -> Optional[str]:
    """
    Infers the MRI sequence slot from a filename based on canonical prefixes.
    Checks in specific order: flair -> t1gd/t1ce/t1c -> t2 -> t1
    """
    fn = filename.lower()
    if "flair" in fn:
        return "flair"
    if "t1gd" in fn or "t1ce" in fn or "t1c" in fn:
        return "t1gd"
    if "t2" in fn:
        return "t2"
    if "t1" in fn:
        return "t1"
    if "seg" in fn or "mask" in fn or "label" in fn:
        return "expert"
    return None


def validate_single_header(path: Path, slot: str) -> nib.Nifti1Image:
    """
    Tier 2 Fast-Fail: Parses NIfTI spatial header without decompressing 3D volume.
    Catches invalid extensions, empty files, memory bombs, 2D scans, and singular affines in < 5ms.
    """
    # 0. Extension & file size check
    fn = path.name.lower()
    if not (fn.endswith(".nii.gz") or fn.endswith(".nii")):
        raise ValidationError(
            "INVALID_EXTENSION",
            f"{slot.upper()}: only valid .nii or .nii.gz files are accepted (got '{path.name}').",
            slot
        )

    try:
        if path.stat().st_size == 0:
            raise ValidationError("EMPTY_FILE", f"{slot.upper()}: file is empty (0 bytes).", slot)
    except OSError:
        raise ValidationError("FILE_NOT_FOUND", f"{slot.upper()}: unable to access file.", slot)

    try:
        img = nib.load(str(path))
    except Exception:
        raise ValidationError("NOT_NIFTI", f"{slot.upper()}: not a valid NIfTI image.", slot)

    # 1. Dimension check (must be 3D volume)
    if img.ndim != 3 or min(img.shape) < 16:
        raise ValidationError(
            "NOT_3D",
            f"{slot.upper()}: image must be a 3D volume with min dimension >= 16 (got shape {img.shape}).",
            slot
        )

    # 2. Declared size memory bomb check (header product * 4 bytes float)
    total_voxels = int(np.prod(img.shape))
    declared_bytes = total_voxels * 4
    if declared_bytes > MAX_DECLARED_BYTES:
        raise ValidationError(
            "TOO_LARGE",
            f"{slot.upper()}: declared volume size ({declared_bytes / 1e9:.2f} GB) exceeds safety limit.",
            slot
        )

    # 3. Spatial affine check
    aff = img.affine
    if not np.isfinite(aff).all() or abs(float(np.linalg.det(aff[:3, :3]))) < 1e-9:
        raise ValidationError(
            "BAD_AFFINE",
            f"{slot.upper()}: spatial affine matrix is non-finite or degenerate (det ≈ 0).",
            slot
        )

    return img


def validate_single_data(img: nib.Nifti1Image, slot: str) -> np.ndarray:
    """
    Tier 3: Lazy array load to catch corrupted gzip streams, NaN/Inf, or blank scans.
    """
    try:
        data = np.asanyarray(img.dataobj).astype(np.float32)
    except Exception:
        raise ValidationError("CORRUPT", f"{slot.upper()}: file is corrupt or truncated.", slot)

    # Finite numbers check
    if not np.isfinite(data).all():
        raise ValidationError("NOT_FINITE", f"{slot.upper()}: contains NaN or infinite voxel values.", slot)

    # Blank / constant scan check
    if float(np.ptp(data)) == 0.0:
        raise ValidationError("CONSTANT", f"{slot.upper()}: image is constant or all-zero.", slot)

    return data


def validate_set(paths: Dict[str, Path]) -> Dict[str, Tuple[nib.Nifti1Image, np.ndarray]]:
    """
    Validates a complete set of 4 MRI sequences.
    1. Checks for missing sequences.
    2. Header-only cross-sequence consistency check across all 4 sequences.
    3. Lazy volume data loading and verification.
    """
    # Check for missing slots
    missing = [s for s in SLOTS if s not in paths or not paths[s]]
    if missing:
        missing_str = ", ".join(m.upper() for m in missing)
        raise ValidationError(
            "MISSING_SEQUENCE",
            f"Missing sequence(s): {missing_str}. All four (T1, T1GD, T2, FLAIR) are required."
        )

    # Header-only validation
    headers: Dict[str, nib.Nifti1Image] = {}
    for slot in SLOTS:
        p = Path(paths[slot])
        if not p.exists():
            raise ValidationError("FILE_NOT_FOUND", f"{slot.upper()}: file not found at {p}", slot)
        headers[slot] = validate_single_header(p, slot)

    # Cross-sequence alignment check (Shape and Affine must match T1 reference)
    ref_slot = "t1"
    ref_img = headers[ref_slot]
    ref_voxels = int(np.prod(ref_img.shape))
    for slot in SLOTS:
        if slot == ref_slot:
            continue
        cur_img = headers[slot]
        cur_voxels = int(np.prod(cur_img.shape))
        if cur_img.shape != ref_img.shape:
            raise ValidationError(
                "MISMATCH",
                f"Dimension mismatch: {ref_slot.upper()} has shape {ref_img.shape} ({ref_voxels:,} voxels) "
                f"vs {slot.upper()} with shape {cur_img.shape} ({cur_voxels:,} voxels). All 4 files must have matching dimensions.",
                slot
            )
        if not np.allclose(cur_img.affine, ref_img.affine, atol=1e-3):
            raise ValidationError(
                "MISMATCH",
                f"Spatial affine mismatch: {slot.upper()} affine does not match {ref_slot.upper()} reference orientation/grid.",
                slot
            )

    # Data array validation
    loaded: Dict[str, Tuple[nib.Nifti1Image, np.ndarray]] = {}
    for slot in SLOTS:
        data = validate_single_data(headers[slot], slot)
        loaded[slot] = (headers[slot], data)

    return loaded


def validate_expert_mask(path: Path, ref_img: nib.Nifti1Image) -> Tuple[nib.Nifti1Image, np.ndarray]:
    """
    Validates an optional ground-truth expert segmentation mask.
    Invariants:
      - Same shape and affine as T1 reference
      - Values strictly in BraTS 2021 codes {0, 1, 2, 4}
      - Catches MSD/Decathlon code 3 with explicit error
    """
    p = Path(path)
    if not p.exists():
        raise ValidationError("FILE_NOT_FOUND", f"Expert mask not found at {p}", "expert")

    try:
        img = nib.load(str(p))
    except Exception:
        raise ValidationError("NOT_NIFTI", "EXPERT: not a valid NIfTI image.", "expert")

    if img.shape != ref_img.shape or not np.allclose(img.affine, ref_img.affine, atol=1e-3):
        raise ValidationError(
            "MISMATCH",
            f"Expert mask shape/affine {img.shape} does not match T1 scan {ref_img.shape}.",
            "expert"
        )

    try:
        data = np.asanyarray(img.dataobj).astype(np.int64)
    except Exception:
        raise ValidationError("CORRUPT", "EXPERT: mask file is corrupt or truncated.", "expert")

    unique_vals = set(np.unique(data))
    if 3 in unique_vals:
        raise ValidationError(
            "BAD_LABEL_CODE",
            "BraTS 2021 codes expected {0, 1, 2, 4}; got code 3 (MSD/Decathlon format).",
            "expert"
        )

    invalid_codes = unique_vals - BRATS_CODES
    if invalid_codes:
        raise ValidationError(
            "BAD_LABEL_CODE",
            f"Invalid label codes {invalid_codes} found in expert mask. Expected subset of {BRATS_CODES}.",
            "expert"
        )

    return img, data.astype(np.uint8)


def sanity_check(loaded: Dict[str, Tuple[nib.Nifti1Image, np.ndarray]]) -> Tuple[List[Dict[str, str]], Dict[str, float]]:
    """
    Calculates heuristic anatomical sanity checks.
    IMPORTANT: Never refuses! Only warns to allow synthetic cube tests and edge cases to pass.
    """
    t1_img, t1_data = loaded["t1"]
    
    # Header zooms and determinant
    zooms = t1_img.header.get_zooms()[:3]
    zooms_vol = float(np.prod(zooms))
    det_vol = abs(float(np.linalg.det(t1_img.affine[:3, :3])))
    
    nz = t1_data != 0.0
    total_voxels = t1_data.size
    nz_count = int(nz.sum())
    
    zero_frac = 1.0 - (nz_count / total_voxels) if total_voxels > 0 else 1.0
    brain_ml = (nz_count * det_vol) / 1000.0

    fill_ratio = 0.0
    if nz_count > 0:
        idx = np.argwhere(nz)
        bbox_dims = idx.max(axis=0) - idx.min(axis=0) + 1
        bbox_volume = float(np.prod(bbox_dims))
        fill_ratio = nz_count / bbox_volume if bbox_volume > 0 else 0.0

    warnings: List[Dict[str, str]] = []

    # Check for affine determinant vs header zooms divergence
    if abs(zooms_vol - det_vol) / max(det_vol, 1e-6) > 0.01:
        warnings.append({
            "code": "ZOOM_AFFINE_DIVERGENCE",
            "message": f"Voxel volume from header zooms ({zooms_vol:.3f} mm³) diverges from affine determinant ({det_vol:.3f} mm³)."
        })

    # Background fraction warning
    if zero_frac < 0.20:
        warnings.append({
            "code": "LOW_BACKGROUND",
            "message": f"Low zero-background fraction ({zero_frac:.1%}). Scan may not be skull-stripped."
        })
    elif zero_frac < 0.40:
        warnings.append({
            "code": "SUSPECTED_NON_SKULL_STRIPPED",
            "message": f"Background fraction is {zero_frac:.1%}. Skull-stripped scans typically have >40% background."
        })

    # Volume bounds warning
    if brain_ml < 300 or brain_ml > 3500:
        warnings.append({
            "code": "UNUSUAL_VOLUME",
            "message": f"Estimated tissue volume ({brain_ml:.0f} mL) is outside typical adult range (700 - 2200 mL)."
        })
    elif brain_ml < 700 or brain_ml > 2200:
        warnings.append({
            "code": "BORDERLINE_VOLUME",
            "message": f"Tissue volume ({brain_ml:.0f} mL) is slightly outside normal adult baseline."
        })

    # Shape fill ratio
    if fill_ratio > 0.85:
        warnings.append({
            "code": "NON_BRAIN_SHAPE",
            "message": f"Non-zero region fill ratio ({fill_ratio:.2f}) is dense/cubic rather than ellipsoidal."
        })

    stats = {
        "zero_frac": float(zero_frac),
        "brain_ml": float(brain_ml),
        "fill_ratio": float(fill_ratio),
        "voxel_volume_mm3": float(det_vol)
    }

    return warnings, stats
