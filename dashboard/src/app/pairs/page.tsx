'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type PairSignal,
  type PairRelationship,
  type PairSpread,
} from '@/lib/api';
import SpreadChart from '@/components/SpreadChart';

type Tab = 'runners' | 'mean_reversion' | 'explorer';

export default function PairsPage() {
  const [runners, setRunners] = useState<PairSignal[]>([]);
  const [mrSignals, setMrSignals] = useState<PairSignal[]>([]);
  const [relationships, setRelationships] = useState<PairRelationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('runners');
  const [sectorFilter, setSectorFilter] = useState<string>('');

  // Spread chart state
  const [expandedPair, setExpandedPair] = useState<string | null>(null);
  const [spreadData, setSpreadData] = useState<PairSpread[]>([]);
  const [spreadLoading, setSpreadLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      api.pairs({ signal_type: 'runner' }).catch(() => []),
      api.pairs({ signal_type: 'mean_reversion' }).catch(() => []),
      api.pairRelationships().catch(() => []),
    ]).then(([r, mr, rel]) => {
      setRunners(r);
      setMrSignals(mr);
      setRelationships(rel);
      setLoading(false);
    });
  }, []);

  const loadSpread = async (symbolA: string, symbolB: string) => {
    const key = `${symbolA}-${symbolB}`;
    if (expandedPair === key) {
      setExpandedPair(null);
      return;
    }
    setSpreadLoading(true);
    setExpandedPair(key);
    try {
      const data = await api.pairSpread(symbolA, symbolB);
      setSpreadData(data);
    } catch {
      setSpreadData([]);
    }
    setSpreadLoading(false);
  };

  const sectors = Array.from(new Set(relationships.map(r => r.sector).filter(Boolean))) as string[];

  const filteredRelationships = sectorFilter
    ? relationships.filter(r => r.sector === sectorFilter)
    : relationships;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          SCANNING COINTEGRATED PAIRS...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          PAIRS TRADING / STAT ARB
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          COINTEGRATED PAIRS + MOMENTUM DIVERGENCE RUNNERS
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3">
        <div
          onClick={() => setActiveTab('runners')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'runners' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-green">
            {runners.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            RUNNERS DETECTED
          </div>
        </div>
        <div
          onClick={() => setActiveTab('mean_reversion')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'mean_reversion' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-cyan">
            {mrSignals.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            MEAN-REVERSION PAIRS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('explorer')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'explorer' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-text">
            {relationships.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            COINTEGRATED PAIRS
          </div>
        </div>
      </div>

      {/* Runners Tab */}
      {activeTab === 'runners' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              RUNNER DETECTION
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Stocks breaking away from cointegrated peers with strong technicals + fundamentals
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Runner</th>
                  <th className="text-left py-3 px-2 font-normal">Laggard</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">Z-Score</th>
                  <th className="text-right py-3 px-2 font-normal">Tech</th>
                  <th className="text-right py-3 px-2 font-normal">Fund</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {runners.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-terminal-dim">
                      No active runner signals. Run the pipeline to detect them.
                    </td>
                  </tr>
                ) : (
                  runners.map((s, i) => {
                    const laggard = s.runner_symbol === s.symbol_a ? s.symbol_b : s.symbol_a;
                    return (
                      <tr
                        key={`${s.runner_symbol}-${s.date}-${i}`}
                        className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                        onClick={() => (window.location.href = `/asset/${s.runner_symbol}`)}
                      >
                        <td className="py-2.5 px-4 font-mono font-bold text-terminal-green">
                          {s.runner_symbol}
                        </td>
                        <td className="py-2.5 px-2 font-mono text-terminal-dim">
                          {laggard}
                        </td>
                        <td className="py-2.5 px-2 text-terminal-dim text-[10px] tracking-wider uppercase">
                          {s.sector || '—'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono">
                          <span
                            className={
                              Math.abs(s.spread_zscore) >= 2
                                ? 'text-terminal-red'
                                : 'text-terminal-amber'
                            }
                          >
                            {s.spread_zscore > 0 ? '+' : ''}
                            {s.spread_zscore.toFixed(1)}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-green">
                          {s.runner_tech_score?.toFixed(0) || '—'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                          {s.runner_fund_score?.toFixed(0) || '—'}
                        </td>
                        <td className="py-2.5 px-2 text-right">
                          <span
                            className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                            style={{
                              backgroundColor:
                                s.pairs_score >= 70
                                  ? 'rgba(0,255,65,0.15)'
                                  : s.pairs_score >= 50
                                  ? 'rgba(255,184,0,0.15)'
                                  : 'rgba(255,255,255,0.05)',
                              color:
                                s.pairs_score >= 70
                                  ? '#00FF41'
                                  : s.pairs_score >= 50
                                  ? '#FFB800'
                                  : '#888',
                            }}
                          >
                            {s.pairs_score.toFixed(0)}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 text-terminal-dim max-w-[320px] truncate">
                          {s.narrative}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Mean-Reversion Tab */}
      {activeTab === 'mean_reversion' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              MEAN-REVERSION PAIRS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Market-neutral long/short — cointegrated spread &gt; 2&sigma; from mean
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Pair</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">Z-Score</th>
                  <th className="text-right py-3 px-2 font-normal">Hedge</th>
                  <th className="text-right py-3 px-2 font-normal">Half-Life</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-center py-3 px-2 font-normal">Direction</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {mrSignals.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-terminal-dim">
                      No active mean-reversion signals. Run the pipeline to detect them.
                    </td>
                  </tr>
                ) : (
                  mrSignals.map((s, i) => (
                    <tr
                      key={`${s.symbol_a}-${s.symbol_b}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => loadSpread(s.symbol_a, s.symbol_b)}
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-bright">
                        {s.symbol_a}{' '}
                        <span className="text-terminal-dim">/</span>{' '}
                        {s.symbol_b}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[10px] tracking-wider uppercase">
                        {s.sector || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-red">
                        {s.spread_zscore > 0 ? '+' : ''}
                        {s.spread_zscore.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {s.hedge_ratio.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {s.half_life_days.toFixed(0)}d
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span
                          className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                          style={{
                            backgroundColor:
                              s.pairs_score >= 70
                                ? 'rgba(0,229,255,0.15)'
                                : s.pairs_score >= 50
                                ? 'rgba(255,184,0,0.15)'
                                : 'rgba(255,255,255,0.05)',
                            color:
                              s.pairs_score >= 70
                                ? '#00E5FF'
                                : s.pairs_score >= 50
                                ? '#FFB800'
                                : '#888',
                          }}
                        >
                          {s.pairs_score.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        <span className="text-[10px] font-bold tracking-wider text-terminal-cyan">
                          {s.direction === 'long_a_short_b'
                            ? `L ${s.symbol_a} / S ${s.symbol_b}`
                            : `L ${s.symbol_b} / S ${s.symbol_a}`}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[280px] truncate">
                        {s.narrative}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Inline spread chart */}
          {expandedPair && (
            <div className="border-t border-terminal-border p-4">
              {spreadLoading ? (
                <div className="text-center py-8 text-terminal-dim animate-pulse">
                  Loading spread data...
                </div>
              ) : spreadData.length > 0 ? (
                <SpreadChart
                  data={spreadData}
                  symbolA={expandedPair.split('-')[0]}
                  symbolB={expandedPair.split('-')[1]}
                  height={250}
                />
              ) : (
                <div className="text-center py-8 text-terminal-dim">
                  No spread history available for this pair.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Pair Explorer Tab */}
      {activeTab === 'explorer' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border flex items-center justify-between">
            <div>
              <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
                PAIR EXPLORER
              </h2>
              <p className="text-[10px] text-terminal-dim mt-0.5">
                All cointegrated pairs sorted by statistical significance
              </p>
            </div>
            <select
              value={sectorFilter}
              onChange={e => setSectorFilter(e.target.value)}
              className="bg-terminal-bg border border-terminal-border text-terminal-text text-[11px] px-2 py-1 rounded-sm tracking-wider"
            >
              <option value="">ALL SECTORS</option>
              {sectors.sort().map(s => (
                <option key={s} value={s}>
                  {s.toUpperCase()}
                </option>
              ))}
            </select>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Pair</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">Corr 60d</th>
                  <th className="text-right py-3 px-2 font-normal">Corr 120d</th>
                  <th className="text-right py-3 px-2 font-normal">Coint p</th>
                  <th className="text-right py-3 px-2 font-normal">Hedge</th>
                  <th className="text-right py-3 px-2 font-normal">Half-Life</th>
                  <th className="text-right py-3 px-4 font-normal">Updated</th>
                </tr>
              </thead>
              <tbody>
                {filteredRelationships.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-terminal-dim">
                      No cointegrated pairs found. Run the pipeline to discover them.
                    </td>
                  </tr>
                ) : (
                  filteredRelationships.map((r, i) => (
                    <tr
                      key={`${r.symbol_a}-${r.symbol_b}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => loadSpread(r.symbol_a, r.symbol_b)}
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-bright">
                        {r.symbol_a}{' '}
                        <span className="text-terminal-dim">/</span>{' '}
                        {r.symbol_b}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[10px] tracking-wider uppercase">
                        {r.sector || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {r.correlation_60d.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {r.correlation_120d?.toFixed(2) || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono">
                        <span
                          className={
                            r.cointegration_pvalue < 0.01
                              ? 'text-terminal-green'
                              : r.cointegration_pvalue < 0.03
                              ? 'text-terminal-amber'
                              : 'text-terminal-text'
                          }
                        >
                          {r.cointegration_pvalue.toFixed(4)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {r.hedge_ratio.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {r.half_life_days.toFixed(0)}d
                      </td>
                      <td className="py-2.5 px-4 text-right text-terminal-dim text-[10px]">
                        {r.last_updated}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Inline spread chart for explorer */}
          {expandedPair && (
            <div className="border-t border-terminal-border p-4">
              {spreadLoading ? (
                <div className="text-center py-8 text-terminal-dim animate-pulse">
                  Loading spread data...
                </div>
              ) : spreadData.length > 0 ? (
                <SpreadChart
                  data={spreadData}
                  symbolA={expandedPair.split('-')[0]}
                  symbolB={expandedPair.split('-')[1]}
                  height={250}
                />
              ) : (
                <div className="text-center py-8 text-terminal-dim">
                  No spread history available for this pair.
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
