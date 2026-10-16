

import nibabel as nib
import numpy as np

folder = "D:/BraTSData/case_00495/"

first = nib.load(
    folder + "BraTS2021_00495_pred.nii.gz"
)
second = nib.load(
    folder + "BraTS2021_00495_pred_repeat.nii.gz"
)

a = np.asarray(first.dataobj)
b = np.asarray(second.dataobj)

print("First shape:", a.shape)
print("Second shape:", b.shape)
print("Identical:", np.array_equal(a, b))
print("Voxel agreement:", float(np.mean(a == b)))

assert a.shape == b.shape, "Output shapes differ"
assert np.array_equal(a, b), "Predictions are not identical"

print("REPEATABILITY TEST PASSED")
