import * as nifti from 'nifti-reader-js';

const cache = {};

/**
 * Reads a single voxel intensity from a NIfTI file array in memory.
 * Caches the typed array once fetched so subsequent reads are instantaneous (0ms).
 */
export async function getVoxelIntensity(url, vox) {
  if (!url || !vox) return null;
  if (!cache[url]) {
    try {
      const res = await fetch(url);
      if (!res.ok) return null;
      let raw = await res.arrayBuffer();
      if (nifti.isCompressed(raw)) {
        raw = nifti.decompress(raw);
      }
      const hdr = nifti.readHeader(raw);
      const img = nifti.readImage(hdr, raw);
      let data = null;
      if (hdr.datatypeCode === 16) {
        data = new Float32Array(img);
      } else if (hdr.datatypeCode === 64) {
        data = new Float64Array(img);
      } else if (hdr.datatypeCode === 4) {
        data = new Int16Array(img);
      } else if (hdr.datatypeCode === 2) {
        data = new Uint8Array(img);
      } else {
        data = new Float32Array(img);
      }
      cache[url] = {
        data,
        dims: [hdr.dims[1] || 240, hdr.dims[2] || 240, hdr.dims[3] || 155]
      };
    } catch (err) {
      console.warn('[mriVolumeCache] fetch error:', err);
      return null;
    }
  }

  const entry = cache[url];
  if (!entry) return null;
  const [dx, dy, dz] = entry.dims;
  const x = Math.round(vox[0]);
  const y = Math.round(vox[1]);
  const z = Math.round(vox[2]);
  if (x < 0 || x >= dx || y < 0 || y >= dy || z < 0 || z >= dz) return null;
  return entry.data[x + y * dx + z * dx * dy];
}

export function getCachedVoxelIntensitySync(url, vox) {
  const entry = cache[url];
  if (!entry || !vox) return null;
  const [dx, dy, dz] = entry.dims;
  const x = Math.round(vox[0]);
  const y = Math.round(vox[1]);
  const z = Math.round(vox[2]);
  if (x < 0 || x >= dx || y < 0 || y >= dy || z < 0 || z >= dz) return null;
  return entry.data[x + y * dx + z * dx * dy];
}
