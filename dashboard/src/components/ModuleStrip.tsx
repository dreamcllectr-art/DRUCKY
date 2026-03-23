'use client';

import { useState } from 'react';
import { MODULES, TOTAL_WEIGHT, scoreColor, scoreBg, getModuleScore } from '@/lib/modules';
import type { ConvergenceSignal } from '@/lib/api';
import { cs, fg } from '@/lib/styles';

interface Props {
  convergence: ConvergenceSignal;
  mode: 'compact' | 'expanded';
}

export default function ModuleStrip({ convergence, mode }: Props) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  if (mode === 'compact') {
    // Parse active modules — only show modules that are actually firing
    let activeKeys: string[] = [];
    try { activeKeys = JSON.parse((convergence as unknown as { active_modules?: string }).active_modules || '[]'); } catch {}

    // active_modules stores keys without _score suffix (e.g. "smartmoney" not "smartmoney_score")
    const activeModules = MODULES.filter(m => activeKeys.includes(m.key.replace(/_score$/, '')));

    return (
      <div className="flex flex-wrap gap-1">
        {activeModules.length === 0 && <span className="text-gray-400 text-[10px]">—</span>}
        {activeModules.map(m => {
          const val = getModuleScore(convergence, m.key);
          return (
            <span
              key={m.key}
              title={`${m.label}: ${val != null ? val.toFixed(0) : '—'}`}
              className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold tracking-wide cursor-default"
              {...cs({
                backgroundColor: scoreBg(val),
                color: scoreColor(val),
              })}
            >
              {m.shortLabel}
            </span>
          );
        })}
      </div>
    );
  }

  // ── Expanded mode: only show modules with data, sorted by score ──
  const withScores = MODULES
    .map(m => ({ m, val: getModuleScore(convergence, m.key) }))
    .filter(({ val }) => val != null && val > 0)
    .sort((a, b) => (b.val ?? 0) - (a.val ?? 0));

  return (
    <div className="space-y-1.5">
      {withScores.map(({ m, val }) => {
        const color = scoreColor(val);
        return (
          <div key={m.key} className="flex items-center gap-3">
            <span className="text-[10px] text-gray-500 w-32 shrink-0 tracking-wider uppercase">
              {m.label}
            </span>
            <div className="flex-1 h-[4px] bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                {...cs({
                  width: `${val}%`,
                  backgroundColor: color,
                })}
              />
            </div>
            <span className="text-[10px] font-mono w-7 text-right font-bold" {...fg(color)}>
              {val!.toFixed(0)}
            </span>
          </div>
        );
      })}
      {withScores.length === 0 && <span className="text-[10px] text-gray-400">No module scores available.</span>}
    </div>
  );
}
