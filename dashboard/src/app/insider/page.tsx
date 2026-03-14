'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type InsiderSignal,
  type InsiderTransaction,
  type InsiderDetail,
} from '@/lib/api';

type Tab = 'unusual' | 'feed' | 'convergence';

export default function InsiderPage() {
  const [signals, setSignals] = useState<InsiderSignal[]>([]);
  const [clusterBuys, setClusterBuys] = useState<InsiderSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('unusual');

  // Transaction detail state
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [detail, setDetail] = useState<InsiderDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      api.insiderSignals(0, 30).catch(() => []),
      api.insiderClusterBuys(30).catch(() => []),
    ]).then(([sigs, clusters]) => {
      setSignals(sigs);
      setClusterBuys(clusters);
      setLoading(false);
    });
  }, []);

  const loadDetail = async (symbol: string) => {
    if (expandedSymbol === symbol) {
      setExpandedSymbol(null);
      return;
    }
    setDetailLoading(true);
    setExpandedSymbol(symbol);
    try {
      const data = await api.insiderTransactions(symbol);
      setDetail(data);
    } catch {
      setDetail(null);
    }
    setDetailLoading(false);
  };

  const formatDollar = (v: number) => {
    if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
    return `$${v.toFixed(0)}`;
  };

  // Split signals for convergence tab
  const highConviction = signals.filter(
    (s) => s.insider_score >= 50 && s.smart_money_score && s.smart_money_score >= 50,
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          SCANNING SEC FORM 4 FILINGS...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          INSIDER TRADING INTELLIGENCE
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          SEC FORM 4 MONITOR — CLUSTER BUYS, UNUSUAL VOLUME, C-SUITE PURCHASES
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        <div
          onClick={() => setActiveTab('unusual')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'unusual' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-green">
            {signals.filter((s) => s.insider_score >= 50).length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            HIGH INSIDER SCORE
          </div>
        </div>
        <div
          onClick={() => setActiveTab('unusual')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'unusual' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-red">
            {clusterBuys.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            CLUSTER BUYS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('feed')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'feed' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-amber">
            {signals.filter((s) => s.unusual_volume_flag).length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            UNUSUAL VOLUME
          </div>
        </div>
        <div
          onClick={() => setActiveTab('convergence')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'convergence' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-cyan">
            {highConviction.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            INSIDER + SMART MONEY
          </div>
        </div>
      </div>

      {/* Unusual Activity Tab */}
      {activeTab === 'unusual' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              UNUSUAL INSIDER ACTIVITY
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Ranked by insider score — cluster buys, large C-suite purchases, unusual volume
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-center py-3 px-2 font-normal">Flags</th>
                  <th className="text-right py-3 px-2 font-normal">Buy $30d</th>
                  <th className="text-right py-3 px-2 font-normal">Sell $30d</th>
                  <th className="text-right py-3 px-2 font-normal">Net</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {signals.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-8 text-terminal-dim">
                      No insider signals detected. Run the pipeline to scan Form 4 filings.
                    </td>
                  </tr>
                ) : (
                  signals.map((s, i) => {
                    const net = s.total_buy_value_30d - s.total_sell_value_30d;
                    return (
                      <>
                        <tr
                          key={`${s.symbol}-${s.date}-${i}`}
                          className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                          onClick={() => loadDetail(s.symbol)}
                        >
                          <td className="py-2.5 px-4 font-mono font-bold text-terminal-green">
                            {s.symbol}
                          </td>
                          <td className="py-2.5 px-2 text-right">
                            <span
                              className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                              style={{
                                backgroundColor:
                                  s.insider_score >= 70
                                    ? 'rgba(0,255,65,0.15)'
                                    : s.insider_score >= 50
                                    ? 'rgba(255,184,0,0.15)'
                                    : 'rgba(255,255,255,0.05)',
                                color:
                                  s.insider_score >= 70
                                    ? '#00FF41'
                                    : s.insider_score >= 50
                                    ? '#FFB800'
                                    : '#888',
                              }}
                            >
                              {s.insider_score.toFixed(0)}
                            </span>
                          </td>
                          <td className="py-2.5 px-2 text-center space-x-1">
                            {s.cluster_buy === 1 && (
                              <span className="inline-block px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-terminal-red/20 text-terminal-red">
                                CLUSTER ({s.cluster_count})
                              </span>
                            )}
                            {s.unusual_volume_flag === 1 && (
                              <span className="inline-block px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-terminal-amber/20 text-terminal-amber">
                                UNUSUAL VOL
                              </span>
                            )}
                            {s.large_buys_count > 0 && (
                              <span className="inline-block px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-terminal-cyan/20 text-terminal-cyan">
                                C-SUITE
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-2 text-right font-mono text-terminal-green">
                            {formatDollar(s.total_buy_value_30d)}
                          </td>
                          <td className="py-2.5 px-2 text-right font-mono text-terminal-red">
                            {formatDollar(s.total_sell_value_30d)}
                          </td>
                          <td
                            className={`py-2.5 px-2 text-right font-mono ${
                              net >= 0 ? 'text-terminal-green' : 'text-terminal-red'
                            }`}
                          >
                            {net >= 0 ? '+' : ''}
                            {formatDollar(Math.abs(net))}
                          </td>
                          <td className="py-2.5 px-4 text-terminal-dim max-w-[320px] truncate">
                            {s.narrative}
                          </td>
                        </tr>
                        {/* Inline transaction detail */}
                        {expandedSymbol === s.symbol && (
                          <tr key={`detail-${s.symbol}`}>
                            <td colSpan={7} className="bg-terminal-panel/50 p-0">
                              <div className="px-6 py-4">
                                {detailLoading ? (
                                  <div className="text-terminal-dim animate-pulse text-center py-4">
                                    Loading transactions...
                                  </div>
                                ) : detail?.transactions && detail.transactions.length > 0 ? (
                                  <table className="w-full text-[10px]">
                                    <thead>
                                      <tr className="text-terminal-dim tracking-widest uppercase">
                                        <th className="text-left py-2 font-normal">Date</th>
                                        <th className="text-left py-2 font-normal">Insider</th>
                                        <th className="text-left py-2 font-normal">Title</th>
                                        <th className="text-center py-2 font-normal">Type</th>
                                        <th className="text-right py-2 font-normal">Shares</th>
                                        <th className="text-right py-2 font-normal">Price</th>
                                        <th className="text-right py-2 font-normal">Value</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {detail.transactions.slice(0, 20).map((tx, j) => (
                                        <tr
                                          key={`tx-${j}`}
                                          className="border-t border-terminal-border/30"
                                        >
                                          <td className="py-1.5 font-mono text-terminal-dim">
                                            {tx.date}
                                          </td>
                                          <td className="py-1.5 text-terminal-text">
                                            {tx.insider_name || '—'}
                                          </td>
                                          <td className="py-1.5 text-terminal-dim text-[9px] tracking-wider uppercase">
                                            {tx.insider_title || '—'}
                                          </td>
                                          <td className="py-1.5 text-center">
                                            <span
                                              className={`px-1.5 py-0.5 rounded-sm text-[9px] font-bold ${
                                                tx.transaction_type === 'BUY'
                                                  ? 'bg-terminal-green/15 text-terminal-green'
                                                  : tx.transaction_type === 'SELL'
                                                  ? 'bg-terminal-red/15 text-terminal-red'
                                                  : 'bg-white/5 text-terminal-dim'
                                              }`}
                                            >
                                              {tx.transaction_type}
                                            </span>
                                          </td>
                                          <td className="py-1.5 text-right font-mono text-terminal-text">
                                            {tx.shares?.toLocaleString() || '—'}
                                          </td>
                                          <td className="py-1.5 text-right font-mono text-terminal-dim">
                                            {tx.price ? `$${tx.price.toFixed(2)}` : '—'}
                                          </td>
                                          <td className="py-1.5 text-right font-mono text-terminal-text">
                                            {tx.value ? formatDollar(tx.value) : '—'}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                ) : (
                                  <div className="text-terminal-dim text-center py-4">
                                    No transaction details available.
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Transaction Feed Tab */}
      {activeTab === 'feed' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              CLUSTER BUY SIGNALS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              3+ distinct insiders buying within 14 days — strongest academic predictor of returns
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-right py-3 px-2 font-normal">Insiders</th>
                  <th className="text-right py-3 px-2 font-normal">Buy $30d</th>
                  <th className="text-right py-3 px-2 font-normal">Smart $</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {clusterBuys.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-terminal-dim">
                      No active cluster buy signals detected.
                    </td>
                  </tr>
                ) : (
                  clusterBuys.map((s, i) => (
                    <tr
                      key={`cluster-${s.symbol}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => (window.location.href = `/asset/${s.symbol}`)}
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-red">
                        {s.symbol}
                        <span className="ml-2 px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-terminal-red/20 text-terminal-red">
                          CLUSTER
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold bg-terminal-green/15 text-terminal-green">
                          {s.insider_score.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-bright">
                        {s.cluster_count || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-green">
                        {formatDollar(s.total_buy_value_30d)}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-cyan">
                        {s.smart_money_score ? s.smart_money_score.toFixed(0) : '—'}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[400px] truncate">
                        {s.narrative}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Smart Money + Insider Convergence Tab */}
      {activeTab === 'convergence' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              INSIDER + SMART MONEY CONVERGENCE
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Where Form 4 insider buying AND 13F institutional flows agree — highest conviction
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-right py-3 px-2 font-normal">Insider</th>
                  <th className="text-right py-3 px-2 font-normal">Smart $</th>
                  <th className="text-center py-3 px-2 font-normal">Flags</th>
                  <th className="text-right py-3 px-2 font-normal">Buy $30d</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {highConviction.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-terminal-dim">
                      No insider + smart money convergence signals. Run the full pipeline to detect.
                    </td>
                  </tr>
                ) : (
                  highConviction.map((s, i) => (
                    <tr
                      key={`conv-${s.symbol}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => (window.location.href = `/asset/${s.symbol}`)}
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-cyan">
                        {s.symbol}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold bg-terminal-green/15 text-terminal-green">
                          {s.insider_score.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold bg-terminal-cyan/15 text-terminal-cyan">
                          {s.smart_money_score?.toFixed(0) || '—'}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-center space-x-1">
                        {s.cluster_buy === 1 && (
                          <span className="inline-block px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-terminal-red/20 text-terminal-red">
                            CLUSTER
                          </span>
                        )}
                        {s.unusual_volume_flag === 1 && (
                          <span className="inline-block px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-terminal-amber/20 text-terminal-amber">
                            VOL
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-green">
                        {formatDollar(s.total_buy_value_30d)}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[400px] truncate">
                        {s.narrative}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
