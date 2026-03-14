'use client';

import React, { useEffect, useState } from 'react';
import {
  api,
  type EnergyIntelSignal,
  type EnergyInventory,
  type EnergyAnomaly,
  type EnergySupplyData,
  type EnergyProductionData,
  type JodiRecord,
  type EnergyBalance,
} from '@/lib/api';

const TABS = [
  { key: 'supply', label: 'SUPPLY BALANCE' },
  { key: 'production', label: 'PRODUCTION & DEMAND' },
  { key: 'flows', label: 'TRADE FLOWS' },
  { key: 'global', label: 'GLOBAL BALANCE' },
];

const CATEGORY_COLORS: Record<string, string> = {
  upstream: '#00FF41',
  downstream: '#FFB800',
  midstream: '#00D4FF',
  ofs: '#FF6B35',
  lng: '#B388FF',
};

function ScoreBar({ score, label }: { score: number; label?: string }) {
  const color = score >= 65 ? '#00FF41' : score >= 45 ? '#FFB800' : '#FF073A';
  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-[9px] text-terminal-dim w-16 uppercase">{label}</span>}
      <div className="flex-1 h-1.5 bg-terminal-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${score}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-mono w-8 text-right" style={{ color }}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}

function InventoryCard({ inv }: { inv: EnergyInventory }) {
  const isDrawColor = inv.draw_build === 'DRAW' ? '#00FF41' : inv.draw_build === 'BUILD' ? '#FF073A' : '#FFB800';
  const vsAvg =
    inv.seasonal_avg != null ? ((inv.value - inv.seasonal_avg) / inv.seasonal_avg) * 100 : null;

  return (
    <div className="panel p-4">
      <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">{inv.name}</div>
      <div className="flex items-baseline gap-3 mb-2">
        <span className="text-2xl font-display font-bold text-terminal-bright">
          {(inv.value / 1000).toFixed(1)}
          <span className="text-xs text-terminal-dim ml-1">M bbl</span>
        </span>
        {inv.wow_change != null && (
          <span
            className="text-xs font-mono px-1.5 py-0.5 rounded"
            style={{ backgroundColor: `${isDrawColor}15`, color: isDrawColor }}
          >
            {inv.wow_change > 0 ? '+' : ''}
            {(inv.wow_change / 1000).toFixed(1)}M
          </span>
        )}
      </div>
      {inv.draw_build && (
        <span
          className="text-[10px] tracking-widest font-bold px-2 py-0.5 rounded"
          style={{ backgroundColor: `${isDrawColor}20`, color: isDrawColor }}
        >
          {inv.draw_build}
        </span>
      )}
      {vsAvg != null && (
        <div className="mt-2 text-[10px] text-terminal-dim">
          vs 5yr avg: <span className={vsAvg < 0 ? 'text-green-400' : 'text-red-400'}>{vsAvg > 0 ? '+' : ''}{vsAvg.toFixed(1)}%</span>
        </div>
      )}
      {inv.seasonal_min != null && inv.seasonal_max != null && (
        <div className="mt-2">
          <div className="relative h-1 bg-terminal-border rounded-full">
            {/* 5yr range bar */}
            <div className="absolute h-full bg-terminal-dim/20 rounded-full" style={{
              left: '0%', width: '100%'
            }} />
            {/* Current value needle */}
            {inv.seasonal_min < inv.seasonal_max && (
              <div
                className="absolute top-[-2px] bottom-[-2px] w-1 rounded-full bg-terminal-bright"
                style={{
                  left: `${Math.max(0, Math.min(100, ((inv.value - inv.seasonal_min) / (inv.seasonal_max - inv.seasonal_min)) * 100))}%`,
                }}
              />
            )}
          </div>
          <div className="flex justify-between text-[8px] text-terminal-dim mt-0.5">
            <span>{(inv.seasonal_min / 1000).toFixed(0)}M</span>
            <span>{(inv.seasonal_max / 1000).toFixed(0)}M</span>
          </div>
        </div>
      )}
    </div>
  );
}

