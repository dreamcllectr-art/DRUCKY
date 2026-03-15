'use client';

import { useEffect, useState } from 'react';
import { api, type MacroData, type Breadth, type Signal } from '@/lib/api';
import MacroGauge from '@/components/MacroGauge';
import IndicatorCard from '@/components/IndicatorCard';
import SignalBadge from '@/components/SignalBadge';
import EconomicTab from '@/components/EconomicTab';

const INDICATORS = [
  { key: 'fed_funds_score', name: 'Fed Funds', desc: 'Cutting = bullish' },
  { key: 'm2_score', name: 'M2 Supply', desc: 'YoY growth' },
  { key: 'real_rates_score', name: 'Real Rates', desc: 'Fed Funds - CPI' },
  { key: 'yield_curve_score', name: 'Yield Curve', desc: '10Y - 2Y' },
  { key: 'credit_spreads_score', name: 'Credit Spreads', desc: 'HY OAS' },
  { key: 'dxy_score', name: 'Dollar (DXY)', desc: '3mo trend' },
  { key: 'vix_score', name: 'VIX', desc: 'Low + contango = bull' },
];

const TABS = ['Regime', 'Economic Indicators'] as const;

export default function MacroDashboard() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Regime');
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [breadth, setBreadth] = useState<Breadth | null>(null);
  const [summary, setSummary] = useState<{ signal: string; count: number }[]>([]);
  const [topSignals, setTopSignals] = useState<Signal[]>([]);

  useEffect(() => {
    Promise.allSettled([
      api.macro(), api.breadth(), api.signalSummary(),
      api.signals({ signal: 'STRONG BUY', sort_by: 'composite_score', limit: '8' }),
    ]).then(([m, b, s, t]) => {
      if (m.status === 'fulfilled') setMacro(m.value);
      if (b.status === 'fulfilled') setBreadth(b.value);
      if (s.status === 'fulfilled') setSummary(s.value);
      if (t.status === 'fulfilled') setTopSignals(t.value);
    });
  }, []);

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-gray-900 tracking-tight">MACRO</h1>
          <p className="text-[10px] text-gray-500 tracking-widest mt-1 uppercase">Regime + Economic Indicators</p>
        </div>
        <div className="flex gap-4 text-[10px] text-gray-500">
          {summary.map(s => (<div key={s.signal} className="text-center"><div className="text-lg font-display font-bold text-gray-700">{s.count}</div><SignalBadge signal={s.signal} size="sm" /></div>))}
        </div>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map(t => (<button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-[10px] tracking-widest border-b-2 transition-all ${tab === t ? 'text-emerald-600 border-emerald-600' : 'text-gray-500 border-transparent hover:text-gray-700'}`}>{t.toUpperCase()}</button>))}
      </div>

      {tab === 'Regime' && macro && (
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-4">
            <div className="col-span-2"><MacroGauge score={macro.total_score} regime={macro.regime} /></div>
            <div className="space-y-4">
              {breadth && (<>
                <div className="panel p-4"><div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">% Above 200 DMA</div><div className={`text-2xl font-display font-bold ${breadth.pct_above_200dma > 50 ? 'text-emerald-600' : 'text-rose-600'}`}>{breadth.pct_above_200dma.toFixed(1)}%</div></div>
                <div className="panel p-4"><div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">A/D Ratio</div><div className={`text-2xl font-display font-bold ${breadth.advance_decline_ratio > 1 ? 'text-emerald-600' : 'text-rose-600'}`}>{breadth.advance_decline_ratio.toFixed(2)}</div></div>
                <div className="panel p-4"><div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">New Highs / Lows</div><div className="flex gap-2 items-baseline"><span className="text-lg font-mono text-emerald-600">{breadth.new_highs}</span><span className="text-gray-500">/</span><span className="text-lg font-mono text-rose-600">{breadth.new_lows}</span></div></div>
              </>)}
            </div>
          </div>
          <div><h2 className="text-xs text-gray-500 tracking-widest uppercase mb-3">Indicator Breakdown</h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{INDICATORS.map(ind => <IndicatorCard key={ind.key} name={ind.name} score={macro[ind.key as keyof MacroData] as number} description={ind.desc} />)}</div>
          </div>
          {topSignals.length > 0 && (<div><h2 className="text-xs text-gray-500 tracking-widest uppercase mb-3">Highest Conviction Setups</h2>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{topSignals.map((s) => (
              <a key={s.symbol} href={`/asset/${s.symbol}`} className="panel p-4 hover:border-emerald-600/30 transition-colors group">
                <div className="flex items-center justify-between mb-2"><span className="text-sm font-display font-bold text-gray-900 group-hover:text-emerald-600 transition-colors">{s.symbol}</span><SignalBadge signal={s.signal} size="sm" /></div>
                <div className="grid grid-cols-3 gap-2 text-[10px]"><div><span className="text-gray-500">Score</span><div className="text-emerald-600 font-mono">{s.composite_score?.toFixed(1) ?? '—'}</div></div><div><span className="text-gray-500">R:R</span><div className="text-amber-600 font-mono">{s.rr_ratio?.toFixed(1) ?? '—'}</div></div><div><span className="text-gray-500">Entry</span><div className="text-gray-700 font-mono">{s.entry_price ? `$${s.entry_price.toFixed(2)}` : '—'}</div></div></div>
              </a>))}</div>
          </div>)}
        </div>
      )}
      {tab === 'Regime' && !macro && <div className="flex items-center justify-center h-[40vh]"><div className="text-gray-400 text-sm font-display tracking-widest animate-pulse">Loading...</div></div>}
      {tab === 'Economic Indicators' && <EconomicTab />}
    </div>
  );
}
