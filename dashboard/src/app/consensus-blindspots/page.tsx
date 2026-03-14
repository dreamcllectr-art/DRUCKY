'use client';

import { useEffect, useState } from 'react';
import { api, ConsensusBlindspotSignal, SentimentCycle } from '@/lib/api';
import Link from 'next/link';

type Tab = 'overview' | 'fat-pitches' | 'crowded' | 'divergences' | 'cycle';

const scoreColor = (v: number) =>
  v >= 70 ? 'text-green-400' : v >= 50 ? 'text-emerald-400' : v >= 30 ? 'text-amber-400' : 'text-red-400';

const gapBadge = (gap: string) => {
  const colors: Record<string, string> = {
    contrarian_bullish: 'bg-green-900/40 text-green-400 border-green-800',
    ahead_of_consensus: 'bg-emerald-900/40 text-emerald-400 border-emerald-800',
    crowded_agreement: 'bg-red-900/40 text-red-400 border-red-800',
    consensus_aligned: 'bg-gray-800/40 text-gray-400 border-gray-700',
    contrarian_bearish_warning: 'bg-amber-900/40 text-amber-400 border-amber-800',
  };
  return colors[gap] || 'bg-gray-800/40 text-gray-400 border-gray-700';
};

const cycleColor = (pos: string | null) => {
  if (!pos) return 'text-gray-400';
  if (pos.includes('FEAR') || pos.includes('PANIC')) return 'text-red-400';
  if (pos.includes('GREED') || pos.includes('EUPHORIA')) return 'text-green-400';
  return 'text-amber-400';
};

