import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Niivue } from '@niivue/niivue';
import { Layers, AlertCircle, RefreshCw } from 'lucide-react';
import { CROSSHAIR_COLOR, REGION_COLORS } from './segmentationColors';
import HoverTooltip from './HoverTooltip';
import { loadAnatomyData, queryAnatomyValue } from './anatomyVolume';
import { getVoxelIntensity, getCachedVoxelIntensitySync } from './mriVolumeCache';

const toRgb = (hex) => {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
};

const rgba = (hex, alpha = 255) => [...toRgb(hex), alpha];

// Discrete RGBA colormap lookup for BraTS labels (0: Bg, 1: NCR, 2: ED, 3: Unused, 4: ET)
export const SEGMENTATION_LABELS = {
  lut: new Uint8ClampedArray([
    ...rgba('#000000', 0),                        // 0: Background
    ...rgba(REGION_COLORS.ncr || '#ef4444', 255), // 1: NCR / Necrotic Core (Crimson Ruby)
    ...rgba(REGION_COLORS.ed || '#f59e0b', 255),  // 2: ED / Peritumoral Edema (Warm Amber Gold)
    ...rgba('#000000', 0),                        // 3: Unused
    ...rgba(REGION_COLORS.et || '#06b6d4', 255),  // 4: ET / Enhancing Tumour (Luminous Electric Cyan)
  ]),
  min: 0,
  max: 4,
  labels: ['Background', 'NCR · Necrotic Core', 'ED · Peritumoral Edema', 'Unused', 'ET · Enhancing Tumour'],
};

/**
 * Normalizes any input representation (string URL, File, Blob, ArrayBuffer) into
 * an object suitable for NiiVue's loadVolumes with a valid extension.
 */
function resolveVolumeSource(src, fallbackName = 'volume.nii.gz') {
  if (!src) return null;

  // File instance
  if (typeof File !== 'undefined' && src instanceof File) {
    const rawName = src.name || fallbackName;
    const name = (rawName.endsWith('.nii.gz') || rawName.endsWith('.nii'))
      ? rawName
      : `${rawName}.nii.gz`;
    return {
      url: URL.createObjectURL(src),
      name,
      isBlobUrl: true,
    };
  }

  // Blob instance
  if (typeof Blob !== 'undefined' && src instanceof Blob) {
    return {
      url: URL.createObjectURL(src),
      name: fallbackName,
      isBlobUrl: true,
    };
  }

  // ArrayBuffer or TypedArray view
  if (src instanceof ArrayBuffer || (ArrayBuffer.isView && ArrayBuffer.isView(src))) {
    const blob = new Blob([src]);
    return {
      url: URL.createObjectURL(blob),
      name: fallbackName,
      isBlobUrl: true,
    };
  }

  // String URL
  if (typeof src === 'string') {
    const cleanUrl = src.split('?')[0];
    const rawName = cleanUrl.split('/').pop() || fallbackName;
    const name = (rawName.endsWith('.nii.gz') || rawName.endsWith('.nii'))
      ? rawName
      : `${rawName}.nii.gz`;
    return {
      url: src,
      name,
      isBlobUrl: false,
    };
  }

  return null;
}

