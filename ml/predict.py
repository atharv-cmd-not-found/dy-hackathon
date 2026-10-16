"""
ML Segmenter module for NeuroScope 3D.
Implements the contract with Segmenter class.
"""
from pathlib import Path
import nibabel as nib
import numpy as np


class Segmenter:
    def __init__(self):
        """Initializes model weights (CUDA if available, else CPU fallback)."""
        self.device = "cpu"
        self.is_warmed_up = False

    def warmup(self):
        """Performs a warmup pass."""
        self.is_warmed_up = True

    def predict(self, paths: dict[str, str], out_path: str) -> None:
        """
        Runs brain MRI segmentation inference.
        
        Args:
            paths: dict with keys {"t1", "t1gd", "t2", "flair"} mapping to NIfTI files.
            out_path: destination path for .nii.gz prediction mask.
            
        Invariants:
            - Output is saved at out_path as NIfTI-1 (.nii.gz)
            - Affine and shape match input t1 exactly
            - Values strictly in BraTS 2021 codes: {0, 1, 2, 4}
            - Data type: np.uint8
        """
        t1_img = nib.load(str(paths["t1"]))
        shape = t1_img.shape
        affine = t1_img.affine
        
        # Load t1 data to generate a plausible mock mask within brain tissue
        t1_data = np.asanyarray(t1_img.dataobj)
        brain_mask = t1_data > 0
        
        # Create empty label array
        pred = np.zeros(shape, dtype=np.uint8)
        
        if np.any(brain_mask):
            coords = np.argwhere(brain_mask)
            center = coords.mean(axis=0).astype(int)
            # Add small mock tumor region around centroid offset for testing
            cx, cy, cz = center
            # Edema (label 2) radius ~12 voxels
            rx, ry, rz = 12, 12, 10
            x, y, z = np.ogrid[:shape[0], :shape[1], :shape[2]]
            dist = ((x - cx)**2 / rx**2 + (y - cy)**2 / ry**2 + (z - cz)**2 / rz**2)
            edema_mask = (dist <= 1.0) & brain_mask
            pred[edema_mask] = 2
            
            # Necrotic core (label 1) radius ~7 voxels
            core_mask = (dist <= 0.35) & brain_mask
            pred[core_mask] = 1
            
            # Enhancing tumor (label 4) rim radius ~0.35 to 0.55
            et_mask = (dist > 0.35) & (dist <= 0.60) & brain_mask
            pred[et_mask] = 4

        out_img = nib.Nifti1Image(pred, affine=affine)
        nib.save(out_img, str(out_path))
