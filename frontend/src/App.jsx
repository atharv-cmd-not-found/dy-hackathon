import React, { useState, useEffect, useRef } from 'react';
import Navbar from './components/Navbar';
import UploadView from './components/UploadView';
import ProcessingView from './components/ProcessingView';
import Viewer2D from './components/Viewer2D';
import Viewer3D from './components/Viewer3D';
import MetricsPanel from './components/MetricsPanel';
import EvalView from './components/EvalView';
import Footer from './components/Footer';

export default function App() {
  const [currentView, setCurrentView] = useState(() => {
    const hash = window.location.hash.replace('#', '');
    return ['upload', 'processing', 'viewer', 'eval'].includes(hash) ? hash : 'upload';
  });
  const [activeCaseId, setActiveCaseId] = useState(null);
  const [caseData, setCaseData] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDemoLoading, setIsDemoLoading] = useState(false);

  const [crosshair, setCrosshair] = useState({ mm: [0, 0, 0], vox: [0, 0, 0] });
  const pollIntervalRef = useRef(null);

  // Synchronize browser history and hash for back/forward buttons
  const navigateTo = (view, replace = false) => {
    setUploadError(null);
    const targetHash = view === 'upload' ? '' : `#${view}`;
    const url = targetHash || window.location.pathname + window.location.search;
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
      const validViews = ['upload', 'processing', 'viewer', 'eval'];
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
            navigateTo('viewer');
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

  const isViewerActive = currentView === 'viewer' && caseData;

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
                  t1Url={caseData.files?.t1}
                  predUrl={caseData.files?.pred_nii}
                  crosshair={crosshair}
                  onCrosshairChange={setCrosshair}
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
                />
              </div>
            </div>

            {/* Right panel: Metrics */}
            <MetricsPanel caseData={caseData} crosshair={crosshair} />
          </div>
        )}
      </main>

      <Footer />
    </div>
  );
}
