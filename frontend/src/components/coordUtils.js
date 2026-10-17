/**
 * Coordinate transformations and anatomical inspection utilities for NeuroScope 3D.
 * Handles voxel <-> world (RAS+ mm) conversions, 4x4 matrix inversions,
 * bounds checking, and tumour prediction label mapping.
 */

export function invert4x4(m) {
  if (!m || m.length < 4) return null;
  const a = m.flat();
  const inv = new Array(16);

  inv[0] = a[5]*a[10]*a[15] - a[5]*a[11]*a[14] - a[9]*a[6]*a[15] + a[9]*a[7]*a[14] + a[13]*a[6]*a[11] - a[13]*a[7]*a[10];
  inv[4] = -a[4]*a[10]*a[15] + a[4]*a[11]*a[14] + a[8]*a[6]*a[15] - a[8]*a[7]*a[14] - a[12]*a[6]*a[11] + a[12]*a[7]*a[10];
  inv[8] = a[4]*a[9]*a[15] - a[4]*a[11]*a[13] - a[8]*a[5]*a[15] + a[8]*a[7]*a[13] + a[12]*a[5]*a[11] - a[12]*a[7]*a[9];
  inv[12] = -a[4]*a[9]*a[14] + a[4]*a[10]*a[13] + a[8]*a[5]*a[14] - a[8]*a[6]*a[13] - a[12]*a[5]*a[10] + a[12]*a[6]*a[9];
  inv[1] = -a[1]*a[10]*a[15] + a[1]*a[11]*a[14] + a[9]*a[2]*a[15] - a[9]*a[3]*a[14] - a[13]*a[2]*a[11] + a[13]*a[3]*a[10];
  inv[5] = a[0]*a[10]*a[15] - a[0]*a[11]*a[14] - a[8]*a[2]*a[15] + a[8]*a[3]*a[14] + a[12]*a[2]*a[11] - a[12]*a[3]*a[10];
  inv[9] = -a[0]*a[9]*a[15] + a[0]*a[11]*a[13] + a[8]*a[1]*a[15] - a[8]*a[3]*a[13] - a[12]*a[1]*a[11] + a[12]*a[3]*a[9];
  inv[13] = a[0]*a[9]*a[14] - a[0]*a[10]*a[13] - a[8]*a[1]*a[14] + a[8]*a[2]*a[13] + a[12]*a[1]*a[10] - a[12]*a[2]*a[9];
  inv[2] = a[1]*a[6]*a[15] - a[1]*a[7]*a[14] - a[5]*a[2]*a[15] + a[5]*a[3]*a[14] + a[13]*a[2]*a[7] - a[13]*a[3]*a[6];
  inv[6] = -a[0]*a[6]*a[15] + a[0]*a[7]*a[14] + a[4]*a[2]*a[15] - a[4]*a[3]*a[14] - a[12]*a[2]*a[7] + a[12]*a[3]*a[6];
  inv[10] = a[0]*a[5]*a[15] - a[0]*a[7]*a[13] - a[4]*a[1]*a[15] + a[4]*a[3]*a[13] + a[12]*a[1]*a[7] - a[12]*a[3]*a[5];
  inv[14] = -a[0]*a[5]*a[14] + a[0]*a[6]*a[13] + a[4]*a[1]*a[14] - a[4]*a[2]*a[13] - a[12]*a[1]*a[6] + a[12]*a[2]*a[5];
  inv[3] = -a[1]*a[6]*a[11] + a[1]*a[7]*a[10] + a[5]*a[2]*a[11] - a[5]*a[3]*a[10] - a[9]*a[2]*a[7] + a[9]*a[3]*a[6];
  inv[7] = a[0]*a[6]*a[11] - a[0]*a[7]*a[10] - a[4]*a[2]*a[11] + a[4]*a[3]*a[10] + a[8]*a[2]*a[7] - a[8]*a[3]*a[6];
  inv[11] = -a[0]*a[5]*a[11] + a[0]*a[7]*a[9] + a[4]*a[1]*a[11] - a[4]*a[3]*a[9] - a[8]*a[1]*a[7] + a[8]*a[3]*a[5];
  inv[15] = a[0]*a[5]*a[10] - a[0]*a[6]*a[9] - a[4]*a[1]*a[10] + a[4]*a[2]*a[9] + a[8]*a[1]*a[6] - a[8]*a[2]*a[5];

  let det = a[0]*inv[0] + a[1]*inv[4] + a[2]*inv[8] + a[3]*inv[12];
  if (Math.abs(det) < 1e-8) return null;
  det = 1.0 / det;

  const res = [];
  for (let i = 0; i < 4; i++) {
    res.push([
      inv[i * 4] * det,
      inv[i * 4 + 1] * det,
      inv[i * 4 + 2] * det,
      inv[i * 4 + 3] * det
    ]);
  }
  return res;
}

