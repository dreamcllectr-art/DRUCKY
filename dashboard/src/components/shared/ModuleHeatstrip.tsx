'use client';

import { useState } from 'react';
import { MODULES, scoreColor } from '@/lib/modules';
import { cs } from '@/lib/styles';

interface Props {
  scores: Record<string, number>;
  compact?: boolean;
}

export default function ModuleHeatstrip({ scores, compact = false }: Props) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const cellH = compact ? 'h-[6px]' : 'h-[14px]';

  return (
    <div className="relative">
      <div className="flex rounded overflow-hidden" {...cs({ gap: '1px' })}>
        {MODULES.map((m, i) => {
          const val = scores[m.key] ?? null;
          const color = val != null && val > 0
            ? val >= 60 ? '#059669' : val >= 40 ? '#d97706' : '#9ca3af'
            : '#e5e7eb';
          return (
            <div
              key={m.key}
              className={`flex-1 ${cellH} rounded-sm cursor-default transition-all`}
              {...cs({ backgroundColor: color, opacity: val != null && val > 0 ? 1 : 0.3 })}
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
            />
          );
        })}
      </div>
      {hoveredIdx !== null && (() => {
        const m = MODULES[hoveredIdx];
        const val = scores[m.key];
        return (
          <div
            className="absolute z-50 px-2 py-1 rounded text-[9px] font-mono whitespace-nowrap pointer-events-none bg-white border border-gray-300 shadow-sm"
            {...cs({
              bottom: compact ? '10px' : '18px',
              left: `${(hoveredIdx / MODULES.length) * 100}%`,
              transform: 'translateX(-50%)',
              color: scoreColor(val),
            })}
          >
            {m.shortLabel} {val != null ? val.toFixed(0) : '\u2014'}
          </div>
        );
      })()}
    </div>
  );
}
