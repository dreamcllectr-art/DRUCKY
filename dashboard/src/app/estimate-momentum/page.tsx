'use client';

import { useEffect, useState } from 'react';
import { api, EstimateMomentumSignal, EstimateMomentumTopMovers, EstimateMomentumSectorSummary } from '@/lib/api';
import Link from 'next/link';

type Tab = 'signals' | 'movers' | 'sectors';

const scoreColor = (v: number) =>
  v >= 70 ? 'text-green-400' : v >= 50 ? 'text-emerald-400' : v >= 30 ? 'text-amber-400' : 'text-red-400';

const velocityColor = (v: number | null) => {
  if (v == null) return 'text-gray-500';
  return v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-gray-400';
};

const fmtPct = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`);

export default function EstimateMomentumPage() {
  const [tab, setTab] = useState<Tab>('signals');
  const [signals, setSignals] = useState<EstimateMomentumSignal[]>([]);
  const [movers, setMovers] = useState<EstimateMomentumTopMovers | null>(null);
  const [sectors, setSectors] = useState<EstimateMomentumSectorSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.estimateMomentum(0, 100).catch(() => [] as EstimateMomentumSignal[]),
      api.estimateMomentumTopMovers().catch(() => ({ upward_revisions: [], beat_streaks: [], tight_dispersion: [] }) as EstimateMomentumTopMovers),
      api.estimateMomentumSectors().catch(() => [] as EstimateMomentumSectorSummary[]),
    ]).then(([sig, mov, sec]) => {
      setSignals(sig);
      setMovers(mov);
      setSectors(sec);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-terminal-dim text-sm animate-pulse">Loading estimate momentum data...</div>
      </div>
    );
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'signals', label: `SIGNALS (${signals.length})` },
    { key: 'movers', label: 'TOP MOVERS' },
    { key: 'sectors', label: 'SECTOR VIEW' },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-lg font-display font-bold text-terminal-green tracking-wider">
          ESTIMATE REVISION MOMENTUM
        </h1>
        <p className="text-[11px] text-terminal-dim mt-1">
          EPS &amp; revenue revision velocity — who is the Street upgrading?
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Tracked</div>
          <div className="text-xl font-bold text-white mt-1">{signals.length}</div>
        </div>
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Strong (≥70)</div>
          <div className="text-xl font-bold text-green-400 mt-1">
            {signals.filter(s => s.em_score >= 70).length}
          </div>
        </div>
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Beat Streaks ≥3</div>
          <div className="text-xl font-bold text-emerald-400 mt-1">
            {signals.filter(s => (s.beat_streak ?? 0) >= 3).length}
          </div>
        </div>
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-[10px] text-gray-500 uppercase tracking-wider">Avg Score</div>
          <div className="text-xl font-bold text-white mt-1">
            {signals.length ? (signals.reduce((a, s) => a + s.em_score, 0) / signals.length).toFixed(1) : '—'}
          </div>
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

      {/* Tab content */}
      {tab === 'signals' && (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-gray-500 text-left border-b border-gray-800">
                <th className="pb-2 pr-3">SYMBOL</th>
                <th className="pb-2 pr-3">SECTOR</th>
                <th className="pb-2 pr-3 text-right">EM SCORE</th>
                <th className="pb-2 pr-3 text-right">VELOCITY</th>
                <th className="pb-2 pr-3 text-right">SURPRISE</th>
                <th className="pb-2 pr-3 text-right">EPS 7D</th>
                <th className="pb-2 pr-3 text-right">EPS 30D</th>
                <th className="pb-2 pr-3 text-right">BEAT STREAK</th>
                <th className="pb-2 pr-3 text-right">DISPERSION</th>
              </tr>
            </thead>
            <tbody>
              {signals.map(s => (
                <tr key={s.symbol} className="border-b border-gray-800/50 hover:bg-white/[0.02]">
                  <td className="py-2 pr-3">
                    <Link href={`/asset/${s.symbol}`} className="text-terminal-green hover:underline font-medium">
                      {s.symbol}
                    </Link>
                    {s.company_name && (
                      <span className="text-gray-600 ml-2">{s.company_name}</span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-gray-400">{s.sector ?? '—'}</td>
                  <td className={`py-2 pr-3 text-right font-mono font-bold ${scoreColor(s.em_score)}`}>
                    {s.em_score.toFixed(1)}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${scoreColor(s.velocity_score)}`}>
                    {s.velocity_score.toFixed(1)}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${scoreColor(s.surprise_score)}`}>
                    {s.surprise_score.toFixed(1)}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${velocityColor(s.eps_velocity_7d)}`}>
                    {fmtPct(s.eps_velocity_7d)}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${velocityColor(s.eps_velocity_30d)}`}>
                    {fmtPct(s.eps_velocity_30d)}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-white">
                    {s.beat_streak != null ? (
                      <span className={s.beat_streak >= 3 ? 'text-green-400 font-bold' : ''}>
                        {s.beat_streak > 0 ? `${s.beat_streak}×` : s.beat_streak < 0 ? `${s.beat_streak}×` : '—'}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-gray-400">
                    {s.dispersion_pct != null ? `${s.dispersion_pct.toFixed(1)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'movers' && movers && (
        <div className="space-y-6">
          {/* Upward revisions */}
          <div>
            <h3 className="text-xs text-green-400 tracking-wider font-bold mb-3">UPWARD EPS REVISIONS</h3>
            <div className="space-y-1">
              {movers.upward_revisions.map(s => (
                <div key={s.symbol} className="flex items-center gap-4 py-2 px-3 bg-[#111] rounded border border-gray-800/50 hover:border-green-900/50">
                  <Link href={`/asset/${s.symbol}`} className="text-terminal-green font-medium w-16">{s.symbol}</Link>
                  <span className="text-gray-400 text-[10px] flex-1">{s.company_name ?? ''} · {s.sector ?? ''}</span>
                  <span className={`font-mono text-right w-16 ${scoreColor(s.em_score)}`}>{s.em_score.toFixed(1)}</span>
                  <span className="text-green-400 font-mono text-right w-20">{fmtPct(s.eps_velocity_7d)}</span>
                </div>
              ))}
              {movers.upward_revisions.length === 0 && <div className="text-gray-600 text-sm">No upward revisions</div>}
            </div>
          </div>

          {/* Beat streaks */}
          <div>
            <h3 className="text-xs text-emerald-400 tracking-wider font-bold mb-3">CONSECUTIVE BEAT STREAKS</h3>
            <div className="space-y-1">
              {movers.beat_streaks.map(s => (
                <div key={s.symbol} className="flex items-center gap-4 py-2 px-3 bg-[#111] rounded border border-gray-800/50 hover:border-emerald-900/50">
                  <Link href={`/asset/${s.symbol}`} className="text-terminal-green font-medium w-16">{s.symbol}</Link>
                  <span className="text-gray-400 text-[10px] flex-1">{s.company_name ?? ''} · {s.sector ?? ''}</span>
                  <span className={`font-mono text-right w-16 ${scoreColor(s.em_score)}`}>{s.em_score.toFixed(1)}</span>
                  <span className="text-emerald-400 font-mono text-right w-20 font-bold">{s.beat_streak}× beat</span>
                  <span className="text-gray-400 font-mono text-right w-20">
                    avg {s.avg_surprise_pct != null ? `${s.avg_surprise_pct.toFixed(1)}%` : '—'}
                  </span>
                </div>
              ))}
              {movers.beat_streaks.length === 0 && <div className="text-gray-600 text-sm">No beat streaks</div>}
            </div>
          </div>

          {/* Tight dispersion */}
          <div>
            <h3 className="text-xs text-amber-400 tracking-wider font-bold mb-3">TIGHT DISPERSION (HIGH CONVICTION)</h3>
            <div className="space-y-1">
              {movers.tight_dispersion.map(s => (
                <div key={s.symbol} className="flex items-center gap-4 py-2 px-3 bg-[#111] rounded border border-gray-800/50 hover:border-amber-900/50">
                  <Link href={`/asset/${s.symbol}`} className="text-terminal-green font-medium w-16">{s.symbol}</Link>
                  <span className="text-gray-400 text-[10px] flex-1">{s.company_name ?? ''} · {s.sector ?? ''}</span>
                  <span className={`font-mono text-right w-16 ${scoreColor(s.em_score)}`}>{s.em_score.toFixed(1)}</span>
                  <span className="text-amber-400 font-mono text-right w-24">
                    {s.dispersion_pct != null ? `${s.dispersion_pct.toFixed(1)}% disp` : '—'}
                  </span>
                </div>
              ))}
              {movers.tight_dispersion.length === 0 && <div className="text-gray-600 text-sm">No tight dispersion setups</div>}
            </div>
          </div>
        </div>
      )}

      {tab === 'sectors' && (
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-gray-500 text-left border-b border-gray-800">
                <th className="pb-2 pr-3">SECTOR</th>
                <th className="pb-2 pr-3 text-right">STOCKS</th>
                <th className="pb-2 pr-3 text-right">AVG EM</th>
                <th className="pb-2 pr-3 text-right">AVG VELOCITY</th>
                <th className="pb-2 pr-3 text-right">AVG SURPRISE</th>
                <th className="pb-2 pr-3 text-right">STRONG (≥70)</th>
                <th className="pb-2 pr-3 text-right">STREAK 3+</th>
              </tr>
            </thead>
            <tbody>
              {sectors.map(s => (
                <tr key={s.sector} className="border-b border-gray-800/50 hover:bg-white/[0.02]">
                  <td className="py-2 pr-3 text-white font-medium">{s.sector}</td>
                  <td className="py-2 pr-3 text-right text-gray-400">{s.num_stocks}</td>
                  <td className={`py-2 pr-3 text-right font-mono font-bold ${scoreColor(s.avg_em_score)}`}>
                    {s.avg_em_score}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${scoreColor(s.avg_velocity_score)}`}>
                    {s.avg_velocity_score}
                  </td>
                  <td className={`py-2 pr-3 text-right font-mono ${scoreColor(s.avg_surprise_score)}`}>
                    {s.avg_surprise_score}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-green-400">{s.strong_count}</td>
                  <td className="py-2 pr-3 text-right font-mono text-emerald-400">{s.streak_3plus}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
