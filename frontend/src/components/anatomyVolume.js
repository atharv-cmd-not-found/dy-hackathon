import * as nifti from 'nifti-reader-js';

let cachedUrl = null;
let cachedData = null;
let cachedDims = [240, 240, 155];
let loadingPromise = null;

/**
 * Loads an anatomy NIfTI volume in memory as a typed array.
 * Decouples anatomy voxel lookup from NiiVue WebGL texture pipelines,
 * preventing GPU texture allocation limits and shader overlay conflicts.
 */
export async function loadAnatomyData(url) {
  if (!url) return null;
  if (cachedUrl === url && cachedData) {
    return { data: cachedData, dims: cachedDims };
  }
  if (loadingPromise && cachedUrl === url) {
    return loadingPromise;
  }

  cachedUrl = url;
  loadingPromise = (async () => {
    try {
      const res = await fetch(url);
      if (!res.ok) {
        console.warn('[loadAnatomyData] HTTP error:', res.status);
        return null;
      }
      let raw = await res.arrayBuffer();
      if (nifti.isCompressed(raw)) {
        raw = nifti.decompress(raw);
      }
      const hdr = nifti.readHeader(raw);
      const img = nifti.readImage(hdr, raw);
      cachedData = new Int16Array(img);
      cachedDims = [hdr.dims[1] || 240, hdr.dims[2] || 240, hdr.dims[3] || 155];
      return { data: cachedData, dims: cachedDims };
    } catch (err) {
      console.warn('[loadAnatomyData] Failed to parse anatomy NIfTI:', err);
      return null;
    } finally {
      loadingPromise = null;
    }
  })();

  return loadingPromise;
}

/**
 * Retrieves the SRI24 anatomy label for a given voxel coordinate [x, y, z].
 * Uses inward ray-stepping and radial neighborhood searching near cortex/CSF
 * to ensure robust parcellation identity.
 */
export function queryAnatomyValue(anatData, dims, vox) {
  if (!anatData || !dims || !vox) return 0;
  const [dimX, dimY, dimZ] = dims;
  const x = Math.round(vox[0]);
  const y = Math.round(vox[1]);
  const z = Math.round(vox[2]);
  if (x < 0 || x >= dimX || y < 0 || y >= dimY || z < 0 || z >= dimZ) return 0;

  const directVal = Math.round(anatData[x + y * dimX + z * dimX * dimY] || 0);
  if (directVal > 0) return directVal;

  // Near cortical boundaries/CSF, probe inward towards brain center
  const cX = dimX / 2.0;
  const cY = dimY / 2.0;
  const cZ = dimZ / 2.0;
  const dX = cX - x;
  const dY = cY - y;
  const dZ = cZ - z;
  const dist = Math.sqrt(dX * dX + dY * dY + dZ * dZ) || 1.0;
  const uX = dX / dist;
  const uY = dY / dist;
  const uZ = dZ / dist;

  // 1. Inward ray stepping (1 to 22 voxels)
  for (let s = 1; s <= 22; s++) {
    const sx = Math.round(x + uX * s);
    const sy = Math.round(y + uY * s);
    const sz = Math.round(z + uZ * s);
    if (sx >= 0 && sx < dimX && sy >= 0 && sy < dimY && sz >= 0 && sz < dimZ) {
      const sVal = Math.round(anatData[sx + sy * dimX + sz * dimX * dimY] || 0);
      if (sVal > 0) return sVal;
    }
  }

  // 2. Local radial neighborhood search
  for (let r = 1; r <= 5; r++) {
    for (let dx = -r; dx <= r; dx += r) {
      for (let dy = -r; dy <= r; dy += r) {
        for (let dz = -r; dz <= r; dz += r) {
          const qx = x + dx;
          const qy = y + dy;
          const qz = z + dz;
          if (qx >= 0 && qx < dimX && qy >= 0 && qy < dimY && qz >= 0 && qz < dimZ) {
            const qVal = Math.round(anatData[qx + qy * dimX + qz * dimX * dimY] || 0);
            if (qVal > 0) return qVal;
          }
        }
      }
    }
  }

  return 0;
}