export default function ConsensusBlindspotPage() {
  const [tab, setTab] = useState<Tab>('overview');
  const [signals, setSignals] = useState<ConsensusBlindspotSignal[]>([]);
  const [fatPitches, setFatPitches] = useState<ConsensusBlindspotSignal[]>([]);
  const [crowded, setCrowded] = useState<ConsensusBlindspotSignal[]>([]);
  const [divergences, setDivergences] = useState<ConsensusBlindspotSignal[]>([]);
  const [cycle, setCycle] = useState<SentimentCycle | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.consensusBlindspots(0, 100).catch(() => [] as ConsensusBlindspotSignal[]),
      api.fatPitches().catch(() => [] as ConsensusBlindspotSignal[]),
      api.crowdedTrades().catch(() => [] as ConsensusBlindspotSignal[]),
      api.signalDivergences().catch(() => [] as ConsensusBlindspotSignal[]),
      api.sentimentCycle().catch(() => ({ current: null, history: [] }) as SentimentCycle),
    ]).then(([sig, fp, cr, div, cy]) => {
      setSignals(sig);
      setFatPitches(fp);
      setCrowded(cr);
      setDivergences(div);
      setCycle(cy);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-terminal-dim text-sm animate-pulse">Loading consensus blindspot data...</div>
      </div>
    );
  }

  const currentCycle = cycle?.current;

  const tabs: { key: Tab; label: string }[] = [
    { key: 'overview', label: `ALL (${signals.length})` },
    { key: 'fat-pitches', label: `FAT PITCHES (${fatPitches.length})` },
    { key: 'crowded', label: `CROWDED (${crowded.length})` },
    { key: 'divergences', label: `DIVERGENCES (${divergences.length})` },
    { key: 'cycle', label: 'SENTIMENT CYCLE' },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-lg font-display font-bold text-terminal-green tracking-wider">
          CONSENSUS BLINDSPOTS
        </h1>
        <p className="text-[11px] text-terminal-dim mt-1">
          Howard Marks second-level thinking — where do we disagree with the crowd?
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-5 gap-3">
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Market Cycle</div>
          <div className={`text-lg font-bold mt-1 ${cycleColor(currentCycle?.cycle_position ?? null)}`}>
            {currentCycle?.cycle_position ?? 'N/A'}
          </div>
          {currentCycle && (
            <div className="text-[10px] text-gray-500 mt-1">
              score: {currentCycle.cycle_score.toFixed(1)}
            </div>
          )}
        </div>
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Tracked</div>
          <div className="text-xl font-bold text-white mt-1">{signals.length}</div>
        </div>
        <div className="bg-[#111] border border-green-900/50 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Fat Pitches</div>
          <div className="text-xl font-bold text-green-400 mt-1">{fatPitches.length}</div>
        </div>
        <div className="bg-[#111] border border-red-900/50 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Crowded Trades</div>
          <div className="text-xl font-bold text-red-400 mt-1">{crowded.length}</div>
        </div>
        <div className="bg-[#111] border border-amber-900/50 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Divergences</div>
          <div className="text-xl font-bold text-amber-400 mt-1">{divergences.length}</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-800 pb-px">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-[11px] tracking-widest transition-colors ${
              tab === t.key
                ? 'text-terminal-green border-b-2 border-terminal-green'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-gray-500 text-left border-b border-gray-800">
                <th className="pb-2 pr-3">SYMBOL</th>
                <th className="pb-2 pr-3 text-right">CBS SCORE</th>
                <th className="pb-2 pr-3">GAP TYPE</th>
                <th className="pb-2 pr-3 text-right">GAP</th>
                <th className="pb-2 pr-3 text-right">POSITIONING</th>
                <th className="pb-2 pr-3 text-right">DIVERGENCE</th>
                <th className="pb-2 pr-3 text-right">FAT PITCH</th>
                <th className="pb-2 pr-3 text-right">BUY %</th>
                <th className="pb-2 pr-3 text-right">SHORT %</th>
                <th className="pb-2 pr-3 text-right">CONV SCORE</th>
              </tr>
            </thead>
            <tbody>
              {signals.map(s => (
                <tr key={s.symbol} className="border-b border-gray-800/50 hover:bg-white/[0.02]">
                  <td className="py-2 pr-3">
                    <Link href={`/asset/${s.symbol}`} className="text-terminal-green hover:underline font-medium">
                      {s.symbol}
                    </Link>
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono font-bold ${scoreColor(s.cbs_score)}`}>
                    {s.cbs_score.toFixed(1)}
                  </td>
                  <td className="py-2 pr-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] border ${gapBadge(s.gap_type)}`}>
                      {s.gap_type.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${scoreColor(s.consensus_gap_score)}`}>
                    {s.consensus_gap_score.toFixed(1)}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${scoreColor(s.positioning_score)}`}>
                    {s.positioning_score.toFixed(1)}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${scoreColor(s.divergence_score)}`}>
                    {s.divergence_score.toFixed(1)}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono">
                    {s.fat_pitch_count > 0 ? (
                      <span className="text-green-400 font-bold">{s.fat_pitch_count}</span>
                    ) : (
                      <span className="text-gray-600">0</span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-gray-400">
                    {s.analyst_buy_pct != null ? `${s.analyst_buy_pct.toFixed(0)}%` : '—'}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-gray-400">
                    {s.short_interest_pct != null ? `${s.short_interest_pct.toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-gray-400">
                    {s.our_convergence_score != null ? s.our_convergence_score.toFixed(1) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Fat Pitches tab */}
      {tab === 'fat-pitches' && (
        <div className="space-y-2">
          <p className="text-[10px] text-gray-500 mb-3">
            Extreme fear + undervaluation + smart money + insider buying — Marks &amp; Buffett dislocations
          </p>
          {fatPitches.length === 0 && (
            <div className="text-gray-600 text-sm py-8 text-center">No fat pitch setups detected in current cycle</div>
          )}
          {fatPitches.map(s => (
            <div key={s.symbol} className="bg-[#111] border border-green-900/30 rounded-lg p-4 hover:border-green-800/50">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <Link href={`/asset/${s.symbol}`} className="text-terminal-green font-bold text-sm hover:underline">
                    {s.symbol}
                  </Link>
                  <span className={`px-2 py-0.5 rounded text-[10px] border ${gapBadge(s.gap_type)}`}>
                    {s.gap_type.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-[10px] text-gray-500">CBS</span>
                  <span className={`font-mono font-bold ${scoreColor(s.cbs_score)}`}>{s.cbs_score.toFixed(1)}</span>
                  <span className="text-[10px] text-gray-500">FAT PITCH</span>
                  <span className="font-mono font-bold text-green-400">{s.fat_pitch_score.toFixed(1)}</span>
                </div>
              </div>
              <div className="flex gap-6 text-[10px] text-gray-400">
                <span>Conditions: <span className="text-green-400">{s.fat_pitch_conditions ?? 'none'}</span></span>
                <span>Anti-pitch: <span className={s.anti_pitch_count > 0 ? 'text-red-400' : 'text-gray-600'}>{s.anti_pitch_count}</span></span>
                <span>Analyst buy: {s.analyst_buy_pct != null ? `${s.analyst_buy_pct.toFixed(0)}%` : '—'}</span>
                <span>Short: {s.short_interest_pct != null ? `${s.short_interest_pct.toFixed(1)}%` : '—'}</span>
              </div>
              {s.narrative && (
                <div className="text-[10px] text-gray-500 mt-2 italic">{s.narrative}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Crowded tab */}
      {tab === 'crowded' && (
        <div className="space-y-2">
          <p className="text-[10px] text-gray-500 mb-3">
            When everyone agrees, beware — crowded trades carry hidden reversal risk
          </p>
          {crowded.length === 0 && (
            <div className="text-gray-600 text-sm py-8 text-center">No crowded trades detected</div>
          )}
          {crowded.map(s => (
            <div key={s.symbol} className="bg-[#111] border border-red-900/30 rounded-lg p-4 hover:border-red-800/50">
              <div className="flex items-center justify-between mb-2">
                <Link href={`/asset/${s.symbol}`} className="text-terminal-green font-bold text-sm hover:underline">
                  {s.symbol}
                </Link>
                <div className="flex items-center gap-4 text-[11px]">
                  <span className={`font-mono ${scoreColor(s.cbs_score)}`}>{s.cbs_score.toFixed(1)}</span>
                  <span className="text-gray-500">|</span>
                  <span className="text-gray-400">Buy {s.analyst_buy_pct?.toFixed(0) ?? '—'}%</span>
                  <span className="text-gray-400">Inst {s.institutional_pct?.toFixed(0) ?? '—'}%</span>
                  <span className="text-gray-400">Conv {s.our_convergence_score?.toFixed(1) ?? '—'}</span>
                </div>
              </div>
              {s.positioning_flags && (
                <div className="text-[10px] text-red-400">{s.positioning_flags}</div>
              )}
              {s.narrative && (
                <div className="text-[10px] text-gray-500 mt-1 italic">{s.narrative}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Divergences tab */}
      {tab === 'divergences' && (
        <div className="space-y-2">
          <p className="text-[10px] text-gray-500 mb-3">
            Internal signal disagreement — when fundamental and momentum modules diverge, look closer
          </p>
          {divergences.length === 0 && (
            <div className="text-gray-600 text-sm py-8 text-center">No significant divergences</div>
          )}
          {divergences.map(s => (
            <div key={s.symbol} className="bg-[#111] border border-amber-900/30 rounded-lg p-4 hover:border-amber-800/50">
              <div className="flex items-center justify-between mb-2">
                <Link href={`/asset/${s.symbol}`} className="text-terminal-green font-bold text-sm hover:underline">
                  {s.symbol}
                </Link>
                <div className="flex items-center gap-4 text-[11px]">
                  <span className={`font-mono ${scoreColor(s.cbs_score)}`}>{s.cbs_score.toFixed(1)}</span>
                  <span className="text-gray-500">|</span>
                  <span className="text-amber-400 font-mono">
                    {s.divergence_type ?? 'none'} ({s.divergence_magnitude?.toFixed(0) ?? '—'}pt)
                  </span>
                </div>
              </div>
              <div className="flex gap-6 text-[10px] text-gray-400">
                <span>Gap: <span className={s.gap_type === 'contrarian_bullish' || s.gap_type === 'ahead_of_consensus' ? 'text-green-400' : 'text-gray-400'}>{s.gap_type.replace(/_/g, ' ')}</span></span>
                <span>Conv score: {s.our_convergence_score?.toFixed(1) ?? '—'}</span>
              </div>
              {s.narrative && (
                <div className="text-[10px] text-gray-500 mt-1 italic">{s.narrative}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Sentiment Cycle tab */}
      {tab === 'cycle' && cycle && (
        <div className="space-y-6">
          {/* Current cycle position */}
          {currentCycle && (
            <div className="bg-[#111] border border-gray-800 rounded-lg p-6">
              <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">CURRENT MARKET SENTIMENT</div>
              <div className={`text-3xl font-bold font-display ${cycleColor(currentCycle.cycle_position)}`}>
                {currentCycle.cycle_position}
              </div>
              <div className="text-gray-400 font-mono mt-2">
                Cycle Score: <span className={cycleColor(currentCycle.cycle_position)}>{currentCycle.cycle_score.toFixed(1)}</span>
              </div>
              {currentCycle.narrative && (
                <div className="text-[11px] text-gray-500 mt-3 leading-relaxed">{currentCycle.narrative}</div>
              )}
            </div>
          )}

          {/* History */}
          <div>
            <h3 className="text-xs text-gray-400 tracking-wider font-bold mb-3">CYCLE HISTORY</h3>
            <div className="space-y-1">
              {cycle.history.map((h, i) => (
                <div key={i} className="flex items-center gap-4 py-2 px-3 bg-[#111] rounded border border-gray-800/50">
                  <span className="text-gray-500 font-mono w-24">{h.date}</span>
                  <span className={`font-bold w-28 ${cycleColor(h.cycle_position)}`}>{h.cycle_position}</span>
                  <span className={`font-mono w-16 text-right ${cycleColor(h.cycle_position)}`}>
                    {h.cycle_score.toFixed(1)}
                  </span>
                  <span className="text-gray-600 text-[10px] flex-1 truncate">{h.narrative ?? ''}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
