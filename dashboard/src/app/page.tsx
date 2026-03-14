'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type MacroData,
  type Breadth,
  type ConvergenceSignal,
  type ConvergenceDelta,
  type SignalChange,
  type Signal,
  type DisplacementSignal,
  type PairSignal,
  type SectorExpertSignal,
  type ConsensusBlindspotSignal,
  type HeatIndex,
} from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import ConvergenceHeatmap from '@/components/ConvergenceHeatmap';
import TradeRangeBar from '@/components/TradeRangeBar';
import ModuleStrip from '@/components/ModuleStrip';
import DailyDelta from '@/components/DailyDelta';
import Sparkline from '@/components/Sparkline';
import { scoreColor } from '@/lib/modules';

// ── Helpers ──
function regimeClass(regime: string) {
  if (regime.includes('strong_risk_on')) return 'regime-strong-risk-on';
  if (regime.includes('risk_on')) return 'regime-risk-on';
  if (regime.includes('strong_risk_off')) return 'regime-strong-risk-off';
  if (regime.includes('risk_off')) return 'regime-risk-off';
  return 'regime-neutral';
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

function convictionBorder(score: number | undefined) {
  if (!score) return '';
  if (score >= 80) return 'border-terminal-green/40 shadow-[0_0_12px_rgba(0,255,65,0.06)]';
  if (score >= 60) return 'border-terminal-green/20';
  return '';
}

// ── Cross-signal cluster type ──
interface ClusterStock {
  symbol: string;
  sector: string | null;
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
  const [heatIndex, setHeatIndex] = useState<HeatIndex | null>(null);
  const [summary, setSummary] = useState<{ signal: string; count: number }[]>([]);
  const [convergence, setConvergence] = useState<ConvergenceSignal[]>([]);
  const [topSignals, setTopSignals] = useState<Signal[]>([]);
  const [displacement, setDisplacement] = useState<DisplacementSignal[]>([]);
  const [runners, setRunners] = useState<PairSignal[]>([]);
  const [sectorExperts, setSectorExperts] = useState<SectorExpertSignal[]>([]);
  const [fatPitches, setFatPitches] = useState<ConsensusBlindspotSignal[]>([]);
  const [deltas, setDeltas] = useState<ConvergenceDelta[]>([]);
  const [signalChanges, setSignalChanges] = useState<SignalChange[]>([]);
  const [sparkPrices, setSparkPrices] = useState<Record<string, { date: string; close: number }[]>>({});
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
      api.heatIndex(),
      api.convergenceDelta(),
      api.signalChanges(),
    ]).then(([m, b, s, c, t, d, r, se, fp, hi, cd, sc]) => {
      if (m.status === 'fulfilled') setMacro(m.value);
      if (b.status === 'fulfilled') setBreadth(b.value);
      if (s.status === 'fulfilled') setSummary(s.value);
      if (c.status === 'fulfilled') setConvergence(c.value);
      if (t.status === 'fulfilled') setTopSignals(t.value);
      if (d.status === 'fulfilled') setDisplacement(d.value);
      if (r.status === 'fulfilled') setRunners(r.value);
      if (se.status === 'fulfilled') setSectorExperts(se.value);
      if (fp.status === 'fulfilled') setFatPitches(fp.value);
      if (hi.status === 'fulfilled') setHeatIndex(hi.value);
      if (cd.status === 'fulfilled') setDeltas(Array.isArray(cd.value) ? cd.value : []);
      if (sc.status === 'fulfilled') setSignalChanges(Array.isArray(sc.value) ? sc.value : []);
      setLoading(false);
    });
  }, []);

  // Fetch sparkline prices for top 6 action stocks
  useEffect(() => {
    if (topSignals.length === 0) return;
    const symbols = topSignals.slice(0, 6).map(s => s.symbol);
    Promise.allSettled(
      symbols.map(sym => api.prices(sym, 30).then(bars => ({ sym, bars })))
    ).then(results => {
      const map: Record<string, { date: string; close: number }[]> = {};
      results.forEach(r => {
        if (r.status === 'fulfilled') {
          map[r.value.sym] = r.value.bars.map(b => ({ date: b.date, close: b.close }));
        }
      });
      setSparkPrices(map);
    });
  }, [topSignals]);

  // ── Build cross-signal clusters ──
  const clusters: ClusterStock[] = (() => {
    const map = new Map<string, ClusterStock>();
    const getOrCreate = (symbol: string): ClusterStock =>
      map.get(symbol) || { symbol, sector: null, sources: [], convergenceScore: null, conviction: null, narrative: null, displacementScore: null, pairsDirection: null, sectorDirection: null };

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
      s.sector = se.sector;
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

  // Split action stocks into hero (1), medium (2-3), small (4-6)
  const hero = actionStocks[0];
  const mediums = actionStocks.slice(1, 3);
  const smalls = actionStocks.slice(3, 6);

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

        {/* Heat Index micro-gauge */}
        {heatIndex && (
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-terminal-dim tracking-wider">HEAT</span>
            <div className="w-16 h-1.5 bg-terminal-muted rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(100, Math.max(0, (heatIndex.heat_index + 100) / 2))}%`,
                  backgroundColor: heatIndex.heat_index > 10 ? '#00FF41' : heatIndex.heat_index > -10 ? '#FFB800' : '#FF073A',
                }}
              />
            </div>
            <span className={`text-[10px] font-mono ${
              heatIndex.heat_index > 10 ? 'text-terminal-green' :
              heatIndex.heat_index > -10 ? 'text-terminal-amber' : 'text-terminal-red'
            }`}>
              {heatIndex.heat_index > 0 ? '+' : ''}{heatIndex.heat_index.toFixed(1)}
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

      {/* ═══ B0: WHAT CHANGED TODAY ═══ */}
      <DailyDelta deltas={deltas} signalChanges={signalChanges} />

      {/* ═══ B: CONVICTION-WEIGHTED CARDS + FAT PITCHES ═══ */}
      <div className="grid grid-cols-5 gap-4">

        {/* Left: Conviction-Weighted Action Cards */}
        <div className="col-span-3 space-y-3">
          <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
            Highest Conviction Setups
          </h2>

          {/* Hero Card — #1 pick, visually dominant */}
          {hero && (
            <a
              href={`/asset/${hero.symbol}`}
              className={`panel p-5 block hover:border-terminal-green/40 transition-all group ${convictionBorder(hero.conv?.convergence_score)}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className="text-lg font-display font-bold text-terminal-bright group-hover:text-terminal-green transition-colors">
                    {hero.symbol}
                  </span>
                  <SignalBadge signal={hero.signal} size="md" />
                  {hero.conv && (
                    <span className={`text-[9px] font-bold tracking-wider px-2 py-0.5 rounded-sm ${
                      hero.conv.conviction_level === 'high'
                        ? 'text-terminal-green bg-terminal-green/10'
                        : hero.conv.conviction_level === 'medium'
                        ? 'text-terminal-amber bg-terminal-amber/10'
                        : 'text-terminal-dim bg-terminal-dim/10'
                    }`}>
                      {hero.conv.conviction_level?.toUpperCase()} · {hero.conv.module_count} MODULES
                    </span>
                  )}
                </div>
                {hero.conv && (
                  <span
                    className="text-3xl font-display font-bold"
                    style={{
                      color: scoreColor(hero.conv.convergence_score),
                      textShadow: hero.conv.convergence_score >= 70 ? `0 0 20px ${scoreColor(hero.conv.convergence_score)}30` : 'none',
                    }}
                  >
                    {hero.conv.convergence_score.toFixed(1)}
                  </span>
                )}
              </div>

              {/* Sparkline + Module strip */}
              <div className="flex items-center gap-4 mb-3">
                {sparkPrices[hero.symbol] && (
                  <Sparkline prices={sparkPrices[hero.symbol]} width={140} height={44} />
                )}
                <div className="flex-1">
                  {hero.conv && <ModuleStrip convergence={hero.conv} mode="compact" />}
                </div>
              </div>

              {/* Trade Range Bar — replaces entry/stop/target numbers */}
              <div className="flex items-center gap-6 mb-3">
                <TradeRangeBar
                  entry={hero.entry_price}
                  stop={hero.stop_loss}
                  target={hero.target_price}
                  width={240}
                  height={20}
                  showLabels
                  showRR
                />
                <div className="text-[9px] text-terminal-dim">
                  <span className="text-terminal-text font-mono">${hero.position_size_dollars ? `${(hero.position_size_dollars / 1000).toFixed(0)}K` : '—'}</span>
                  <span className="ml-1">SIZE</span>
                </div>
              </div>

              {/* Narrative — 3 lines visible, not truncated to oblivion */}
              {hero.conv?.narrative && (
                <p className="text-[10px] text-terminal-dim leading-relaxed line-clamp-3">
                  {hero.conv.narrative}
                </p>
              )}
            </a>
          )}

          {/* Medium Cards — #2 and #3, side by side */}
          <div className="grid grid-cols-2 gap-3">
            {mediums.map(s => (
              <a
                key={s.symbol}
                href={`/asset/${s.symbol}`}
                className={`panel p-4 block hover:border-terminal-green/30 transition-all group ${convictionBorder(s.conv?.convergence_score)}`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-display font-bold text-terminal-bright group-hover:text-terminal-green transition-colors">
                      {s.symbol}
                    </span>
                    <SignalBadge signal={s.signal} size="sm" />
                  </div>
                  {s.conv && (
                    <span
                      className="text-xl font-display font-bold"
                      style={{ color: scoreColor(s.conv.convergence_score) }}
                    >
                      {s.conv.convergence_score.toFixed(1)}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-3 mb-2">
                  {sparkPrices[s.symbol] && (
                    <Sparkline prices={sparkPrices[s.symbol]} width={90} height={32} />
                  )}
                  <div className="flex-1">
                    {s.conv && <ModuleStrip convergence={s.conv} mode="compact" />}
                  </div>
                </div>

                <TradeRangeBar
                  entry={s.entry_price}
                  stop={s.stop_loss}
                  target={s.target_price}
                  width={180}
                  height={14}
                  showRR
                />

                {s.conv?.narrative && (
                  <p className="text-[9px] text-terminal-dim mt-2 line-clamp-2 leading-relaxed">
                    {s.conv.narrative}
                  </p>
                )}
              </a>
            ))}
          </div>

          {/* Small Cards — #4, #5, #6 */}
          <div className="grid grid-cols-3 gap-3">
            {smalls.map(s => (
              <a
                key={s.symbol}
                href={`/asset/${s.symbol}`}
                className="panel p-3 block hover:border-terminal-green/30 transition-all group"
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-sm font-display font-bold text-terminal-bright group-hover:text-terminal-green transition-colors">
                    {s.symbol}
                  </span>
                  {s.conv && (
                    <span
                      className="text-base font-display font-bold"
                      style={{ color: scoreColor(s.conv.convergence_score) }}
                    >
                      {s.conv.convergence_score.toFixed(0)}
                    </span>
                  )}
                </div>

                <TradeRangeBar
                  entry={s.entry_price}
                  stop={s.stop_loss}
                  target={s.target_price}
                  width={140}
                  height={10}
                  showRR
                />

                {s.conv?.narrative && (
                  <p className="text-[8px] text-terminal-dim mt-1.5 line-clamp-1 leading-relaxed">
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
              {fatPitches.slice(0, 6).map((fp, idx) => {
                const badge = gapTypeBadge(fp.gap_type);
                const isTop = idx === 0 && fp.fat_pitch_count >= 3;
                return (
                  <a
                    key={fp.symbol}
                    href={`/asset/${fp.symbol}`}
                    className={`panel p-3 block hover:border-terminal-green/30 transition-colors group ${
                      isTop ? 'border-terminal-green/30 shadow-[0_0_12px_rgba(0,255,65,0.05)]' : ''
                    }`}
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

                    {/* Fat pitch conditions — visual dots instead of just count */}
                    <div className="flex items-center gap-2 mb-1">
                      <div className="flex gap-1">
                        {Array.from({ length: fp.fat_pitch_count || 0 }).map((_, i) => (
                          <div key={i} className="w-1.5 h-1.5 rounded-full bg-terminal-green shadow-[0_0_4px_#00FF41]" />
                        ))}
                        {Array.from({ length: Math.max(0, 4 - (fp.fat_pitch_count || 0)) }).map((_, i) => (
                          <div key={`e${i}`} className="w-1.5 h-1.5 rounded-full bg-terminal-muted" />
                        ))}
                      </div>
                      {fp.fat_pitch_conditions && (
                        <span className="text-[8px] text-terminal-dim truncate">
                          {fp.fat_pitch_conditions}
                        </span>
                      )}
                    </div>

                    {/* Positioning context */}
                    <div className="flex gap-3 text-[8px] text-terminal-dim">
                      {fp.short_interest_pct != null && (
                        <span>SI: <span className={fp.short_interest_pct > 10 ? 'text-terminal-amber' : ''}>{fp.short_interest_pct.toFixed(1)}%</span></span>
                      )}
                      {fp.analyst_buy_pct != null && (
                        <span>Buy: {fp.analyst_buy_pct.toFixed(0)}%</span>
                      )}
                      {fp.our_convergence_score != null && (
                        <span>Conv: <span className="text-terminal-green">{fp.our_convergence_score.toFixed(0)}</span></span>
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

      {/* ═══ D: CROSS-SIGNAL CLUSTERS (grouped by sector) ═══ */}
      {clusters.length > 0 && (() => {
        // Group by sector
        const sectorMap = new Map<string, ClusterStock[]>();
        clusters.slice(0, 12).forEach(c => {
          const sec = c.sector || 'Other';
          if (!sectorMap.has(sec)) sectorMap.set(sec, []);
          sectorMap.get(sec)!.push(c);
        });
        const sectors = Array.from(sectorMap.entries())
          .sort((a, b) => b[1].length - a[1].length);

        return (
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
                Cross-Signal Clusters
              </h2>
              <span className="text-[9px] text-terminal-dim">
                {clusters.length} stocks with 2+ signal sources
              </span>
            </div>
            <div className="space-y-4">
              {sectors.map(([sector, stocks]) => {
                const avgScore = stocks.reduce((s, c) => s + (c.convergenceScore ?? 0), 0) / stocks.length;
                return (
                  <div key={sector}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[10px] text-terminal-amber font-bold tracking-wider uppercase">
                        {sector}
                      </span>
                      <span className="text-[9px] text-terminal-dim">({stocks.length})</span>
                      <span
                        className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded-sm"
                        style={{
                          color: scoreColor(avgScore),
                          backgroundColor: avgScore >= 50 ? 'rgba(0,255,65,0.08)' : 'rgba(255,184,0,0.08)',
                        }}
                      >
                        {avgScore.toFixed(0)}
                      </span>
                    </div>
                    <div className="grid grid-cols-4 gap-3">
                      {stocks.map(c => (
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
                                <div className="font-mono" style={{ color: scoreColor(c.convergenceScore) }}>{c.convergenceScore.toFixed(1)}</div>
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
                );
              })}
            </div>
          </div>
        );
      })()}

      {/* ═══ E: ACTION TABLE — Visual trade setups ═══ */}
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
                    <th className="text-center py-3 px-2 font-normal w-[200px]">Modules</th>
                    <th className="text-center py-3 px-2 font-normal w-[140px]">Trade Setup</th>
                    <th className="text-right py-3 px-4 font-normal">Size</th>
                  </tr>
                </thead>
                <tbody>
                  {actionStocks.map((s) => (
                    <>
                      <tr
                        key={s.symbol}
                        className={`border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer ${
                          s.conv && s.conv.convergence_score >= 80 ? 'bg-terminal-green/[0.02]' : ''
                        }`}
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
                        <td className="py-2.5 px-2 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-12 h-[3px] bg-terminal-muted rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${Math.min(100, s.composite_score)}%`,
                                  backgroundColor: scoreColor(s.composite_score),
                                }}
                              />
                            </div>
                            <span className="font-mono text-terminal-text w-8 text-right">{s.composite_score.toFixed(0)}</span>
                          </div>
                        </td>
                        <td className="py-2.5 px-2 text-right">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-12 h-[3px] bg-terminal-muted rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${Math.min(100, s.conv?.convergence_score ?? 0)}%`,
                                  backgroundColor: s.conv ? scoreColor(s.conv.convergence_score) : '#333',
                                }}
                              />
                            </div>
                            <span className="font-mono w-8 text-right" style={{ color: s.conv ? scoreColor(s.conv.convergence_score) : '#555' }}>
                              {s.conv?.convergence_score?.toFixed(0) ?? '—'}
                            </span>
                          </div>
                        </td>
                        <td className="py-2.5 px-2">
                          {s.conv ? (
                            <ModuleStrip convergence={s.conv} mode="compact" />
                          ) : (
                            <span className="text-terminal-dim text-[9px]">—</span>
                          )}
                        </td>
                        <td className="py-2.5 px-2">
                          <div className="flex justify-center">
                            <TradeRangeBar
                              entry={s.entry_price}
                              stop={s.stop_loss}
                              target={s.target_price}
                              width={130}
                              height={14}
                              showRR
                            />
                          </div>
                        </td>
                        <td className="py-2.5 px-4 text-right font-mono text-terminal-dim">
                          {s.position_size_dollars ? `$${(s.position_size_dollars / 1000).toFixed(0)}K` : '—'}
                        </td>
                      </tr>
                      {expandedAction === s.symbol && s.conv && (
                        <tr key={`${s.symbol}-exp`} className="bg-terminal-bg/50">
                          <td colSpan={7} className="px-4 py-4">
                            <div className="grid grid-cols-2 gap-6">
                              {/* Left: Narrative + Trade details */}
                              <div className="space-y-3">
                                <div>
                                  <div className="text-[9px] text-terminal-dim tracking-wider mb-1">NARRATIVE</div>
                                  <p className="text-[11px] text-terminal-text leading-relaxed">
                                    {s.conv.narrative || 'No narrative available.'}
                                  </p>
                                </div>
                                <div className="flex gap-6 text-[10px]">
                                  <div>
                                    <span className="text-terminal-dim">Entry </span>
                                    <span className="text-terminal-cyan font-mono">${s.entry_price.toFixed(2)}</span>
                                  </div>
                                  <div>
                                    <span className="text-terminal-dim">Stop </span>
                                    <span className="text-terminal-red font-mono">${s.stop_loss.toFixed(2)}</span>
                                    <span className="text-terminal-dim text-[8px] ml-1">
                                      ({((1 - s.stop_loss / s.entry_price) * 100).toFixed(1)}%)
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-terminal-dim">Target </span>
                                    <span className="text-terminal-green font-mono">${s.target_price.toFixed(2)}</span>
                                    <span className="text-terminal-dim text-[8px] ml-1">
                                      (+{((s.target_price / s.entry_price - 1) * 100).toFixed(1)}%)
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-terminal-dim">R:R </span>
                                    <span className="text-terminal-amber font-mono font-bold">{s.rr_ratio.toFixed(1)}</span>
                                  </div>
                                </div>
                              </div>
                              {/* Right: Module breakdown — visual bar chart replacing number grid */}
                              <div>
                                <div className="text-[9px] text-terminal-dim tracking-wider mb-2">MODULE BREAKDOWN</div>
                                <ModuleStrip convergence={s.conv} mode="expanded" />
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
