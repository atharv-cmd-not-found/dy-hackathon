"""
3D Mesh generation and GLB export engine for NeuroScope 3D.
Implements voxel-space Marching Cubes, spatial affine transformation,
polygon normal winding correction, and binary GLB export for Three.js.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np
import nibabel as nib
import trimesh
from skimage.measure import marching_cubes
from scipy.ndimage import gaussian_filter

from app.volumes import get_region_masks


def mask_to_mesh(
    mask: np.ndarray,
    affine: np.ndarray,
    smooth_sigma: float = 0.8,
    step_size: int = 1
) -> Optional[trimesh.Trimesh]:
    """
    Converts a 3D boolean/binary mask into an aligned 3D surface mesh in World Space (RAS+ mm).
    
    Critical Geometric Rules:
      1. marching_cubes runs in PURE voxel-index space (no spacing argument).
      2. Vertices are mapped to physical space via the full 4x4 spatial affine matrix.
      3. If det(affine[:3, :3]) < 0 (mirrored acquisition), normals are inverted to preserve correct winding.
    """
    if not np.any(mask):
        return None
        
    m = mask.astype(np.float32)
    if smooth_sigma > 0:
        smoothed = gaussian_filter(m, sigma=smooth_sigma)
        # If smoothing keeps peak above threshold, use smooth surface; otherwise fallback to raw mask
        if smoothed.max() > 0.5:
            m = smoothed

    if m.max() <= 0.5:
        return None
        
    try:
        # Step 1: Marching cubes in voxel space
        verts, faces, normals, _ = marching_cubes(m, level=0.5, step_size=step_size)
    except (ValueError, RuntimeError):
        return None
        
    # Step 2: Transform vertices into World mm space using full affine
    verts_mm = nib.affines.apply_affine(affine, verts)
    
    # Step 3: Construct Trimesh object
    mesh = trimesh.Trimesh(vertices=verts_mm, faces=faces, process=False)
    
    # Step 4: Handle mirrored spatial coordinate systems (winding check)
    det = float(np.linalg.det(affine[:3, :3]))
    if det < 0:
        mesh.invert()
        
    return mesh


def export_mesh_to_glb(mesh: trimesh.Trimesh, dest_path: Path) -> Path:
    """Exports a Trimesh object to binary GLB format."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    # trimesh.export returns bytes for 'glb'
    glb_data = mesh.export(file_type="glb")
    dest_path.write_bytes(glb_data)
    return dest_path


def generate_case_meshes(
    pred_data: np.ndarray,
    t1_data: np.ndarray,
    affine: np.ndarray,
    output_dir: Path
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Generates all 4 standard 3D meshes for a case:
      - brain.glb : Patient skull-stripped brain contour (step_size=2 for performance)
      - wt.glb    : Whole Tumor surface
      - tc.glb    : Tumor Core surface
      - et.glb    : Enhancing Tumor surface
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    masks = get_region_masks(pred_data)
    
    # 1. Brain surface mesh (T1 non-zero tissue)
    brain_mask = t1_data > 0.0
    brain_mesh = mask_to_mesh(brain_mask, affine, smooth_sigma=1.0, step_size=2)
    
    results: Dict[str, Optional[Dict[str, Any]]] = {}
    
    if brain_mesh is not None:
        brain_path = output_dir / "brain.glb"
        export_mesh_to_glb(brain_mesh, brain_path)
        results["brain"] = {
            "path": str(brain_path),
            "filename": "brain.glb",
            "vertices": len(brain_mesh.vertices),
            "faces": len(brain_mesh.faces)
        }
    else:
        results["brain"] = None
        
    # 2. Tumor regions: WT, TC, ET
    for region_name in ["WT", "TC", "ET"]:
        reg_mask = masks[region_name]
        reg_mesh = mask_to_mesh(reg_mask, affine, smooth_sigma=0.8, step_size=1)
        
        if reg_mesh is not None:
            mesh_filename = f"{region_name.lower()}.glb"
            mesh_path = output_dir / mesh_filename
            export_mesh_to_glb(reg_mesh, mesh_path)
            results[region_name.lower()] = {
                "path": str(mesh_path),
                "filename": mesh_filename,
                "vertices": len(reg_mesh.vertices),
                "faces": len(reg_mesh.faces)
            }
        else:
            results[region_name.lower()] = None
            
    return results
