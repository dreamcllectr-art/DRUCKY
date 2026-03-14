'use client';

import { Fragment, useEffect, useState } from 'react';
import { api, type ThematicIdea, type ThemeSummary } from '@/lib/api';

const THEME_META: Record<string, { label: string; icon: string; color: string }> = {
  ai_infrastructure:    { label: 'AI INFRASTRUCTURE',    icon: '🤖', color: 'text-blue-400' },
  energy_buildout:      { label: 'ENERGY BUILDOUT',      icon: '⚡', color: 'text-amber-400' },
  fintech_stablecoins:  { label: 'FINTECH & STABLECOINS', icon: '💰', color: 'text-emerald-400' },
  defense_tech:         { label: 'DEFENSE TECH',         icon: '🛡', color: 'text-red-400' },
  reshoring_chips:      { label: 'RESHORING & CHIPS',    icon: '🏭', color: 'text-purple-400' },
};

type Tab = 'top' | 'ai_infrastructure' | 'energy_buildout' | 'fintech_stablecoins' | 'defense_tech' | 'reshoring_chips';

export default function TradingIdeasPage() {
  const [ideas, setIdeas] = useState<ThematicIdea[]>([]);
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [topIdeas, setTopIdeas] = useState<ThematicIdea[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('top');
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.tradingIdeasThemes().catch(() => []),
      api.tradingIdeasTop(20).catch(() => []),
      api.tradingIdeas().catch(() => []),
    ]).then(([t, top, all]) => {
      setThemes(t);
      setTopIdeas(top);
      setIdeas(all);
      setLoading(false);
    });
  }, []);

  const loadTheme = async (theme: string) => {
    setActiveTab(theme as Tab);
    if (theme === 'top') return;
    try {
      const data = await api.tradingIdeasTheme(theme);
      setIdeas(prev => {
        const other = prev.filter(i => i.theme !== theme);
        return [...other, ...data];
      });
    } catch { /* keep existing */ }
  };

  const formatMcap = (v: number) => {
    if (!v) return 'N/A';
    if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
    if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
    return `$${v.toFixed(0)}`;
  };

  const formatPct = (v: number | null) => {
    if (v == null) return '—';
    return `${(v * 100).toFixed(0)}%`;
  };

  const scoreColor = (score: number) => {
    if (score >= 70) return 'text-terminal-green';
    if (score >= 55) return 'text-terminal-amber';
    if (score >= 40) return 'text-terminal-text';
    return 'text-terminal-dim';
  };

  const scoreBg = (score: number) => {
    if (score >= 70) return 'bg-terminal-green/15 border-terminal-green/30';
    if (score >= 55) return 'bg-terminal-amber/10 border-terminal-amber/30';
    return 'bg-white/[0.02] border-terminal-border';
  };

  const displayedIdeas = activeTab === 'top'
    ? topIdeas
    : ideas.filter(i => i.theme === activeTab).sort((a, b) => b.composite_score - a.composite_score);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          SCANNING THEMATIC UNIVERSE...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          THEMATIC ALPHA SCANNER
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          SMALL/MID-CAP TRADING IDEAS — POLICY-DRIVEN SECULAR THEMES — $300M-$10B
        </p>
      </div>

      {/* Theme summary cards */}
      <div className="grid grid-cols-5 gap-3">
        {Object.entries(THEME_META).map(([key, meta]) => {
          const theme = themes.find(t => t.theme === key);
          return (
            <div
              key={key}
              onClick={() => loadTheme(key)}
              className={`panel px-4 py-3 cursor-pointer transition-all ${
                activeTab === key ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">{meta.icon}</span>
                <span className={`text-[10px] tracking-widest ${meta.color}`}>{meta.label}</span>
              </div>
              {theme ? (
                <>
                  <div className="text-xl font-display font-bold text-terminal-green">
                    {theme.strong_ideas}
                  </div>
                  <div className="text-[9px] text-terminal-dim tracking-widest">
                    STRONG IDEAS / {theme.num_stocks} TOTAL
                  </div>
                  <div className="flex gap-3 mt-2 text-[9px]">
                    <span className="text-terminal-dim">AVG <span className={scoreColor(theme.avg_score)}>{theme.avg_score}</span></span>
                    <span className="text-terminal-dim">TOP <span className="text-terminal-green">{theme.top_score}</span></span>
                  </div>
                </>
              ) : (
                <div className="text-terminal-dim text-xs">No data</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-terminal-border pb-0">
        <button
          onClick={() => setActiveTab('top')}
          className={`px-4 py-2 text-[10px] tracking-widest transition-all border-b-2 ${
            activeTab === 'top'
              ? 'text-terminal-green border-terminal-green'
              : 'text-terminal-dim border-transparent hover:text-terminal-text'
          }`}
        >
          TOP IDEAS
        </button>
        {Object.entries(THEME_META).map(([key, meta]) => (
          <button
            key={key}
            onClick={() => loadTheme(key)}
            className={`px-3 py-2 text-[10px] tracking-widest transition-all border-b-2 ${
              activeTab === key
                ? `${meta.color} border-current`
                : 'text-terminal-dim border-transparent hover:text-terminal-text'
            }`}
          >
            {meta.icon} {meta.label}
          </button>
        ))}
      </div>

      {/* Ideas table */}
      {displayedIdeas.length === 0 ? (
        <div className="panel p-8 text-center text-terminal-dim">
          No thematic ideas found. Run the scanner first: <code className="text-terminal-green">python tools/thematic_scanner.py</code>
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-terminal-border text-[9px] tracking-widest text-terminal-dim">
                <th className="text-left px-4 py-3">#</th>
                <th className="text-left px-3 py-3">SYMBOL</th>
                <th className="text-left px-3 py-3">NAME</th>
                <th className="text-left px-3 py-3">THEME</th>
                <th className="text-left px-3 py-3">SUB-THEME</th>
                <th className="text-right px-3 py-3">SCORE</th>
                <th className="text-right px-3 py-3">POLICY</th>
                <th className="text-right px-3 py-3">GROWTH</th>
                <th className="text-right px-3 py-3">TECH</th>
                <th className="text-right px-3 py-3">VALUE</th>
                <th className="text-right px-3 py-3">INST</th>
                <th className="text-right px-3 py-3">MCAP</th>
                <th className="text-right px-3 py-3">PRICE</th>
                <th className="text-right px-3 py-3">REV GR</th>
                <th className="text-right px-3 py-3">MOM 3M</th>
              </tr>
            </thead>
            <tbody>
              {displayedIdeas.map((idea, idx) => {
                const meta = THEME_META[idea.theme] || { label: idea.theme, icon: '?', color: 'text-terminal-dim' };
                const isExpanded = expandedSymbol === `${idea.symbol}-${idea.theme}`;
                let catalysts: string[] = [];
                try { catalysts = JSON.parse(idea.catalysts || '[]'); } catch { /* ignore */ }

                return (
                  <Fragment key={`${idea.symbol}-${idea.theme}`}>
                    <tr
                      onClick={() => setExpandedSymbol(isExpanded ? null : `${idea.symbol}-${idea.theme}`)}
                      className={`border-b border-terminal-border/50 cursor-pointer transition-all ${
                        isExpanded ? 'bg-terminal-green/5' : 'hover:bg-white/[0.02]'
                      }`}
                    >
                      <td className="px-4 py-2.5 text-terminal-dim">{idx + 1}</td>
                      <td className="px-3 py-2.5 font-mono font-bold text-terminal-bright">{idea.symbol}</td>
                      <td className="px-3 py-2.5 text-terminal-text truncate max-w-[180px]">{idea.name}</td>
                      <td className={`px-3 py-2.5 ${meta.color}`}>
                        <span className="text-[10px] tracking-wider">{meta.icon} {meta.label}</span>
                      </td>
                      <td className="px-3 py-2.5 text-terminal-dim text-[10px] tracking-wider">
                        {idea.sub_theme?.replace(/_/g, ' ').toUpperCase()}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <span className={`font-mono font-bold ${scoreColor(idea.composite_score)}`}>
                          {idea.composite_score.toFixed(1)}
                        </span>
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono ${scoreColor(idea.policy_score)}`}>
                        {idea.policy_score.toFixed(0)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono ${scoreColor(idea.growth_score)}`}>
                        {idea.growth_score.toFixed(0)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono ${scoreColor(idea.technical_score)}`}>
                        {idea.technical_score.toFixed(0)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono ${scoreColor(idea.valuation_score)}`}>
                        {idea.valuation_score.toFixed(0)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono ${scoreColor(idea.institutional_score)}`}>
                        {idea.institutional_score.toFixed(0)}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-terminal-dim">
                        {formatMcap(idea.market_cap)}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-terminal-text">
                        ${idea.price?.toFixed(2) ?? '—'}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono ${
                        idea.revenue_growth != null && idea.revenue_growth > 0.10
                          ? 'text-terminal-green'
                          : idea.revenue_growth != null && idea.revenue_growth < 0
                          ? 'text-terminal-red'
                          : 'text-terminal-dim'
                      }`}>
                        {formatPct(idea.revenue_growth)}
                      </td>
                      <td className={`px-3 py-2.5 text-right font-mono ${
                        idea.momentum_3m != null && idea.momentum_3m > 0
                          ? 'text-terminal-green'
                          : 'text-terminal-red'
                      }`}>
                        {idea.momentum_3m != null ? `${idea.momentum_3m.toFixed(1)}%` : '—'}
                      </td>
                    </tr>

                    {/* Expanded detail row */}
                    {isExpanded && (
                      <tr key={`${idea.symbol}-${idea.theme}-detail`} className="bg-terminal-green/5">
                        <td colSpan={15} className="px-6 py-4">
                          <div className="grid grid-cols-3 gap-6">
                            {/* Score breakdown */}
                            <div>
                              <div className="text-[10px] text-terminal-dim tracking-widest mb-2">SCORE BREAKDOWN</div>
                              <div className="space-y-1.5">
                                {[
                                  { label: 'Policy Exposure', score: idea.policy_score, weight: '25%' },
                                  { label: 'Growth Quality', score: idea.growth_score, weight: '25%' },
                                  { label: 'Technical Setup', score: idea.technical_score, weight: '20%' },
                                  { label: 'Valuation', score: idea.valuation_score, weight: '15%' },
                                  { label: 'Institutional', score: idea.institutional_score, weight: '15%' },
                                ].map(({ label, score, weight }) => (
                                  <div key={label} className="flex items-center gap-2">
                                    <span className="text-[10px] text-terminal-dim w-28">{label} ({weight})</span>
                                    <div className="flex-1 h-1.5 bg-terminal-border rounded-full overflow-hidden">
                                      <div
                                        className={`h-full rounded-full ${
                                          score >= 70 ? 'bg-terminal-green' : score >= 50 ? 'bg-terminal-amber' : 'bg-terminal-red'
                                        }`}
                                        style={{ width: `${score}%` }}
                                      />
                                    </div>
                                    <span className={`font-mono text-[10px] w-8 text-right ${scoreColor(score)}`}>
                                      {score.toFixed(0)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>

                            {/* Catalysts */}
                            <div>
                              <div className="text-[10px] text-terminal-dim tracking-widest mb-2">POLICY CATALYSTS</div>
                              <div className="space-y-1">
                                {catalysts.map((c, i) => (
                                  <div key={i} className="flex items-start gap-2">
                                    <span className="text-terminal-green text-[10px] mt-0.5">+</span>
                                    <span className="text-[11px] text-terminal-text">{c}</span>
                                  </div>
                                ))}
                              </div>
                            </div>

                            {/* Metrics */}
                            <div>
                              <div className="text-[10px] text-terminal-dim tracking-widest mb-2">KEY METRICS</div>
                              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                                <span className="text-terminal-dim">P/E</span>
                                <span className="text-terminal-text font-mono">
                                  {idea.pe_ratio?.toFixed(1) ?? '—'}
                                </span>
                                <span className="text-terminal-dim">P/S</span>
                                <span className="text-terminal-text font-mono">
                                  {idea.ps_ratio?.toFixed(1) ?? '—'}
                                </span>
                                <span className="text-terminal-dim">RSI</span>
                                <span className={`font-mono ${
                                  idea.rsi_14 != null && idea.rsi_14 > 70 ? 'text-terminal-red' :
                                  idea.rsi_14 != null && idea.rsi_14 < 30 ? 'text-terminal-green' :
                                  'text-terminal-text'
                                }`}>
                                  {idea.rsi_14?.toFixed(0) ?? '—'}
                                </span>
                                <span className="text-terminal-dim">Short %</span>
                                <span className={`font-mono ${
                                  idea.short_pct != null && idea.short_pct > 0.10 ? 'text-terminal-red' : 'text-terminal-text'
                                }`}>
                                  {idea.short_pct != null ? `${(idea.short_pct * 100).toFixed(1)}%` : '—'}
                                </span>
                                <span className="text-terminal-dim">Earnings Gr</span>
                                <span className={`font-mono ${
                                  idea.earnings_growth != null && idea.earnings_growth > 0 ? 'text-terminal-green' : 'text-terminal-red'
                                }`}>
                                  {formatPct(idea.earnings_growth)}
                                </span>
                              </div>

                              {idea.narrative && (
                                <div className="mt-3 text-[10px] text-terminal-dim leading-relaxed">
                                  {idea.narrative}
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
