'use client';

import React, { useEffect, useState } from 'react';
import { api, type EconomicIndicator, type HeatIndex, type IndicatorHistoryPoint } from '@/lib/api';
import EconIndicatorRow from '@/components/EconIndicatorRow';
import EconomicChart from '@/components/EconomicChart';

const CATEGORIES = [
  { key: 'leading', label: 'LEADING', count: 12, desc: 'Predict where the economy is heading' },
  { key: 'coincident', label: 'COINCIDENT', count: 4, desc: 'Confirm current economic state' },
  { key: 'lagging', label: 'LAGGING', count: 5, desc: 'Confirm established trends' },
  { key: 'liquidity', label: 'LIQUIDITY', count: 2, desc: 'Financial system stress & liquidity' },
];

// Threshold lines for specific indicators
const THRESHOLD_CONFIG: Record<string, { value: number; color: string; label?: string }[]> = {
  SAHMREALTIME: [{ value: 0.5, color: '#FF073A80', label: 'Recession' }],
  T10Y3M: [{ value: 0, color: '#FF073A60', label: 'Inversion' }],
  NFCI: [{ value: 0, color: '#FFB80060', label: 'Neutral' }],
  STLFSI4: [{ value: 0, color: '#FFB80060', label: 'Neutral' }],
  UNRATE: [{ value: 4.0, color: '#FFB80040', label: '~NAIRU' }],
};

function HeatGauge({ score }: { score: number }) {
  // -100 to +100 mapped to 0-100% position
  const pct = ((score + 100) / 200) * 100;
  const color = score > 20 ? '#00FF41' : score > -20 ? '#FFB800' : '#FF073A';
  const label = score > 40 ? 'EXPANSION' : score > 10 ? 'GROWTH' : score > -10 ? 'MIXED' : score > -40 ? 'SLOWING' : 'CONTRACTION';

  return (
    <div className="panel p-6">
      <div className="text-[10px] text-terminal-dim tracking-[0.2em] uppercase mb-2">
        Macro Heat Index
      </div>
      <div className="flex items-baseline gap-3 mb-4">
        <span className="text-4xl font-display font-bold" style={{ color }}>
          {score > 0 ? '+' : ''}{score.toFixed(0)}
        </span>
        <span
          className="text-xs font-display tracking-wider px-2 py-0.5 rounded"
          style={{ backgroundColor: `${color}20`, color }}
        >
          {label}
        </span>
      </div>
      {/* Gauge bar */}
      <div className="relative h-2 bg-terminal-border rounded-full overflow-hidden">
        <div
          className="absolute top-0 bottom-0 rounded-full transition-all duration-1000"
          style={{
            left: 0,
            width: `${Math.max(2, pct)}%`,
            background: `linear-gradient(90deg, #FF073A, #FFB800, #00FF41)`,
            opacity: 0.8,
          }}
        />
        {/* Needle */}
        <div
          className="absolute top-[-2px] bottom-[-2px] w-1 rounded-full transition-all duration-1000"
          style={{
            left: `${pct}%`,
            backgroundColor: color,
            boxShadow: `0 0 8px ${color}80`,
          }}
        />
      </div>
      <div className="flex justify-between text-[9px] text-terminal-dim mt-1">
        <span>CONTRACTION</span>
        <span>EXPANSION</span>
      </div>
    </div>
  );
}

