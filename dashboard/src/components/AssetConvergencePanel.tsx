'use client';

import { useState } from 'react';
import type { ConvergenceSignal } from '@/lib/api';
import { MODULES, scoreColor, scoreBg } from '@/lib/modules';

interface ConvergencePanelProps {
  conv: ConvergenceSignal;
  signalHistory?: Array<{
    date: string;
    signal: string;
    composite_score: number;
    convergence_score?: number;
    conviction_level?: string;
    module_count?: number;
  }>;
}

const SIGNAL_COLORS: Record<string, string> = {
  'STRONG BUY': '#059669',
  'BUY': '#059669',
  'NEUTRAL': '#d97706',
  'SELL': '#e11d48',
  'STRONG SELL': '#e11d48',
};

function ScorePill({ value }: { value: number | null | undefined }) {
  const v = value ?? null;
  if (v === null) return <span className="text-[9px] font-mono text-gray-300">—</span>;
  return (
    <span
      className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded"
      style={{ color: scoreColor(v), background: scoreBg(v) }}
    >
      {v.toFixed(0)}
    </span>
  );
}

export function AssetConvergencePanel({ conv, signalHistory = [] }: ConvergencePanelProps) {
  const [tab, setTab] = useState<'modules' | 'history'>('modules');

  // All modules sorted by score desc (active ones first)
  const activeModules = MODULES.filter(m => {
    const val = (conv as any)[m.key] as number | null;
    return val != null && val > 0;
  }).sort((a, b) => ((conv as any)[b.key] ?? 0) - ((conv as any)[a.key] ?? 0));

  const inactiveModules = MODULES.filter(m => {
    const val = (conv as any)[m.key] as number | null;
    return val == null || val === 0;
  });

  const bullishCount = activeModules.filter(m => ((conv as any)[m.key] ?? 0) >= 50).length;
  const bearishCount = activeModules.filter(m => ((conv as any)[m.key] ?? 0) < 25).length;

  return (
    <div className="panel p-5">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <span className="text-[10px] text-gray-500 tracking-widest uppercase">Signal Audit</span>
          {conv.narrative && (
            <p className="text-[11px] text-gray-600 leading-relaxed mt-1 max-w-2xl">{conv.narrative}</p>
          )}
        </div>
        <div className="text-right">
          <div className="text-2xl font-display font-bold" style={{ color: scoreColor(conv.convergence_score) }}>
            {conv.convergence_score?.toFixed(1)}
          </div>
          <div className="text-[9px] text-gray-500 tracking-wider">CONVERGENCE</div>
          <div className="text-[9px] mt-0.5">
            <span className="text-emerald-600 font-bold">{bullishCount} bullish</span>
            <span className="text-gray-400 mx-1">·</span>
            <span className="text-rose-600 font-bold">{bearishCount} bearish</span>
            <span className="text-gray-400 mx-1">·</span>
            <span className="text-gray-500">{inactiveModules.length} no data</span>
          </div>
        </div>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-3 mb-4 border-b border-gray-100 pb-2">
        {(['modules', 'history'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-[9px] tracking-widest uppercase font-bold transition-colors ${
              tab === t ? 'text-gray-900 border-b-2 border-gray-900 pb-1 -mb-[9px]' : 'text-gray-400 hover:text-gray-600'
            }`}
          >
            {t === 'modules' ? `All Modules (${activeModules.length})` : `Signal History (${signalHistory.length})`}
          </button>
        ))}
      </div>

      {tab === 'modules' && (
        <div>
          {/* Active modules table */}
          <div className="space-y-0.5">
            <div className="grid grid-cols-[1fr_60px_60px_auto] gap-2 text-[8px] text-gray-400 tracking-widest uppercase pb-1 border-b border-gray-100">
              <span>Module</span>
              <span className="text-right">Score</span>
              <span className="text-right">Weight</span>
              <span className="text-right">Verdict</span>
            </div>
            {activeModules.map(m => {
              const val = (conv as any)[m.key] as number;
              const verdict = val >= 70 ? 'STRONG' : val >= 50 ? 'BULLISH' : val >= 25 ? 'NEUTRAL' : 'BEARISH';
              const verdictColor = val >= 50 ? '#059669' : val >= 25 ? '#d97706' : '#e11d48';
              return (
                <div
                  key={m.key}
                  className="grid grid-cols-[1fr_60px_60px_auto] gap-2 items-center py-1.5 px-2 rounded hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <div
                      className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{ background: scoreColor(val) }}
                    />
                    <span className="text-[10px] text-gray-700">{m.label}</span>
                  </div>
                  <div className="text-right"><ScorePill value={val} /></div>
                  <div className="text-right text-[9px] text-gray-400">{m.weight}%</div>
                  <div
                    className="text-right text-[8px] font-bold tracking-wider w-14"
                    style={{ color: verdictColor }}
                  >
                    {verdict}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Inactive modules */}
          {inactiveModules.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              <div className="text-[8px] text-gray-400 tracking-widest uppercase mb-2">No Data Yet</div>
              <div className="flex flex-wrap gap-1">
                {inactiveModules.map(m => (
                  <span key={m.key} className="text-[8px] text-gray-400 bg-gray-50 px-2 py-0.5 rounded">
                    {m.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Formula */}
          <div className="mt-4 pt-3 border-t border-gray-100 bg-gray-50 rounded-lg p-3">
            <div className="text-[8px] text-gray-400 tracking-widest uppercase mb-2">Decision Formula</div>
            <div className="text-[10px] text-gray-600 font-mono leading-relaxed">
              convergence_score = Σ(module_score × weight) / Σ(active_weights)<br />
              <span className="text-gray-400">
                Active: {activeModules.length}/{MODULES.length} modules ·{' '}
                Conviction: {conv.conviction_level?.toUpperCase()} ·{' '}
                Module count: {conv.module_count}
              </span>
            </div>
          </div>
        </div>
      )}

      {tab === 'history' && (
        <div>
          {signalHistory.length === 0 ? (
            <div className="text-[10px] text-gray-400 py-4 text-center">No signal history available</div>
          ) : (
            <div className="space-y-0.5">
              <div className="grid grid-cols-[80px_80px_70px_70px_auto] gap-2 text-[8px] text-gray-400 tracking-widest uppercase pb-1 border-b border-gray-100">
                <span>Date</span>
                <span>Signal</span>
                <span className="text-right">Score</span>
                <span className="text-right">Conv.</span>
                <span className="text-right">Modules</span>
              </div>
              {signalHistory.map((row, i) => (
                <div
                  key={i}
                  className="grid grid-cols-[80px_80px_70px_70px_auto] gap-2 items-center py-1.5 px-1 rounded hover:bg-gray-50 text-[10px]"
                >
                  <span className="text-gray-500 font-mono">{row.date}</span>
                  <span
                    className="font-bold text-[9px] tracking-wider"
                    style={{ color: SIGNAL_COLORS[row.signal] ?? '#9ca3af' }}
                  >
                    {row.signal}
                  </span>
                  <span className="text-right font-mono text-gray-700">
                    {row.composite_score?.toFixed(1)}
                  </span>
                  <span className="text-right font-mono text-gray-500">
                    {row.convergence_score?.toFixed(1) ?? '—'}
                  </span>
                  <span className="text-right text-gray-400">
                    {row.module_count ?? '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
