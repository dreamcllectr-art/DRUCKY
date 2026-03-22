'use client';

import { useEffect, useState, useCallback } from 'react';
import { useStockPanel } from '@/contexts/StockPanelContext';
import { fmtM, fmt, GATE_COLORS } from '@/lib/utils';
import PriceChart from '@/components/PriceChart';
import { Tooltip, InfoTip } from '@/components/shared/Tooltip';
import { CONVERGENCE_DEFS, CONVICTION_DEFS } from '@/lib/definitions';

interface Price { date: string; open: number; high: number; low: number; close: number; volume: number; }
interface Signal {
  signal?: string; composite_score?: number;
  entry_price?: number; stop_loss?: number; target_price?: number; rr_ratio?: number;
}
interface Convergence {
  convergence_score?: number; module_count?: number; main_signal_score?: number;
  smartmoney_score?: number; worldview_score?: number; estimate_momentum_score?: number;
  conviction_level?: string; narrative?: string;
}
interface Insider {
  insider_score?: number; cluster_buy?: number; cluster_count?: number;
  total_buy_value_30d?: number; total_sell_value_30d?: number;
  large_buys_count?: number; top_buyer?: string; narrative?: string;
}
interface InsiderTxn {
  transaction_type?: string; transaction_date?: string;
  shares?: number; price?: number; value?: number;
  insider_name?: string; insider_title?: string;
}
interface Catalyst { catalyst_type?: string; catalyst_detail?: string; catalyst_strength?: number; }
interface StockInfo { name?: string; sector?: string; }
interface Gate { gate_10?: number; last_gate_passed?: number; }

interface MASignal { ma_score?: number; deal_stage?: string; expected_premium_pct?: number; acquirer_name?: string; narrative?: string; best_headline?: string; date?: string; }
interface MARumor { rumor_headline?: string; credibility_score?: number; date?: string; rumor_source?: string; }

interface StockData {
  symbol: string;
  prices: Price[];
  signal: Signal | null;
  convergence: Convergence | null;
  fundamentals: Record<string, string | number>;
  info: StockInfo;
  catalyst: Catalyst | null;
  insider: Insider | null;
  insider_transactions: InsiderTxn[];
  gate: Gate | null;
  ma_signal: MASignal | null;
  ma_rumors: MARumor[];
}

// ─── Fundamentals formatting ──────────────────────────────────────────────────

type FundType = 'large$' | 'price$' | 'pct' | 'ratio_x' | 'plain' | 'shares' | 'shares_large';

interface FundDef { label: string; type: FundType; }