function HeatMapTile({ indicator }: { indicator: EconomicIndicator }) {
  const colors: Record<string, { bg: string; text: string; glow: string }> = {
    bullish: { bg: '#00FF4115', text: '#00FF41', glow: '0 0 8px #00FF4120' },
    neutral: { bg: '#FFB80010', text: '#FFB800', glow: '0 0 8px #FFB80015' },
    bearish: { bg: '#FF073A15', text: '#FF073A', glow: '0 0 8px #FF073A20' },
  };
  const c = colors[indicator.signal] || colors.neutral;
  const trendArrow = indicator.trend === 'improving' ? '▲' : indicator.trend === 'deteriorating' ? '▼' : '▶';

  return (
    <div
      className="panel p-3 transition-all hover:scale-[1.02]"
      style={{ backgroundColor: c.bg, boxShadow: c.glow }}
    >
      <div className="text-[9px] text-terminal-dim tracking-wider uppercase truncate mb-1">
        {indicator.name}
      </div>
      <div className="flex items-baseline justify-between">
        <span className="text-lg font-display font-bold font-mono" style={{ color: c.text }}>
          {Math.abs(indicator.value) >= 1000
            ? `${(indicator.value / 1000).toFixed(1)}K`
            : indicator.value < 10
              ? indicator.value.toFixed(2)
              : indicator.value.toFixed(1)}
        </span>
        <span className="text-xs" style={{ color: c.text }}>{trendArrow}</span>
      </div>
      {indicator.zscore !== null && (
        <div className="text-[9px] font-mono mt-1" style={{ color: c.text }}>
          {indicator.zscore > 0 ? '+' : ''}{indicator.zscore.toFixed(1)}σ
        </div>
      )}
    </div>
  );
}

