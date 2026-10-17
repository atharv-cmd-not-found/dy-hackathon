from pathlib import Path
import random
import csv

DATA_ROOT = Path(r"D:\BraTSData\BraTS2021_Training_Data")
SPLIT_DIR = Path("eval/splits")
SEED = 20261017
HOLDOUT_FRACTION = 0.20

# These 10 cases were already used for threshold tuning and must not be in holdout.
USED_FOR_TUNING = {
    "BraTS2021_00000",
    "BraTS2021_00002",
    "BraTS2021_00003",
    "BraTS2021_00005",
    "BraTS2021_00006",
    "BraTS2021_00008",
    "BraTS2021_00009",
    "BraTS2021_00011",
    "BraTS2021_00012",
    "BraTS2021_00014",
}

def main():
    cases = sorted(
        p.name for p in DATA_ROOT.glob("BraTS2021_*")
        if p.is_dir() and (p / f"{p.name}_seg.nii.gz").is_file()
    )
    if not cases:
        raise SystemExit(f"No labelled BraTS cases found under {DATA_ROOT}")

    unseen = [case for case in cases if case not in USED_FOR_TUNING]
    if not unseen:
        raise SystemExit(
            "No untouched cases remain. Do not reuse tuning cases as holdout; "
            "add more labelled cases or use a separate dataset."
        )

    rng = random.Random(SEED)
    rng.shuffle(unseen)

    # Keep at least one test case when there are untouched cases.
    n_test = max(1, round(len(unseen) * HOLDOUT_FRACTION))
    holdout = sorted(unseen[:n_test])
    validation = sorted(unseen[n_test:])

    SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    (SPLIT_DIR / "threshold_tuning_cases.txt").write_text(
        "\n".join(sorted(USED_FOR_TUNING)) + "\n", encoding="utf-8"
    )
    (SPLIT_DIR / "validation_cases.txt").write_text(
        "\n".join(validation) + ("\n" if validation else ""), encoding="utf-8"
    )
    (SPLIT_DIR / "holdout_test_cases.txt").write_text(
        "\n".join(holdout) + "\n", encoding="utf-8"
    )

    with (SPLIT_DIR / "split_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.writer(f)
        writer.writerow(["split", "case_id"])
        writer.writerows(("threshold_tuning", c) for c in sorted(USED_FOR_TUNING))
        writer.writerows(("validation", c) for c in validation)
        writer.writerows(("holdout_test", c) for c in holdout)

    print(f"Found labelled cases: {len(cases)}")
    print(f"Already used for tuning: {len(USED_FOR_TUNING)}")
    print(f"Untouched cases available: {len(unseen)}")
    print(f"Validation cases: {len(validation)}")
    print(f"Holdout test cases: {len(holdout)}")
    print(f"\nSaved split files in: {SPLIT_DIR.resolve()}")
    print("\nHOLDOUT TEST IDs (do not use these to tune thresholds):")
    print("\n".join(holdout))
    if len(holdout) < 5:
        print(
            "\nWARNING: The holdout is very small; its score will be noisy. "
            "Use more labelled cases if possible."
        )

if __name__ == "__main__":
    main()
