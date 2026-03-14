'use client';

import { useEffect, useState } from 'react';
import { api, type MacroData, type Breadth } from '@/lib/api';
import MacroGauge from '@/components/MacroGauge';
import IndicatorCard from '@/components/IndicatorCard';
import SignalBadge from '@/components/SignalBadge';

const INDICATORS = [
  { key: 'fed_funds_score', name: 'Fed Funds', desc: 'Cutting = bullish · Hiking = bearish' },
  { key: 'm2_score', name: 'M2 Supply', desc: 'YoY growth · Expansion = bullish' },
  { key: 'real_rates_score', name: 'Real Rates', desc: 'Fed Funds − CPI · Negative = stimulative' },
  { key: 'yield_curve_score', name: 'Yield Curve', desc: '10Y − 2Y · Inverted = bearish' },
  { key: 'credit_spreads_score', name: 'Credit Spreads', desc: 'HY OAS · Tight = risk-on' },
  { key: 'dxy_score', name: 'Dollar (DXY)', desc: '3mo trend · Weakening = bullish' },
  { key: 'vix_score', name: 'VIX + Structure', desc: 'Low + contango = bullish' },
];

export default function MacroDashboard() {
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [breadth, setBreadth] = useState<Breadth | null>(null);
  const [summary, setSummary] = useState<{ signal: string; count: number }[]>([]);
  const [topSignals, setTopSignals] = useState<any[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.allSettled([
      api.macro(),
      api.breadth(),
      api.signalSummary(),
      api.signals({ signal: 'STRONG BUY', sort_by: 'composite_score', limit: '8' }),
    ]).then(([m, b, s, t]) => {
      if (m.status === 'fulfilled') setMacro(m.value);
      else setError('No macro data. Run: python -m tools.daily_pipeline');
      if (b.status === 'fulfilled') setBreadth(b.value);
      if (s.status === 'fulfilled') setSummary(s.value);
      if (t.status === 'fulfilled') setTopSignals(t.value);
    });
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="panel p-8 text-center max-w-md">
          <div className="text-terminal-green text-2xl mb-4 glow-green">◈</div>
          <p className="text-terminal-dim text-sm">{error}</p>
          <pre className="mt-4 text-[10px] text-terminal-green bg-terminal-bg p-3 rounded">
            source venv/bin/activate{'\n'}python -m tools.daily_pipeline
          </pre>
        </div>
      </div>
    );
  }

  if (!macro) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green text-lg">LOADING SYSTEM...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
            MACRO REGIME
          </h1>
          <p className="text-[10px] text-terminal-dim tracking-widest mt-1 uppercase">
            {macro.date} · &ldquo;Focus on central banks and liquidity&rdquo;
          </p>
        </div>
        <div className="flex gap-4 text-[10px] text-terminal-dim">
          {summary.map(s => (
            <div key={s.signal} className="text-center">
              <div className="text-lg font-display font-bold text-terminal-text">{s.count}</div>
              <SignalBadge signal={s.signal} size="sm" />
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2">
          <MacroGauge score={macro.total_score} regime={macro.regime} />
        </div>
        <div className="space-y-4">
          {breadth && (
            <>
              <div className="panel p-4">
                <div className="text-[10px] text-terminal-dim tracking-wider uppercase mb-1">% Above 200 DMA</div>
                <div className={`text-2xl font-display font-bold ${breadth.pct_above_200dma > 50 ? 'text-terminal-green' : 'text-terminal-red'}`}>
                  {breadth.pct_above_200dma.toFixed(1)}%
                </div>
              </div>
              <div className="panel p-4">
                <div className="text-[10px] text-terminal-dim tracking-wider uppercase mb-1">A/D Ratio</div>
                <div className={`text-2xl font-display font-bold ${breadth.advance_decline_ratio > 1 ? 'text-terminal-green' : 'text-terminal-red'}`}>
                  {breadth.advance_decline_ratio.toFixed(2)}
                </div>
              </div>
              <div className="panel p-4">
                <div className="text-[10px] text-terminal-dim tracking-wider uppercase mb-1">New Highs / Lows</div>
                <div className="flex gap-2 items-baseline">
                  <span className="text-lg font-mono text-terminal-green">{breadth.new_highs}</span>
                  <span className="text-terminal-dim">/</span>
                  <span className="text-lg font-mono text-terminal-red">{breadth.new_lows}</span>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div>
        <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-3">
          Indicator Breakdown
        </h2>
        <div className="grid grid-cols-4 gap-3">
          {INDICATORS.map(ind => (
            <IndicatorCard
              key={ind.key}
              name={ind.name}
              score={(macro as any)[ind.key]}
              description={ind.desc}
            />
          ))}
        </div>
      </div>

      {topSignals.length > 0 && (
        <div>
          <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-3">
            Highest Conviction Setups
          </h2>
          <div className="grid grid-cols-4 gap-3">
            {topSignals.map((s: any) => (
              <a
                key={s.symbol}
                href={`/asset/${s.symbol}`}
                className="panel p-4 hover:border-terminal-green/30 transition-colors group"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-display font-bold text-terminal-bright group-hover:text-terminal-green transition-colors">
                    {s.symbol}
                  </span>
                  <SignalBadge signal={s.signal} size="sm" />
                </div>
                <div className="text-[10px] text-terminal-dim mb-2">{s.asset_class}</div>
                <div className="grid grid-cols-3 gap-2 text-[10px]">
                  <div>
                    <span className="text-terminal-dim">Score</span>
                    <div className="text-terminal-green font-mono">{s.composite_score.toFixed(1)}</div>
                  </div>
                  <div>
                    <span className="text-terminal-dim">R:R</span>
                    <div className="text-terminal-amber font-mono">{s.rr_ratio.toFixed(1)}</div>
                  </div>
                  <div>
                    <span className="text-terminal-dim">Entry</span>
                    <div className="text-terminal-text font-mono">${s.entry_price.toFixed(2)}</div>
                  </div>
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