export default function Viewer2D({
  files = {},
  t1Url,
  predUrl,
  anatomyLookup,
  crosshair,
  onCrosshairChange,
  activeUnderlay = 't1',
  onUnderlayChange,
  onNVReady
}) {
  const canvasRef             = useRef(null);
  const wrapperRef            = useRef(null);
  const nvRef                 = useRef(null);
  const isMountedRef          = useRef(true);
  const isCanvasAttachedRef   = useRef(false);
  const isLoadingRef          = useRef(false);
  const pendingLoadRef        = useRef(false);
  const createdBlobUrls       = useRef(new Set());
  const isLoadedRef           = useRef(false);
  const rafRef                = useRef(null);
  const hoverRafRef           = useRef(null);
  const anatomyDataRef        = useRef(null);
  const extractDataRef        = useRef(null);
  const onCrosshairRef        = useRef(onCrosshairChange);
  const loadedKeyRef          = useRef('');
  const isUpdatingCrosshairRef = useRef(false);
  const loadActiveVolumesRef  = useRef(null);

  const [opacity,   setOpacity]   = useState(0.65);
  const [sliceType, setSliceType] = useState(3); // 3 = Multiplanar (Axial, Coronal, Sagittal)
  const [loading,   setLoading]   = useState(true);
  const [errorMsg,  setErrorMsg]  = useState(null);

  // Hover state for cursor tooltip
  const [hoverState, setHoverState] = useState(null);

  // Keep references current without triggering reruns
  onCrosshairRef.current     = onCrosshairChange;
  const opacityRef           = useRef(opacity);
  const sliceTypeRef         = useRef(sliceType);
  const filesRef             = useRef(files);
  const activeUnderlayRef    = useRef(activeUnderlay);
  const anatomyLookupRef     = useRef(anatomyLookup);

  opacityRef.current         = opacity;
  sliceTypeRef.current       = sliceType;
  filesRef.current           = files;
  activeUnderlayRef.current  = activeUnderlay;
  anatomyLookupRef.current   = anatomyLookup;

  // Resolve raw source handles
  const rawUnderlay = files?.[activeUnderlay] ||
    files?.t1 ||
    files?.t1gd ||
    files?.t2 ||
    files?.flair ||
    files?.image ||
    files?.volume ||
    files?.file ||
    files?.mri ||
    t1Url;

  const rawPred    = files?.pred_nii || predUrl;
  const rawAnatomy = files?.anatomy_nii;

  // Pre-load anatomy NIfTI in background into typed array
  useEffect(() => {
    if (rawAnatomy && typeof rawAnatomy === 'string') {
      loadAnatomyData(rawAnatomy).then((res) => {
        if (isMountedRef.current) {
          anatomyDataRef.current = res;
        }
      }).catch((err) => {
        console.warn('[Viewer2D] Anatomy preload warning:', err);
      });
    }
  }, [rawAnatomy]);

  const cleanupBlobUrls = () => {
    createdBlobUrls.current.forEach((url) => {
      try { URL.revokeObjectURL(url); } catch (_) {}
    });
    createdBlobUrls.current.clear();
  };

  // ─── Query Voxel Values (Referentially stable) ───────────────────────────
  const extractVoxelData = useCallback((vox, mm) => {
    const nv = nvRef.current;
    if (!nv || !nv.volumes || nv.volumes.length === 0) return null;

    const curUnderlay = activeUnderlayRef.current;
    const curFiles    = filesRef.current || {};
    const curLookup   = anatomyLookupRef.current;
    const intensities = {};
    let predVal       = 0;

    // Active underlay is always Volume 0 (guaranteed opacity 1.0)
    const baseVol = nv.volumes[0];
    if (baseVol) {
      intensities[curUnderlay] = baseVol.getValue(vox[0], vox[1], vox[2]);
    }

    // Pred mask volume is Volume 1
    const predVol = nv.volumes.find(v => {
      const n = (v.name || '').toLowerCase();
      return n.includes('pred') || n.includes('seg') || n.includes('mask') || n.includes('label');
    });
    if (predVol) {
      predVal = Math.round(predVol.getValue(vox[0], vox[1], vox[2]) || 0);
    }

    // Query anatomy via pure typed-array lookup
    let anatVal = 0;
    if (anatomyDataRef.current) {
      anatVal = queryAnatomyValue(
        anatomyDataRef.current.data,
        anatomyDataRef.current.dims,
        vox
      );
    }

    // Multi-modal intensity population (cached or active)
    ['t1', 't1gd', 't2', 'flair'].forEach((mod) => {
      if (mod === curUnderlay) return;
      const modSource = curFiles[mod];
      if (modSource && typeof modSource === 'string') {
        const cached = getCachedVoxelIntensitySync(modSource, vox);
        if (cached !== null) {
          intensities[mod] = cached;
        } else {
          getVoxelIntensity(modSource, vox);
        }
      }
    });

    const labelsObj     = curLookup?.labels || {};
    const labelMeta     = labelsObj[String(anatVal)];
    const isUnavailable = curLookup?.status === 'unavailable';
    const regionName    = isUnavailable
      ? 'Anatomical labels unavailable'
      : (labelMeta?.name || (anatVal > 0 ? `Structure #${anatVal}` : 'No anatomical label at this location'));

    return {
      mm,
      vox,
      predVal,
      anatVal,
      regionName,
      hemisphere: labelMeta?.hemisphere || null,
      lobe: labelMeta?.lobe || null,
      intensities,
      labelsUnavailable: isUnavailable,
      unavailableReason: curLookup?.message || '',
      activeModality: curUnderlay.toUpperCase(),
      activeIntensity: intensities[curUnderlay] ?? null
    };
  }, []);

  extractDataRef.current = extractVoxelData;

  // ─── Serialized Volume Loader (Single In-Flight WebGL Task, Guarded Cache) ─
  const loadActiveVolumes = useCallback(async () => {
    const nv = nvRef.current;
    if (!nv) return;

    if (!rawUnderlay) {
      setLoading(false);
      isLoadingRef.current = false;
      return;
    }

    // Build stable configuration key
    const underlayKey = typeof rawUnderlay === 'string' ? rawUnderlay : (rawUnderlay?.name || 'underlayBlob');
    const predKey     = typeof rawPred === 'string' ? rawPred : (rawPred?.name || 'predNone');
    const currentKey  = `${activeUnderlay}::${underlayKey}::${predKey}`;

    // If identical configuration is already loaded, ensure scene is drawn and return
    if (loadedKeyRef.current === currentKey && nv.volumes && nv.volumes.length > 0) {
      nv.drawScene();
      return;
    }

    if (isLoadingRef.current) {
      pendingLoadRef.current = true;
      return;
    }

    isLoadingRef.current = true;
    setLoading(true);
    setErrorMsg(null);

    const underlayResolved = resolveVolumeSource(rawUnderlay, `${activeUnderlay}.nii.gz`);
    if (!underlayResolved) {
      setLoading(false);
      isLoadingRef.current = false;
      setErrorMsg('Invalid MRI input format. Expected .nii or .nii.gz file/URL.');
      return;
    }

    if (underlayResolved.isBlobUrl) {
      createdBlobUrls.current.add(underlayResolved.url);
    }

    let predResolved = null;
    if (rawPred) {
      predResolved = resolveVolumeSource(rawPred, 'prediction.nii.gz');
      if (predResolved?.isBlobUrl) {
        createdBlobUrls.current.add(predResolved.url);
      }
    }

    // Preserve crosshair position across volume updates
    const curFrac = nv.scene?.crosshairPos ? [...nv.scene.crosshairPos] : null;

    try {
      const volumesToLoad = [
        {
          url: underlayResolved.url,
          name: underlayResolved.name,
          colorMap: 'gray',
          opacity: 1.0,
        },
        ...(predResolved ? [{
          url: predResolved.url,
          name: predResolved.name,
          opacity: opacityRef.current,
          colormapLabel: SEGMENTATION_LABELS,
        }] : [])
      ];

      await nv.loadVolumes(volumesToLoad);

      if (!isMountedRef.current) return;

      // Ensure discrete LUT is set on the prediction mask volume
      if (predResolved) {
        const predVol = nv.volumes.find(v => {
          const n = (v.name || '').toLowerCase();
          return n.includes('pred') || n.includes('seg') || n.includes('mask') || n.includes('label');
        });
        if (predVol) {
          predVol.colormapLabel = SEGMENTATION_LABELS;
        }
      }

      if (curFrac) {
        nv.scene.crosshairPos = curFrac;
      }

      nv.setSliceType(sliceTypeRef.current);
      try {
        nv.resizeListener();
      } catch (_) {
        nv.drawScene();
      }
      isLoadedRef.current = true;
      loadedKeyRef.current = currentKey;
    } catch (err) {
      if (!isMountedRef.current) return;
      console.error('[Viewer2D] NiiVue volume load error:', err);
      setErrorMsg(
        `Failed to render MRI volume.\n` +
        `File: ${underlayResolved?.name || 'unknown'}\n` +
        `Details: ${err?.message || err}`
      );
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
        isLoadingRef.current = false;
        // If a new load request arrived while busy, process it
        if (pendingLoadRef.current) {
          pendingLoadRef.current = false;
          loadActiveVolumesRef.current?.();
        }
      }
    }
  }, [rawUnderlay, rawPred, activeUnderlay]);

  loadActiveVolumesRef.current = loadActiveVolumes;

  // ─── Component Mount Lifecycle: Initialize NiiVue ONCE ───────────────────
  useEffect(() => {
    isMountedRef.current = true;
    const canvas = canvasRef.current;
    const wrapper = wrapperRef.current;
    if (!canvas || !wrapper) return;

    // Prevent Chromium from treating WebGL context loss as fatal
    const handleContextLost = (e) => {
      e.preventDefault();
      console.warn('[Viewer2D] WebGL context lost; preventing fatal tear-down.');
    };
    const handleContextRestored = () => {
      console.info('[Viewer2D] WebGL context restored; reloading textures.');
      loadedKeyRef.current = '';
      loadActiveVolumesRef.current?.();
    };
    canvas.addEventListener('webglcontextlost', handleContextLost, false);
    canvas.addEventListener('webglcontextrestored', handleContextRestored, false);

    let nv = nvRef.current;
    if (!nv) {
      nv = new Niivue({
        backColor:             [0.06, 0.09, 0.16, 1], // #0f172a
        crosshairColor:        [...toRgb(CROSSHAIR_COLOR).map(v => v / 255), 0.9],
        crosshairWidth:        1.5,
        show3Dcrosshair:       false,
        isColorbar:            false,
        isOrientCube:          true,
        multiplanarShowRender: 0,    // 0 = NEVER: 3 orthogonal views (Axial, Coronal, Sagittal)
        multiplanarEqualSize:  true, // Balanced multiplanar layout
        dragMode:              1,    // 1 = contrast / brightness adjustment
      });

      nvRef.current = nv;
      if (onNVReady) onNVReady(nv);

      // Register crosshair change handler once
      nv.onLocationChange = (data) => {
        // Prevent feedback loop if this location change was initiated programmatically
        if (isUpdatingCrosshairRef.current) return;
        if (!data?.mm || !data?.vox) return;
        const mm = data.mm.map(v => Math.round(v * 10) / 10);
        const vox = data.vox.map(v => Math.round(v));

        if (rafRef.current) cancelAnimationFrame(rafRef.current);
        rafRef.current = requestAnimationFrame(() => {
          if (extractDataRef.current) {
            const locInfo = extractDataRef.current(vox, mm);
            if (locInfo && onCrosshairRef.current) {
              onCrosshairRef.current(locInfo);
            }
          }
        });
      };
    }

    // Attach to canvas once, then trigger initial volume loading via latest ref
    nv.attachToCanvas(canvas).then(() => {
      if (!isMountedRef.current) return;
      isCanvasAttachedRef.current = true;
      loadActiveVolumesRef.current?.();
    }).catch((err) => {
      console.error('[Viewer2D] WebGL attach error:', err);
      if (isMountedRef.current) {
        setErrorMsg(`Failed to initialize WebGL graphics context:\n${err?.message || err}`);
        setLoading(false);
      }
    });

    // ResizeObserver purely triggers viewport and canvas resolution sync
    const obs = new ResizeObserver(() => {
      if (!isMountedRef.current) return;
      const activeNv = nvRef.current;
      if (activeNv && isCanvasAttachedRef.current) {
        try {
          activeNv.resizeListener();
        } catch (_) {
          activeNv.drawScene();
        }
      }
    });
    obs.observe(wrapper);

    return () => {
      isMountedRef.current = false;
      isCanvasAttachedRef.current = false;
      obs.disconnect();
      canvas.removeEventListener('webglcontextlost', handleContextLost);
      canvas.removeEventListener('webglcontextrestored', handleContextRestored);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (hoverRafRef.current) cancelAnimationFrame(hoverRafRef.current);
      cleanupBlobUrls();
      if (nvRef.current) {
        try {
          nvRef.current.cleanup();
          nvRef.current.closeAllVolumes();
        } catch (_) {}
        nvRef.current = null;
      }
      isLoadedRef.current = false;
      loadedKeyRef.current = '';
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Reactive Volume Sync (Runs whenever canvas is attached and sources change) ──
  useEffect(() => {
    if (nvRef.current && isCanvasAttachedRef.current) {
      loadActiveVolumes();
    }
  }, [activeUnderlay, rawUnderlay, rawPred, loadActiveVolumes]);

  // ─── Sync Crosshair from 3D View (Guarded Primitive Coordinate Check) ─────
  const cx = crosshair?.mm?.[0];
  const cy = crosshair?.mm?.[1];
  const cz = crosshair?.mm?.[2];

  useEffect(() => {
    const nv = nvRef.current;
    if (!nv || !isLoadedRef.current || cx === undefined || cy === undefined || cz === undefined) return;
    try {
      const frac = nv.mm2frac([cx, cy, cz], 0, true);
      if (frac && frac.length >= 3 && !isNaN(frac[0])) {
        const cur = nv.scene?.crosshairPos;
        // Don't redraw if already at this position
        if (cur &&
            Math.abs(cur[0] - frac[0]) < 1e-4 &&
            Math.abs(cur[1] - frac[1]) < 1e-4 &&
            Math.abs(cur[2] - frac[2]) < 1e-4) {
          return;
        }
        isUpdatingCrosshairRef.current = true;
        nv.scene.crosshairPos = frac;
        nv.drawScene();
        isUpdatingCrosshairRef.current = false;
      }
    } catch (_) {
      isUpdatingCrosshairRef.current = false;
    }
  }, [cx, cy, cz]);

  // ─── Mask Opacity Live Update (Hardware Texture Opacity, NO Reload) ─────────
  const handleOpacity = (e) => {
    const val = parseFloat(e.target.value);
    setOpacity(val);
    opacityRef.current = val;
    const nv = nvRef.current;
    if (nv && nv.volumes && nv.volumes.length > 1) {
      nv.volumes[1].opacity = val;
      try {
        nv.refreshLayers(nv.volumes[1], 1);
        nv.drawScene();
      } catch (err) {
        console.warn('[Viewer2D] Overlay opacity refresh warning:', err);
      }
    }
  };

  // ─── Slice Type Switch (Multiplanar vs Single Slice, NO Reload) ───────────
  const handleSlice = (type) => {
    setSliceType(type);
    nvRef.current?.setSliceType(type);
  };

  // ─── Canvas Mouse Interaction (Hover Tooltip & Pin Click) ────────────────
  const handleCanvasMouseMove = (e) => {
    const nv = nvRef.current;
    if (!nv || !nv.scene?.crosshairPos) return;

    const clientX = e.clientX;
    const clientY = e.clientY;

    if (hoverRafRef.current) cancelAnimationFrame(hoverRafRef.current);
    hoverRafRef.current = requestAnimationFrame(() => {
      hoverRafRef.current = null;
      if (!nv.scene?.crosshairPos) return;
      const vox = nv.frac2vox(nv.scene.crosshairPos);
      const mm = nv.frac2mm(nv.scene.crosshairPos, 0, true);
      const voxelData = extractVoxelData(vox, mm);
      if (voxelData) {
        setHoverState({
          ...voxelData,
          x: clientX,
          y: clientY
        });
      }
    });
  };

  const handleCanvasMouseLeave = () => {
    if (hoverRafRef.current) {
      cancelAnimationFrame(hoverRafRef.current);
      hoverRafRef.current = null;
    }
    setHoverState(null);
  };

  const handleCanvasClick = () => {
    const nv = nvRef.current;
    if (!nv || !nv.scene?.crosshairPos) return;

    const vox = nv.frac2vox(nv.scene.crosshairPos);
    const mm = nv.frac2mm(nv.scene.crosshairPos, 0, true);

    const voxelData = extractVoxelData(vox, mm);
    if (voxelData && onCrosshairRef.current) {
      onCrosshairRef.current({
        ...voxelData,
        isPinned: true
      });
    }
  };

  const availableModalities = ['t1', 't1gd', 't2', 'flair'].filter(k => Boolean(files?.[k] || (k === 't1' && t1Url)));
  const hasPred = Boolean(rawPred);
  const hasUnderlay = Boolean(rawUnderlay);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, position: 'relative', background: '#0b1120' }}>

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div style={{
        padding: '0.45rem 0.85rem',
        background: '#0d1424',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        fontSize: '0.8rem', flexShrink: 0, gap: '0.5rem', flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <Layers size={14} color="#38bdf8" />
          <span style={{ fontWeight: 600, color: '#f8fafc' }}>2D Multiplanar View</span>
          <span className="badge" style={{ background: 'rgba(255,255,255,0.08)', color: '#94a3b8', fontSize: '0.68rem' }}>
            Axial · Coronal · Sagittal
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          {/* Underlay Modality Selector */}
          {availableModalities.length > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', background: 'rgba(255,255,255,0.05)', padding: '2px', borderRadius: '4px' }}>
              <span style={{ fontSize: '0.68rem', color: '#94a3b8', paddingLeft: '4px' }}>Underlay:</span>
              {availableModalities.map((mod) => (
                <button
                  key={mod}
                  onClick={() => onUnderlayChange && onUnderlayChange(mod)}
                  style={{
                    border: 'none',
                    cursor: 'pointer',
                    borderRadius: '3px',
                    fontSize: '0.68rem',
                    padding: '2px 6px',
                    background: activeUnderlay === mod ? '#0284c7' : 'transparent',
                    color: activeUnderlay === mod ? '#ffffff' : '#94a3b8',
                    fontWeight: activeUnderlay === mod ? 600 : 400,
                    textTransform: 'uppercase',
                    transition: 'all 0.1s'
                  }}
                >
                  {mod === 't1gd' ? 'T1-Gd' : mod}
                </button>
              ))}
            </div>
          )}

          {/* Mask Opacity Slider (Only if prediction is available) */}
          {hasPred && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', color: '#94a3b8' }}>
              <span style={{ fontSize: '0.7rem' }}>Mask:</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={opacity}
                onChange={handleOpacity}
                style={{ width: '64px', cursor: 'pointer', accentColor: '#06b6d4' }}
              />
              <span style={{ fontSize: '0.7rem', fontFamily: 'var(--font-mono)', minWidth: '2.2em', color: '#38bdf8' }}>
                {Math.round(opacity * 100)}%
              </span>
            </div>
          )}

          {/* View Mode Buttons (Multiplanar vs Single Slices) */}
          <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', padding: '2px', gap: '1px' }}>
            {[
              { label: 'Multi', t: 3 },
              { label: 'Axial', t: 0 },
              { label: 'Cor',   t: 1 },
              { label: 'Sag',   t: 2 },
            ].map(({ label, t }) => (
              <button
                key={t}
                onClick={() => handleSlice(t)}
                style={{
                  border: 'none',
                  cursor: 'pointer',
                  borderRadius: '3px',
                  fontSize: '0.68rem',
                  padding: '2px 6px',
                  background: sliceType === t ? '#1e293b' : 'transparent',
                  fontWeight: sliceType === t ? 600 : 400,
                  color: sliceType === t ? '#38bdf8' : '#94a3b8',
                  boxShadow: sliceType === t ? '0 1px 2px rgba(0,0,0,0.2)' : 'none',
                  transition: 'all 0.1s',
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Canvas Wrapper (ResizeObserver target) ─────────────────────── */}
      <div
        ref={wrapperRef}
        onMouseMove={handleCanvasMouseMove}
        onMouseLeave={handleCanvasMouseLeave}
        onClick={handleCanvasClick}
        style={{ flex: 1, position: 'relative', background: '#0f172a', overflow: 'hidden', minHeight: 0, cursor: 'crosshair' }}
      >
        <canvas
          ref={canvasRef}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block', background: '#0f172a' }}
        />

        {/* 1. Loading State */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 5,
            background: 'rgba(15,23,42,0.88)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: '0.75rem',
            pointerEvents: 'none',
          }}>
            <div style={{
              width: 34, height: 34,
              border: '3px solid rgba(255,255,255,0.12)',
              borderTop: '3px solid #06b6d4',
              borderRadius: '50%',
              animation: 'nvSpin 0.75s linear infinite',
            }} />
            <span style={{ fontSize: '0.8rem', color: '#94a3b8', letterSpacing: '0.01em' }}>
              Loading MRI slices…
            </span>
            <style>{`@keyframes nvSpin { to { transform:rotate(360deg); } }`}</style>
          </div>
        )}

        {/* 2. Error State */}
        {errorMsg && !loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 6,
            background: 'rgba(15,23,42,0.95)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: '0.75rem', color: '#f87171', padding: '1.5rem', textAlign: 'center',
          }}>
            <div style={{
              width: 44, height: 44, borderRadius: '50%',
              background: 'rgba(239, 68, 68, 0.15)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#ef4444'
            }}>
              <AlertCircle size={24} />
            </div>
            <div style={{ fontSize: '0.92rem', fontWeight: 600, color: '#f87171' }}>
              MRI Slices Failed to Render
            </div>
            <pre style={{
              fontSize: '0.72rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              maxWidth: '360px', lineHeight: 1.5, color: '#fca5a5',
              background: 'rgba(0,0,0,0.3)', padding: '0.5rem 0.75rem',
              borderRadius: '4px', border: '1px solid rgba(239,68,68,0.2)',
              textAlign: 'left'
            }}>{errorMsg}</pre>
            <button
              onClick={() => loadActiveVolumes()}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.4rem',
                marginTop: '0.25rem',
                background: '#0284c7',
                color: '#ffffff',
                border: 'none',
                padding: '0.45rem 0.9rem',
                borderRadius: '4px',
                fontSize: '0.75rem',
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              <RefreshCw size={13} />
              Retry Loading
            </button>
          </div>
        )}

        {/* 3. Empty State (No scan selected) */}
        {!hasUnderlay && !loading && !errorMsg && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 4,
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: '0.75rem', padding: '2rem', textAlign: 'center',
            color: '#94a3b8',
          }}>
            <div style={{
              width: 48, height: 48, borderRadius: '50%',
              background: 'rgba(56, 189, 248, 0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#38bdf8', marginBottom: '0.25rem'
            }}>
              <Layers size={24} />
            </div>
            <div style={{ fontSize: '0.95rem', fontWeight: 600, color: '#f1f5f9' }}>
              No MRI Scan Selected
            </div>
            <p style={{ fontSize: '0.78rem', color: '#94a3b8', maxWidth: '280px', margin: 0, lineHeight: 1.5 }}>
              Upload a multi-sequence brain MRI or select a case to visualize axial, coronal, and sagittal cross-sections.
            </p>
          </div>
        )}

        {/* 4. Watermark & Space Hint */}
        {hasUnderlay && !loading && !errorMsg && (
          <div style={{
            position: 'absolute', bottom: 5, right: 8, zIndex: 4,
            display: 'flex', alignItems: 'center', gap: '0.4rem', pointerEvents: 'none'
          }}>
            <span style={{
              fontSize: '0.62rem', color: 'rgba(148,163,184,0.65)',
              fontFamily: 'var(--font-mono)'
            }}>
              RAS+ · SRI24 Aligned · mm
            </span>
          </div>
        )}
      </div>

      {/* ── Floating Hover Tooltip ───────────────────────────────────────── */}
      {hoverState && (
        <HoverTooltip
          x={hoverState.x}
          y={hoverState.y}
          mm={hoverState.mm}
          vox={hoverState.vox}
          predVal={hoverState.predVal}
          anatVal={hoverState.anatVal}
          regionName={hoverState.regionName}
          hemisphere={hoverState.hemisphere}
          lobe={hoverState.lobe}
          activeIntensity={hoverState.activeIntensity}
          activeModality={hoverState.activeModality}
          labelsUnavailable={hoverState.labelsUnavailable}
          unavailableReason={hoverState.unavailableReason}
        />
      )}

      {/* ── Bottom Legend Bar ────────────────────────────────────────────── */}
      <div style={{
        padding: '0.35rem 0.85rem',
        background: '#090d16',
        borderTop: '1px solid rgba(255,255,255,0.06)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: '1.25rem', fontSize: '0.7rem', color: '#cbd5e1', flexShrink: 0
      }}>
        {hasPred ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <span style={{ width: 8, height: 8, borderRadius: '2px', background: REGION_COLORS.ed, display: 'inline-block' }} />
              <span>ED · Edema</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <span style={{ width: 8, height: 8, borderRadius: '2px', background: REGION_COLORS.ncr, display: 'inline-block' }} />
              <span>NCR · Core</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <span style={{ width: 8, height: 8, borderRadius: '2px', background: REGION_COLORS.et, display: 'inline-block' }} />
              <span>ET · Enhancing</span>
            </div>
          </>
        ) : (
          <span style={{ color: '#94a3b8', fontSize: '0.68rem' }}>
            Underlay: {activeUnderlay.toUpperCase()} · 3 Orthogonal Views (Axial · Coronal · Sagittal)
          </span>
        )}
      </div>

    </div>
  );
}
