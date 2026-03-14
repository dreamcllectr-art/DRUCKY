'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type MASignal,
  type MARumor,
} from '@/lib/api';

type Tab = 'targets' | 'rumors' | 'deals';

export default function MAPage() {
  const [signals, setSignals] = useState<MASignal[]>([]);
  const [rumors, setRumors] = useState<MARumor[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('targets');

  useEffect(() => {
    Promise.all([
      api.maTopTargets().catch(() => []),
      api.maRumors(30).catch(() => []),
    ]).then(([sigs, rums]) => {
      setSignals(sigs);
      setRumors(rums);
      setLoading(false);
    });
  }, []);

  const dealStageColor = (stage: string | null) => {
    if (!stage) return 'text-terminal-dim';
    if (stage === 'definitive') return 'text-terminal-green';
    if (stage === 'rumor') return 'text-terminal-amber';
    if (stage === 'speculation') return 'text-terminal-dim';
    return 'text-terminal-cyan';
  };

  const dealStageBg = (stage: string | null) => {
    if (!stage) return 'bg-white/5';
    if (stage === 'definitive') return 'bg-terminal-green/15';
    if (stage === 'rumor') return 'bg-terminal-amber/15';
    return 'bg-white/5';
  };

  const definitive = signals.filter((s) => s.deal_stage === 'definitive');
  const highScore = signals.filter((s) => s.ma_score >= 50);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          SCANNING M&A INTELLIGENCE...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          M&A INTELLIGENCE
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          TARGET PROFILING — RUMOR DETECTION — DEAL STAGE TRACKING
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        <div
          onClick={() => setActiveTab('targets')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'targets' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-green">
            {highScore.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            HIGH M&A SCORE
          </div>
        </div>
        <div
          onClick={() => setActiveTab('deals')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'deals' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-cyan">
            {definitive.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            DEFINITIVE DEALS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('rumors')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'rumors' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-amber">
            {rumors.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            ACTIVE RUMORS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('targets')}
          className="panel px-4 py-3 cursor-pointer transition-all hover:border-terminal-muted"
        >
          <div className="text-2xl font-display font-bold text-terminal-red">
            {signals.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            TOTAL TARGETS
          </div>
        </div>
      </div>

      {/* Targets Tab */}
      {activeTab === 'targets' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              TOP M&A TARGETS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Ranked by composite M&A score — valuation, balance sheet, growth, smart money, sector consolidation
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-right py-3 px-2 font-normal">Profile</th>
                  <th className="text-right py-3 px-2 font-normal">Rumor</th>
                  <th className="text-center py-3 px-2 font-normal">Stage</th>
                  <th className="text-right py-3 px-2 font-normal">Premium</th>
                  <th className="text-left py-3 px-4 font-normal">Acquirer / Headline</th>
                </tr>
              </thead>
              <tbody>
                {signals.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-terminal-dim">
                      No M&A signals detected. Run the pipeline to scan targets.
                    </td>
                  </tr>
                ) : (
                  signals.map((s, i) => (
                    <tr
                      key={`ma-${s.symbol}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => (window.location.href = `/asset/${s.symbol}`)}
                    >
                      <td className="py-2.5 px-4">
                        <span className="font-mono font-bold text-terminal-green">{s.symbol}</span>
                        {s.company_name && (
                          <span className="ml-2 text-[9px] text-terminal-dim">{s.company_name}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[10px] tracking-wider uppercase">
                        {s.sector || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span
                          className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                          style={{
                            backgroundColor:
                              s.ma_score >= 70
                                ? 'rgba(0,255,65,0.15)'
                                : s.ma_score >= 50
                                ? 'rgba(255,184,0,0.15)'
                                : 'rgba(255,255,255,0.05)',
                            color:
                              s.ma_score >= 70
                                ? '#00FF41'
                                : s.ma_score >= 50
                                ? '#FFB800'
                                : '#888',
                          }}
                        >
                          {s.ma_score.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-dim">
                        {s.target_profile_score?.toFixed(0) || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-dim">
                        {s.rumor_score?.toFixed(0) || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        {s.deal_stage && (
                          <span
                            className={`px-1.5 py-0.5 rounded-sm text-[9px] font-bold uppercase ${dealStageBg(s.deal_stage)} ${dealStageColor(s.deal_stage)}`}
                          >
                            {s.deal_stage}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-cyan">
                        {s.expected_premium_pct ? `+${s.expected_premium_pct.toFixed(0)}%` : '—'}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[300px] truncate">
                        {s.acquirer_name || s.best_headline || s.narrative || '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Rumors Tab */}
      {activeTab === 'rumors' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              M&A RUMOR TRACKER
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              News + web search rumors with credibility scoring and temporal decay
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-left py-3 px-2 font-normal">Date</th>
                  <th className="text-left py-3 px-2 font-normal">Source</th>
                  <th className="text-center py-3 px-2 font-normal">Credibility</th>
                  <th className="text-center py-3 px-2 font-normal">Stage</th>
                  <th className="text-left py-3 px-2 font-normal">Acquirer</th>
                  <th className="text-left py-3 px-4 font-normal">Headline</th>
                </tr>
              </thead>
              <tbody>
                {rumors.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-8 text-terminal-dim">
                      No active M&A rumors detected.
                    </td>
                  </tr>
                ) : (
                  rumors.map((r, i) => (
                    <tr
                      key={`rum-${r.symbol}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors"
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-amber">
                        {r.symbol}
                      </td>
                      <td className="py-2.5 px-2 font-mono text-terminal-dim text-[10px]">
                        {r.date}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[10px] tracking-wider uppercase">
                        {r.rumor_source || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        <span
                          className={`px-1.5 py-0.5 rounded-sm text-[10px] font-bold ${
                            (r.credibility_score || 0) >= 7
                              ? 'bg-terminal-green/15 text-terminal-green'
                              : (r.credibility_score || 0) >= 4
                              ? 'bg-terminal-amber/15 text-terminal-amber'
                              : 'bg-white/5 text-terminal-dim'
                          }`}
                        >
                          {r.credibility_score || '—'}/10
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        <span
                          className={`px-1.5 py-0.5 rounded-sm text-[9px] font-bold uppercase ${dealStageBg(r.deal_stage)} ${dealStageColor(r.deal_stage)}`}
                        >
                          {r.deal_stage || '—'}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-terminal-cyan text-[10px]">
                        {r.acquirer_name || '—'}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[400px] truncate">
                        {r.rumor_headline || '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Definitive Deals Tab */}
      {activeTab === 'deals' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              DEFINITIVE AGREEMENTS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Confirmed M&A deals — highest conviction targets with announced premiums
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-left py-3 px-2 font-normal">Acquirer</th>
                  <th className="text-right py-3 px-2 font-normal">Premium</th>
                  <th className="text-left py-3 px-4 font-normal">Headline</th>
                </tr>
              </thead>
              <tbody>
                {definitive.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-terminal-dim">
                      No definitive M&A deals currently tracked.
                    </td>
                  </tr>
                ) : (
                  definitive.map((s, i) => (
                    <tr
                      key={`deal-${s.symbol}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => (window.location.href = `/asset/${s.symbol}`)}
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-cyan">
                        {s.symbol}
                        {s.company_name && (
                          <span className="ml-2 text-[9px] text-terminal-dim">{s.company_name}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[10px] tracking-wider uppercase">
                        {s.sector || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold bg-terminal-green/15 text-terminal-green">
                          {s.ma_score.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-terminal-bright">
                        {s.acquirer_name || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-green">
                        {s.expected_premium_pct ? `+${s.expected_premium_pct.toFixed(0)}%` : '—'}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[400px] truncate">
                        {s.best_headline || s.narrative || '—'}
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
