"""
Anatomical Mapper for NeuroScope 3D.
Provides:
- Mode A (Atlas lookup): verifies template space alignment, calculates per-region
  involvement for WT, TC, and ET, primary/secondary regions, and an explicit
  'Outside atlas / unlabelled' row so percentages sum to 100%.
- Mode B (Coarse geometric fallback): divides brain extent into thirds (anterior/posterior,
  superior/inferior) and determines hemisphere from world coordinates relative to centroid.
- Three trainee Answer Cards:
  1. "One mass or several?": 26-connectivity connected components of WT (> min volume).
  2. "Which side?": hemisphere from WT centroid in RAS world coordinates + orientation code.
  3. "How big?": WT/TC/ET estimated volumes with formula and actual numbers.
"""

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import nibabel as nib
import numpy as np
import scipy.ndimage

from .config import LocalizationConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class AnswerCardComponents:
    title: str = "One mass or several?"
    count: int = 0
    components: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""


@dataclass
class AnswerCardSide:
    title: str = "Which side?"
    hemisphere: str = "Unknown"
    centroid_ras_mm: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    affine_orientation: str = ""
    summary: str = ""


@dataclass
class AnswerCardVolume:
    title: str = "How big?"
    formula: str = "estimated volume (mL) = voxels × |det(affine[:3,:3])| / 1000"
    voxel_volume_mm3: float = 1.0
    wt_voxels: int = 0
    wt_volume_ml: float = 0.0
    tc_voxels: int = 0
    tc_volume_ml: float = 0.0
    et_voxels: int = 0
    et_volume_ml: float = 0.0
    summary: str = ""


@dataclass
class LocalizationResult:
    status: str  # "available", "low_confidence", "unavailable"
    mode: str    # "Mode A (Atlas Lookup)" or "Mode B (Coarse Geometric Fallback)"
    quality_message: str
    overlap_dice: float
    space_check: Dict[str, Any]
    answer_cards: Dict[str, Any]
    table: List[Dict[str, Any]]
    primary_regions: Dict[str, Optional[str]]
    secondary_regions: Dict[str, List[str]]
    mode_b_data: Optional[Dict[str, Any]] = None
    atlas_metadata: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "quality_message": self.quality_message,
            "overlap_dice": round(self.overlap_dice, 4),
            "space_check": self.space_check,
            "answer_cards": self.answer_cards,
            "table": self.table,
            "primary_regions": self.primary_regions,
            "secondary_regions": self.secondary_regions,
            "mode_b_data": self.mode_b_data,
            "atlas_metadata": self.atlas_metadata,
            "warnings": self.warnings,
        }