const FUND_MAP: Record<string, FundDef> = {
  // Market size
  marketcap:                    { label: 'Market Cap',       type: 'large$' },
  market_cap:                   { label: 'Market Cap',       type: 'large$' },
  enterprisevalue:              { label: 'EV',               type: 'large$' },
  enterprise_value:             { label: 'EV',               type: 'large$' },
  freecashflow:                 { label: 'Free Cash Flow',   type: 'large$' },
  free_cash_flow:               { label: 'Free Cash Flow',   type: 'large$' },
  insider_net_value_90d:        { label: 'Net Insider Value 90d', type: 'large$' },
  // Price targets (analyst consensus)
  analyst_target_consensus:     { label: 'Price Target',     type: 'price$' },
  analysttargetconsensus:       { label: 'Price Target',     type: 'price$' },
  analyst_target_high:          { label: 'Target High',      type: 'price$' },
  analysttargethigh:            { label: 'Target High',      type: 'price$' },
  analyst_target_low:           { label: 'Target Low',       type: 'price$' },
  analysttargetlow:             { label: 'Target Low',       type: 'price$' },
  // Margin / yield percentages (stored as 0.48 = 48%)
  grossmargins:                 { label: 'Gross Margin',     type: 'pct' },
  gross_margin:                 { label: 'Gross Margin',     type: 'pct' },
  operatingmargins:             { label: 'Op Margin',        type: 'pct' },
  operating_margin:             { label: 'Op Margin',        type: 'pct' },
  net_margin:                   { label: 'Net Margin',       type: 'pct' },
  netmargin:                    { label: 'Net Margin',       type: 'pct' },
  fcf_yield:                    { label: 'FCF Yield',        type: 'pct' },
  dividend_yield:               { label: 'Div Yield',        type: 'pct' },
  dividendyield:                { label: 'Div Yield',        type: 'pct' },
  div_yield:                    { label: 'Div Yield',        type: 'pct' },
  earningsgrowth:               { label: 'EPS Growth',       type: 'pct' },
  earnings_growth:              { label: 'EPS Growth',       type: 'pct' },
  revenuegrowth:                { label: 'Rev Growth',       type: 'pct' },
  revenue_growth:               { label: 'Rev Growth',       type: 'pct' },
  heldpercentinsiders:          { label: 'Insider Own',      type: 'pct' },
  insider_pct:                  { label: 'Insider Own',      type: 'pct' },
  // Analyst pct (stored as 52.60 = 52.6%)
  analyst_buy_pct:              { label: 'Analyst Buy %',    type: 'pct' },
  analystbuypct:                { label: 'Analyst Buy %',    type: 'pct' },
  finnhub_analyst_bullish_pct:  { label: 'Analyst Buy %',    type: 'pct' },
  analyst_hold_pct:             { label: 'Analyst Hold %',   type: 'pct' },
  analystholdpct:               { label: 'Analyst Hold %',   type: 'pct' },
  analyst_sell_pct:             { label: 'Analyst Sell %',   type: 'pct' },
  analystsellpct:               { label: 'Analyst Sell %',   type: 'pct' },
  finnhub_analyst_bearish_pct:  { label: 'Analyst Sell %',   type: 'pct' },
  // Debt/Equity — stored as percentage (143 = 143%)
  debttoequity:                 { label: 'Debt/Equity',      type: 'pct' },
  debt_equity:                  { label: 'Debt/Equity',      type: 'pct' },
  debt_to_equity:               { label: 'Debt/Equity',      type: 'pct' },
  // Ratio multiples
  pe_ratio:                     { label: 'P/E',              type: 'ratio_x' },
  peratio:                      { label: 'P/E',              type: 'ratio_x' },
  forwardpe:                    { label: 'Fwd P/E',          type: 'ratio_x' },
  forward_pe:                   { label: 'Fwd P/E',          type: 'ratio_x' },
  pb_ratio:                     { label: 'P/B',              type: 'ratio_x' },
  pbratio:                      { label: 'P/B',              type: 'ratio_x' },
  pricetobook:                  { label: 'P/B',              type: 'ratio_x' },
  price_to_book:                { label: 'P/B',              type: 'ratio_x' },
  enterprisetoebitda:           { label: 'EV/EBITDA',        type: 'ratio_x' },
  enterprise_to_ebitda:         { label: 'EV/EBITDA',        type: 'ratio_x' },
  ev_ebitda:                    { label: 'EV/EBITDA',        type: 'ratio_x' },
  currentratio:                 { label: 'Current Ratio',    type: 'ratio_x' },
  current_ratio:                { label: 'Current Ratio',    type: 'ratio_x' },
  // Share counts
  sharesoutstanding:            { label: 'Shares Outstanding',  type: 'shares_large' },
  shares_outstanding:           { label: 'Shares Outstanding',  type: 'shares_large' },
  insider_net_shares_90d:       { label: 'Net Insider Shares 90d', type: 'shares' },
  finnhub_analyst_strong_buy:   { label: 'Strong Buys',      type: 'plain' },
  finnhub_analyst_total:        { label: 'Analyst Count',    type: 'plain' },
  analyst_rating_count:         { label: 'Analyst Count',    type: 'plain' },
  analystratingcount:           { label: 'Analyst Count',    type: 'plain' },
};

