'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type InsiderSignal,
  type InsiderDetail,
} from '@/lib/api';
import { scorePillSty } from '@/lib/styles';

export default function InsiderTab() {
  const [signals, setSignals] = useState<InsiderSignal[]>([]);
  const [clusterBuys, setClusterBuys] = useState<InsiderSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'unusual' | 'feed' | 'convergence'>('unusual');
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
    if (expandedSymbol === symbol) { setExpandedSymbol(null); return; }
    setDetailLoading(true);
    setExpandedSymbol(symbol);
    try { setDetail(await api.insiderTransactions(symbol)); } catch { setDetail(null); }
    setDetailLoading(false);
  };

  const formatDollar = (v: number) => {
    if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
    return `$${v.toFixed(0)}`;
  };

  const highConviction = signals.filter(s => s.insider_score >= 50 && s.smart_money_score && s.smart_money_score >= 50);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading insider data...</div>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <div onClick={() => setActiveTab('unusual')} className={`panel px-4 py-3 cursor-pointer transition-all ${activeTab === 'unusual' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}>
          <div className="text-2xl font-display font-bold text-emerald-600">{signals.filter(s => s.insider_score >= 50).length}</div>
          <div className="text-[10px] text-gray-500 tracking-widest mt-1">HIGH INSIDER SCORE</div>
        </div>
        <div onClick={() => setActiveTab('unusual')} className="panel px-4 py-3 cursor-pointer transition-all hover:border-gray-300">
          <div className="text-2xl font-display font-bold text-rose-600">{clusterBuys.length}</div>
          <div className="text-[10px] text-gray-500 tracking-widest mt-1">CLUSTER BUYS</div>
        </div>
        <div onClick={() => setActiveTab('feed')} className={`panel px-4 py-3 cursor-pointer transition-all ${activeTab === 'feed' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}>
          <div className="text-2xl font-display font-bold text-amber-600">{signals.filter(s => s.unusual_volume_flag).length}</div>
          <div className="text-[10px] text-gray-500 tracking-widest mt-1">UNUSUAL VOLUME</div>
        </div>
        <div onClick={() => setActiveTab('convergence')} className={`panel px-4 py-3 cursor-pointer transition-all ${activeTab === 'convergence' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}>
          <div className="text-2xl font-display font-bold text-blue-600">{highConviction.length}</div>
          <div className="text-[10px] text-gray-500 tracking-widest mt-1">INSIDER + SMART MONEY</div>
        </div>
      </div>

      {activeTab === 'unusual' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="text-xs text-gray-900 tracking-widest font-bold">UNUSUAL INSIDER ACTIVITY</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-center py-3 px-2 font-normal">Flags</th>
                  <th className="text-right py-3 px-2 font-normal">Buy $30d</th>
                  <th className="text-right py-3 px-2 font-normal">Net</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {signals.length === 0 ? (
                  <tr><td colSpan={6} className="text-center py-8 text-gray-500">No insider signals detected.</td></tr>
                ) : signals.map((s, i) => {
                  const net = s.total_buy_value_30d - s.total_sell_value_30d;
                  return (
                    <tr key={`${s.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] transition-colors cursor-pointer" onClick={() => loadDetail(s.symbol)}>
                      <td className="py-2.5 px-4 font-mono font-bold text-emerald-600">{s.symbol}</td>
                      <td className="py-2.5 px-2 text-right">
                        <span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(s.insider_score)}>{s.insider_score.toFixed(0)}</span>
                      </td>
                      <td className="py-2.5 px-2 text-center space-x-1">
                        {s.cluster_buy === 1 && <span className="inline-block px-1.5 py-0.5 rounded-lg text-[9px] font-bold bg-rose-600/20 text-rose-600">CLUSTER</span>}
                        {s.unusual_volume_flag === 1 && <span className="inline-block px-1.5 py-0.5 rounded-lg text-[9px] font-bold bg-amber-600/20 text-amber-600">VOL</span>}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-emerald-600">{formatDollar(s.total_buy_value_30d)}</td>
                      <td className={`py-2.5 px-2 text-right font-mono ${net >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{net >= 0 ? '+' : ''}{formatDollar(Math.abs(net))}</td>
                      <td className="py-2.5 px-4 text-gray-500 max-w-[320px] truncate">{s.narrative}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {expandedSymbol && (
            <div className="px-6 py-4 bg-gray-500 border-t border-gray-200">
              {detailLoading ? <div className="text-gray-500 animate-pulse text-center py-4">Loading...</div>
                : detail?.transactions?.length ? (
                  <table className="w-full text-[10px]">
                    <thead><tr className="text-gray-500 tracking-widest uppercase"><th className="text-left py-2 font-normal">Date</th><th className="text-left py-2 font-normal">Insider</th><th className="text-center py-2 font-normal">Type</th><th className="text-right py-2 font-normal">Value</th></tr></thead>
                    <tbody>{detail.transactions.slice(0, 10).map((tx, j) => (
                      <tr key={j} className="border-t border-gray-200/30">
                        <td className="py-1.5 font-mono text-gray-500">{tx.date}</td>
                        <td className="py-1.5 text-gray-700">{tx.insider_name || '--'}</td>
                        <td className="py-1.5 text-center"><span className={`px-1.5 py-0.5 rounded-lg text-[9px] font-bold ${tx.transaction_type === 'BUY' ? 'bg-emerald-600/15 text-emerald-600' : 'bg-rose-600/15 text-rose-600'}`}>{tx.transaction_type}</span></td>
                        <td className="py-1.5 text-right font-mono text-gray-700">{tx.value ? formatDollar(tx.value) : '--'}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                ) : <div className="text-gray-500 text-center py-4">No details available.</div>}
            </div>
          )}
        </div>
      )}

      {activeTab === 'feed' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="text-xs text-gray-900 tracking-widest font-bold">CLUSTER BUY SIGNALS</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">Score</th><th className="text-right py-3 px-2 font-normal">Insiders</th><th className="text-right py-3 px-2 font-normal">Buy $30d</th><th className="text-left py-3 px-4 font-normal">Narrative</th></tr></thead>
              <tbody>
                {clusterBuys.length === 0 ? <tr><td colSpan={5} className="text-center py-8 text-gray-500">No cluster buys.</td></tr> : clusterBuys.map((s, i) => (
                  <tr key={`cluster-${s.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${s.symbol}`)}>
                    <td className="py-2.5 px-4 font-mono font-bold text-rose-600">{s.symbol}</td>
                    <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold bg-emerald-600/15 text-emerald-600">{s.insider_score.toFixed(0)}</span></td>
                    <td className="py-2.5 px-2 text-right font-mono text-gray-900">{s.cluster_count || '--'}</td>
                    <td className="py-2.5 px-2 text-right font-mono text-emerald-600">{formatDollar(s.total_buy_value_30d)}</td>
                    <td className="py-2.5 px-4 text-gray-500 max-w-[400px] truncate">{s.narrative}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'convergence' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="text-xs text-gray-900 tracking-widest font-bold">INSIDER + SMART MONEY CONVERGENCE</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">Insider</th><th className="text-right py-3 px-2 font-normal">Smart $</th><th className="text-right py-3 px-2 font-normal">Buy $30d</th><th className="text-left py-3 px-4 font-normal">Narrative</th></tr></thead>
              <tbody>
                {highConviction.length === 0 ? <tr><td colSpan={5} className="text-center py-8 text-gray-500">No convergence signals.</td></tr> : highConviction.map((s, i) => (
                  <tr key={`conv-${s.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${s.symbol}`)}>
                    <td className="py-2.5 px-4 font-mono font-bold text-blue-600">{s.symbol}</td>
                    <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold bg-emerald-600/15 text-emerald-600">{s.insider_score.toFixed(0)}</span></td>
                    <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold bg-blue-600/15 text-blue-600">{s.smart_money_score?.toFixed(0) || '--'}</span></td>
                    <td className="py-2.5 px-2 text-right font-mono text-emerald-600">{formatDollar(s.total_buy_value_30d)}</td>
                    <td className="py-2.5 px-4 text-gray-500 max-w-[400px] truncate">{s.narrative}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
