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
    output_dir: Path,
    anat_data: Optional[np.ndarray] = None
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Generates 3D surface meshes in World Space (RAS+ mm) for Three.js:
      - brain.glb      : High-fidelity patient skull-stripped brain contour
      - cerebrum.glb   : Major cerebral hemispheres (when atlas parcellation available)
      - cerebellum.glb : Cerebellum division (when atlas parcellation available)
      - brainstem.glb  : Brainstem division (when atlas parcellation available)
      - ed.glb         : Peritumoral Edema (Label 2 · non-overlapping)
      - ncr.glb        : Necrotic/Non-enhancing Core (Label 1 · non-overlapping)
      - et.glb         : Active Enhancing Tumour (Label 4 · non-overlapping)
      - wt.glb         : Whole Tumour cumulative shell (NCR + ED + ET)
      - tc.glb         : Tumour Core cumulative volume (NCR + ET)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results: Dict[str, Optional[Dict[str, Any]]] = {}

    # Helper to export and record mesh metadata
    def _export_and_record(mesh: Optional[trimesh.Trimesh], name: str):
        if mesh is not None:
            filename = f"{name}.glb"
            dest = output_dir / filename
            export_mesh_to_glb(mesh, dest)
            results[name] = {
                "path": str(dest),
                "filename": filename,
                "vertices": len(mesh.vertices),
                "faces": len(mesh.faces)
            }
        else:
            results[name] = None

    # 1. Whole Brain Surface Mesh (t1 > 0 with gentle smoothing to preserve gyral sulci)
    brain_mask = t1_data > 0.0
    brain_mesh = mask_to_mesh(brain_mask, affine, smooth_sigma=0.7, step_size=2)
    _export_and_record(brain_mesh, "brain")

    # 2. The 3 Anatomical Brain Divisions (Cerebrum, Cerebellum, Brainstem) from SRI24 atlas
    if anat_data is not None and np.any(anat_data > 0):
        try:
            labels_path = Path(__file__).resolve().parent / "localization" / "atlas" / "sri24_labels.json"
            if labels_path.exists():
                import json
                with open(labels_path, "r", encoding="utf-8") as lf:
                    atlas_info = json.load(lf)
                labels_dict = atlas_info.get("labels", {})

                cerebrum_ids = []
                cerebellum_ids = []
                brainstem_ids = []

                for k, v in labels_dict.items():
                    if not k.isdigit():
                        continue
                    lid = int(k)
                    lobe_str = str(v.get("lobe", ""))
                    name_str = str(v.get("name", ""))
                    if "Cerebell" in lobe_str or "Cerebell" in name_str:
                        cerebellum_ids.append(lid)
                    elif "Brainstem" in lobe_str or "Brainstem" in name_str or "Pons" in name_str or "Medulla" in name_str:
                        brainstem_ids.append(lid)
                    else:
                        cerebrum_ids.append(lid)

                # Generate Cerebrum mesh
                mask_cerebrum = np.isin(anat_data, cerebrum_ids)
                m_cerebrum = mask_to_mesh(mask_cerebrum, affine, smooth_sigma=0.8, step_size=2)
                _export_and_record(m_cerebrum, "cerebrum")

                # Generate Cerebellum mesh
                mask_cerebellum = np.isin(anat_data, cerebellum_ids)
                m_cerebellum = mask_to_mesh(mask_cerebellum, affine, smooth_sigma=0.8, step_size=2)
                _export_and_record(m_cerebellum, "cerebellum")

                # Generate Brainstem mesh
                mask_brainstem = np.isin(anat_data, brainstem_ids)
                m_brainstem = mask_to_mesh(mask_brainstem, affine, smooth_sigma=0.8, step_size=2)
                _export_and_record(m_brainstem, "brainstem")
        except Exception:
            # Non-blocking: proceed if atlas parcellation partitioning encounters any issue
            pass

    # 3. The 3 Distinct Non-Overlapping Physiological Tumour Compartments
    # Part 1: Edema (Label 2)
    m_ed = mask_to_mesh(pred_data == 2, affine, smooth_sigma=0.8, step_size=1)
    _export_and_record(m_ed, "ed")

    # Part 2: Necrotic Core (Label 1)
    m_ncr = mask_to_mesh(pred_data == 1, affine, smooth_sigma=0.8, step_size=1)
    _export_and_record(m_ncr, "ncr")

    # Part 3: Enhancing Tumour (Label 4)
    m_et = mask_to_mesh(pred_data == 4, affine, smooth_sigma=0.8, step_size=1)
    _export_and_record(m_et, "et")

    # 4. The Cumulative Standard BraTS Evaluation Meshes
    masks = get_region_masks(pred_data)
    m_wt = mask_to_mesh(masks["WT"], affine, smooth_sigma=0.8, step_size=1)
    _export_and_record(m_wt, "wt")

    m_tc = mask_to_mesh(masks["TC"], affine, smooth_sigma=0.8, step_size=1)
    _export_and_record(m_tc, "tc")

    return results
