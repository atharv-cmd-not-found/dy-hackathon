import React from 'react';
import { Activity, Play, UploadCloud, BarChart2, CheckCircle2 } from 'lucide-react';

export default function Navbar({ currentView, setView, activeCase, onLoadDemo, isDemoLoading }) {
  return (
    <header style={{
      background: '#ffffff',
      borderBottom: '1px solid var(--border-light)',
      padding: '0.75rem 1.5rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      position: 'sticky',
      top: 0,
      zIndex: 50
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
                Case: {activeCase.case_id.substring(0, 8)}
              </span>
            )}
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Volumetric Brain MRI Segmentation & 3D Interactive Anatomy
          </p>
        </div>
      </div>

      {/* Navigation & Action Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <button
          onClick={onLoadDemo}
          disabled={isDemoLoading}
          className="btn btn-outline btn-sm"
          title="Load precomputed synthetic multi-sequence scan for immediate testing"
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
