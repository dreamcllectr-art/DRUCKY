'use client';
import { useEffect, useState } from 'react';
import { api, ConsensusBlindspotSignal, SentimentCycle } from '@/lib/api';
import Link from 'next/link';

const scoreColor = (v: number) => v >= 70 ? 'text-green-400' : v >= 50 ? 'text-emerald-400' : v >= 30 ? 'text-amber-400' : 'text-red-400';
const gapBadge = (gap: string) => ({ contrarian_bullish: 'bg-green-900/40 text-green-400 border-green-800', ahead_of_consensus: 'bg-emerald-900/40 text-emerald-400 border-emerald-800', crowded_agreement: 'bg-red-900/40 text-red-400 border-red-800', contrarian_bearish_warning: 'bg-amber-900/40 text-amber-400 border-amber-800' }[gap] || 'bg-white/40 text-gray-500 border-gray-200');

export default function ConsensusBlindspotTab() {
  const [signals, setSignals] = useState<ConsensusBlindspotSignal[]>([]);
  const [fatPitches, setFatPitches] = useState<ConsensusBlindspotSignal[]>([]);
  const [cycle, setCycle] = useState<SentimentCycle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'overview' | 'fat-pitches' | 'cycle'>('overview');

  useEffect(() => {
    Promise.all([
      api.consensusBlindspots(0, 100),
      api.fatPitches(),
      api.sentimentCycle(),
    ]).then(([sig, fp, cy]) => { setSignals(sig as ConsensusBlindspotSignal[]); setFatPitches(fp as ConsensusBlindspotSignal[]); setCycle(cy as SentimentCycle); }).catch((e) => setError(e.message || 'Failed to load blindspot data')).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading blindspots...</div>;

  const cycleColor = (pos: string | null) => !pos ? 'text-gray-500' : pos.includes('FEAR') ? 'text-red-400' : pos.includes('GREED') ? 'text-green-400' : 'text-amber-400';

  return (
    <div className="space-y-4">
      {error && (
        <div className="panel p-4 border-rose-200 bg-rose-50">
          <div className="text-rose-600 text-sm font-bold mb-1">Failed to load data</div>
          <p className="text-[11px] text-gray-500">{error}</p>
        </div>
      )}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-white border border-gray-200 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase tracking-wider">Cycle</div><div className={`text-lg font-bold mt-1 ${cycleColor(cycle?.current?.cycle_position ?? null)}`}>{cycle?.current?.cycle_position ?? 'N/A'}</div></div>
        <div className="bg-white border border-gray-200 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase tracking-wider">Tracked</div><div className="text-xl font-bold text-gray-900 mt-1">{signals.length}</div></div>
        <div className="bg-white border border-green-900/50 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase tracking-wider">Fat Pitches</div><div className="text-xl font-bold text-green-400 mt-1">{fatPitches.length}</div></div>
        <div className="bg-white border border-red-900/50 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase tracking-wider">Crowded</div><div className="text-xl font-bold text-red-400 mt-1">{signals.filter(s => s.gap_type === 'crowded_agreement').length}</div></div>
      </div>
      <div className="flex gap-1 border-b border-gray-200">
        {[{ key: 'overview' as const, label: `ALL (${signals.length})` }, { key: 'fat-pitches' as const, label: `FAT PITCHES (${fatPitches.length})` }, { key: 'cycle' as const, label: 'CYCLE' }].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} className={`px-4 py-2 text-[11px] tracking-widest ${tab === t.key ? 'text-emerald-600 border-b-2 border-emerald-600' : 'text-gray-500 hover:text-gray-600'}`}>{t.label}</button>
        ))}
      </div>
      {tab === 'overview' && (
        <div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="text-gray-500 text-left border-b border-gray-200"><th className="pb-2 pr-3">SYMBOL</th><th className="pb-2 pr-3 text-right">CBS</th><th className="pb-2 pr-3">GAP</th><th className="pb-2 pr-3 text-right">FAT PITCH</th><th className="pb-2 pr-3 text-right">CONV</th></tr></thead>
          <tbody>{signals.map(s => (
            <tr key={s.symbol} className="border-b border-gray-200/50 hover:bg-white/[0.02]">
              <td className="py-2 pr-3"><Link href={`/asset/${s.symbol}`} className="text-emerald-600 hover:underline font-medium">{s.symbol}</Link></td>
              <td className={`py-2 pr-3 text-right font-mono font-bold ${scoreColor(s.cbs_score)}`}>{s.cbs_score.toFixed(1)}</td>
              <td className="py-2 pr-3"><span className={`px-2 py-0.5 rounded text-[10px] border ${gapBadge(s.gap_type)}`}>{s.gap_type.replace(/_/g, ' ')}</span></td>
              <td className="py-2 pr-3 text-right font-mono">{s.fat_pitch_count > 0 ? <span className="text-green-400 font-bold">{s.fat_pitch_count}</span> : <span className="text-gray-600">0</span>}</td>
              <td className="py-2 pr-3 text-right font-mono text-gray-500">{s.our_convergence_score?.toFixed(1) ?? '--'}</td>
            </tr>
          ))}</tbody></table></div>
      )}
      {tab === 'fat-pitches' && (
        <div className="space-y-2">
          {fatPitches.length === 0 && <div className="text-gray-600 text-sm py-8 text-center">No fat pitches</div>}
          {fatPitches.map(s => (
            <div key={s.symbol} className="bg-white border border-green-900/30 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <Link href={`/asset/${s.symbol}`} className="text-emerald-600 font-bold text-sm hover:underline">{s.symbol}</Link>
                <span className={`font-mono font-bold ${scoreColor(s.cbs_score)}`}>{s.cbs_score.toFixed(1)}</span>
              </div>
              {s.narrative && <div className="text-[10px] text-gray-500 italic">{s.narrative}</div>}
            </div>
          ))}
        </div>
      )}
      {tab === 'cycle' && cycle?.current && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">CURRENT SENTIMENT</div>
          <div className={`text-3xl font-bold font-display ${cycleColor(cycle.current.cycle_position)}`}>{cycle.current.cycle_position}</div>
          <div className="text-gray-500 font-mono mt-2">Score: {cycle.current.cycle_score.toFixed(1)}</div>
          {cycle.current.narrative && <div className="text-[11px] text-gray-500 mt-3">{cycle.current.narrative}</div>}
        </div>
      )}
    </div>
  );
}
