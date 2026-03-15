'use client';

import { useMemo } from 'react';
import type { PatternScanResult, CompressionRow } from '@/lib/api';
import { WYCKOFF_COLORS, ScorePill } from '@/components/PatternsShared';
import { cs } from '@/lib/styles';

interface CyclesTabProps {
  patterns: PatternScanResult[];
  compression: CompressionRow[];
}

export function PatternsCyclesTab({ patterns, compression }: CyclesTabProps) {
  const phaseCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    patterns.forEach((p) => {
      const phase = p.wyckoff_phase || 'unknown';
      counts[phase] = (counts[phase] || 0) + 1;
    });
    return counts;
  }, [patterns]);

  const total = patterns.length || 1;

  const volCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    patterns.forEach((p) => {
      const regime = p.vol_regime || 'normal';
      counts[regime] = (counts[regime] || 0) + 1;
    });
    return counts;
  }, [patterns]);

  const nearEarnings = patterns
    .filter((p) => p.earnings_days_to_next != null && p.earnings_days_to_next <= 14)
    .sort((a, b) => (a.earnings_days_to_next || 99) - (b.earnings_days_to_next || 99));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        {/* Wyckoff Phase Distribution */}
        <div className="bg-white border border-gray-200 rounded p-4">
          <div className="text-[10px] text-gray-500 tracking-widest mb-3">
            WYCKOFF PHASE DISTRIBUTION
          </div>
          <div className="space-y-2">
            {['accumulation', 'markup', 'distribution', 'markdown'].map((phase) => {
              const count = phaseCounts[phase] || 0;
              const pct = (count / total) * 100;
              return (
                <div key={phase} className="flex items-center gap-3">
                  <span className={`text-xs w-28 ${WYCKOFF_COLORS[phase]}`}>
                    {phase.toUpperCase()}
                  </span>
                  <div className="flex-1 bg-gray-50 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        phase === 'accumulation'
                          ? 'bg-emerald-600/60'
                          : phase === 'markup'
                          ? 'bg-cyan-400/60'
                          : phase === 'distribution'
                          ? 'bg-amber-400/60'
                          : 'bg-red-400/60'
                      }`}
                      {...cs({ width: `${pct}%` })}
                    />
                  </div>
                  <span className="text-xs text-gray-500 w-12 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Vol Regime Distribution */}
        <div className="bg-white border border-gray-200 rounded p-4">
          <div className="text-[10px] text-gray-500 tracking-widest mb-3">
            VOLATILITY REGIME DISTRIBUTION
          </div>
          <div className="space-y-2">
            {['low', 'normal', 'high'].map((regime) => {
              const count = volCounts[regime] || 0;
              const pct = (count / total) * 100;
              return (
                <div key={regime} className="flex items-center gap-3">
                  <span className={`text-xs w-20 ${
                    regime === 'low' ? 'text-emerald-600' : regime === 'high' ? 'text-red-400' : 'text-gray-500'
                  }`}>
                    {regime.toUpperCase()}
                  </span>
                  <div className="flex-1 bg-gray-50 rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        regime === 'low'
                          ? 'bg-emerald-600/60'
                          : regime === 'high'
                          ? 'bg-red-400/60'
                          : 'bg-white/20'
                      }`}
                      {...cs({ width: `${pct}%` })}
                    />
                  </div>
                  <span className="text-xs text-gray-500 w-12 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Compression / Squeeze Setups */}
      {compression.length > 0 && (
        <div className="bg-white border border-gray-200 rounded overflow-hidden">
          <div className="p-3 border-b border-gray-200">
            <div className="text-[10px] text-gray-500 tracking-widest">
              VOLATILITY COMPRESSION SETUPS ({compression.length})
            </div>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-[10px] tracking-widest">
                <th className="text-left p-2">SYMBOL</th>
                <th className="text-left p-2">SECTOR</th>
                <th className="text-right p-2">COMPRESS</th>
                <th className="text-right p-2">HURST</th>
                <th className="text-right p-2">MR</th>
                <th className="text-right p-2">MOM</th>
                <th className="text-center p-2">PHASE</th>
                <th className="text-center p-2">SQ</th>
                <th className="text-right p-2">IV RANK</th>
              </tr>
            </thead>
            <tbody>
              {compression.slice(0, 30).map((c) => (
                <tr key={c.symbol} className="border-b border-gray-200/50 hover:bg-white/[0.02]">
                  <td className="p-2 font-mono text-gray-900">{c.symbol}</td>
                  <td className="p-2 text-gray-500">{c.sector || '--'}</td>
                  <td className="p-2 text-right"><ScorePill value={c.compression_score} /></td>
                  <td className="p-2 text-right font-mono">{c.hurst_exponent?.toFixed(3)}</td>
                  <td className="p-2 text-right"><ScorePill value={c.mr_score} /></td>
                  <td className="p-2 text-right"><ScorePill value={c.momentum_score} /></td>
                  <td className="p-2 text-center">
                    <span className={WYCKOFF_COLORS[c.wyckoff_phase]}>
                      {c.wyckoff_phase?.substring(0, 5).toUpperCase()}
                    </span>
                  </td>
                  <td className="p-2 text-center">
                    {c.squeeze_active ? <span className="text-cyan-400">SQ</span> : '--'}
                  </td>
                  <td className="p-2 text-right"><ScorePill value={c.iv_rank} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Earnings Proximity */}
      {nearEarnings.length > 0 && (
        <div className="bg-white border border-gray-200 rounded overflow-hidden">
          <div className="p-3 border-b border-gray-200">
            <div className="text-[10px] text-gray-500 tracking-widest">
              EARNINGS WITHIN 14 DAYS ({nearEarnings.length})
            </div>
          </div>
          <div className="flex flex-wrap gap-2 p-3">
            {nearEarnings.slice(0, 30).map((p) => (
              <div
                key={p.symbol}
                className="px-2 py-1 rounded border border-amber-400/30 bg-amber-400/10 text-[10px] font-mono"
              >
                <span className="text-gray-900">{p.symbol}</span>
                <span className="text-amber-400 ml-1">{p.earnings_days_to_next}d</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
