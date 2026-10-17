"""Tune BraTS WT/TC/ET probability thresholds on labelled validation cases.

Expected CSV columns: case_id,t1,t1gd,t2,flair,seg
Paths may be absolute or relative to --manifest-dir. Segmentation labels use
BraTS IDs: 1=NCR/NET, 2=edema, 4=enhancing tumour.

Example:
  python tools/tune_thresholds.py --manifest validation.csv --manifest-dir D:/BraTSData --out thresholds.json

This script does NOT train the network. It calibrates thresholds against the
provided labelled validation cases. Use a separate held-out test set for final
metrics; never tune thresholds on that test set.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from pathlib import Path
from typing import Dict, List, Tuple

import nibabel as nib
import numpy as np
import torch
from nibabel.processing import resample_from_to

from ml.predict import Segmenter

REGIONS = ("tc", "wt", "et")
DEFAULT_CANDIDATES = np.round(np.arange(0.10, 0.901, 0.05), 2)


def dice_score(pred: np.ndarray, target: np.ndarray) -> float:
    pred = np.asarray(pred, dtype=bool)
    target = np.asarray(target, dtype=bool)
    denom = int(pred.sum()) + int(target.sum())
    if denom == 0:
        return 1.0
    return 2.0 * float(np.logical_and(pred, target).sum()) / denom


def read_manifest(path: Path, base_dir: Path) -> List[dict]:
    required = {"case_id", "t1", "t1gd", "t2", "flair", "seg"}
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        missing = required - fields
        if missing:
            raise ValueError(f"Manifest missing CSV columns: {sorted(missing)}")
        rows = []
        for row in reader:
            item = {k: (row[k] or "").strip() for k in required}
            if any(not item[k] for k in required):
                raise ValueError(f"Empty required field in row: {row}")
            for key in ("t1", "t1gd", "t2", "flair", "seg"):
                p = Path(item[key])
                if not p.is_absolute():
                    p = base_dir / p
                if not p.is_file():
                    raise FileNotFoundError(f"{key} for case {item['case_id']} not found: {p}")
                item[key] = str(p)
            rows.append(item)
    if not rows:
        raise ValueError("Manifest contains no cases.")
    return rows


def load_gt_on_t1(seg_path: str, t1_img: nib.spatialimages.SpatialImage) -> np.ndarray:
    gt_img = nib.load(seg_path)
    if len(gt_img.shape) != 3:
        raise ValueError(f"Ground-truth mask must be 3D: {seg_path}, shape={gt_img.shape}")
    if gt_img.shape[:3] == t1_img.shape[:3] and np.allclose(gt_img.affine, t1_img.affine, atol=1e-4):
        aligned = gt_img
    else:
        aligned = resample_from_to(
            gt_img, (t1_img.shape[:3], t1_img.affine), order=0,
            mode="constant", cval=0,
        )
    gt = np.asarray(aligned.dataobj)
    # BraTS foreground labels only; reject unexpected labels to avoid silently
    # interpreting a differently encoded mask.
    observed = set(np.unique(gt).astype(int).tolist())
    unexpected = observed - {0, 1, 2, 4}
    if unexpected:
        raise ValueError(f"Unexpected BraTS labels in {seg_path}: {sorted(unexpected)}")
    return gt.astype(np.uint8, copy=False)


def get_probabilities(segmenter: Segmenter, paths: Dict[str, str]) -> Tuple[np.ndarray, nib.spatialimages.SpatialImage]:
    image, original_t1, model_reference = segmenter._load_and_align(paths)
    tensor = torch.from_numpy(image).unsqueeze(0).to(segmenter.device)
    with torch.inference_mode():
        with torch.autocast(
            device_type=segmenter.device.type,
            enabled=(segmenter.device.type == "cuda"),
        ):
            logits = segmenter.inferer(tensor, segmenter.model)
        probs_model = torch.sigmoid(logits.float())[0].cpu().numpy()
    probs_t1 = segmenter._probabilities_to_original_t1(
        probabilities=probs_model,
        model_reference=model_reference,
        original_t1=original_t1,
    )
    return probs_t1, original_t1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="CSV with case_id,t1,t1gd,t2,flair,seg")
    parser.add_argument("--manifest-dir", default=".", help="Base for relative manifest paths")
    parser.add_argument("--out", default="thresholds.json", help="Output calibrated threshold JSON")
    parser.add_argument("--weights", default=None, help="Optional checkpoint path")
    parser.add_argument("--device", default=None, choices=("cuda", "cpu"), help="Default: auto")
    parser.add_argument("--min-threshold", type=float, default=0.10)
    parser.add_argument("--max-threshold", type=float, default=0.90)
    parser.add_argument("--step", type=float, default=0.05)
    args = parser.parse_args()

    if not (0 < args.min_threshold < args.max_threshold < 1) or args.step <= 0:
        raise ValueError("Threshold range must satisfy 0 < min < max < 1 and step > 0")

    manifest = Path(args.manifest).resolve()
    rows = read_manifest(manifest, Path(args.manifest_dir).resolve())
    candidates = np.round(np.arange(args.min_threshold, args.max_threshold + args.step / 2, args.step), 4)
    segmenter_kwargs = {}
    if args.weights:
        segmenter_kwargs["weights"] = args.weights
    if args.device:
        segmenter_kwargs["device"] = args.device
    segmenter = Segmenter(**segmenter_kwargs)
    segmenter.warmup()

    # Collect probabilities and matching binary targets. Calibration is done
    # independently per BraTS region. Nested label constraints are still
    # applied at inference by probabilities_to_labels().
    collected = {name: [] for name in REGIONS}
    cases_done = []
    for idx, row in enumerate(rows, start=1):
        paths = {k: row[k] for k in ("t1", "t1gd", "t2", "flair")}
        probs, t1_img = get_probabilities(segmenter, paths)
        gt = load_gt_on_t1(row["seg"], t1_img)
        if probs.shape[1:] != gt.shape:
            raise ValueError(f"Prediction/GT shape mismatch for {row['case_id']}: {probs.shape[1:]} vs {gt.shape}")
        targets = {
            "tc": np.logical_or(gt == 1, gt == 4),
            "wt": gt > 0,
            "et": gt == 4,
        }
        for ch, name in enumerate(REGIONS):
            collected[name].append((probs[ch].reshape(-1), targets[name].reshape(-1)))
        cases_done.append(row["case_id"])
        print(f"[{idx}/{len(rows)}] {row['case_id']} processed on {segmenter.device}")

    tuned = {}
    report = {}
    for name in REGIONS:
        best_threshold = 0.5
        best_mean = -1.0
        scored = []
        for threshold in candidates:
            scores = [dice_score(prob >= threshold, target) for prob, target in collected[name]]
            mean_score = float(np.mean(scores))
            scored.append((float(threshold), mean_score, scores))
            if mean_score > best_mean:
                best_mean, best_threshold = mean_score, float(threshold)
        base_scores = [dice_score(prob >= 0.5, target) for prob, target in collected[name]]
        tuned_scores = [dice_score(prob >= best_threshold, target) for prob, target in collected[name]]
        tuned[name] = round(best_threshold, 4)
        report[name] = {
            "threshold_0_5_mean_dice": round(float(np.mean(base_scores)), 6),
            "best_threshold": round(best_threshold, 4),
            "tuned_mean_dice": round(float(np.mean(tuned_scores)), 6),
            "delta_mean_dice": round(float(np.mean(tuned_scores) - np.mean(base_scores)), 6),
            "per_case_dice_at_best_threshold": {case: round(float(score), 6) for case, score in zip(cases_done, tuned_scores)},
        }
        print(f"{name.upper()}: threshold 0.50 Dice={np.mean(base_scores):.4f}; best={best_threshold:.2f}, Dice={np.mean(tuned_scores):.4f}")

    payload = {
        "description": "Validation-calibrated thresholds for MONAI BraTS multi-region probabilities.",
        "regions": {"tc": "channel 0 / BraTS tumour core", "wt": "channel 1 / BraTS whole tumour", "et": "channel 2 / BraTS enhancing tumour"},
        "thresholds": tuned,
        "validation_cases": cases_done,
        "num_validation_cases": len(cases_done),
        "region_report": report,
        "warning": "These are validation results, not held-out test results. Do not claim improvement unless independently evaluated on a separate test set.",
    }
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote calibrated thresholds: {out_path}")


if __name__ == "__main__":
    main()
