'use client';

import { useState } from 'react';
import { MODULES, TOTAL_WEIGHT, scoreColor, scoreBg } from '@/lib/modules';
import type { ConvergenceSignal } from '@/lib/api';

interface Props {
  convergence: ConvergenceSignal;
  mode: 'compact' | 'expanded';
}

export default function ModuleStrip({ convergence, mode }: Props) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (mode === 'compact') {
    return (
      <div className="relative">
        <div
          className="flex h-[6px] rounded-sm overflow-hidden"
          style={{ gap: '1px' }}
        >
          {MODULES.map((m, i) => {
            const val = (convergence as any)[m.key] as number | null;
            const w = Math.max(1, (m.weight / TOTAL_WEIGHT) * 100);
            return (
              <div
                key={m.key}
                className="relative transition-all duration-200"
                style={{
                  width: `${w}%`,
                  backgroundColor: val != null && val > 0 ? scoreColor(val) : '#222',
                  opacity: val != null && val > 0 ? (val >= 70 ? 1 : val >= 50 ? 0.7 : val >= 25 ? 0.5 : 0.4) : 0.15,
                  boxShadow: val != null && val >= 70 ? `0 0 4px ${scoreColor(val)}40` : 'none',
                }}
                onMouseEnter={() => setHoveredIdx(i)}
                onMouseLeave={() => setHoveredIdx(null)}
              />
            );
          })}
        </div>
        {/* Tooltip */}
        {hoveredIdx !== null && (() => {
          const m = MODULES[hoveredIdx];
          const val = (convergence as any)[m.key] as number | null;
          return (
            <div
              className="absolute z-50 px-2 py-1 rounded text-[9px] font-mono whitespace-nowrap pointer-events-none"
              style={{
                top: '-28px',
                left: `${(hoveredIdx / MODULES.length) * 100}%`,
                transform: 'translateX(-50%)',
                backgroundColor: '#1A1A1A',
                border: '1px solid #333',
                color: scoreColor(val),
              }}
            >
              {m.shortLabel} {val != null ? val.toFixed(0) : '—'}
            </div>
          );
        })()}
      </div>
    );
  }

  // ── Expanded mode: horizontal bar chart ──
  const sorted = [...MODULES].sort((a, b) => b.weight - a.weight);

  return (
    <div className="space-y-1">
      {sorted.map(m => {
        const val = (convergence as any)[m.key] as number | null;
        const displayVal = val != null && val > 0 ? val : 0;
        const color = scoreColor(val);

        return (
          <div key={m.key} className="flex items-center gap-2">
            <span className="text-[9px] text-terminal-dim w-[100px] shrink-0 truncate tracking-wider uppercase">
              {m.label}
              <span className="text-terminal-dim/50 ml-1">({m.weight}%)</span>
            </span>
            <div className="flex-1 h-[5px] bg-terminal-muted/30 rounded-sm overflow-hidden">
              <div
                className="h-full rounded-sm transition-all duration-500"
                style={{
                  width: `${displayVal}%`,
                  backgroundColor: color,
                  boxShadow: displayVal >= 70 ? `0 0 6px ${color}40` : 'none',
                }}
              />
            </div>
            <span
              className="text-[9px] font-mono w-6 text-right font-bold"
              style={{ color }}
            >
              {val != null && val > 0 ? val.toFixed(0) : '—'}
            </span>
          </div>
        );
      })}
    </div>
  );
}
