import React, { useState, useEffect, useRef, useCallback } from 'react';
import Navbar from './components/Navbar';
import UploadView from './components/UploadView';
import ProcessingView from './components/ProcessingView';
import Viewer2D from './components/Viewer2D';
import Viewer3D from './components/Viewer3D';
import MetricsPanel from './components/MetricsPanel';
import LocalizationView from './components/LocalizationView';
import EvalView from './components/EvalView';
import Footer from './components/Footer';
import { Layers, UploadCloud, Sparkles } from 'lucide-react';
import { loadAnatomyData, queryAnatomyValue } from './components/anatomyVolume';
import { getCachedVoxelIntensitySync, getVoxelIntensity } from './components/mriVolumeCache';

export default function App() {
  const [currentView, setCurrentView] = useState(() => {
    const hash = window.location.hash.replace('#', '');
    return ['upload', 'processing', 'viewer', 'localization', 'eval'].includes(hash) ? hash : 'upload';
  });
  const [activeCaseId, setActiveCaseId] = useState(null);
  const [caseData, setCaseData] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDemoLoading, setIsDemoLoading] = useState(false);

  const [crosshair, setCrosshair] = useState({
    mm: [0, 0, 0],
    vox: [0, 0, 0],
    anatVal: 0,
    predVal: 0,
    intensities: {},
    regionName: 'Click slice or 3D mesh to inspect',
    hemisphere: null,
    lobe: null,
    isPinned: false
  });
  const [activeUnderlay, setActiveUnderlay] = useState('t1');
  const pollIntervalRef = useRef(null);
  const nvInstanceRef = useRef(null);
  const anatDataRef = useRef(null);

  // Pre-load anatomy NIfTI when case data is ready
  useEffect(() => {
    if (caseData?.files?.anatomy_nii) {
      loadAnatomyData(caseData.files.anatomy_nii).then((res) => {
        anatDataRef.current = res;
      });
    }
  }, [caseData?.files?.anatomy_nii]);

  // Reset location when active case changes
  useEffect(() => {
    setCrosshair({
      mm: [0, 0, 0],
      vox: [0, 0, 0],
      anatVal: 0,
      predVal: 0,
      intensities: {},
      regionName: 'Click slice or 3D mesh to inspect',
      hemisphere: null,
      lobe: null,
      isPinned: false
    });
    setActiveUnderlay('t1');
    nvInstanceRef.current = null;
  }, [activeCaseId]);

  const caseDataRef       = useRef(caseData);
  const activeUnderlayRef = useRef(activeUnderlay);
  caseDataRef.current     = caseData;
  activeUnderlayRef.current = activeUnderlay;

  // Query voxel intensities & labels across all loaded NiiVue volumes
  const queryVoxel = useCallback((vox, mm) => {
    const nv = nvInstanceRef.current;
    const curUnderlay = activeUnderlayRef.current;
    const curCase = caseDataRef.current;
    const intensities = {};
    let predVal = 0;

    if (nv && nv.volumes && nv.volumes.length > 0) {
      const baseVol = nv.volumes[0];
      if (baseVol) {
        intensities[curUnderlay] = baseVol.getValue(vox[0], vox[1], vox[2]);
      }
      const predVol = nv.volumes.find(v => (v.name || '').toLowerCase().includes('pred'));
      if (predVol) {
        predVal = Math.round(predVol.getValue(vox[0], vox[1], vox[2]) || 0);
      }
    }

    // Populate other modalities via cache
    if (curCase?.files) {
      ['t1', 't1gd', 't2', 'flair'].forEach((mod) => {
        if (mod === curUnderlay) return;
        const url = curCase.files[mod];
        if (url) {
          const cached = getCachedVoxelIntensitySync(url, vox);
          if (cached !== null) {
            intensities[mod] = cached;
          } else {
            getVoxelIntensity(url, vox);
          }
        }
      });
    }

    // Anatomy label query via memory-based typed array
    let anatVal = 0;
    if (anatDataRef.current) {
      anatVal = queryAnatomyValue(
        anatDataRef.current.data,
        anatDataRef.current.dims,
        vox
      );
    }

    return { intensities, predVal, anatVal };
  }, []);

  const handle3DSelectLocation = useCallback((loc) => {
    setCrosshair(loc);
    if (nvInstanceRef.current && loc.mm) {
      try {
        const frac = nvInstanceRef.current.mm2frac(loc.mm, 0, true);
        if (frac && frac.length >= 3 && !isNaN(frac[0])) {
          nvInstanceRef.current.scene.crosshairPos = frac;
          nvInstanceRef.current.drawScene();
        }
      } catch (_) {}
    }
  }, []);

  // Synchronize browser history and hash for back/forward buttons while preserving active case
  const navigateTo = (view, replace = false, caseIdToPreserve = null) => {
    setUploadError(null);
    const targetCaseId = caseIdToPreserve || activeCaseId || new URLSearchParams(window.location.search).get('case');
    const search = targetCaseId ? `?case=${encodeURIComponent(targetCaseId)}` : '';
    const targetHash = view === 'upload' ? '' : `#${view}`;
    const url = `${window.location.pathname}${search}${targetHash}`;
    if (replace) {
      window.history.replaceState({ view }, '', url);
    } else {
      window.history.pushState({ view }, '', url);
    }
    setCurrentView(view);
  };

  useEffect(() => {
    const handlePopState = () => {
      const hash = window.location.hash.replace('#', '');
      const validViews = ['upload', 'processing', 'viewer', 'localization', 'eval'];
      setCurrentView(validViews.includes(hash) ? hash : 'upload');
    };

    window.addEventListener('popstate', handlePopState);
    window.addEventListener('hashchange', handlePopState);

    return () => {
      window.removeEventListener('popstate', handlePopState);
      window.removeEventListener('hashchange', handlePopState);
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, []);

  const loadCaseById = async (caseId) => {
    try {
      const resp = await fetch(`/api/cases/${caseId}`);
      if (resp.status === 200) {
        const data = await resp.json();
        setActiveCaseId(caseId);
        setCaseData(data);
        try {
          localStorage.setItem('neuroscope_last_case_id', caseId);
        } catch (_) {}
        if (data.status === 'done') {
          navigateTo('viewer', false, caseId);
        } else {
          navigateTo('processing', false, caseId);
          startPolling(caseId);
        }
      }
    } catch (err) {
      console.error('Failed to load case:', err);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    let targetCase = params.get('case');
    if (!targetCase) {
      try {
        targetCase = localStorage.getItem('neuroscope_last_case_id');
      } catch (_) {}
    }

    if (targetCase) {
      loadCaseById(targetCase);
    } else if (window.location.hash.includes('viewer')) {
      // Auto-load most recent completed case if navigating directly to #viewer
      fetch('/api/cases')
        .then(r => r.json())
        .then(cases => {
          const latestDone = Array.isArray(cases) ? cases.find(c => c.status === 'done') : null;
          if (latestDone) {
            loadCaseById(latestDone.id);
          }
        })
        .catch(err => console.warn('Could not auto-load recent case:', err));
    }
  }, []);

  const startPolling = (caseId) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    pollIntervalRef.current = setInterval(async () => {
      try {
        const resp = await fetch(`/api/cases/${caseId}`);
        const data = await resp.json();
        if (resp.status === 200) {
          setCaseData(data);
          if (data.status === 'done') {
            clearInterval(pollIntervalRef.current);
            navigateTo('viewer', false, caseId);
          }
        } else if (resp.status === 422 || data.status === 'failed') {
          clearInterval(pollIntervalRef.current);
          setCaseData(null);
          setUploadError(data.error || { code: 'PROCESSING_FAILED', message: 'Case analysis failed.' });
          navigateTo('upload');
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 1000);
  };

  const handleUploadSubmit = async (files) => {
    setIsSubmitting(true);
    setUploadError(null);
    setCaseData(null);
    const formData = new FormData();
    formData.append('t1', files.t1);
    formData.append('t1gd', files.t1gd);
    formData.append('t2', files.t2);
    formData.append('flair', files.flair);
    if (files.expert) formData.append('expert', files.expert);
    try {
      const resp = await fetch('/api/cases', { method: 'POST', body: formData });
      const data = await resp.json();
      if (resp.status === 202) {
        setActiveCaseId(data.case_id);
        navigateTo('processing');
        startPolling(data.case_id);
      } else {
        setUploadError(data.detail || { code: 'UPLOAD_FAILED', message: 'Failed to upload scans.' });
        navigateTo('upload');
      }
    } catch (err) {
      setUploadError({ code: 'NETWORK_ERROR', message: `Could not connect: ${err.message}` });
      navigateTo('upload');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleLoadDemo = async () => {
    setIsDemoLoading(true);
    setUploadError(null);
    setCaseData(null);
    try {
      const resp = await fetch('/api/cases/demo', { method: 'POST' });
      const data = await resp.json();
      if (resp.status === 202) {
        setActiveCaseId(data.case_id);
        navigateTo('processing');
        startPolling(data.case_id);
      } else {
        setUploadError({ code: 'DEMO_ERROR', message: data.detail || 'Could not launch demo scan.' });
      }
    } catch (err) {
      setUploadError({ code: 'DEMO_NETWORK_ERROR', message: err.message });
    } finally {
      setIsDemoLoading(false);
    }
  };

  const isViewerActive = currentView === 'viewer';

  return (
    /*
     * ROOT: full viewport, no overflow, dark background so nothing white flashes.
     * We use a dark fallback bg so even before React hydrates, no white shows.
     */
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      width: '100vw',
      overflow: 'hidden',
      background: isViewerActive ? '#0f172a' : 'var(--bg-main)',
    }}>
      <Navbar
        currentView={currentView}
        setView={(v) => navigateTo(v)}
        activeCase={caseData}
        onLoadDemo={handleLoadDemo}
        isDemoLoading={isDemoLoading}
        onSelectCase={loadCaseById}
      />

      {/*
       * MAIN: flex: 1 + minHeight: 0 is critical for nested flex children
       * to take available height without overflowing.
       * overflow: hidden prevents white body background from showing through.
       * background matches the active state so no flash on view switch.
       */}
      <main style={{
        flex: 1,
        minHeight: 0,         // ← allows flex child to shrink below content size
        overflow: 'hidden',   // ← prevents scroll & white background bleed
        display: 'flex',
        flexDirection: 'column',
        background: isViewerActive ? '#0f172a' : 'var(--bg-main)',
      }}>

        {/* ── Upload ───────────────────────────────────────────────────── */}
        {currentView === 'upload' && (
          <div style={{ flex: 1, overflow: 'auto' }}>
            <UploadView
              onUploadSubmit={handleUploadSubmit}
              isSubmitting={isSubmitting}
              uploadError={uploadError}
              clearError={() => setUploadError(null)}
              onLoadDemo={handleLoadDemo}
              isDemoLoading={isDemoLoading}
            />
          </div>
        )}

        {/* ── Processing ───────────────────────────────────────────────── */}
        {currentView === 'processing' && (
          <div style={{ flex: 1, overflow: 'auto', background: 'var(--bg-main)' }}>
            <ProcessingView caseData={caseData} />
          </div>
        )}

        {/* ── Eval ─────────────────────────────────────────────────────── */}
        {currentView === 'eval' && (
          <div style={{ flex: 1, overflow: 'auto' }}>
            <EvalView />
          </div>
        )}

        {/* ── Anatomical Localization ──────────────────────────────────── */}
        {currentView === 'localization' && caseData && (
          <div style={{ flex: 1, overflow: 'auto', background: 'var(--bg-main)' }}>
            <LocalizationView
              caseData={caseData}
              onSelectRegionCentroid={(mm, name) => {
                handle3DSelectLocation({
                  mm,
                  vox: [0, 0, 0],
                  regionName: name,
                  isPinned: true
                });
                navigateTo('viewer');
              }}
            />
          </div>
        )}

        {/* ── Viewer Empty State (No Case Selected) ────────────────────── */}
        {currentView === 'viewer' && !caseData && (
          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            textAlign: 'center',
            background: '#0b1120',
          }}>
            <div style={{
              maxWidth: '460px',
              padding: '2.5rem',
              background: '#0f172a',
              borderRadius: '12px',
              boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
              border: '1px solid rgba(255,255,255,0.08)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '1.25rem',
            }}>
              <div style={{
                width: '56px',
                height: '56px',
                borderRadius: '50%',
                background: 'rgba(6, 182, 212, 0.15)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#38bdf8',
                border: '1px solid rgba(6, 182, 212, 0.3)',
              }}>
                <Layers size={28} />
              </div>

              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.4rem' }}>
                  No Active MRI Case Selected
                </h3>
                <p style={{ fontSize: '0.82rem', color: '#94a3b8', lineHeight: 1.55 }}>
                  The 2D Multiplanar Reconstruction (MPR) and 3D Workstation require an MRI scan to render. Load a pre-analyzed demo scan or upload your own NIfTI files (.nii or .nii.gz).
                </p>
              </div>

              <div style={{ display: 'flex', gap: '0.75rem', width: '100%' }}>
                <button
                  onClick={handleLoadDemo}
                  disabled={isDemoLoading}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.4rem',
                    padding: '0.65rem 1rem',
                    borderRadius: '6px',
                    border: 'none',
                    background: '#0284c7',
                    color: '#ffffff',
                    fontWeight: 600,
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                    boxShadow: '0 2px 8px rgba(2,132,199,0.3)',
                  }}
                >
                  <Sparkles size={15} />
                  {isDemoLoading ? 'Loading Demo…' : 'Load Demo Scan'}
                </button>

                <button
                  onClick={() => navigateTo('upload')}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.4rem',
                    padding: '0.65rem 1rem',
                    borderRadius: '6px',
                    border: '1px solid rgba(255,255,255,0.12)',
                    background: 'rgba(255,255,255,0.04)',
                    color: '#e2e8f0',
                    fontWeight: 500,
                    fontSize: '0.82rem',
                    cursor: 'pointer',
                  }}
                >
                  <UploadCloud size={15} />
                  Upload Scans
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Viewer ───────────────────────────────────────────────────── */}
        {/*
         * Viewer is always rendered (not conditionally mounted/unmounted)
         * once caseData is available, to prevent NiiVue/Three.js re-init.
         * visibility:hidden hides it without destroying the GL context.
         * This eliminates the flash caused by mounting → layout → NiiVue init.
         */}
        {caseData && (
          <div style={{
            display: 'flex',
            flex: 1,
            minHeight: 0,
            overflow: 'hidden',
            // Use visibility instead of conditional render to avoid teardown
            visibility: currentView === 'viewer' ? 'visible' : 'hidden',
            position: currentView === 'viewer' ? 'relative' : 'absolute',
            inset: currentView === 'viewer' ? 'auto' : 0,
            pointerEvents: currentView === 'viewer' ? 'auto' : 'none',
            background: '#0f172a', // dark so no white canvas shows ever
          }}>
            {/* Left: 2D NiiVue */}
            {/* Right: 3D Three.js */}
            <div style={{
              flex: 1,
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gridTemplateRows: '1fr',    // ← explicit row height
              minHeight: 0,
              overflow: 'hidden',
            }}>
              <div style={{
                borderRight: '1px solid rgba(255,255,255,0.06)',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                background: '#0f172a',   // dark bg behind canvas
              }}>
                <Viewer2D
                  files={caseData.files}
                  t1Url={caseData.files?.t1}
                  predUrl={caseData.files?.pred_nii}
                  anatomyLookup={caseData.anatomy}
                  crosshair={crosshair}
                  onCrosshairChange={setCrosshair}
                  activeUnderlay={activeUnderlay}
                  onUnderlayChange={setActiveUnderlay}
                  onNVReady={(nv) => { nvInstanceRef.current = nv; }}
                />
              </div>

              <div style={{
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                background: '#0d1424',   // dark bg behind canvas
              }}>
                <Viewer3D
                  meshes={caseData.meshes}
                  crosshairMM={crosshair.mm}
                  spatialMeta={caseData.spatial_meta}
                  anatomyLookup={caseData.anatomy}
                  queryVoxel={queryVoxel}
                  onSelectLocation={handle3DSelectLocation}
                />
              </div>
            </div>

            {/* Right panel: Metrics */}
            <MetricsPanel
              caseData={caseData}
              crosshair={crosshair}
              activeUnderlay={activeUnderlay}
              onUnderlayChange={setActiveUnderlay}
              onSelectLocation={handle3DSelectLocation}
            />
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
