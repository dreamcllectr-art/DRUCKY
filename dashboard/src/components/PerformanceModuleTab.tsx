'use client';

import { useState } from 'react';
import type { ModulePerformance } from '@/lib/api';

export function PerformanceModuleTab({ modules }: { modules: ModulePerformance[] }) {
  const [sortKey, setSortKey] = useState<string>('win_rate');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const sorted = [...modules].sort((a, b) => {
    const av = (a as Record<string, number | null>)[sortKey] ?? -999;
    const bv = (b as Record<string, number | null>)[sortKey] ?? -999;
    return sortDir === 'desc' ? (bv as number) - (av as number) : (av as number) - (bv as number);
  });

  const handleSort = (key: string) => {
    if (sortKey === key) setSortDir(sortDir === 'desc' ? 'asc' : 'desc');
    else { setSortKey(key); setSortDir('desc'); }
  };

  const SortHeader = ({ k, label }: { k: string; label: string }) => (
    <th className="text-right pb-2 cursor-pointer hover:text-emerald-600 transition-colors" onClick={() => handleSort(k)}>
      {label} {sortKey === k ? (sortDir === 'desc' ? '\u25BC' : '\u25B2') : ''}
    </th>
  );

  return (
    <div className="panel p-4">
      <h3 className="text-xs text-gray-500 tracking-[0.2em] uppercase mb-4">MODULE PERFORMANCE LEADERBOARD</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-gray-500 tracking-wider">
              <th className="text-left pb-2">MODULE</th>
              <SortHeader k="win_rate" label="WIN%" />
              <SortHeader k="avg_return_20d" label="AVG 20D" />
              <SortHeader k="sharpe_ratio" label="SHARPE" />
              <th className="text-right pb-2">N</th>
              <th className="text-right pb-2">STATIC W</th>
              <th className="text-right pb-2">ADAPTIVE W</th>
              <th className="text-right pb-2">DELTA</th>
              <th className="text-right pb-2">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((m) => {
              const wrColor = m.win_rate >= 55 ? 'text-[#059669]' : m.win_rate >= 45 ? 'text-[#d97706]' : 'text-[#e11d48]';
              const avgRet = m.avg_return_20d ?? m.avg_return_30d ?? m.avg_return_5d;
              const retColor = avgRet && avgRet > 0 ? 'text-[#059669]' : 'text-[#e11d48]';
              const delta = m.adaptive_weight != null ? m.adaptive_weight - m.static_weight : null;
              const deltaColor = delta != null ? (delta > 0 ? 'text-[#059669]' : delta < 0 ? 'text-[#e11d48]' : 'text-gray-500') : 'text-gray-500';

              return (
                <tr key={m.module_name} className="border-t border-gray-200 hover:bg-gray-200/30">
                  <td className="py-2 font-display text-gray-700">{m.module_name}</td>
                  <td className={`py-2 text-right font-mono ${wrColor}`}>{m.win_rate.toFixed(1)}%</td>
                  <td className={`py-2 text-right font-mono ${retColor}`}>
                    {avgRet != null ? `${avgRet > 0 ? '+' : ''}${avgRet.toFixed(2)}%` : '\u2014'}
                  </td>
                  <td className="py-2 text-right font-mono text-gray-700">{m.sharpe_ratio != null ? m.sharpe_ratio.toFixed(2) : '\u2014'}</td>
                  <td className="py-2 text-right font-mono text-gray-500">{m.observation_count ?? m.total_signals}</td>
                  <td className="py-2 text-right font-mono text-gray-500">{(m.static_weight * 100).toFixed(0)}%</td>
                  <td className="py-2 text-right font-mono text-gray-700">{m.adaptive_weight != null ? `${(m.adaptive_weight * 100).toFixed(1)}%` : '\u2014'}</td>
                  <td className={`py-2 text-right font-mono ${deltaColor}`}>{delta != null ? `${delta > 0 ? '+' : ''}${(delta * 100).toFixed(1)}%` : '\u2014'}</td>
                  <td className="py-2 text-right font-mono text-gray-500 text-[11px]">
                    {m.confidence_interval_low != null && m.confidence_interval_high != null
                      ? `[${m.confidence_interval_low > 0 ? '+' : ''}${m.confidence_interval_low.toFixed(1)}, +${m.confidence_interval_high.toFixed(1)}]`
                      : '\u2014'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
