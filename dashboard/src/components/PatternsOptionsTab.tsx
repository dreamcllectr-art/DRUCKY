'use client';

import { useState } from 'react';
import type { OptionsIntelResult, UnusualActivityRow, ExpectedMoveRow, DealerExposureRow } from '@/lib/api';
import { QUADRANT_BG, WYCKOFF_COLORS, DEALER_COLORS, ScorePill, Badge } from '@/components/PatternsShared';

interface OptionsTabProps {
  options: OptionsIntelResult[];
  unusual: UnusualActivityRow[];
  expectedMoves: ExpectedMoveRow[];
  dealers: DealerExposureRow[];
}

export function PatternsOptionsTab({ options, unusual, expectedMoves, dealers }: OptionsTabProps) {
  const [subTab, setSubTab] = useState<'moves' | 'unusual' | 'dealer' | 'iv'>('moves');

  return (
    <div className="space-y-4">
      {/* Sub-tabs */}
      <div className="flex gap-2">
        {(['moves', 'unusual', 'dealer', 'iv'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setSubTab(t)}
            className={`text-[10px] tracking-widest px-3 py-1.5 rounded border transition-all ${
              subTab === t
                ? 'text-emerald-600 border-emerald-600/40 bg-emerald-600/10'
                : 'text-gray-500 border-gray-200 hover:text-gray-700'
            }`}
          >
            {t === 'moves' ? 'EXPECTED MOVES' : t === 'unusual' ? 'UNUSUAL FLOW' : t === 'dealer' ? 'DEALER GEX' : 'IV RANK'}
          </button>
        ))}
      </div>

      {/* Expected Moves */}
      {subTab === 'moves' && (
        <div className="bg-white border border-gray-200 rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-[10px] tracking-widest">
                <th className="text-left p-3">SYMBOL</th>
                <th className="text-left p-3">SECTOR</th>
                <th className="text-right p-3">EXP MOVE %</th>
                <th className="text-right p-3">STRADDLE</th>
                <th className="text-right p-3">ATM IV</th>
                <th className="text-right p-3">IV RANK</th>
                <th className="text-center p-3">DEALER</th>
                <th className="text-center p-3">PHASE</th>
                <th className="text-center p-3">SQ</th>
              </tr>
            </thead>
            <tbody>
              {expectedMoves.slice(0, 50).map((m) => (
                <tr key={m.symbol} className="border-b border-gray-200/50 hover:bg-white/[0.02]">
                  <td className="p-3 font-mono text-gray-900">{m.symbol}</td>
                  <td className="p-3 text-gray-500">{m.sector || '--'}</td>
                  <td className="p-3 text-right font-mono text-amber-400">
                    {'\u00B1'}{m.expected_move_pct?.toFixed(1)}%
                  </td>
                  <td className="p-3 text-right font-mono">${m.straddle_cost?.toFixed(2)}</td>
                  <td className="p-3 text-right font-mono">{(m.atm_iv ? m.atm_iv * 100 : 0).toFixed(0)}%</td>
                  <td className="p-3 text-right"><ScorePill value={m.iv_rank} /></td>
                  <td className="p-3 text-center">
                    <span className={DEALER_COLORS[m.dealer_regime || 'neutral']}>
                      {m.dealer_regime?.toUpperCase() || '--'}
                    </span>
                  </td>
                  <td className="p-3 text-center">
                    <span className={WYCKOFF_COLORS[m.wyckoff_phase || 'unknown']}>
                      {m.wyckoff_phase?.substring(0, 5).toUpperCase() || '--'}
                    </span>
                  </td>
                  <td className="p-3 text-center">
                    {m.squeeze_active ? <span className="text-cyan-400">SQ</span> : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Unusual Activity */}
      {subTab === 'unusual' && (
        <div className="bg-white border border-gray-200 rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-[10px] tracking-widest">
                <th className="text-left p-3">SYMBOL</th>
                <th className="text-left p-3">SECTOR</th>
                <th className="text-right p-3"># SIGNALS</th>
                <th className="text-center p-3">DIRECTION</th>
                <th className="text-right p-3">IV RANK</th>
                <th className="text-right p-3">EXP MOVE</th>
                <th className="text-center p-3">DEALER</th>
                <th className="text-right p-3">OPT SCORE</th>
              </tr>
            </thead>
            <tbody>
              {unusual.map((u) => (
                <tr key={u.symbol} className="border-b border-gray-200/50 hover:bg-white/[0.02]">
                  <td className="p-3 font-mono text-gray-900">{u.symbol}</td>
                  <td className="p-3 text-gray-500">{u.sector || '--'}</td>
                  <td className="p-3 text-right font-mono text-amber-400">{u.unusual_activity_count}</td>
                  <td className="p-3 text-center">
                    <Badge
                      text={u.unusual_direction_bias || 'mixed'}
                      color={
                        u.unusual_direction_bias === 'bullish'
                          ? QUADRANT_BG.leading
                          : u.unusual_direction_bias === 'bearish'
                          ? QUADRANT_BG.lagging
                          : QUADRANT_BG.neutral
                      }
                    />
                  </td>
                  <td className="p-3 text-right"><ScorePill value={u.iv_rank} /></td>
                  <td className="p-3 text-right font-mono">
                    {u.expected_move_pct ? `\u00B1${u.expected_move_pct.toFixed(1)}%` : '--'}
                  </td>
                  <td className="p-3 text-center">
                    <span className={DEALER_COLORS[u.dealer_regime || 'neutral']}>
                      {u.dealer_regime?.toUpperCase() || '--'}
                    </span>
                  </td>
                  <td className="p-3 text-right"><ScorePill value={u.options_score} /></td>
                </tr>
              ))}
              {unusual.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-4 text-center text-gray-500">
                    No unusual options activity detected
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Dealer Exposure */}
      {subTab === 'dealer' && (
        <div className="bg-white border border-gray-200 rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 text-[10px] tracking-widest">
                <th className="text-left p-3">SYMBOL</th>
                <th className="text-center p-3">REGIME</th>
                <th className="text-right p-3">NET GEX ($)</th>
                <th className="text-right p-3">GAMMA FLIP</th>
                <th className="text-right p-3">MAX PAIN</th>
                <th className="text-right p-3">PUT WALL</th>
                <th className="text-right p-3">CALL WALL</th>
                <th className="text-right p-3">OPT SCORE</th>
              </tr>
            </thead>
            <tbody>
              {dealers.slice(0, 50).map((d) => (
                <tr key={d.symbol} className="border-b border-gray-200/50 hover:bg-white/[0.02]">
                  <td className="p-3 font-mono text-gray-900">{d.symbol}</td>
                  <td className="p-3 text-center">
                    <Badge
                      text={d.dealer_regime}
                      color={
                        d.dealer_regime === 'amplifying'
                          ? QUADRANT_BG.lagging
                          : d.dealer_regime === 'pinning'
                          ? QUADRANT_BG.weakening
                          : QUADRANT_BG.neutral
                      }
                    />
                  </td>
                  <td className="p-3 text-right font-mono">
                    {d.net_gex ? (d.net_gex > 0 ? '+' : '') + (d.net_gex / 1e6).toFixed(1) + 'M' : '--'}
                  </td>
                  <td className="p-3 text-right font-mono">${d.gamma_flip_level?.toFixed(0) || '--'}</td>
                  <td className="p-3 text-right font-mono">${d.max_pain?.toFixed(0) || '--'}</td>
                  <td className="p-3 text-right font-mono text-red-400">${d.put_wall?.toFixed(0) || '--'}</td>
                  <td className="p-3 text-right font-mono text-emerald-600">${d.call_wall?.toFixed(0) || '--'}</td>
                  <td className="p-3 text-right"><ScorePill value={d.options_score} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* IV Rank Heatmap */}
      {subTab === 'iv' && (
        <div className="space-y-3">
          <div className="text-[10px] text-gray-500 tracking-widest">
            IV RANK HEATMAP -- GREEN = LOW IV (CHEAP OPTIONS) | RED = HIGH IV (EXPENSIVE)
          </div>
          <div className="flex flex-wrap gap-1">
            {options
              .filter((o) => o.iv_rank != null)
              .sort((a, b) => (b.iv_rank || 0) - (a.iv_rank || 0))
              .map((o) => {
                const rank = o.iv_rank || 0;
                const bg =
                  rank > 80
                    ? 'bg-red-500/30 border-red-500/50'
                    : rank > 60
                    ? 'bg-amber-500/20 border-amber-500/40'
                    : rank > 40
                    ? 'bg-gray-50 border-white/20'
                    : rank > 20
                    ? 'bg-cyan-500/15 border-cyan-500/30'
                    : 'bg-emerald-600/20 border-emerald-600/40';

                return (
                  <div
                    key={o.symbol}
                    className={`px-2 py-1 rounded border text-[9px] font-mono ${bg}`}
                    title={`${o.symbol}: IV Rank ${rank.toFixed(0)}, IV ${((o.atm_iv || 0) * 100).toFixed(0)}%`}
                  >
                    <div className="text-gray-900">{o.symbol}</div>
                    <div className="text-gray-500">{rank.toFixed(0)}</div>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}
