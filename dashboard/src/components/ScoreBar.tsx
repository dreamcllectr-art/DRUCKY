'use client';

import { cs, fg } from '@/lib/styles';

interface Props {
  value: number;
  label: string;
  max?: number;
}

export default function ScoreBar({ value, label, max = 100 }: Props) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const color =
    pct >= 70 ? '#059669' :
    pct >= 40 ? '#d97706' :
    '#e11d48';
  const glow = value >= 70;

  return (
    <div className="flex items-center gap-3">
      <span className="text-[10px] text-gray-500 w-24 shrink-0 tracking-wider uppercase">
        {label}
      </span>
      <div className="flex-1 h-2 bg-gray-100 rounded-lg overflow-hidden relative">
        <div
          className="h-full rounded-lg transition-all duration-500"
          {...cs({
            width: `${pct}%`,
            backgroundColor: color,
            boxShadow: glow ? `0 0 8px ${color}40, 0 0 2px ${color}60` : 'none',
          })}
        />
      </div>
      <span
        className="text-[11px] font-mono w-8 text-right font-bold"
        {...fg(color)}
      >
        {value.toFixed(0)}
      </span>
    </div>
  );
}
