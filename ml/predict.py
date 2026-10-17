
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np
import torch
from monai.inferers import SlidingWindowInferer
from monai.networks.nets import SegResNet
from nibabel.processing import resample_from_to, resample_to_output


MODEL_NAME = "MONAI brats_mri_segmentation 0.5.4"
CHANNEL_ORDER = ("t1gd", "t1", "t2", "flair")
VALID_LABELS = (0, 1, 2, 4)
DEFAULT_WEIGHTS = (
    "models/brats_mri_segmentation/"
    "brats_mri_segmentation/models/model.pt"
)


def probabilities_to_labels(
    pred: np.ndarray,
    threshold: float | tuple[float, float, float] = 0.5,
) -> np.ndarray:
    """
    Convert model probabilities to BraTS label IDs.

    Input:
        pred: (3, X, Y, Z), channels [TC, WT, ET]

    Output:
        0 = background
        1 = tumour core (TC, excluding ET)
        2 = whole tumour outside TC (WT, excluding TC)
        4 = enhancing tumour (ET)

    Enforce ET subset TC subset WT.
    """
    pred = np.asarray(pred)

    if pred.ndim != 4 or pred.shape[0] != 3:
        raise ValueError(
            "Expected probabilities shaped (3, X, Y, Z), "
            f"got {pred.shape}"
        )

    if not np.isfinite(pred).all():
        raise ValueError("Prediction contains NaN or infinite values.")

    if isinstance(threshold, (int, float)):
        tc_threshold = wt_threshold = et_threshold = float(threshold)
    else:
        if len(threshold) != 3:
            raise ValueError("threshold tuple must be (TC, WT, ET)")
        tc_threshold, wt_threshold, et_threshold = map(float, threshold)
    if not all(0.0 < value < 1.0 for value in (tc_threshold, wt_threshold, et_threshold)):
        raise ValueError("All thresholds must be between 0 and 1")

    tc = pred[0] > tc_threshold
    wt = pred[1] > wt_threshold
    et = pred[2] > et_threshold

    # Ensure nested regions.
    tc = tc | et
    wt = wt | tc

    labels = np.zeros(pred.shape[1:], dtype=np.uint8)
    labels[wt] = 2
    labels[tc] = 1
    labels[et] = 4

    return labels


