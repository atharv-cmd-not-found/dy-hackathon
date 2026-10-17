"""
Anatomical Atlas Mapping and Brain Region Engine for NeuroScope 3D.
Provides SRI24 template resampling via affine transformation, nearest-neighbour
interpolation, alignment verification, anatomical label lookups, and per-region
tumour involvement estimation.
"""
import json
import time
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List
import numpy as np
import scipy.ndimage
import nibabel as nib

# Locate atlas files relative to repository
ATLAS_DIR = Path(__file__).resolve().parent.parent / "data" / "atlas" / "sri24"
ATLAS_NII = ATLAS_DIR / "tzo116plus.nii.gz"
ATLAS_NII_RAW = ATLAS_DIR / "tzo116plus.nii"
ATLAS_LABELS_JSON = ATLAS_DIR / "sri24_labels.json"


def get_atlas_path() -> Optional[Path]:
    """Finds the SRI24 label volume file (.nii.gz preferred, .nii fallback)."""
    if ATLAS_NII.exists():
        return ATLAS_NII
    if ATLAS_NII_RAW.exists():
        return ATLAS_NII_RAW
    return None


def load_atlas_labels_metadata() -> Dict[str, Any]:
    """Loads canonical SRI24 labels metadata and lookup table."""
    if ATLAS_LABELS_JSON.exists():
        try:
            return json.loads(ATLAS_LABELS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "provenance": {
            "method": "SRI24 Template Space Resampling (Nearest-Neighbor)",
            "atlas_name": "SRI24 Multi-Channel Atlas (TZO116+)",
            "license": "CC BY-SA 3.0",
            "disclaimer": "ATLAS-DERIVED ANATOMY — approximate. Non-clinical research prototype."
        },
        "labels": {}
    }


