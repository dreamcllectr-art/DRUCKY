'use client';

import React from 'react';
import type { PerformanceSummary } from '@/lib/api';
import { PerformanceSufficiencyBadge } from '@/components/PerformanceShared';
import { fg } from '@/lib/styles';

function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  const colorClass = color === '#d97706' ? 'text-[#d97706]' : 'text-[#059669]';
  return (
    <div className="panel p-4">
      <div className="text-[10px] text-gray-500 tracking-[0.2em] uppercase mb-1">{label}</div>
      <div className={`text-2xl font-display font-bold ${color ? '' : 'text-[#059669]'}`} {...(color ? fg(color) : {})}>{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-1">{sub}</div>}
    </div>
  );
}

function colorForValue(value: number | undefined, thresholds: { high: number; mid: number }) {
  if (value === undefined) return 'text-gray-500';
  if (value >= thresholds.high) return 'text-[#059669]';
  if (value >= thresholds.mid) return 'text-[#d97706]';
  return 'text-[#e11d48]';
}

function returnColor(value: number | undefined) {
  if (value === undefined) return 'text-gray-500';
  return value > 0 ? 'text-[#059669]' : 'text-[#e11d48]';
}

export function PerformanceOverviewTab({ summary }: { summary: PerformanceSummary }) {
  const resolved = summary.resolved_by_window;
  const bestWindow = resolved['5d'] > 0 ? '5d' : resolved['20d'] > 0 ? '20d' : '30d';

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Signals" value={summary.total_signals.toLocaleString()} sub={`Since ${summary.first_signal_date || '\u2014'}`} />
        <StatCard label="Track Record" value={`${summary.days_running}d`} sub={`Since ${summary.first_signal_date || 'inception'}`} />
        <StatCard label={`Resolved (${bestWindow})`} value={`${resolved[bestWindow] || 0}`} sub={`Of ${summary.total_signals} total`} />
        <StatCard label="Optimizer Status" value={summary.data_sufficient ? 'ACTIVE' : 'CALIBRATING'} color={summary.data_sufficient ? '#059669' : '#d97706'} sub={summary.data_sufficient ? (summary.latest_optimizer?.action || 'Weights optimized') : `Requires ${Math.max(30 - summary.days_running, 0)} more days`} />
      </div>
      <div className="panel p-4">
        <h3 className="text-xs text-gray-500 tracking-[0.2em] uppercase mb-4">WIN RATE BY CONVICTION LEVEL</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] text-gray-500 tracking-wider">
                <th className="text-left pb-2">LEVEL</th>
                <th className="text-right pb-2">5D WIN%</th><th className="text-right pb-2">5D AVG</th>
                <th className="text-right pb-2">20D WIN%</th><th className="text-right pb-2">20D AVG</th>
                <th className="text-right pb-2">30D WIN%</th><th className="text-right pb-2">30D AVG</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_conviction.map((c) => (
                <tr key={c.level} className="border-t border-gray-200">
                  <td className="py-2 font-display font-bold text-emerald-600">{c.level}</td>
                  {[5, 20, 30].map((d) => {
                    const wr = (c as unknown as Record<string, number | undefined>)[`win_rate_${d}d`];
                    const ar = (c as unknown as Record<string, number | undefined>)[`avg_return_${d}d`];
                    return (
                      <React.Fragment key={d}>
                        <td className={`py-2 text-right font-mono ${colorForValue(wr, { high: 55, mid: 45 })}`}>
                          {wr !== undefined ? `${wr.toFixed(1)}%` : '\u2014'}
                        </td>
                        <td className={`py-2 text-right font-mono ${returnColor(ar)}`}>
                          {ar !== undefined ? `${ar > 0 ? '+' : ''}${ar.toFixed(2)}%` : '\u2014'}
                        </td>
                      </React.Fragment>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="panel p-4">
        <h3 className="text-xs text-gray-500 tracking-[0.2em] uppercase mb-3">RESOLVED SIGNALS BY HOLDING PERIOD</h3>
        <div className="grid grid-cols-7 gap-2">
          {Object.entries(resolved).map(([window, count]) => (
            <div key={window} className="text-center">
              <div className="text-lg font-display font-bold text-emerald-600">{count}</div>
              <div className="text-[10px] text-gray-500">{window}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