function fmtFundValue(def: FundDef, v: string | number): string {
  if (typeof v === 'string') return v;
  if (v == null || isNaN(v as number)) return '—';
  const n = v as number;

  switch (def.type) {
    case 'large$': {
      const abs = Math.abs(n);
      if (abs >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
      if (abs >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
      if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
      return `$${n.toFixed(0)}`;
    }
    case 'price$':
      return `$${n.toFixed(2)}`;
    case 'pct': {
      // Detect if stored as decimal (0.48) or already percentage (48.0)
      const pct = Math.abs(n) <= 1.5 ? n * 100 : n;
      return `${pct.toFixed(1)}%`;
    }
    case 'ratio_x':
      return `${n.toFixed(2)}x`;
    case 'shares_large': {
      const abs = Math.abs(n);
      if (abs >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
      if (abs >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
      if (abs >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
      return n.toFixed(0);
    }
    case 'shares':
      return Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 });
    case 'plain':
    default:
      if (Number.isInteger(n)) return n.toFixed(0);
      if (Math.abs(n) > 10) return n.toFixed(1);
      return n.toFixed(2);
  }
}

function formatFundamentals(raw: Record<string, string | number>): { label: string; value: string }[] {
  const seen = new Map<string, { label: string; value: string }>();

  for (const [rawKey, v] of Object.entries(raw)) {
    const k = rawKey.toLowerCase();
    const def = FUND_MAP[k];
    const label = def?.label ?? rawKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    const canonKey = label.toLowerCase();

    if (!seen.has(canonKey)) {
      seen.set(canonKey, {
        label,
        value: def ? fmtFundValue(def, v) : (typeof v === 'number' ? v.toFixed(2) : String(v)),
      });
    }
  }

  return Array.from(seen.values());
}

// ─── Score pill ───────────────────────────────────────────────────────────────

function ScorePill({ score }: { score: number | null | undefined }) {
  if (score == null) return null;
  const cls = score >= 70 ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : score >= 50 ? 'bg-amber-50 text-amber-700 border-amber-200'
    : 'bg-gray-50 text-gray-500 border-gray-200';
  return <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${cls}`}>{score.toFixed(0)}</span>;
}

export default function StockPanel() {
  const { symbol, close } = useStockPanel();
  const [data, setData] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState(false);
  const [tab, setTab] = useState<'chart' | 'fundamentals' | 'insider' | 'ma'>('chart');

  useEffect(() => {
    if (!symbol) { setData(null); setFetchError(false); return; }
    setLoading(true);
    setFetchError(false);
    setTab('chart');
    fetch(`/api/v2/stock/${symbol}`)
      .then(r => { if (!r.ok) throw new Error('fetch'); return r.json(); })
      .then(d => { setData(d); })
      .catch(() => setFetchError(true))
      .finally(() => setLoading(false));
  }, [symbol]);

  // Close on Escape key
  const handleKey = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') close();
  }, [close]);

  useEffect(() => {
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  if (!symbol) return null;

  const sig = data?.signal;
  const conv = data?.convergence;
  const info = data?.info;
  const gate = data?.gate;
  const signalColor = sig?.signal?.includes('BUY') ? 'text-emerald-600'
    : sig?.signal?.includes('SELL') ? 'text-rose-600' : 'text-gray-600';

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/20 z-40 backdrop-blur-[1px]" onClick={close} />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-screen w-[580px] bg-white border-l border-gray-200 z-50 flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold text-gray-900 tracking-tight">{symbol}</span>
                {gate?.gate_10 === 1 && (
                  <span className="text-[10px] bg-emerald-500 text-white px-1.5 py-0.5 rounded font-bold tracking-widest">FAT PITCH</span>
                )}
                {gate && gate.gate_10 !== 1 && gate.last_gate_passed != null && (
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${GATE_COLORS[gate.last_gate_passed] ?? 'bg-gray-100 text-gray-600'}`}>
                    G{gate.last_gate_passed}
                  </span>
                )}
              </div>
              <div className="text-[11px] text-gray-500 truncate max-w-[300px]">
                {info?.name}{info?.sector ? ` · ${info.sector}` : ''}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {sig && (
              <div className="text-right">
                <div className={`text-sm font-bold ${signalColor}`}>{sig.signal}</div>
                <ScorePill score={sig.composite_score} />
              </div>
            )}
            <button
              onClick={close}
              className="w-7 h-7 flex items-center justify-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
              title="Close (Esc)"
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round">
                <path d="M1 1l10 10M11 1L1 11"/>
              </svg>
            </button>
          </div>
        </div>

        {/* Trade setup strip */}
        {sig && (sig.entry_price || sig.stop_loss || sig.target_price) && (
          <div className="flex items-center gap-0 border-b border-gray-100 shrink-0">
            {[
              { label: 'ENTRY',  value: sig.entry_price  ? `$${fmt(sig.entry_price, 2)}`  : '—', color: 'text-slate-700' },
              { label: 'STOP',   value: sig.stop_loss    ? `$${fmt(sig.stop_loss, 2)}`    : '—', color: 'text-rose-600' },
              { label: 'TARGET', value: sig.target_price ? `$${fmt(sig.target_price, 2)}` : '—', color: 'text-emerald-600' },
              { label: 'R:R',    value: sig.rr_ratio     ? `${fmt(sig.rr_ratio, 1)}x`     : '—', color: 'text-gray-700' },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex-1 px-4 py-2.5 border-r border-gray-100 last:border-r-0">
                <div className="text-[10px] text-gray-400 tracking-wider uppercase">{label}</div>
                <div className={`text-sm font-mono font-bold ${color}`}>{value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Conviction narrative */}
        {conv?.narrative && (
          <div className="px-5 py-2.5 bg-gray-50 border-b border-gray-100 shrink-0">
            <div className="text-[10px] text-gray-500 leading-relaxed">{conv.narrative}</div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-gray-200 shrink-0">
          {(['chart', 'fundamentals', 'insider', 'ma'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-5 py-2.5 text-[10px] uppercase tracking-widest font-semibold transition-colors ${
                tab === t
                  ? 'text-emerald-600 border-b-2 border-emerald-600 bg-emerald-50/50'
                  : 'text-gray-400 hover:text-gray-700'
              }`}
            >
              {t === 'chart' ? 'Price Chart' : t === 'fundamentals' ? 'Fundamentals' : t === 'insider' ? 'Insider' : (
                <span className="flex items-center gap-1">
                  M&amp;A
                  {data?.ma_signal && <span className="w-1.5 h-1.5 rounded-full bg-purple-500" />}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-8 text-center text-gray-400 text-[11px] animate-pulse">Loading {symbol}...</div>
          ) : fetchError ? (
            <div className="p-8 text-center">
              <div className="text-[11px] font-semibold text-rose-600 mb-1">Could not load data for {symbol}</div>
              <div className="text-[10px] text-gray-400">Check that the backend is running.</div>
            </div>
          ) : !data ? (
            <div className="p-8 text-center text-gray-400 text-[11px]">No data found for {symbol}</div>
          ) : (
            <>
              {tab === 'chart' && (
                <div className="p-4">
                  {data.prices.length > 0 ? (
                    <PriceChart
                      data={data.prices}
                      symbol={symbol}
                      entry={sig?.entry_price ?? undefined}
                      stop={sig?.stop_loss ?? undefined}
                      target={sig?.target_price ?? undefined}
                    />
                  ) : (
                    <div className="text-center py-12 text-gray-400 text-[11px]">No price data available</div>
                  )}

                  {conv && (
                    <div className="mt-4 bg-gray-50 rounded-xl p-4 border border-gray-200">
                      <div className="text-[10px] font-semibold text-gray-400 tracking-widest uppercase mb-3">Signal Intelligence</div>
                      <div className="grid grid-cols-3 gap-2">
                        {([
                          { label: 'Convergence',  score: conv.convergence_score,  tip: CONVERGENCE_DEFS.convergence_score },
                          { label: 'Modules',      score: conv.module_count != null ? conv.module_count * 10 : null, raw: conv.module_count, tip: CONVERGENCE_DEFS.module_count },
                          { label: 'Main Signal',  score: conv.main_signal_score,  tip: CONVERGENCE_DEFS.composite_score },
                          { label: 'Smart Money',  score: conv.smartmoney_score },
                          { label: 'Worldview',    score: conv.worldview_score },
                          { label: 'Momentum',     score: conv.estimate_momentum_score },
                        ] as { label: string; score: number | null | undefined; raw?: number | null; tip?: string }[])
                          .filter(x => x.score != null)
                          .map(({ label, score, raw, tip }) => (
                            <div key={label} className="bg-white rounded-lg p-2.5 border border-gray-200">
                              <div className="text-[10px] text-gray-400 uppercase tracking-wide">
                                {tip ? <>{label} <InfoTip text={tip} /></> : label}
                              </div>
                              <div className="text-sm font-mono font-bold text-gray-800">{raw ?? score?.toFixed(0)}</div>
                            </div>
                          ))}
                      </div>
                    </div>
                  )}

                  {data.catalyst?.catalyst_type && (
                    <div className="mt-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-amber-700">Catalyst</span>
                        <span className="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">{data.catalyst.catalyst_type}</span>
                        <ScorePill score={data.catalyst.catalyst_strength} />
                      </div>
                      <div className="text-[11px] text-amber-800">{data.catalyst.catalyst_detail}</div>
                    </div>
                  )}
                </div>
              )}

              {tab === 'fundamentals' && (
                <div className="p-5">
                  {Object.keys(data.fundamentals).length === 0 ? (
                    <div className="text-center py-12 text-gray-400 text-[11px]">No fundamental data available</div>
                  ) : (
                    <div className="grid grid-cols-3 gap-2">
                      {formatFundamentals(data.fundamentals).map(({ label, value }) => (
                        <div key={label} className="bg-gray-50 border border-gray-200 rounded-lg p-2.5">
                          <div className="text-[10px] text-gray-400 uppercase tracking-wide truncate">{label}</div>
                          <div className="text-xs font-mono font-semibold text-gray-800">{value}</div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {tab === 'insider' && (
                <div className="p-5 space-y-4">
                  {data.insider && (
                    <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
                      <div className="flex items-center justify-between mb-3">
                        <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold">Insider Summary</div>
                        <ScorePill score={data.insider.insider_score} />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        {[
                          { label: 'Cluster Buy',    value: data.insider.cluster_buy ? 'YES' : 'NO',              color: data.insider.cluster_buy ? 'text-emerald-600 font-bold' : 'text-gray-600' },
                          { label: 'Cluster Size',   value: `${data.insider.cluster_count || 0} insiders` },
                          { label: 'Buy Value (30d)', value: fmtM(data.insider.total_buy_value_30d),              color: 'text-emerald-600 font-semibold' },
                          { label: 'Sell Value (30d)', value: fmtM(data.insider.total_sell_value_30d),            color: 'text-rose-600' },
                          { label: 'Large Buys',     value: `${data.insider.large_buys_count || 0} transactions` },
                          { label: 'Top Buyer',      value: data.insider.top_buyer || '—' },
                        ].map(({ label, value, color }) => (
                          <div key={label} className="bg-white rounded-lg p-2.5 border border-gray-200">
                            <div className="text-[10px] text-gray-400 uppercase tracking-wide">{label}</div>
                            <div className={`text-xs font-mono ${color || 'text-gray-800'}`}>{value}</div>
                          </div>
                        ))}
                      </div>
                      {data.insider.narrative && (
                        <div className="mt-3 text-[10px] text-gray-600 leading-relaxed">{data.insider.narrative}</div>
                      )}
                    </div>
                  )}

                  {data.insider_transactions.length > 0 ? (
                    <div>
                      <div className="text-[10px] font-semibold text-gray-400 tracking-widest uppercase mb-2">Recent Transactions</div>
                      <div className="space-y-2">
                        {(() => {
                          // Group same-date non-market transactions (vesting events) into a single collapsed row
                          const vestingByDate: Record<string, typeof data.insider_transactions> = {};
                          const marketTxns: typeof data.insider_transactions = [];
                          for (const txn of data.insider_transactions) {
                            const tt = (txn.transaction_type || '').toUpperCase();
                            const isMarket = tt === 'BUY' || tt === 'P' || tt === 'SELL' || tt === 'S';
                            if (isMarket) { marketTxns.push(txn); }
                            else {
                              const key = txn.transaction_date || 'unknown';
                              if (!vestingByDate[key]) vestingByDate[key] = [];
                              vestingByDate[key].push(txn);
                            }
                          }
                          const vestingRows = Object.entries(vestingByDate).map(([date, txns]) => {
                            const totalValue = txns.reduce((s, t) => s + (t.value || 0), 0);
                            const totalShares = txns.reduce((s, t) => s + (t.shares || 0), 0);
                            return (
                              <div key={`vest-${date}`} className="flex items-center gap-3 p-3 rounded-lg border bg-slate-50 border-slate-200">
                                <div className="w-12 text-center text-[10px] font-bold uppercase py-1 rounded bg-slate-300 text-slate-700">VEST</div>
                                <div className="flex-1 min-w-0">
                                  <div className="text-[11px] font-semibold text-slate-600">
                                    {fmtM(totalValue)}
                                    <span className="text-[10px] text-gray-500 ml-1">({totalShares.toLocaleString()} shares · {txns.length} insiders)</span>
                                  </div>
                                  <div className="text-[10px] text-gray-400">RSU vesting / tax withholding — not a market sale</div>
                                </div>
                                <div className="text-[10px] text-gray-400 shrink-0">{date}</div>
                              </div>
                            );
                          });
                          const marketRows = marketTxns.map((txn, i) => {
                            const tt = (txn.transaction_type || '').toUpperCase();
                            const isBuy = tt === 'BUY' || tt === 'P';
                            return (
                              <div key={`mkt-${i}`} className={`flex items-center gap-3 p-3 rounded-lg border ${isBuy ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'}`}>
                                <div className={`w-12 text-center text-[10px] font-bold uppercase py-1 rounded ${isBuy ? 'bg-emerald-500 text-white' : 'bg-rose-500 text-white'}`}>
                                  {isBuy ? 'BUY' : 'SELL'}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <div className={`text-[11px] font-semibold ${isBuy ? 'text-emerald-800' : 'text-rose-800'}`}>
                                    {txn.value ? fmtM(txn.value) : '—'}
                                    {txn.shares != null && (
                                      <span className="text-[10px] text-gray-500 ml-1">({txn.shares.toLocaleString()} shares)</span>
                                    )}
                                  </div>
                                  <div className="text-[10px] text-gray-600 truncate">
                                    {txn.insider_name || 'Unknown'}{txn.insider_title ? ` · ${txn.insider_title}` : ''}
                                  </div>
                                </div>
                                <div className="text-[10px] text-gray-400 shrink-0">{txn.transaction_date}</div>
                              </div>
                            );
                          });
                          return [...marketRows, ...vestingRows];
                        })()}
                      </div>
                    </div>
                  ) : (
                    !data.insider && (
                      <div className="text-center py-12 text-gray-400 text-[11px]">No insider activity data available</div>
                    )
                  )}
                </div>
              )}

              {tab === 'ma' && (
                <div className="p-5 space-y-4">
                  {data.ma_signal ? (
                    <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
                      <div className="flex items-center gap-2 mb-3">
                        <span className="text-[10px] text-purple-600 tracking-widest uppercase font-bold">M&A Signal</span>
                        <span className="text-sm font-mono font-bold text-purple-700">{data.ma_signal.ma_score?.toFixed(0)}</span>
                        {data.ma_signal.deal_stage && (
                          <span className={`text-[7px] font-bold px-1.5 py-0.5 rounded uppercase ${
                            data.ma_signal.deal_stage === 'definitive' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
                          }`}>{data.ma_signal.deal_stage}</span>
                        )}
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        {[
                          { label: 'Expected Premium', value: data.ma_signal.expected_premium_pct != null ? `+${data.ma_signal.expected_premium_pct.toFixed(0)}%` : '—', color: 'text-blue-600 font-bold' },
                          { label: 'Acquirer',         value: data.ma_signal.acquirer_name || '—' },
                          { label: 'Deal Stage',       value: data.ma_signal.deal_stage || '—' },
                          { label: 'Date',             value: data.ma_signal.date || '—', color: 'text-gray-500' },
                        ].map(({ label, value, color }) => (
                          <div key={label} className="bg-white rounded-lg p-2.5 border border-purple-100">
                            <div className="text-[10px] text-gray-400 uppercase tracking-wide">{label}</div>
                            <div className={`text-xs font-mono ${color || 'text-gray-800'}`}>{value}</div>
                          </div>
                        ))}
                      </div>
                      {(data.ma_signal.narrative || data.ma_signal.best_headline) && (
                        <div className="mt-3 text-[10px] text-purple-800 leading-relaxed">
                          {data.ma_signal.narrative || data.ma_signal.best_headline}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-gray-400 text-[11px]">No M&A signals for this stock</div>
                  )}

                  {(data.ma_rumors ?? []).length > 0 && (
                    <div>
                      <div className="text-[10px] text-gray-400 tracking-widest uppercase mb-2">Active Rumors</div>
                      <div className="space-y-2">
                        {(data.ma_rumors ?? []).map((r, i) => (
                          <div key={i} className="bg-gray-50 border border-gray-200 rounded-xl p-3">
                            <div className="flex items-center gap-2 mb-1">
                              {r.credibility_score != null && (
                                <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${r.credibility_score >= 7 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                                  {r.credibility_score}/10
                                </span>
                              )}
                              <span className="text-[10px] text-gray-400">{r.date}</span>
                              {r.rumor_source && <span className="text-[10px] text-gray-400 ml-auto">{r.rumor_source}</span>}
                            </div>
                            <div className="text-[10px] text-gray-700 leading-snug">{r.rumor_headline}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-200 flex items-center justify-between shrink-0">
          <a href={`/asset/${symbol}`} className="text-[10px] text-emerald-600 hover:underline tracking-wide">
            Full Dossier →
          </a>
          {conv?.conviction_level && (
            <Tooltip text={CONVICTION_DEFS[conv.conviction_level] ?? conv.conviction_level} position="top" width="w-72">
              <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest ${
                conv.conviction_level === 'HIGH'    ? 'bg-emerald-100 text-emerald-700'
                : conv.conviction_level === 'NOTABLE' ? 'bg-amber-100 text-amber-700'
                : 'bg-gray-100 text-gray-500'
              }`}>{conv.conviction_level}</span>
            </Tooltip>
          )}
        </div>
      </div>
    </>
  );
}
