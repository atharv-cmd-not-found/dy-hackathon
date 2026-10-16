import React from 'react';
import { Loader2, CheckCircle2, Clock, Activity } from 'lucide-react';

const STAGES = [
  { id: 'validating', name: 'Stage 1: Scan Integrity & Affine Validation', desc: 'Verifies 3D dimensions, non-finite voxels, and spatial affine matrix' },
  { id: 'segmenting', name: 'Stage 2: BraTS 2021 Neural Segmentation', desc: 'Predicts necrotic core (NCR), edema (ED), and enhancing tumour (ET)' },
  { id: 'volumetrics', name: 'Stage 3: Volumetric & Laterality Analysis', desc: 'Computes volume (mL) via |det(affine)| and brain centroid laterality' },
  { id: 'meshing', name: 'Stage 4: 3D Surface Reconstruction', desc: 'Marching cubes in voxel space, world mm mapping, and GLB export' },
];

export default function ProcessingView({ caseData }) {
  const currentStage = caseData?.stage || 'queued';
  const stageSeconds = caseData?.stage_seconds || {};

  const getStageStatus = (stageId, index) => {
    const stageOrder = ['validating', 'segmenting', 'volumetrics', 'meshing', 'done'];
    const currentIndex = stageOrder.indexOf(currentStage);
    const thisIndex = stageOrder.indexOf(stageId);

    if (caseData?.status === 'done' || currentIndex > thisIndex) {
      return 'completed';
    } else if (currentIndex === thisIndex) {
      return 'active';
    } else {
      return 'pending';
    }
  };

  return (
    <div style={{ maxWidth: '680px', margin: '4rem auto', padding: '0 1.5rem' }}>
      <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>
        <div style={{
          width: '54px',
          height: '54px',
          borderRadius: '50%',
          background: 'var(--primary-blue-light)',
          color: 'var(--primary-blue)',
          margin: '0 auto 1.25rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <Loader2 size={28} className="animate-spin" style={{ animation: 'spin 1.5s linear infinite' }} />
        </div>

        <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)' }}>
          Processing Brain MRI Case
        </h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
          Case ID: <code style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{caseData?.case_id}</code>
        </p>

        {/* Linear Stage Progress */}
        <div style={{ marginTop: '2rem', textAlign: 'left', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {STAGES.map((s, idx) => {
            const status = getStageStatus(s.id, idx);
            const duration = stageSeconds[s.id];

            return (
              <div
                key={s.id}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: '0.85rem',
                  padding: '0.85rem 1rem',
                  borderRadius: '6px',
                  background: status === 'active' ? 'var(--bg-subtle)' : '#ffffff',
                  border: status === 'active' ? '1px solid var(--primary-blue)' : '1px solid var(--border-light)'
                }}
              >
                <div style={{ marginTop: '2px' }}>
                  {status === 'completed' && <CheckCircle2 size={18} color="var(--success-green)" />}
                  {status === 'active' && <Loader2 size={18} color="var(--primary-blue)" style={{ animation: 'spin 1.5s linear infinite' }} />}
                  {status === 'pending' && <Clock size={18} color="var(--text-muted)" />}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ fontSize: '0.875rem', fontWeight: 600, color: status === 'active' ? 'var(--primary-blue)' : 'var(--text-primary)' }}>
                      {s.name}
                    </div>
                    {duration !== undefined && (
                      <span className="badge badge-blue" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem' }}>
                        {duration}s
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                    {s.desc}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <style>{`
        @keyframes spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