export function voxelToWorld(vox, affine) {
  if (!vox || !affine) return [0, 0, 0];
  const [i, j, k] = vox;
  const x = affine[0][0] * i + affine[0][1] * j + affine[0][2] * k + affine[0][3];
  const y = affine[1][0] * i + affine[1][1] * j + affine[1][2] * k + affine[1][3];
  const z = affine[2][0] * i + affine[2][1] * j + affine[2][2] * k + affine[2][3];
  return [Math.round(x * 10) / 10, Math.round(y * 10) / 10, Math.round(z * 10) / 10];
}

export function worldToVoxel(mm, invAffine) {
  if (!mm || !invAffine) return [0, 0, 0];
  const [x, y, z] = mm;
  const i = invAffine[0][0] * x + invAffine[0][1] * y + invAffine[0][2] * z + invAffine[0][3];
  const j = invAffine[1][0] * x + invAffine[1][1] * y + invAffine[1][2] * z + invAffine[1][3];
  const k = invAffine[2][0] * x + invAffine[2][1] * y + invAffine[2][2] * z + invAffine[2][3];
  return [Math.round(i), Math.round(j), Math.round(k)];
}

export function isVoxelInBounds(vox, shape) {
  if (!vox || !shape || shape.length < 3) return false;
  return (
    vox[0] >= 0 && vox[0] < shape[0] &&
    vox[1] >= 0 && vox[1] < shape[1] &&
    vox[2] >= 0 && vox[2] < shape[2]
  );
}

export function getTumourStatusInfo(predVal) {
  const p = Math.round(predVal || 0);
  switch (p) {
    case 1:
      return {
        label: 'NCR',
        code: 1,
        name: 'Necrotic Core (NCR · Label 1)',
        description: 'Inside predicted necrotic tumour core',
        memberships: ['WT', 'TC'],
        status: 'inside_tumor',
        color: 'var(--color-tc)',
        badgeClass: 'badge-red'
      };
    case 2:
      return {
        label: 'ED',
        code: 2,
        name: 'Peritumoural Edema (ED · Label 2)',
        description: 'Inside predicted peritumoural edematous tissue',
        memberships: ['WT'],
        status: 'inside_tumor',
        color: 'var(--color-wt)',
        badgeClass: 'badge-amber'
      };
    case 4:
      return {
        label: 'ET',
        code: 4,
        name: 'Enhancing Tumour (ET · Label 4)',
        description: 'Inside predicted active contrast-enhancing tumour rim',
        memberships: ['WT', 'TC', 'ET'],
        status: 'inside_tumor',
        color: 'var(--color-et)',
        badgeClass: 'badge-cyan'
      };
    default:
      return {
        label: 'Normal',
        code: 0,
        name: 'Outside predicted tumour',
        description: 'Outside model-predicted tumour mask',
        memberships: [],
        status: 'outside_tumor',
        color: '#64748b',
        badgeClass: 'badge-gray'
      };
  }
}
