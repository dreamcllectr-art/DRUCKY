import type { MacroData, Breadth, HeatIndex } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import { cs } from '@/lib/styles';

function regimeClass(regime: string) {
  if (regime.includes('strong_risk_on')) return 'regime-strong-risk-on';
  if (regime.includes('risk_on')) return 'regime-risk-on';
  if (regime.includes('strong_risk_off')) return 'regime-strong-risk-off';
  if (regime.includes('risk_off')) return 'regime-risk-off';
  return 'regime-neutral';
}

interface CommandStripProps {
  macro: MacroData | null;
  breadth: Breadth | null;
  heatIndex: HeatIndex | null;
  summary: { signal: string; count: number }[];
}

export function HomeCommandStrip({ macro, breadth, heatIndex, summary }: CommandStripProps) {
  return (
    <div className="flex items-center gap-4 flex-wrap">
      {macro && (
        <div className={regimeClass(macro.regime)}>
          {macro.regime.replace(/_/g, ' ').toUpperCase()}
          <span className="ml-2 opacity-70">{macro.total_score.toFixed(0)}</span>
        </div>
      )}

      {breadth && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500 tracking-wider">BREADTH</span>
          <div className="w-24 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                breadth.pct_above_200dma > 50 ? 'bg-[#059669]' : 'bg-[#e11d48]'
              }`}
              {...cs({ width: `${breadth.pct_above_200dma}%` })}
            />
          </div>
          <span className={`text-[10px] font-mono ${breadth.pct_above_200dma > 50 ? 'text-emerald-600' : 'text-rose-600'}`}>
            {breadth.pct_above_200dma.toFixed(0)}%
          </span>
        </div>
      )}

      {heatIndex && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gray-500 tracking-wider">HEAT</span>
          <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                heatIndex.heat_index > 10 ? 'bg-[#059669]' : heatIndex.heat_index > -10 ? 'bg-[#d97706]' : 'bg-[#e11d48]'
              }`}
              {...cs({ width: `${Math.min(100, Math.max(0, (heatIndex.heat_index + 100) / 2))}%` })}
            />
          </div>
          <span className={`text-[10px] font-mono ${
            heatIndex.heat_index > 10 ? 'text-emerald-600' :
            heatIndex.heat_index > -10 ? 'text-amber-600' : 'text-rose-600'
          }`}>
            {heatIndex.heat_index > 0 ? '+' : ''}{heatIndex.heat_index.toFixed(1)}
          </span>
        </div>
      )}

      <div className="flex-1" />

      <div className="flex gap-3">
        {summary.map(s => (
          <div key={s.signal} className="flex items-center gap-1.5">
            <SignalBadge signal={s.signal} size="sm" />
            <span className="text-[11px] font-mono text-gray-700 font-bold">{s.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
