import React, { useState } from 'react';
import {
  Download,
  Compass,
  Crosshair,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  Printer,
  Brain,
  Activity,
  Layers,
  ChevronDown,
  ChevronRight,
  Info
} from 'lucide-react';
import { getTumourStatusInfo } from './coordUtils';

export default function MetricsPanel({
  caseData,
  crosshair,
  activeUnderlay = 't1',
  onUnderlayChange,
  onSelectLocation
}) {
  const [panelTab, setPanelTab] = useState('inspection');
  const [showInvolvement, setShowInvolvement] = useState(true);

  const localization = caseData?.localization || {};
  const answerCards = localization.answer_cards || {};
  const locTable = localization.table || [];
  const repSentences = localization.report_sentences || {};
  const card1 = answerCards.card_one_mass_or_several || {};
  const card2 = answerCards.card_which_side || {};
  const card3 = answerCards.card_how_big || {};
  const primary = localization.primary_regions || {};

  const volumes = caseData?.volumes || {};
  const laterality = caseData?.laterality || {};
  const agreement = caseData?.agreement;
  const warnings = caseData?.warnings || [];
  const anatomyMeta = caseData?.anatomy || {};
  const spatial = caseData?.spatial_meta || {};
  const predFileUrl = caseData?.files?.pred_nii;

  // Selected / active location data
  const mm = crosshair?.mm;
  const vox = crosshair?.vox;
  const isPinned = Boolean(crosshair?.isPinned);
  const anatVal = crosshair?.anatVal ?? 0;
  const predVal = crosshair?.predVal ?? 0;
  const intensities = crosshair?.intensities || {};
  const regionName = crosshair?.regionName;
  const hemisphere = crosshair?.hemisphere;
  const lobe = crosshair?.lobe;

  const isUnavailable = anatomyMeta?.status === 'unavailable' || crosshair?.labelsUnavailable;
  const unavailableReason = crosshair?.unavailableReason || anatomyMeta?.message || 'Atlas labels not aligned.';

  const tumorInfo = getTumourStatusInfo(predVal);
  const regionInvolvement = anatomyMeta?.region_involvement || [];

  // Voxel spacing formatting
  const zoomsStr = spatial?.zooms
    ? spatial.zooms.map(z => Number(z).toFixed(2)).join(' × ') + ' mm'
    : '1.00 × 1.00 × 1.00 mm';

  return (
    <div style={{
      width: '340px',
      background: '#ffffff',
      borderLeft: '1px solid var(--border-light)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflowY: 'auto'
    }}>
      {/* Panel Header */}
      <div style={{
        padding: '0.75rem 1rem',
        borderBottom: '1px solid var(--border-light)',
        background: 'var(--bg-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div>
          <h3 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            NeuroScope Telemetry
          </h3>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            Anatomical parcellation & tumour metrics
          </p>
        </div>
        <span
          className={`badge ${isPinned ? 'badge-blue' : 'badge-gray'}`}
          style={{ fontSize: '0.65rem', textTransform: 'uppercase' }}
        >
          {isPinned ? '📍 Pinned' : 'Live Cursor'}
        </span>
      </div>

      {/* ── Sub-tab Switcher: Inspection vs. Localization ──────────────── */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-light)', background: '#ffffff', flexShrink: 0 }}>
        <button
          type="button"
          onClick={() => setPanelTab('inspection')}
          style={{
            flex: 1,
            padding: '0.5rem',
            border: 'none',
            borderBottom: panelTab === 'inspection' ? '2px solid var(--primary-blue)' : '2px solid transparent',
            background: 'transparent',
            fontSize: '0.74rem',
            fontWeight: panelTab === 'inspection' ? 700 : 500,
            color: panelTab === 'inspection' ? 'var(--primary-blue)' : 'var(--text-secondary)',
            cursor: 'pointer'
          }}
        >
          🎯 Live Telemetry
        </button>
        <button
          type="button"
          onClick={() => setPanelTab('localization')}
          style={{
            flex: 1,
            padding: '0.5rem',
            border: 'none',
            borderBottom: panelTab === 'localization' ? '2px solid var(--primary-blue)' : '2px solid transparent',
            background: 'transparent',
            fontSize: '0.74rem',
            fontWeight: panelTab === 'localization' ? 700 : 500,
            color: panelTab === 'localization' ? 'var(--primary-blue)' : 'var(--text-secondary)',
            cursor: 'pointer'
          }}
        >
          🗺️ Answer Cards
        </button>
      </div>

      <div style={{ padding: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>

        {panelTab === 'inspection' ? (
        <>
        {/* ── 1. BRAIN REGION (MOST PROMINENT) ─────────────────────────── */}
        <div className="card" style={{
          padding: '0.85rem',
          borderLeft: '3px solid #0284c7',
          background: '#f8fafc'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Brain size={16} color="#0284c7" />
              <h4 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                Brain Region Identity
              </h4>
            </div>
            {anatVal > 0 && !isUnavailable && (
              <span className="badge" style={{ background: '#e0f2fe', color: '#0369a1', fontFamily: 'var(--font-mono)' }}>
                ID #{anatVal}
              </span>
            )}
          </div>

          {/* Region Name */}
          <div style={{ marginTop: '0.25rem' }}>
            {isUnavailable ? (
              <div style={{ padding: '0.4rem 0.5rem', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '4px' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 700, color: '#991b1b' }}>
                  Anatomical labels unavailable
                </div>
                <div style={{ fontSize: '0.68rem', color: '#b91c1c', marginTop: '0.15rem', lineHeight: 1.3 }}>
                  {unavailableReason}
                </div>
              </div>
            ) : (anatVal > 0 || (regionName && regionName !== 'Click slice or 3D mesh to inspect' && !regionName.includes('No anatomical label'))) ? (
              <div>
                <div style={{ fontSize: '0.95rem', fontWeight: 800, color: '#0f172a', lineHeight: 1.25 }}>
                  {regionName}
                </div>
                <div style={{ display: 'flex', gap: '0.35rem', marginTop: '0.4rem', flexWrap: 'wrap' }}>
                  {hemisphere && (
                    <span className="badge" style={{
                      background: hemisphere === 'Left' ? '#e0f2fe' : '#f3e8ff',
                      color: hemisphere === 'Left' ? '#0369a1' : '#7e22ce',
                      fontWeight: 700
                    }}>
                      {hemisphere} Hemisphere
                    </span>
                  )}
                  {lobe && (
                    <span className="badge" style={{ background: '#f1f5f9', color: '#475569' }}>
                      {lobe}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div style={{ color: '#64748b', fontSize: '0.8rem', fontStyle: 'italic', padding: '0.2rem 0' }}>
                {regionName && regionName.includes('Click slice') ? regionName : 'No anatomical label at this location (background / outside atlas mask)'}
              </div>
            )}
          </div>
        </div>

        {/* ── 2. TUMOUR STATUS (PREDICTED) ─────────────────────────────── */}
        <div className="card" style={{
          padding: '0.85rem',
          borderLeft: tumorInfo.status === 'inside_tumor' ? '3px solid #ef4444' : '3px solid #94a3b8'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Activity size={15} color={tumorInfo.status === 'inside_tumor' ? '#ef4444' : '#64748b'} />
              <h4 style={{ fontSize: '0.8rem', fontWeight: 700 }}>
                Tumour Status
              </h4>
            </div>
            <span style={{ fontSize: '0.62rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
              MODEL PREDICTION
            </span>
          </div>

          <div style={{ marginTop: '0.2rem' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.45rem',
              fontSize: '0.82rem',
              fontWeight: 700,
              color: tumorInfo.status === 'inside_tumor' ? '#b91c1c' : '#334155'
            }}>
              <span style={{
                width: 9,
                height: 9,
                borderRadius: '50%',
                background: tumorInfo.status === 'inside_tumor' ? tumorInfo.color : '#94a3b8',
                flexShrink: 0
              }} />
              <span>{tumorInfo.description}</span>
            </div>

            {tumorInfo.status === 'inside_tumor' && tumorInfo.memberships.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '0.4rem' }}>
                <span style={{ fontSize: '0.68rem', color: '#64748b' }}>Member of:</span>
                {tumorInfo.memberships.map((m) => (
                  <span key={m} className="badge badge-amber" style={{ fontSize: '0.65rem' }}>
                    {m}
                  </span>
                ))}
                <span style={{ fontSize: '0.65rem', color: '#94a3b8', fontStyle: 'italic' }}>
                  (predicted)
                </span>
              </div>
            )}

            {tumorInfo.status === 'outside_tumor' && (
              <div style={{ fontSize: '0.7rem', color: '#64748b', marginTop: '0.2rem' }}>
                Voxel is outside the predicted tumour segmentation mask.
              </div>
            )}
          </div>
        </div>

        {/* ── 3. SPATIAL LOCATION & RESOLUTION ─────────────────────────── */}
        <div className="card" style={{ padding: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Crosshair size={14} color="var(--primary-blue)" />
              <h4 style={{ fontSize: '0.8rem', fontWeight: 600 }}>Spatial Coordinates</h4>
            </div>
            <span style={{ fontSize: '0.62rem', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>
              CALCULATED MEASUREMENT
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.4rem', marginTop: '0.4rem' }}>
            <div style={{ background: 'var(--bg-subtle)', padding: '0.4rem 0.55rem', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>World (RAS+ mm)</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', fontWeight: 700 }}>
                {mm ? `[${mm[0]}, ${mm[1]}, ${mm[2]}]` : 'Click viewer'}
              </div>
            </div>

            <div style={{ background: 'var(--bg-subtle)', padding: '0.4rem 0.55rem', borderRadius: '4px' }}>
              <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Voxel Index (i, j, k)</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', fontWeight: 700 }}>
                {vox ? `[${vox[0]}, ${vox[1]}, ${vox[2]}]` : 'N/A'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.68rem', color: '#64748b', marginTop: '0.4rem', padding: '0 2px' }}>
            <span>Voxel Spacing:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{zoomsStr}</span>
          </div>
        </div>

        {/* ── 4. MULTI-SEQUENCE IMAGE INTENSITIES ──────────────────────── */}
        <div className="card" style={{ padding: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <Layers size={14} color="var(--primary-blue)" />
              <h4 style={{ fontSize: '0.8rem', fontWeight: 600 }}>Multi-Modal Intensity</h4>
            </div>
            <span style={{ fontSize: '0.65rem', color: '#0284c7', fontWeight: 600 }}>
              Underlay: {activeUnderlay.toUpperCase()}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.3rem', marginTop: '0.4rem' }}>
            {[
              { key: 't1', label: 'T1' },
              { key: 't1gd', label: 'T1-Gd' },
              { key: 't2', label: 'T2' },
              { key: 'flair', label: 'FLAIR' }
            ].map(({ key, label }) => {
              const val = intensities[key];
              const isCurrent = activeUnderlay === key;
              return (
                <div
                  key={key}
                  onClick={() => onUnderlayChange && onUnderlayChange(key)}
                  style={{
                    background: isCurrent ? '#e0f2fe' : 'var(--bg-subtle)',
                    border: isCurrent ? '1px solid #38bdf8' : '1px solid transparent',
                    borderRadius: '4px',
                    padding: '0.35rem 0.2rem',
                    textAlign: 'center',
                    cursor: 'pointer',
                    transition: 'all 0.15s'
                  }}
                  title={`Click to set ${label} as active underlay`}
                >
                  <div style={{ fontSize: '0.64rem', fontWeight: 600, color: isCurrent ? '#0369a1' : 'var(--text-muted)' }}>
                    {label}
                  </div>
                  <div style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '0.74rem',
                    fontWeight: 700,
                    color: isCurrent ? '#0284c7' : 'var(--text-primary)',
                    marginTop: '0.1rem'
                  }}>
                    {val !== undefined && val !== null ? Math.round(val) : '—'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── 5. RELIABILITY & METHODOLOGY NOTE ────────────────────────── */}
        <div style={{
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: '6px',
          padding: '0.65rem 0.75rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.25rem' }}>
            <span className="badge" style={{ background: '#dbeafe', color: '#1e40af', fontSize: '0.62rem', fontWeight: 700 }}>
              ATLAS-DERIVED ANATOMY — approximate
            </span>
          </div>
          <div style={{ fontSize: '0.68rem', color: '#475569', lineHeight: 1.35 }}>
            Anatomical labels are approximate. Mass effect, edema, and tumour infiltration displace normal tissue, reducing anatomical atlas precision near the lesion.
          </div>
          <div style={{ fontSize: '0.64rem', color: '#64748b', marginTop: '0.3rem', fontFamily: 'var(--font-mono)' }}>
            Method: {anatomyMeta?.provenance?.method || 'SRI24 Template Resampling (Nearest-Neighbor)'}
          </div>
        </div>

        {/* ── 6. PER-REGION TUMOUR INVOLVEMENT (SECTION 7) ─────────────── */}
        {regionInvolvement.length > 0 && (
          <div className="card" style={{ padding: '0.85rem' }}>
            <div
              onClick={() => setShowInvolvement(!showInvolvement)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
                userSelect: 'none'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <FileSpreadsheet size={14} color="var(--primary-blue)" />
                <h4 style={{ fontSize: '0.8rem', fontWeight: 600 }}>
                  Regional Involvement ({regionInvolvement.length})
                </h4>
              </div>
              {showInvolvement ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </div>

            {showInvolvement && (
              <div style={{ marginTop: '0.5rem', maxHeight: '180px', overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.68rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-light)', color: '#64748b', textAlign: 'left' }}>
                      <th style={{ padding: '3px 2px' }}>Region</th>
                      <th style={{ padding: '3px 2px', textAlign: 'right' }}>WT (mL)</th>
                      <th style={{ padding: '3px 2px', textAlign: 'right' }}>% Reg</th>
                    </tr>
                  </thead>
                  <tbody>
                    {regionInvolvement.slice(0, 10).map((r) => (
                      <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '3px 2px', maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <span style={{ fontWeight: 600 }}>{r.name}</span>
                          {r.hemisphere && (
                            <span style={{ fontSize: '0.62rem', color: '#64748b', marginLeft: '3px' }}>
                              ({r.hemisphere[0]})
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '3px 2px', textAlign: 'right', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                          {r.tumor_volume_ml}
                        </td>
                        <td style={{ padding: '3px 2px', textAlign: 'right', fontFamily: 'var(--font-mono)', color: '#0284c7' }}>
                          {r.pct_of_region_involved}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div style={{ fontSize: '0.62rem', color: '#94a3b8', marginTop: '0.3rem', fontStyle: 'italic' }}>
                  Predicted atlas-derived involvement estimate.
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── 7. ANATOMICAL LATERALITY ─────────────────────────────────── */}
        <div className="card" style={{ padding: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.4rem' }}>
            <Compass size={14} color="var(--primary-blue)" />
            <h4 style={{ fontSize: '0.8rem', fontWeight: 600 }}>Estimated Laterality</h4>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.25rem' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>
              {laterality.side ? `${laterality.side} Hemisphere` : 'Evaluating...'}
            </span>
            {laterality.delta_x_mm !== undefined && (
              <span className="badge badge-blue" style={{ fontFamily: 'var(--font-mono)' }}>
                Δx: {laterality.delta_x_mm > 0 ? `+${laterality.delta_x_mm}` : laterality.delta_x_mm} mm
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Computed relative to patient brain centroid in RAS+ space.
          </div>
        </div>

        {/* ── 8. BRAIN TUMOUR VOLUMETRICS ──────────────────────────────── */}
        <div className="card" style={{ padding: '0.85rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
            <FileSpreadsheet size={14} color="var(--primary-blue)" />
            <h4 style={{ fontSize: '0.8rem', fontWeight: 600 }}>Tumour Volumetrics</h4>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
            {/* WT */}
            <div style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: '0.35rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.78rem', fontWeight: 600 }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-wt)' }} />
                  Whole Tumour (WT)
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', fontWeight: 700 }}>
                  {volumes.WT?.ml !== undefined ? `${volumes.WT.ml} mL` : '—'}
                </span>
              </div>
              <div style={{ fontSize: '0.67rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>
                {volumes.WT?.formula || 'Total lesion volume including edema'}
              </div>
            </div>

            {/* TC */}
            <div style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: '0.35rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.78rem', fontWeight: 600 }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-tc)' }} />
                  Tumour Core (TC)
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', fontWeight: 700 }}>
                  {volumes.TC?.ml !== undefined ? `${volumes.TC.ml} mL` : '—'}
                </span>
              </div>
              <div style={{ fontSize: '0.67rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>
                {volumes.TC?.formula || 'Necrotic core + active rim'}
              </div>
            </div>

            {/* ET */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.78rem', fontWeight: 600 }}>
                  <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-et)' }} />
                  Enhancing Tumour (ET)
                </span>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem', fontWeight: 700 }}>
                  {volumes.ET?.ml !== undefined ? `${volumes.ET.ml} mL` : '—'}
                </span>
              </div>
              <div style={{ fontSize: '0.67rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>
                {volumes.ET?.formula || 'Active enhancing rim tissue'}
              </div>
            </div>
          </div>
        </div>

        {/* ── 9. EXPERT AGREEMENT METRICS ──────────────────────────────── */}
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

        {/* ── 10. SCAN SANITY NOTICE ──────────────────────────────────── */}
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
        </>
        ) : (
        <>
          {/* ── ANSWER CARDS (COMPACT FOR SIDEBAR) ── */}
          <div className="card" style={{ padding: '0.75rem', borderLeft: '3px solid #0284c7' }}>
            <div style={{ fontSize: '0.68rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>
              Question 1
            </div>
            <h4 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.15rem' }}>
              One mass or several?
            </h4>
            <div style={{ fontSize: '0.76rem', fontWeight: 600, color: '#0284c7', marginTop: '0.3rem' }}>
              {card1.summary || 'Evaluating connected components...'}
            </div>
            {card1.components && card1.components.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginTop: '0.4rem' }}>
                {card1.components.map((c, i) => (
                  <div
                    key={c.id || i}
                    onClick={() => onSelectLocation && onSelectLocation({ mm: c.centroid_ras_mm, vox: [0, 0, 0], regionName: `Mass #${i + 1}`, isPinned: true })}
                    style={{
                      display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem',
                      background: 'var(--bg-subtle)', padding: '0.2rem 0.4rem', borderRadius: '4px', cursor: 'pointer'
                    }}
                    title="Click to jump to mass centroid"
                  >
                    <span>Mass #{i + 1}: <strong>{c.volume_ml.toFixed(2)} mL</strong></span>
                    <span className="mono" style={{ color: 'var(--text-muted)' }}>📍 Locate</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card" style={{ padding: '0.75rem', borderLeft: '3px solid #10b981' }}>
            <div style={{ fontSize: '0.68rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>
              Question 2
            </div>
            <h4 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.15rem' }}>
              Which side?
            </h4>
            <div style={{ fontSize: '0.76rem', fontWeight: 600, color: '#059669', marginTop: '0.3rem' }}>
              {card2.summary || 'Evaluating side...'}
            </div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
              Side: <strong>{card2.hemisphere || 'Midline'}</strong> (Orientation: <span className="mono">{card2.affine_orientation || 'RAS'}</span>)
            </div>
          </div>

          <div className="card" style={{ padding: '0.75rem', borderLeft: '3px solid #f59e0b' }}>
            <div style={{ fontSize: '0.68rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>
              Question 3
            </div>
            <h4 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.15rem' }}>
              How big?
            </h4>
            <div style={{ fontSize: '0.74rem', color: '#b45309', marginTop: '0.3rem', lineHeight: 1.4 }}>
              {card3.summary || 'Calculating volumes...'}
            </div>
          </div>

          {/* ── REGIONAL INVOLVEMENT BREAKDOWN ── */}
          {locTable && locTable.length > 0 && (
            <div className="card" style={{ padding: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                <h4 style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Regional Involvement
                </h4>
                <span className="badge badge-gray" style={{ fontSize: '0.62rem' }}>
                  {locTable.length} regions
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', maxHeight: '180px', overflowY: 'auto' }}>
                {locTable.map((row, idx) => (
                  <div
                    key={idx}
                    onClick={() => onSelectLocation && onSelectLocation({ mm: row.centroid_ras_mm, vox: [0, 0, 0], regionName: row.region, isPinned: true })}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: '0.72rem',
                      background: 'var(--bg-subtle)',
                      padding: '0.25rem 0.45rem',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                    title="Click to jump to this structure's centroid"
                  >
                    <span style={{ fontWeight: 600, maxWidth: '170px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.region}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span className="mono" style={{ color: '#0284c7', fontWeight: 700 }}>
                        {row.wt_pct?.toFixed(1)}%
                      </span>
                      <span className="mono" style={{ color: 'var(--text-muted)' }}>
                        {row.wt_ml?.toFixed(2)}mL
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── REPORT SUMMARY PARAGRAPH ── */}
          {repSentences.wt_paragraph && (
            <div className="card" style={{ padding: '0.75rem', fontSize: '0.72rem', lineHeight: 1.5, background: '#f8fafc' }}>
              <div style={{ fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.2rem' }}>
                Automated Findings Summary
              </div>
              <p style={{ color: 'var(--text-secondary)' }}>{repSentences.wt_paragraph}</p>
            </div>
          )}

          <div style={{
            fontSize: '0.68rem',
            color: 'var(--text-muted)',
            lineHeight: 1.3,
            padding: '0.4rem',
            background: 'var(--bg-subtle)',
            borderRadius: '4px'
          }}>
            <em>Anatomical localization is an approximate research-use estimate derived from model-predicted voxels and atlas overlap. It is not a clinical diagnosis and may be inaccurate.</em>
          </div>
        </>
        )}

        {/* ── 11. ACTIONS ─────────────────────────────────────────────── */}
        <div style={{ marginTop: 'auto', paddingTop: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
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
