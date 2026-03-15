'use client';
import { useEffect, useState } from 'react';
import { api, type MacroData, type Breadth, type ConvergenceSignal, type ConvergenceDelta, type SignalChange, type Signal, type ConsensusBlindspotSignal, type HeatIndex } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import ConvergenceHeatmap from '@/components/ConvergenceHeatmap';
import TradeRangeBar from '@/components/TradeRangeBar';
import ModuleStrip from '@/components/ModuleStrip';
import DailyDelta from '@/components/DailyDelta';
import Sparkline from '@/components/Sparkline';
import { scoreColor } from '@/lib/modules';
import { cs, fg } from '@/lib/styles';

function regimeClass(regime: string) {
  if (regime.includes('strong_risk_on')) return 'regime-strong-risk-on';
  if (regime.includes('risk_on')) return 'regime-risk-on';
  if (regime.includes('strong_risk_off')) return 'regime-strong-risk-off';
  if (regime.includes('risk_off')) return 'regime-risk-off';
  return 'regime-neutral';
}

export default function HomeContent() {
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [breadth, setBreadth] = useState<Breadth | null>(null);
  const [summary, setSummary] = useState<{ signal: string; count: number }[]>([]);
  const [convergence, setConvergence] = useState<ConvergenceSignal[]>([]);
  const [topSignals, setTopSignals] = useState<Signal[]>([]);
  const [fatPitches, setFatPitches] = useState<ConsensusBlindspotSignal[]>([]);
  const [deltas, setDeltas] = useState<ConvergenceDelta[]>([]);
  const [signalChanges, setSignalChanges] = useState<SignalChange[]>([]);
  const [sparkPrices, setSparkPrices] = useState<Record<string, { date: string; close: number }[]>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      api.macro(), api.breadth(), api.signalSummary(), api.convergence(),
      api.signals({ signal: 'STRONG BUY', sort_by: 'composite_score', limit: '15' }),
      api.fatPitches(), api.convergenceDelta(), api.signalChanges(),
    ]).then(([m, b, s, c, t, fp, cd, sc]) => {
      if (m.status === 'fulfilled') setMacro(m.value);
      if (b.status === 'fulfilled') setBreadth(b.value);
      if (s.status === 'fulfilled') setSummary(s.value);
      if (c.status === 'fulfilled') setConvergence(c.value);
      if (t.status === 'fulfilled') setTopSignals(t.value);
      if (fp.status === 'fulfilled') setFatPitches(fp.value);
      if (cd.status === 'fulfilled') setDeltas(Array.isArray(cd.value) ? cd.value : []);
      if (sc.status === 'fulfilled') setSignalChanges(Array.isArray(sc.value) ? sc.value : []);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (topSignals.length === 0) return;
    Promise.allSettled(topSignals.slice(0, 6).map(s => api.prices(s.symbol, 30).then(bars => ({ sym: s.symbol, bars })))).then(results => {
      const map: Record<string, { date: string; close: number }[]> = {};
      results.forEach(r => { if (r.status === 'fulfilled') map[r.value.sym] = r.value.bars.map(b => ({ date: b.date, close: b.close })); });
      setSparkPrices(map);
    });
  }, [topSignals]);

  const actionStocks = topSignals.map(sig => ({ ...sig, conv: convergence.find(c => c.symbol === sig.symbol) }));

  if (loading) return (
    <div className="flex items-center justify-center h-[60vh]"><div className="text-center">
      <p className="text-emerald-600 glow-green font-display text-lg tracking-widest animate-pulse-green">SYNTHESIZING SIGNALS...</p>
    </div></div>
  );

  const hero = actionStocks[0];
  const mediums = actionStocks.slice(1, 3);
  const smalls = actionStocks.slice(3, 6);

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex items-center gap-4 flex-wrap">
        {macro && <div className={regimeClass(macro.regime)}>{macro.regime.replace(/_/g, ' ').toUpperCase()} <span className="ml-2 opacity-70">{macro.total_score.toFixed(0)}</span></div>}
        {breadth && <div className="flex items-center gap-2"><span className="text-[9px] text-gray-500 tracking-wider">BREADTH</span><div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden"><div className="h-full rounded-full transition-all duration-500" {...cs({ width: `${breadth.pct_above_200dma}%`, backgroundColor: breadth.pct_above_200dma > 50 ? '#059669' : '#e11d48' })} /></div><span className={`text-[10px] font-mono ${breadth.pct_above_200dma > 50 ? 'text-emerald-600' : 'text-rose-600'}`}>{breadth.pct_above_200dma.toFixed(0)}%</span></div>}
        <div className="flex-1" />
        <div className="flex gap-3">{summary.map(s => <div key={s.signal} className="flex items-center gap-1.5"><SignalBadge signal={s.signal} size="sm" /><span className="text-[11px] font-mono text-gray-700 font-bold">{s.count}</span></div>)}</div>
      </div>
      <DailyDelta deltas={deltas} signalChanges={signalChanges} />
      <div className="grid grid-cols-5 gap-4">
        <div className="col-span-3 space-y-3">
          <h2 className="text-xs text-gray-500 tracking-widest uppercase">Highest Conviction</h2>
          {hero && (
            <a href={`/asset/${hero.symbol}`} className="panel p-5 block hover:border-emerald-600/40 transition-all group">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3"><span className="text-lg font-display font-bold text-gray-900 group-hover:text-emerald-600">{hero.symbol}</span><SignalBadge signal={hero.signal} size="md" /></div>
                {hero.conv && <span className="text-3xl font-display font-bold" {...fg(scoreColor(hero.conv.convergence_score))}>{hero.conv.convergence_score.toFixed(1)}</span>}
              </div>
              <div className="flex items-center gap-4 mb-3">{sparkPrices[hero.symbol] && <Sparkline prices={sparkPrices[hero.symbol]} width={140} height={44} />}<div className="flex-1">{hero.conv && <ModuleStrip convergence={hero.conv} mode="compact" />}</div></div>
              <TradeRangeBar entry={hero.entry_price} stop={hero.stop_loss} target={hero.target_price} width={240} height={20} showLabels showRR />
            </a>
          )}
          <div className="grid grid-cols-2 gap-3">{mediums.map(s => (
            <a key={s.symbol} href={`/asset/${s.symbol}`} className="panel p-4 block hover:border-emerald-600/30 transition-all group">
              <div className="flex items-center justify-between mb-2"><span className="text-sm font-display font-bold text-gray-900 group-hover:text-emerald-600">{s.symbol}</span>{s.conv && <span className="text-xl font-display font-bold" {...fg(scoreColor(s.conv.convergence_score))}>{s.conv.convergence_score.toFixed(1)}</span>}</div>
              <TradeRangeBar entry={s.entry_price} stop={s.stop_loss} target={s.target_price} width={180} height={14} showRR />
            </a>
          ))}</div>
          <div className="grid grid-cols-3 gap-3">{smalls.map(s => (
            <a key={s.symbol} href={`/asset/${s.symbol}`} className="panel p-3 block hover:border-emerald-600/30 transition-all group">
              <div className="flex items-center justify-between mb-1.5"><span className="text-sm font-display font-bold text-gray-900 group-hover:text-emerald-600">{s.symbol}</span>{s.conv && <span className="text-base font-display font-bold" {...fg(scoreColor(s.conv.convergence_score))}>{s.conv.convergence_score.toFixed(0)}</span>}</div>
              <TradeRangeBar entry={s.entry_price} stop={s.stop_loss} target={s.target_price} width={140} height={10} showRR />
            </a>
          ))}</div>
        </div>
        <div className="col-span-2 space-y-3">
          <div className="flex items-center justify-between"><h2 className="text-xs text-gray-500 tracking-widest uppercase">Fat Pitches</h2><a href="/signals" className="text-[9px] text-blue-600 hover:text-emerald-600">VIEW ALL</a></div>
          {fatPitches.length === 0 ? <div className="panel p-6 text-center text-gray-500 text-[11px]">No fat pitches today.</div> : fatPitches.slice(0, 6).map(fp => (
            <a key={fp.symbol} href={`/asset/${fp.symbol}`} className="panel p-3 block hover:border-emerald-600/30 transition-colors group">
              <div className="flex items-center justify-between mb-1"><span className="font-mono font-bold text-gray-900 text-sm group-hover:text-emerald-600">{fp.symbol}</span><span className="text-lg font-display font-bold" {...fg(scoreColor(fp.cbs_score))}>{fp.cbs_score.toFixed(0)}</span></div>
              {fp.narrative && <p className="text-[8px] text-gray-500 line-clamp-1">{fp.narrative}</p>}
            </a>
          ))}
        </div>
      </div>
      <div><div className="flex items-center justify-between mb-3"><h2 className="text-xs text-gray-500 tracking-widest uppercase">Convergence Heatmap</h2><a href="/synthesis" className="text-[9px] text-blue-600 hover:text-emerald-600">FULL VIEW</a></div>
        {convergence.length > 0 ? <ConvergenceHeatmap data={convergence} /> : <div className="panel p-6 text-center text-[11px] text-gray-500">No convergence data.</div>}
      </div>
    </div>
  );
}
