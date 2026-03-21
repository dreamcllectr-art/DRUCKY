'use client';

import { useEffect, useState } from 'react';
import { useStockPanel } from '@/contexts/StockPanelContext';
import PriceChart from '@/components/PriceChart';

interface StockData {
  symbol: string;
  prices: any[];
  signal: any;
  convergence: any;
  fundamentals: Record<string, string | number>;
  info: any;
  catalyst: any;
  insider: any;
  insider_transactions: any[];
  gate: any;
}

function fmt(v: number | null | undefined, prefix = '', suffix = '', dec = 2) {
  if (v == null || isNaN(v as number)) return '—';
  return `${prefix}${(v as number).toFixed(dec)}${suffix}`;
}

function fmtM(v: number | null | undefined) {
  if (v == null) return '—';
  const n = v as number;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function ScorePill({ score }: { score: number | null | undefined }) {
  if (score == null) return null;
  const s = score as number;
  const cls = s >= 70 ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : s >= 50 ? 'bg-amber-50 text-amber-700 border-amber-200'
    : 'bg-gray-50 text-gray-500 border-gray-200';
  return <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${cls}`}>{s.toFixed(0)}</span>;
}

export default function StockPanel() {
  const { symbol, close } = useStockPanel();
  const [data, setData] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<'chart' | 'fundamentals' | 'insider'>('chart');

  useEffect(() => {
    if (!symbol) { setData(null); return; }
    setLoading(true);
    setTab('chart');
    fetch(`/api/v2/stock/${symbol}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [symbol]);

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
      <div
        className="fixed inset-0 bg-black/20 z-40 backdrop-blur-[1px]"
        onClick={close}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-screen w-[580px] bg-white border-l border-gray-200 z-50 flex flex-col shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold text-gray-900 tracking-tight">{symbol}</span>
                {gate?.gate_10 === 1 && (
                  <span className="text-[8px] bg-emerald-500 text-white px-1.5 py-0.5 rounded font-bold tracking-widest">FAT PITCH</span>
                )}
                {gate && gate.gate_10 !== 1 && gate.last_gate_passed != null && (
                  <span className="text-[8px] bg-blue-50 text-blue-600 border border-blue-200 px-1.5 py-0.5 rounded font-bold">G{gate.last_gate_passed}</span>
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
            <button onClick={close} className="w-7 h-7 flex items-center justify-center rounded-full text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors text-sm">
              ✕
            </button>
          </div>
        </div>

        {/* Trade setup strip */}
        {sig && (sig.entry_price || sig.stop_loss || sig.target_price) && (
          <div className="flex items-center gap-0 border-b border-gray-100 shrink-0">
            {[
              { label: 'ENTRY', value: sig.entry_price ? `$${sig.entry_price.toFixed(2)}` : '—', color: 'text-blue-600' },
              { label: 'STOP', value: sig.stop_loss ? `$${sig.stop_loss.toFixed(2)}` : '—', color: 'text-rose-600' },
              { label: 'TARGET', value: sig.target_price ? `$${sig.target_price.toFixed(2)}` : '—', color: 'text-emerald-600' },
              { label: 'R:R', value: sig.rr_ratio ? `${sig.rr_ratio.toFixed(1)}x` : '—', color: 'text-gray-700' },
            ].map(({ label, value, color }) => (
              <div key={label} className="flex-1 px-4 py-2.5 border-r border-gray-100 last:border-r-0">
                <div className="text-[8px] text-gray-400 tracking-widest uppercase">{label}</div>
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
          {(['chart', 'fundamentals', 'insider'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-5 py-2.5 text-[10px] uppercase tracking-widest font-semibold transition-colors ${
                tab === t
                  ? 'text-emerald-600 border-b-2 border-emerald-600 bg-emerald-50/50'
                  : 'text-gray-400 hover:text-gray-700'
              }`}
            >
              {t === 'chart' ? 'Price Chart' : t === 'fundamentals' ? 'Fundamentals' : 'Insider Activity'}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-8 text-center text-gray-400 text-[11px] animate-pulse">Loading {symbol}...</div>
          ) : !data ? (
            <div className="p-8 text-center text-gray-400 text-[11px]">No data found for {symbol}</div>
          ) : (
            <>
              {/* Chart tab */}
              {tab === 'chart' && (
                <div className="p-4">
                  {data.prices && data.prices.length > 0 ? (
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

                  {/* Signal modules heatstrip */}
                  {conv && (
                    <div className="mt-4 bg-gray-50 rounded-xl p-4 border border-gray-200">
                      <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Signal Intelligence</div>
                      <div className="grid grid-cols-3 gap-2">
                        {[
                          { label: 'Convergence', score: conv.convergence_score },
                          { label: 'Modules', score: conv.module_count ? conv.module_count * 10 : null, raw: conv.module_count },
                          { label: 'Main Signal', score: conv.main_signal_score },
                          { label: 'Smart Money', score: conv.smartmoney_score },
                          { label: 'Worldview', score: conv.worldview_score },
                          { label: 'Momentum', score: conv.estimate_momentum_score },
                        ].filter(x => x.score != null).map(({ label, score, raw }) => (
                          <div key={label} className="bg-white rounded-lg p-2.5 border border-gray-200">
                            <div className="text-[8px] text-gray-400 uppercase tracking-wider">{label}</div>
                            <div className="text-sm font-mono font-bold text-gray-800">{raw ?? score?.toFixed(0)}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Catalyst */}
                  {data.catalyst && data.catalyst.catalyst_type && (
                    <div className="mt-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-[8px] font-bold uppercase tracking-widest text-amber-700">Catalyst</span>
                        <span className="text-[8px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">{data.catalyst.catalyst_type}</span>
                        <ScorePill score={data.catalyst.catalyst_strength} />
                      </div>
                      <div className="text-[11px] text-amber-800">{data.catalyst.catalyst_detail}</div>
                    </div>
                  )}
                </div>
              )}

              {/* Fundamentals tab */}
              {tab === 'fundamentals' && (
                <div className="p-5">
                  {Object.keys(data.fundamentals).length === 0 ? (
                    <div className="text-center py-12 text-gray-400 text-[11px]">No fundamental data available</div>
                  ) : (
                    <div className="grid grid-cols-3 gap-2">
                      {Object.entries(data.fundamentals).map(([k, v]) => (
                        <div key={k} className="bg-gray-50 border border-gray-200 rounded-lg p-2.5">
                          <div className="text-[8px] text-gray-400 uppercase tracking-wider truncate">{k.replace(/_/g, ' ')}</div>
                          <div className="text-xs font-mono font-semibold text-gray-800">
                            {typeof v === 'number' ? v.toFixed(2) : v}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Insider tab */}
              {tab === 'insider' && (
                <div className="p-5 space-y-4">
                  {/* Aggregate summary */}
                  {data.insider && (
                    <div className="bg-gray-50 border border-gray-200 rounded-xl p-4">
                      <div className="flex items-center justify-between mb-3">
                        <div className="text-[9px] text-gray-500 tracking-widest uppercase font-semibold">Insider Summary</div>
                        <ScorePill score={data.insider.insider_score} />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        {[
                          { label: 'Cluster Buy', value: data.insider.cluster_buy ? 'YES' : 'NO', color: data.insider.cluster_buy ? 'text-emerald-600 font-bold' : 'text-gray-600' },
                          { label: 'Cluster Size', value: `${data.insider.cluster_count || 0} insiders` },
                          { label: 'Buy Value (30d)', value: fmtM(data.insider.total_buy_value_30d), color: 'text-emerald-600 font-semibold' },
                          { label: 'Sell Value (30d)', value: fmtM(data.insider.total_sell_value_30d), color: 'text-rose-600' },
                          { label: 'Large Buys', value: `${data.insider.large_buys_count || 0} transactions` },
                          { label: 'Top Buyer', value: data.insider.top_buyer || '—' },
                        ].map(({ label, value, color }) => (
                          <div key={label} className="bg-white rounded-lg p-2.5 border border-gray-200">
                            <div className="text-[8px] text-gray-400 uppercase tracking-wider">{label}</div>
                            <div className={`text-[11px] font-mono ${color || 'text-gray-800'}`}>{value}</div>
                          </div>
                        ))}
                      </div>
                      {data.insider.narrative && (
                        <div className="mt-3 text-[10px] text-gray-600 leading-relaxed">{data.insider.narrative}</div>
                      )}
                    </div>
                  )}

                  {/* Individual transactions */}
                  {data.insider_transactions.length > 0 ? (
                    <div>
                      <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-2">Recent Transactions</div>
                      <div className="space-y-2">
                        {data.insider_transactions.map((txn, i) => {
                          const isBuy = txn.transaction_type?.toLowerCase().includes('buy') || txn.transaction_type === 'P';
                          return (
                            <div key={i} className={`flex items-center gap-3 p-3 rounded-lg border ${isBuy ? 'bg-emerald-50 border-emerald-200' : 'bg-rose-50 border-rose-200'}`}>
                              <div className={`w-12 text-center text-[9px] font-bold uppercase py-1 rounded ${isBuy ? 'bg-emerald-500 text-white' : 'bg-rose-500 text-white'}`}>
                                {isBuy ? 'BUY' : 'SELL'}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className={`text-[11px] font-semibold ${isBuy ? 'text-emerald-800' : 'text-rose-800'}`}>
                                  {fmtM(txn.value)}
                                  {txn.shares && <span className="text-[9px] text-gray-500 ml-1">({(txn.shares as number).toLocaleString()} shares)</span>}
                                </div>
                                <div className="text-[9px] text-gray-600 truncate">
                                  {txn.insider_name || 'Unknown'}{txn.insider_title ? ` · ${txn.insider_title}` : ''}
                                </div>
                              </div>
                              <div className="text-[9px] text-gray-400 shrink-0">{txn.transaction_date}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
                    !data.insider && <div className="text-center py-12 text-gray-400 text-[11px]">No insider activity data available</div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer links */}
        <div className="px-5 py-3 border-t border-gray-200 flex items-center justify-between shrink-0">
          <a href={`/asset/${symbol}`} className="text-[10px] text-emerald-600 hover:underline tracking-wide">
            Full Dossier →
          </a>
          <div className="text-[9px] text-gray-400">
            {conv?.conviction_level && (
              <span className={`px-2 py-0.5 rounded text-[8px] font-bold uppercase tracking-widest ${
                conv.conviction_level === 'HIGH' ? 'bg-emerald-100 text-emerald-700'
                : conv.conviction_level === 'NOTABLE' ? 'bg-amber-100 text-amber-700'
                : 'bg-gray-100 text-gray-500'
              }`}>{conv.conviction_level}</span>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
