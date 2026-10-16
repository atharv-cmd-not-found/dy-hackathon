
import nibabel as nib
import numpy as np

folder = r"D:\BraTSData\case_00495"

pred = nib.load(
    folder + r"\BraTS2021_00495_pred.nii.gz"
)
t1ce = nib.load(
    folder + r"\BraTS2021_00495_t1ce.nii.gz"
)

print("Prediction shape:", pred.shape)
print("T1ce shape:", t1ce.shape)
print("Shape match:", pred.shape == t1ce.shape)
print("Affine match:", np.allclose(pred.affine, t1ce.affine))
print(
    "Affine max difference:",
    np.max(np.abs(pred.affine - t1ce.affine)),
)

assert pred.shape == t1ce.shape, "Shape mismatch"
assert np.allclose(pred.affine, t1ce.affine), "Affine mismatch"

print("GEOMETRY MATCH PASSED")
