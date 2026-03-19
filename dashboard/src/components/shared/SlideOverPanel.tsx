'use client';

import { useEffect, useCallback } from 'react';

interface Props {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  title?: string;
}

export default function SlideOverPanel({ open, onClose, children, title }: Props) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      {/* Panel */}
      <div className="relative w-[60%] max-w-[900px] min-w-[400px] bg-white shadow-2xl border-l border-gray-200 overflow-y-auto animate-slide-in">
        <div className="sticky top-0 z-10 bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
          {title && <h2 className="text-sm font-semibold text-gray-900 tracking-wide">{title}</h2>}
          <button
            onClick={onClose}
            className="ml-auto text-gray-400 hover:text-gray-700 transition-colors text-lg leading-none p-1"
          >
            &times;
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
      <style jsx>{`
        @keyframes slideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in {
          animation: slideIn 0.2s ease-out;
        }
      `}</style>
    </div>
  );
}
