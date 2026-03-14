'use client';

import { useEffect, useState } from 'react';
import { api, type Signal } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';

const ASSET_FILTERS = ['All', 'stock', 'crypto', 'commodity'] as const;
const SIGNAL_FILTERS = ['All', 'STRONG BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG SELL'] as const;

export default function ScreenerPage() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [filtered, setFiltered] = useState<Signal[]>([]);
  const [assetFilter, setAssetFilter] = useState<string>('All');
  const [signalFilter, setSignalFilter] = useState<string>('All');
  const [sortBy, setSortBy] = useState<string>('composite_score');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.signals().then(data => {
      setSignals(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    let result = [...signals];
    if (assetFilter !== 'All') result = result.filter(s => s.asset_class === assetFilter);
    if (signalFilter !== 'All') result = result.filter(s => s.signal === signalFilter);
    result.sort((a, b) => (b as any)[sortBy] - (a as any)[sortBy]);
    setFiltered(result);
  }, [signals, assetFilter, signalFilter, sortBy]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">SCANNING UNIVERSE...</div>
      </div>
    );
  }

  const counts = signals.reduce((acc, s) => {
    acc[s.signal] = (acc[s.signal] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          SCREENER
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          TECHNICAL FIRST · FUNDAMENTALS SECOND — {filtered.length} ASSETS
        </p>
      </div>

      {/* Signal counts */}
      <div className="flex gap-3">
        {['STRONG BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG SELL'].map(sig => (
          <div
            key={sig}
            onClick={() => setSignalFilter(signalFilter === sig ? 'All' : sig)}
            className={`panel px-4 py-2 cursor-pointer transition-all ${
              signalFilter === sig ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
            }`}
          >
            <div className="text-xl font-display font-bold text-terminal-text">
              {counts[sig] || 0}
            </div>
            <SignalBadge signal={sig} size="sm" />
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-4 items-center">
        <div className="flex gap-1">
          {ASSET_FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setAssetFilter(f)}
              className={`px-3 py-1.5 text-[10px] tracking-widest uppercase rounded-sm transition-colors ${
                assetFilter === f
                  ? 'bg-terminal-green/10 text-terminal-green border border-terminal-green/30'
                  : 'text-terminal-dim hover:text-terminal-text border border-terminal-border'
              }`}
            >
              {f === 'All' ? 'ALL' : f.toUpperCase()}
            </button>
          ))}
        </div>

        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
          className="bg-terminal-panel border border-terminal-border text-terminal-text text-[10px] tracking-wider px-3 py-1.5 rounded-sm"
        >
          <option value="composite_score">COMPOSITE ↓</option>
          <option value="technical_score">TECHNICAL ↓</option>
          <option value="fundamental_score">FUNDAMENTAL ↓</option>
          <option value="rr_ratio">R:R RATIO ↓</option>
        </select>
      </div>

      {/* Table */}
      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                <th className="text-left py-3 px-4 font-normal">Symbol</th>
                <th className="text-left py-3 px-2 font-normal">Class</th>
                <th className="text-center py-3 px-2 font-normal">Signal</th>
                <th className="text-right py-3 px-2 font-normal">Composite</th>
                <th className="text-right py-3 px-2 font-normal">Technical</th>
                <th className="text-right py-3 px-2 font-normal">Fundamental</th>
                <th className="text-right py-3 px-2 font-normal">Entry</th>
                <th className="text-right py-3 px-2 font-normal">Stop</th>
                <th className="text-right py-3 px-2 font-normal">Target</th>
                <th className="text-right py-3 px-2 font-normal">R:R</th>
                <th className="text-right py-3 px-4 font-normal">Size $</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 100).map((s, i) => (
                <tr
                  key={s.symbol}
                  className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                  onClick={() => window.location.href = `/asset/${s.symbol}`}
                  style={{ animationDelay: `${i * 20}ms` }}
                >
                  <td className="py-2.5 px-4 font-mono font-bold text-terminal-bright">
                    {s.symbol}
                  </td>
                  <td className="py-2.5 px-2 text-terminal-dim">{s.asset_class}</td>
                  <td className="py-2.5 px-2 text-center">
                    <SignalBadge signal={s.signal} size="sm" />
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                    {s.composite_score.toFixed(1)}
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono" style={{
                    color: s.technical_score > 70 ? '#00FF41' : s.technical_score > 40 ? '#FFB800' : '#FF073A'
                  }}>
                    {s.technical_score.toFixed(1)}
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                    {s.fundamental_score.toFixed(1)}
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                    ${s.entry_price.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono text-terminal-red">
                    ${s.stop_loss.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono text-terminal-green">
                    ${s.target_price.toFixed(2)}
                  </td>
                  <td className="py-2.5 px-2 text-right font-mono text-terminal-amber">
                    {s.rr_ratio.toFixed(1)}
                  </td>
                  <td className="py-2.5 px-4 text-right font-mono text-terminal-dim">
                    {s.position_size_dollars ? `$${s.position_size_dollars.toLocaleString()}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filtered.length > 100 && (
          <div className="text-center py-3 text-[10px] text-terminal-dim border-t border-terminal-border">
            Showing 100 of {filtered.length} — refine filters to see more
          </div>
        )}
      </div>
    </div>
  );
}