class AnatomicalMapper:
    """Core localization engine executing Mode A, Mode B, and Answer Cards."""

    def __init__(self, config: Optional[LocalizationConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self._atlas_img: Optional[nib.Nifti1Image] = None
        self._atlas_data: Optional[np.ndarray] = None
        self._atlas_labels: Optional[Dict[str, Any]] = None
        self._load_atlas_cache()

    def _load_atlas_cache(self):
        """Loads bundled atlas volume and canonical label metadata."""
        atlas_nii_path = self.config.atlas_dir / self.config.atlas_nii_name
        labels_path = self.config.atlas_dir / self.config.atlas_labels_name

        if atlas_nii_path.exists():
            try:
                self._atlas_img = nib.load(str(atlas_nii_path))
                self._atlas_data = np.asanyarray(self._atlas_img.dataobj).astype(np.int32)
            except Exception as e:
                logger.warning(f"Could not load atlas NIfTI {atlas_nii_path}: {e}")

        if labels_path.exists():
            try:
                with open(labels_path, "r", encoding="utf-8") as f:
                    self._atlas_labels = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load atlas labels {labels_path}: {e}")

    def get_canonical_region_name(self, label_id: int) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Maps an integer label ID to a canonical anatomical region name.
        Supported regions: left/right frontal, parietal, temporal, occipital,
        insula, cerebellum, basal ganglia, thalamus; brainstem; corpus callosum; ventricles.
        Returns: (canonical_name, hemisphere, lobe)
        """
        if label_id == 0 or not self._atlas_labels:
            return ("Outside atlas / unlabelled", None, None)

        labels_dict = self._atlas_labels.get("labels", {})
        meta = labels_dict.get(str(label_id))
        if not meta:
            return (f"Atlas Structure #{label_id}", None, None)

        name = meta.get("name", "")
        name_lower = name.lower()
        hemi = meta.get("hemisphere")  # "Left", "Right", "Midline", or None
        lobe = meta.get("lobe")

        # Canonical group assignment according to specification
        if "thalam" in name_lower:
            canonical = f"{hemi} Thalamus".strip() if hemi else "Thalamus"
        elif any(bg in name_lower for bg in ["caudate", "putamen", "pallid", "striatum"]):
            canonical = f"{hemi} Basal Ganglia".strip() if hemi else "Basal Ganglia"
        elif "corpus callosum" in name_lower or "callos" in name_lower:
            canonical = "Corpus Callosum"
        elif any(bs in name_lower for bs in ["brainstem", "pons", "medulla", "midbrain"]):
            canonical = "Brainstem"
        elif "ventricle" in name_lower or lobe == "Ventricular System":
            canonical = "Ventricles"
        elif lobe in ["Frontal Lobe", "Parietal Lobe", "Temporal Lobe", "Occipital Lobe", "Insular Cortex", "Cerebellum"]:
            canonical = f"{hemi} {lobe}".strip() if hemi else lobe
        elif lobe:
            canonical = f"{hemi} {lobe}".strip() if hemi else lobe
        else:
            canonical = f"{hemi} {name}".strip() if hemi else name

        return (canonical, hemi, lobe)

    def calculate_voxel_volume_mm3(self, affine: np.ndarray, header: Optional[nib.Nifti1Header] = None) -> Tuple[float, List[str]]:
        """
        Calculates voxel volume in mm3 using |det(affine[:3, :3])|.
        Emits warning if it disagrees with header zooms.
        """
        warnings = []
        det_vol = abs(float(np.linalg.det(affine[:3, :3])))
        if header is not None:
            try:
                zooms = header.get_zooms()[:3]
                zoom_vol = float(np.prod(zooms))
                if abs(det_vol - zoom_vol) > 1e-2:
                    warnings.append(
                        f"Affine determinant volume ({det_vol:.4f} mm³) differs from header zooms product ({zoom_vol:.4f} mm³)."
                    )
            except Exception:
                pass
        return det_vol, warnings

    def compute_answer_cards(
        self,
        pred_data: np.ndarray,
        affine: np.ndarray,
        voxel_volume_mm3: float,
        brain_centroid_ras: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Computes the three trainee Answer Cards:
        1. "One mass or several?": 26-connectivity connected components of WT (> min_component_volume_ml).
        2. "Which side?": hemisphere from WT centroid in RAS world coordinates + affine orientation.
        3. "How big?": WT/TC/ET estimated volumes with formula and actual numbers.
        """
        wt_mask = (pred_data > 0)
        tc_mask = np.isin(pred_data, [1, 4])
        et_mask = (pred_data == 4)

        wt_voxels = int(wt_mask.sum())
        tc_voxels = int(tc_mask.sum())
        et_voxels = int(et_mask.sum())

        wt_ml = (wt_voxels * voxel_volume_mm3) / 1000.0
        tc_ml = (tc_voxels * voxel_volume_mm3) / 1000.0
        et_ml = (et_voxels * voxel_volume_mm3) / 1000.0

        # --- Card 1: One mass or several? ---
        if wt_voxels == 0:
            card1 = {
                "title": "One mass or several?",
                "count": 0,
                "components": [],
                "summary": "No suspected tumour region predicted by the model."
            }
        else:
            # 26-connectivity in 3D: 3x3x3 structuring element
            structure_26 = np.ones((3, 3, 3), dtype=bool)
            labeled_array, num_features = scipy.ndimage.label(wt_mask, structure=structure_26)

            filtered_components = []
            for comp_id in range(1, num_features + 1):
                comp_mask = (labeled_array == comp_id)
                c_voxels = int(comp_mask.sum())
                c_ml = (c_voxels * voxel_volume_mm3) / 1000.0

                if c_ml >= self.config.min_component_volume_ml or num_features == 1:
                    # Compute component centroid
                    coords = np.argwhere(comp_mask)
                    vox_c = coords.mean(axis=0)
                    world_c = affine @ np.append(vox_c, 1.0)
                    filtered_components.append({
                        "id": comp_id,
                        "voxels": c_voxels,
                        "volume_ml": round(c_ml, 3),
                        "centroid_vox": [round(float(v), 2) for v in vox_c],
                        "centroid_ras_mm": [round(float(w), 2) for w in world_c[:3]]
                    })

            # Sort descending by volume
            filtered_components.sort(key=lambda x: x["volume_ml"], reverse=True)
            comp_count = len(filtered_components)

            if comp_count == 0:
                summary1 = "No distinct mass meeting the minimum volume threshold (0.1 mL) predicted."
            elif comp_count == 1:
                summary1 = f"Single mass predicted (estimated volume: {filtered_components[0]['volume_ml']:.2f} mL)."
            else:
                largest_ml = filtered_components[0]["volume_ml"]
                summary1 = f"Multifocal: {comp_count} distinct masses predicted (largest: {largest_ml:.2f} mL)."

            card1 = {
                "title": "One mass or several?",
                "count": comp_count,
                "components": filtered_components,
                "summary": summary1
            }

        # --- Card 2: Which side? ---
        try:
            axcodes = "".join(nib.aff2axcodes(affine))
        except Exception:
            axcodes = "Unknown"

        if wt_voxels == 0:
            card2 = {
                "title": "Which side?",
                "hemisphere": "None",
                "centroid_ras_mm": [0.0, 0.0, 0.0],
                "affine_orientation": axcodes,
                "summary": "No suspected tumour region predicted by the model."
            }
        else:
            wt_coords = np.argwhere(wt_mask)
            vox_center = wt_coords.mean(axis=0)
            world_center = affine @ np.append(vox_center, 1.0)
            ras_x = float(world_center[0])

            # In RAS+ world space: +x is Right, -x is Left.
            # Compare relative to brain centroid x if available, else volume center in world space.
            if brain_centroid_ras is not None:
                ref_x = float(brain_centroid_ras[0])
            else:
                center_vox = np.array(pred_data.shape, dtype=float) / 2.0
                ref_x = float((affine @ np.append(center_vox, 1.0))[0])
            diff_x = ras_x - ref_x

            if abs(diff_x) <= self.config.midline_band_mm:
                hemi_str = "Midline / Bilateral"
                hemi_summary = f"Predicted mass is centered near the midline (world x: {ras_x:.1f} mm, affine: {axcodes})."
            elif diff_x > self.config.midline_band_mm:
                hemi_str = "Right Hemisphere"
                hemi_summary = f"Predicted mass is located in the Right Hemisphere (world x: {ras_x:.1f} mm, affine: {axcodes})."
            else:
                hemi_str = "Left Hemisphere"
                hemi_summary = f"Predicted mass is located in the Left Hemisphere (world x: {ras_x:.1f} mm, affine: {axcodes})."

            card2 = {
                "title": "Which side?",
                "hemisphere": hemi_str,
                "centroid_ras_mm": [round(float(c), 2) for c in world_center[:3]],
                "affine_orientation": axcodes,
                "summary": hemi_summary
            }

        # --- Card 3: How big? ---
        formula_str = f"estimated volume (mL) = voxels × {voxel_volume_mm3:.4f} mm³ / 1000"
        card3 = {
            "title": "How big?",
            "formula": formula_str,
            "voxel_volume_mm3": round(voxel_volume_mm3, 4),
            "wt_voxels": wt_voxels,
            "wt_volume_ml": round(wt_ml, 3),
            "tc_voxels": tc_voxels,
            "tc_volume_ml": round(tc_ml, 3),
            "et_voxels": et_voxels,
            "et_volume_ml": round(et_ml, 3),
            "summary": (
                f"WT: {wt_ml:.2f} mL ({wt_voxels:,} voxels), "
                f"TC: {tc_ml:.2f} mL ({tc_voxels:,} voxels), "
                f"ET: {et_ml:.2f} mL ({et_voxels:,} voxels)."
            )
        }

        return {
            "card_one_mass_or_several": card1,
            "card_which_side": card2,
            "card_how_big": card3,
        }

    def compute_mode_b_coarse(
        self,
        pred_data: np.ndarray,
        t1gd_data: np.ndarray,
        affine: np.ndarray
    ) -> Dict[str, Any]:
        """
        Mode B: Coarse geometric fallback (always works, clearly labelled).
        Does NOT name lobes. Reports hemisphere, anterior/posterior thirds,
        and superior/inferior thirds based on brain bounding box extent in world coordinates.
        """
        wt_mask = (pred_data > 0)
        brain_mask = (t1gd_data > 0)
        if not brain_mask.any():
            brain_mask = np.ones_like(pred_data, dtype=bool)

        brain_coords = np.argwhere(brain_mask)
        b_min_vox = brain_coords.min(axis=0)
        b_max_vox = brain_coords.max(axis=0)

        # Get world bounds of brain
        corners = np.array([
            [b_min_vox[0], b_min_vox[1], b_min_vox[2], 1.0],
            [b_max_vox[0], b_max_vox[1], b_max_vox[2], 1.0],
        ])
        corners_world = (affine @ corners.T).T[:, :3]
        w_min = np.minimum(corners_world[0], corners_world[1])
        w_max = np.maximum(corners_world[0], corners_world[1])

        # Centroid of brain
        brain_vox_c = brain_coords.mean(axis=0)
        brain_world_c = affine @ np.append(brain_vox_c, 1.0)

        if not wt_mask.any():
            return {
                "title": "Approximate coarse position (no atlas available)",
                "hemisphere": "None",
                "anterior_posterior": "None",
                "superior_inferior": "None",
                "summary": "No suspected tumour region predicted by the model.",
                "brain_extent_world": {
                    "min": [round(float(v), 1) for v in w_min],
                    "max": [round(float(v), 1) for v in w_max],
                    "centroid": [round(float(v), 1) for v in brain_world_c[:3]]
                }
            }

        wt_coords = np.argwhere(wt_mask)
        wt_vox_c = wt_coords.mean(axis=0)
        wt_world_c = affine @ np.append(wt_vox_c, 1.0)

        # 1. Hemisphere: sign of (x - brain_center_x)
        diff_x = wt_world_c[0] - brain_world_c[0]
        if abs(diff_x) <= self.config.midline_band_mm:
            hemi = "Midline / Bilateral"
        elif diff_x > self.config.midline_band_mm:
            hemi = "Right Hemisphere"
        else:
            hemi = "Left Hemisphere"

        # 2. Anterior / Posterior: world y divided into thirds (+y is Anterior in RAS+)
        y_span = w_max[1] - w_min[1]
        y_rel = (wt_world_c[1] - w_min[1]) / (y_span if y_span > 0 else 1.0)
        if y_rel < 0.333:
            ap = "Posterior third"
        elif y_rel < 0.666:
            ap = "Middle third"
        else:
            ap = "Anterior third"

        # 3. Superior / Inferior: world z divided into thirds (+z is Superior in RAS+)
        z_span = w_max[2] - w_min[2]
        z_rel = (wt_world_c[2] - w_min[2]) / (z_span if z_span > 0 else 1.0)
        if z_rel < 0.333:
            si = "Inferior third"
        elif z_rel < 0.666:
            si = "Middle third"
        else:
            si = "Superior third"

        summary = f"Approximate position: {hemi}, {ap}, {si}."
        return {
            "title": "Approximate coarse position (no atlas available)",
            "hemisphere": hemi,
            "anterior_posterior": ap,
            "superior_inferior": si,
            "summary": summary,
            "wt_centroid_world": [round(float(v), 1) for v in wt_world_c[:3]],
            "brain_extent_world": {
                "min": [round(float(v), 1) for v in w_min],
                "max": [round(float(v), 1) for v in w_max],
                "centroid": [round(float(v), 1) for v in brain_world_c[:3]]
            }
        }

    def check_template_space_alignment(
        self,
        ref_shape: Tuple[int, ...],
        ref_affine: np.ndarray,
        t1gd_data: np.ndarray
    ) -> Tuple[str, str, float, Dict[str, Any]]:
        """
        Verifies whether the input scan matches the SRI24 template space:
        1. Shape equal
        2. Affine equal within tolerance
        3. Brain mask (t1gd > 0) overlaps atlas brain mask with Dice >= threshold.
        Returns: (status, message, dice_score, check_details)
        """
        if self._atlas_img is None or self._atlas_data is None:
            return (
                "unavailable",
                "Anatomical localization unavailable: atlas resource files not found on server.",
                0.0,
                {"error": "atlas_missing"}
            )

        atlas_shape = tuple(self._atlas_img.shape[:3])
        target_shape = tuple(ref_shape[:3])
        shapes_match = (atlas_shape == target_shape)

        atlas_affine = self._atlas_img.affine
        affine_diff = float(np.max(np.abs(atlas_affine - ref_affine)))
        affines_match = affine_diff <= self.config.affine_tolerance

        if not shapes_match or not affines_match:
            msg = "Anatomical localization unavailable: input grid or affine does not match SRI24 template space."
            check_details = {
                "atlas_shape": list(atlas_shape),
                "target_shape": list(target_shape),
                "shapes_match": shapes_match,
                "affine_max_diff": round(affine_diff, 6),
                "affine_tolerance": self.config.affine_tolerance,
                "affines_match": affines_match,
                "overlap_dice": 0.0,
                "min_dice_available": self.config.min_dice_available,
                "min_dice_low_confidence": self.config.min_dice_low_confidence,
            }
            return ("unavailable", msg, 0.0, check_details)

        # Brain tissue Dice overlap (only computed when shapes and grids match)
        patient_brain = (t1gd_data > 0)
        atlas_brain = (self._atlas_data > 0)

        p_sum = int(patient_brain.sum())
        a_sum = int(atlas_brain.sum())
        if p_sum + a_sum == 0:
            dice = 0.0
        else:
            intersection = int(np.logical_and(patient_brain, atlas_brain).sum())
            dice = float(2.0 * intersection / (p_sum + a_sum))

        check_details = {
            "atlas_shape": list(atlas_shape),
            "target_shape": list(target_shape),
            "shapes_match": shapes_match,
            "affine_max_diff": round(affine_diff, 6),
            "affine_tolerance": self.config.affine_tolerance,
            "affines_match": affines_match,
            "overlap_dice": round(dice, 4),
            "min_dice_available": self.config.min_dice_available,
            "min_dice_low_confidence": self.config.min_dice_low_confidence,
        }

        if dice >= self.config.min_dice_available:
            status = "available"
            msg = f"Patient scan verified aligned to SRI24 template space (brain overlap Dice: {dice:.3f})."
        elif dice >= self.config.min_dice_low_confidence:
            status = "low_confidence"
            msg = (
                f"Marginal template alignment (brain overlap Dice: {dice:.3f}). "
                f"Anatomical localization shown with low confidence."
            )
        else:
            status = "unavailable"
            msg = "Anatomical localization unavailable: input is not in the atlas template space."

        return (status, msg, dice, check_details)

    def localize_case(
        self,
        pred_data: np.ndarray,
        t1gd_data: np.ndarray,
        affine: np.ndarray,
        header: Optional[nib.Nifti1Header] = None
    ) -> LocalizationResult:
        """
        Executes full anatomical localization:
        - Checks template space alignment.
        - If available or low_confidence: runs Mode A atlas lookup.
        - If unavailable: runs Mode B coarse geometric fallback.
        - Computes the 3 trainee Answer Cards in both modes.
        - Guarantees zero crashes and complete determinism.
        """
        warnings = []
        voxel_vol, vol_warnings = self.calculate_voxel_volume_mm3(affine, header)
        warnings.extend(vol_warnings)

        # Brain center of mass for reference
        brain_mask = (t1gd_data > 0)
        brain_centroid_ras = None
        if brain_mask.any():
            bc_vox = np.argwhere(brain_mask).mean(axis=0)
            brain_centroid_ras = (affine @ np.append(bc_vox, 1.0))[:3]

        # 1. Answer Cards (always computed directly from prediction on original grid)
        answer_cards = self.compute_answer_cards(
            pred_data=pred_data,
            affine=affine,
            voxel_volume_mm3=voxel_vol,
            brain_centroid_ras=brain_centroid_ras
        )

        # 2. Check Space Alignment
        status, quality_msg, dice, check_details = self.check_template_space_alignment(
            ref_shape=pred_data.shape,
            ref_affine=affine,
            t1gd_data=t1gd_data
        )

        wt_mask = (pred_data > 0)
        tc_mask = np.isin(pred_data, [1, 4])
        et_mask = (pred_data == 4)

        total_wt_voxels = int(wt_mask.sum())
        total_tc_voxels = int(tc_mask.sum())
        total_et_voxels = int(et_mask.sum())

        wt_total_ml = (total_wt_voxels * voxel_vol) / 1000.0
        tc_total_ml = (total_tc_voxels * voxel_vol) / 1000.0
        et_total_ml = (total_et_voxels * voxel_vol) / 1000.0

        atlas_meta = {
            "atlas_name": "SRI24 Multi-Channel Atlas (TZO116+)",
            "license": "CC BY-SA 3.0",
            "citation": "Rohlfing et al. Human Brain Mapping 2010; 31(5):798-819",
            "coordinate_space": "SRI24 / RAS+ mm",
            "disclaimer": self.config.section_disclaimer
        }

        # If UNAVAILABLE -> Fall back to Mode B
        if status == "unavailable":
            mode_b_info = self.compute_mode_b_coarse(pred_data, t1gd_data, affine)
            return LocalizationResult(
                status="unavailable",
                mode="Mode B (Coarse Geometric Fallback)",
                quality_message=quality_msg,
                overlap_dice=dice,
                space_check=check_details,
                answer_cards=answer_cards,
                table=[],
                primary_regions={"WT": None, "TC": None, "ET": None},
                secondary_regions={"WT": [], "TC": [], "ET": []},
                mode_b_data=mode_b_info,
                atlas_metadata=atlas_meta,
                warnings=warnings
            )

        # MODE A: ATLAS LOOKUP
        # If mask is empty, handle cleanly without NaN or blank
        if total_wt_voxels == 0:
            empty_table = [
                {
                    "region": "Outside atlas / unlabelled",
                    "wt_voxels": 0, "wt_pct": 100.0, "wt_ml": 0.0,
                    "tc_voxels": 0, "tc_pct": 100.0, "tc_ml": 0.0,
                    "et_voxels": 0, "et_pct": 100.0, "et_ml": 0.0,
                    "centroid_ras_mm": [0.0, 0.0, 0.0],
                }
            ]
            return LocalizationResult(
                status=status,
                mode="Mode A (Atlas Lookup)",
                quality_message=quality_msg,
                overlap_dice=dice,
                space_check=check_details,
                answer_cards=answer_cards,
                table=empty_table,
                primary_regions={"WT": "No suspected tumour region predicted", "TC": "No suspected tumour core predicted", "ET": "No suspected enhancing tumour predicted"},
                secondary_regions={"WT": [], "TC": [], "ET": []},
                mode_b_data=None,
                atlas_metadata=atlas_meta,
                warnings=warnings
            )

        atlas_labels = self._atlas_data

        # Find all unique non-zero label IDs under WT mask
        wt_labels = atlas_labels[wt_mask]
        unique_labels = np.unique(wt_labels)

        # Group voxels by canonical region name to aggregate sub-structures into major lobes/regions
        # Map: canonical_region_name -> {wt_voxels, tc_voxels, et_voxels, coords_list}
        grouped_regions: Dict[str, Dict[str, Any]] = {}

        for lab_id in unique_labels:
            lab_int = int(lab_id)
            reg_name, hemi, lobe = self.get_canonical_region_name(lab_int)

            reg_mask = (atlas_labels == lab_int)
            overlap_wt = int(np.logical_and(reg_mask, wt_mask).sum())
            overlap_tc = int(np.logical_and(reg_mask, tc_mask).sum())
            overlap_et = int(np.logical_and(reg_mask, et_mask).sum())

            if overlap_wt == 0 and overlap_tc == 0 and overlap_et == 0:
                continue

            if reg_name not in grouped_regions:
                grouped_regions[reg_name] = {
                    "region": reg_name,
                    "hemisphere": hemi,
                    "lobe": lobe,
                    "wt_voxels": 0,
                    "tc_voxels": 0,
                    "et_voxels": 0,
                    "coords": []
                }

            grouped_regions[reg_name]["wt_voxels"] += overlap_wt
            grouped_regions[reg_name]["tc_voxels"] += overlap_tc
            grouped_regions[reg_name]["et_voxels"] += overlap_et

            # Sample coords for centroid calculation
            overlap_vox = np.argwhere(np.logical_and(reg_mask, wt_mask))
            if len(overlap_vox) > 0:
                grouped_regions[reg_name]["coords"].append(overlap_vox)

        # Calculate "Outside atlas / unlabelled" row
        # Outside atlas voxels = voxels where atlas_labels == 0
        outside_wt = int(np.logical_and(atlas_labels == 0, wt_mask).sum())
        outside_tc = int(np.logical_and(atlas_labels == 0, tc_mask).sum())
        outside_et = int(np.logical_and(atlas_labels == 0, et_mask).sum())

        # Build table rows with exact percentages and volumes
        table_rows = []
        for reg_name, data in grouped_regions.items():
            if reg_name == "Outside atlas / unlabelled":
                continue

            wt_v = data["wt_voxels"]
            tc_v = data["tc_voxels"]
            et_v = data["et_voxels"]

            wt_pct = (wt_v / total_wt_voxels * 100.0) if total_wt_voxels > 0 else 0.0
            tc_pct = (tc_v / total_tc_voxels * 100.0) if total_tc_voxels > 0 else 0.0
            et_pct = (et_v / total_et_voxels * 100.0) if total_et_voxels > 0 else 0.0

            # Calculate centroid of overlap in RAS world mm
            all_coords = np.vstack(data["coords"]) if data["coords"] else np.zeros((1, 3))
            c_vox = all_coords.mean(axis=0)
            c_world = (affine @ np.append(c_vox, 1.0))[:3]

            table_rows.append({
                "region": reg_name,
                "hemisphere": data["hemisphere"],
                "lobe": data["lobe"],
                "wt_voxels": wt_v,
                "wt_pct": round(wt_pct, 1),
                "wt_ml": round(wt_v * voxel_vol / 1000.0, 3),
                "tc_voxels": tc_v,
                "tc_pct": round(tc_pct, 1),
                "tc_ml": round(tc_v * voxel_vol / 1000.0, 3),
                "et_voxels": et_v,
                "et_pct": round(et_pct, 1),
                "et_ml": round(et_v * voxel_vol / 1000.0, 3),
                "centroid_ras_mm": [round(float(v), 2) for v in c_world],
            })

        # Sort named regions descending by WT %
        table_rows.sort(key=lambda x: x["wt_pct"], reverse=True)

        # Identify Primary and Secondary Regions from all named regions
        # Primary = highest percentage named region
        # Secondary = other named regions with >= config.secondary_min_pct (10%)
        def find_prim_sec(rows, pct_key, total_count):
            if total_count == 0:
                return (None, [])
            valid_named = [r for r in rows if r["region"] != "Outside atlas / unlabelled" and r[pct_key] > 0]
            if not valid_named:
                return ("Outside atlas / unlabelled", [])
            valid_named_sorted = sorted(valid_named, key=lambda x: x[pct_key], reverse=True)
            primary = valid_named_sorted[0]["region"]
            secondary = [
                r["region"] for r in valid_named_sorted[1:]
                if r[pct_key] >= self.config.secondary_min_pct
            ]
            return (primary, secondary)

        prim_wt, sec_wt = find_prim_sec(table_rows, "wt_pct", total_wt_voxels)
        prim_tc, sec_tc = find_prim_sec(table_rows, "tc_pct", total_tc_voxels)
        prim_et, sec_et = find_prim_sec(table_rows, "et_pct", total_et_voxels)

        # Filter display table to rows >= table_min_pct, plus outside atlas row
        display_table = [r for r in table_rows if r["wt_pct"] >= self.config.table_min_pct]

        # Outside atlas row: explicit row guaranteeing displayed table sums to exactly 100.0%
        named_display_wt = sum(r["wt_pct"] for r in display_table)
        outside_wt_pct = round(max(0.0, 100.0 - named_display_wt), 1)

        named_display_tc = sum(r["tc_pct"] for r in display_table)
        outside_tc_pct = round(max(0.0, 100.0 - named_display_tc), 1) if total_tc_voxels > 0 else 0.0

        named_display_et = sum(r["et_pct"] for r in display_table)
        outside_et_pct = round(max(0.0, 100.0 - named_display_et), 1) if total_et_voxels > 0 else 0.0

        outside_row = {
            "region": "Outside atlas / unlabelled",
            "hemisphere": None,
            "lobe": None,
            "wt_voxels": outside_wt,
            "wt_pct": outside_wt_pct,
            "wt_ml": round(outside_wt * voxel_vol / 1000.0, 3),
            "tc_voxels": outside_tc,
            "tc_pct": outside_tc_pct,
            "tc_ml": round(outside_tc * voxel_vol / 1000.0, 3),
            "et_voxels": outside_et,
            "et_pct": outside_et_pct,
            "et_ml": round(outside_et * voxel_vol / 1000.0, 3),
            "centroid_ras_mm": [0.0, 0.0, 0.0],
        }
        display_table.append(outside_row)

        return LocalizationResult(
            status=status,
            mode="Mode A (Atlas Lookup)",
            quality_message=quality_msg,
            overlap_dice=dice,
            space_check=check_details,
            answer_cards=answer_cards,
            table=display_table,
            primary_regions={"WT": prim_wt, "TC": prim_tc, "ET": prim_et},
            secondary_regions={"WT": sec_wt, "TC": sec_tc, "ET": sec_et},
            mode_b_data=None,
            atlas_metadata=atlas_meta,
            warnings=warnings
        )
