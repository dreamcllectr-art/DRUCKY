'use client';

import type { EconomicIndicator } from '@/lib/api';

interface Props {
  indicator: EconomicIndicator;
  isExpanded: boolean;
  onToggle: () => void;
}

const signalColor: Record<string, string> = {
  bullish: '#00FF41',
  neutral: '#FFB800',
  bearish: '#FF073A',
};

const trendArrow: Record<string, string> = {
  improving: '▲',
  stable: '▶',
  deteriorating: '▼',
};

const trendColor: Record<string, string> = {
  improving: 'text-terminal-green',
  stable: 'text-terminal-amber',
  deteriorating: 'text-terminal-red',
};

function formatValue(val: number | null, indicator_id: string): string {
  if (val === null || val === undefined) return '—';
  // Large numbers (payrolls, balance sheet, etc.)
  if (Math.abs(val) >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (Math.abs(val) >= 10_000) return `${(val / 1_000).toFixed(1)}K`;
  if (Math.abs(val) >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
  // Small numbers (rates, percentages, indices)
  if (Math.abs(val) < 10) return val.toFixed(2);
  return val.toFixed(1);
}

function formatPct(val: number | null): string {
  if (val === null || val === undefined) return '—';
  const sign = val > 0 ? '+' : '';
  return `${sign}${val.toFixed(1)}%`;
}

export default function EconIndicatorRow({ indicator, isExpanded, onToggle }: Props) {
  const { indicator_id, name, value, mom_change, yoy_change, zscore, trend, signal } = indicator;
  const color = signalColor[signal] || '#FFB800';

  // Z-score bar: normalized to [-3, +3] range, centered at 50%
  const zNorm = zscore !== null ? Math.max(-3, Math.min(3, zscore)) : 0;
  const barLeft = 50; // center
  const barWidth = (Math.abs(zNorm) / 3) * 50;
  const barStart = zNorm >= 0 ? barLeft : barLeft - barWidth;

  return (
    <tr
      className="border-b border-terminal-border/30 hover:bg-terminal-green/5 cursor-pointer transition-colors"
      onClick={onToggle}
    >
      {/* Signal dot */}
      <td className="py-3 pl-4 pr-2">
        <div
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: color, boxShadow: `0 0 6px ${color}60` }}
        />
      </td>

      {/* Name */}
      <td className="py-3 pr-4">
        <div className="text-xs text-terminal-bright font-medium">{name}</div>
        <div className="text-[9px] text-terminal-dim mt-0.5 uppercase tracking-wider">
          {indicator.category}
        </div>
      </td>

      {/* Value */}
      <td className="py-3 px-3 text-right font-mono text-xs text-terminal-text">
        {formatValue(value, indicator_id)}
      </td>

      {/* MoM */}
      <td className={`py-3 px-3 text-right font-mono text-[11px] ${
        mom_change !== null && mom_change > 0 ? 'text-terminal-green' :
        mom_change !== null && mom_change < 0 ? 'text-terminal-red' : 'text-terminal-dim'
      }`}>
        {formatPct(mom_change)}
      </td>

      {/* YoY */}
      <td className={`py-3 px-3 text-right font-mono text-[11px] ${
        yoy_change !== null && yoy_change > 0 ? 'text-terminal-green' :
        yoy_change !== null && yoy_change < 0 ? 'text-terminal-red' : 'text-terminal-dim'
      }`}>
        {formatPct(yoy_change)}
      </td>

      {/* Z-Score Bar */}
      <td className="py-3 px-3">
        <div className="relative h-3 bg-terminal-border/30 rounded-full overflow-hidden w-24">
          {/* Center tick */}
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-terminal-dim/40" />
          {/* Bar */}
          {zscore !== null && (
            <div
              className="absolute top-0 bottom-0 rounded-full transition-all duration-700"
              style={{
                left: `${barStart}%`,
                width: `${Math.max(2, barWidth)}%`,
                background: color,
                boxShadow: `0 0 4px ${color}40`,
              }}
            />
          )}
        </div>
        <div className="text-[9px] text-terminal-dim text-center mt-0.5 font-mono">
          {zscore !== null ? `${zscore > 0 ? '+' : ''}${zscore.toFixed(1)}σ` : '—'}
        </div>
      </td>

      {/* Trend */}
      <td className={`py-3 px-3 text-center text-xs ${trendColor[trend] || 'text-terminal-dim'}`}>
        <span className="text-sm">{trendArrow[trend] || '—'}</span>
        <div className="text-[9px] mt-0.5">{trend}</div>
      </td>

      {/* Expand arrow */}
      <td className="py-3 pr-4 text-terminal-dim text-xs">
        {isExpanded ? '▾' : '▸'}
      </td>
    </tr>
  );
}
