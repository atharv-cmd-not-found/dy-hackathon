"""
Test fixtures generator for NeuroScope 3D.
Generates synthetic data and test cases for judges' evaluation rubrics and validation failure packs.
"""
from pathlib import Path
import numpy as np
import nibabel as nib

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

SLOTS = ["t1", "t1gd", "t2", "flair"]


def fake_brain(shape=(96, 96, 80), seed=0):
    """Generates a synthetic skull-stripped brain volume with exact 0 background."""
    rng = np.random.RandomState(seed)
    x, y, z = np.meshgrid(
        np.linspace(-1, 1, shape[0]),
        np.linspace(-1, 1, shape[1]),
        np.linspace(-1, 1, shape[2]),
        indexing="ij"
    )
    # Ellipsoid brain mask
    inside = (x**2 / 0.8**2 + y**2 / 0.9**2 + z**2 / 0.8**2) < 1.0
    vol = np.where(inside, 100 + 30 * rng.randn(*shape), 0.0).astype(np.float32)
    vol = np.clip(vol, 0.0, None)
    vol[~inside] = 0.0
    return vol


def save_nifti(data, affine, filename):
    img = nib.Nifti1Image(data, affine)
    target = FIXTURES_DIR / filename
    nib.save(img, str(target))
    return target


def save_sequence_set(prefix, data_dict, affine):
    for slot in SLOTS:
        save_nifti(data_dict[slot], affine, f"{prefix}_{slot}.nii.gz")


def generate_all_fixtures():
    print(f"Generating test fixtures in {FIXTURES_DIR}...")
    
    # 1. Base Scan Set (1x1x2 mm spacing)
    aff = np.diag([1.0, 1.0, 2.0, 1.0])
    base_data = {s: fake_brain(seed=i) for i, s in enumerate(SLOTS)}
    save_sequence_set("base", base_data, aff)
    print("  [x] Base sequence set generated (base_t1, base_t1gd, base_t2, base_flair)")

    # 2. Volume Test: 20x20x20 Cube of label 2 at 1x1x2 mm
    # 20 * 20 * 20 = 8000 voxels * 2 mm^3 = 16,000 mm^3 = 16.0 mL
    shape = base_data["t1"].shape
    cube_label = np.zeros(shape, dtype=np.uint8)
    cube_label[30:50, 30:50, 30:50] = 2
    save_nifti(cube_label, aff, "cube_label.nii.gz")
    print("  [x] Cube fixture generated (cube_label.nii.gz -> expect WT = 16.0 mL, TC = 0, ET = 0)")

    # 3. Orientation: Same anatomy (Voxel flip on axis 0 + updated affine)
    def flip_with_affine(data, affine, axis=0):
        d_flipped = np.flip(data, axis).copy()
        a_flipped = affine.copy()
        a_flipped[:3, axis] = -affine[:3, axis]
        a_flipped[:3, 3] = affine[:3, 3] + affine[:3, axis] * (data.shape[axis] - 1)
        return d_flipped, a_flipped

    fa_data = {}
    fa_affine = None
    for slot in SLOTS:
        d2, a2 = flip_with_affine(base_data[slot], aff, axis=0)
        fa_data[slot] = d2
        fa_affine = a2
    save_sequence_set("flip_same_anatomy", fa_data, fa_affine)
    print("  [x] Flip same anatomy set generated (flip_same_anatomy_*)")

    # 4. Orientation: Mirrored anatomy (Voxel flip on axis 0 + unchanged affine)
    mirrored_data = {s: np.flip(base_data[s], axis=0).copy() for s in SLOTS}
    save_sequence_set("flip_mirrored", mirrored_data, aff)
    print("  [x] Flip mirrored anatomy set generated (flip_mirrored_*)")

    # 5. Anisotropic Set (Downsample along axis 2 by taking every 2nd slice)
    aff_half = aff.copy()
    aff_half[:3, 2] *= 2.0  # Spacing along z doubles
    half_data = {s: base_data[s][:, :, ::2].copy() for s in SLOTS}
    save_sequence_set("half_slices", half_data, aff_half)
    print("  [x] Anisotropic half slices set generated (half_slices_*)")

    # 6. Linked Crosshair Marker Block
    marker_data = {s: base_data[s].copy() for s in SLOTS}
    # Place bright intensity block at known voxel region
    marker_data["t1gd"][60:64, 40:44, 30:34] = 2000.0
    save_sequence_set("marker", marker_data, aff)
    print("  [x] Crosshair marker set generated (marker_*)")

    # 7. Failure Pack (8 inputs for negative testing)
    # (a) Not a NIfTI file (text pretending to be nifti)
    (FIXTURES_DIR / "fail_notnifti.nii.gz").write_text("This is an invalid plain text file pretending to be nifti.")
    
    # (b) Corrupt / Truncated Gzip
    valid_bytes = (FIXTURES_DIR / "base_t1.nii.gz").read_bytes()
    (FIXTURES_DIR / "fail_corrupt_gzip.nii.gz").write_bytes(valid_bytes[: len(valid_bytes) // 3])
    
    # (c) 2D Image instead of 3D
    save_nifti(np.random.rand(64, 64).astype(np.float32), np.eye(4), "fail_2d.nii.gz")
    
    # (d) All zeros (constant)
    save_nifti(np.zeros_like(base_data["t1"]), aff, "fail_zeros.nii.gz")
    
    # (e) NaN values
    nan_data = base_data["t1"].copy()
    nan_data[15, 15, 15] = np.nan
    save_nifti(nan_data, aff, "fail_nan.nii.gz")
    
    # (f) Shape mismatch
    save_nifti(np.random.rand(50, 50, 40).astype(np.float32), aff, "fail_shape_mismatch.nii.gz")
    
    # (g) Expert mask with MSD/Decathlon code 3 (illegal in BraTS 2021)
    bad_code_mask = np.zeros(shape, dtype=np.uint8)
    bad_code_mask[20:30, 20:30, 20:30] = 3
    save_nifti(bad_code_mask, aff, "fail_code3.nii.gz")
    
    print("  [x] Failure pack generated (fail_notnifti, fail_corrupt_gzip, fail_2d, fail_zeros, fail_nan, fail_shape_mismatch, fail_code3)")
    print("\nAll fixtures generated successfully!")


if __name__ == "__main__":
    generate_all_fixtures()
