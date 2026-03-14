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
  type ConsensusBlindspotSignal,
} from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import ConvergenceHeatmap from '@/components/ConvergenceHeatmap';

// ── Helpers ──
function regimeClass(regime: string) {
  if (regime.includes('strong_risk_on')) return 'regime-strong-risk-on';
  if (regime.includes('risk_on')) return 'regime-risk-on';
  if (regime.includes('strong_risk_off')) return 'regime-strong-risk-off';
  if (regime.includes('risk_off')) return 'regime-risk-off';
  return 'regime-neutral';
}

function scoreColor(v: number) {
  if (v >= 70) return '#00FF41';
  if (v >= 40) return '#FFB800';
  return '#FF073A';
}

function gapTypeBadge(gapType: string) {
  switch (gapType) {
    case 'contrarian_bullish':
      return { label: 'CONTRARIAN BULL', cls: 'bg-terminal-green/12 text-terminal-green border-terminal-green/25' };
    case 'ahead_of_consensus':
      return { label: 'AHEAD OF STREET', cls: 'bg-terminal-cyan/12 text-terminal-cyan border-terminal-cyan/25' };
    case 'crowded_agreement':
      return { label: 'CROWDED', cls: 'bg-terminal-red/12 text-terminal-red border-terminal-red/25' };
    case 'contrarian_bearish_warning':
      return { label: 'BEARISH WARNING', cls: 'bg-terminal-red/15 text-terminal-red border-terminal-red/30' };
    default:
      return { label: gapType?.replace(/_/g, ' ').toUpperCase() || 'N/A', cls: 'bg-terminal-dim/10 text-terminal-dim border-terminal-dim/20' };
  }
}

// ── Module Agreement Bar ──
function ModuleBar({ convergence }: { convergence: ConvergenceSignal }) {
  const modules = [
    { key: 'main_signal_score', w: 3 },
    { key: 'smartmoney_score', w: 15 },
    { key: 'worldview_score', w: 13 },
    { key: 'variant_score', w: 9 },
    { key: 'research_score', w: 6 },
    { key: 'foreign_intel_score', w: 7 },
    { key: 'news_displacement_score', w: 6 },
    { key: 'sector_expert_score', w: 5 },
    { key: 'pairs_score', w: 5 },
    { key: 'ma_score', w: 5 },
    { key: 'energy_intel_score', w: 5 },
    { key: 'prediction_markets_score', w: 5 },
    { key: 'pattern_options_score', w: 4 },
    { key: 'estimate_momentum_score', w: 4 },
    { key: 'ai_regulatory_score', w: 3 },
    { key: 'consensus_blindspots_score', w: 4 },
    { key: 'alt_data_score', w: 2 },
  ];

  let bullW = 0, bearW = 0, neutW = 0;
  modules.forEach(m => {
    const val = (convergence as any)[m.key];
    if (val == null || val === 0) { neutW += m.w; return; }
    if (val >= 50) bullW += m.w;
    else if (val < 25) bearW += m.w;
    else neutW += m.w;
  });
  const total = bullW + bearW + neutW || 1;

  return (
    <div className="flex h-1.5 rounded-full overflow-hidden bg-terminal-muted" title={`Bull: ${bullW}% | Bear: ${bearW}% | Neutral: ${neutW}%`}>
      {bullW > 0 && (
        <div className="bg-terminal-green" style={{ width: `${(bullW / total) * 100}%` }} />
      )}
      {neutW > 0 && (
        <div className="bg-terminal-dim/30" style={{ width: `${(neutW / total) * 100}%` }} />
      )}
      {bearW > 0 && (
        <div className="bg-terminal-red" style={{ width: `${(bearW / total) * 100}%` }} />
      )}
    </div>
  );
}

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

