import React, { useEffect, useRef, useState } from 'react';
import { Niivue } from '@niivue/niivue';
import { Layers } from 'lucide-react';
import { CROSSHAIR_COLOR, REGION_COLORS } from './segmentationColors';

const toRgb = (hex) => {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
};

const rgba = (hex, alpha = 255) => [...toRgb(hex), alpha];

const SEGMENTATION_LABELS = {
  lut: new Uint8ClampedArray([
    ...rgba('#000000', 0),
    ...rgba(REGION_COLORS.tc),
    ...rgba(REGION_COLORS.wt),
    ...rgba('#000000', 0),
    ...rgba(REGION_COLORS.et),
  ]),
  min: 0,
  max: 4,
  labels: ['Background', 'TC · Core', 'WT · Edema', 'Unused', 'ET · Enhancing'],
};

/**
 * Viewer2D — NiiVue-powered multiplanar MRI viewer.
 *
 * KEY FIX: NiiVue reads the canvas size at attachToCanvas() time.
 * If the canvas is 0×0 (CSS not yet laid out), it renders nothing.
 * We use a ResizeObserver + a deferred init pattern so we only
 * call attachToCanvas after the container has real pixel dimensions.
 *
 * KEY FIX 2: NiiVue detects file type from the `name` field extension
 * (`.nii.gz`), NOT from the URL path or Content-Type header.
 * We must pass name: 't1.nii.gz' etc., not a display string.
 */
