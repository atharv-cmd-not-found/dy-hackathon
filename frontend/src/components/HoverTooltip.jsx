import React from 'react';
import { getTumourStatusInfo } from './coordUtils';

export default function HoverTooltip({
  x,
  y,
  mm,
  vox,
  predVal = 0,
  anatVal = 0,
  regionName = '',
  hemisphere = null,
  lobe = null,
  activeIntensity = null,
  activeModality = 'T1',
  labelsUnavailable = false,
  unavailableReason = ''
}) {
  if (x === null || y === null || !mm || !vox) return null;

  const tumorInfo = getTumourStatusInfo(predVal);

  // Position offset to prevent cursor overlap
  const offsetX = 16;
  const offsetY = 16;
  
  // Guard against overflowing window edge
  const screenW = typeof window !== 'undefined' ? window.innerWidth : 1200;
  const screenH = typeof window !== 'undefined' ? window.innerHeight : 800;
  
  const left = x + offsetX + 240 > screenW ? x - 250 : x + offsetX;
  const top = y + offsetY + 180 > screenH ? y - 190 : y + offsetY;

  return (
    <div
      style={{
        position: 'fixed',
        left: `${left}px`,
        top: `${top}px`,
        zIndex: 9999,
        pointerEvents: 'none',
        background: 'rgba(15, 23, 42, 0.94)',
        backdropFilter: 'blur(8px)',
        border: '1px solid rgba(255, 255, 255, 0.15)',
        borderRadius: '8px',
        padding: '0.65rem 0.85rem',
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.6), 0 0 1px 1px rgba(255, 255, 255, 0.1)',
        color: '#f8fafc',
        fontSize: '0.75rem',
        maxWidth: '280px',
        lineHeight: 1.35,
        transition: 'opacity 0.08s ease-out',
      }}
    >
      {/* Region Name / Anatomical Identity */}
      <div style={{ marginBottom: '0.35rem' }}>
        <div style={{
          fontSize: '0.82rem',
          fontWeight: 700,
          color: labelsUnavailable ? '#94a3b8' : '#38bdf8',
          display: 'flex',
          alignItems: 'center',
          gap: '0.3rem',
          flexWrap: 'wrap'
        }}>
          <span>
            {labelsUnavailable
              ? 'Anatomical labels unavailable'
              : (regionName || (anatVal > 0 ? `Structure #${anatVal}` : 'Cerebral Cortex'))}
          </span>
        </div>

        {!labelsUnavailable && (hemisphere || lobe) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginTop: '0.2rem' }}>
            {hemisphere && (
              <span style={{
                background: hemisphere === 'Left' ? 'rgba(56, 189, 248, 0.2)' : 'rgba(168, 85, 247, 0.2)',
                color: hemisphere === 'Left' ? '#38bdf8' : '#c084fc',
                fontSize: '0.65rem',
                padding: '1px 5px',
                borderRadius: '3px',
                fontWeight: 600
              }}>
                {hemisphere} Hemisphere
              </span>
            )}
            {lobe && (
              <span style={{
                background: 'rgba(255, 255, 255, 0.08)',
                color: '#cbd5e1',
                fontSize: '0.65rem',
                padding: '1px 5px',
                borderRadius: '3px'
              }}>
                {lobe}
              </span>
            )}
          </div>
        )}

        {labelsUnavailable && unavailableReason && (
          <div style={{ fontSize: '0.65rem', color: '#94a3b8', fontStyle: 'italic', marginTop: '0.15rem' }}>
            {unavailableReason}
          </div>
        )}
      </div>

      {/* Tumour Prediction Status */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.25rem 0.4rem',
        background: tumorInfo.status === 'inside_tumor' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(255, 255, 255, 0.05)',
        borderRadius: '4px',
        border: tumorInfo.status === 'inside_tumor' ? '1px solid rgba(239, 68, 68, 0.3)' : '1px solid rgba(255, 255, 255, 0.05)',
        marginBottom: '0.35rem'
      }}>
        <span style={{ fontSize: '0.68rem', color: '#cbd5e1' }}>
          Tumour Status (predicted):
        </span>
        <span style={{
          fontSize: '0.68rem',
          fontWeight: 600,
          color: tumorInfo.status === 'inside_tumor' ? '#f87171' : '#94a3b8'
        }}>
          {tumorInfo.label !== 'Normal' ? `Inside ${tumorInfo.label}` : 'Outside Tumour'}
        </span>
      </div>

      {/* Spatial Coordinates & Voxel Index */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '0.35rem',
        fontSize: '0.66rem',
        fontFamily: 'var(--font-mono)',
        color: '#94a3b8',
        borderTop: '1px solid rgba(255, 255, 255, 0.08)',
        paddingTop: '0.35rem'
      }}>
        <div>
          <span style={{ color: '#64748b' }}>RAS+ mm: </span>
          [{mm[0]}, {mm[1]}, {mm[2]}]
        </div>
        <div>
          <span style={{ color: '#64748b' }}>Voxel: </span>
          [{vox[0]}, {vox[1]}, {vox[2]}]
        </div>
      </div>

      {/* Intensity (if available) */}
      {activeIntensity !== null && activeIntensity !== undefined && (
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: '0.65rem',
          marginTop: '0.25rem',
          color: '#64748b',
          fontFamily: 'var(--font-mono)'
        }}>
          <span>Underlay ({activeModality}):</span>
          <span style={{ color: '#38bdf8', fontWeight: 600 }}>{Math.round(activeIntensity)}</span>
        </div>
      )}

      {/* Pinning Hint */}
      <div style={{
        marginTop: '0.35rem',
        textAlign: 'center',
        fontSize: '0.6rem',
        color: '#64748b',
        borderTop: '1px dashed rgba(255, 255, 255, 0.08)',
        paddingTop: '0.25rem'
      }}>
        Click anywhere to pin inspection panel
      </div>
    </div>
  );
}
