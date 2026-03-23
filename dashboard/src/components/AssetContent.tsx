'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api, type AssetDetail, type PriceBar, type RegulatorySignal, type RegulatoryEvent, type ConvergenceSignal, type SignalHistoryRow, type ConvergenceHistoryRow } from '@/lib/api';
import PriceChart from '@/components/PriceChart';
import SignalBadge from '@/components/SignalBadge';
import ScoreBar from '@/components/ScoreBar';
import { AssetTradeSetup } from '@/components/AssetTradeSetup';
import { AssetConvergencePanel } from '@/components/AssetConvergencePanel';
import { AssetRegulatoryPanel } from '@/components/AssetRegulatoryPanel';

const METRIC_LABELS: Record<string, { label: string; format: (v: number) => string }> = {
  trailingPE: { label: 'P/E Ratio', format: v => v.toFixed(1) },
  priceToBook: { label: 'P/B Ratio', format: v => v.toFixed(2) },
  dividendYield: { label: 'Dividend Yield', format: v => v.toFixed(2) + '%' },
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
  const [signalHistory, setSignalHistory] = useState<SignalHistoryRow[]>([]);
  const [convHistory, setConvHistory] = useState<ConvergenceHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    Promise.all([
      api.asset(symbol), api.prices(symbol),
      api.regulatorySymbol(symbol).catch(() => null),
      api.convergenceSymbol(symbol).catch(() => null),
      api.assetSignalHistory(symbol).catch(() => null),
    ]).then(([d, p, r, c, hist]) => {
      setDetail(d); setPrices(p); setRegData(r); setConv(c);
      if (hist) { setSignalHistory(hist.signal_history); setConvHistory(hist.convergence_history); }
      setLoading(false);
    }).catch(e => { setError(e.message || `Failed to load ${symbol}`); setLoading(false); });
  }, [symbol, retryCount]);

  if (loading) return <div className="flex items-center justify-center h-[60vh]"><div className="text-gray-400 text-sm font-display tracking-widest animate-pulse">Compiling intelligence for {symbol}...</div></div>;
  if (error) return <div className="panel p-8 text-center"><div className="text-rose-600 text-sm font-bold mb-2">Failed to load {symbol}</div><p className="text-[11px] text-gray-500 mb-4">{error}</p><button onClick={() => setRetryCount(c => c + 1)} className="px-4 py-2 text-[10px] tracking-widest text-emerald-600 border border-emerald-600/30 rounded-lg hover:bg-emerald-600/5">RETRY</button></div>;
  if (!detail?.signal) return (
    <div className="panel p-8 text-center space-y-3">
      <div className="text-gray-900 font-display font-bold text-lg">{symbol}</div>
      <p className="text-gray-400 text-sm">Intelligence data not yet available for this symbol.</p>
      <p className="text-gray-300 text-[11px]">This asset may not be covered in the current universe, or the pipeline has not yet ingested data for it.</p>
      <a href="/discover" className="inline-block mt-2 px-4 py-2 text-[10px] tracking-widest text-emerald-600 border border-emerald-600/30 rounded-lg hover:bg-emerald-600/5">BROWSE UNIVERSE</a>
    </div>
  );

  const s = detail.signal;
  const t = detail.technical;
  const f = detail.fundamental;
  const currentPrice = prices.length > 0 ? prices[0].close : (s.entry_price ?? 0);
  const prevPrice = prices.length > 1 ? prices[1].close : currentPrice;
  const dailyChange = prevPrice ? ((currentPrice - prevPrice) / prevPrice) * 100 : 0;

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
                conv.conviction_level?.toUpperCase() === 'HIGH' ? 'text-emerald-600 bg-emerald-600/10'
                : conv.conviction_level?.toUpperCase() === 'NOTABLE' ? 'text-amber-600 bg-amber-600/10'
                : 'text-gray-500 bg-gray-400/10'
              }`}>{conv.conviction_level?.toUpperCase()} CONVICTION &middot; {conv.module_count} SOURCES</span>
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
      {conv && (
        <AssetConvergencePanel
          conv={conv}
          signalHistory={signalHistory.map(sh => {
            const ch = convHistory.find(c => c.date === sh.date);
            return { ...sh, convergence_score: ch?.convergence_score, conviction_level: ch?.conviction_level, module_count: ch?.module_count };
          })}
        />
      )}
      <PriceChart data={prices} symbol={symbol} entry={s.entry_price ?? undefined} stop={s.stop_loss ?? undefined} target={s.target_price ?? undefined} />

      {/* Scores */}
      <div className="grid grid-cols-2 gap-4">
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] text-gray-500 tracking-widest uppercase">Technical Score</span>
            <span className={`text-xl font-display font-bold ${(t?.total_score || 0) > 70 ? 'text-[#059669]' : (t?.total_score || 0) > 40 ? 'text-[#d97706]' : 'text-[#e11d48]'}`}>
              {t?.total_score.toFixed(1) || '\u2014'} / 100
            </span>
          </div>
          {t && <div className="space-y-3"><ScoreBar value={t.trend_score * 5} label="Trend" /><ScoreBar value={t.momentum_score * 5} label="Momentum" /><ScoreBar value={t.breakout_score * 5} label="Breakout" /><ScoreBar value={t.relative_strength_score * 5} label="Rel. Strength" /><ScoreBar value={t.breadth_score * 5} label="Breadth" /></div>}
        </div>
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-4">
            <span className="text-[10px] text-gray-500 tracking-widest uppercase">Fundamental Score</span>
            <span className={`text-xl font-display font-bold ${!f ? 'text-gray-400' : f.total_score > 70 ? 'text-[#059669]' : f.total_score > 40 ? 'text-[#d97706]' : 'text-[#e11d48]'}`}>
              {f?.total_score.toFixed(1) || '\u2014'} / 100
            </span>
          </div>
          {f ? <div className="space-y-3"><ScoreBar value={f.valuation_score * 5} label="Valuation" /><ScoreBar value={f.growth_score * 5} label="Growth" /><ScoreBar value={f.profitability_score * 5} label="Profitability" /><ScoreBar value={f.health_score * 5} label="Health" /><ScoreBar value={f.quality_score * 5} label="Quality" /></div> : <p className="text-[10px] text-gray-500">N/A for {s.asset_class}</p>}
        </div>
      </div>

      {Object.keys(detail.fundamentals).length > 0 && (
        <div className="panel p-5">
          <div className="text-[10px] text-gray-500 tracking-widest uppercase mb-4">Key Metrics</div>
          <div className="grid grid-cols-4 gap-4">
            {Object.entries(METRIC_LABELS).map(([key, { label, format }]) => {
              const val = detail.fundamentals[key];
              if (val === undefined) return null;
              return <div key={key}><div className="text-[10px] text-gray-500">{label}</div><div className="text-sm font-mono text-gray-700">{format(val)}</div></div>;
            })}
          </div>
        </div>
      )}

      {regData && <AssetRegulatoryPanel signals={regData.signals} events={regData.events} />}
    </div>
  );
}