export default function EconomicDashboard() {
  const [indicators, setIndicators] = useState<EconomicIndicator[]>([]);
  const [heatIndex, setHeatIndex] = useState<HeatIndex | null>(null);
  const [activeTab, setActiveTab] = useState('leading');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [chartData, setChartData] = useState<IndicatorHistoryPoint[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.allSettled([
      api.economicIndicators(),
      api.heatIndex(),
    ]).then(([ind, heat]) => {
      if (ind.status === 'fulfilled') setIndicators(ind.value);
      else setError('No economic data. Run: python -m tools.fetch_macro && python -m tools.economic_dashboard');
      if (heat.status === 'fulfilled' && heat.value.heat_index !== undefined) setHeatIndex(heat.value);
    });
  }, []);

  const handleToggle = async (indicatorId: string) => {
    if (expandedId === indicatorId) {
      setExpandedId(null);
      setChartData([]);
      return;
    }
    setExpandedId(indicatorId);
    setChartLoading(true);
    try {
      const data = await api.indicatorHistory(indicatorId, 1095); // 3 years
      setChartData(data);
    } catch {
      setChartData([]);
    }
    setChartLoading(false);
  };

  if (error) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="panel p-8 text-center max-w-lg">
          <div className="text-terminal-green text-2xl mb-4 glow-green">◈</div>
          <p className="text-terminal-dim text-sm">{error}</p>
          <pre className="mt-4 text-[10px] text-terminal-green bg-terminal-bg p-3 rounded">
            source venv/bin/activate{'\n'}python -m tools.fetch_macro{'\n'}python -m tools.economic_dashboard
          </pre>
        </div>
      </div>
    );
  }

  if (!indicators.length) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green text-lg">LOADING INDICATORS...</div>
      </div>
    );
  }

  const leadingIndicators = indicators.filter(i => i.category === 'leading');
  const tabIndicators = indicators.filter(i => i.category === activeTab);
  const expandedIndicator = expandedId ? indicators.find(i => i.indicator_id === expandedId) : null;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
            ECONOMIC INDICATORS
          </h1>
          <p className="text-[10px] text-terminal-dim tracking-widest mt-1 uppercase">
            {indicators[0]?.date} · {indicators.length} indicators across {CATEGORIES.length} categories
          </p>
        </div>
        {heatIndex && (
          <div className="text-right">
            <div className="text-[10px] text-terminal-dim tracking-wider uppercase">Leading Indicators</div>
            <div className="flex gap-4 mt-1 text-xs">
              <span className="text-terminal-green">{heatIndex.improving_count} improving</span>
              <span className="text-terminal-amber">{heatIndex.stable_count} stable</span>
              <span className="text-terminal-red">{heatIndex.deteriorating_count} deteriorating</span>
            </div>
          </div>
        )}
      </div>

      {/* Heat Index Gauge + Trend Summary */}
      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2">
          {heatIndex ? (
            <HeatGauge score={heatIndex.heat_index} />
          ) : (
            <div className="panel p-6 text-terminal-dim text-sm">No heat index data yet</div>
          )}
        </div>
        <div className="panel p-6">
          <div className="text-[10px] text-terminal-dim tracking-[0.2em] uppercase mb-3">
            Trend Summary
          </div>
          {heatIndex && (
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-terminal-green">Improving</span>
                  <span className="text-terminal-green font-mono">{heatIndex.improving_count}/{heatIndex.leading_count}</span>
                </div>
                <div className="h-1.5 bg-terminal-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-terminal-green rounded-full transition-all duration-700"
                    style={{ width: `${(heatIndex.improving_count / Math.max(1, heatIndex.leading_count)) * 100}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-terminal-amber">Stable</span>
                  <span className="text-terminal-amber font-mono">{heatIndex.stable_count}/{heatIndex.leading_count}</span>
                </div>
                <div className="h-1.5 bg-terminal-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-terminal-amber rounded-full transition-all duration-700"
                    style={{ width: `${(heatIndex.stable_count / Math.max(1, heatIndex.leading_count)) * 100}%` }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-terminal-red">Deteriorating</span>
                  <span className="text-terminal-red font-mono">{heatIndex.deteriorating_count}/{heatIndex.leading_count}</span>
                </div>
                <div className="h-1.5 bg-terminal-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-terminal-red rounded-full transition-all duration-700"
                    style={{ width: `${(heatIndex.deteriorating_count / Math.max(1, heatIndex.leading_count)) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Leading Indicators Heat Map */}
      {leadingIndicators.length > 0 && (
        <div>
          <h2 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-3">
            Leading Indicators — At a Glance
          </h2>
          <div className="grid grid-cols-4 gap-3">
            {leadingIndicators.map(ind => (
              <HeatMapTile key={ind.indicator_id} indicator={ind} />
            ))}
          </div>
        </div>
      )}

      {/* Category Tabs */}
      <div>
        <div className="flex gap-1 mb-4">
          {CATEGORIES.map(cat => (
            <button
              key={cat.key}
              onClick={() => { setActiveTab(cat.key); setExpandedId(null); }}
              className={`px-4 py-2 text-[10px] tracking-[0.15em] uppercase font-display transition-colors rounded-t ${
                activeTab === cat.key
                  ? 'bg-terminal-green/10 text-terminal-green border border-terminal-green/20 border-b-0'
                  : 'text-terminal-dim hover:text-terminal-text hover:bg-terminal-green/5'
              }`}
            >
              {cat.label}
              <span className="ml-1.5 text-[9px] opacity-60">{cat.count}</span>
            </button>
          ))}
        </div>

        {/* Description */}
        <div className="text-[10px] text-terminal-dim mb-3 tracking-wide">
          {CATEGORIES.find(c => c.key === activeTab)?.desc}
        </div>

        {/* Indicator Table */}
        <div className="panel overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-terminal-border text-[9px] text-terminal-dim tracking-wider uppercase">
                <th className="py-2 pl-4 pr-2 w-6"></th>
                <th className="py-2 pr-4 text-left">Indicator</th>
                <th className="py-2 px-3 text-right">Value</th>
                <th className="py-2 px-3 text-right">MoM</th>
                <th className="py-2 px-3 text-right">YoY</th>
                <th className="py-2 px-3 text-center w-32">Z-Score</th>
                <th className="py-2 px-3 text-center">Trend</th>
                <th className="py-2 pr-4 w-6"></th>
              </tr>
            </thead>
            <tbody>
              {tabIndicators.map(ind => (
                <React.Fragment key={ind.indicator_id}>
                  <EconIndicatorRow
                    indicator={ind}
                    isExpanded={expandedId === ind.indicator_id}
                    onToggle={() => handleToggle(ind.indicator_id)}
                  />
                  {expandedId === ind.indicator_id && (
                    <tr>
                      <td colSpan={8} className="p-0">
                        <div className="px-4 py-3 bg-terminal-bg/50">
                          {chartLoading ? (
                            <div className="text-terminal-dim text-xs py-8 text-center animate-pulse">
                              Loading chart...
                            </div>
                          ) : chartData.length > 0 ? (
                            <EconomicChart
                              data={chartData}
                              name={expandedIndicator?.name || ''}
                              thresholdLines={THRESHOLD_CONFIG[ind.indicator_id]}
                              height={220}
                            />
                          ) : (
                            <div className="text-terminal-dim text-xs py-8 text-center">
                              No historical data available
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
