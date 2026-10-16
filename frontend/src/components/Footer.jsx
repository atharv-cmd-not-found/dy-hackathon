import React from 'react';
import { AlertCircle } from 'lucide-react';

export default function Footer() {
  return (
    <footer style={{
      background: '#ffffff',
      borderTop: '1px solid var(--border-light)',
      padding: '0.65rem 1.5rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '0.5rem',
      fontSize: '0.75rem',
      color: 'var(--text-secondary)',
      zIndex: 40
    }}>
      <AlertCircle size={14} color="#b45309" />
      <span>
        <strong>Medical Research Prototype:</strong> Model outputs represent suspected tumour regions predicted by AI algorithms; volumes are estimates. Not a clinical diagnosis. Must not replace professional radiological evaluation.
      </span>
    </footer>
  );
}
