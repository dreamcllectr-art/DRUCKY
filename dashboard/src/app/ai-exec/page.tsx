'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type AIExecSignal,
  type AIExecInvestment,
  type AIExecConvergence,
  type AIExecDetail,
} from '@/lib/api';

type Tab = 'signals' | 'investments' | 'convergence';

export default function AIExecPage() {
  const [signals, setSignals] = useState<AIExecSignal[]>([]);
  const [investments, setInvestments] = useState<AIExecInvestment[]>([]);
  const [convergence, setConvergence] = useState<AIExecConvergence[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('signals');

  // Detail expansion
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [detail, setDetail] = useState<AIExecDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      api.aiExecSignals(0, 180).catch(() => []),
      api.aiExecInvestments(180).catch(() => []),
      api.aiExecConvergence().catch(() => []),
    ]).then(([sigs, invs, conv]) => {
      setSignals(sigs);
      setInvestments(invs);
      setConvergence(conv);
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
      const data = await api.aiExecSymbol(symbol);
      setDetail(data);
    } catch {
      setDetail(null);
    }
    setDetailLoading(false);
  };

  const formatDollar = (v: number | null) => {
    if (!v) return '--';
    if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(1)}B`;
    if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
    return `$${v.toFixed(0)}`;
  };

  const activityLabel = (type: string) => {
    const labels: Record<string, { text: string; color: string }> = {
      personal_purchase: { text: 'PURCHASE', color: 'bg-terminal-green/15 text-terminal-green' },
      board_appointment: { text: 'BOARD', color: 'bg-terminal-cyan/15 text-terminal-cyan' },
      angel_investment: { text: 'ANGEL', color: 'bg-terminal-amber/15 text-terminal-amber' },
      vc_investment: { text: 'VC', color: 'bg-purple-500/15 text-purple-400' },
      advisory_role: { text: 'ADVISOR', color: 'bg-white/5 text-terminal-dim' },
      equity_grant: { text: 'EQUITY', color: 'bg-white/5 text-terminal-dim' },
      fund_raise: { text: 'FUND RAISE', color: 'bg-terminal-amber/15 text-terminal-amber' },
    };
    return labels[type] || { text: type.toUpperCase(), color: 'bg-white/5 text-terminal-dim' };
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          SCANNING AI EXECUTIVE INVESTMENTS...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          AI EXECUTIVE TRACKER
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          PERSONAL INVESTMENTS, BOARD SEATS, AND FUNDING BY AI LEADERS
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        <div
          onClick={() => setActiveTab('signals')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'signals' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-green">
            {signals.filter((s) => s.ai_exec_score >= 50).length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            HIGH SCORE SIGNALS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('investments')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'investments' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-amber">
            {investments.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            TRACKED ACTIVITIES
          </div>
        </div>
        <div
          onClick={() => setActiveTab('convergence')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'convergence' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-cyan">
            {convergence.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            MULTI-EXEC TARGETS
          </div>
        </div>
        <div className="panel px-4 py-3">
          <div className="text-2xl font-display font-bold text-terminal-dim">
            {new Set(investments.map((i) => i.exec_name)).size}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            ACTIVE EXECS
          </div>
        </div>
      </div>

      {/* Signals Tab */}
      {activeTab === 'signals' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              AI EXEC INVESTMENT SIGNALS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Universe stocks with AI executive backing — ranked by score
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-right py-3 px-2 font-normal">Execs</th>
                  <th className="text-left py-3 px-2 font-normal">Top Exec</th>
                  <th className="text-center py-3 px-2 font-normal">Activity</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {signals.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-8 text-terminal-dim">
                      No AI exec signals yet. Run the pipeline to scan executive investments.
                    </td>
                  </tr>
                ) : (
                  signals.map((s, i) => {
                    const activity = activityLabel(s.top_activity || '');
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
                                  s.ai_exec_score >= 70
                                    ? 'rgba(0,255,65,0.15)'
                                    : s.ai_exec_score >= 50
                                    ? 'rgba(255,184,0,0.15)'
                                    : 'rgba(255,255,255,0.05)',
                                color:
                                  s.ai_exec_score >= 70
                                    ? '#00FF41'
                                    : s.ai_exec_score >= 50
                                    ? '#FFB800'
                                    : '#888',
                              }}
                            >
                              {s.ai_exec_score.toFixed(0)}
                            </span>
                          </td>
                          <td className="py-2.5 px-2 text-right font-mono text-terminal-bright">
                            {s.exec_count}
                            {s.exec_count >= 2 && (
                              <span className="ml-1 text-[9px] text-terminal-cyan">+</span>
                            )}
                          </td>
                          <td className="py-2.5 px-2 text-terminal-text text-[10px]">
                            {s.top_exec || '--'}
                          </td>
                          <td className="py-2.5 px-2 text-center">
                            <span
                              className={`inline-block px-1.5 py-0.5 rounded-sm text-[9px] font-bold ${activity.color}`}
                            >
                              {activity.text}
                            </span>
                          </td>
                          <td className="py-2.5 px-2 text-terminal-dim text-[10px]">
                            {s.sector_signal || '--'}
                          </td>
                          <td className="py-2.5 px-4 text-terminal-dim max-w-[300px] truncate">
                            {s.narrative}
                          </td>
                        </tr>
                        {expandedSymbol === s.symbol && (
                          <tr key={`detail-${s.symbol}`}>
                            <td colSpan={7} className="bg-terminal-panel/50 p-0">
                              <div className="px-6 py-4">
                                {detailLoading ? (
                                  <div className="text-terminal-dim animate-pulse text-center py-4">
                                    Loading investment details...
                                  </div>
                                ) : detail?.investments && detail.investments.length > 0 ? (
                                  <table className="w-full text-[10px]">
                                    <thead>
                                      <tr className="text-terminal-dim tracking-widest uppercase">
                                        <th className="text-left py-2 font-normal">Exec</th>
                                        <th className="text-left py-2 font-normal">Org</th>
                                        <th className="text-center py-2 font-normal">Type</th>
                                        <th className="text-right py-2 font-normal">Amount</th>
                                        <th className="text-left py-2 font-normal">Round</th>
                                        <th className="text-right py-2 font-normal">Score</th>
                                        <th className="text-left py-2 font-normal">Summary</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {detail.investments.map((inv, j) => {
                                        const act = activityLabel(inv.activity_type);
                                        return (
                                          <tr
                                            key={`inv-${j}`}
                                            className="border-t border-terminal-border/30"
                                          >
                                            <td className="py-1.5 text-terminal-bright">
                                              {inv.exec_name}
                                            </td>
                                            <td className="py-1.5 text-terminal-dim">
                                              {inv.exec_org}
                                            </td>
                                            <td className="py-1.5 text-center">
                                              <span
                                                className={`px-1.5 py-0.5 rounded-sm text-[9px] font-bold ${act.color}`}
                                              >
                                                {act.text}
                                              </span>
                                            </td>
                                            <td className="py-1.5 text-right font-mono text-terminal-green">
                                              {formatDollar(inv.investment_amount)}
                                            </td>
                                            <td className="py-1.5 text-terminal-dim uppercase">
                                              {inv.funding_round || '--'}
                                            </td>
                                            <td className="py-1.5 text-right font-mono text-terminal-text">
                                              {inv.raw_score.toFixed(0)}
                                            </td>
                                            <td className="py-1.5 text-terminal-dim max-w-[250px] truncate">
                                              {inv.summary || '--'}
                                            </td>
                                          </tr>
                                        );
                                      })}
                                    </tbody>
                                  </table>
                                ) : (
                                  <div className="text-terminal-dim text-center py-4">
                                    No investment details available.
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

      {/* Investment Log Tab */}
      {activeTab === 'investments' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              INVESTMENT ACTIVITY LOG
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              All tracked personal investments by AI executives — chronological feed
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Exec</th>
                  <th className="text-left py-3 px-2 font-normal">Org</th>
                  <th className="text-center py-3 px-2 font-normal">Type</th>
                  <th className="text-left py-3 px-2 font-normal">Target</th>
                  <th className="text-left py-3 px-2 font-normal">Ticker</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">Amount</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-left py-3 px-4 font-normal">Summary</th>
                </tr>
              </thead>
              <tbody>
                {investments.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="text-center py-8 text-terminal-dim">
                      No investment activity tracked yet. Run the pipeline to scan.
                    </td>
                  </tr>
                ) : (
                  investments.map((inv, i) => {
                    const act = activityLabel(inv.activity_type);
                    return (
                      <tr
                        key={`inv-${i}`}
                        className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors"
                      >
                        <td className="py-2.5 px-4 text-terminal-bright font-bold text-[10px]">
                          {inv.exec_name}
                        </td>
                        <td className="py-2.5 px-2 text-terminal-dim text-[10px]">
                          {inv.exec_org}
                        </td>
                        <td className="py-2.5 px-2 text-center">
                          <span
                            className={`inline-block px-1.5 py-0.5 rounded-sm text-[9px] font-bold ${act.color}`}
                          >
                            {act.text}
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-terminal-text text-[10px]">
                          {inv.target_company}
                        </td>
                        <td className="py-2.5 px-2 font-mono text-terminal-green text-[10px]">
                          {inv.target_ticker || '--'}
                        </td>
                        <td className="py-2.5 px-2 text-terminal-dim text-[10px]">
                          {inv.target_sector || '--'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-green">
                          {formatDollar(inv.investment_amount)}
                        </td>
                        <td className="py-2.5 px-2 text-right">
                          <span
                            className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                            style={{
                              backgroundColor:
                                inv.raw_score >= 70
                                  ? 'rgba(0,255,65,0.15)'
                                  : inv.raw_score >= 50
                                  ? 'rgba(255,184,0,0.15)'
                                  : 'rgba(255,255,255,0.05)',
                              color:
                                inv.raw_score >= 70
                                  ? '#00FF41'
                                  : inv.raw_score >= 50
                                  ? '#FFB800'
                                  : '#888',
                            }}
                          >
                            {inv.raw_score.toFixed(0)}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 text-terminal-dim max-w-[300px] truncate">
                          {inv.summary || '--'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Multi-Exec Convergence Tab */}
      {activeTab === 'convergence' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              MULTI-EXEC CONVERGENCE
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Companies where 2+ AI executives have independently invested — strongest signal
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Company</th>
                  <th className="text-left py-3 px-2 font-normal">Ticker</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">Execs</th>
                  <th className="text-left py-3 px-2 font-normal">Who</th>
                  <th className="text-right py-3 px-2 font-normal">Max Score</th>
                  <th className="text-left py-3 px-4 font-normal">Last Scan</th>
                </tr>
              </thead>
              <tbody>
                {convergence.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-8 text-terminal-dim">
                      No multi-exec convergence detected yet. This requires data from multiple scans.
                    </td>
                  </tr>
                ) : (
                  convergence.map((c, i) => (
                    <tr
                      key={`conv-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() =>
                        c.target_ticker &&
                        (window.location.href = `/asset/${c.target_ticker}`)
                      }
                    >
                      <td className="py-2.5 px-4 text-terminal-bright font-bold">
                        {c.target_company}
                      </td>
                      <td className="py-2.5 px-2 font-mono text-terminal-green">
                        {c.target_ticker || 'PRIVATE'}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[10px]">
                        {c.target_sector || '--'}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold bg-terminal-cyan/15 text-terminal-cyan">
                          {c.exec_count}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-terminal-text text-[10px] max-w-[250px] truncate">
                        {c.executives}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span
                          className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                          style={{
                            backgroundColor:
                              c.max_score >= 70
                                ? 'rgba(0,255,65,0.15)'
                                : 'rgba(255,184,0,0.15)',
                            color: c.max_score >= 70 ? '#00FF41' : '#FFB800',
                          }}
                        >
                          {c.max_score.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-4 font-mono text-terminal-dim text-[10px]">
                        {c.latest_scan}
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
