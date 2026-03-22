'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useStockPanel } from '@/contexts/StockPanelContext';
import { fmtM } from '@/lib/utils';
import { Tooltip, InfoTip } from '@/components/shared/Tooltip';
import { MACRO_DEFS, BREADTH_DEFS } from '@/lib/definitions';

interface Headline {
  headline: string;
  source: string;
  url?: string | null;
  symbol?: string | null;
  category: string;
  company_name?: string | null;
  direction?: string | null;
}

interface TerminalData {
  macro: any;
  breadth: any;
  sectors: any[];
  insider_flow: any[];
  score_movers: any[];
  catalysts: any[];
  key_indicators: any[];
  ma_intel: any[];
  ma_rumors: any[];
  energy_anomalies: any[];
  pipeline: any;
}


function Ticker({ symbol, onClick }: { symbol: string; onClick: () => void }) {
  return (
    <button
      onClick={e => { e.stopPropagation(); onClick(); }}
      className="font-mono font-bold text-blue-700 hover:text-blue-600 hover:underline underline-offset-2 transition-colors text-[11px] tracking-wide"
    >
      {symbol}
    </button>
  );
}

function NewsTicker() {
  const [headlines, setHeadlines] = useState<Headline[]>([]);
  const tickerRef = useRef<HTMLDivElement>(null);
  const { open: openStock } = useStockPanel();

  useEffect(() => {
    const load = () => {
      fetch('/api/v2/headlines')
        .then(r => r.json())
        .then(d => setHeadlines(d.headlines || []))
        .catch(() => {});
    };
    load();
    // Refresh every 2 minutes
    const interval = setInterval(load, 120_000);
    return () => clearInterval(interval);
  }, []);

  if (headlines.length === 0) return null;

  // Duplicate for seamless loop
  const items = [...headlines, ...headlines];

  return (
    <div className="bg-gray-900 border-b border-gray-700 overflow-hidden shrink-0 h-8 flex items-center">
      <div className="shrink-0 px-3 flex items-center gap-1.5 border-r border-gray-700 h-full bg-blue-600">
        <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
        <span className="text-[9px] font-bold text-white tracking-widest uppercase">Live</span>
      </div>
      <div className="flex-1 overflow-hidden">
        <div
          ref={tickerRef}
          className="flex items-center gap-0 whitespace-nowrap"
          style={{
            animation: 'ticker-scroll 120s linear infinite',
          }}
        >
          {items.map((h, i) => {
            const dirColor = h.direction === 'bullish' ? 'text-emerald-400'
              : h.direction === 'bearish' ? 'text-rose-400' : 'text-gray-300';
            const catColor = h.category === 'ma' ? 'text-purple-400'
              : h.category === 'stock' ? 'text-blue-400' : 'text-gray-400';
            return (
              <span key={i} className="flex items-center">
                <span className="flex items-center gap-1.5 px-4">
                  {h.symbol && (
                    <button
                      onClick={() => openStock(h.symbol!)}
                      className={`font-mono font-bold text-[9px] ${catColor} hover:text-white transition-colors`}
                    >
                      {h.symbol}
                    </button>
                  )}
                  {h.url ? (
                    <a
                      href={h.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`text-[10px] ${dirColor} hover:text-white transition-colors`}
                    >
                      {h.headline}
                    </a>
                  ) : (
                    <span className={`text-[10px] ${dirColor}`}>{h.headline}</span>
                  )}
                  <span className="text-[9px] text-gray-600 ml-1">{h.source}</span>
                </span>
                <span className="text-gray-700 text-[10px]">·</span>
              </span>
            );
          })}
        </div>
      </div>
      <style jsx>{`
        @keyframes ticker-scroll {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
      `}</style>
    </div>
  );
}


type RightTab = 'insider' | 'ma' | 'signals';
type EconCat = 'ALL' | 'LEADING' | 'COINCIDENT' | 'LAGGING' | 'LIQUIDITY';

