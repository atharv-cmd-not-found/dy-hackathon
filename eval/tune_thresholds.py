
from pathlib import Path
import csv
import itertools

import nibabel as nib
import numpy as np
import torch
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from ml.predict import Segmenter, probabilities_to_labels

DATA_ROOT = Path(r"D:\BraTSData\BraTS2021_Training_Data")
OUTPUT_CSV = PROJECT_ROOT / "eval" / "threshold_results.csv"
SPLITS_DIR = PROJECT_ROOT / "eval" / "splits"
TUNING_FILE = SPLITS_DIR / "threshold_tuning_cases.txt"
HOLDOUT_FILE = SPLITS_DIR / "holdout_test_cases.txt"

# Candidate thresholds. Wider search can be done after this initial pass.
CANDIDATES = [0.25, 0.35, 0.45, 0.50, 0.55, 0.65]

def dice_score(pred, truth):
    pred = np.asarray(pred, dtype=bool)
    truth = np.asarray(truth, dtype=bool)
    denominator = pred.sum() + truth.sum()
    if denominator == 0:
        return 1.0
    return float(2 * np.logical_and(pred, truth).sum() / denominator)

def region_masks(labels):
    # BraTS labels: 0 background, 1 NCR/NET, 2 edema, 4 enhancing tumour
    return {
        "TC": np.isin(labels, [1, 4]),
        "WT": np.isin(labels, [1, 2, 4]),
        "ET": labels == 4,
    }

def load_case(case_dir):
    files = {
        "t1": case_dir / f"{case_dir.name}_t1.nii.gz",
        "t1gd": case_dir / f"{case_dir.name}_t1ce.nii.gz",
        "t2": case_dir / f"{case_dir.name}_t2.nii.gz",
        "flair": case_dir / f"{case_dir.name}_flair.nii.gz",
    }
    seg = case_dir / f"{case_dir.name}_seg.nii.gz"

    missing = [str(p) for p in [*files.values(), seg] if not p.is_file()]
    if missing:
        raise FileNotFoundError("Missing files: " + ", ".join(missing))

    return {k: str(v) for k, v in files.items()}, nib.load(str(seg))

def get_probabilities(segmenter, paths):
    image, original_t1, model_reference = segmenter._load_and_align(paths)
    tensor = torch.from_numpy(image).unsqueeze(0).to(segmenter.device)

    with torch.inference_mode():
        with torch.autocast(
            device_type=segmenter.device.type,
            enabled=(segmenter.device.type == "cuda"),
        ):
            logits = segmenter.inferer(tensor, segmenter.model)

        probs = torch.sigmoid(logits.float())[0].cpu().numpy()

    return segmenter._probabilities_to_original_t1(
        probs, model_reference, original_t1
    )

def read_case_ids(path):
    if not path.is_file():
        raise FileNotFoundError(f"Required split file not found: {path}")
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def main():
    # Only tune on the explicitly listed 20 cases. Never glob the full dataset.
    tuning_ids = read_case_ids(TUNING_FILE)
    holdout_ids = set(read_case_ids(HOLDOUT_FILE))

    if len(tuning_ids) != 20:
        raise RuntimeError(
            f"Expected exactly 20 tuning IDs in {TUNING_FILE}, found {len(tuning_ids)}"
        )
    if len(set(tuning_ids)) != len(tuning_ids):
        raise RuntimeError("Duplicate IDs found in threshold_tuning_cases.txt")
    overlap = set(tuning_ids) & holdout_ids
    if overlap:
        raise RuntimeError(f"Tuning/holdout overlap detected: {sorted(overlap)}")

    cases = []
    for case_id in tuning_ids:
        case_dir = DATA_ROOT / case_id
        seg_file = case_dir / f"{case_id}_seg.nii.gz"
        if not case_dir.is_dir() or not seg_file.is_file():
            raise FileNotFoundError(
                f"Missing tuning case or segmentation for {case_id}: {case_dir}"
            )
        cases.append(case_dir)

    print(f"Threshold tuning will use exactly {len(cases)} cases from {TUNING_FILE}")
    print(f"Holdout overlap check passed: {len(overlap)} overlapping cases")
    segmenter = Segmenter()
    rows = []

    for i, case in enumerate(cases, start=1):
        print(f"[{i}/{len(cases)}] {case.name}")
        paths, seg_img = load_case(case)
        probs = get_probabilities(segmenter, paths)
        truth_labels = np.asarray(seg_img.dataobj)

        # Ground truth must be on the same voxel grid as the original T1.
        t1_img = nib.load(paths["t1"])
        if truth_labels.shape != t1_img.shape or not np.allclose(
            seg_img.affine, t1_img.affine, atol=1e-3
        ):
            seg_img = nib.processing.resample_from_to(
                seg_img, (t1_img.shape[:3], t1_img.affine), order=0
            )
            truth_labels = np.asarray(seg_img.dataobj)

        truth = region_masks(truth_labels)

        for thresholds in itertools.product(CANDIDATES, repeat=3):
            predicted_labels = probabilities_to_labels(probs, thresholds)
            predicted = region_masks(predicted_labels)

            row = {
                "case": case.name,
                "tc_threshold": thresholds[0],
                "wt_threshold": thresholds[1],
                "et_threshold": thresholds[2],
                "tc_dice": dice_score(predicted["TC"], truth["TC"]),
                "wt_dice": dice_score(predicted["WT"], truth["WT"]),
                "et_dice": dice_score(predicted["ET"], truth["ET"]),
            }
            rows.append(row)

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved all results to: {OUTPUT_CSV.resolve()}")

    # Show best mean Dice for each region across cases.
    print("\nBest thresholds per region (mean Dice across all cases):")
    for region, column, threshold_col in [
        ("TC", "tc_dice", "tc_threshold"),
        ("WT", "wt_dice", "wt_threshold"),
        ("ET", "et_dice", "et_threshold"),
    ]:
        grouped = {}
        for row in rows:
            grouped.setdefault(row[threshold_col], []).append(row[column])
        best_threshold, scores = max(
            grouped.items(), key=lambda item: np.mean(item[1])
        )
        print(
            f"{region}: threshold={best_threshold:.2f}, "
            f"mean Dice={np.mean(scores):.4f}"
        )

if __name__ == "__main__":
    main()