function AnomalyBanner({ anomalies }: { anomalies: EnergyAnomaly[] }) {
  if (!anomalies.length) return null;
  const severityColor: Record<string, string> = {
    critical: '#FF073A',
    high: '#FF6B35',
    medium: '#FFB800',
    low: '#00D4FF',
  };

  return (
    <div className="space-y-2 mb-4">
      {anomalies.map((a, i) => (
        <div
          key={i}
          className="panel p-3 flex items-start gap-3"
          style={{ borderLeft: `3px solid ${severityColor[a.severity] || '#FFB800'}` }}
        >
          <span
            className="text-[9px] tracking-widest font-bold px-1.5 py-0.5 rounded shrink-0"
            style={{
              backgroundColor: `${severityColor[a.severity]}20`,
              color: severityColor[a.severity],
            }}
          >
            {a.severity.toUpperCase()}
          </span>
          <div>
            <div className="text-xs text-terminal-text">{a.description}</div>
            <div className="text-[9px] text-terminal-dim mt-0.5">
              z-score: {a.zscore?.toFixed(2)} | Affected: {a.affected_tickers}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function EnergyPage() {
  const [tab, setTab] = useState('supply');
  const [signals, setSignals] = useState<EnergyIntelSignal[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [anomalies, setAnomalies] = useState<EnergyAnomaly[]>([]);
  const [supply, setSupply] = useState<EnergySupplyData | null>(null);
  const [production, setProduction] = useState<EnergyProductionData | null>(null);
  const [tradeFlows, setTradeFlows] = useState<Record<string, unknown> | null>(null);
  const [globalBalance, setGlobalBalance] = useState<{
    jodi_data: JodiRecord[];
    balance: EnergyBalance | null;
    global_stocks: { country: string; value: number; mom_change: number | null }[];
  } | null>(null);

  useEffect(() => {
    api.energyIntel().then((d) => {
      setSignals(d.signals);
      setSummary(d.summary);
      setAnomalies(d.anomalies);
    }).catch(() => {});
    api.energySupplyBalance().then(setSupply).catch(() => {});
  }, []);

  useEffect(() => {
    if (tab === 'production' && !production) {
      api.energyProduction().then(setProduction).catch(() => {});
    }
    if (tab === 'flows' && !tradeFlows) {
      api.energyTradeFlows().then(setTradeFlows).catch(() => {});
    }
    if (tab === 'global' && !globalBalance) {
      api.energyGlobalBalance().then(setGlobalBalance).catch(() => {});
    }
  }, [tab, production, tradeFlows, globalBalance]);

  const bullish = signals.filter((s) => s.energy_intel_score >= 55).length;
  const bearish = signals.filter((s) => s.energy_intel_score < 45).length;
  const avgScore = summary?.avg_score ?? 0;
  const overallColor = avgScore >= 55 ? '#00FF41' : avgScore >= 45 ? '#FFB800' : '#FF073A';
  const overallLabel = avgScore >= 55 ? 'BULLISH' : avgScore >= 45 ? 'NEUTRAL' : 'BEARISH';

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright">
          ENERGY INTELLIGENCE
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          SUPPLY-DEMAND FUNDAMENTALS | EIA + JODI + COMTRADE
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-3">
        <div className="panel p-4">
          <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">Overall Signal</div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-display font-bold" style={{ color: overallColor }}>
              {avgScore.toFixed(0)}
            </span>
            <span
              className="text-[10px] tracking-widest font-bold px-2 py-0.5 rounded"
              style={{ backgroundColor: `${overallColor}20`, color: overallColor }}
            >
              {overallLabel}
            </span>
          </div>
        </div>
        <div className="panel p-4">
          <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">Tickers Scored</div>
          <span className="text-3xl font-display font-bold text-terminal-bright">
            {signals.length}
          </span>
        </div>
        <div className="panel p-4">
          <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">Bullish / Bearish</div>
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-display font-bold text-green-400">{bullish}</span>
            <span className="text-terminal-dim">/</span>
            <span className="text-xl font-display font-bold text-red-400">{bearish}</span>
          </div>
        </div>
        <div className="panel p-4">
          <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">Active Anomalies</div>
          <span
            className="text-3xl font-display font-bold"
            style={{ color: anomalies.length > 0 ? '#FFB800' : '#00FF41' }}
          >
            {anomalies.length}
          </span>
        </div>
      </div>

      {/* Anomaly Alerts */}
      <AnomalyBanner anomalies={anomalies} />

      {/* Scores Table */}
      {signals.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="p-4 border-b border-terminal-border">
            <h2 className="text-xs tracking-widest text-terminal-dim uppercase">
              Energy Ticker Scores
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-terminal-border text-[9px] text-terminal-dim tracking-widest uppercase">
                  <th className="text-left px-4 py-2">Symbol</th>
                  <th className="text-left px-4 py-2">Category</th>
                  <th className="text-left px-4 py-2 w-48">Score</th>
                  <th className="text-right px-4 py-2">Inventory</th>
                  <th className="text-right px-4 py-2">Production</th>
                  <th className="text-right px-4 py-2">Demand</th>
                  <th className="text-right px-4 py-2">Flows</th>
                  <th className="text-right px-4 py-2">Global</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s) => {
                  const color =
                    s.energy_intel_score >= 65
                      ? '#00FF41'
                      : s.energy_intel_score >= 45
                      ? '#FFB800'
                      : '#FF073A';
                  return (
                    <tr
                      key={s.symbol}
                      className="border-b border-terminal-border/30 hover:bg-white/[0.02]"
                    >
                      <td className="px-4 py-2 font-mono font-bold text-terminal-bright">
                        {s.symbol}
                      </td>
                      <td className="px-4 py-2">
                        <span
                          className="text-[9px] tracking-wider px-1.5 py-0.5 rounded"
                          style={{
                            backgroundColor: `${CATEGORY_COLORS[s.ticker_category] || '#888'}15`,
                            color: CATEGORY_COLORS[s.ticker_category] || '#888',
                          }}
                        >
                          {s.ticker_category.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-4 py-2">
                        <ScoreBar score={s.energy_intel_score} />
                      </td>
                      <td className="px-4 py-2 text-right font-mono" style={{ color }}>
                        {s.inventory_signal?.toFixed(0)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono" style={{ color }}>
                        {s.production_signal?.toFixed(0)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono" style={{ color }}>
                        {s.demand_signal?.toFixed(0)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono" style={{ color }}>
                        {s.trade_flow_signal?.toFixed(0)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono" style={{ color }}>
                        {s.global_balance_signal?.toFixed(0)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tabbed Detail */}
      <div className="flex gap-1 border-b border-terminal-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-[10px] tracking-widest transition-all ${
              tab === t.key
                ? 'text-terminal-green border-b-2 border-terminal-green'
                : 'text-terminal-dim hover:text-terminal-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Supply Balance Tab */}
      {tab === 'supply' && supply && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {supply.inventories.map((inv) => (
              <InventoryCard key={inv.series_id} inv={inv} />
            ))}
          </div>
          {supply.days_of_supply && (
            <div className="panel p-4">
              <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-1">
                Days of Crude Supply
              </div>
              <span className="text-2xl font-display font-bold text-terminal-bright">
                {supply.days_of_supply.value.toFixed(1)}
                <span className="text-xs text-terminal-dim ml-1">days</span>
              </span>
            </div>
          )}
          {supply.crude_history.length > 0 && (
            <div className="panel p-4">
              <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-3">
                US Crude Stocks — 12 Month Trend
              </div>
              <div className="h-40 flex items-end gap-[2px]">
                {supply.crude_history.slice(-52).map((h, i) => {
                  const vals = supply.crude_history.slice(-52).map((v) => v.value);
                  const mn = Math.min(...vals);
                  const mx = Math.max(...vals);
                  const range = mx - mn || 1;
                  const pct = ((h.value - mn) / range) * 100;
                  return (
                    <div
                      key={i}
                      className="flex-1 rounded-t bg-terminal-green/30 hover:bg-terminal-green/60 transition-colors"
                      style={{ height: `${Math.max(4, pct)}%` }}
                      title={`${h.date}: ${(h.value / 1000).toFixed(1)}M bbl`}
                    />
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Production & Demand Tab */}
      {tab === 'production' && production && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* US Production */}
            <div className="panel p-4">
              <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-2">
                US Crude Production (Mb/d)
              </div>
              {production.production[0] && (
                <div className="text-2xl font-display font-bold text-terminal-bright mb-3">
                  {production.production[0].value.toFixed(1)}
                </div>
              )}
              <div className="h-24 flex items-end gap-[2px]">
                {production.production
                  .slice()
                  .reverse()
                  .slice(-26)
                  .map((p, i) => {
                    const vals = production.production.map((v) => v.value);
                    const mn = Math.min(...vals);
                    const mx = Math.max(...vals);
                    const range = mx - mn || 1;
                    const pct = ((p.value - mn) / range) * 100;
                    return (
                      <div
                        key={i}
                        className="flex-1 rounded-t bg-blue-500/30"
                        style={{ height: `${Math.max(4, pct)}%` }}
                        title={`${p.date}: ${p.value.toFixed(1)}`}
                      />
                    );
                  })}
              </div>
            </div>

            {/* Refinery Utilization */}
            <div className="panel p-4">
              <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-2">
                Refinery Utilization (%)
              </div>
              {production.refinery_util[0] && (
                <div className="text-2xl font-display font-bold text-terminal-bright mb-3">
                  {production.refinery_util[0].value.toFixed(1)}%
                </div>
              )}
              <div className="h-24 flex items-end gap-[2px]">
                {production.refinery_util
                  .slice()
                  .reverse()
                  .slice(-26)
                  .map((r, i) => {
                    const color = r.value >= 92 ? '#00FF41' : r.value >= 85 ? '#FFB800' : '#FF073A';
                    return (
                      <div
                        key={i}
                        className="flex-1 rounded-t"
                        style={{
                          height: `${Math.max(4, r.value)}%`,
                          backgroundColor: `${color}40`,
                        }}
                        title={`${r.date}: ${r.value.toFixed(1)}%`}
                      />
                    );
                  })}
              </div>
            </div>

            {/* Product Supplied (Implied Demand) */}
            <div className="panel p-4">
              <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-2">
                Total Product Supplied (Mb/d)
              </div>
              {production.product_supplied[0] && (
                <div className="text-2xl font-display font-bold text-terminal-bright mb-3">
                  {production.product_supplied[0].value.toFixed(1)}
                </div>
              )}
              <div className="h-24 flex items-end gap-[2px]">
                {production.product_supplied
                  .slice()
                  .reverse()
                  .slice(-26)
                  .map((d, i) => {
                    const vals = production.product_supplied.map((v) => v.value);
                    const mn = Math.min(...vals);
                    const mx = Math.max(...vals);
                    const range = mx - mn || 1;
                    const pct = ((d.value - mn) / range) * 100;
                    return (
                      <div
                        key={i}
                        className="flex-1 rounded-t bg-purple-500/30"
                        style={{ height: `${Math.max(4, pct)}%` }}
                        title={`${d.date}: ${d.value.toFixed(1)}`}
                      />
                    );
                  })}
              </div>
            </div>

            {/* Crack Spread */}
            <div className="panel p-4">
              <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-2">
                Crack Spread (Gasoline - WTI)
              </div>
              {production.crack_spread[0] && (
                <div className="text-2xl font-display font-bold text-terminal-bright mb-3">
                  ${production.crack_spread[0].value.toFixed(2)}
                </div>
              )}
              <div className="h-24 flex items-end gap-[2px]">
                {production.crack_spread
                  .slice()
                  .reverse()
                  .slice(-26)
                  .map((c, i) => {
                    const vals = production.crack_spread.map((v) => v.value);
                    const mn = Math.min(...vals);
                    const mx = Math.max(...vals);
                    const range = mx - mn || 1;
                    const pct = ((c.value - mn) / range) * 100;
                    const color = c.value > 0 ? '#00FF41' : '#FF073A';
                    return (
                      <div
                        key={i}
                        className="flex-1 rounded-t"
                        style={{
                          height: `${Math.max(4, Math.abs(pct))}%`,
                          backgroundColor: `${color}40`,
                        }}
                        title={`${c.date}: $${c.value.toFixed(2)}`}
                      />
                    );
                  })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Trade Flows Tab */}
      {tab === 'flows' && tradeFlows && (
        <div className="space-y-4">
          {/* PADD District Stocks */}
          {(tradeFlows as Record<string, unknown[]>).padd_stocks?.length > 0 && (
            <div className="panel overflow-hidden">
              <div className="p-4 border-b border-terminal-border">
                <h3 className="text-xs tracking-widest text-terminal-dim uppercase">
                  PADD District Crude Stocks
                </h3>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-terminal-border text-[9px] text-terminal-dim tracking-widest uppercase">
                    <th className="text-left px-4 py-2">District</th>
                    <th className="text-right px-4 py-2">Stocks (M bbl)</th>
                  </tr>
                </thead>
                <tbody>
                  {((tradeFlows as Record<string, { description: string; value: number }[]>).padd_stocks || []).map(
                    (p, i) => (
                      <tr key={i} className="border-b border-terminal-border/30">
                        <td className="px-4 py-2 text-terminal-text">{p.description}</td>
                        <td className="px-4 py-2 text-right font-mono text-terminal-bright">
                          {(p.value / 1000).toFixed(1)}
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Imports by Country */}
          {(tradeFlows as Record<string, unknown[]>).import_by_country?.length > 0 && (
            <div className="panel overflow-hidden">
              <div className="p-4 border-b border-terminal-border">
                <h3 className="text-xs tracking-widest text-terminal-dim uppercase">
                  US Crude Import Origins
                </h3>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-terminal-border text-[9px] text-terminal-dim tracking-widest uppercase">
                    <th className="text-left px-4 py-2">Source</th>
                    <th className="text-right px-4 py-2">Volume (Mb/d)</th>
                  </tr>
                </thead>
                <tbody>
                  {((tradeFlows as Record<string, { description: string; value: number }[]>).import_by_country || []).map(
                    (c, i) => (
                      <tr key={i} className="border-b border-terminal-border/30">
                        <td className="px-4 py-2 text-terminal-text">{c.description}</td>
                        <td className="px-4 py-2 text-right font-mono text-terminal-bright">
                          {c.value.toFixed(1)}
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Global Balance Tab */}
      {tab === 'global' && globalBalance && (
        <div className="space-y-4">
          {/* Balance Summary */}
          {globalBalance.balance && (
            <div className="panel p-6">
              <div className="text-[9px] text-terminal-dim tracking-wider uppercase mb-2">
                Global Supply-Demand Balance (JODI)
              </div>
              <div className="grid grid-cols-3 gap-6">
                <div>
                  <div className="text-[9px] text-terminal-dim uppercase mb-1">Production</div>
                  <span className="text-2xl font-display font-bold text-terminal-bright">
                    {globalBalance.balance.production_total_kbd.toFixed(0)}
                    <span className="text-xs text-terminal-dim ml-1">kbd</span>
                  </span>
                </div>
                <div>
                  <div className="text-[9px] text-terminal-dim uppercase mb-1">Demand</div>
                  <span className="text-2xl font-display font-bold text-terminal-bright">
                    {globalBalance.balance.demand_total_kbd.toFixed(0)}
                    <span className="text-xs text-terminal-dim ml-1">kbd</span>
                  </span>
                </div>
                <div>
                  <div className="text-[9px] text-terminal-dim uppercase mb-1">Balance</div>
                  <span
                    className="text-2xl font-display font-bold"
                    style={{
                      color:
                        globalBalance.balance.balance === 'DEFICIT' ? '#00FF41' : '#FF073A',
                    }}
                  >
                    {globalBalance.balance.surplus_kbd > 0 ? '+' : ''}
                    {globalBalance.balance.surplus_kbd.toFixed(0)}
                    <span className="text-xs ml-1">kbd</span>
                  </span>
                  <span
                    className="ml-2 text-[10px] tracking-widest font-bold px-2 py-0.5 rounded"
                    style={{
                      backgroundColor:
                        globalBalance.balance.balance === 'DEFICIT'
                          ? '#00FF4120'
                          : '#FF073A20',
                      color:
                        globalBalance.balance.balance === 'DEFICIT' ? '#00FF41' : '#FF073A',
                    }}
                  >
                    {globalBalance.balance.balance}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* JODI Country Data */}
          {globalBalance.jodi_data.length > 0 && (
            <div className="panel overflow-hidden">
              <div className="p-4 border-b border-terminal-border">
                <h3 className="text-xs tracking-widest text-terminal-dim uppercase">
                  Country-Level Data (JODI)
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-terminal-border text-[9px] text-terminal-dim tracking-widest uppercase">
                      <th className="text-left px-4 py-2">Country</th>
                      <th className="text-left px-4 py-2">Indicator</th>
                      <th className="text-right px-4 py-2">Value</th>
                      <th className="text-right px-4 py-2">Unit</th>
                      <th className="text-right px-4 py-2">MoM</th>
                      <th className="text-right px-4 py-2">YoY</th>
                    </tr>
                  </thead>
                  <tbody>
                    {globalBalance.jodi_data.map((j, i) => (
                      <tr key={i} className="border-b border-terminal-border/30">
                        <td className="px-4 py-2 text-terminal-text">{j.country}</td>
                        <td className="px-4 py-2 text-terminal-dim capitalize">{j.indicator}</td>
                        <td className="px-4 py-2 text-right font-mono text-terminal-bright">
                          {j.value?.toFixed(0)}
                        </td>
                        <td className="px-4 py-2 text-right text-terminal-dim">{j.unit}</td>
                        <td className="px-4 py-2 text-right font-mono">
                          {j.mom_change != null && (
                            <span style={{ color: j.mom_change > 0 ? '#00FF41' : '#FF073A' }}>
                              {j.mom_change > 0 ? '+' : ''}
                              {j.mom_change.toFixed(0)}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right font-mono">
                          {j.yoy_change != null && (
                            <span style={{ color: j.yoy_change > 0 ? '#00FF41' : '#FF073A' }}>
                              {j.yoy_change > 0 ? '+' : ''}
                              {j.yoy_change.toFixed(0)}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Global Stocks by Country */}
          {globalBalance.global_stocks.length > 0 && (
            <div className="panel overflow-hidden">
              <div className="p-4 border-b border-terminal-border">
                <h3 className="text-xs tracking-widest text-terminal-dim uppercase">
                  Global Oil Stocks by Country
                </h3>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-terminal-border text-[9px] text-terminal-dim tracking-widest uppercase">
                    <th className="text-left px-4 py-2">Country</th>
                    <th className="text-right px-4 py-2">Stocks</th>
                    <th className="text-right px-4 py-2">MoM Change</th>
                  </tr>
                </thead>
                <tbody>
                  {globalBalance.global_stocks.map((s, i) => (
                    <tr key={i} className="border-b border-terminal-border/30">
                      <td className="px-4 py-2 text-terminal-text">{s.country}</td>
                      <td className="px-4 py-2 text-right font-mono text-terminal-bright">
                        {s.value?.toFixed(0)}
                      </td>
                      <td className="px-4 py-2 text-right font-mono">
                        {s.mom_change != null && (
                          <span style={{ color: s.mom_change < 0 ? '#00FF41' : '#FF073A' }}>
                            {s.mom_change > 0 ? '+' : ''}
                            {s.mom_change.toFixed(0)}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {globalBalance.jodi_data.length === 0 && !globalBalance.balance && (
            <div className="panel p-8 text-center text-terminal-dim text-xs">
              No JODI data available yet. Run the pipeline to fetch international oil statistics.
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {signals.length === 0 && (
        <div className="panel p-12 text-center">
          <div className="text-terminal-dim text-sm mb-2">No energy intelligence data yet</div>
          <div className="text-terminal-dim/50 text-xs">
            Run the daily pipeline to fetch EIA data and compute energy scores.
          </div>
        </div>
      )}
    </div>
  );
}
