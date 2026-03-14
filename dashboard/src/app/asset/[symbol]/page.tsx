'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api, type AssetDetail, type PriceBar, type RegulatorySignal, type RegulatoryEvent, type ConvergenceSignal } from '@/lib/api';
import PriceChart from '@/components/PriceChart';
import SignalBadge from '@/components/SignalBadge';
import ScoreBar from '@/components/ScoreBar';
import TradeRangeBar from '@/components/TradeRangeBar';
import ModuleStrip from '@/components/ModuleStrip';
import { scoreColor, MODULES } from '@/lib/modules';

const METRIC_LABELS: Record<string, { label: string; format: (v: number) => string }> = {
  trailingPE: { label: 'P/E Ratio', format: v => v.toFixed(1) },
  priceToBook: { label: 'P/B Ratio', format: v => v.toFixed(2) },
  dividendYield: { label: 'Dividend Yield', format: v => (v * 100).toFixed(2) + '%' },
  revenueGrowth: { label: 'Revenue Growth', format: v => (v * 100).toFixed(1) + '%' },
  earningsGrowth: { label: 'Earnings Growth', format: v => (v * 100).toFixed(1) + '%' },
  returnOnEquity: { label: 'ROE', format: v => (v * 100).toFixed(1) + '%' },
  grossMargins: { label: 'Gross Margin', format: v => (v * 100).toFixed(1) + '%' },
  operatingMargins: { label: 'Op. Margin', format: v => (v * 100).toFixed(1) + '%' },
  debtToEquity: { label: 'Debt/Equity', format: v => v.toFixed(0) },
  currentRatio: { label: 'Current Ratio', format: v => v.toFixed(2) },
  marketCap: { label: 'Market Cap', format: v => `$${(v / 1e9).toFixed(1)}B` },
};

