'use client';

import { useEffect, useState } from 'react';
import { useStockPanel } from '@/contexts/StockPanelContext';

interface TerminalData {
  macro: any;
  fat_pitches: any[];
  insider_flow: any[];
  score_movers: any[];
  catalysts: any[];
  key_indicators: any[];
  gate_summary: any;
}

function fmtM(v: number | null | undefined) {
  if (v == null) return '—';
  const n = v as number;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function Ticker({ symbol, onClick }: { symbol: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="font-mono font-bold text-emerald-700 hover:text-emerald-600 hover:underline underline-offset-2 transition-colors text-[11px] tracking-wide"
    >
      {symbol}
    </button>
  );
}

function ScoreBadge({ score, size = 'sm' }: { score: number | null | undefined; size?: 'sm' | 'lg' }) {
  if (score == null) return null;
  const s = score as number;
  const cls = s >= 70 ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
    : s >= 50 ? 'bg-amber-100 text-amber-800 border-amber-300'
    : 'bg-gray-100 text-gray-600 border-gray-300';
  return (
    <span className={`border rounded font-mono font-bold ${cls} ${size === 'lg' ? 'text-sm px-2 py-0.5' : 'text-[9px] px-1.5 py-0.5'}`}>
      {s.toFixed(0)}
    </span>
  );
}

function RegimeBadge({ regime }: { regime: string }) {
  const upper = (regime || '').toUpperCase();
  const cls = upper.includes('RISK') && upper.includes('ON') ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
    : upper.includes('BEAR') || upper.includes('RISK') && upper.includes('OFF') ? 'bg-rose-100 text-rose-800 border-rose-300'
    : 'bg-amber-100 text-amber-800 border-amber-300';
  return <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border ${cls}`}>{upper || 'UNKNOWN'}</span>;
}

export default function TerminalView() {
  const [data, setData] = useState<TerminalData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshed, setRefreshed] = useState<Date | null>(null);
  const { open: openStock } = useStockPanel();

  const load = () => {
    setLoading(true);
    setError(null);
    fetch('/api/v2/terminal')
      .then(r => r.json())
      .then(d => { setData(d); setRefreshed(new Date()); setLoading(false); })
      .catch(() => { setError('Cannot connect to backend'); setLoading(false); });
  };

  useEffect(() => { load(); }, []);

  if (loading) return (
    <div className="flex-1 animate-pulse p-6 space-y-4">
      <div className="h-12 bg-gray-100 rounded-xl" />
      <div className="grid grid-cols-[280px_1fr_280px] gap-4 h-[calc(100vh-200px)]">
        <div className="bg-gray-100 rounded-xl" />
        <div className="bg-gray-100 rounded-xl" />
        <div className="bg-gray-100 rounded-xl" />
      </div>
    </div>
  );

  if (error) return (
    <div className="flex items-center justify-center h-64 text-gray-500 text-sm">{error}</div>
  );

  if (!data) return null;

  const { macro, fat_pitches, insider_flow, score_movers, catalysts, key_indicators, gate_summary } = data;

  const macroScore = macro?.total_score ?? macro?.regime_score ?? 0;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gray-50">

      {/* ── Terminal header bar ── */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 shrink-0">
        <div className="flex items-center justify-between max-w-[1600px] mx-auto">
          <div className="flex items-center gap-4">
            <div className="text-[10px] text-gray-400 tracking-widest uppercase font-semibold">Market Intelligence Terminal</div>
            <div className="w-px h-4 bg-gray-200" />
            <RegimeBadge regime={macro?.regime || ''} />
            <div className="w-px h-4 bg-gray-200" />
            <div className="flex items-center gap-4 text-[10px]">
              <div className="flex items-center gap-1.5">
                <span className="text-gray-400 tracking-wider">MACRO</span>
                <span className={`font-mono font-bold ${macroScore >= 60 ? 'text-emerald-600' : macroScore >= 40 ? 'text-amber-600' : 'text-rose-600'}`}>
                  {macroScore.toFixed(0)}
                </span>
              </div>
              {macro?.fed_funds_score != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-gray-400 tracking-wider">FED</span>
                  <span className="font-mono font-bold text-gray-700">{(macro.fed_funds_score as number).toFixed(0)}</span>
                </div>
              )}
              {macro?.yield_curve_score != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-gray-400 tracking-wider">YIELD CURVE</span>
                  <span className="font-mono font-bold text-gray-700">{(macro.yield_curve_score as number).toFixed(0)}</span>
                </div>
              )}
              {macro?.vix_score != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-gray-400 tracking-wider">VIX</span>
                  <span className="font-mono font-bold text-gray-700">{(macro.vix_score as number).toFixed(0)}</span>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {gate_summary?.fat_pitches_count > 0 && (
              <a href="/v2/gates" className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-full text-[10px] text-emerald-700 font-bold hover:bg-emerald-100 transition-colors">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                {gate_summary.fat_pitches_count} Fat {gate_summary.fat_pitches_count === 1 ? 'Pitch' : 'Pitches'}
              </a>
            )}
            <button onClick={load} className="text-[9px] text-gray-400 hover:text-emerald-600 transition-colors tracking-widest uppercase">
              Refresh
            </button>
            {refreshed && (
              <span className="text-[9px] text-gray-300">
                {refreshed.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Main 3-column grid ── */}
      <div className="flex-1 overflow-hidden">
        <div className="grid grid-cols-[260px_1fr_280px] h-full divide-x divide-gray-200 max-w-[1600px] mx-auto">

          {/* ── LEFT: Macro Environment ── */}
          <div className="overflow-y-auto p-4 space-y-4">
            <div className="text-[9px] text-gray-400 tracking-widest uppercase font-semibold px-1">Macro Environment</div>

            {/* Regime summary */}
            <div className="bg-white border border-gray-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <RegimeBadge regime={macro?.regime || ''} />
                <span className={`text-2xl font-bold font-mono ${macroScore >= 60 ? 'text-emerald-600' : macroScore >= 40 ? 'text-amber-600' : 'text-rose-600'}`}>
                  {macroScore.toFixed(0)}
                </span>
              </div>
              <div className="space-y-2">
                {[
                  { label: 'Fed Policy', score: macro?.fed_funds_score },
                  { label: 'Yield Curve', score: macro?.yield_curve_score },
                  { label: 'Credit Spreads', score: macro?.credit_spreads_score },
                  { label: 'DXY', score: macro?.dxy_score },
                  { label: 'VIX', score: macro?.vix_score },
                  { label: 'M2 Liquidity', score: macro?.m2_score },
                  { label: 'Real Rates', score: macro?.real_rates_score },
                ].filter(x => x.score != null).map(({ label, score }) => {
                  const s = score as number;
                  const pct = Math.min(100, Math.max(0, s));
                  const barColor = s >= 60 ? 'bg-emerald-400' : s >= 40 ? 'bg-amber-400' : 'bg-rose-400';
                  return (
                    <div key={label} className="flex items-center gap-2">
                      <div className="text-[9px] text-gray-500 w-20 truncate">{label}</div>
                      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
                      </div>
                      <div className={`text-[10px] font-mono font-bold w-6 text-right ${s >= 60 ? 'text-emerald-600' : s >= 40 ? 'text-amber-600' : 'text-rose-600'}`}>
                        {s.toFixed(0)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Gate funnel summary */}
            {gate_summary?.total > 0 && (
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Gate Funnel</div>
                <div className="space-y-1.5">
                  {Object.entries(gate_summary.gate_counts || {}).map(([gate, count]) => {
                    const total = gate_summary.total || 1;
                    const pct = ((count as number) / total) * 100;
                    return (
                      <div key={gate} className="flex items-center gap-2">
                        <div className="text-[9px] text-gray-500 w-5 text-right font-mono">G{gate}</div>
                        <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                          <div className="h-full bg-blue-400 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="text-[9px] font-mono text-gray-600 w-8 text-right">{count as number}</div>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-2 pt-2 border-t border-gray-100 flex items-center justify-between">
                  <span className="text-[9px] text-gray-400">Universe: {gate_summary.total}</span>
                  <a href="/v2/gates" className="text-[9px] text-emerald-600 hover:underline">See cascade →</a>
                </div>
              </div>
            )}

            {/* Economic indicators */}
            {key_indicators.length > 0 && (
              <div className="bg-white border border-gray-200 rounded-xl p-4">
                <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Key Indicators</div>
                <div className="space-y-2">
                  {key_indicators.map((ind, i) => {
                    const z = (ind.z_score as number) || 0;
                    const yoy = ind.yoy_pct_change as number;
                    return (
                      <div key={i} className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-[9px] text-gray-700 truncate font-medium">{ind.name}</div>
                          <div className="text-[8px] text-gray-400">{ind.category}</div>
                        </div>
                        <div className="text-right shrink-0">
                          <div className="text-[10px] font-mono font-semibold text-gray-800">
                            {(ind.value as number)?.toFixed(2)}
                          </div>
                          {yoy != null && (
                            <div className={`text-[8px] font-mono ${yoy > 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
                              {yoy > 0 ? '+' : ''}{yoy.toFixed(1)}%
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* ── CENTER: Intelligence Feed ── */}
          <div className="overflow-y-auto p-5 space-y-5">
            <div className="text-[9px] text-gray-400 tracking-widest uppercase font-semibold px-1">Intelligence Feed</div>

            {/* Fat Pitches — newspaper headline style */}
            {fat_pitches.length > 0 && (
              <section>
                <div className="flex items-center justify-between mb-3">
                  <div className="text-[10px] font-semibold text-gray-800 tracking-wide uppercase">
                    Today&apos;s Fat Pitches
                    <span className="ml-2 text-[9px] bg-emerald-500 text-white px-1.5 py-0.5 rounded font-bold">{fat_pitches.length}</span>
                  </div>
                  <a href="/v2/gates" className="text-[9px] text-gray-400 hover:text-emerald-600 transition-colors tracking-wider">View all →</a>
                </div>
                <div className="space-y-2">
                  {fat_pitches.map((fp, i) => (
                    <div key={i} className="bg-white border border-gray-200 rounded-xl p-4 hover:border-emerald-300 hover:shadow-sm transition-all cursor-pointer"
                      onClick={() => openStock(fp.symbol)}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap mb-1">
                            <Ticker symbol={fp.symbol} onClick={() => openStock(fp.symbol)} />
                            <span className="text-[9px] text-gray-400 truncate max-w-[160px]">{fp.name}</span>
                            {fp.sector && <span className="text-[8px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">{fp.sector}</span>}
                            {fp.catalyst_type && (
                              <span className="text-[8px] bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded">{fp.catalyst_type}</span>
                            )}
                          </div>
                          {fp.narrative && (
                            <div className="text-[11px] text-gray-600 leading-relaxed">{fp.narrative}</div>
                          )}
                          <div className="flex items-center gap-3 mt-2">
                            {fp.entry_price && (
                              <span className="text-[9px] text-blue-600 font-mono">Entry ${fp.entry_price.toFixed(2)}</span>
                            )}
                            {fp.target_price && (
                              <span className="text-[9px] text-emerald-600 font-mono">Target ${fp.target_price.toFixed(2)}</span>
                            )}
                            {fp.rr_ratio && (
                              <span className="text-[9px] text-gray-500 font-mono">R:R {fp.rr_ratio.toFixed(1)}x</span>
                            )}
                            {fp.module_count && (
                              <span className="text-[9px] text-gray-400">{fp.module_count} signals</span>
                            )}
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <ScoreBadge score={fp.composite_score ?? fp.convergence_score} size="lg" />
                          <div className={`text-[9px] mt-1 font-semibold ${fp.signal?.includes('BUY') ? 'text-emerald-600' : 'text-gray-500'}`}>
                            {fp.signal}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Score movers */}
            {score_movers.length > 0 && (
              <section>
                <div className="text-[10px] font-semibold text-gray-800 tracking-wide uppercase mb-3">
                  Score Movers Today
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {score_movers.map((m, i) => {
                    const delta = m.delta as number;
                    const up = delta > 0;
                    return (
                      <div
                        key={i}
                        className={`bg-white border rounded-xl p-3 cursor-pointer hover:shadow-sm transition-all ${up ? 'border-emerald-200 hover:border-emerald-300' : 'border-rose-200 hover:border-rose-300'}`}
                        onClick={() => openStock(m.symbol)}
                      >
                        <div className="flex items-center justify-between">
                          <Ticker symbol={m.symbol} onClick={() => openStock(m.symbol)} />
                          <span className={`text-[11px] font-mono font-bold ${up ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {up ? '+' : ''}{delta.toFixed(1)}
                          </span>
                        </div>
                        <div className="text-[9px] text-gray-400 truncate mt-0.5">{m.name}</div>
                        <div className="flex items-center gap-1.5 mt-1.5">
                          <ScoreBadge score={m.convergence_score} />
                          {m.conviction_level && (
                            <span className={`text-[8px] px-1 py-0.5 rounded font-bold ${
                              m.conviction_level === 'HIGH' ? 'bg-emerald-100 text-emerald-700'
                              : m.conviction_level === 'NOTABLE' ? 'bg-amber-100 text-amber-700'
                              : 'bg-gray-100 text-gray-500'
                            }`}>{m.conviction_level}</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {/* Catalyst events */}
            {catalysts.length > 0 && (
              <section>
                <div className="text-[10px] font-semibold text-gray-800 tracking-wide uppercase mb-3">
                  Active Catalysts
                </div>
                <div className="space-y-2">
                  {catalysts.map((cat, i) => (
                    <div
                      key={i}
                      className="bg-white border border-amber-200 rounded-xl p-3 cursor-pointer hover:bg-amber-50 transition-colors"
                      onClick={() => openStock(cat.symbol)}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Ticker symbol={cat.symbol} onClick={() => openStock(cat.symbol)} />
                        <span className="text-[8px] bg-amber-100 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded font-semibold">{cat.catalyst_type}</span>
                        <ScoreBadge score={cat.catalyst_strength} />
                      </div>
                      <div className="text-[10px] text-gray-600 leading-relaxed">{cat.catalyst_detail}</div>
                      {cat.sector && <div className="text-[9px] text-gray-400 mt-1">{cat.name} · {cat.sector}</div>}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {fat_pitches.length === 0 && score_movers.length === 0 && catalysts.length === 0 && (
              <div className="text-center py-16 text-gray-400 text-sm">
                <div className="text-2xl mb-2">—</div>
                No intelligence data yet. Run the pipeline to generate signals.
              </div>
            )}
          </div>

          {/* ── RIGHT: Insider Flow ── */}
          <div className="overflow-y-auto p-4 space-y-4">
            <div className="flex items-center justify-between px-1">
              <div className="text-[9px] text-gray-400 tracking-widest uppercase font-semibold">Insider Flow</div>
              <a href="/insider" className="text-[9px] text-gray-400 hover:text-emerald-600 transition-colors tracking-wider">All →</a>
            </div>

            {insider_flow.length === 0 ? (
              <div className="bg-white border border-gray-200 rounded-xl p-6 text-center text-gray-400 text-[11px]">
                No significant insider activity<br />in the last 14 days
              </div>
            ) : (
              <div className="space-y-2">
                {insider_flow.map((txn, i) => {
                  const isBuy = (txn.transaction_type || '').toLowerCase().includes('buy')
                    || txn.transaction_type === 'P';
                  const value = txn.value as number;
                  return (
                    <div
                      key={i}
                      className={`bg-white border rounded-xl p-3 cursor-pointer hover:shadow-sm transition-all ${
                        isBuy ? 'border-emerald-200 hover:border-emerald-300' : 'border-rose-200 hover:border-rose-300'
                      }`}
                      onClick={() => openStock(txn.symbol)}
                    >
                      {/* Direction + amount */}
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-1.5">
                          <span className={`text-[8px] font-bold uppercase px-1.5 py-0.5 rounded ${
                            isBuy ? 'bg-emerald-500 text-white' : 'bg-rose-500 text-white'
                          }`}>{isBuy ? 'BUY' : 'SELL'}</span>
                          <Ticker symbol={txn.symbol} onClick={() => openStock(txn.symbol)} />
                          {txn.cluster_buy && (
                            <span className="text-[7px] bg-emerald-100 text-emerald-700 border border-emerald-200 px-1 py-0.5 rounded font-bold">CLUSTER</span>
                          )}
                        </div>
                        <span className={`text-[12px] font-mono font-bold ${isBuy ? 'text-emerald-700' : 'text-rose-700'}`}>
                          {fmtM(value)}
                        </span>
                      </div>

                      {/* Company name */}
                      <div className="text-[9px] text-gray-500 mb-1 truncate">{txn.company_name}</div>

                      {/* Insider name + title */}
                      {txn.insider_name && (
                        <div className="text-[9px] text-gray-400 truncate">
                          {txn.insider_name}
                          {txn.insider_title && <span className="text-gray-300"> · {txn.insider_title}</span>}
                        </div>
                      )}

                      {/* Date */}
                      <div className="text-[8px] text-gray-300 mt-1">{txn.transaction_date}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
