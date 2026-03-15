'use client';
import { useEffect, useState } from 'react';
import { api, type PredictionMarketSignal, type PredictionMarketRaw, type PredictionMarketCategory } from '@/lib/api';
import { scorePillSty } from '@/lib/styles';

export default function PredictionsTab() {
  const [signals, setSignals] = useState<PredictionMarketSignal[]>([]);
  const [markets, setMarkets] = useState<PredictionMarketRaw[]>([]);
  const [categories, setCategories] = useState<PredictionMarketCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'signals' | 'markets'>('signals');

  useEffect(() => {
    Promise.all([api.predictionMarkets(0, 7), api.predictionMarketsRaw(undefined, 3), api.predictionMarketCategories()]).then(([s, m, c]) => { setSignals(s); setMarkets(m); setCategories(c); }).catch((e) => setError(e.message || 'Failed to load prediction data')).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading predictions...</div>;

  const dirColor = (dir: string | null) => !dir ? 'text-gray-500' : (dir === 'bullish' || dir === 'positive') ? 'text-emerald-600' : (dir === 'bearish' || dir === 'negative') ? 'text-rose-600' : 'text-amber-600';

  return (
    <div className="space-y-4">
      {error && (
        <div className="panel p-4 border-rose-200 bg-rose-50">
          <div className="text-rose-600 text-sm font-bold mb-1">Failed to load data</div>
          <p className="text-[11px] text-gray-500">{error}</p>
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        <div onClick={() => setTab('signals')} className={`panel px-4 py-3 cursor-pointer transition-all ${tab === 'signals' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-emerald-600">{signals.filter(s => s.pm_score >= 50).length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">HIGH IMPACT</div></div>
        <div onClick={() => setTab('markets')} className={`panel px-4 py-3 cursor-pointer transition-all ${tab === 'markets' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-amber-600">{markets.length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">ACTIVE MARKETS</div></div>
        <div className="panel px-4 py-3"><div className="text-2xl font-display font-bold text-rose-600">{categories.length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">CATEGORIES</div></div>
      </div>
      {tab === 'signals' && (
        <div className="panel overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">PM Score</th><th className="text-right py-3 px-2 font-normal">Markets</th><th className="text-right py-3 px-2 font-normal">Net Impact</th><th className="text-left py-3 px-4 font-normal">Narrative</th></tr></thead>
          <tbody>{signals.length === 0 ? <tr><td colSpan={5} className="text-center py-8 text-gray-500">No signals.</td></tr> : signals.map((s, i) => (
            <tr key={`pm-${s.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${s.symbol}`)}>
              <td className="py-2.5 px-4 font-mono font-bold text-emerald-600">{s.symbol}</td>
              <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(s.pm_score, [60, 50])}>{s.pm_score.toFixed(0)}</span></td>
              <td className="py-2.5 px-2 text-right font-mono text-gray-500">{s.market_count || '--'}</td>
              <td className={`py-2.5 px-2 text-right font-mono ${(s.net_impact || 0) >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{s.net_impact ? `${s.net_impact >= 0 ? '+' : ''}${s.net_impact.toFixed(1)}` : '--'}</td>
              <td className="py-2.5 px-4 text-gray-500 max-w-[350px] truncate">{s.narrative || '--'}</td>
            </tr>))}</tbody></table></div>
        </div>
      )}
      {tab === 'markets' && (
        <div className="panel overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Question</th><th className="text-right py-3 px-2 font-normal">YES %</th><th className="text-center py-3 px-2 font-normal">Direction</th><th className="text-left py-3 px-2 font-normal">Symbols</th></tr></thead>
          <tbody>{markets.length === 0 ? <tr><td colSpan={4} className="text-center py-8 text-gray-500">No markets.</td></tr> : markets.map((m, i) => (
            <tr key={`mkt-${m.market_id}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03]">
              <td className="py-2.5 px-4 text-gray-700 max-w-[400px] truncate">{m.question || '--'}</td>
              <td className="py-2.5 px-2 text-right font-mono text-gray-900">{m.yes_probability ? `${(m.yes_probability * 100).toFixed(0)}%` : '--'}</td>
              <td className={`py-2.5 px-2 text-center font-bold text-[10px] ${dirColor(m.direction)}`}>{m.direction?.toUpperCase() || '--'}</td>
              <td className="py-2.5 px-2 text-emerald-600 font-mono text-[10px]">{m.specific_symbols || '--'}</td>
            </tr>))}</tbody></table></div>
        </div>
      )}
    </div>
  );
}
