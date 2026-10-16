
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np


def test_output_geometry():
    shape = (12, 14, 16)
    affine = np.array([
        [1.5, 0, 0, -20],
        [0, 1.5, 0, -30],
        [0, 0, 2.0, -40],
        [0, 0, 0, 1],
    ], dtype=float)

    original = nib.Nifti1Image(
        np.zeros(shape, dtype=np.float32),
        affine,
    )

    labels = np.zeros(shape, dtype=np.uint8)
    labels[3, 4, 5] = 4

    output = nib.Nifti1Image(
        labels,
        original.affine,
        original.header.copy(),
    )
    output.set_data_dtype(np.uint8)

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prediction.nii.gz"
        nib.save(output, str(path))
        reloaded = nib.load(str(path))

        assert reloaded.shape == original.shape, (
            reloaded.shape, original.shape
        )
        assert np.allclose(reloaded.affine, original.affine), (
            reloaded.affine, original.affine
        )
        assert set(np.unique(reloaded.get_fdata())).issubset(
            {0, 1, 2, 4}
        )

    print("OUTPUT GEOMETRY TEST PASSED")


if __name__ == "__main__":
    test_output_geometry()