export default function TerminalView() {
  const [data, setData] = useState<TerminalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshed, setRefreshed] = useState<Date | null>(null);
  const [rightTab, setRightTab] = useState<RightTab>('insider');
  const [econCat, setEconCat] = useState<EconCat>('ALL');
  const { open: openStock } = useStockPanel();

  const load = () => {
    setLoading(true);
    fetch('/api/v2/terminal')
      .then(r => r.json())
      .then(d => { setData(d); setRefreshed(new Date()); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div className="flex-1 animate-pulse p-6 space-y-3">
      <div className="h-10 bg-gray-100 rounded-xl" />
      <div className="grid grid-cols-[260px_1fr_280px] gap-0 h-[calc(100vh-200px)]">
        {[0,1,2].map(i => <div key={i} className="bg-gray-100 m-1 rounded-xl" />)}
      </div>
    </div>
  );

  if (!data) return <div className="flex items-center justify-center h-64 text-gray-400 text-sm">Cannot connect to backend</div>;

  const macro            = data.macro            ?? {};
  const breadth          = data.breadth          ?? {};
  const sectors          = data.sectors          ?? [];
  const insider_flow     = data.insider_flow     ?? [];
  const score_movers     = data.score_movers     ?? [];
  const catalysts        = data.catalysts        ?? [];
  const key_indicators   = data.key_indicators   ?? [];
  const ma_intel         = data.ma_intel         ?? [];
  const ma_rumors        = data.ma_rumors        ?? [];
  const energy_anomalies = data.energy_anomalies ?? [];
  const pipeline         = data.pipeline         ?? {};
  const macroScore = macro?.total_score ?? macro?.regime_score ?? 0;

  // Right panel stats
  const clusterCount   = insider_flow.filter((t: any) => !!t.cluster_buy).length;
  const highScoreCount = insider_flow.filter((t: any) => t.insider_score >= 50).length;
  const maHighCount    = ma_intel.filter((m: any) => m.ma_score >= 50).length;
  const energyCount    = energy_anomalies.length;

  // Econ indicator categories present in data
  const econCats = ['ALL', ...Array.from(new Set(key_indicators.map((i: any) => i.category))).sort()] as EconCat[];
  const filteredEcon = econCat === 'ALL' ? key_indicators : key_indicators.filter((i: any) => i.category === econCat);

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gray-50">

      {/* ── Header bar ── */}
      <div className="bg-white border-b border-gray-200 px-6 py-2.5 shrink-0">
        <div className="flex items-center justify-between max-w-[1600px] mx-auto">
          <div className="flex items-center gap-4">
            {/* Regime */}
            <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[9px] font-bold uppercase tracking-widest border ${
              (macro?.regime || '').toUpperCase().includes('RISK') && (macro?.regime || '').toUpperCase().includes('ON')
                ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                : (macro?.regime || '').toUpperCase().includes('RISK') && (macro?.regime || '').toUpperCase().includes('OFF')
                ? 'bg-rose-50 text-rose-800 border-rose-300'
                : (macro?.regime || '').toUpperCase().includes('BEAR')
                ? 'bg-rose-50 text-rose-800 border-rose-300'
                : (macro?.regime || '').toUpperCase().includes('NEUTRAL')
                ? 'bg-slate-100 text-slate-600 border-slate-300'
                : 'bg-amber-50 text-amber-800 border-amber-300'
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${
                (macro?.regime || '').toUpperCase().includes('RISK') && (macro?.regime || '').toUpperCase().includes('ON') ? 'bg-emerald-500'
                : (macro?.regime || '').toUpperCase().includes('RISK') && (macro?.regime || '').toUpperCase().includes('OFF') ? 'bg-rose-500'
                : (macro?.regime || '').toUpperCase().includes('BEAR') ? 'bg-rose-500'
                : (macro?.regime || '').toUpperCase().includes('NEUTRAL') ? 'bg-slate-400'
                : 'bg-amber-400'
              }`} />
              {macro?.regime || 'UNKNOWN REGIME'}
            </div>

            <div className="w-px h-4 bg-gray-200" />

            {/* Key macro stats */}
            <div className="flex items-center gap-4 text-[10px]">
              {[
                { label: 'MACRO', val: macroScore },
                { label: 'VIX', val: macro?.vix_score },
                { label: 'YIELD CURVE', val: macro?.yield_curve_score },
                { label: 'CREDIT', val: macro?.credit_spreads_score },
              ].filter(x => x.val != null).map(({ label, val }) => (
                <span key={label} className="flex items-center gap-1">
                  <span className="text-gray-400 tracking-wider">{label}</span>
                  <span className={`font-mono font-bold ${(val as number) >= 55 ? 'text-emerald-700' : (val as number) >= 40 ? 'text-amber-600' : 'text-rose-600'}`}>
                    {(val as number).toFixed(0)}
                  </span>
                </span>
              ))}

              {/* Breadth */}
              {breadth?.breadth_score != null && (
                <>
                  <div className="w-px h-3 bg-gray-200" />
                  <span className="flex items-center gap-1">
                    <span className="text-gray-400 tracking-wider">BREADTH</span>
                    <span className={`font-mono font-bold ${breadth.breadth_score >= 55 ? 'text-emerald-700' : breadth.breadth_score >= 40 ? 'text-amber-600' : 'text-rose-600'}`}>
                      {breadth.breadth_score.toFixed(0)}
                    </span>
                  </span>
                  {breadth.pct_above_200dma != null && (
                    <span className="text-[9px] text-gray-400">{breadth.pct_above_200dma.toFixed(0)}% above 200dma</span>
                  )}
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* CTA to Gates — this is where our picks live */}
            {pipeline?.fat_pitches_count > 0 && (
              <a href="/v2/gates" className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full text-[10px] text-emerald-700 font-semibold hover:bg-emerald-100 transition-colors">
                {pipeline.fat_pitches_count} fat {pipeline.fat_pitches_count === 1 ? 'pitch' : 'pitches'} in cascade →
              </a>
            )}
            <button onClick={load} disabled={loading} className="text-[9px] text-gray-400 hover:text-gray-700 transition-colors tracking-widest uppercase disabled:opacity-40 disabled:cursor-not-allowed">
              {loading ? 'Loading...' : 'Refresh'}
            </button>
            {refreshed && <span className="text-[9px] text-gray-300">{refreshed.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}</span>}
          </div>
        </div>
      </div>

      {/* ── News ticker ── */}
      <NewsTicker />

      {/* ── Deep-dive quick links ── */}
      <div className="shrink-0 bg-gray-900 border-b border-gray-700 px-4 h-7 flex items-center gap-1">
        <span className="text-[9px] text-gray-500 tracking-widest uppercase mr-2 font-semibold">Deep Dive</span>
        {[
          { label: 'Macro', href: '/macro' },
          { label: 'Signal Intel', href: '/signals' },
          { label: 'Energy Intel', href: '/energy' },
          { label: 'Alpha Intelligence', href: '/alpha' },
          { label: 'Performance', href: '/performance' },
        ].map(({ label, href }) => (
          <a key={href} href={href} className="text-[9px] text-gray-400 hover:text-white transition-colors px-2.5 py-0.5 rounded hover:bg-gray-700 tracking-wide">
            {label}
          </a>
        ))}
      </div>

      {/* ── 3-column body ── */}
      <div className="flex-1 overflow-hidden">
        <div className="grid grid-cols-[260px_1fr_280px] h-full divide-x divide-gray-200 max-w-[1600px] mx-auto">

          {/* ── LEFT: Macro Environment ── */}
          <div className="overflow-y-auto p-4 space-y-4">
            <div className="text-[9px] text-gray-400 tracking-widest uppercase font-semibold px-1">Macro Environment</div>

            {/* Regime card */}
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1">
                <Tooltip text={MACRO_DEFS.overall} width="w-72">
                  <span className="text-[9px] text-gray-400 uppercase tracking-widest">Macro Score</span>
                </Tooltip>
                <span className={`text-2xl font-bold font-mono ${macroScore >= 30 ? 'text-emerald-600' : macroScore >= 10 ? 'text-amber-600' : 'text-rose-600'}`}>
                  {macroScore > 0 ? '+' : ''}{macroScore.toFixed(0)}
                </span>
              </div>
              <div className="text-[9px] text-gray-400 mb-3">Sum of signed components · green = bullish · &gt;+30 risk-on</div>
              {(() => {
                const bars = [
                  { label: 'Fed Policy',       score: macro?.fed_funds_score      },
                  { label: 'Yield Curve',      score: macro?.yield_curve_score    },
                  { label: 'Credit Spreads',   score: macro?.credit_spreads_score },
                  { label: 'DXY (Dollar)',     score: macro?.dxy_score            },
                  { label: 'VIX (Volatility)', score: macro?.vix_score            },
                  { label: 'M2 Liquidity',     score: macro?.m2_score             },
                  { label: 'Real Rates',       score: macro?.real_rates_score     },
                ].filter(b => b.score != null) as { label: string; score: number }[];
                const maxAbs = Math.max(...bars.map(b => Math.abs(b.score)), 1);
                return (
                  <div className="space-y-2">
                    {bars.map(({ label, score }) => {
                      const pct = Math.abs(score) / maxAbs * 100;
                      const barColor = score >= 5 ? 'bg-emerald-400' : score >= 0 ? 'bg-amber-400' : 'bg-rose-400';
                      const textColor = score >= 5 ? 'text-emerald-700' : score >= 0 ? 'text-amber-600' : 'text-rose-600';
                      return (
                        <div key={label} className="flex items-center gap-2">
                          <div className="text-[9px] text-gray-500 w-24 truncate">{label}</div>
                          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden relative">
                            {score >= 0
                              ? <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
                              : <div className={`h-full rounded-full ${barColor} absolute right-0`} style={{ width: `${pct}%` }} />
                            }
                          </div>
                          <div className={`text-[10px] font-mono font-bold w-6 text-right ${textColor}`}>{score > 0 ? '+' : ''}{score.toFixed(0)}</div>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>

            {/* Market breadth */}
            {breadth && Object.keys(breadth).length > 1 && (
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="flex items-center gap-1.5 mb-3">
                  <Tooltip text={BREADTH_DEFS.breadth_score} position="bottom" width="w-80">
                    <span className="text-[9px] text-gray-400 tracking-widest uppercase">Market Breadth</span>
                  </Tooltip>
                </div>
                <div className="space-y-2">
                  {[
                    { label: '% above 200dma', value: breadth.pct_above_200dma != null ? `${breadth.pct_above_200dma.toFixed(0)}%` : null },
                    { label: 'Adv/Dec ratio',  value: breadth.advance_decline_ratio != null ? breadth.advance_decline_ratio.toFixed(2) : null },
                    { label: 'New 52w highs',  value: breadth.new_highs != null ? breadth.new_highs : null },
                    { label: 'New 52w lows',   value: breadth.new_lows != null ? breadth.new_lows : null },
                  ].filter(x => x.value != null).map(({ label, value }) => (
                    <div key={label} className="flex items-center justify-between">
                      <span className="text-[9px] text-gray-500">{label}</span>
                      <span className="text-[10px] font-mono font-semibold text-gray-800">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Key economic indicators — tabbed by category */}
            {key_indicators.length > 0 && (
              <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <div className="px-3 pt-3 pb-1">
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-[9px] text-gray-400 tracking-widest uppercase">Economic Indicators</div>
                    <a href="/macro" className="text-[9px] text-emerald-600 hover:underline tracking-wide">Full Macro →</a>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {econCats.map(cat => (
                      <button
                        key={cat}
                        onClick={() => setEconCat(cat)}
                        className={`text-[7px] px-1.5 py-0.5 rounded font-bold tracking-widest uppercase transition-colors ${
                          econCat === cat
                            ? 'bg-gray-900 text-white'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                        }`}
                      >
                        {cat}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="divide-y divide-gray-50 max-h-64 overflow-y-auto">
                  {filteredEcon.map((ind: any, i: number) => {
                    const mom = ind.mom_change as number | null;
                    const yoy = ind.yoy_change as number | null;
                    const z   = ind.zscore as number | null;
                    const trend = ind.trend as string | null;
                    const dotColor = z == null ? 'bg-gray-300'
                      : Math.abs(z) < 1 ? 'bg-emerald-400'
                      : Math.abs(z) < 2 ? 'bg-amber-400' : 'bg-rose-400';
                    return (
                      <div key={i} className="flex items-center gap-2 px-3 py-2">
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
                        <div className="min-w-0 flex-1">
                          <div className="text-[9px] text-gray-700 truncate">{ind.name}</div>
                        </div>
                        <div className="text-right shrink-0 space-y-0.5">
                          <div className="text-[9px] font-mono font-semibold text-gray-800">
                            {typeof ind.value === 'number' ? ind.value.toLocaleString('en-US', { maximumFractionDigits: 2 }) : ind.value}
                          </div>
                          <div className="flex items-center gap-1 justify-end">
                            {mom != null && (
                              <span className={`text-[9px] font-mono ${mom >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                                {mom >= 0 ? '+' : ''}{mom.toFixed(1)}%
                              </span>
                            )}
                            {z != null && (
                              <span className="text-[7px] text-gray-400 font-mono">{z >= 0 ? '+' : ''}{z.toFixed(1)}σ</span>
                            )}
                            {trend && (
                              <span className={`text-[7px] font-bold ${
                                trend === 'improving' ? 'text-emerald-500'
                                : trend === 'deteriorating' ? 'text-rose-500'
                                : 'text-amber-500'
                              }`}>
                                {trend === 'improving' ? '▲' : trend === 'deteriorating' ? '▼' : '▶'}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* ── CENTER: Market Intelligence ── */}
          <div className="overflow-y-auto p-5 space-y-5">
            <div className="text-[9px] text-gray-400 tracking-widest uppercase font-semibold px-1">Market Intelligence — 903 stocks</div>

            {/* Sector Rotation table */}
            {sectors.length > 0 && (
              <section>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[10px] font-semibold text-gray-800 uppercase tracking-wide">Sector Rotation</div>
                  <span className="text-[9px] text-gray-400">avg signal score</span>
                </div>
                <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-gray-100">
                        <th className="text-left text-[9px] text-gray-400 px-3 py-2 uppercase tracking-widest font-semibold">Sector</th>
                        <th className="text-right text-[9px] text-gray-400 px-3 py-2 uppercase tracking-widest font-semibold">Score</th>
                        <th className="text-right text-[9px] text-gray-400 px-2 py-2 uppercase tracking-widest font-semibold">Bulls</th>
                        <th className="text-right text-[9px] text-gray-400 px-2 py-2 uppercase tracking-widest font-semibold">Bears</th>
                        <th className="px-3 py-2 w-24"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {sectors.map((sec, i) => {
                        const score = sec.avg_score as number;
                        const maxScore = (sectors[0]?.avg_score as number) || 1;
                        const barPct = (score / maxScore) * 100;
                        const barColor = score >= 55 ? 'bg-emerald-400' : score >= 45 ? 'bg-amber-400' : 'bg-rose-300';
                        const scoreColor = score >= 55 ? 'text-emerald-700 font-bold' : score >= 45 ? 'text-amber-700' : 'text-rose-600';
                        return (
                          <tr key={sec.sector} className={`border-b border-gray-50 last:border-0 ${i === 0 ? 'bg-emerald-50/40' : ''}`}>
                            <td className="px-3 py-2">
                              <span className="text-[10px] text-gray-800">{sec.sector}</span>
                              <span className="text-[9px] text-gray-400 ml-1.5">({sec.stock_count})</span>
                            </td>
                            <td className={`px-3 py-2 text-right text-[11px] font-mono ${scoreColor}`}>{score.toFixed(1)}</td>
                            <td className="px-2 py-2 text-right text-[10px] font-mono text-emerald-600">{sec.bull_count || 0}</td>
                            <td className="px-2 py-2 text-right text-[10px] font-mono text-rose-500">{sec.bear_count || 0}</td>
                            <td className="px-3 py-2">
                              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div className={`h-full rounded-full ${barColor}`} style={{ width: `${barPct}%` }} />
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Score movers across universe */}
            {score_movers.length > 0 && (
              <section>
                <div className="text-[10px] font-semibold text-gray-800 uppercase tracking-wide mb-2">
                  Biggest Movers Today
                  <span className="ml-2 text-[9px] font-normal text-gray-400">across all 903 stocks</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {score_movers.map((m, i) => {
                    const delta = m.delta as number;
                    const up = delta > 0;
                    return (
                      <div
                        key={i}
                        className={`bg-white border rounded-xl p-3 cursor-pointer hover:shadow-sm transition-all ${
                          up ? 'border-emerald-200 hover:border-emerald-300' : 'border-rose-200 hover:border-rose-300'
                        }`}
                        onClick={() => openStock(m.symbol)}
                      >
                        <div className="flex items-center justify-between">
                          <Ticker symbol={m.symbol} onClick={() => openStock(m.symbol)} />
                          <span className={`text-[11px] font-mono font-bold ${up ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {up ? '+' : ''}{delta.toFixed(1)}
                          </span>
                        </div>
                        <div className="text-[9px] text-gray-400 truncate mt-0.5">{m.name || m.sector}</div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[9px] text-gray-500 font-mono">{m.convergence_score?.toFixed(0)}</span>
                          {m.conviction_level && m.conviction_level !== 'WEAK' && (
                            <span className={`text-[9px] px-1 py-0.5 rounded font-bold ${
                              m.conviction_level === 'HIGH' ? 'bg-emerald-100 text-emerald-700'
                              : 'bg-amber-100 text-amber-700'
                            }`}>{m.conviction_level}</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {sectors.length === 0 && score_movers.length === 0 && (
              <div className="text-center py-16 text-gray-400 text-sm">
                No market data yet. Run the pipeline to generate signals.
              </div>
            )}
          </div>

          {/* ── RIGHT: Intelligence Panel (tabbed) ── */}
          <div className="flex flex-col h-full overflow-hidden">
            {/* Tab bar + summary counts */}
            <div className="shrink-0 px-3 pt-3 pb-0 border-b border-gray-100 bg-white">
              <div className="flex items-center gap-1 mb-2">
                {([
                  { id: 'insider', label: 'INSIDER', count: highScoreCount, dot: 'bg-emerald-400' },
                  { id: 'ma',      label: 'M&A',     count: maHighCount,    dot: 'bg-purple-400' },
                  { id: 'signals', label: 'SIGNALS',  count: energyCount,   dot: 'bg-amber-400'  },
                ] as const).map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setRightTab(tab.id)}
                    className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-t text-[9px] font-bold tracking-widest uppercase transition-colors border-b-2 ${
                      rightTab === tab.id
                        ? 'text-gray-900 border-gray-900'
                        : 'text-gray-400 border-transparent hover:text-gray-600'
                    }`}
                  >
                    {tab.label}
                    {tab.count > 0 && (
                      <span className={`w-4 h-4 rounded-full ${tab.dot} text-white text-[7px] font-bold flex items-center justify-center`}>
                        {tab.count}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2.5">

              {/* ── INSIDER tab ── */}
              {rightTab === 'insider' && (
                <>
                  <a href="/signals" className="block text-right text-[9px] text-emerald-600 hover:underline tracking-wide">Full Signal Intel →</a>
                  <div className="grid grid-cols-2 gap-2">
                    {[
                      { label: 'HIGH SCORE', val: highScoreCount, color: 'text-emerald-600' },
                      { label: 'CLUSTER BUYS', val: clusterCount, color: 'text-blue-600' },
                    ].map(({ label, val, color }) => (
                      <div key={label} className="bg-white border border-gray-200 rounded-xl p-2.5 text-center">
                        <div className={`text-xl font-bold font-mono ${color}`}>{val}</div>
                        <div className="text-[7px] text-gray-400 tracking-widest uppercase mt-0.5 leading-tight">{label}</div>
                      </div>
                    ))}
                  </div>
                  {insider_flow.length > 0 ? (
                    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                      <div className="divide-y divide-gray-50">
                        {insider_flow.map((ins: any, i: number) => {
                          const net = (ins.total_buy_value_30d || 0) - (ins.total_sell_value_30d || 0);
                          const scoreColor = ins.insider_score >= 60 ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                            : ins.insider_score >= 40 ? 'text-amber-700 bg-amber-50 border-amber-200'
                            : 'text-gray-500 bg-gray-50 border-gray-200';
                          return (
                            <div key={i} className="px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors" onClick={() => openStock(ins.symbol)}>
                              <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                                <Ticker symbol={ins.symbol} onClick={() => openStock(ins.symbol)} />
                                <span className={`text-[9px] font-bold font-mono px-1.5 py-0.5 rounded border ${scoreColor}`}>{ins.insider_score?.toFixed(0)}</span>
                                {!!ins.cluster_buy && <span className="text-[7px] font-bold bg-rose-100 text-rose-600 border border-rose-200 px-1.5 py-0.5 rounded uppercase">CLUSTER</span>}
                                {!!ins.unusual_volume_flag && <span className="text-[7px] font-bold bg-amber-100 text-amber-600 border border-amber-200 px-1.5 py-0.5 rounded uppercase">VOL</span>}
                                <div className="ml-auto flex gap-1.5">
                                  <span className="text-[9px] font-mono text-emerald-700">{fmtM(ins.total_buy_value_30d)}</span>
                                  <span className={`text-[9px] font-mono font-bold ${net >= 0 ? 'text-emerald-600' : 'text-rose-500'}`}>{net >= 0 ? '+' : ''}{fmtM(net)}</span>
                                </div>
                              </div>
                              {ins.narrative ? (
                                <div className="text-[9px] text-gray-500 leading-snug line-clamp-2">{ins.narrative}</div>
                              ) : ins.top_buyer ? (
                                <div className="text-[9px] text-gray-400 truncate">{ins.cluster_count ? `${ins.cluster_count} insiders · ` : ''}{ins.top_buyer}</div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    <div className="bg-white border border-gray-200 rounded-xl p-6 text-center text-gray-400 text-[11px]">No significant insider activity.</div>
                  )}
                </>
              )}

              {/* ── M&A tab ── */}
              {rightTab === 'ma' && (
                <>
                  <a href="/signals?tab=ma" className="block text-right text-[9px] text-emerald-600 hover:underline tracking-wide">Full M&amp;A Intel →</a>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { label: 'HIGH SCORE', val: maHighCount, color: 'text-purple-600' },
                      { label: 'DEFINITIVE', val: ma_intel.filter((m: any) => m.deal_stage === 'definitive').length, color: 'text-emerald-600' },
                      { label: 'RUMORS', val: ma_rumors.length, color: 'text-amber-600' },
                    ].map(({ label, val, color }) => (
                      <div key={label} className="bg-white border border-gray-200 rounded-xl p-2 text-center">
                        <div className={`text-xl font-bold font-mono ${color}`}>{val}</div>
                        <div className="text-[7px] text-gray-400 tracking-widest uppercase mt-0.5 leading-tight">{label}</div>
                      </div>
                    ))}
                  </div>

                  {ma_intel.length > 0 && (
                    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                      <div className="px-3 py-2 border-b border-gray-100 text-[9px] text-gray-400 uppercase tracking-widest font-semibold">Top Targets</div>
                      <div className="divide-y divide-gray-50">
                        {ma_intel.map((m: any, i: number) => (
                          <div key={i} className="px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors" onClick={() => openStock(m.symbol)}>
                            <div className="flex items-center gap-1.5 flex-wrap mb-0.5">
                              <Ticker symbol={m.symbol} onClick={() => openStock(m.symbol)} />
                              <span className="text-[9px] font-mono font-bold text-purple-700 bg-purple-50 border border-purple-200 px-1.5 py-0.5 rounded">{m.ma_score?.toFixed(0)}</span>
                              {m.deal_stage && (
                                <span className={`text-[7px] font-bold px-1.5 py-0.5 rounded uppercase ${m.deal_stage === 'definitive' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{m.deal_stage}</span>
                              )}
                              {m.expected_premium_pct != null && (
                                <span className="ml-auto text-[9px] font-mono text-blue-600 font-bold">+{m.expected_premium_pct?.toFixed(0)}%</span>
                              )}
                            </div>
                            <div className="text-[9px] text-gray-500 truncate">{m.acquirer_name || m.narrative || m.best_headline || m.company_name}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {ma_rumors.length > 0 && (
                    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                      <div className="px-3 py-2 border-b border-gray-100 text-[9px] text-gray-400 uppercase tracking-widest font-semibold">Active Rumors</div>
                      <div className="divide-y divide-gray-50">
                        {ma_rumors.map((r: any, i: number) => (
                          <div key={i} className="px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors" onClick={() => openStock(r.symbol)}>
                            <div className="flex items-center gap-1.5 mb-0.5">
                              <Ticker symbol={r.symbol} onClick={() => openStock(r.symbol)} />
                              {r.credibility_score != null && (
                                <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded ${r.credibility_score >= 7 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{r.credibility_score}/10</span>
                              )}
                              <span className="ml-auto text-[9px] text-gray-400">{r.date}</span>
                            </div>
                            <div className="text-[9px] text-gray-500 leading-snug line-clamp-2">{r.rumor_headline}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {ma_intel.length === 0 && ma_rumors.length === 0 && (
                    <div className="bg-white border border-gray-200 rounded-xl p-6 text-center text-gray-400 text-[11px]">No M&A signals. Run the pipeline to refresh.</div>
                  )}
                </>
              )}

              {/* ── SIGNALS tab (energy + sector anomalies) ── */}
              {rightTab === 'signals' && (
                <>
                  <a href="/energy" className="block text-right text-[9px] text-emerald-600 hover:underline tracking-wide">Full Energy Intel →</a>
                  {energy_anomalies.length > 0 && (
                    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                      <div className="px-3 py-2 border-b border-gray-100 text-[9px] text-gray-400 uppercase tracking-widest font-semibold">Energy Intelligence</div>
                      <div className="divide-y divide-gray-50">
                        {energy_anomalies.map((e: any, i: number) => {
                          const scoreColor = e.energy_score >= 70 ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                            : e.energy_score >= 50 ? 'text-amber-700 bg-amber-50 border-amber-200'
                            : 'text-gray-500 bg-gray-50 border-gray-200';
                          return (
                            <div key={i} className="px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors" onClick={() => openStock(e.symbol)}>
                              <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                                <Ticker symbol={e.symbol} onClick={() => openStock(e.symbol)} />
                                <span className={`text-[9px] font-bold font-mono px-1.5 py-0.5 rounded border ${scoreColor}`}>{e.energy_score?.toFixed(0)}</span>
                                {e.supply_signal && <span className="text-[7px] font-bold bg-blue-100 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded uppercase">SUPPLY</span>}
                                {e.demand_signal && <span className="text-[7px] font-bold bg-orange-100 text-orange-700 border border-orange-200 px-1.5 py-0.5 rounded uppercase">DEMAND</span>}
                              </div>
                              {e.narrative && <div className="text-[9px] text-gray-500 leading-snug line-clamp-2">{e.narrative}</div>}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {catalysts.slice(0, 8).length > 0 && (
                    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                      <div className="px-3 py-2 border-b border-gray-100 text-[9px] text-gray-400 uppercase tracking-widest font-semibold">Active Catalysts</div>
                      <div className="divide-y divide-gray-50">
                        {catalysts.slice(0, 8).map((cat: any, i: number) => (
                          <div key={i} className="px-3 py-2.5 cursor-pointer hover:bg-gray-50 transition-colors" onClick={() => openStock(cat.symbol)}>
                            <div className="flex items-center gap-1.5 mb-0.5 flex-wrap">
                              <Ticker symbol={cat.symbol} onClick={() => openStock(cat.symbol)} />
                              <span className="text-[7px] font-bold bg-amber-100 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded uppercase">{cat.catalyst_type}</span>
                              <span className={`ml-auto text-[9px] font-mono font-bold ${(cat.catalyst_strength as number) >= 70 ? 'text-emerald-600' : 'text-amber-600'}`}>{cat.catalyst_strength?.toFixed(0)}</span>
                            </div>
                            <div className="text-[9px] text-gray-500 leading-snug line-clamp-2">{cat.catalyst_detail}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {energy_anomalies.length === 0 && catalysts.length === 0 && (
                    <div className="bg-white border border-gray-200 rounded-xl p-6 text-center text-gray-400 text-[11px]">No active signals. Run the pipeline to refresh.</div>
                  )}
                </>
              )}

            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
