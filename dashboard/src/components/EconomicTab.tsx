'use client';
import React, { useEffect, useState } from 'react';
import { api, type EconomicIndicator, type HeatIndex, type IndicatorHistoryPoint } from '@/lib/api';
import EconIndicatorRow from '@/components/EconIndicatorRow';
import EconomicChart from '@/components/EconomicChart';
import { fg } from '@/lib/styles';

const CATEGORIES = [
  { key: 'leading', label: 'LEADING', desc: 'Predict where the economy is heading' },
  { key: 'coincident', label: 'COINCIDENT', desc: 'Confirm current economic state' },
  { key: 'lagging', label: 'LAGGING', desc: 'Confirm established trends' },
  { key: 'liquidity', label: 'LIQUIDITY', desc: 'Financial system stress' },
];

const THRESHOLD_CONFIG: Record<string, { value: number; color: string; label?: string }[]> = {
  SAHMREALTIME: [{ value: 0.5, color: '#e11d4880', label: 'Recession' }],
  T10Y3M: [{ value: 0, color: '#e11d4860', label: 'Inversion' }],
};

export default function EconomicTab() {
  const [indicators, setIndicators] = useState<EconomicIndicator[]>([]);
  const [heatIndex, setHeatIndex] = useState<HeatIndex | null>(null);
  const [activeTab, setActiveTab] = useState('leading');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [chartData, setChartData] = useState<IndicatorHistoryPoint[]>([]);
  const [chartLoading, setChartLoading] = useState(false);

  useEffect(() => {
    Promise.allSettled([api.economicIndicators(), api.heatIndex()]).then(([ind, heat]) => {
      if (ind.status === 'fulfilled') setIndicators(ind.value);
      if (heat.status === 'fulfilled' && heat.value.heat_index !== undefined) setHeatIndex(heat.value);
    });
  }, []);

  const handleToggle = async (indicatorId: string) => {
    if (expandedId === indicatorId) { setExpandedId(null); setChartData([]); return; }
    setExpandedId(indicatorId); setChartLoading(true);
    try { setChartData(await api.indicatorHistory(indicatorId, 1095)); } catch { setChartData([]); }
    setChartLoading(false);
  };

  if (!indicators.length) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading indicators...</div>;

  const tabIndicators = indicators.filter(i => i.category === activeTab);
  const expandedIndicator = expandedId ? indicators.find(i => i.indicator_id === expandedId) : null;

  return (
    <div className="space-y-4">
      {heatIndex && (
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-widest uppercase mb-2">Macro Heat Index</div>
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-display font-bold" {...fg(heatIndex.heat_index > 20 ? '#059669' : heatIndex.heat_index > -20 ? '#d97706' : '#e11d48')}>{heatIndex.heat_index > 0 ? '+' : ''}{heatIndex.heat_index.toFixed(0)}</span>
            <div className="flex gap-4 text-xs"><span className="text-emerald-600">{heatIndex.improving_count} improving</span><span className="text-amber-600">{heatIndex.stable_count} stable</span><span className="text-rose-600">{heatIndex.deteriorating_count} deteriorating</span></div>
          </div>
        </div>
      )}
      <div className="flex gap-1 mb-4">
        {CATEGORIES.map(cat => (
          <button key={cat.key} onClick={() => { setActiveTab(cat.key); setExpandedId(null); }} className={`px-4 py-2 text-[10px] tracking-widest uppercase font-display transition-colors rounded-t ${activeTab === cat.key ? 'bg-emerald-600/10 text-emerald-600 border border-emerald-600/20 border-b-0' : 'text-gray-500 hover:text-gray-700'}`}>{cat.label}</button>
        ))}
      </div>
      <div className="panel overflow-hidden">
        <table className="w-full">
          <thead><tr className="border-b border-gray-200 text-[10px] text-gray-500 tracking-wider uppercase"><th className="py-2 pl-4 pr-2 w-6"></th><th className="py-2 pr-4 text-left">Indicator</th><th className="py-2 px-3 text-right">Value</th><th className="py-2 px-3 text-right">MoM</th><th className="py-2 px-3 text-center">Trend</th><th className="py-2 pr-4 w-6"></th></tr></thead>
          <tbody>
            {tabIndicators.map(ind => (
              <React.Fragment key={ind.indicator_id}>
                <EconIndicatorRow indicator={ind} isExpanded={expandedId === ind.indicator_id} onToggle={() => handleToggle(ind.indicator_id)} />
                {expandedId === ind.indicator_id && (
                  <tr><td colSpan={6} className="p-0"><div className="px-4 py-3 bg-gray-50/50">
                    {chartLoading ? <div className="text-gray-500 text-xs py-8 text-center animate-pulse">Loading chart...</div>
                      : chartData.length > 0 ? <EconomicChart data={chartData} name={expandedIndicator?.name || ''} thresholdLines={THRESHOLD_CONFIG[ind.indicator_id]} height={220} />
                      : <div className="text-gray-500 text-xs py-8 text-center">No historical data</div>}
                  </div></td></tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