export default function HomePage() {
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [breadth, setBreadth] = useState<Breadth | null>(null);
  const [summary, setSummary] = useState<{ signal: string; count: number }[]>([]);
  const [convergence, setConvergence] = useState<ConvergenceSignal[]>([]);
  const [topSignals, setTopSignals] = useState<Signal[]>([]);
  const [displacement, setDisplacement] = useState<DisplacementSignal[]>([]);
  const [runners, setRunners] = useState<PairSignal[]>([]);
  const [sectorExperts, setSectorExperts] = useState<SectorExpertSignal[]>([]);
  const [fatPitches, setFatPitches] = useState<ConsensusBlindspotSignal[]>([]);
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
      api.fatPitches(),
    ]).then(([m, b, s, c, t, d, r, se, fp]) => {
      if (m.status === 'fulfilled') setMacro(m.value);
      if (b.status === 'fulfilled') setBreadth(b.value);
      if (s.status === 'fulfilled') setSummary(s.value);
      if (c.status === 'fulfilled') setConvergence(c.value);
      if (t.status === 'fulfilled') setTopSignals(t.value);
      if (d.status === 'fulfilled') setDisplacement(d.value);
      if (r.status === 'fulfilled') setRunners(r.value);
      if (se.status === 'fulfilled') setSectorExperts(se.value);
      if (fp.status === 'fulfilled') setFatPitches(fp.value);
      setLoading(false);
    });
  }, []);

  // ── Build cross-signal clusters ──
  const clusters: ClusterStock[] = (() => {
    const map = new Map<string, ClusterStock>();
    const getOrCreate = (symbol: string): ClusterStock =>
      map.get(symbol) || { symbol, sources: [], convergenceScore: null, conviction: null, narrative: null, displacementScore: null, pairsDirection: null, sectorDirection: null };

    convergence.slice(0, 30).forEach(c => {
      const s = getOrCreate(c.symbol);
      s.sources.push('CONVERGENCE');
      s.convergenceScore = c.convergence_score;
      s.conviction = c.conviction_level;
      s.narrative = c.narrative;
      map.set(c.symbol, s);
    });
    displacement.forEach(d => {
      const s = getOrCreate(d.symbol);
      if (!s.sources.includes('DISPLACEMENT')) s.sources.push('DISPLACEMENT');
      s.displacementScore = Math.max(s.displacementScore ?? 0, d.displacement_score);
      map.set(d.symbol, s);
    });
    runners.forEach(r => {
      const sym = r.runner_symbol || r.symbol_a;
      const s = getOrCreate(sym);
      if (!s.sources.includes('PAIRS')) s.sources.push('PAIRS');
      s.pairsDirection = r.direction;
      map.set(sym, s);
    });
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

  // Action table: top signals enriched with convergence
  const actionStocks = topSignals.map(sig => {
    const conv = convergence.find(c => c.symbol === sig.symbol);
    return { ...sig, conv };
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-center">
          <p className="text-terminal-green glow-green font-display text-lg tracking-widest animate-pulse-green">
            SYNTHESIZING SIGNALS...
          </p>
          <p className="text-[10px] text-terminal-dim mt-2 tracking-widest">
            18 MODULES · CONVERGENCE · DISPLACEMENT · PAIRS · FAT PITCHES
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ═══ A: COMMAND STRIP ═══ */}
      <div className="flex items-center gap-4 flex-wrap">
        {/* Regime pill */}
        {macro && (
          <div className={regimeClass(macro.regime)}>
            {macro.regime.replace(/_/g, ' ').toUpperCase()}
            <span className="ml-2 opacity-70">{macro.total_score.toFixed(0)}</span>
          </div>
        )}

        {/* Breadth micro-gauge */}
        {breadth && (
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-terminal-dim tracking-wider">BREADTH</span>
            <div className="w-24 h-1.5 bg-terminal-muted rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${breadth.pct_above_200dma}%`,
                  backgroundColor: breadth.pct_above_200dma > 50 ? '#00FF41' : '#FF073A',
                }}
              />
            </div>
            <span className={`text-[10px] font-mono ${breadth.pct_above_200dma > 50 ? 'text-terminal-green' : 'text-terminal-red'}`}>
              {breadth.pct_above_200dma.toFixed(0)}%
            </span>
          </div>
        )}

        {/* Spacer */}
        <div className="flex-1" />

        {/* Signal distribution */}
        <div className="flex gap-3">
          {summary.map(s => (
            <div key={s.signal} className="flex items-center gap-1.5">
              <SignalBadge signal={s.signal} size="sm" />
              <span className="text-[11px] font-mono text-terminal-text font-bold">{s.count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ═══ B: TOP ACTIONS + FAT PITCHES ═══ */}
      <div className="grid grid-cols-5 gap-4">

        {/* Left: Top 6 Action Cards */}
        <div className="col-span-3 space-y-3">
          <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
            Highest Conviction Setups
          </h2>
          <div className="grid grid-cols-3 gap-3">
            {actionStocks.slice(0, 6).map(s => (
              <a
                key={s.symbol}
                href={`/asset/${s.symbol}`}
                className="panel p-4 hover:border-terminal-green/30 transition-all group"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-display font-bold text-terminal-bright group-hover:text-terminal-green transition-colors">
                    {s.symbol}
                  </span>
                  <SignalBadge signal={s.signal} size="sm" />
                </div>

                {/* Convergence score */}
                {s.conv && (
                  <div className="flex items-baseline gap-2 mb-2">
                    <span
                      className="text-xl font-display font-bold"
                      style={{ color: scoreColor(s.conv.convergence_score) }}
                    >
                      {s.conv.convergence_score.toFixed(1)}
                    </span>
                    <span className="text-[9px] text-terminal-dim">CONV</span>
                    <span className={`text-[9px] font-bold tracking-wider ${
                      s.conv.conviction_level === 'high' ? 'text-terminal-green' :
                      s.conv.conviction_level === 'medium' ? 'text-terminal-amber' : 'text-terminal-dim'
                    }`}>
                      {s.conv.conviction_level?.toUpperCase()}
                    </span>
                  </div>
                )}

                {/* Module agreement bar */}
                {s.conv && <ModuleBar convergence={s.conv} />}

                {/* Metrics row */}
                <div className="grid grid-cols-3 gap-2 text-[9px] mt-2">
                  <div>
                    <span className="text-terminal-dim">Score</span>
                    <div className="text-terminal-text font-mono">{s.composite_score.toFixed(0)}</div>
                  </div>
                  <div>
                    <span className="text-terminal-dim">R:R</span>
                    <div className="text-terminal-amber font-mono">{s.rr_ratio.toFixed(1)}</div>
                  </div>
                  <div>
                    <span className="text-terminal-dim">Entry</span>
                    <div className="text-terminal-text font-mono">${s.entry_price.toFixed(0)}</div>
                  </div>
                </div>

                {/* Narrative */}
                {s.conv?.narrative && (
                  <p className="text-[8px] text-terminal-dim mt-2 line-clamp-1 leading-relaxed">
                    {s.conv.narrative}
                  </p>
                )}
              </a>
            ))}
          </div>
        </div>

        {/* Right: Fat Pitch Spotlight */}
        <div className="col-span-2 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
              Fat Pitches
            </h2>
            <a href="/consensus-blindspots" className="text-[9px] text-terminal-cyan hover:text-terminal-green transition-colors">
              VIEW ALL →
            </a>
          </div>

          {fatPitches.length === 0 ? (
            <div className="panel p-6 text-center">
              <p className="text-terminal-dim text-[11px]">No fat pitches detected today.</p>
              <p className="text-terminal-dim text-[9px] mt-1">Extreme fear + undervaluation + smart money convergence = fat pitch</p>
            </div>
          ) : (
            <div className="space-y-2">
              {fatPitches.slice(0, 6).map(fp => {
                const badge = gapTypeBadge(fp.gap_type);
                return (
                  <a
                    key={fp.symbol}
                    href={`/asset/${fp.symbol}`}
                    className="panel p-3 block hover:border-terminal-green/30 transition-colors group"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-terminal-bright text-sm group-hover:text-terminal-green transition-colors">
                          {fp.symbol}
                        </span>
                        <span className={`text-[8px] px-1.5 py-0.5 rounded-sm font-bold border ${badge.cls}`}>
                          {badge.label}
                        </span>
                      </div>
                      <span
                        className="text-lg font-display font-bold"
                        style={{ color: scoreColor(fp.cbs_score) }}
                      >
                        {fp.cbs_score.toFixed(0)}
                      </span>
                    </div>

                    {/* Fat pitch conditions */}
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[9px] text-terminal-amber font-mono">
                        {fp.fat_pitch_count} condition{fp.fat_pitch_count !== 1 ? 's' : ''} met
                      </span>
                      {fp.fat_pitch_conditions && (
                        <span className="text-[8px] text-terminal-dim truncate">
                          {fp.fat_pitch_conditions}
                        </span>
                      )}
                    </div>

                    {/* Positioning context */}
                    <div className="flex gap-3 text-[8px] text-terminal-dim">
                      {fp.short_interest_pct != null && (
                        <span>SI: {fp.short_interest_pct.toFixed(1)}%</span>
                      )}
                      {fp.analyst_buy_pct != null && (
                        <span>Buy: {fp.analyst_buy_pct.toFixed(0)}%</span>
                      )}
                      {fp.our_convergence_score != null && (
                        <span>Conv: {fp.our_convergence_score.toFixed(0)}</span>
                      )}
                    </div>

                    {fp.narrative && (
                      <p className="text-[8px] text-terminal-dim mt-1 line-clamp-1">{fp.narrative}</p>
                    )}
                  </a>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ═══ C: CONVERGENCE HEATMAP ═══ */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
            Convergence Heatmap
          </h2>
          <div className="flex items-center gap-4 text-[9px] text-terminal-dim">
            <span>{convergence.length} stocks · 18 modules</span>
            <a href="/synthesis" className="text-terminal-cyan hover:text-terminal-green transition-colors">
              FULL VIEW →
            </a>
          </div>
        </div>
        {convergence.length > 0 ? (
          <ConvergenceHeatmap data={convergence} />
        ) : (
          <div className="panel p-6 text-center text-[11px] text-terminal-dim">
            No convergence data. Run the daily pipeline first.
          </div>
        )}
      </div>

      {/* ═══ D: CROSS-SIGNAL CLUSTERS ═══ */}
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
          <div className="grid grid-cols-4 gap-3">
            {clusters.slice(0, 8).map(c => (
              <a
                key={c.symbol}
                href={`/asset/${c.symbol}`}
                className="panel p-3 hover:border-terminal-green/30 transition-colors group"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-mono font-bold text-terminal-bright text-sm group-hover:text-terminal-green transition-colors">
                    {c.symbol}
                  </span>
                  <div className="flex gap-1">
                    {c.sources.map(src => (
                      <span
                        key={src}
                        className={`text-[7px] px-1 py-0.5 rounded-sm font-bold tracking-wider border ${
                          src === 'CONVERGENCE' ? 'bg-terminal-green/10 text-terminal-green border-terminal-green/20' :
                          src === 'DISPLACEMENT' ? 'bg-terminal-cyan/10 text-terminal-cyan border-terminal-cyan/20' :
                          src === 'PAIRS' ? 'bg-terminal-amber/10 text-terminal-amber border-terminal-amber/20' :
                          'bg-terminal-bright/10 text-terminal-bright border-terminal-bright/20'
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
                      <span className="text-terminal-dim">Conv.</span>
                      <div className={`font-mono ${
                        c.conviction === 'high' ? 'text-terminal-green' :
                        c.conviction === 'medium' ? 'text-terminal-amber' : 'text-terminal-dim'
                      }`}>
                        {c.conviction.toUpperCase()}
                      </div>
                    </div>
                  )}
                </div>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* ═══ E: ACTION TABLE ═══ */}
      {actionStocks.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
              Full Action Table
            </h2>
            <span className="text-[9px] text-terminal-dim">
              Top {actionStocks.length} STRONG BUY · click row to expand
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
                    <th className="text-right py-3 px-2 font-normal">Mod</th>
                    <th className="text-right py-3 px-2 font-normal">Entry</th>
                    <th className="text-right py-3 px-2 font-normal">Stop</th>
                    <th className="text-right py-3 px-2 font-normal">Target</th>
                    <th className="text-right py-3 px-2 font-normal">R:R</th>
                    <th className="text-right py-3 px-4 font-normal">Size</th>
                  </tr>
                </thead>
                <tbody>
                  {actionStocks.map((s, i) => (
                    <>
                      <tr
                        key={s.symbol}
                        className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                        onClick={() => setExpandedAction(expandedAction === s.symbol ? null : s.symbol)}
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
                        <td className="py-2.5 px-2 text-right font-mono" style={{ color: s.conv ? scoreColor(s.conv.convergence_score) : '#555' }}>
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
                          {s.position_size_dollars ? `$${(s.position_size_dollars / 1000).toFixed(0)}K` : '—'}
                        </td>
                      </tr>
                      {expandedAction === s.symbol && s.conv && (
                        <tr key={`${s.symbol}-exp`} className="bg-terminal-bg/50">
                          <td colSpan={10} className="px-4 py-3">
                            <div className="grid grid-cols-2 gap-4">
                              <div>
                                <div className="text-[9px] text-terminal-dim tracking-wider mb-1">NARRATIVE</div>
                                <p className="text-[10px] text-terminal-text leading-relaxed">
                                  {s.conv.narrative || 'No narrative available.'}
                                </p>
                              </div>
                              <div>
                                <div className="text-[9px] text-terminal-dim tracking-wider mb-1">ALL 18 MODULE SCORES</div>
                                <div className="grid grid-cols-6 gap-x-3 gap-y-1 text-[9px]">
                                  {[
                                    ['Signal', s.conv.main_signal_score],
                                    ['Smart$', s.conv.smartmoney_score],
                                    ['World', s.conv.worldview_score],
                                    ['Variant', s.conv.variant_score],
                                    ['Research', s.conv.research_score],
                                    ['F.Intel', s.conv.foreign_intel_score],
                                    ['Displ', s.conv.news_displacement_score],
                                    ['Sector', s.conv.sector_expert_score],
                                    ['Pairs', s.conv.pairs_score],
                                    ['M&A', (s.conv as any).ma_score],
                                    ['Energy', (s.conv as any).energy_intel_score],
                                    ['Pred', (s.conv as any).prediction_markets_score],
                                    ['Pattern', (s.conv as any).pattern_options_score],
                                    ['Est.M', (s.conv as any).estimate_momentum_score],
                                    ['Reg', (s.conv as any).ai_regulatory_score],
                                    ['CBS', (s.conv as any).consensus_blindspots_score],
                                    ['Alt', s.conv.alt_data_score],
                                    ['Reddit', s.conv.reddit_score],
                                  ].map(([label, val]) => (
                                    <div key={label as string} className="flex justify-between">
                                      <span className="text-terminal-dim">{label}</span>
                                      <span className={`font-mono ${
                                        val && (val as number) >= 50 ? 'text-terminal-green' :
                                        val && (val as number) >= 25 ? 'text-terminal-amber' :
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
