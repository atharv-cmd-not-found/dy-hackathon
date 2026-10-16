# NeuroScope — Model Card

## Model Overview

- **Model:** MONAI BraTS MRI Segmentation
- **Bundle version:** 0.5.4
- **Architecture:** SegResNet
- **Framework:** PyTorch and MONAI
- **Task:** 3D brain MRI tumour-region segmentation
- **Intended use:** Hackathon prototype, research and educational visualization
- **Clinical use:** Not intended for diagnosis or clinical decision-making

## Input

The model receives four aligned 3D MRI volumes in this exact channel order:

1. T1Gd (T1ce)
2. T1
3. T2
4. FLAIR

The preprocessing pipeline reorients images to RAS+, resamples to 1 mm isotropic spacing and performs z-score normalization on non-zero voxels.

## Output

The model predicts three probability channels:

- TC — Tumour Core
- WT — Whole Tumour
- ET — Enhancing Tumour

The probability maps are interpolated onto the original T1 image grid before thresholding and conversion to the output label map.

| Label | Meaning |
|---|---|
| 0 | Background |
| 1 | Tumour-core region excluding ET |
| 2 | Edema region outside TC |
| 4 | Enhancing tumour |

The output is a `.nii.gz` NIfTI segmentation aligned with the original T1 volume.

## Evaluation

Preliminary evaluation was performed on 10 BraTS2021 cases.

| Region | Mean Dice | Mean Sensitivity |
|---|---:|---:|
| WT | 0.8725 | 0.8669 |
| TC | 0.8314 | 0.9427 |
| ET | 0.7538 | 0.7989 |

These results are preliminary and do not establish clinical performance or independent generalization.

## License and Data

The downloaded MONAI bundle metadata identifies the model license as Apache-2.0. Verify the bundled LICENSE and model metadata before redistribution.

The model was pretrained on BraTS 2018 data according to its bundle metadata. Potential overlap with the BraTS2021 evaluation cases cannot be ruled out.

## Limitations

- Performance varies across cases and tumour regions.
- The model predicts tumour regions; it does not provide a clinical diagnosis.
- The output channels do not separately distinguish NCR from NET.
- Evaluation on 10 cases is limited and may not represent other scanners, populations or acquisition protocols.
- No claim of independent test-set performance is made.
- The model should not be used as a substitute for assessment by qualified medical professionals.

## Reproducibility

- Evaluation artifacts: `eval/results.json` and `eval/split.json`
- Inference entry point: `ml/predict.py`
- Checkpoint: `models/brats_mri_segmentation/brats_mri_segmentation/models/model.pt`

Confirm the checkpoint path and preprocessing implementation in the deployed version before release.
