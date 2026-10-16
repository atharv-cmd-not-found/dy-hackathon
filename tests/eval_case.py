
import nibabel as nib
import numpy as np

folder = r"D:\BraTSData\case_00495"

pred_img = nib.load(folder + r"\BraTS2021_00495_pred.nii.gz")
gt_img = nib.load(folder + r"\BraTS2021_00495_seg.nii.gz")

pred = np.asarray(pred_img.dataobj)
gt = np.asarray(gt_img.dataobj)

if pred.shape != gt.shape:
    raise ValueError(f"Shape mismatch: prediction {pred.shape}, GT {gt.shape}")

if not np.allclose(pred_img.affine, gt_img.affine):
    raise ValueError("Prediction and ground truth affines differ")

print("Ground-truth labels:", np.unique(gt))


def dice_score(a, b):
    a = np.asarray(a, dtype=bool)
    b = np.asarray(b, dtype=bool)
    denominator = a.sum() + b.sum()

    if denominator == 0:
        return 1.0

    return 2.0 * np.logical_and(a, b).sum() / denominator


# BraTS regions: WT = labels 1,2,4; TC = labels 1,4; ET = label 4
regions = {
    "WT": [1, 2, 4],
    "TC": [1, 4],
    "ET": [4],
}

for name, labels in regions.items():
    pred_mask = np.isin(pred, labels)
    gt_mask = np.isin(gt, labels)
    score = dice_score(pred_mask, gt_mask)
    print(f"{name} Dice: {score:.4f}")

print("SINGLE-CASE EVALUATION COMPLETE")
