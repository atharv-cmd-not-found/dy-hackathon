"""
Unit tests for NeuroScope 3D Volumetric & Meshing Engines.
Verifies Cube Volume test, laterality, orientation stability, and GLB mesh alignment.
"""
from pathlib import Path
import pytest
import numpy as np
import nibabel as nib
import trimesh

from app.volumes import (
    compute_volumes,
    compute_voxel_volume,
    centroid_world_mm,
    determine_laterality,
    compute_agreement_metrics,
    get_region_masks
)
from app.meshes import mask_to_mesh, export_mesh_to_glb, generate_case_meshes

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_cube_volume_exact_16ml():
    """
    CRITICAL JUDGES' TEST (B2):
    20x20x20 cube of label 2 at 1x1x2 mm spacing.
    Expected:
      - Total voxels: 8,000
      - Voxel volume: 2.0 mm^3
      - WT Volume: exactly 16.000 mL (+- 1%)
      - TC Volume: 0.000 mL
      - ET Volume: 0.000 mL
    """
    cube_img = nib.load(str(FIXTURES_DIR / "cube_label.nii.gz"))
    cube_data = np.asanyarray(cube_img.dataobj).astype(np.uint8)
    
    det_vol, warning = compute_voxel_volume(cube_img)
    assert np.isclose(det_vol, 2.0, atol=1e-3)
    
    vols = compute_volumes(cube_data, det_vol)
    
    # WT must be 16.0 mL (+- 1%)
    assert vols["WT"]["voxels"] == 8000
    assert np.isclose(vols["WT"]["ml"], 16.0, rtol=0.01)
    assert "8,000 voxels × 2 mm³ / 1000 = 16.000 mL" in vols["WT"]["formula"]
    
    # TC and ET must be exactly 0
    assert vols["TC"]["voxels"] == 0
    assert vols["TC"]["ml"] == 0.0
    assert vols["ET"]["voxels"] == 0
    assert vols["ET"]["ml"] == 0.0


def test_orientation_laterality():
    """
    Verifies that centroid_world_mm accurately respects the affine matrix,
    and laterality correctly assigns 'Right' or 'Left' based on the brain centroid.
    """
    affine = np.diag([1.0, 1.0, 2.0, 1.0])
    shape = (100, 100, 80)
    
    brain_mask = np.zeros(shape, dtype=bool)
    brain_mask[20:80, 20:80, 20:60] = True  # Brain centroid at x = 49.5
    
    # Tumor placed on the Right (+x relative to brain centroid)
    tumor_right = np.zeros(shape, dtype=bool)
    tumor_right[65:80, 40:60, 30:50] = True
    
    res_right = determine_laterality(tumor_right, brain_mask, affine)
    assert res_right["side"] == "Right"
    assert res_right["delta_x_mm"] > 2.0
    
    # Tumor placed on the Left (-x relative to brain centroid)
    tumor_left = np.zeros(shape, dtype=bool)
    tumor_left[20:35, 40:60, 30:50] = True
    
    res_left = determine_laterality(tumor_left, brain_mask, affine)
    assert res_left["side"] == "Left"
    assert res_left["delta_x_mm"] < -2.0


def test_agreement_metrics():
    """Verifies Dice and Sensitivity computation."""
    # Perfect agreement
    shape = (50, 50, 50)
    mask1 = np.zeros(shape, dtype=np.uint8)
    mask1[10:20, 10:20, 10:20] = 4  # ET region
    
    metrics = compute_agreement_metrics(mask1, mask1)
    assert metrics["ET"]["dice"] == 1.0
    assert metrics["ET"]["sensitivity"] == 1.0
    assert metrics["WT"]["dice"] == 1.0
    
    # Partial agreement (50% overlap)
    mask2 = np.zeros(shape, dtype=np.uint8)
    mask2[10:20, 10:20, 15:25] = 4
    metrics_partial = compute_agreement_metrics(mask1, mask2)
    assert 0.0 < metrics_partial["ET"]["dice"] < 1.0


def test_mask_to_mesh_alignment_and_centroid():
    """
    Verifies that marching cubes mesh vertices in world mm match the mask centroid
    within <= 1.5 voxels in physical space.
    """
    cube_img = nib.load(str(FIXTURES_DIR / "cube_label.nii.gz"))
    cube_data = np.asanyarray(cube_img.dataobj).astype(np.uint8)
    affine = cube_img.affine
    
    mask = cube_data == 2
    mesh = mask_to_mesh(mask, affine, smooth_sigma=0.0, step_size=1)
    
    assert mesh is not None
    assert len(mesh.vertices) > 0
    assert len(mesh.faces) > 0
    
    # Compare mesh center of mass to voxel centroid
    mesh_centroid = mesh.centroid
    mask_centroid = centroid_world_mm(mask, affine)
    
    assert mask_centroid is not None
    # Distance between mesh centroid and mask centroid should be <= 1.5 mm
    dist = np.linalg.norm(mesh_centroid - mask_centroid)
    assert dist <= 1.5, f"Mesh centroid {mesh_centroid} differs from mask centroid {mask_centroid} by {dist} mm"


def test_glb_export(tmp_path):
    """Verifies that generated GLB file is a valid binary glTF file."""
    cube_img = nib.load(str(FIXTURES_DIR / "cube_label.nii.gz"))
    cube_data = np.asanyarray(cube_img.dataobj).astype(np.uint8)
    affine = cube_img.affine
    
    mask = cube_data == 2
    mesh = mask_to_mesh(mask, affine, smooth_sigma=0.5)
    assert mesh is not None
    
    glb_path = tmp_path / "test_cube.glb"
    export_mesh_to_glb(mesh, glb_path)
    
    assert glb_path.exists()
    assert glb_path.stat().st_size > 0
    
    # Check binary glTF header: first 4 bytes must be b'glTF'
    with open(glb_path, "rb") as f:
        magic = f.read(4)
    assert magic == b"glTF", f"Expected GLB magic b'glTF', got {magic}"


def test_generate_case_meshes(tmp_path):
    """Verifies the complete 4-mesh generation pipeline."""
    base_t1 = nib.load(str(FIXTURES_DIR / "base_t1.nii.gz"))
    t1_data = np.asanyarray(base_t1.dataobj).astype(np.float32)
    affine = base_t1.affine
    
    # Synthetic tumor mask with WT, TC, ET labels
    pred_data = np.zeros_like(t1_data, dtype=np.uint8)
    pred_data[40:50, 40:50, 30:40] = 2  # ED (part of WT)
    pred_data[43:47, 43:47, 33:37] = 1  # NCR (part of TC, WT)
    pred_data[45:47, 45:47, 35:37] = 4  # ET (part of ET, TC, WT)
    
    case_out = tmp_path / "case_meshes"
    meshes = generate_case_meshes(pred_data, t1_data, affine, case_out)
    
    assert "brain" in meshes and meshes["brain"] is not None
    assert "wt" in meshes and meshes["wt"] is not None
    assert "tc" in meshes and meshes["tc"] is not None
    assert "et" in meshes and meshes["et"] is not None
    
    for region in ["brain", "wt", "tc", "et"]:
        entry = meshes[region]
        assert Path(entry["path"]).exists()
        assert entry["vertices"] > 0
        assert entry["faces"] > 0
