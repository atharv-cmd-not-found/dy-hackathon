"""Apply minimal threshold configurability edits to ml/predict.py.

Run from repository root:
  python tools/apply_threshold_patch.py

It adds per-region threshold settings using environment variables:
  NEUROSCOPE_TC_THRESHOLD (default 0.50)
  NEUROSCOPE_WT_THRESHOLD (default 0.50)
  NEUROSCOPE_ET_THRESHOLD (default 0.50)
The script is intentionally fail-closed if the expected code is not found.
"""
from pathlib import Path

path = Path("ml/predict.py")
text = path.read_text(encoding="utf-8-sig")
original = text

if "NEUROSCOPE_TC_THRESHOLD" in text:
    print("Threshold settings already appear to be present; no changes made.")
    raise SystemExit(0)

text = text.replace(
    "import argparse\nimport time\n",
    "import argparse\nimport os\nimport time\n",
    1,
)

old_sig = '''def probabilities_to_labels(
    pred: np.ndarray,
    threshold: float = 0.5,
) -> np.ndarray:'''
new_sig = '''def probabilities_to_labels(
    pred: np.ndarray,
    threshold: float | tuple[float, float, float] = 0.5,
) -> np.ndarray:'''
if old_sig not in text:
    raise SystemExit("Could not find probabilities_to_labels signature; no changes made.")
text = text.replace(old_sig, new_sig, 1)

old_body = '''    tc = pred[0] > threshold
    wt = pred[1] > threshold
    et = pred[2] > threshold'''
new_body = '''    if isinstance(threshold, (int, float)):
        tc_threshold = wt_threshold = et_threshold = float(threshold)
    else:
        if len(threshold) != 3:
            raise ValueError("threshold tuple must be (TC, WT, ET)")
        tc_threshold, wt_threshold, et_threshold = map(float, threshold)
    if not all(0.0 < value < 1.0 for value in (tc_threshold, wt_threshold, et_threshold)):
        raise ValueError("All thresholds must be between 0 and 1")

    tc = pred[0] > tc_threshold
    wt = pred[1] > wt_threshold
    et = pred[2] > et_threshold'''
if old_body not in text:
    raise SystemExit("Could not find thresholding lines; no changes made.")
text = text.replace(old_body, new_body, 1)

old_class_init = '''        self.weights = Path(weights).resolve()

        if not self.weights.is_file():'''
new_class_init = '''        self.weights = Path(weights).resolve()
        # Validation-calibrated per-region thresholds can be configured without
        # changing model weights. Keep 0.50 defaults until calibrated on labels.
        self.thresholds = (
            float(os.getenv("NEUROSCOPE_TC_THRESHOLD", "0.50")),
            float(os.getenv("NEUROSCOPE_WT_THRESHOLD", "0.50")),
            float(os.getenv("NEUROSCOPE_ET_THRESHOLD", "0.50")),
        )
        if not all(0.0 < value < 1.0 for value in self.thresholds):
            raise ValueError("NEUROSCOPE_*_THRESHOLD values must be between 0 and 1")

        if not self.weights.is_file():'''
if old_class_init not in text:
    raise SystemExit("Could not find Segmenter init block; no changes made.")
text = text.replace(old_class_init, new_class_init, 1)

old_call = '''        labels = probabilities_to_labels(
            probabilities_original,
            threshold=0.5,
        )'''
new_call = '''        labels = probabilities_to_labels(
            probabilities_original,
            threshold=self.thresholds,
        )'''
if old_call not in text:
    raise SystemExit("Could not find predict() label conversion call; no changes made.")
text = text.replace(old_call, new_call, 1)

if text == original:
    raise SystemExit("No changes applied.")
path.write_text(text, encoding="utf-8")
print(f"Updated {path}. Default thresholds remain 0.50 until environment variables are set.")
