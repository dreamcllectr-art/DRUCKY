'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type PredictionMarketSignal,
  type PredictionMarketRaw,
  type PredictionMarketCategory,
} from '@/lib/api';

type Tab = 'signals' | 'markets' | 'categories';

export default function PredictionsPage() {
  const [signals, setSignals] = useState<PredictionMarketSignal[]>([]);
  const [markets, setMarkets] = useState<PredictionMarketRaw[]>([]);
  const [categories, setCategories] = useState<PredictionMarketCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('signals');
  const [categoryFilter, setCategoryFilter] = useState<string>('');

  useEffect(() => {
    Promise.all([
      api.predictionMarkets(0, 7).catch(() => []),
      api.predictionMarketsRaw(undefined, 3).catch(() => []),
      api.predictionMarketCategories().catch(() => []),
    ]).then(([sigs, mkts, cats]) => {
      setSignals(sigs);
      setMarkets(mkts);
      setCategories(cats);
      setLoading(false);
    });
  }, []);

  const loadCategory = async (cat: string) => {
    setCategoryFilter(cat);
    setActiveTab('markets');
    try {
      const mkts = await api.predictionMarketsRaw(cat, 7);
      setMarkets(mkts);
    } catch {
      /* keep existing */
    }
  };

  const formatVol = (v: number | null) => {
    if (!v) return '—';
    if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
    return `$${v.toFixed(0)}`;
  };

  const dirColor = (dir: string | null) => {
    if (!dir) return 'text-terminal-dim';
    if (dir === 'bullish' || dir === 'positive') return 'text-terminal-green';
    if (dir === 'bearish' || dir === 'negative') return 'text-terminal-red';
    return 'text-terminal-amber';
  };

  const categoryColor = (cat: string) => {
    if (cat.includes('rate_cut') || cat.includes('inflation_lower')) return 'text-terminal-green';
    if (cat.includes('rate_hike') || cat.includes('recession') || cat.includes('tariff_increase')) return 'text-terminal-red';
    return 'text-terminal-amber';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          FETCHING POLYMARKET DATA...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          PREDICTION MARKETS
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          POLYMARKET SIGNALS — IMPACT CLASSIFICATION — STOCK MAPPING
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
            {signals.filter((s) => s.pm_score >= 50).length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            HIGH IMPACT SIGNALS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('signals')}
          className="panel px-4 py-3 cursor-pointer transition-all hover:border-terminal-muted"
        >
          <div className="text-2xl font-display font-bold text-terminal-cyan">
            {signals.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            STOCKS AFFECTED
          </div>
        </div>
        <div
          onClick={() => setActiveTab('markets')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'markets' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-amber">
            {markets.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            ACTIVE MARKETS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('categories')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'categories' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-red">
            {categories.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            IMPACT CATEGORIES
          </div>
        </div>
      </div>

      {/* Signals Tab — Stock-level impact */}
      {activeTab === 'signals' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              STOCK-LEVEL PREDICTION MARKET SIGNALS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Polymarket events classified and mapped to equities via Gemini LLM
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">PM Score</th>
                  <th className="text-right py-3 px-2 font-normal">Markets</th>
                  <th className="text-right py-3 px-2 font-normal">Net Impact</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {signals.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-terminal-dim">
                      No prediction market signals. Run the pipeline to fetch Polymarket data.
                    </td>
                  </tr>
                ) : (
                  signals.map((s, i) => (
                    <tr
                      key={`pm-${s.symbol}-${i}`}
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
                              s.pm_score >= 60
                                ? 'rgba(0,255,65,0.15)'
                                : s.pm_score >= 40
                                ? 'rgba(255,184,0,0.15)'
                                : 'rgba(255,255,255,0.05)',
                            color:
                              s.pm_score >= 60
                                ? '#00FF41'
                                : s.pm_score >= 40
                                ? '#FFB800'
                                : '#888',
                          }}
                        >
                          {s.pm_score.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-dim">
                        {s.market_count || '—'}
                      </td>
                      <td className={`py-2.5 px-2 text-right font-mono ${
                        (s.net_impact || 0) >= 0 ? 'text-terminal-green' : 'text-terminal-red'
                      }`}>
                        {s.net_impact ? (s.net_impact >= 0 ? '+' : '') + s.net_impact.toFixed(1) : '—'}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[350px] truncate">
                        {s.narrative || '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Markets Tab — Raw Polymarket data */}
      {activeTab === 'markets' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border flex items-center justify-between">
            <div>
              <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
                RAW POLYMARKET EVENTS
                {categoryFilter && (
                  <span className="ml-2 text-terminal-amber">
                    [{categoryFilter.replace(/_/g, ' ').toUpperCase()}]
                  </span>
                )}
              </h2>
              <p className="text-[10px] text-terminal-dim mt-0.5">
                Classified financial markets from Polymarket Gamma API
              </p>
            </div>
            {categoryFilter && (
              <button
                onClick={() => {
                  setCategoryFilter('');
                  api.predictionMarketsRaw(undefined, 3).then(setMarkets).catch(() => {});
                }}
                className="text-[10px] text-terminal-dim hover:text-terminal-green transition-colors"
              >
                CLEAR FILTER
              </button>
            )}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Question</th>
                  <th className="text-center py-3 px-2 font-normal">Category</th>
                  <th className="text-right py-3 px-2 font-normal">YES %</th>
                  <th className="text-right py-3 px-2 font-normal">Volume</th>
                  <th className="text-center py-3 px-2 font-normal">Direction</th>
                  <th className="text-left py-3 px-2 font-normal">Symbols</th>
                </tr>
              </thead>
              <tbody>
                {markets.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-8 text-terminal-dim">
                      No classified markets available.
                    </td>
                  </tr>
                ) : (
                  markets.map((m, i) => (
                    <tr
                      key={`mkt-${m.market_id}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors"
                    >
                      <td className="py-2.5 px-4 text-terminal-text max-w-[400px] truncate">
                        {m.question || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        <span className={`px-1.5 py-0.5 rounded-sm text-[9px] font-bold uppercase ${
                          categoryColor(m.impact_category || '')
                        }`}>
                          {m.impact_category?.replace(/_/g, ' ') || '—'}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-bright">
                        {m.yes_probability ? `${(m.yes_probability * 100).toFixed(0)}%` : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-dim">
                        {formatVol(m.volume)}
                      </td>
                      <td className={`py-2.5 px-2 text-center font-bold text-[10px] ${dirColor(m.direction)}`}>
                        {m.direction?.toUpperCase() || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-green font-mono text-[10px]">
                        {m.specific_symbols || '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Categories Tab */}
      {activeTab === 'categories' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              IMPACT CATEGORIES
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Aggregated Polymarket signal categories — click to drill into markets
            </p>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 p-4">
            {categories.length === 0 ? (
              <div className="col-span-full text-center py-8 text-terminal-dim">
                No categories available.
              </div>
            ) : (
              categories.map((cat) => (
                <div
                  key={cat.impact_category}
                  onClick={() => loadCategory(cat.impact_category)}
                  className="panel px-4 py-3 cursor-pointer hover:border-terminal-green/30 transition-all"
                >
                  <div className={`text-xs font-bold tracking-wider uppercase ${categoryColor(cat.impact_category)}`}>
                    {cat.impact_category.replace(/_/g, ' ')}
                  </div>
                  <div className="flex items-center justify-between mt-2 text-[10px] text-terminal-dim">
                    <span>{cat.market_count} markets</span>
                    <span>Avg prob: {(cat.avg_probability * 100).toFixed(0)}%</span>
                  </div>
                  <div className="text-[10px] text-terminal-dim mt-1">
                    Volume: {formatVol(cat.total_volume)}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
