'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type EnergyIntelSignal,
  type EnergyAnomaly,
  type EnergySupplyData,
  type EnergyProductionData,
  type JodiRecord,
  type EnergyBalance,
} from '@/lib/api';
import { EnergyAnomalyBanner } from '@/components/EnergyAnomalyBanner';
import { EnergyTickerTable } from '@/components/EnergyTickerTable';
import { EnergySupplyTab } from '@/components/EnergySupplyTab';
import { EnergyProductionTab } from '@/components/EnergyProductionTab';
import { EnergyFlowsTab } from '@/components/EnergyFlowsTab';
import { EnergyGlobalTab } from '@/components/EnergyGlobalTab';

const TABS = [
  { key: 'supply', label: 'SUPPLY BALANCE' },
  { key: 'production', label: 'PRODUCTION & DEMAND' },
  { key: 'flows', label: 'TRADE FLOWS' },
  { key: 'global', label: 'GLOBAL BALANCE' },
];

export default function EnergyContent() {
  const [tab, setTab] = useState('supply');
  const [signals, setSignals] = useState<EnergyIntelSignal[]>([]);
  const [summary, setSummary] = useState<Record<string, number>>({});
  const [anomalies, setAnomalies] = useState<EnergyAnomaly[]>([]);
  const [supply, setSupply] = useState<EnergySupplyData | null>(null);
  const [production, setProduction] = useState<EnergyProductionData | null>(null);
  const [tradeFlows, setTradeFlows] = useState<Record<string, unknown> | null>(null);
  const [globalBalance, setGlobalBalance] = useState<{
    jodi_data: JodiRecord[]; balance: EnergyBalance | null;
    global_stocks: { country: string; value: number; mom_change: number | null }[];
  } | null>(null);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.energyIntel()
      .then((d) => { setSignals(d.signals); setSummary(d.summary); setAnomalies(d.anomalies); })
      .catch((e) => setError(e.message || 'Failed to load energy data'));
    api.energySupplyBalance().then(setSupply).catch(() => {});
  }, []);

  useEffect(() => {
    if (tab === 'production' && !production) api.energyProduction().then(setProduction).catch(() => {});
    if (tab === 'flows' && !tradeFlows) api.energyTradeFlows().then(setTradeFlows).catch(() => {});
    if (tab === 'global' && !globalBalance) api.energyGlobalBalance().then(setGlobalBalance).catch(() => {});
  }, [tab, production, tradeFlows, globalBalance]);

  const bullish = signals.filter((s) => s.energy_intel_score >= 55).length;
  const bearish = signals.filter((s) => s.energy_intel_score < 45).length;
  const avgScore = summary?.avg_score ?? 0;
  const overallColorClass = avgScore >= 55 ? 'text-[#059669]' : avgScore >= 45 ? 'text-[#d97706]' : 'text-[#e11d48]';
  const overallBgClass = avgScore >= 55 ? 'bg-[#05966920] text-[#059669]' : avgScore >= 45 ? 'bg-[#d9770620] text-[#d97706]' : 'bg-[#e11d4820] text-[#e11d48]';
  const overallLabel = avgScore >= 55 ? 'BULLISH' : avgScore >= 45 ? 'NEUTRAL' : 'BEARISH';

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-6">
      <div>
        <h1 className="font-display text-2xl font-bold text-gray-900">ENERGY INTELLIGENCE</h1>
        <p className="text-[10px] text-gray-500 tracking-widest mt-1">SUPPLY-DEMAND FUNDAMENTALS | EIA + JODI + COMTRADE</p>
      </div>
      <div className="grid grid-cols-4 gap-3">
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Overall Signal</div>
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl font-display font-bold ${overallColorClass}`}>{avgScore.toFixed(0)}</span>
            <span className={`text-[10px] tracking-widest font-bold px-2 py-0.5 rounded ${overallBgClass}`}>{overallLabel}</span>
          </div>
        </div>
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Tickers Scored</div>
          <span className="text-3xl font-display font-bold text-gray-900">{signals.length}</span>
        </div>
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Bullish / Bearish</div>
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-display font-bold text-[#059669]">{bullish}</span>
            <span className="text-gray-500">/</span>
            <span className="text-xl font-display font-bold text-[#e11d48]">{bearish}</span>
          </div>
        </div>
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Active Anomalies</div>
          <span className={`text-3xl font-display font-bold ${anomalies.length > 0 ? 'text-[#d97706]' : 'text-[#059669]'}`}>{anomalies.length}</span>
        </div>
      </div>
      {error && (
        <div className="panel p-4 border-rose-200 bg-rose-50">
          <div className="text-rose-600 text-sm font-bold mb-1">Failed to load energy data</div>
          <p className="text-[11px] text-gray-500">{error}</p>
        </div>
      )}
      <EnergyAnomalyBanner anomalies={anomalies} />
      <EnergyTickerTable signals={signals} />
      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-[10px] tracking-widest transition-all ${tab === t.key ? 'text-emerald-600 border-b-2 border-emerald-600' : 'text-gray-500 hover:text-gray-700'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'supply' && (supply ? <EnergySupplyTab supply={supply} /> : <div className="panel p-8 text-center text-gray-400 animate-pulse text-sm">Computing supply-demand balance...</div>)}
      {tab === 'production' && (production ? <EnergyProductionTab production={production} /> : <div className="panel p-8 text-center text-gray-400 animate-pulse text-sm">Analyzing production and demand trends...</div>)}
      {tab === 'flows' && (tradeFlows ? <EnergyFlowsTab tradeFlows={tradeFlows} /> : <div className="panel p-8 text-center text-gray-400 animate-pulse text-sm">Mapping global trade flow patterns...</div>)}
      {tab === 'global' && (globalBalance ? <EnergyGlobalTab globalBalance={globalBalance} /> : <div className="panel p-8 text-center text-gray-400 animate-pulse text-sm">Aggregating global inventory balance...</div>)}
      {signals.length === 0 && (
        <div className="panel p-12 text-center">
          <div className="text-gray-400 text-sm mb-2">Energy intelligence data not yet available</div>
          <div className="text-gray-300 text-xs">Energy data is sourced from EIA, JODI, and COMTRADE feeds. Data populates after the daily pipeline completes.</div>
        </div>
      )}
    </div>
  );
}
