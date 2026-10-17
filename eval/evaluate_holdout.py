from pathlib import Path
import csv
import sys
import numpy as np
import nibabel as nib
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ml.predict import Segmenter, probabilities_to_labels

DATA_ROOT = Path(r"D:\BraTSData\BraTS2021_Training_Data")
SPLITS_DIR = PROJECT_ROOT / "eval" / "splits"
HOLDOUT_FILE = SPLITS_DIR / "holdout_test_cases.txt"
OUTPUT_CSV = PROJECT_ROOT / "eval" / "holdout_results.csv"

# Freeze these before inspecting holdout results.
THRESHOLDS = (0.65, 0.55, 0.35)  # TC, WT, ET

def dice_score(pred, truth):
    pred = np.asarray(pred, dtype=bool)
    truth = np.asarray(truth, dtype=bool)
    denom = pred.sum() + truth.sum()
    if denom == 0:
        return 1.0
    return float(2 * np.logical_and(pred, truth).sum() / denom)

def region_masks(labels):
    return {
        "TC": np.isin(labels, [1, 4]),
        "WT": np.isin(labels, [1, 2, 4]),
        "ET": labels == 4,
    }

def read_ids(path):
    if not path.is_file():
        raise FileNotFoundError(f"Holdout list not found: {path}")
    return [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

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
        raise FileNotFoundError("Missing holdout files: " + ", ".join(missing))
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
    return segmenter._probabilities_to_original_t1(probs, model_reference, original_t1)

def main():
    holdout_ids = read_ids(HOLDOUT_FILE)
    if len(holdout_ids) != 10:
        raise RuntimeError(
            f"Expected exactly 10 holdout IDs in {HOLDOUT_FILE}, found {len(holdout_ids)}"
        )
    if len(set(holdout_ids)) != len(holdout_ids):
        raise RuntimeError("Duplicate IDs found in holdout list")

    tuning_file = SPLITS_DIR / "threshold_tuning_cases.txt"
    tuning_ids = set(read_ids(tuning_file))
    overlap = tuning_ids & set(holdout_ids)
    if overlap:
        raise RuntimeError(f"Tuning/holdout overlap detected: {sorted(overlap)}")

    cases = []
    for case_id in holdout_ids:
        case_dir = DATA_ROOT / case_id
        if not case_dir.is_dir():
            raise FileNotFoundError(f"Holdout case folder missing: {case_dir}")
        cases.append(case_dir)

    print("FINAL HOLDOUT EVALUATION")
    print(f"Cases: {len(cases)} | Tuning overlap: {len(overlap)}")
    print(f"Frozen thresholds (TC, WT, ET): {THRESHOLDS}")
    print("Do not alter thresholds based on these results.\n")

    segmenter = Segmenter()
    rows = []

    for i, case in enumerate(cases, start=1):
        print(f"[{i}/{len(cases)}] Evaluating {case.name} ...", flush=True)
        paths, seg_img = load_case(case)
        probs = get_probabilities(segmenter, paths)
        truth_labels = np.asarray(seg_img.dataobj)

        t1_img = nib.load(paths["t1"])
        if truth_labels.shape != t1_img.shape or not np.allclose(
            seg_img.affine, t1_img.affine, atol=1e-3
        ):
            seg_img = nib.processing.resample_from_to(
                seg_img, (t1_img.shape[:3], t1_img.affine), order=0
            )
            truth_labels = np.asarray(seg_img.dataobj)

        pred_labels = probabilities_to_labels(probs, THRESHOLDS)
        truth = region_masks(truth_labels)
        pred = region_masks(pred_labels)

        row = {
            "case": case.name,
            "tc_threshold": THRESHOLDS[0],
            "wt_threshold": THRESHOLDS[1],
            "et_threshold": THRESHOLDS[2],
            "tc_dice": dice_score(pred["TC"], truth["TC"]),
            "wt_dice": dice_score(pred["WT"], truth["WT"]),
            "et_dice": dice_score(pred["ET"], truth["ET"]),
        }
        row["macro_dice"] = float(np.mean([row["tc_dice"], row["wt_dice"], row["et_dice"]]))
        rows.append(row)
        print(
            f"  TC={row['tc_dice']:.4f}  WT={row['wt_dice']:.4f}  "
            f"ET={row['et_dice']:.4f}  Macro={row['macro_dice']:.4f}",
            flush=True,
        )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "case", "tc_threshold", "wt_threshold", "et_threshold",
        "tc_dice", "wt_dice", "et_dice", "macro_dice"
    ]
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\nHOLDOUT SUMMARY (mean Dice)")
    for region in ("tc_dice", "wt_dice", "et_dice", "macro_dice"):
        vals = [r[region] for r in rows]
        print(f"{region.upper()}: {np.mean(vals):.4f} (std={np.std(vals, ddof=1):.4f})")
    print(f"\nSaved per-case results to: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
