import React from 'react';
import { Download, Compass, Crosshair, FileSpreadsheet, CheckCircle2, AlertTriangle, Printer } from 'lucide-react';

export default function MetricsPanel({ caseData, crosshair }) {
  const volumes = caseData?.volumes || {};
  const laterality = caseData?.laterality || {};
  const agreement = caseData?.agreement;
  const warnings = caseData?.warnings || [];

  const predFileUrl = caseData?.files?.pred_nii;

  return (
    <div style={{
      width: '320px',
      background: '#ffffff',
      borderLeft: '1px solid var(--border-light)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflowY: 'auto'
    }}>
      {/* Panel Header */}
      <div style={{
        padding: '0.85rem 1rem',
        borderBottom: '1px solid var(--border-light)',
        background: 'var(--bg-subtle)'
      }}>
        <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>
          Clinical Telemetry & Metrics
        </h3>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Spatial coordinates and volumetric breakdown
        </p>
      </div>

      <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {/* Live Synchronized Spatial Crosshair */}
        <div className="card" style={{ padding: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem' }}>
            <Crosshair size={14} color="var(--primary-blue)" />
            <h4 style={{ fontSize: '0.8rem', fontWeight: 600 }}>Active Spatial Cursor</h4>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginTop: '0.5rem' }}>
            <div style={{ background: 'var(--bg-subtle)', padding: '0.4rem 0.6rem', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>World (RAS+ mm)</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 600 }}>
                {crosshair?.mm ? `${crosshair.mm[0]}, ${crosshair.mm[1]}, ${crosshair.mm[2]}` : 'Click slice'}
              </div>
            </div>

            <div style={{ background: 'var(--bg-subtle)', padding: '0.4rem 0.6rem', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Voxel Index (i,j,k)</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', fontWeight: 600 }}>
                {crosshair?.vox ? `[${crosshair.vox[0]}, ${crosshair.vox[1]}, ${crosshair.vox[2]}]` : 'N/A'}
              </div>
            </div>
          </div>
        </div>

        {/* Anatomical Laterality */}
        <div className="card" style={{ padding: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem' }}>
            <Compass size={14} color="var(--primary-blue)" />
            <h4 style={{ fontSize: '0.8rem', fontWeight: 600 }}>Estimated Laterality</h4>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.25rem' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>
              {laterality.side ? `${laterality.side} Hemisphere` : 'Evaluating...'}
            </span>
            {laterality.delta_x_mm !== undefined && (
              <span className="badge badge-blue" style={{ fontFamily: 'var(--font-mono)' }}>
                Δx: {laterality.delta_x_mm > 0 ? `+${laterality.delta_x_mm}` : laterality.delta_x_mm} mm
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.25rem', lineHeight: 1.2 }}>
            Computed relative to patient brain centroid in RAS+ space.
          </div>
        </div>

        {/* Volumetric Breakdown */}
        <div className="card" style={{ padding: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
            <FileSpreadsheet size={14} color="var(--primary-blue)" />
            <h4 style={{ fontSize: '0.8rem', fontWeight: 600 }}>Tumour Volumetrics</h4>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {/* WT */}
            <div style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', fontWeight: 500 }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-wt)' }}></span>
                  Whole Tumour (WT)
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {volumes.WT?.ml !== undefined ? `${volumes.WT.ml} mL` : '—'}
                </span>
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                {volumes.WT?.formula || 'Total area including edema'}
              </div>
            </div>

            {/* TC */}
            <div style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: '0.4rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', fontWeight: 500 }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-tc)' }}></span>
                  Tumour Core (TC)
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {volumes.TC?.ml !== undefined ? `${volumes.TC.ml} mL` : '—'}
                </span>
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                {volumes.TC?.formula || 'Necrotic core + active rim'}
              </div>
            </div>

            {/* ET */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.8rem', fontWeight: 500 }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-et)' }}></span>
                  Enhancing Tumour (ET)
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {volumes.ET?.ml !== undefined ? `${volumes.ET.ml} mL` : '—'}
                </span>
              </div>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                {volumes.ET?.formula || 'Active enhancing tissue'}
              </div>
            </div>
          </div>
        </div>

        {/* Expert Agreement (if available) */}
        {agreement && (
          <div className="card" style={{ padding: '0.85rem', background: 'var(--success-light)', borderColor: '#a7f3d0' }}>
            <h4 style={{ fontSize: '0.8rem', fontWeight: 600, color: '#047857', marginBottom: '0.4rem' }}>
              Expert Agreement Metrics
            </h4>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: '0.75rem' }}>
              <div>WT Dice: <strong>{(agreement.WT?.dice * 100).toFixed(1)}%</strong></div>
              <div>WT Recall: <strong>{(agreement.WT?.sensitivity * 100).toFixed(1)}%</strong></div>
            </div>
          </div>
        )}

        {/* Warnings Banner (Non-refusing sanity) */}
        {warnings.length > 0 && (
          <div style={{
            background: 'var(--warning-light)',
            border: '1px solid #fde68a',
            borderRadius: '6px',
            padding: '0.65rem 0.75rem'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', color: '#b45309', fontWeight: 600, fontSize: '0.75rem' }}>
              <AlertTriangle size={14} /> Scan Sanity Notice
            </div>
            {warnings.map((w, i) => (
              <div key={i} style={{ fontSize: '0.7rem', color: '#92400e', marginTop: '0.2rem' }}>
                • {w.message}
              </div>
            ))}
          </div>
        )}

        {/* Action Buttons: NIfTI Download & Report */}
        <div style={{ marginTop: 'auto', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {caseData?.case_id && (
            <a
              href={`/api/cases/${caseData.case_id}/report`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-outline btn-sm"
              style={{ width: '100%', textDecoration: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}
            >
              <Printer size={14} />
              <span>Print Clinical Dossier (PDF)</span>
            </a>
          )}
          {predFileUrl && (
            <a
              href={predFileUrl}
              download="prediction.nii.gz"
              className="btn btn-primary btn-sm"
              style={{ width: '100%', textDecoration: 'none' }}
            >
              <Download size={14} />
              <span>Download Predicted Mask (.nii.gz)</span>
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
