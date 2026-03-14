'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type MacroData,
  type Breadth,
  type ConvergenceSignal,
  type Signal,
  type DisplacementSignal,
  type PairSignal,
  type SectorExpertSignal,
} from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import ConvergenceHeatmap from '@/components/ConvergenceHeatmap';

// ── Cross-signal cluster type ──
interface ClusterStock {
  symbol: string;
  sources: string[];
  convergenceScore: number | null;
  conviction: string | null;
  narrative: string | null;
  displacementScore: number | null;
  pairsDirection: string | null;
  sectorDirection: string | null;
}

export default function SynthesisPage() {
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
    Promise.allSettled([
      api.macro(),
      api.breadth(),
      api.signalSummary(),
      api.convergence(),
      api.signals({ signal: 'STRONG BUY', sort_by: 'composite_score', limit: '15' }),
      api.displacement(7),
      api.pairs({ signal_type: 'runner' }),
      api.sectorExperts(),
    ]).then(([m, b, s, c, t, d, r, se]) => {
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

  // ── Build cross-signal clusters ──
  const clusters: ClusterStock[] = (() => {
    const map = new Map<string, ClusterStock>();

    const getOrCreate = (symbol: string): ClusterStock =>
      map.get(symbol) || {
        symbol,
        sources: [],
        convergenceScore: null,
        conviction: null,
        narrative: null,
        displacementScore: null,
        pairsDirection: null,
        sectorDirection: null,
      };

    // Convergence (top 30)
    convergence.slice(0, 30).forEach(c => {
      const s = getOrCreate(c.symbol);
      s.sources.push('CONVERGENCE');
      s.convergenceScore = c.convergence_score;
      s.conviction = c.conviction_level;
      s.narrative = c.narrative;
      map.set(c.symbol, s);
    });

    // Displacement
    displacement.forEach(d => {
      const s = getOrCreate(d.symbol);
      if (!s.sources.includes('DISPLACEMENT')) s.sources.push('DISPLACEMENT');
      s.displacementScore = Math.max(s.displacementScore ?? 0, d.displacement_score);
      map.set(d.symbol, s);
    });

    // Pairs runners
    runners.forEach(r => {
      const sym = r.runner_symbol || r.symbol_a;
      const s = getOrCreate(sym);
      if (!s.sources.includes('PAIRS')) s.sources.push('PAIRS');
      s.pairsDirection = r.direction;
      map.set(sym, s);
    });

    // Sector experts
    sectorExperts.forEach(se => {
      const s = getOrCreate(se.symbol);
      if (!s.sources.includes('SECTOR')) s.sources.push('SECTOR');
      s.sectorDirection = se.direction;
      map.set(se.symbol, s);
    });

    return Array.from(map.values())
      .filter(s => s.sources.length >= 2)
      .sort((a, b) => b.sources.length - a.sources.length || (b.convergenceScore ?? 0) - (a.convergenceScore ?? 0));
  })();

  // ── Merge action table: top signals enriched with convergence data ──
  const actionStocks = topSignals.map(sig => {
    const conv = convergence.find(c => c.symbol === sig.symbol);
    return { ...sig, conv };
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-terminal-green glow-green font-display text-lg tracking-widest animate-pulse-green">
            SYNTHESIZING SIGNALS...
          </p>
          <p className="text-[10px] text-terminal-dim mt-2 tracking-widest">
            CONVERGENCE / DISPLACEMENT / PAIRS / SECTOR EXPERTS
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* ═══ SECTION 1: Market Context Bar ═══ */}
      <div>
        <div className="flex items-end justify-between mb-4">
          <div>
            <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
              SYNTHESIS
            </h1>
            <p className="text-[10px] text-terminal-dim tracking-widest mt-1 uppercase">
              All signals converged into one view — what deserves attention now
            </p>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-3">
          {/* Macro regime */}
          <div className="panel p-4">
            <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">Macro Regime</div>
            {macro ? (
              <>
                <div className={`text-xl font-display font-bold ${
                  macro.total_score >= 60 ? 'text-terminal-green' :
                  macro.total_score >= 40 ? 'text-terminal-amber' : 'text-terminal-red'
                }`}>
                  {macro.total_score.toFixed(0)}
                </div>
                <div className={`text-[9px] font-bold tracking-widest mt-1 ${
                  macro.regime.includes('risk_on') ? 'text-terminal-green' :
                  macro.regime.includes('risk_off') ? 'text-terminal-red' : 'text-terminal-amber'
                }`}>
                  {macro.regime.replace(/_/g, ' ').toUpperCase()}
                </div>
              </>
            ) : (
              <div className="text-terminal-dim text-[10px]">No data</div>
            )}
          </div>

          {/* Breadth */}
          <div className="panel p-4">
            <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">Market Breadth</div>
            {breadth ? (
              <>
                <div className={`text-xl font-display font-bold ${
                  breadth.pct_above_200dma > 50 ? 'text-terminal-green' : 'text-terminal-red'
                }`}>
                  {breadth.pct_above_200dma.toFixed(1)}%
                </div>
                <div className="text-[9px] text-terminal-dim mt-1">
                  A/D {breadth.advance_decline_ratio.toFixed(2)} · H/L {breadth.new_highs}/{breadth.new_lows}
                </div>
              </>
            ) : (
              <div className="text-terminal-dim text-[10px]">No data</div>
            )}
          </div>

          {/* Convergence summary */}
          <div className="panel p-4">
            <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">Convergence</div>
            <div className="text-xl font-display font-bold text-terminal-cyan">
              {convergence.length}
            </div>
            <div className="text-[9px] text-terminal-dim mt-1">
              {convergence.filter(c => c.conviction_level === 'high').length} high conviction
            </div>
          </div>

          {/* Signal distribution */}
          <div className="panel p-4">
            <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-2">Signals</div>
            <div className="flex gap-2">
              {summary.map(s => (
                <div key={s.signal} className="text-center">
                  <div className="text-sm font-display font-bold text-terminal-text">{s.count}</div>
                  <SignalBadge signal={s.signal} size="sm" />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ═══ SECTION 2: Convergence Heatmap ═══ */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
            Convergence Heatmap
          </h2>
          <span className="text-[9px] text-terminal-dim">
            {convergence.length} stocks · 11 modules · click to expand narrative
          </span>
        </div>
        {convergence.length > 0 ? (
          <ConvergenceHeatmap data={convergence} />
        ) : (
          <div className="panel p-6 text-center text-[11px] text-terminal-dim">
            No convergence data. Run the daily pipeline first.
          </div>
        )}
      </div>

      {/* ═══ SECTION 3: Cross-Signal Clusters ═══ */}
      {clusters.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
              Cross-Signal Clusters
            </h2>
            <span className="text-[9px] text-terminal-dim">
              {clusters.length} stocks with 2+ signal sources
            </span>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {clusters.slice(0, 12).map(c => (
              <a
                key={c.symbol}
                href={`/asset/${c.symbol}`}
                className="panel p-4 hover:border-terminal-green/30 transition-colors group"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-terminal-bright text-sm group-hover:text-terminal-green transition-colors">
                    {c.symbol}
                  </span>
                  <div className="flex gap-1">
                    {c.sources.map(src => (
                      <span
                        key={src}
                        className={`text-[7px] px-1.5 py-0.5 rounded-sm font-bold tracking-wider ${
                          src === 'CONVERGENCE' ? 'bg-terminal-green/10 text-terminal-green border border-terminal-green/20' :
                          src === 'DISPLACEMENT' ? 'bg-terminal-cyan/10 text-terminal-cyan border border-terminal-cyan/20' :
                          src === 'PAIRS' ? 'bg-terminal-amber/10 text-terminal-amber border border-terminal-amber/20' :
                          'bg-terminal-bright/10 text-terminal-bright border border-terminal-bright/20'
                        }`}
                      >
                        {src}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2 text-[9px]">
                  {c.convergenceScore !== null && (
                    <div>
                      <span className="text-terminal-dim">Conv</span>
                      <div className="text-terminal-green font-mono">{c.convergenceScore.toFixed(1)}</div>
                    </div>
                  )}
                  {c.displacementScore !== null && (
                    <div>
                      <span className="text-terminal-dim">Displ</span>
                      <div className="text-terminal-cyan font-mono">{c.displacementScore.toFixed(0)}</div>
                    </div>
                  )}
                  {c.conviction && (
                    <div>
                      <span className="text-terminal-dim">Conviction</span>
                      <div className={`font-mono ${
                        c.conviction === 'high' ? 'text-terminal-green' :
                        c.conviction === 'medium' ? 'text-terminal-amber' : 'text-terminal-dim'
                      }`}>
                        {c.conviction.toUpperCase()}
                      </div>
                    </div>
                  )}
                </div>
                {c.narrative && (
                  <p className="text-[8px] text-terminal-dim mt-2 line-clamp-2 leading-relaxed">
                    {c.narrative}
                  </p>
                )}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* ═══ SECTION 4: Action Table ═══ */}
      {actionStocks.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
              Highest Conviction Actions
            </h2>
            <span className="text-[9px] text-terminal-dim">
              Top {actionStocks.length} STRONG BUY setups ranked by composite score
            </span>
          </div>
          <div className="panel overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                    <th className="text-left py-3 px-4 font-normal">Symbol</th>
                    <th className="text-center py-3 px-2 font-normal">Signal</th>
                    <th className="text-right py-3 px-2 font-normal">Composite</th>
                    <th className="text-right py-3 px-2 font-normal">Conv.</th>
                    <th className="text-right py-3 px-2 font-normal">Modules</th>
                    <th className="text-right py-3 px-2 font-normal">Entry</th>
                    <th className="text-right py-3 px-2 font-normal">Stop</th>
                    <th className="text-right py-3 px-2 font-normal">Target</th>
                    <th className="text-right py-3 px-2 font-normal">R:R</th>
                    <th className="text-right py-3 px-4 font-normal">Size $</th>
                  </tr>
                </thead>
                <tbody>
                  {actionStocks.map((s, i) => (
                    <>
                      <tr
                        key={s.symbol}
                        className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                        onClick={() => setExpandedAction(expandedAction === s.symbol ? null : s.symbol)}
                        style={{ animationDelay: `${i * 20}ms` }}
                      >
                        <td className="py-2.5 px-4">
                          <a
                            href={`/asset/${s.symbol}`}
                            className="font-mono font-bold text-terminal-bright hover:text-terminal-green transition-colors"
                            onClick={e => e.stopPropagation()}
                          >
                            {s.symbol}
                          </a>
                        </td>
                        <td className="py-2.5 px-2 text-center">
                          <SignalBadge signal={s.signal} size="sm" />
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                          {s.composite_score.toFixed(1)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-green">
                          {s.conv?.convergence_score?.toFixed(1) ?? '—'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                          {s.conv?.module_count ?? '—'}
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
                      {expandedAction === s.symbol && s.conv && (
                        <tr key={`${s.symbol}-narrative`} className="bg-terminal-bg/50">
                          <td colSpan={10} className="px-4 py-3">
                            <div className="grid grid-cols-2 gap-4">
                              <div>
                                <div className="text-[9px] text-terminal-dim tracking-wider mb-1">NARRATIVE</div>
                                <p className="text-[10px] text-terminal-text leading-relaxed">
                                  {s.conv.narrative || 'No narrative available.'}
                                </p>
                              </div>
                              <div>
                                <div className="text-[9px] text-terminal-dim tracking-wider mb-1">MODULE SCORES</div>
                                <div className="grid grid-cols-4 gap-x-4 gap-y-1 text-[9px]">
                                  {[
                                    ['Signal', s.conv.main_signal_score],
                                    ['Smart$', s.conv.smartmoney_score],
                                    ['World', s.conv.worldview_score],
                                    ['Variant', s.conv.variant_score],
                                    ['Research', s.conv.research_score],
                                    ['Reddit', s.conv.reddit_score],
                                    ['F.Intel', s.conv.foreign_intel_score],
                                    ['Displ', s.conv.news_displacement_score],
                                    ['Alt', s.conv.alt_data_score],
                                    ['Sector', s.conv.sector_expert_score],
                                    ['Pairs', s.conv.pairs_score],
                                  ].map(([label, val]) => (
                                    <div key={label as string} className="flex justify-between">
                                      <span className="text-terminal-dim">{label}</span>
                                      <span className={`font-mono ${
                                        val && (val as number) >= 70 ? 'text-terminal-green' :
                                        val && (val as number) >= 40 ? 'text-terminal-amber' :
                                        val ? 'text-terminal-red' : 'text-terminal-dim'
                                      }`}>
                                        {val != null ? (val as number).toFixed(0) : '—'}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
