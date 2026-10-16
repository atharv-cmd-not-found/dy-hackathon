import React, { useState } from 'react';
import { UploadCloud, FileCheck, AlertCircle, FileText, X, ArrowRight, ShieldCheck, Sparkles } from 'lucide-react';

const REQUIRED_SLOTS = [
  { id: 't1', label: 'T1-Weighted', sub: 'Anatomical reference scan', desc: 'Baseline tissue contrast without enhancement' },
  { id: 't1gd', label: 'T1-Gd (Contrast)', sub: 'Post-Gadolinium enhancement', desc: 'Highlights active vascularized enhancing tumour rim (ET)' },
  { id: 't2', label: 'T2-Weighted', sub: 'Fluid-sensitive sequence', desc: 'Defines anatomical boundaries and peritumoral edema' },
  { id: 'flair', label: 'T2-FLAIR', sub: 'Fluid-Attenuated Inversion', desc: 'Suppresses free CSF to delineate whole tumour perimeter (WT)' },
];

export default function UploadView({ onUploadSubmit, isSubmitting, uploadError, clearError, onLoadDemo, isDemoLoading }) {
  const [files, setFiles] = useState({
    t1: null,
    t1gd: null,
    t2: null,
    flair: null,
    expert: null,
  });

  const [dragOverSlot, setDragOverSlot] = useState(null);
  const [clientErrors, setClientErrors] = useState({});

  // Client-side extension pre-flight validation
  const validateFileExtension = (file) => {
    if (!file) return false;
    const name = file.name.toLowerCase();
    return name.endsWith('.nii.gz') || name.endsWith('.nii');
  };

  const handleFileSelect = (slot, file) => {
    clearError();
    if (!file) return;

    if (!validateFileExtension(file)) {
      setClientErrors(prev => ({
        ...prev,
        [slot]: `Invalid file format (${file.name}). Only .nii or .nii.gz NIfTI files are accepted.`
      }));
      return;
    }

    setClientErrors(prev => {
      const copy = { ...prev };
      delete copy[slot];
      return copy;
    });

    setFiles(prev => ({ ...prev, [slot]: file }));
  };

  // Auto-assignment helper based on filename
  const autoAssignFiles = (fileList) => {
    clearError();
    const newFiles = { ...files };
    const newErrors = { ...clientErrors };

    Array.from(fileList).forEach(file => {
      if (!validateFileExtension(file)) {
        return;
      }
      const fn = file.name.toLowerCase();
      if (fn.includes('flair')) {
        newFiles.flair = file;
        delete newErrors.flair;
      } else if (fn.includes('t1gd') || fn.includes('t1ce') || fn.includes('t1c')) {
        newFiles.t1gd = file;
        delete newErrors.t1gd;
      } else if (fn.includes('t2')) {
        newFiles.t2 = file;
        delete newErrors.t2;
      } else if (fn.includes('t1')) {
        newFiles.t1 = file;
        delete newErrors.t1;
      } else if (fn.includes('seg') || fn.includes('mask') || fn.includes('label')) {
        newFiles.expert = file;
        delete newErrors.expert;
      }
    });

    setFiles(newFiles);
    setClientErrors(newErrors);
  };

  const isFormComplete = files.t1 && files.t1gd && files.t2 && files.flair;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!isFormComplete) return;
    onUploadSubmit(files);
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return '';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '2rem auto', padding: '0 1.5rem' }}>
      {/* Title & Guidance */}
      <div style={{ marginBottom: '1.25rem', textAlign: 'center' }}>
        <h2 style={{ fontSize: '1.6rem', fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
          Upload Multi-Sequence Brain MRI Scans
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', maxWidth: '640px', margin: '0.4rem auto 0' }}>
          Upload 4 canonical MRI sequences (<code>.nii.gz</code>) or test immediately with the newly added clinical BraTS 2021 dataset.
        </p>
      </div>

      {/* Quick Launch Real BraTS 2021 Case Banner */}
      {onLoadDemo && (
        <div style={{
          background: 'linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%)',
          border: '1px solid #bfdbfe',
          borderRadius: '10px',
          padding: '0.9rem 1.25rem',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.75rem',
          boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{
              width: '36px', height: '36px', borderRadius: '8px',
              background: '#2563eb', color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Sparkles size={20} />
            </div>
            <div>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#1e3a8a' }}>
                Real BraTS 2021 Dataset Ready (Case #00012)
              </div>
              <div style={{ fontSize: '0.75rem', color: '#475569', marginTop: '0.1rem' }}>
                4 sequences detected in workspace (T1, T1-CE, T2, FLAIR) • High-resolution skull-stripped clinical scan
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={onLoadDemo}
            disabled={isDemoLoading || isSubmitting}
            className="btn btn-primary"
            style={{ fontSize: '0.825rem', padding: '0.5rem 1.1rem', background: '#2563eb' }}
          >
            <Sparkles size={15} />
            <span>{isDemoLoading ? 'Launching Pipeline...' : 'Test on BraTS 2021 Data'}</span>
          </button>
        </div>
      )}

      {/* Backend / Global Error Banner */}
      {uploadError && (
        <div style={{
          background: 'var(--danger-light)',
          border: '1px solid #fecaca',
          borderRadius: '8px',
          padding: '1rem',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '0.75rem'
        }}>
          <AlertCircle size={20} color="#dc2626" style={{ marginTop: '2px', flexShrink: 0 }} />
          <div>
            <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#991b1b' }}>
              Validation Error: {uploadError.code || 'VALIDATION_FAILED'}
            </h4>
            <p style={{ fontSize: '0.8125rem', color: '#b91c1c', marginTop: '0.2rem' }}>
              {uploadError.message}
            </p>
          </div>
        </div>
      )}

      {/* Global Drag & Drop Strip */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          if (e.dataTransfer.files) autoAssignFiles(e.dataTransfer.files);
        }}
        style={{
          border: '2px dashed #cbd5e1',
          borderRadius: '10px',
          padding: '1.5rem',
          textAlign: 'center',
          background: '#ffffff',
          marginBottom: '1.5rem',
          cursor: 'pointer'
        }}
        onClick={() => document.getElementById('batch-upload').click()}
      >
        <input
          id="batch-upload"
          type="file"
          multiple
          accept=".nii,.nii.gz"
          style={{ display: 'none' }}
          onChange={(e) => {
            if (e.target.files) autoAssignFiles(e.target.files);
          }}
        />
        <UploadCloud size={32} color="var(--primary-blue)" style={{ margin: '0 auto 0.5rem' }} />
        <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)' }}>
          Drop all scan files here for auto-slot assignment
        </h3>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
          Select multiple files simultaneously, or populate each sequence card below manually.
        </p>
      </div>

      {/* 4 Required Sequence Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        {REQUIRED_SLOTS.map((slot) => {
          const file = files[slot.id];
          const error = clientErrors[slot.id];
          const isOver = dragOverSlot === slot.id;

          return (
            <div
              key={slot.id}
              className="card"
              style={{
                padding: '1rem',
                border: error ? '1px solid var(--danger-red)' : isOver ? '2px solid var(--primary-blue)' : '1px solid var(--border-light)',
                background: file ? 'var(--bg-card)' : '#ffffff',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between'
              }}
              onDragOver={(e) => { e.preventDefault(); setDragOverSlot(slot.id); }}
              onDragLeave={() => setDragOverSlot(null)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOverSlot(null);
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  handleFileSelect(slot.id, e.dataTransfer.files[0]);
                }
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                  <span className="badge badge-blue" style={{ fontWeight: 600, fontSize: '0.75rem' }}>
                    {slot.label}
                  </span>
                  {file ? (
                    <span style={{ color: 'var(--success-green)', display: 'flex', alignItems: 'center', gap: '0.2rem', fontSize: '0.75rem', fontWeight: 500 }}>
                      <FileCheck size={14} /> Ready
                    </span>
                  ) : (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Required</span>
                  )}
                </div>

                <div style={{ fontSize: '0.8rem', fontWeight: 500, color: 'var(--text-primary)' }}>
                  {slot.sub}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem', lineHeight: 1.3 }}>
                  {slot.desc}
                </div>
              </div>

              {/* Slot Staged File Info or Upload Button */}
              <div style={{ marginTop: '1rem' }}>
                {file ? (
                  <div style={{
                    background: 'var(--bg-subtle)',
                    borderRadius: '6px',
                    padding: '0.5rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                  }}>
                    <div style={{ overflow: 'hidden', paddingRight: '0.5rem' }}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 500, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                        {file.name}
                      </div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        {formatFileSize(file.size)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFiles(prev => ({ ...prev, [slot.id]: null }))}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <div>
                    <label
                      htmlFor={`input-${slot.id}`}
                      className="btn btn-outline btn-sm"
                      style={{ width: '100%', cursor: 'pointer' }}
                    >
                      <span>Choose Scan File</span>
                    </label>
                    <input
                      id={`input-${slot.id}`}
                      type="file"
                      accept=".nii,.nii.gz"
                      style={{ display: 'none' }}
                      onChange={(e) => {
                        if (e.target.files && e.target.files[0]) {
                          handleFileSelect(slot.id, e.target.files[0]);
                        }
                      }}
                    />
                  </div>
                )}

                {error && (
                  <div style={{ fontSize: '0.7rem', color: 'var(--danger-red)', marginTop: '0.4rem', lineHeight: 1.2 }}>
                    {error}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Optional Expert Ground Truth Mask Card */}
      <div className="card" style={{ marginTop: '1rem', padding: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="badge" style={{ background: '#f1f5f9', color: '#475569' }}>Optional</span>
              <h4 style={{ fontSize: '0.875rem', fontWeight: 600 }}>Expert Ground Truth Mask (.nii.gz)</h4>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.2rem' }}>
              Attach radiologist ground truth mask to compute Dice coefficient and Sensitivity agreement metrics.
            </p>
          </div>

          <div>
            {files.expert ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'var(--bg-subtle)', padding: '0.35rem 0.75rem', borderRadius: '6px' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 500 }}>{files.expert.name}</span>
                <button
                  type="button"
                  onClick={() => setFiles(prev => ({ ...prev, expert: null }))}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                >
                  <X size={14} />
                </button>
              </div>
            ) : (
              <div>
                <label htmlFor="input-expert" className="btn btn-outline btn-sm" style={{ cursor: 'pointer' }}>
                  <span>Attach Mask</span>
                </label>
                <input
                  id="input-expert"
                  type="file"
                  accept=".nii,.nii.gz"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileSelect('expert', e.target.files[0]);
                    }
                  }}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Submit Action */}
      <div style={{ marginTop: '2rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          <ShieldCheck size={18} color="var(--primary-blue)" />
          <span>Local Monolith Execution: No data leaves this device. 24-hr secure TTL.</span>
        </div>

        <button
          onClick={handleSubmit}
          disabled={!isFormComplete || isSubmitting}
          className="btn btn-primary"
          style={{ padding: '0.7rem 1.8rem', opacity: (!isFormComplete || isSubmitting) ? 0.6 : 1 }}
        >
          <span>{isSubmitting ? 'Uploading Scans...' : 'Run Automated Analysis'}</span>
          <ArrowRight size={16} />
        </button>
      </div>
    </div>
  );
}