class Segmenter:
    """
    Research/teaching prototype for multimodal brain MRI segmentation.

    Input channel order: [T1Gd, T1, T2, FLAIR]
    Model output channels: [TC, WT, ET]
    Output NIfTI grid: original T1 shape and affine.

    This model output is not a diagnosis.
    """

    def __init__(
        self,
        weights: str = DEFAULT_WEIGHTS,
        device: Optional[str] = None,
    ):
        self.weights = Path(weights).resolve()
        # Validation-calibrated per-region thresholds can be configured without
        # changing model weights. Keep 0.50 defaults until calibrated on labels.
        
        self.thresholds = (
            float(os.getenv("NEUROSCOPE_TC_THRESHOLD", "0.65")),
            float(os.getenv("NEUROSCOPE_WT_THRESHOLD", "0.55")),
            float(os.getenv("NEUROSCOPE_ET_THRESHOLD", "0.45")),
        )

        if not all(0.0 < value < 1.0 for value in self.thresholds):
            raise ValueError("NEUROSCOPE_*_THRESHOLD values must be between 0 and 1")

        if not self.weights.is_file():
            raise FileNotFoundError(
                f"Model checkpoint not found: {self.weights}"
            )

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        self.device = torch.device(device)

        if self.device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable.")

        self.model = SegResNet(
            blocks_down=(1, 2, 2, 4),
            blocks_up=(1, 1, 1),
            init_filters=16,
            in_channels=4,
            out_channels=3,
            dropout_prob=0.2,
        ).to(self.device)

        checkpoint = torch.load(
            str(self.weights),
            map_location="cpu",
            weights_only=True,
        )
        state_dict = checkpoint.get("model", checkpoint)
        self.model.load_state_dict(state_dict, strict=True)
        self.model.eval()

        # Match the published bundle's inference ROI.
        self.roi_size = (240, 240, 160)
        self.inferer = SlidingWindowInferer(
            roi_size=self.roi_size,
            sw_batch_size=1,
            overlap=0.5,
        )

        # Improve repeatability within the same environment.
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True

    def warmup(self) -> None:
        """Run one dummy forward pass during service startup."""
        dummy = torch.zeros(
            (1, 4, *self.roi_size),
            dtype=torch.float32,
            device=self.device,
        )

        with torch.inference_mode():
            with torch.autocast(
                device_type=self.device.type,
                enabled=(self.device.type == "cuda"),
            ):
                _ = self.model(dummy)

        if self.device.type == "cuda":
            torch.cuda.synchronize()

    @staticmethod
    def _normalize_nonzero(volume: np.ndarray) -> np.ndarray:
        """
        Per-modality z-score normalization on non-zero voxels only.
        Background voxels remain zero.
        """
        volume = np.asarray(volume, dtype=np.float32)
        mask = np.isfinite(volume) & (volume != 0)

        result = np.zeros(volume.shape, dtype=np.float32)

        if not mask.any():
            return result

        values = volume[mask]
        mean = float(values.mean())
        std = float(values.std())

        if std > 1e-8:
            result[mask] = (values - mean) / std
        else:
            result[mask] = values - mean

        result[~np.isfinite(result)] = 0.0
        return result

    @staticmethod
    def _validate_image(img: nib.spatialimages.SpatialImage, key: str):
        if len(img.shape) != 3:
            raise ValueError(
                f"{key} must be a 3D NIfTI image; got {img.shape}"
            )

        if not np.isfinite(img.affine).all():
            raise ValueError(f"{key} has a non-finite affine.")

        if abs(np.linalg.det(img.affine[:3, :3])) < 1e-8:
            raise ValueError(f"{key} has a singular affine.")

    def _load_and_align(self, paths: dict[str, str]):
        """
        Load modalities, use T1 as the output-grid reference, and prepare
        model input in [T1Gd, T1, T2, FLAIR] order.

        Returns:
            image: (4, X, Y, Z) float32 model input
            original_t1: original T1 NIfTI image
            model_reference: RAS-oriented 1 mm reference image
        """
        missing = [key for key in CHANNEL_ORDER if key not in paths]
        if missing:
            raise ValueError(f"Missing input modalities: {missing}")

        images = {}

        for key in CHANNEL_ORDER:
            path = Path(paths[key])

            if not path.is_file():
                raise FileNotFoundError(
                    f"{key} file not found: {path}"
                )

            img = nib.load(str(path))
            self._validate_image(img, key)
            images[key] = img

        original_t1 = images["t1"]

        # Convert the T1 reference grid to RAS orientation and 1 mm
        # isotropic spacing for model inference.
        model_reference = resample_to_output(
            original_t1,
            voxel_sizes=(1.0, 1.0, 1.0),
            order=1,
        )

        target = (model_reference.shape[:3], model_reference.affine)
        channels = []

        for key in CHANNEL_ORDER:
            aligned = resample_from_to(
                images[key],
                target,
                order=1,
                mode="constant",
                cval=0.0,
            )

            volume = np.asarray(aligned.dataobj, dtype=np.float32)
            channels.append(self._normalize_nonzero(volume))

        image = np.stack(channels, axis=0).astype(
            np.float32, copy=False
        )

        return image, original_t1, model_reference

    @staticmethod
    def _probabilities_to_original_t1(
        probabilities: np.ndarray,
        model_reference: nib.spatialimages.SpatialImage,
        original_t1: nib.spatialimages.SpatialImage,
    ) -> np.ndarray:
        """
        Linearly interpolate each probability channel onto the original
        T1 grid. Thresholding happens only after this remapping.
        """
        target = (original_t1.shape[:3], original_t1.affine)
        channels_original = []

        for channel in range(probabilities.shape[0]):
            probability_image = nib.Nifti1Image(
                probabilities[channel].astype(np.float32, copy=False),
                model_reference.affine,
            )

            mapped = resample_from_to(
                probability_image,
                target,
                order=1,
                mode="constant",
                cval=0.0,
            )

            channels_original.append(
                np.asarray(mapped.dataobj, dtype=np.float32)
            )

        return np.stack(channels_original, axis=0)

    def predict(
        self,
        paths: dict[str, str],
        out_path: Optional[str] = None,
    ) -> dict:
        """
        Predict a segmentation and save it on the original T1 grid.

        paths = {
            "t1": "...",
            "t1gd": "...",
            "t2": "...",
            "flair": "..."
        }
        """
        start = time.perf_counter()

        image, original_t1, model_reference = self._load_and_align(paths)
        tensor = torch.from_numpy(image).unsqueeze(0).to(self.device)

        with torch.inference_mode():
            with torch.autocast(
                device_type=self.device.type,
                enabled=(self.device.type == "cuda"),
            ):
                logits = self.inferer(tensor, self.model)

            # Convert logits to float32 before sigmoid for stable
            # probability postprocessing.
            probabilities_model_grid = torch.sigmoid(logits.float())[0]

        if self.device.type == "cuda":
            torch.cuda.synchronize()

        probabilities = probabilities_model_grid.cpu().numpy()

        # IMPORTANT: remap probabilities first, then threshold/label.
        probabilities_original = self._probabilities_to_original_t1(
            probabilities=probabilities,
            model_reference=model_reference,
            original_t1=original_t1,
        )

        labels = probabilities_to_labels(
            probabilities_original,
            threshold=self.thresholds,
        )

        if out_path is None:
            input_path = Path(paths["t1"])
            name = input_path.name

            if name.endswith(".nii.gz"):
                name = name[:-7]
            elif name.endswith(".nii"):
                name = name[:-4]

            out_path = str(input_path.with_name(name + "_pred.nii.gz"))

        output = Path(out_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        header = original_t1.header.copy()
        header.set_data_dtype(np.uint8)

        output_img = nib.Nifti1Image(
            labels,
            original_t1.affine,
            header=header,
        )

        # Preserve original T1 qform/sform matrices and codes.
        qform, qcode = original_t1.get_qform(coded=True)
        sform, scode = original_t1.get_sform(coded=True)

        output_img.set_qform(qform, int(qcode))
        output_img.set_sform(sform, int(scode))

        nib.save(output_img, str(output))

        elapsed = time.perf_counter() - start

        return {
            "label_nifti_path": str(output),
            "seconds": round(elapsed, 3),
            "device": str(self.device),
            "model": MODEL_NAME,
        }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Research/teaching brain MRI segmentation prototype. "
            "Output is not a diagnosis."
        )
    )
    parser.add_argument("--t1", required=True)
    parser.add_argument("--t1gd", required=True)
    parser.add_argument("--t2", required=True)
    parser.add_argument("--flair", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--weights", default=DEFAULT_WEIGHTS)
    parser.add_argument("--device", default=None)

    args = parser.parse_args()

    segmenter = Segmenter(
        weights=args.weights,
        device=args.device,
    )
    segmenter.warmup()

    result = segmenter.predict(
        paths={
            "t1": args.t1,
            "t1gd": args.t1gd,
            "t2": args.t2,
            "flair": args.flair,
        },
        out_path=args.out,
    )

    print(result)
    print(
        "Research/teaching output only: suspected tumour region "
        "predicted by the model; not a diagnosis."
    )


if __name__ == "__main__":
    main()
