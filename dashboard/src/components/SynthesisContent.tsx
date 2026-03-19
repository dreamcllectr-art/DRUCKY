'use client';
import { useEffect, useState } from 'react';
import { api, type MacroData, type Breadth, type ConvergenceSignal, type Signal, type DisplacementSignal, type PairSignal, type SectorExpertSignal } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import ConvergenceHeatmap from '@/components/ConvergenceHeatmap';

interface ClusterStock { symbol: string; sources: string[]; convergenceScore: number | null; conviction: string | null; narrative: string | null; displacementScore: number | null; }

export default function SynthesisContent() {
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [breadth, setBreadth] = useState<Breadth | null>(null);
  const [summary, setSummary] = useState<{ signal: string; count: number }[]>([]);
  const [convergence, setConvergence] = useState<ConvergenceSignal[]>([]);
  const [topSignals, setTopSignals] = useState<Signal[]>([]);
  const [displacement, setDisplacement] = useState<DisplacementSignal[]>([]);
  const [runners, setRunners] = useState<PairSignal[]>([]);
  const [sectorExperts, setSectorExperts] = useState<SectorExpertSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedAction, setExpandedAction] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([api.macro(), api.breadth(), api.signalSummary(), api.convergence(), api.signals({ signal: 'STRONG BUY', sort_by: 'composite_score', limit: '15' }), api.displacement(7), api.pairs({ signal_type: 'runner' }), api.sectorExperts()]).then(([m, b, s, c, t, d, r, se]) => {
      if (m.status === 'fulfilled') setMacro(m.value);
      if (b.status === 'fulfilled') setBreadth(b.value);
      if (s.status === 'fulfilled') setSummary(s.value);
      if (c.status === 'fulfilled') setConvergence(c.value);
      if (t.status === 'fulfilled') setTopSignals(t.value);
      if (d.status === 'fulfilled') setDisplacement(d.value);
      if (r.status === 'fulfilled') setRunners(r.value);
      if (se.status === 'fulfilled') setSectorExperts(se.value);
      setLoading(false);
    });
  }, []);

  const clusters: ClusterStock[] = (() => {
    const map = new Map<string, ClusterStock>();
    const get = (sym: string): ClusterStock => map.get(sym) || { symbol: sym, sources: [], convergenceScore: null, conviction: null, narrative: null, displacementScore: null };
    convergence.slice(0, 30).forEach(c => { const s = get(c.symbol); s.sources.push('CONVERGENCE'); s.convergenceScore = c.convergence_score; s.conviction = c.conviction_level; s.narrative = c.narrative; map.set(c.symbol, s); });
    displacement.forEach(d => { const s = get(d.symbol); if (!s.sources.includes('DISPLACEMENT')) s.sources.push('DISPLACEMENT'); s.displacementScore = Math.max(s.displacementScore ?? 0, d.displacement_score); map.set(d.symbol, s); });
    runners.forEach(r => { const sym = r.runner_symbol || r.symbol_a; const s = get(sym); if (!s.sources.includes('PAIRS')) s.sources.push('PAIRS'); map.set(sym, s); });
    sectorExperts.forEach(se => { const s = get(se.symbol); if (!s.sources.includes('SECTOR')) s.sources.push('SECTOR'); map.set(se.symbol, s); });
    return Array.from(map.values()).filter(s => s.sources.length >= 2).sort((a, b) => b.sources.length - a.sources.length || (b.convergenceScore ?? 0) - (a.convergenceScore ?? 0));
  })();

  const actionStocks = topSignals.map(sig => ({ ...sig, conv: convergence.find(c => c.symbol === sig.symbol) }));

  if (loading) return <div className="flex items-center justify-center h-[40vh]"><div className="text-gray-400 font-display text-sm tracking-widest animate-pulse">Synthesizing convergence signals...</div></div>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="panel p-4"><div className="text-[9px] text-gray-500 tracking-wider uppercase mb-1">Macro</div>{macro ? <><div className={`text-xl font-display font-bold ${macro.total_score >= 60 ? 'text-emerald-600' : macro.total_score >= 40 ? 'text-amber-600' : 'text-rose-600'}`}>{macro.total_score.toFixed(0)}</div><div className={`text-[9px] font-bold tracking-widest mt-1 ${macro.regime.includes('risk_on') ? 'text-emerald-600' : macro.regime.includes('risk_off') ? 'text-rose-600' : 'text-amber-600'}`}>{macro.regime.replace(/_/g, ' ').toUpperCase()}</div></> : <div className="text-gray-500 text-[10px]">N/A</div>}</div>
        <div className="panel p-4"><div className="text-[9px] text-gray-500 tracking-wider uppercase mb-1">Breadth</div>{breadth ? <div className={`text-xl font-display font-bold ${breadth.pct_above_200dma > 50 ? 'text-emerald-600' : 'text-rose-600'}`}>{breadth.pct_above_200dma.toFixed(1)}%</div> : <div className="text-gray-500 text-[10px]">N/A</div>}</div>
        <div className="panel p-4"><div className="text-[9px] text-gray-500 tracking-wider uppercase mb-1">Convergence</div><div className="text-xl font-display font-bold text-blue-600">{convergence.length}</div><div className="text-[9px] text-gray-500 mt-1">{convergence.filter(c => c.conviction_level === 'HIGH').length} high conviction</div></div>
        <div className="panel p-4"><div className="text-[9px] text-gray-500 tracking-wider uppercase mb-2">Signals</div><div className="flex gap-2">{summary.map(s => <div key={s.signal} className="text-center"><div className="text-sm font-display font-bold text-gray-700">{s.count}</div><SignalBadge signal={s.signal} size="sm" /></div>)}</div></div>
      </div>
      <div><h2 className="text-xs text-gray-500 tracking-widest uppercase mb-3">Convergence Heatmap</h2>{convergence.length > 0 ? <ConvergenceHeatmap data={convergence} /> : <div className="panel p-6 text-center text-[11px] text-gray-400">Convergence data unavailable. Pipeline may be initializing.</div>}</div>
      {clusters.length > 0 && <div><h2 className="text-xs text-gray-500 tracking-widest uppercase mb-3">Cross-Signal Clusters ({clusters.length})</h2><div className="grid grid-cols-3 gap-3">{clusters.slice(0, 12).map(c => (
        <a key={c.symbol} href={`/asset/${c.symbol}`} className="panel p-4 hover:border-emerald-600/30 transition-colors group">
          <div className="flex items-center justify-between mb-2"><span className="font-mono font-bold text-gray-900 text-sm group-hover:text-emerald-600">{c.symbol}</span><div className="flex gap-1">{c.sources.map(src => <span key={src} className={`text-[7px] px-1.5 py-0.5 rounded-lg font-bold tracking-wider border ${src === 'CONVERGENCE' ? 'bg-emerald-600/10 text-emerald-600 border-emerald-600/20' : src === 'DISPLACEMENT' ? 'bg-blue-600/10 text-blue-600 border-blue-600/20' : 'bg-amber-600/10 text-amber-600 border-amber-600/20'}`}>{src}</span>)}</div></div>
          {c.narrative && <p className="text-[8px] text-gray-500 mt-2 line-clamp-2 leading-relaxed">{c.narrative}</p>}
        </a>))}</div></div>}
      {actionStocks.length > 0 && <div><h2 className="text-xs text-gray-500 tracking-widest uppercase mb-3">Top Actions ({actionStocks.length})</h2><div className="panel overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-center py-3 px-2 font-normal">Signal</th><th className="text-right py-3 px-2 font-normal">Composite</th><th className="text-right py-3 px-2 font-normal">Conv.</th><th className="text-right py-3 px-2 font-normal">R:R</th><th className="text-right py-3 px-4 font-normal">Size</th></tr></thead>
        <tbody>{actionStocks.map(s => (
          <tr key={s.symbol} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => setExpandedAction(expandedAction === s.symbol ? null : s.symbol)}>
            <td className="py-2.5 px-4"><a href={`/asset/${s.symbol}`} className="font-mono font-bold text-gray-900 hover:text-emerald-600" onClick={e => e.stopPropagation()}>{s.symbol}</a></td>
            <td className="py-2.5 px-2 text-center"><SignalBadge signal={s.signal} size="sm" /></td>
            <td className="py-2.5 px-2 text-right font-mono text-gray-700">{(s.composite_score ?? 0).toFixed(1)}</td>
            <td className="py-2.5 px-2 text-right font-mono text-emerald-600">{s.conv?.convergence_score?.toFixed(1) ?? '--'}</td>
            <td className="py-2.5 px-2 text-right font-mono text-amber-600">{s.rr_ratio?.toFixed(1) ?? '—'}</td>
            <td className="py-2.5 px-4 text-right font-mono text-gray-500">{s.position_size_dollars ? `$${(s.position_size_dollars / 1000).toFixed(0)}K` : '--'}</td>
          </tr>))}</tbody></table></div></div></div>}
    </div>
  );
}
