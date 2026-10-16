
import json
import math
import time
from pathlib import Path

import nibabel as nib
import numpy as np

from ml.predict import Segmenter


DATA_DIR = Path(r"D:\BraTSData")
OUTPUT_DIR = DATA_DIR / "eval_predictions"
EVAL_DIR = Path("eval")

CASE_IDS = [
    "00000", "00002", "00003", "00005", "00006",
    "00008", "00009", "00011", "00012", "00014",
]

WEIGHTS = (
    "models/brats_mri_segmentation/"
    "brats_mri_segmentation/models/model.pt"
)


def dice_score(pred_mask, gt_mask):
    pred_mask = np.asarray(pred_mask, dtype=bool)
    gt_mask = np.asarray(gt_mask, dtype=bool)

    denominator = pred_mask.sum() + gt_mask.sum()
    if denominator == 0:
        return 1.0

    intersection = np.logical_and(pred_mask, gt_mask).sum()
    return float(2.0 * intersection / denominator)


def sensitivity_score(pred_mask, gt_mask):
    gt_mask = np.asarray(gt_mask, dtype=bool)
    pred_mask = np.asarray(pred_mask, dtype=bool)

    positives = int(gt_mask.sum())
    if positives == 0:
        return None

    true_positives = np.logical_and(pred_mask, gt_mask).sum()
    return float(true_positives / positives)


def region_masks(labels):
    # BraTS labels: 1=NCR, 2=ED, 4=ET
    return {
        "WT": np.isin(labels, [1, 2, 4]),
        "TC": np.isin(labels, [1, 4]),
        "ET": labels == 4,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    split = {
        "dataset": "BraTS2021",
        "purpose": "Preliminary patient-wise evaluation",
        "case_ids": [f"BraTS2021_{case_id}" for case_id in CASE_IDS],
        "notes": [
            "These are held-out evaluation cases for this run.",
            "Pretrained model training-data overlap cannot be ruled out.",
            "This evaluation is not clinical validation.",
        ],
    }

    (EVAL_DIR / "split.json").write_text(
        json.dumps(split, indent=2),
        encoding="utf-8",
    )

    print("Loading model once...")
    segmenter = Segmenter(weights=WEIGHTS)
    segmenter.warmup()
    print("Model ready.")

    results = []

    for case_id in CASE_IDS:
        case_name = f"BraTS2021_{case_id}"
        folder = DATA_DIR / case_name

        paths = {
            "t1": str(folder / f"{case_name}_t1.nii.gz"),
            "t1gd": str(folder / f"{case_name}_t1ce.nii.gz"),
            "t2": str(folder / f"{case_name}_t2.nii.gz"),
            "flair": str(folder / f"{case_name}_flair.nii.gz"),
        }

        gt_path = folder / f"{case_name}_seg.nii.gz"
        pred_path = OUTPUT_DIR / f"{case_name}_pred.nii.gz"

        for path in [*paths.values(), str(gt_path)]:
            if not Path(path).is_file():
                raise FileNotFoundError(path)

        print(f"\nEvaluating {case_name}...")
        start = time.perf_counter()

        prediction_info = segmenter.predict(
            paths=paths,
            out_path=str(pred_path),
        )

        elapsed = time.perf_counter() - start

        pred_img = nib.load(str(pred_path))
        gt_img = nib.load(str(gt_path))

        pred = np.asarray(pred_img.dataobj)
        gt = np.asarray(gt_img.dataobj)

        if pred.shape != gt.shape:
            raise ValueError(
                f"{case_name}: shape mismatch: "
                f"prediction {pred.shape}, GT {gt.shape}"
            )

        if not np.allclose(pred_img.affine, gt_img.affine, atol=1e-4):
            raise ValueError(
                f"{case_name}: prediction and GT affine do not match"
            )

        pred_regions = region_masks(pred)
        gt_regions = region_masks(gt)

        dice = {
            region: dice_score(pred_regions[region], gt_regions[region])
            for region in ["WT", "TC", "ET"]
        }

        sensitivity = {
            region: sensitivity_score(
                pred_regions[region], gt_regions[region]
            )
            for region in ["WT", "TC", "ET"]
        }

        case_result = {
            "case_id": case_name,
            "prediction_file": pred_path.name,
            "seconds": round(elapsed, 3),
            "device": prediction_info.get("device", "unknown"),
            "dice": dice,
            "sensitivity": sensitivity,
            "ground_truth_empty": {
                region: not bool(gt_regions[region].any())
                for region in ["WT", "TC", "ET"]
            },
        }

        results.append(case_result)
        print(
            f"WT Dice={dice['WT']:.4f} | "
            f"TC Dice={dice['TC']:.4f} | "
            f"ET Dice={dice['ET']:.4f} | "
            f"{elapsed:.2f}s"
        )

    summaries = {}

    for region in ["WT", "TC", "ET"]:
        scores = [row["dice"][region] for row in results]
        sensitivities = [
            row["sensitivity"][region]
            for row in results
            if row["sensitivity"][region] is not None
        ]

        summaries[region] = {
            "mean_dice": float(np.mean(scores)),
            "std_dice": float(np.std(scores)),
            "cases": len(scores),
            "mean_sensitivity": (
                float(np.mean(sensitivities))
                if sensitivities else None
            ),
            "sensitivity_cases": len(sensitivities),
        }

    report = {
        "dataset": "BraTS2021",
        "evaluation_type": "preliminary_held_out_cases",
        "case_count": len(results),
        "model": "MONAI brats_mri_segmentation 0.5.4",
        "results": results,
        "summary": summaries,
        "limitations": [
            "Only the listed 10 cases were evaluated.",
            "Pretraining overlap with evaluation cases cannot be ruled out.",
            "Dice is 1.0 when both prediction and GT masks are empty.",
            "Sensitivity is null when the GT region is empty.",
            "Results are for research/teaching, not clinical validation.",
        ],
    }

    results_path = EVAL_DIR / "results.json"
    results_path.write_text(
        json.dumps(report, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    print("\nEvaluation complete.")
    print(f"Split:   {EVAL_DIR / 'split.json'}")
    print(f"Results: {results_path}")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
