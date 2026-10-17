from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent
SPLITS = ROOT / "eval" / "splits"

TUNING_FILE = SPLITS / "threshold_tuning_cases.txt"
VALIDATION_FILE = SPLITS / "validation_cases.txt"
HOLDOUT_FILE = SPLITS / "holdout_test_cases.txt"

SEED = 20261017
ADD_TUNING = 10
HOLDOUT_COUNT = 10

def read_ids(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing split file: {path}")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")]

def write_ids(path, ids):
    path.write_text("\n".join(ids) + "\n", encoding="utf-8")

def main():
    rng = random.Random(SEED)
    existing_tuning = read_ids(TUNING_FILE)
    validation = read_ids(VALIDATION_FILE)
    old_holdout = read_ids(HOLDOUT_FILE)

    # Keep the original 10 tuning IDs and select 10 new ones from validation.
    validation_pool = sorted(set(validation) - set(existing_tuning))
    if len(validation_pool) < ADD_TUNING:
        raise ValueError("Not enough unused validation cases to add 10 tuning cases.")
    new_tuning = sorted(rng.sample(validation_pool, ADD_TUNING))
    tuning = existing_tuning + new_tuning

    # Select 10 holdout cases only from the existing holdout pool, never from tuning.
    holdout_pool = sorted(set(old_holdout) - set(tuning))
    if len(holdout_pool) < HOLDOUT_COUNT:
        raise ValueError("Not enough separate cases available for the 10-case holdout.")
    holdout = sorted(rng.sample(holdout_pool, HOLDOUT_COUNT))

    if set(tuning) & set(holdout):
        raise RuntimeError("Split overlap detected.")

    # Save the final lists. Keep a backup of the original files first.
    for path in (TUNING_FILE, HOLDOUT_FILE):
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    write_ids(TUNING_FILE, tuning)
    write_ids(HOLDOUT_FILE, holdout)

    print(f"Updated tuning cases: {len(tuning)} (existing {len(existing_tuning)} + new {len(new_tuning)})")
    print(f"Updated holdout cases: {len(holdout)}")
    print(f"Overlap: {len(set(tuning) & set(holdout))}")
    print("\nNew tuning cases:")
    print("\n".join(new_tuning))
    print("\nHoldout cases:")
    print("\n".join(holdout))
    print("\nBackups saved as *.txt.bak if they did not already exist.")
    print("IMPORTANT: Run threshold tuning ONLY on threshold_tuning_cases.txt.")
    print("Do not use holdout_test_cases.txt until thresholds are frozen.")

if __name__ == "__main__":
    main()
