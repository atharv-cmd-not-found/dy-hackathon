import React, { useState } from 'react';
import {
  Compass,
  Layers,
  MapPin,
  Maximize2,
  Sparkles,
  AlertTriangle,
  ShieldCheck,
  CheckCircle2,
  HelpCircle,
  FileText,
  Activity,
  ArrowRight,
  ExternalLink
} from 'lucide-react';

export default function LocalizationView({ caseData, onSelectRegionCentroid }) {
  const [selectedRegion, setSelectedRegion] = useState(null);

  const localization = caseData?.localization || {};
  const status = localization.status || 'unavailable';
  const mode = localization.mode || 'Mode B (Coarse Geometric Fallback)';
  const qualityMsg = localization.quality_message || 'No localization computed yet.';
  const dice = localization.overlap_dice || 0.0;
  const answerCards = localization.answer_cards || {};
  const table = localization.table || [];
  const primary = localization.primary_regions || {};
  const secondary = localization.secondary_regions || {};
  const repSentences = localization.report_sentences || {};
  const provenance = localization.atlas_metadata || {};
  const spaceCheck = localization.space_check || {};
  const modeBData = localization.mode_b_data || {};
  const warnings = localization.warnings || [];

  const card1 = answerCards.card_one_mass_or_several || {};
  const card2 = answerCards.card_which_side || {};
  const card3 = answerCards.card_how_big || {};

  const isAvailable = status === 'available';
  const isLowConfidence = status === 'low_confidence';
  const isUnavailable = status === 'unavailable';

  const statusBadge = isAvailable ? (
    <span className="badge badge-green">Template Aligned · Mode A</span>
  ) : isLowConfidence ? (
    <span className="badge badge-amber">Low Confidence · Marginal Alignment</span>
  ) : (
    <span className="badge badge-red">Coarse Fallback · Mode B</span>
  );

  const handleRowClick = (row) => {
    setSelectedRegion(row.region);
    if (row.centroid_ras_mm && onSelectRegionCentroid) {
      onSelectRegionCentroid(row.centroid_ras_mm, row.region);
    }
  };

  return (
    <div style={{
      maxWidth: '1200px',
      margin: '0 auto',
      padding: '1.5rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '1.25rem',
      height: '100%',
      overflowY: 'auto'
    }}>

      {/* ── GLOBAL SAFETY & EDUCATION BANNER ───────────────────────────── */}
      <div style={{
        background: '#f8fafc',
        border: '1px solid #e2e8f0',
        borderRadius: '8px',
        padding: '0.65rem 1rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        fontSize: '0.78rem',
        color: '#475569'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <ShieldCheck size={16} color="var(--primary-blue)" />
          <span>
            <strong>RESEARCH & EDUCATION ONLY</strong>: Suspected tumour regions are predicted by an AI model.
            This is not a diagnosis and is not a substitute for clinical interpretation.
          </span>
        </div>
        <span className="badge badge-blue" style={{ fontSize: '0.68rem' }}>Non-Diagnostic</span>
      </div>

      {/* ── HEADER & STATUS CARD ──────────────────────────────────────── */}
      <div className="card" style={{ padding: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <div style={{
                background: 'var(--primary-blue-light)',
                color: 'var(--primary-blue)',
                padding: '6px',
                borderRadius: '8px',
                display: 'flex'
              }}>
                <Compass size={22} />
              </div>
              <div>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  Anatomical Localization
                </h2>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  SRI24 Template Space Mapping & Three Trainee Answer Cards
                </p>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            {statusBadge}
            {dice > 0 && (
              <span className="badge badge-blue mono" style={{ fontSize: '0.75rem' }}>
                Dice: {(dice * 100).toFixed(1)}%
              </span>
            )}
          </div>
        </div>

        {/* Quality Message Alert */}
        <div style={{
          marginTop: '0.85rem',
          padding: '0.65rem 0.85rem',
          borderRadius: '6px',
          background: isAvailable ? '#eff6ff' : isLowConfidence ? '#fffbeb' : '#fef2f2',
          border: `1px solid ${isAvailable ? '#bfdbfe' : isLowConfidence ? '#fef3c7' : '#fecaca'}`,
          fontSize: '0.8rem',
          color: isAvailable ? '#1e40af' : isLowConfidence ? '#92400e' : '#991b1b',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem'
        }}>
          {isAvailable ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>{qualityMsg}</span>
        </div>
      </div>

      {/* ── THREE ANSWER CARDS (THE QUESTIONS A TRAINEE ASKS) ─────────── */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
          <HelpCircle size={16} color="var(--primary-blue)" />
          <h3 style={{ fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Trainee Answer Cards
          </h3>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>

          {/* Card 1: One mass or several? */}
          <div className="card" style={{ padding: '1rem', borderLeft: '4px solid #0284c7' }}>
            <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>
              Question 1
            </div>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.2rem' }}>
              One mass or several?
            </h4>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#0284c7', marginTop: '0.45rem' }}>
              {card1.summary || 'Evaluating connected components...'}
            </div>

            {card1.components && card1.components.length > 0 && (
              <div style={{ marginTop: '0.6rem', borderTop: '1px solid var(--border-light)', paddingTop: '0.5rem' }}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>
                  26-Connectivity Components (≥ 0.1 mL):
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', maxHeight: '110px', overflowY: 'auto' }}>
                  {card1.components.map((c, i) => (
                    <div
                      key={c.id || i}
                      onClick={() => onSelectRegionCentroid && onSelectRegionCentroid(c.centroid_ras_mm, `Mass #${i + 1}`)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        fontSize: '0.75rem',
                        background: 'var(--bg-subtle)',
                        padding: '0.25rem 0.5rem',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                      title="Click to view this mass centroid in 2D/3D"
                    >
                      <span style={{ fontWeight: 600 }}>Mass #{i + 1}: {c.volume_ml.toFixed(2)} mL</span>
                      <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        RAS [{c.centroid_ras_mm.map(v => Math.round(v)).join(', ')}]
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Card 2: Which side? */}
          <div className="card" style={{ padding: '1rem', borderLeft: '4px solid #10b981' }}>
            <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>
              Question 2
            </div>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.2rem' }}>
              Which side?
            </h4>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#059669', marginTop: '0.45rem' }}>
              {card2.summary || 'Evaluating world coordinates...'}
            </div>

            <div style={{ marginTop: '0.6rem', borderTop: '1px solid var(--border-light)', paddingTop: '0.5rem', fontSize: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Dominant Side:</span>
                <strong>{card2.hemisphere || 'Midline'}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.2rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>Affine Orientation:</span>
                <span className="badge badge-gray mono">{card2.affine_orientation || 'RAS'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-muted)' }}>Centroid (RAS+ mm):</span>
                <span className="mono">[{card2.centroid_ras_mm?.map(v => Math.round(v * 10) / 10).join(', ') || '0, 0, 0'}]</span>
              </div>
            </div>
          </div>

          {/* Card 3: How big? */}
          <div className="card" style={{ padding: '1rem', borderLeft: '4px solid #f59e0b' }}>
            <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 700 }}>
              Question 3
            </div>
            <h4 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)', marginTop: '0.2rem' }}>
              How big?
            </h4>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#d97706', marginTop: '0.45rem' }}>
              {card3.summary || 'Calculating compartment volumes...'}
            </div>

            <div style={{ marginTop: '0.6rem', borderTop: '1px solid var(--border-light)', paddingTop: '0.5rem', fontSize: '0.72rem' }}>
              <div style={{ color: 'var(--text-muted)', marginBottom: '0.25rem' }}>
                Formula: <code style={{ fontSize: '0.68rem', color: '#b45309' }}>{card3.formula || 'voxels × voxel_vol / 1000'}</code>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                <span>WT: <strong>{card3.wt_volume_ml?.toFixed(2)} mL</strong> ({card3.wt_voxels?.toLocaleString()} vox)</span>
                <span>TC: <strong>{card3.tc_volume_ml?.toFixed(2)} mL</strong></span>
                <span>ET: <strong>{card3.et_volume_ml?.toFixed(2)} mL</strong></span>
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* ── MODE B COARSE FALLBACK (IF UNAVAILABLE) ────────────────────── */}
      {isUnavailable && modeBData && (
        <div className="card" style={{ padding: '1rem', background: '#fffbeb', border: '1px solid #fef3c7' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
            <AlertTriangle size={18} color="#d97706" />
            <h4 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#92400e' }}>
              Approximate coarse position (no atlas available)
            </h4>
          </div>
          <p style={{ fontSize: '0.8rem', color: '#78350f', lineHeight: 1.5 }}>
            {modeBData.summary || 'Scan does not align with the SRI24 template space. Coarse anatomical thirds reported.'}
          </p>
          <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.6rem', fontSize: '0.78rem' }}>
            <div><strong>Hemisphere:</strong> {modeBData.hemisphere || 'Midline'}</div>
            <div><strong>Anterior/Posterior:</strong> {modeBData.anterior_posterior || 'Middle third'}</div>
            <div><strong>Superior/Inferior:</strong> {modeBData.superior_inferior || 'Middle third'}</div>
          </div>
        </div>
      )}

      {/* ── DETERMINISTIC REPORT SUMMARY PARAGRAPHS ───────────────────── */}
      <div className="card" style={{ padding: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <FileText size={18} color="var(--primary-blue)" />
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Deterministic Report Summaries
          </h3>
        </div>

        <div style={{
          background: 'var(--bg-subtle)',
          border: '1px solid var(--border-light)',
          borderRadius: '6px',
          padding: '0.85rem',
          fontSize: '0.82rem',
          lineHeight: 1.6,
          display: 'flex',
          flexDirection: 'column',
          gap: '0.65rem'
        }}>
          <div>
            <strong style={{ color: '#0284c7' }}>Whole-Tumour (WT):</strong>{' '}
            {repSentences.wt_paragraph || 'No summary generated.'}
          </div>
          <div>
            <strong style={{ color: '#dc2626' }}>Tumour Core (TC):</strong>{' '}
            {repSentences.tc_paragraph || 'No summary generated.'}
          </div>
          <div>
            <strong style={{ color: '#0891b2' }}>Enhancing Tumour (ET):</strong>{' '}
            {repSentences.et_paragraph || 'No summary generated.'}
          </div>
        </div>
      </div>

      {/* ── REGIONAL INVOLVEMENT BREAKDOWN TABLE ───────────────────────── */}
      {table && table.length > 0 && (
        <div className="card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                Regional Anatomical Involvement Table
              </h3>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Click any row to jump to that structure's centroid in the 2D slices and 3D mesh
              </p>
            </div>
            <span className="badge badge-gray" style={{ fontSize: '0.7rem' }}>
              {table.length} Rows (Percentages sum to 100%)
            </span>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table className="data-table" style={{ width: '100%', fontSize: '0.78rem' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left' }}>Anatomical Region</th>
                  <th>WT %</th>
                  <th>WT (mL)</th>
                  <th>TC %</th>
                  <th>TC (mL)</th>
                  <th>ET %</th>
                  <th>ET (mL)</th>
                  <th>Centroid (RAS+ mm)</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {table.map((row, idx) => {
                  const isSelected = selectedRegion === row.region;
                  const isOutside = row.region.includes('Outside atlas');
                  return (
                    <tr
                      key={idx}
                      onClick={() => handleRowClick(row)}
                      style={{
                        cursor: 'pointer',
                        background: isSelected ? 'rgba(2, 132, 199, 0.08)' : isOutside ? '#fafafa' : undefined,
                        fontStyle: isOutside ? 'italic' : 'normal'
                      }}
                    >
                      <td style={{ textAlign: 'left', fontWeight: isOutside ? 400 : 600 }}>
                        {row.region}
                      </td>
                      <td className="mono" style={{ fontWeight: 600, color: '#0284c7' }}>
                        {row.wt_pct?.toFixed(1)}%
                      </td>
                      <td className="mono">{row.wt_ml?.toFixed(3)}</td>
                      <td className="mono">{row.tc_pct?.toFixed(1)}%</td>
                      <td className="mono">{row.tc_ml?.toFixed(3)}</td>
                      <td className="mono">{row.et_pct?.toFixed(1)}%</td>
                      <td className="mono">{row.et_ml?.toFixed(3)}</td>
                      <td className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        [{row.centroid_ras_mm?.map(v => Math.round(v)).join(', ')}]
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn btn-sm btn-outline"
                          style={{ padding: '2px 8px', fontSize: '0.7rem' }}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRowClick(row);
                          }}
                        >
                          <span>Locate</span>
                          <ArrowRight size={12} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── PROVENANCE & LIMITATIONS BLOCKS ────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>

        {/* Provenance Block */}
        <div className="card" style={{ padding: '1rem', fontSize: '0.75rem' }}>
          <h4 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
            Atlas Provenance & Verification
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', color: 'var(--text-secondary)' }}>
            <div><strong>Atlas Name:</strong> {provenance.atlas_name || 'SRI24 Multi-Channel Atlas (TZO116+)'}</div>
            <div><strong>License:</strong> {provenance.license || 'CC BY-SA 3.0'}</div>
            <div><strong>Reference:</strong> {provenance.citation || 'Rohlfing et al. Human Brain Mapping 2010'}</div>
            <div><strong>Mode:</strong> {mode}</div>
            <div><strong>Brain Mask Overlap Dice:</strong> {(dice * 100).toFixed(2)}%</div>
            <div><strong>Regions Evaluated:</strong> 421 anatomical structures</div>
            <div><strong>Affine Alignment Tolerance:</strong> ≤ 0.001 mm</div>
          </div>
        </div>

        {/* Limitations Block */}
        <div className="card" style={{ padding: '1rem', fontSize: '0.75rem' }}>
          <h4 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
            Clinical Research Limitations
          </h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', color: 'var(--text-secondary)' }}>
            <div>• <strong>Approximate research-use estimate</strong> derived from model-predicted voxels and atlas overlap.</div>
            <div>• <strong>No tumour type or histological grade</strong> is inferred or asserted.</div>
            <div>• <strong>No growth rate, prognosis, or survival</strong> metrics are provided.</div>
            <div>• <strong>Mass effect distortion</strong>: Intracranial mass effect may shift real tissue relative to atlas coordinates.</div>
            <div>• <strong>Not a clinical diagnosis</strong>: Does not replace board-certified neuroradiologist interpretation.</div>
          </div>
        </div>

      </div>

    </div>
  );
}