export default function AssetPage() {
  const params = useParams();
  const symbol = decodeURIComponent(params.symbol as string);
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [prices, setPrices] = useState<PriceBar[]>([]);
  const [regData, setRegData] = useState<{ signals: RegulatorySignal[]; events: RegulatoryEvent[] } | null>(null);
  const [conv, setConv] = useState<ConvergenceSignal | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.asset(symbol),
      api.prices(symbol),
      api.regulatorySymbol(symbol).catch(() => null),
      api.convergenceSymbol(symbol).catch(() => null),
    ]).then(([d, p, r, c]) => {
      setDetail(d);
      setPrices(p);
      setRegData(r);
      setConv(c);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [symbol]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">LOADING {symbol}...</div>
      </div>
    );
  }

  if (!detail?.signal) {
    return (
      <div className="panel p-8 text-center">
        <p className="text-terminal-dim">No data available for {symbol}</p>
      </div>
    );
  }

  const s = detail.signal;
  const t = detail.technical;
  const f = detail.fundamental;
  const currentPrice = prices.length > 0 ? prices[0].close : s.entry_price;
  const prevPrice = prices.length > 1 ? prices[1].close : currentPrice;
  const dailyChange = ((currentPrice - prevPrice) / prevPrice) * 100;

  // Split modules into bullish and bearish for the convergence section
  const bullishModules = conv ? MODULES.filter(m => {
    const val = (conv as any)[m.key] as number | null;
    return val != null && val >= 50;
  }).sort((a, b) => ((conv as any)[b.key] ?? 0) - ((conv as any)[a.key] ?? 0)) : [];

  const bearishModules = conv ? MODULES.filter(m => {
    const val = (conv as any)[m.key] as number | null;
    return val != null && val > 0 && val < 25;
  }).sort((a, b) => ((conv as any)[a.key] ?? 0) - ((conv as any)[b.key] ?? 0)) : [];

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-4">
            <h1 className="font-display text-3xl font-bold text-terminal-bright">{symbol}</h1>
            <SignalBadge signal={s.signal} size="lg" />
            {conv && (
              <span className={`text-[10px] font-bold tracking-wider px-2 py-1 rounded-sm ${
                conv.conviction_level === 'high'
                  ? 'text-terminal-green bg-terminal-green/10'
                  : conv.conviction_level === 'medium'
                  ? 'text-terminal-amber bg-terminal-amber/10'
                  : 'text-terminal-dim bg-terminal-dim/10'
              }`}>
                {conv.conviction_level?.toUpperCase()} CONVICTION · {conv.module_count} MODULES
              </span>
            )}
          </div>
          <p className="text-[10px] text-terminal-dim tracking-widest mt-1 uppercase">
            {s.asset_class} · {s.date}
          </p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-display font-bold text-terminal-bright">
            ${currentPrice.toFixed(2)}
          </div>
          <div className={`text-sm font-mono ${dailyChange >= 0 ? 'text-terminal-green' : 'text-terminal-red'}`}>
            {dailyChange >= 0 ? '+' : ''}{dailyChange.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Trade Setup — visual range bar replaces number grid */}
      <div className="panel p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="text-[10px] text-terminal-dim tracking-widest uppercase">
            Trade Setup · R:R {s.rr_ratio.toFixed(1)}:1
          </div>
          {conv && (
            <span
              className="text-2xl font-display font-bold"
              style={{
                color: scoreColor(conv.convergence_score),
                textShadow: conv.convergence_score >= 70 ? `0 0 16px ${scoreColor(conv.convergence_score)}25` : 'none',
              }}
            >
              {conv.convergence_score.toFixed(1)}
              <span className="text-[10px] text-terminal-dim ml-2">CONVERGENCE</span>
            </span>
          )}
        </div>

        {/* Large trade range bar — the centerpiece */}
        <div className="flex justify-center mb-4">
          <TradeRangeBar
            entry={s.entry_price}
            stop={s.stop_loss}
            target={s.target_price}
            currentPrice={currentPrice}
            width={500}
            height={28}
            showLabels
            showRR
          />
        </div>

        {/* Supporting numbers below the visual */}
        <div className="grid grid-cols-5 gap-6 text-center">
          <div>
            <div className="text-[9px] text-terminal-dim mb-1">ENTRY</div>
            <div className="text-sm font-mono text-terminal-cyan">${s.entry_price.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-[9px] text-terminal-dim mb-1">STOP LOSS</div>
            <div className="text-sm font-mono text-terminal-red">${s.stop_loss.toFixed(2)}</div>
            <div className="text-[8px] text-terminal-dim">
              −{((1 - s.stop_loss / s.entry_price) * 100).toFixed(1)}%
            </div>
          </div>
          <div>
            <div className="text-[9px] text-terminal-dim mb-1">TARGET</div>
            <div className="text-sm font-mono text-terminal-green">${s.target_price.toFixed(2)}</div>
            <div className="text-[8px] text-terminal-dim">
              +{((s.target_price / s.entry_price - 1) * 100).toFixed(1)}%
            </div>
          </div>
          <div>
            <div className="text-[9px] text-terminal-dim mb-1">COMPOSITE</div>
            <div className="text-sm font-mono text-terminal-amber">{s.composite_score.toFixed(1)}</div>
          </div>
          <div>
            <div className="text-[9px] text-terminal-dim mb-1">POSITION SIZE</div>
            <div className="text-sm font-mono text-terminal-text">
              {s.position_size_dollars ? `$${s.position_size_dollars.toLocaleString()}` : '—'}
            </div>
            {s.position_size_shares && (
              <div className="text-[8px] text-terminal-dim">{s.position_size_shares.toFixed(1)} shares</div>
            )}
          </div>
        </div>
      </div>

      {/* Convergence Module Breakdown — NEW section */}
      {conv && (
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] text-terminal-dim tracking-widest uppercase">
              Module Convergence · {conv.module_count} agreeing
            </span>
          </div>

          {/* Narrative — full paragraph, not truncated */}
          {conv.narrative && (
            <p className="text-[12px] text-terminal-text leading-relaxed mb-4">
              {conv.narrative}
            </p>
          )}

          <div className="grid grid-cols-3 gap-6">
            {/* Module bar chart */}
            <div className="col-span-2">
              <ModuleStrip convergence={conv} mode="expanded" />
            </div>

            {/* Bullish vs Bearish split */}
            <div className="space-y-4">
              {bullishModules.length > 0 && (
                <div>
                  <div className="text-[9px] text-terminal-green tracking-wider mb-2 font-bold">BULLISH MODULES</div>
                  <div className="space-y-1">
                    {bullishModules.map(m => {
                      const val = (conv as any)[m.key] as number;
                      return (
                        <div key={m.key} className="flex items-center justify-between text-[9px]">
                          <div className="flex items-center gap-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-terminal-green shadow-[0_0_3px_#00FF41]" />
                            <span className="text-terminal-text">{m.label}</span>
                          </div>
                          <span className="font-mono text-terminal-green font-bold">{val.toFixed(0)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {bearishModules.length > 0 && (
                <div>
                  <div className="text-[9px] text-terminal-red tracking-wider mb-2 font-bold">BEARISH MODULES</div>
                  <div className="space-y-1">
                    {bearishModules.map(m => {
                      const val = (conv as any)[m.key] as number;
                      return (
                        <div key={m.key} className="flex items-center justify-between text-[9px]">
                          <div className="flex items-center gap-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-terminal-red" />
                            <span className="text-terminal-text">{m.label}</span>
                          </div>
                          <span className="font-mono text-terminal-red font-bold">{val.toFixed(0)}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
              {bullishModules.length === 0 && bearishModules.length === 0 && (
                <div className="text-[9px] text-terminal-dim">No strong directional signals</div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Price chart — NOW with entry/stop/target lines */}
      <PriceChart data={prices} symbol={symbol} entry={s.entry_price} stop={s.stop_loss} target={s.target_price} />

      {/* Scores */}
      <div className="grid grid-cols-2 gap-4">
        {/* Technical */}
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] text-terminal-dim tracking-widest uppercase">Technical Score</span>
            <span className="text-xl font-display font-bold" style={{
              color: (t?.total_score || 0) > 70 ? '#00FF41' : (t?.total_score || 0) > 40 ? '#FFB800' : '#FF073A'
            }}>
              {t?.total_score.toFixed(1) || '—'} / 100
            </span>
          </div>
          {t && (
            <div className="space-y-3">
              <ScoreBar value={t.trend_score} label="Trend" />
              <ScoreBar value={t.momentum_score} label="Momentum" />
              <ScoreBar value={t.breakout_score} label="Breakout" />
              <ScoreBar value={t.relative_strength_score} label="Rel. Strength" />
              <ScoreBar value={t.breadth_score} label="Breadth" />
            </div>
          )}
        </div>

        {/* Fundamental */}
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] text-terminal-dim tracking-widest uppercase">Fundamental Score</span>
            <span className="text-xl font-display font-bold" style={{
              color: (f?.total_score || 50) > 70 ? '#00FF41' : (f?.total_score || 50) > 40 ? '#FFB800' : '#FF073A'
            }}>
              {f?.total_score.toFixed(1) || '50.0'} / 100
            </span>
          </div>
          {f ? (
            <div className="space-y-3">
              <ScoreBar value={f.valuation_score} label="Valuation" />
              <ScoreBar value={f.growth_score} label="Growth" />
              <ScoreBar value={f.profitability_score} label="Profitability" />
              <ScoreBar value={f.health_score} label="Health" />
              <ScoreBar value={f.quality_score} label="Quality" />
            </div>
          ) : (
            <p className="text-[10px] text-terminal-dim">N/A for {s.asset_class}</p>
          )}
        </div>
      </div>

      {/* Fundamental metrics (stocks only) */}
      {Object.keys(detail.fundamentals).length > 0 && (
        <div className="panel p-5">
          <div className="text-[10px] text-terminal-dim tracking-widest uppercase mb-4">
            Key Metrics
          </div>
          <div className="grid grid-cols-4 gap-4">
            {Object.entries(METRIC_LABELS).map(([key, { label, format }]) => {
              const val = detail.fundamentals[key];
              if (val === undefined) return null;
              return (
                <div key={key}>
                  <div className="text-[9px] text-terminal-dim">{label}</div>
                  <div className="text-sm font-mono text-terminal-text">{format(val)}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Regulatory Risk */}
      {regData && regData.signals.length > 0 && (() => {
        const sig = regData.signals[0];
        const sc = sig.reg_score >= 60 ? '#00FF41' : sig.reg_score >= 40 ? '#FFB800' : '#FF073A';
        const sBg = sig.reg_score >= 60 ? 'rgba(0,255,65,0.15)' : sig.reg_score >= 40 ? 'rgba(255,184,0,0.15)' : 'rgba(255,7,58,0.15)';
        const dirLabel = sig.reg_score > 55 ? 'TAILWIND' : sig.reg_score < 45 ? 'HEADWIND' : 'NEUTRAL';
        const dirBadgeColor = sig.reg_score > 55 ? 'text-terminal-green bg-terminal-green/10' : sig.reg_score < 45 ? 'text-terminal-red bg-terminal-red/10' : 'text-terminal-amber bg-terminal-amber/10';
        return (
          <div className="panel p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <span className="text-[10px] text-terminal-dim tracking-widest uppercase">
                  AI Regulatory Risk
                </span>
                <span className={`px-2 py-0.5 rounded-sm text-[9px] font-bold ${dirBadgeColor}`}>
                  {dirLabel}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[10px] text-terminal-dim">
                  {sig.event_count} event{sig.event_count !== 1 ? 's' : ''}
                </span>
                <span
                  className="text-xl font-display font-bold px-2 py-0.5 rounded-sm"
                  style={{ color: sc, backgroundColor: sBg }}
                >
                  {sig.reg_score.toFixed(0)}
                </span>
              </div>
            </div>

            {sig.narrative && (
              <p className="text-[11px] text-terminal-dim leading-relaxed mb-4">
                {sig.narrative}
              </p>
            )}

            {regData.events.length > 0 && (
              <div className="space-y-2">
                <div className="text-[9px] text-terminal-dim tracking-widest uppercase">
                  CONTRIBUTING EVENTS
                </div>
                {regData.events.slice(0, 5).map((ev, i) => {
                  const sevColor = ev.severity >= 4 ? '#FF073A' : ev.severity >= 3 ? '#FFB800' : ev.severity >= 2 ? '#00E5FF' : '#888';
                  const sevBg = ev.severity >= 4 ? 'rgba(255,7,58,0.15)' : ev.severity >= 3 ? 'rgba(255,184,0,0.15)' : ev.severity >= 2 ? 'rgba(0,229,255,0.12)' : 'rgba(255,255,255,0.05)';
                  return (
                    <div
                      key={`reg-ev-${i}`}
                      className="flex items-start gap-3 py-2 border-b border-terminal-border/30 last:border-0"
                    >
                      <span
                        className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold shrink-0 mt-0.5"
                        style={{ backgroundColor: sevBg, color: sevColor }}
                      >
                        {ev.severity}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] text-terminal-text truncate">
                          {ev.url ? (
                            <a href={ev.url} target="_blank" rel="noopener noreferrer" className="hover:text-terminal-green transition-colors">
                              {ev.title}
                            </a>
                          ) : (
                            ev.title
                          )}
                        </div>
                        {ev.rationale && (
                          <div className="text-[9px] text-terminal-dim mt-0.5 truncate">{ev.rationale}</div>
                        )}
                      </div>
                      <div className={`text-[10px] font-bold shrink-0 ${
                        ev.direction === 'tailwind' ? 'text-terminal-green'
                        : ev.direction === 'headwind' ? 'text-terminal-red'
                        : 'text-terminal-amber'
                      }`}>
                        {ev.direction?.toUpperCase() || '\u2014'}
                      </div>
                    </div>
                  );
                })}
                {regData.events.length > 5 && (
                  <a
                    href="/regulatory"
                    className="block text-[10px] text-terminal-cyan hover:text-terminal-green transition-colors mt-2"
                  >
                    VIEW ALL {regData.events.length} EVENTS →
                  </a>
                )}
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}
