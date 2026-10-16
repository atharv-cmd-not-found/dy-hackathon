"""
Background processing pipeline for NeuroScope 3D.
Sequentially executes Validation -> Segmentation -> Volumetrics -> 3D Meshing.
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
import nibabel as nib

from app.config import CASES_DIR
from app.validation import validate_set, validate_expert_mask, sanity_check, ValidationError
from app.volumes import (
    compute_volumes,
    compute_voxel_volume,
    determine_laterality,
    compute_agreement_metrics,
    get_region_masks
)
from app.meshes import generate_case_meshes
from app.db import update_case_stage, save_case_results


def run_case_pipeline(case_id: str, segmenter: Any, git_commit: str = "local") -> None:
    """
    Executes the full automated analysis pipeline for a submitted case.
    Stages:
      1. validating : verifies spatial headers, shapes, and scans for corruption
      2. segmenting : executes model forward pass via Segmenter.predict()
      3. volumetrics: calculates exact volumes (mL), formulas, and laterality
      4. meshing    : generates 4 binary GLB meshes (brain, wt, tc, et)
      5. done       : commits final records to DB
    """
    case_dir = CASES_DIR / case_id
    paths = {
        "t1": case_dir / "t1.nii.gz",
        "t1gd": case_dir / "t1gd.nii.gz",
        "t2": case_dir / "t2.nii.gz",
        "flair": case_dir / "flair.nii.gz",
    }
    expert_path = case_dir / "expert.nii.gz"
    pred_path = case_dir / "pred.nii.gz"
    mesh_dir = case_dir / "meshes"
    
    stage_seconds: Dict[str, float] = {}
    
    try:
        # ================= STAGE 1: VALIDATION =================
        t0 = time.time()
        update_case_stage(case_id, status="processing", stage="validating")
        
        # Validate 4 sequences
        loaded = validate_set(paths)
        ref_img, t1_data = loaded["t1"]
        affine = ref_img.affine
        
        # Non-refusing sanity heuristics
        warnings, stats = sanity_check(loaded)
        det_vol, vol_warn = compute_voxel_volume(ref_img)
        if vol_warn:
            warnings.append({"code": "VOL_WARN", "message": vol_warn})
            
        # Optional expert mask validation
        has_expert = expert_path.exists()
        expert_data = None
        if has_expert:
            _, expert_data = validate_expert_mask(expert_path, ref_img)
            
        # Commit spatial metadata to DB
        spatial_meta = {
            "shape": list(ref_img.shape),
            "zooms": [round(float(z), 3) for z in ref_img.header.get_zooms()[:3]],
            "voxel_volume_mm3": det_vol
        }
        update_case_stage(case_id, status="processing", stage="validating", spatial_meta=spatial_meta, warnings=warnings)
        stage_seconds["validating"] = round(time.time() - t0, 3)
        
        # ================= STAGE 2: SEGMENTATION =================
        t0 = time.time()
        update_case_stage(case_id, status="processing", stage="segmenting")
        
        # Execute ML prediction via strict contract
        segmenter.predict(paths, str(pred_path))
        if not pred_path.exists():
            raise RuntimeError("Segmenter failed to produce pred.nii.gz output file.")
            
        stage_seconds["segmenting"] = round(time.time() - t0, 3)
        
        # ================= STAGE 3: VOLUMETRICS =================
        t0 = time.time()
        update_case_stage(case_id, status="processing", stage="volumetrics")
        
        pred_img = nib.load(str(pred_path))
        pred_data = np.asanyarray(pred_img.dataobj).astype(np.uint8)
        
        # Volumes & Formulas
        volumes = compute_volumes(pred_data, det_vol)
        
        # Laterality (Left vs Right relative to brain centroid)
        brain_mask = t1_data > 0.0
        masks = get_region_masks(pred_data)
        laterality = determine_laterality(masks["WT"], brain_mask, affine)
        
        # Expert mask metrics (if provided)
        expert_volumes = None
        agreement = None
        if has_expert and expert_data is not None:
            expert_volumes = compute_volumes(expert_data, det_vol)
            agreement = compute_agreement_metrics(pred_data, expert_data)
            
        stage_seconds["volumetrics"] = round(time.time() - t0, 3)
        
        # ================= STAGE 4: MESHING =================
        t0 = time.time()
        update_case_stage(case_id, status="processing", stage="meshing")
        
        generate_case_meshes(pred_data, t1_data, affine, mesh_dir)
        stage_seconds["meshing"] = round(time.time() - t0, 3)
        
        # ================= STAGE 5: COMMIT RESULTS =================
        model_info = {
            "name": getattr(segmenter, "name", "MONAI SegResNet (BraTS 2021)"),
            "version": getattr(segmenter, "version", "1.0"),
            "license": "Apache-2.0",
            "framework": "PyTorch / MONAI"
        }
        
        save_case_results(
            case_id=case_id,
            volumes=volumes,
            laterality=laterality,
            model_info=model_info,
            commit_hash=git_commit,
            expert_volumes=expert_volumes,
            agreement=agreement
        )
        
        update_case_stage(
            case_id=case_id,
            status="done",
            stage="done",
            stage_seconds=stage_seconds,
            warnings=warnings
        )
        
    except ValidationError as ve:
        update_case_stage(
            case_id=case_id,
            status="failed",
            stage="failed",
            error_code=ve.code,
            error_message=ve.message,
            failed_slot=ve.slot,
            stage_seconds=stage_seconds
        )
    except Exception as e:
        update_case_stage(
            case_id=case_id,
            status="failed",
            stage="failed",
            error_code="PIPELINE_ERROR",
            error_message=str(e),
            stage_seconds=stage_seconds
        )
