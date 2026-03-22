'use client';

import { useState, useRef } from 'react';

interface TooltipProps {
  text: string;
  children: React.ReactNode;
  position?: 'top' | 'bottom' | 'right';
  width?: string;
}

// Shared tooltip box rendered via fixed positioning — never clipped by overflow containers
function TooltipBox({ text, coords, width }: { text: string; coords: { top: number; left: number; transform: string }; width: string }) {
  return (
    <span
      className={`fixed z-[9999] ${width} bg-gray-900 text-white text-[10px] leading-relaxed rounded-lg px-3 py-2 shadow-xl pointer-events-none`}
      style={{ top: coords.top, left: coords.left, transform: coords.transform, minWidth: '180px' }}
    >
      {text}
    </span>
  );
}

export function Tooltip({ text, children, position = 'top', width = 'w-64' }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0, transform: 'none' });
  const ref = useRef<HTMLSpanElement>(null);

  const handleEnter = () => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    if (position === 'bottom') {
      setCoords({ top: r.bottom + 6, left: r.left, transform: 'none' });
    } else if (position === 'right') {
      setCoords({ top: r.top, left: r.right + 6, transform: 'none' });
    } else {
      // top (default)
      setCoords({ top: r.top - 6, left: r.left, transform: 'translateY(-100%)' });
    }
    setVisible(true);
  };

  return (
    <span
      ref={ref}
      className="inline-flex items-center gap-1 cursor-help"
      onMouseEnter={handleEnter}
      onMouseLeave={() => setVisible(false)}
    >
      {children}
      <span className="text-gray-300 hover:text-gray-400 text-[8px] leading-none select-none">ⓘ</span>
      {visible && <TooltipBox text={text} coords={coords} width={width} />}
    </span>
  );
}

// Standalone info icon with tooltip — use when you can't wrap the label
export function InfoTip({ text, width = 'w-64' }: { text: string; width?: string }) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0, transform: 'none' });
  const ref = useRef<HTMLSpanElement>(null);

  const handleEnter = () => {
    if (!ref.current) return;
    const r = ref.current.getBoundingClientRect();
    setCoords({ top: r.top - 6, left: r.left, transform: 'translateY(-100%)' });
    setVisible(true);
  };

  return (
    <span ref={ref} className="relative inline-block">
      <span
        className="text-gray-300 hover:text-gray-500 text-[9px] cursor-help select-none transition-colors"
        onMouseEnter={handleEnter}
        onMouseLeave={() => setVisible(false)}
      >
        ⓘ
      </span>
      {visible && <TooltipBox text={text} coords={coords} width={width} />}
    </span>
  );
}
