'use client';
import { useEffect, useState } from 'react';
import { api, type PairSignal, type PairRelationship, type PairSpread } from '@/lib/api';
import SpreadChart from '@/components/SpreadChart';
import { scorePillSty, fg } from '@/lib/styles';

export default function PairsTab() {
  const [runners, setRunners] = useState<PairSignal[]>([]);
  const [mrSignals, setMrSignals] = useState<PairSignal[]>([]);
  const [relationships, setRelationships] = useState<PairRelationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'runners' | 'mr' | 'explorer'>('runners');
  const [expandedPair, setExpandedPair] = useState<string | null>(null);
  const [spreadData, setSpreadData] = useState<PairSpread[]>([]);
  const [spreadLoading, setSpreadLoading] = useState(false);

  useEffect(() => {
    Promise.all([api.pairs({ signal_type: 'runner' }).catch(() => []), api.pairs({ signal_type: 'mean_reversion' }).catch(() => []), api.pairRelationships().catch(() => [])]).then(([r, mr, rel]) => { setRunners(r); setMrSignals(mr); setRelationships(rel); setLoading(false); });
  }, []);

  const loadSpread = async (a: string, b: string) => {
    const key = `${a}-${b}`;
    if (expandedPair === key) { setExpandedPair(null); return; }
    setSpreadLoading(true); setExpandedPair(key);
    try { setSpreadData(await api.pairSpread(a, b)); } catch { setSpreadData([]); }
    setSpreadLoading(false);
  };

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading pairs...</div>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div onClick={() => setActiveTab('runners')} className={`panel px-4 py-3 cursor-pointer transition-all ${activeTab === 'runners' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-emerald-600">{runners.length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">RUNNERS</div></div>
        <div onClick={() => setActiveTab('mr')} className={`panel px-4 py-3 cursor-pointer transition-all ${activeTab === 'mr' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-blue-600">{mrSignals.length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">MEAN-REVERSION</div></div>
        <div onClick={() => setActiveTab('explorer')} className={`panel px-4 py-3 cursor-pointer transition-all ${activeTab === 'explorer' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-gray-700">{relationships.length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">COINTEGRATED</div></div>
      </div>
      {activeTab === 'runners' && (
        <div className="panel overflow-hidden"><div className="px-4 py-3 border-b border-gray-200"><h2 className="text-xs text-gray-900 tracking-widest font-bold">RUNNERS</h2></div>
          <div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Runner</th><th className="text-left py-3 px-2 font-normal">Laggard</th><th className="text-right py-3 px-2 font-normal">Z</th><th className="text-right py-3 px-2 font-normal">Score</th><th className="text-left py-3 px-4 font-normal">Narrative</th></tr></thead>
            <tbody>{runners.length === 0 ? <tr><td colSpan={5} className="text-center py-8 text-gray-500">No runners.</td></tr> : runners.map((s, i) => { const laggard = s.runner_symbol === s.symbol_a ? s.symbol_b : s.symbol_a; return (
              <tr key={`${s.runner_symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${s.runner_symbol}`)}>
                <td className="py-2.5 px-4 font-mono font-bold text-emerald-600">{s.runner_symbol}</td>
                <td className="py-2.5 px-2 font-mono text-gray-500">{laggard}</td>
                <td className={`py-2.5 px-2 text-right font-mono ${Math.abs(s.spread_zscore) >= 2 ? 'text-rose-600' : 'text-amber-600'}`}>{s.spread_zscore.toFixed(1)}</td>
                <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(s.pairs_score)}>{s.pairs_score.toFixed(0)}</span></td>
                <td className="py-2.5 px-4 text-gray-500 max-w-[280px] truncate">{s.narrative}</td>
              </tr>); })}</tbody></table></div>
        </div>
      )}
      {activeTab === 'mr' && (
        <div className="panel overflow-hidden"><div className="px-4 py-3 border-b border-gray-200"><h2 className="text-xs text-gray-900 tracking-widest font-bold">MEAN-REVERSION PAIRS</h2></div>
          <div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Pair</th><th className="text-right py-3 px-2 font-normal">Z</th><th className="text-right py-3 px-2 font-normal">Half-Life</th><th className="text-right py-3 px-2 font-normal">Score</th><th className="text-left py-3 px-4 font-normal">Narrative</th></tr></thead>
            <tbody>{mrSignals.length === 0 ? <tr><td colSpan={5} className="text-center py-8 text-gray-500">No MR signals.</td></tr> : mrSignals.map((s, i) => (
              <tr key={`${s.symbol_a}-${s.symbol_b}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => loadSpread(s.symbol_a, s.symbol_b)}>
                <td className="py-2.5 px-4 font-mono font-bold text-gray-900">{s.symbol_a} / {s.symbol_b}</td>
                <td className="py-2.5 px-2 text-right font-mono text-rose-600">{s.spread_zscore.toFixed(2)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-gray-700">{s.half_life_days.toFixed(0)}d</td>
                <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(s.pairs_score, [70, 50], { hiBg: 'rgba(37,99,235,0.15)', hiFg: '#2563eb', midBg: 'rgba(217,119,6,0.15)', midFg: '#d97706', loBg: 'rgba(243,244,246,1)', loFg: '#6b7280' })}>{s.pairs_score.toFixed(0)}</span></td>
                <td className="py-2.5 px-4 text-gray-500 max-w-[280px] truncate">{s.narrative}</td>
              </tr>))}</tbody></table></div>
          {expandedPair && <div className="border-t border-gray-200 p-4">{spreadLoading ? <div className="text-center py-8 text-gray-500 animate-pulse">Loading...</div> : spreadData.length > 0 ? <SpreadChart data={spreadData} symbolA={expandedPair.split('-')[0]} symbolB={expandedPair.split('-')[1]} height={200} /> : <div className="text-center py-8 text-gray-500">No spread data.</div>}</div>}
        </div>
      )}
      {activeTab === 'explorer' && (
        <div className="panel overflow-hidden"><div className="px-4 py-3 border-b border-gray-200"><h2 className="text-xs text-gray-900 tracking-widest font-bold">COINTEGRATED PAIRS</h2></div>
          <div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Pair</th><th className="text-right py-3 px-2 font-normal">Corr 60d</th><th className="text-right py-3 px-2 font-normal">Coint p</th><th className="text-right py-3 px-2 font-normal">Half-Life</th></tr></thead>
            <tbody>{relationships.length === 0 ? <tr><td colSpan={4} className="text-center py-8 text-gray-500">No pairs.</td></tr> : relationships.slice(0, 50).map((r, i) => (
              <tr key={`${r.symbol_a}-${r.symbol_b}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => loadSpread(r.symbol_a, r.symbol_b)}>
                <td className="py-2.5 px-4 font-mono font-bold text-gray-900">{r.symbol_a} / {r.symbol_b}</td>
                <td className="py-2.5 px-2 text-right font-mono text-gray-700">{r.correlation_60d.toFixed(2)}</td>
                <td className="py-2.5 px-2 text-right font-mono" {...fg(r.cointegration_pvalue < 0.01 ? '#059669' : '#d97706')}>{r.cointegration_pvalue.toFixed(4)}</td>
                <td className="py-2.5 px-2 text-right font-mono text-gray-700">{r.half_life_days.toFixed(0)}d</td>
              </tr>))}</tbody></table></div>
        </div>
      )}
    </div>
  );
}
