'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type DisplacementSignal,
  type AltDataSignal,
  type SectorExpertSignal,
} from '@/lib/api';

const ORDER_TYPE_LABELS: Record<string, string> = {
  first_order: '1ST ORDER',
  second_order: '2ND ORDER',
  cross_asset: 'CROSS-ASSET',
};

const SOURCE_ICONS: Record<string, string> = {
  noaa_weather: '🌊',
  nasa_firms: '🔥',
  google_trends: '📈',
  usda_crop: '🌾',
  china_activity: '🏭',
  baltic_dry: '🚢',
};

export default function DisplacementPage() {
  const [displacements, setDisplacements] = useState<DisplacementSignal[]>([]);
  const [altData, setAltData] = useState<AltDataSignal[]>([]);
  const [experts, setExperts] = useState<SectorExpertSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'news' | 'alt' | 'expert'>('news');

  useEffect(() => {
    Promise.all([
      api.displacement().catch(() => []),
      api.altData().catch(() => []),
      api.sectorExperts().catch(() => []),
    ]).then(([d, a, e]) => {
      setDisplacements(d);
      setAltData(a);
      setExperts(e);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          SCANNING FOR DISPLACEMENTS...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          DISPLACEMENT DETECTION
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          MATERIAL EVENTS THE MARKET HASN&apos;T PRICED IN YET
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3">
        <div
          onClick={() => setActiveTab('news')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'news' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-text">
            {displacements.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            NEWS DISPLACEMENTS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('alt')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'alt' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-text">
            {altData.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            ALT DATA SIGNALS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('expert')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'expert' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-text">
            {experts.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            SECTOR EXPERT SIGNALS
          </div>
        </div>
      </div>

      {/* News Displacements Tab */}
      {activeTab === 'news' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              NEWS DISPLACEMENT SIGNALS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Material news + no price response = opportunity
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-right py-3 px-2 font-normal">Score</th>
                  <th className="text-center py-3 px-2 font-normal">Direction</th>
                  <th className="text-center py-3 px-2 font-normal">Type</th>
                  <th className="text-right py-3 px-2 font-normal">Expected</th>
                  <th className="text-right py-3 px-2 font-normal">Actual 1d</th>
                  <th className="text-right py-3 px-2 font-normal">Actual 3d</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {displacements.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-terminal-dim">
                      No active displacement signals. Run the pipeline to detect them.
                    </td>
                  </tr>
                ) : (
                  displacements.map((d, i) => (
                    <tr
                      key={`${d.symbol}-${d.date}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => (window.location.href = `/asset/${d.symbol}`)}
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-bright">
                        {d.symbol}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono">
                        <span
                          className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                          style={{
                            backgroundColor:
                              d.displacement_score >= 70
                                ? 'rgba(0,255,65,0.15)'
                                : d.displacement_score >= 50
                                ? 'rgba(255,184,0,0.15)'
                                : 'rgba(255,255,255,0.05)',
                            color:
                              d.displacement_score >= 70
                                ? '#00FF41'
                                : d.displacement_score >= 50
                                ? '#FFB800'
                                : '#888',
                          }}
                        >
                          {d.displacement_score.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        <span
                          className={`text-[10px] font-bold tracking-wider ${
                            d.expected_direction === 'bullish'
                              ? 'text-terminal-green'
                              : 'text-terminal-red'
                          }`}
                        >
                          {d.expected_direction === 'bullish' ? '▲ BULL' : '▼ BEAR'}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-center text-[10px] text-terminal-dim tracking-wider">
                        {ORDER_TYPE_LABELS[d.order_type] || d.order_type}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-amber">
                        {d.expected_magnitude.toFixed(1)}%
                      </td>
                      <td
                        className="py-2.5 px-2 text-right font-mono"
                        style={{
                          color:
                            d.actual_price_change_1d != null
                              ? d.actual_price_change_1d > 0
                                ? '#00FF41'
                                : '#FF073A'
                              : '#555',
                        }}
                      >
                        {d.actual_price_change_1d != null
                          ? `${d.actual_price_change_1d > 0 ? '+' : ''}${d.actual_price_change_1d.toFixed(1)}%`
                          : '—'}
                      </td>
                      <td
                        className="py-2.5 px-2 text-right font-mono"
                        style={{
                          color:
                            d.actual_price_change_3d != null
                              ? d.actual_price_change_3d > 0
                                ? '#00FF41'
                                : '#FF073A'
                              : '#555',
                        }}
                      >
                        {d.actual_price_change_3d != null
                          ? `${d.actual_price_change_3d > 0 ? '+' : ''}${d.actual_price_change_3d.toFixed(1)}%`
                          : '—'}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[400px] whitespace-normal leading-relaxed">
                        {d.narrative}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alternative Data Tab */}
      {activeTab === 'alt' && (
        <div className="space-y-3">
          <div className="panel px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              ALTERNATIVE DATA SIGNALS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Physical-world signals that lead price by days to weeks
            </p>
          </div>
          {altData.length === 0 ? (
            <div className="panel px-4 py-8 text-center text-terminal-dim text-sm">
              No active alternative data signals. Run the pipeline to fetch them.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {altData.map((a, i) => (
                <div key={`${a.source}-${a.indicator}-${i}`} className="panel px-4 py-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">
                        {SOURCE_ICONS[a.source] || '📊'}
                      </span>
                      <div>
                        <div className="text-[11px] font-bold text-terminal-bright tracking-wider uppercase">
                          {a.source.replace(/_/g, ' ')}
                        </div>
                        <div className="text-[10px] text-terminal-dim">
                          {a.indicator.replace(/_/g, ' ')}
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className="text-lg font-display font-bold"
                        style={{
                          color:
                            a.signal_direction === 'bullish'
                              ? '#00FF41'
                              : a.signal_direction === 'bearish'
                              ? '#FF073A'
                              : '#FFB800',
                        }}
                      >
                        {a.signal_strength.toFixed(0)}
                      </div>
                      <div
                        className="text-[10px] font-bold tracking-wider"
                        style={{
                          color:
                            a.signal_direction === 'bullish'
                              ? '#00FF41'
                              : a.signal_direction === 'bearish'
                              ? '#FF073A'
                              : '#FFB800',
                        }}
                      >
                        {a.signal_direction.toUpperCase()}
                      </div>
                    </div>
                  </div>
                  <p className="text-[11px] text-terminal-text leading-relaxed">
                    {a.narrative}
                  </p>
                  <div className="mt-2 text-[10px] text-terminal-dim">
                    {a.date}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Sector Expert Tab */}
      {activeTab === 'expert' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              SECTOR EXPERT DISPLACEMENT SIGNALS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Where consensus is structurally wrong — domain expertise identifies the gap
            </p>
          </div>
          {experts.length === 0 ? (
            <div className="px-4 py-8 text-center text-terminal-dim text-sm">
              No sector expert signals. Run the pipeline to generate them.
            </div>
          ) : (
            <div className="divide-y divide-terminal-border/50">
              {experts.map((e, i) => (
                <div
                  key={`${e.symbol}-${e.expert_type}-${i}`}
                  className="px-4 py-3 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                  onClick={() => (window.location.href = `/asset/${e.symbol}`)}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-3">
                      <span className="font-mono font-bold text-terminal-bright text-sm">
                        {e.symbol}
                      </span>
                      <span className="text-[10px] text-terminal-dim tracking-wider uppercase">
                        {e.expert_type}
                      </span>
                      <span
                        className={`text-[10px] font-bold tracking-wider ${
                          e.direction === 'bullish'
                            ? 'text-terminal-green'
                            : e.direction === 'bearish'
                            ? 'text-terminal-red'
                            : 'text-terminal-amber'
                        }`}
                      >
                        {e.direction.toUpperCase()}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span
                        className="px-2 py-0.5 rounded-sm text-[10px] font-bold tracking-wider"
                        style={{
                          backgroundColor:
                            e.conviction_level === 'high'
                              ? 'rgba(0,255,65,0.15)'
                              : e.conviction_level === 'medium'
                              ? 'rgba(255,184,0,0.15)'
                              : 'rgba(255,255,255,0.05)',
                          color:
                            e.conviction_level === 'high'
                              ? '#00FF41'
                              : e.conviction_level === 'medium'
                              ? '#FFB800'
                              : '#888',
                        }}
                      >
                        {e.conviction_level.toUpperCase()}
                      </span>
                      <span className="font-display font-bold text-terminal-text">
                        {e.sector_displacement_score.toFixed(0)}
                      </span>
                    </div>
                  </div>
                  <div className="text-[11px] text-terminal-dim mb-1">
                    <span className="text-terminal-text">Consensus:</span>{' '}
                    {e.consensus_narrative}
                  </div>
                  <div className="text-[11px]">
                    <span
                      className={
                        e.direction === 'bullish'
                          ? 'text-terminal-green'
                          : 'text-terminal-red'
                      }
                    >
                      Variant:
                    </span>{' '}
                    <span className="text-terminal-text">{e.variant_narrative}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
