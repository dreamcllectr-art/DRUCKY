'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api, type AssetDetail, type PriceBar, type RegulatorySignal, type RegulatoryEvent, type ConvergenceSignal } from '@/lib/api';
import PriceChart from '@/components/PriceChart';
import SignalBadge from '@/components/SignalBadge';
import ScoreBar from '@/components/ScoreBar';
import { AssetTradeSetup } from '@/components/AssetTradeSetup';
import { AssetConvergencePanel } from '@/components/AssetConvergencePanel';
import { AssetRegulatoryPanel } from '@/components/AssetRegulatoryPanel';

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

export default function AssetContent() {
  const params = useParams();
  const symbol = decodeURIComponent(params.symbol as string);
  const [detail, setDetail] = useState<AssetDetail | null>(null);
  const [prices, setPrices] = useState<PriceBar[]>([]);
  const [regData, setRegData] = useState<{ signals: RegulatorySignal[]; events: RegulatoryEvent[] } | null>(null);
  const [conv, setConv] = useState<ConvergenceSignal | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.asset(symbol), api.prices(symbol),
      api.regulatorySymbol(symbol).catch(() => null),
      api.convergenceSymbol(symbol).catch(() => null),
    ]).then(([d, p, r, c]) => {
      setDetail(d); setPrices(p); setRegData(r); setConv(c); setLoading(false);
    }).catch(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div className="flex items-center justify-center h-[60vh]"><div className="text-emerald-600 animate-pulse glow-green">LOADING {symbol}...</div></div>;
  if (!detail?.signal) return <div className="panel p-8 text-center"><p className="text-gray-500">No data available for {symbol}</p></div>;

  const s = detail.signal;
  const t = detail.technical;
  const f = detail.fundamental;
  const currentPrice = prices.length > 0 ? prices[0].close : s.entry_price;
  const prevPrice = prices.length > 1 ? prices[1].close : currentPrice;
  const dailyChange = ((currentPrice - prevPrice) / prevPrice) * 100;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-4">
            <h1 className="font-display text-3xl font-bold text-gray-900">{symbol}</h1>
            <SignalBadge signal={s.signal} size="lg" />
            {conv && (
              <span className={`text-[10px] font-bold tracking-wider px-2 py-1 rounded-lg ${
                conv.conviction_level === 'high' ? 'text-emerald-600 bg-emerald-600/10'
                : conv.conviction_level === 'medium' ? 'text-amber-600 bg-amber-600/10'
                : 'text-gray-500 bg-gray-400/10'
              }`}>{conv.conviction_level?.toUpperCase()} CONVICTION · {conv.module_count} MODULES</span>
            )}
          </div>
          <p className="text-[10px] text-gray-500 tracking-widest mt-1 uppercase">{s.asset_class} · {s.date}</p>
        </div>
        <div className="text-right">
          <div className="text-3xl font-display font-bold text-gray-900">${currentPrice.toFixed(2)}</div>
          <div className={`text-sm font-mono ${dailyChange >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {dailyChange >= 0 ? '+' : ''}{dailyChange.toFixed(2)}%
          </div>
        </div>
      </div>

      <AssetTradeSetup signal={s} conv={conv} currentPrice={currentPrice} />
      {conv && <AssetConvergencePanel conv={conv} />}
      <PriceChart data={prices} symbol={symbol} entry={s.entry_price} stop={s.stop_loss} target={s.target_price} />

      {/* Scores */}
      <div className="grid grid-cols-2 gap-4">
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] text-gray-500 tracking-widest uppercase">Technical Score</span>
            <span className={`text-xl font-display font-bold ${(t?.total_score || 0) > 70 ? 'text-[#059669]' : (t?.total_score || 0) > 40 ? 'text-[#d97706]' : 'text-[#e11d48]'}`}>
              {t?.total_score.toFixed(1) || '\u2014'} / 100
            </span>
          </div>
          {t && <div className="space-y-3"><ScoreBar value={t.trend_score} label="Trend" /><ScoreBar value={t.momentum_score} label="Momentum" /><ScoreBar value={t.breakout_score} label="Breakout" /><ScoreBar value={t.relative_strength_score} label="Rel. Strength" /><ScoreBar value={t.breadth_score} label="Breadth" /></div>}
        </div>
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] text-gray-500 tracking-widest uppercase">Fundamental Score</span>
            <span className={`text-xl font-display font-bold ${(f?.total_score || 50) > 70 ? 'text-[#059669]' : (f?.total_score || 50) > 40 ? 'text-[#d97706]' : 'text-[#e11d48]'}`}>
              {f?.total_score.toFixed(1) || '50.0'} / 100
            </span>
          </div>
          {f ? <div className="space-y-3"><ScoreBar value={f.valuation_score} label="Valuation" /><ScoreBar value={f.growth_score} label="Growth" /><ScoreBar value={f.profitability_score} label="Profitability" /><ScoreBar value={f.health_score} label="Health" /><ScoreBar value={f.quality_score} label="Quality" /></div> : <p className="text-[10px] text-gray-500">N/A for {s.asset_class}</p>}
        </div>
      </div>

      {Object.keys(detail.fundamentals).length > 0 && (
        <div className="panel p-5">
          <div className="text-[10px] text-gray-500 tracking-widest uppercase mb-4">Key Metrics</div>
          <div className="grid grid-cols-4 gap-4">
            {Object.entries(METRIC_LABELS).map(([key, { label, format }]) => {
              const val = detail.fundamentals[key];
              if (val === undefined) return null;
              return <div key={key}><div className="text-[9px] text-gray-500">{label}</div><div className="text-sm font-mono text-gray-700">{format(val)}</div></div>;
            })}
          </div>
        </div>
      )}

      {regData && <AssetRegulatoryPanel signals={regData.signals} events={regData.events} />}
    </div>
  );
}