def compute_mask_dice(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    """Computes Dice similarity coefficient between two binary masks."""
    a_sum = int(mask_a.sum())
    b_sum = int(mask_b.sum())
    if a_sum + b_sum == 0:
        return 1.0
    intersection = int(np.logical_and(mask_a, mask_b).sum())
    return float(2.0 * intersection / (a_sum + b_sum))


def resample_atlas_for_case(
    ref_img: nib.Nifti1Image,
    t1_data: np.ndarray,
    output_nii_path: Path,
    output_json_path: Path,
    min_alignment_dice: float = 0.25
) -> Dict[str, Any]:
    """
    Resamples SRI24 atlas labels onto the patient MRI grid using affine transformation
    and nearest-neighbour interpolation (order=0).
    Verifies spatial alignment against patient brain tissue.
    Saves:
      - output_nii_path: patient-aligned label NIfTI (matching dimensions & affine)
      - output_json_path: label lookup dictionary with provenance and quality metrics
    """
    atlas_path = get_atlas_path()
    if not atlas_path:
        error_meta = {
            "status": "unavailable",
            "quality": "missing_atlas_file",
            "message": "Atlas resource file (tzo116plus.nii.gz) not found on server.",
            "provenance": {
                "method": "SRI24 Template Space Resampling",
                "status": "error"
            },
            "labels": {}
        }
        output_json_path.write_text(json.dumps(error_meta, indent=2), encoding="utf-8")
        return error_meta

    t0 = time.time()
    atlas_img = nib.load(str(atlas_path))
    atlas_data = np.squeeze(np.asanyarray(atlas_img.dataobj)).astype(np.int16)
    atlas_affine = atlas_img.affine
    target_affine = ref_img.affine
    target_shape = ref_img.shape[:3]

    # Coordinate transform: target voxel -> world (target_affine) -> atlas voxel (inv(atlas_affine))
    T = np.linalg.inv(atlas_affine) @ target_affine
    matrix = T[:3, :3]
    offset = T[:3, 3]

    # Nearest-neighbor interpolation preserves discrete integer region IDs
    resampled = scipy.ndimage.affine_transform(
        atlas_data,
        matrix=matrix,
        offset=offset,
        output_shape=target_shape,
        order=0,
        mode="constant",
        cval=0
    ).astype(np.int16)

    # Calculate alignment quality: Dice overlap between patient brain mask and atlas brain mask
    patient_brain = (t1_data > 0.0)
    atlas_brain = (resampled > 0)
    overlap_dice = compute_mask_dice(patient_brain, atlas_brain)

    is_aligned = overlap_dice >= min_alignment_dice
    quality_status = "verified_template_alignment" if is_aligned else "unaligned_template_space"
    status_str = "available" if is_aligned else "unavailable"

    if is_aligned:
        quality_message = f"Patient scan verified aligned to SRI24 template space (brain overlap Dice: {overlap_dice:.3f})."
    else:
        quality_message = (
            f"Patient scan is not in SRI24 template space (brain overlap Dice: {overlap_dice:.3f} < {min_alignment_dice}). "
            f"Anatomical labels unavailable for this case."
        )

    # Save aligned label volume as NIfTI with exact patient affine and header
    hdr = ref_img.header.copy()
    hdr.set_data_dtype(np.int16)
    out_img = nib.Nifti1Image(resampled, affine=target_affine, header=hdr)
    nib.save(out_img, str(output_nii_path))

    # Load canonical label lookup and package case lookup
    base_meta = load_atlas_labels_metadata()
    lookup_payload = {
        "status": status_str,
        "quality": quality_status,
        "message": quality_message,
        "overlap_dice": round(overlap_dice, 4),
        "resample_time_sec": round(time.time() - t0, 3),
        "target_shape": list(target_shape),
        "target_zooms": [round(float(z), 3) for z in ref_img.header.get_zooms()[:3]],
        "provenance": {
            **base_meta.get("provenance", {}),
            "alignment_quality": quality_status,
            "overlap_dice": round(overlap_dice, 4),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tool": f"scipy.ndimage.affine_transform (order=0) / nibabel {nib.__version__}"
        },
        "labels": base_meta.get("labels", {})
    }

    output_json_path.write_text(json.dumps(lookup_payload, indent=2), encoding="utf-8")
    return lookup_payload


def compute_region_involvement(
    pred_data: np.ndarray,
    anatomy_data: np.ndarray,
    voxel_volume_mm3: float,
    label_lookup: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Computes per-region tumour involvement summary (Section 7).
    Calculates estimated tumour volume in mL and fraction of anatomical structure
    occupied by predicted tumour.
    """
    wt_mask = (pred_data > 0)
    tc_mask = (pred_data == 1) | (pred_data == 4)
    et_mask = (pred_data == 4)

    total_wt_voxels = int(wt_mask.sum())
    if total_wt_voxels == 0:
        return []

    # Find unique non-zero anatomical region IDs that overlap WT
    overlapping_regions = np.unique(anatomy_data[wt_mask])
    overlapping_regions = overlapping_regions[overlapping_regions > 0]

    involvement = []
    labels_dict = label_lookup.get("labels", {})

    for reg_id in overlapping_regions:
        reg_id_int = int(reg_id)
        reg_mask = (anatomy_data == reg_id_int)
        reg_total_voxels = int(reg_mask.sum())
        if reg_total_voxels == 0:
            continue

        wt_overlap = int(np.logical_and(reg_mask, wt_mask).sum())
        tc_overlap = int(np.logical_and(reg_mask, tc_mask).sum())
        et_overlap = int(np.logical_and(reg_mask, et_mask).sum())

        wt_ml = (wt_overlap * voxel_volume_mm3) / 1000.0
        tc_ml = (tc_overlap * voxel_volume_mm3) / 1000.0
        et_ml = (et_overlap * voxel_volume_mm3) / 1000.0
        reg_ml = (reg_total_voxels * voxel_volume_mm3) / 1000.0

        pct_of_region = (wt_overlap / reg_total_voxels) * 100.0
        pct_of_tumor = (wt_overlap / total_wt_voxels) * 100.0

        meta = labels_dict.get(str(reg_id_int), {
            "name": f"Region {reg_id_int}",
            "hemisphere": None,
            "lobe": "Subcortical / White Matter",
            "id": reg_id_int
        })

        involvement.append({
            "id": reg_id_int,
            "name": meta.get("name", f"Region {reg_id_int}"),
            "hemisphere": meta.get("hemisphere"),
            "lobe": meta.get("lobe", "Unknown"),
            "tumor_volume_ml": round(wt_ml, 3),
            "tc_volume_ml": round(tc_ml, 3),
            "et_volume_ml": round(et_ml, 3),
            "region_volume_ml": round(reg_ml, 3),
            "pct_of_region_involved": round(pct_of_region, 1),
            "pct_of_total_tumor": round(pct_of_tumor, 1),
            "voxels": wt_overlap
        })

    # Sort descending by tumor volume in mL
    involvement.sort(key=lambda x: x["tumor_volume_ml"], reverse=True)
    return involvement
