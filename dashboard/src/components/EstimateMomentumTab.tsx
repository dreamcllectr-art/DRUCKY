'use client';
import { useEffect, useState } from 'react';
import { api, EstimateMomentumSignal, EstimateMomentumTopMovers } from '@/lib/api';
import Link from 'next/link';

const scoreColor = (v: number) => v >= 70 ? 'text-green-400' : v >= 50 ? 'text-emerald-400' : v >= 30 ? 'text-amber-400' : 'text-red-400';
const velocityColor = (v: number | null) => v == null ? 'text-gray-500' : v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-gray-500';
const fmtPct = (v: number | null) => v == null ? '--' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;

export default function EstimateMomentumTab() {
  const [signals, setSignals] = useState<EstimateMomentumSignal[]>([]);
  const [movers, setMovers] = useState<EstimateMomentumTopMovers | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'signals' | 'movers'>('signals');

  useEffect(() => {
    Promise.all([
      api.estimateMomentum(0, 100),
      api.estimateMomentumTopMovers(),
    ]).then(([sig, mov]) => { setSignals(sig as EstimateMomentumSignal[]); setMovers(mov as EstimateMomentumTopMovers); }).catch((e) => setError(e.message || 'Failed to load estimate momentum data')).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading estimate momentum...</div>;

  return (
    <div className="space-y-4">
      {error && (
        <div className="panel p-4 border-rose-200 bg-rose-50">
          <div className="text-rose-600 text-sm font-bold mb-1">Failed to load data</div>
          <p className="text-[11px] text-gray-500">{error}</p>
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white border border-gray-200 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase tracking-wider">Tracked</div><div className="text-xl font-bold text-gray-900 mt-1">{signals.length}</div></div>
        <div className="bg-white border border-gray-200 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase tracking-wider">Strong ({'\u2265'}70)</div><div className="text-xl font-bold text-green-400 mt-1">{signals.filter(s => s.em_score >= 70).length}</div></div>
        <div className="bg-white border border-gray-200 rounded-lg p-3"><div className="text-[10px] text-gray-500 uppercase tracking-wider">Beat Streaks {'\u2265'}3</div><div className="text-xl font-bold text-emerald-400 mt-1">{signals.filter(s => (s.beat_streak ?? 0) >= 3).length}</div></div>
      </div>
      <div className="flex gap-1 border-b border-gray-200">
        {[{ key: 'signals' as const, label: 'SIGNALS' }, { key: 'movers' as const, label: 'TOP MOVERS' }].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} className={`px-4 py-2 text-[11px] tracking-widest transition-colors ${tab === t.key ? 'text-emerald-600 border-b-2 border-emerald-600' : 'text-gray-500 hover:text-gray-600'}`}>{t.label}</button>
        ))}
      </div>
      {tab === 'signals' && (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead><tr className="text-gray-500 text-left border-b border-gray-200"><th className="pb-2 pr-3">SYMBOL</th><th className="pb-2 pr-3 text-right">EM SCORE</th><th className="pb-2 pr-3 text-right">VELOCITY</th><th className="pb-2 pr-3 text-right">EPS 7D</th><th className="pb-2 pr-3 text-right">BEAT STREAK</th></tr></thead>
            <tbody>{signals.map(s => (
              <tr key={s.symbol} className="border-b border-gray-200/50 hover:bg-white/[0.02]">
                <td className="py-2 pr-3"><Link href={`/asset/${s.symbol}`} className="text-emerald-600 hover:underline font-medium">{s.symbol}</Link></td>
                <td className={`py-2 pr-3 text-right font-mono font-bold ${scoreColor(s.em_score)}`}>{s.em_score.toFixed(1)}</td>
                <td className={`py-2 pr-3 text-right font-mono ${scoreColor(s.velocity_score)}`}>{s.velocity_score.toFixed(1)}</td>
                <td className={`py-2 pr-3 text-right font-mono ${velocityColor(s.eps_velocity_7d)}`}>{fmtPct(s.eps_velocity_7d)}</td>
                <td className="py-2 pr-3 text-right font-mono">{s.beat_streak != null && s.beat_streak > 0 ? <span className={s.beat_streak >= 3 ? 'text-green-400 font-bold' : 'text-gray-900'}>{s.beat_streak}x</span> : '--'}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {tab === 'movers' && movers && (
        <div className="space-y-4">
          <div><h3 className="text-xs text-green-400 tracking-wider font-bold mb-2">UPWARD REVISIONS</h3>
            {movers.upward_revisions.length === 0 ? <div className="text-gray-600 text-sm">None</div> : movers.upward_revisions.map(s => (
              <div key={s.symbol} className="flex items-center gap-4 py-2 px-3 bg-white rounded border border-gray-200/50 mb-1">
                <Link href={`/asset/${s.symbol}`} className="text-emerald-600 font-medium w-16">{s.symbol}</Link>
                <span className="text-gray-500 text-[10px] flex-1">{s.company_name ?? ''}</span>
                <span className={`font-mono w-16 text-right ${scoreColor(s.em_score)}`}>{s.em_score.toFixed(1)}</span>
                <span className="text-green-400 font-mono w-20 text-right">{fmtPct(s.eps_velocity_7d)}</span>
              </div>
            ))}
          </div>
          <div><h3 className="text-xs text-emerald-400 tracking-wider font-bold mb-2">BEAT STREAKS</h3>
            {movers.beat_streaks.length === 0 ? <div className="text-gray-600 text-sm">None</div> : movers.beat_streaks.map(s => (
              <div key={s.symbol} className="flex items-center gap-4 py-2 px-3 bg-white rounded border border-gray-200/50 mb-1">
                <Link href={`/asset/${s.symbol}`} className="text-emerald-600 font-medium w-16">{s.symbol}</Link>
                <span className="text-gray-500 text-[10px] flex-1">{s.company_name ?? ''}</span>
                <span className="text-emerald-400 font-mono font-bold">{s.beat_streak}x beat</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
