import React, { useState, useEffect } from 'react';
import { Activity, Play, UploadCloud, BarChart2, Folder, Compass } from 'lucide-react';

export default function Navbar({ currentView, setView, activeCase, onLoadDemo, isDemoLoading, onSelectCase }) {
  const [cases, setCases] = useState([]);

  useEffect(() => {
    fetch('/api/cases')
      .then(res => res.json())
      .then(data => {
        if (Array.isArray(data)) {
          setCases(data);
        }
      })
      .catch(() => {});
  }, [activeCase]);

  const activeCaseId = activeCase?.case_id;

  return (
    <header style={{
      background: '#ffffff',
      borderBottom: '1px solid var(--border-light)',
      padding: '0.65rem 1.25rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      gap: '1rem',
      flexWrap: 'wrap'
    }}>
      {/* Brand & Workstation Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <div style={{
          background: 'var(--primary-blue-light)',
          color: 'var(--primary-blue)',
          width: '36px',
          height: '36px',
          borderRadius: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <Activity size={20} />
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h1 style={{ fontSize: '1.05rem', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              NeuroScope 3D
            </h1>
            <span className="badge badge-blue">Clinical Workstation</span>
            {activeCase && (
              <span className="badge badge-green" style={{ fontFamily: 'var(--font-mono)' }}>
                Case: {activeCaseId?.substring(0, 8)}
              </span>
            )}
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Volumetric Brain MRI Segmentation & 3D Interactive Anatomy
          </p>
        </div>
      </div>

      {/* Navigation & Action Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
        {/* Case Switcher Dropdown */}
        {cases.length > 0 && onSelectCase && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', background: 'var(--bg-subtle)', padding: '0.2rem 0.5rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}>
            <Folder size={14} color="var(--text-muted)" />
            <select
              value={activeCaseId || ''}
              onChange={(e) => {
                if (e.target.value) onSelectCase(e.target.value);
              }}
              style={{
                border: 'none',
                background: 'transparent',
                fontSize: '0.75rem',
                color: 'var(--text-primary)',
                fontWeight: 500,
                outline: 'none',
                cursor: 'pointer',
                maxWidth: '180px'
              }}
              title="Switch to another processed patient or demo scan"
            >
              <option value="" disabled>Select Case ({cases.length})...</option>
              {cases.map((c) => {
                const isDemo = c.id.startsWith('demo');
                const label = isDemo
                  ? `Demo (${c.id.substring(0, 11)})`
                  : `Patient ${c.id.substring(0, 8)}...`;
                return (
                  <option key={c.id} value={c.id}>
                    {label} [{c.status}]
                  </option>
                );
              })}
            </select>
          </div>
        )}

        {activeCase && (
          <>
            <button
              onClick={() => setView('viewer')}
              className={`btn btn-sm ${currentView === 'viewer' ? 'btn-primary' : 'btn-outline'}`}
              title="Interactive 2D multiplanar slices and 3D surface mesh viewer"
            >
              <Activity size={14} />
              <span>3D Workstation</span>
            </button>

            <button
              onClick={() => setView('localization')}
              className={`btn btn-sm ${currentView === 'localization' ? 'btn-primary' : 'btn-outline'}`}
              title="SRI24 anatomical localization breakdown and trainee Answer Cards"
            >
              <Compass size={14} />
              <span>Anatomical Localization</span>
            </button>
          </>
        )}

        <button
          onClick={onLoadDemo}
          disabled={isDemoLoading}
          className="btn btn-outline btn-sm"
          title="Load precomputed multi-sequence scan for immediate testing"
        >
          <Play size={14} color="#0284c7" />
          <span>{isDemoLoading ? 'Loading Sample...' : 'Try Demo Scan'}</span>
        </button>

        <button
          onClick={() => setView('upload')}
          className={`btn btn-sm ${currentView === 'upload' ? 'btn-primary' : 'btn-outline'}`}
        >
          <UploadCloud size={14} />
          <span>New Upload</span>
        </button>

        <button
          onClick={() => setView('eval')}
          className={`btn btn-sm ${currentView === 'eval' ? 'btn-primary' : 'btn-outline'}`}
        >
          <BarChart2 size={14} />
          <span>Model Benchmark</span>
        </button>
      </div>
    </header>
  );
}
