"""
Volumetric calculation and anatomical geometry engine for NeuroScope 3D.
Implements exact volume formulas, BraTS 2021 region masking,
world-space centroid calculations, and relative laterality estimation.
"""
from typing import Dict, Any, Tuple, Optional
import numpy as np
import nibabel as nib


def get_region_masks(label_array: np.ndarray) -> Dict[str, np.ndarray]:
    """
    Extracts binary boolean masks for BraTS 2021 evaluation regions:
      - WT (Whole Tumor): label > 0 (combines NCR=1, ED=2, ET=4)
      - TC (Tumor Core): label == 1 | label == 4 (NCR + ET)
      - ET (Enhancing Tumor): label == 4
    """
    return {
        "WT": label_array > 0,
        "TC": (label_array == 1) | (label_array == 4),
        "ET": label_array == 4
    }


def compute_voxel_volume(img: nib.Nifti1Image) -> Tuple[float, Optional[str]]:
    """
    Computes exact voxel volume in mm^3 using the spatial affine matrix determinant.
    Cross-checks against header zooms and warns if they diverge by >1%.
    """
    aff = img.affine
    det_vol = abs(float(np.linalg.det(aff[:3, :3])))
    
    zooms = img.header.get_zooms()[:3]
    zooms_vol = float(np.prod(zooms))
    
    warning = None
    if det_vol > 0 and abs(det_vol - zooms_vol) / det_vol > 0.01:
        warning = (
            f"Voxel volume from header zooms ({zooms_vol:.3f} mm³) differs from "
            f"affine determinant ({det_vol:.3f} mm³). Using affine determinant as ground truth."
        )
    return det_vol, warning


def compute_volumes(
    label_array: np.ndarray,
    voxel_volume_mm3: float
) -> Dict[str, Dict[str, Any]]:
    """
    Computes volume (mL) and formatting formulas for each BraTS tumor region.
    Formula: Volume [mL] = (voxel_count * voxel_volume_mm^3) / 1000.0
    """
    masks = get_region_masks(label_array)
    out: Dict[str, Dict[str, Any]] = {}
    
    for name, mask in masks.items():
        n_voxels = int(mask.sum())
        vol_ml = (n_voxels * voxel_volume_mm3) / 1000.0
        out[name] = {
            "voxels": n_voxels,
            "voxel_mm3": round(voxel_volume_mm3, 4),
            "ml": round(vol_ml, 3),
            "formula": f"{n_voxels:,} voxels × {voxel_volume_mm3:g} mm³ / 1000 = {vol_ml:.3f} mL"
        }
    return out


def centroid_world_mm(mask: np.ndarray, affine: np.ndarray) -> Optional[np.ndarray]:
    """
    Computes the 3D center-of-mass (centroid) of a mask in World Coordinates (RAS+ mm).
    Formula: C_world = Affine @ [i_mean, j_mean, k_mean, 1]^T
    """
    if not np.any(mask):
        return None
    coords = np.argwhere(mask)
    voxel_centroid = coords.mean(axis=0)
    world_pt = nib.affines.apply_affine(affine, voxel_centroid)
    return np.asarray(world_pt, dtype=np.float64)


def determine_laterality(
    tumor_mask: np.ndarray,
    brain_mask: np.ndarray,
    affine: np.ndarray,
    midline_tolerance_mm: float = 2.0
) -> Dict[str, Any]:
    """
    Estimates the laterality (Left vs Right side) of the suspected tumor.
    Calculates Δx relative to the brain tissue centroid (RAS+ space: +x is Right, -x is Left).
    """
    t_centroid = centroid_world_mm(tumor_mask, affine)
    b_centroid = centroid_world_mm(brain_mask, affine)
    
    if t_centroid is None:
        return {
            "side": "None",
            "delta_x_mm": 0.0,
            "note": "no suspected tumor region found"
        }
    
    if b_centroid is None:
        # Fallback to origin if no brain tissue mask available
        b_x = 0.0
    else:
        b_x = b_centroid[0]
        
    delta_x = float(t_centroid[0] - b_x)
    
    if abs(delta_x) <= midline_tolerance_mm:
        side = "Near Midline"
        note = f"within ±{midline_tolerance_mm} mm of anatomical brain midline"
    elif delta_x > 0:
        side = "Right"
        note = "image-based estimate relative to brain centroid"
    else:
        side = "Left"
        note = "image-based estimate relative to brain centroid"
        
    return {
        "side": side,
        "delta_x_mm": round(delta_x, 2),
        "tumor_centroid_mm": [round(float(c), 2) for c in t_centroid],
        "brain_centroid_mm": [round(float(c), 2) for c in b_centroid] if b_centroid is not None else None,
        "note": note
    }


def compute_agreement_metrics(
    pred_label: np.ndarray,
    expert_label: np.ndarray
) -> Dict[str, Dict[str, float]]:
    """
    Computes Dice similarity and Sensitivity (Recall) between predicted and expert masks
    for regions WT, TC, and ET.
    """
    pred_masks = get_region_masks(pred_label)
    expert_masks = get_region_masks(expert_label)
    
    results: Dict[str, Dict[str, float]] = {}
    
    for region in ["WT", "TC", "ET"]:
        p = pred_masks[region]
        g = expert_masks[region]
        
        intersection = int(np.logical_and(p, g).sum())
        p_sum = int(p.sum())
        g_sum = int(g.sum())
        
        # Dice calculation
        if p_sum + g_sum == 0:
            dice = 1.0  # Perfect agreement on absence
        else:
            dice = (2.0 * intersection) / (p_sum + g_sum)
            
        # Sensitivity calculation (TP / (TP + FN))
        if g_sum == 0:
            sensitivity = 1.0 if p_sum == 0 else 0.0
        else:
            sensitivity = intersection / g_sum
            
        results[region] = {
            "dice": round(float(dice), 4),
            "sensitivity": round(float(sensitivity), 4)
        }
        
    return results