export default function Viewer2D({ t1Url, predUrl, crosshair, onCrosshairChange }) {
  const canvasRef   = useRef(null);
  const wrapperRef  = useRef(null);
  const nvRef       = useRef(null);          // NiiVue instance
  const initRef     = useRef(false);         // guard: init only once per URL set
  const urlsRef     = useRef({ t1Url, predUrl }); // latest URLs without stale closure

  const [opacity,   setOpacity]   = useState(0.65);
  const [sliceType, setSliceType] = useState(3);   // 3 = Multiplanar
  const [loading,   setLoading]   = useState(true);
  const [errorMsg,  setErrorMsg]  = useState(null);

  // keep urlsRef current
  urlsRef.current = { t1Url, predUrl };

  // ─── Helper: extract .nii.gz filename from any URL path ────────────────────
  const slotName = (url) => {
    if (!url) return 'volume.nii.gz';
    const base = url.split('/').pop();       // last segment, e.g. "t1.nii.gz" or "t1"
    return base.endsWith('.nii.gz') ? base : base + '.nii.gz';
  };

  // ─── Teardown NiiVue ───────────────────────────────────────────────────────
  const destroyNV = () => {
    if (nvRef.current) {
      try { nvRef.current.closeAllVolumes(); } catch (_) {}
      nvRef.current = null;
    }
    initRef.current = false;
  };

  // ─── Core init: only runs when canvas has real dimensions ─────────────────
  const doInit = async () => {
    if (initRef.current) return;              // already inited
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;  // not laid out yet

    const { t1Url: t1, predUrl: pred } = urlsRef.current;
    if (!t1) return;

    initRef.current = true;
    setLoading(true);
    setErrorMsg(null);

    try {
      // ── Create NiiVue ──────────────────────────────────────────────────────
      const nv = new Niivue({
        backColor:         [0.06, 0.09, 0.16, 1],   // #0f172a
        crosshairColor:    [...toRgb(CROSSHAIR_COLOR).map(value => value / 255), 0.9],
        crosshairWidth:    1.5,
        show3Dcrosshair:   false,
        isColorbar:        false,
        isOrientCube:      true,
        multiplanarForceRender: true,
        dragMode:          1,  // 1 = contrast/brightness pan
      });

      nv.attachToCanvas(canvas);
      nvRef.current = nv;

      // ── Linked crosshair callback ──────────────────────────────────────────
      nv.onLocationChange = (data) => {
        if (data?.mm && data?.vox) {
          onCrosshairChange({
            mm:  data.mm.map(v => Math.round(v * 10) / 10),
            vox: data.vox.map(v => Math.round(v)),
            val: data.values?.[1] ?? 0,
          });
        }
      };

      // ── Build volume list — MUST pass name with .nii.gz extension ─────────
      const volumes = [
        { url: t1, name: slotName(t1), colorMap: 'gray', opacity: 1.0 },
      ];
      if (pred) {
        volumes.push({
          url: pred,
          name: slotName(pred),
          colorMap: 'gray',
          opacity: 0.65,
        });
      }

      await nv.loadVolumes(volumes);
      if (pred && nv.volumes[1]) {
        // loadVolumes currently does not forward colormapLabel in its URL options.
        nv.volumes[1].colormapLabel = SEGMENTATION_LABELS;
        nv.drawScene();
      }
      nv.setSliceType(sliceType);
    } catch (err) {
      console.error('[Viewer2D] NiiVue error:', err);
      setErrorMsg(
        `Could not load MRI volume.\n` +
        `URL: ${t1}\n` +
        `Error: ${err?.message || err}`
      );
      initRef.current = false;
    } finally {
      setLoading(false);
    }
  };

  // ─── Effect: re-init whenever URLs change ─────────────────────────────────
  useEffect(() => {
    destroyNV();
    if (!t1Url) { setLoading(false); return; }
    setLoading(true);

    // Try immediately (layout may already be settled)
    doInit();

    // ResizeObserver: fires when wrapper gets real dimensions
    const obs = new ResizeObserver(() => doInit());
    if (wrapperRef.current) obs.observe(wrapperRef.current);

    return () => {
      obs.disconnect();
      destroyNV();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t1Url, predUrl]);

  // ─── Opacity live update ───────────────────────────────────────────────────
  const handleOpacity = (e) => {
    const val = parseFloat(e.target.value);
    setOpacity(val);
    if (nvRef.current?.volumes?.length > 1) {
      nvRef.current.setOpacity(1, val);
    }
  };

  // ─── Slice type ────────────────────────────────────────────────────────────
  const handleSlice = (type) => {
    setSliceType(type);
    nvRef.current?.setSliceType(type);
  };

  // ──────────────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div style={{
        padding: '0.45rem 0.85rem',
        background: '#ffffff',
        borderBottom: '1px solid var(--border-light)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        fontSize: '0.8rem', flexShrink: 0, gap: '0.5rem', flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <Layers size={14} color="var(--primary-blue)" />
          <span style={{ fontWeight: 600 }}>2D Multiplanar View</span>
          <span className="badge" style={{ background: '#f1f5f9', fontSize: '0.68rem' }}>
            Axial · Coronal · Sagittal
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
          {/* Mask opacity */}
          {predUrl && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Mask:</span>
              <input type="range" min="0" max="1" step="0.05" value={opacity}
                onChange={handleOpacity}
                style={{ width: '68px', cursor: 'pointer', accentColor: '#06b6d4' }} />
              <span style={{ fontSize: '0.7rem', fontFamily: 'var(--font-mono)', minWidth: '2.2em' }}>
                {Math.round(opacity * 100)}%
              </span>
            </div>
          )}

          {/* View mode buttons */}
          <div style={{ display: 'flex', background: 'var(--bg-subtle)', borderRadius: '4px', padding: '2px', gap: '1px' }}>
            {[
              { label: 'Multi', t: 3 },
              { label: 'Axial', t: 0 },
              { label: 'Cor',   t: 1 },
              { label: 'Sag',   t: 2 },
            ].map(({ label, t }) => (
              <button key={t} onClick={() => handleSlice(t)} style={{
                border: 'none', cursor: 'pointer', borderRadius: '3px',
                fontSize: '0.68rem', padding: '2px 6px',
                background: sliceType === t ? '#ffffff' : 'transparent',
                fontWeight: sliceType === t ? 600 : 400,
                color: sliceType === t ? 'var(--primary-blue)' : 'var(--text-secondary)',
                boxShadow: sliceType === t ? '0 1px 2px rgba(0,0,0,0.1)' : 'none',
                transition: 'all 0.1s',
              }}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Canvas wrapper (ResizeObserver target) ─────────────────────── */}
      <div ref={wrapperRef}
        style={{ flex: 1, position: 'relative', background: '#0f172a', overflow: 'hidden', minHeight: 0 }}>

        <canvas ref={canvasRef}
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block' }} />

        {/* Loading */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 5,
            background: 'rgba(15,23,42,0.9)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center', gap: '0.75rem',
          }}>
            <div style={{
              width: 34, height: 34,
              border: '3px solid rgba(255,255,255,0.12)',
              borderTop: '3px solid #06b6d4',
              borderRadius: '50%',
              animation: 'nvSpin 0.75s linear infinite',
            }} />
            <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
              Loading MRI slices…
            </span>
            <style>{`@keyframes nvSpin { to { transform:rotate(360deg); } }`}</style>
          </div>
        )}

        {/* Error */}
        {errorMsg && !loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 5,
            background: 'rgba(15,23,42,0.92)',
            display: 'flex', flexDirection: 'column',
            alignItems: 'center', justifyContent: 'center',
            gap: '0.5rem', color: '#f87171', padding: '1.5rem', textAlign: 'center',
          }}>
            <span style={{ fontSize: '1.6rem' }}>⚠️</span>
            <pre style={{
              fontSize: '0.72rem', whiteSpace: 'pre-wrap',
              maxWidth: '300px', lineHeight: 1.6, color: '#fca5a5',
            }}>{errorMsg}</pre>
          </div>
        )}

        {/* Watermark */}
        {!loading && !errorMsg && (
          <span style={{
            position: 'absolute', bottom: 5, right: 8, zIndex: 4,
            fontSize: '0.62rem', color: 'rgba(148,163,184,0.55)',
            fontFamily: 'var(--font-mono)', pointerEvents: 'none',
          }}>RAS+ · mm</span>
        )}
      </div>

      {predUrl && (
        <div style={{
          padding: '0.4rem 0.85rem',
          background: '#0f172a',
          borderTop: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0.9rem',
          flexWrap: 'wrap',
          flexShrink: 0,
        }}>
          {[
            { label: 'WT · Edema', color: REGION_COLORS.wt },
            { label: 'TC · Core', color: REGION_COLORS.tc },
            { label: 'ET · Enhancing', color: REGION_COLORS.et },
          ].map(({ label, color }) => (
            <div key={label} style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem',
              fontSize: '0.68rem',
              color: '#cbd5e1',
            }}>
              <span style={{
                width: 8,
                height: 8,
                borderRadius: '2px',
                background: color,
                display: 'inline-block',
              }} />
              <span>{label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
