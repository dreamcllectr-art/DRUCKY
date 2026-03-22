'use client';

import React, { useState } from 'react';
import type { ConvergenceSignal } from '@/lib/api';
import ModuleStrip from '@/components/ModuleStrip';
import { scoreColor } from '@/lib/modules';
import { cs, fg } from '@/lib/styles';

type SortKey = 'convergence_score' | 'module_count';

function convictionColor(conviction: string) {
  switch (conviction?.toLowerCase()) {
    case 'high': return 'text-emerald-600';
    case 'medium': return 'text-amber-600';
    case 'low': return 'text-gray-500';
    default: return 'text-gray-500';
  }
}

interface Props {
  data: ConvergenceSignal[];
}

export default function ConvergenceHeatmap({ data }: Props) {
  const [sortBy, setSortBy] = useState<SortKey>('convergence_score');
  const [expanded, setExpanded] = useState<string | null>(null);

  const sorted = [...data].sort((a, b) => {
    const av = a[sortBy] ?? 0;
    const bv = b[sortBy] ?? 0;
    return bv - av;
  });

  return (
    <div className="panel overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase">
              <th className="text-left py-3 px-4 font-normal w-20">Symbol</th>
              <th
                className="text-right py-3 px-2 font-normal cursor-pointer hover:text-emerald-600 transition-colors w-16"
                onClick={() => setSortBy('convergence_score')}
              >
                Score {sortBy === 'convergence_score' ? '↓' : ''}
              </th>
              <th className="text-center py-3 px-2 font-normal w-16">Conv.</th>
              <th
                className="text-right py-3 px-2 font-normal cursor-pointer hover:text-emerald-600 transition-colors w-12"
                onClick={() => setSortBy('module_count')}
              >
                Mod {sortBy === 'module_count' ? '↓' : ''}
              </th>
              <th className="text-center py-3 px-2 font-normal">
                <span className="text-[8px]">MODULE AGREEMENT</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s, i) => {
              const isTop5 = i < 5;
              return (
                <React.Fragment key={s.symbol}>
                  <tr
                    className={`border-b border-gray-200/50 hover:bg-emerald-600/[0.03] transition-colors cursor-pointer ${
                      isTop5 ? 'border-l-2 border-l-emerald-600/30' : ''
                    }`}
                    {...cs({
                      backgroundColor: isTop5 ? `rgba(5,150,105,${0.01 + (5 - i) * 0.005})` : undefined,
                    })}
                    onClick={() => setExpanded(expanded === s.symbol ? null : s.symbol)}
                  >
                    <td className="py-2.5 px-4">
                      <a
                        href={`/asset/${s.symbol}`}
                        className="font-mono font-bold text-gray-900 hover:text-emerald-600 transition-colors"
                        onClick={e => e.stopPropagation()}
                      >
                        {s.symbol}
                      </a>
                    </td>
                    <td className="py-2.5 px-2 text-right">
                      <span className="font-mono font-bold" {...fg(scoreColor(s.convergence_score))}>
                        {s.convergence_score.toFixed(1)}
                      </span>
                    </td>
                    <td className={`py-2.5 px-2 text-center text-[10px] font-bold tracking-wider ${convictionColor(s.conviction_level)}`}>
                      {s.conviction_level?.toUpperCase()}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono text-gray-700">
                      {s.module_count}
                    </td>
                    <td className="py-2.5 px-2">
                      <ModuleStrip convergence={s} mode="compact" />
                    </td>
                  </tr>
                  {expanded === s.symbol && (
                    <tr key={`${s.symbol}-detail`} className="bg-gray-50/50">
                      <td colSpan={5} className="px-4 py-4">
                        <div className="grid grid-cols-2 gap-6">
                          <div>
                            <div className="text-[10px] text-gray-500 tracking-wider mb-1">NARRATIVE</div>
                            <p className="text-[11px] text-gray-700 leading-relaxed">
                              {s.narrative || 'No narrative available.'}
                            </p>
                            <div className="flex gap-4 mt-3 text-[10px] text-gray-500">
                              <span>Active: {s.active_modules || '—'}</span>
                            </div>
                          </div>
                          <div>
                            <div className="text-[10px] text-gray-500 tracking-wider mb-2">MODULE BREAKDOWN</div>
                            <ModuleStrip convergence={s} mode="expanded" />
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
