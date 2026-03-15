import type { EnergyInventory } from '@/lib/api';
import { cs, bgFg } from '@/lib/styles';

export function EnergyInventoryCard({ inv }: { inv: EnergyInventory }) {
  const isDrawColor = inv.draw_build === 'DRAW' ? '#059669' : inv.draw_build === 'BUILD' ? '#e11d48' : '#d97706';
  const vsAvg =
    inv.seasonal_avg != null ? ((inv.value - inv.seasonal_avg) / inv.seasonal_avg) * 100 : null;

  return (
    <div className="panel p-4">
      <div className="text-[9px] text-gray-500 tracking-wider uppercase mb-1">{inv.name}</div>
      <div className="flex items-baseline gap-3 mb-2">
        <span className="text-2xl font-display font-bold text-gray-900">
          {(inv.value / 1000).toFixed(1)}
          <span className="text-xs text-gray-500 ml-1">M bbl</span>
        </span>
        {inv.wow_change != null && (
          <span
            className="text-xs font-mono px-1.5 py-0.5 rounded"
            {...bgFg(`${isDrawColor}15`, isDrawColor)}
          >
            {inv.wow_change > 0 ? '+' : ''}
            {(inv.wow_change / 1000).toFixed(1)}M
          </span>
        )}
      </div>
      {inv.draw_build && (
        <span
          className="text-[10px] tracking-widest font-bold px-2 py-0.5 rounded"
          {...bgFg(`${isDrawColor}20`, isDrawColor)}
        >
          {inv.draw_build}
        </span>
      )}
      {vsAvg != null && (
        <div className="mt-2 text-[10px] text-gray-500">
          vs 5yr avg: <span className={vsAvg < 0 ? 'text-green-400' : 'text-red-400'}>{vsAvg > 0 ? '+' : ''}{vsAvg.toFixed(1)}%</span>
        </div>
      )}
      {inv.seasonal_min != null && inv.seasonal_max != null && (
        <div className="mt-2">
          <div className="relative h-1 bg-gray-200 rounded-full">
            <div className="absolute h-full bg-gray-400/20 rounded-full left-0 w-full" />
            {inv.seasonal_min < inv.seasonal_max && (
              <div
                className="absolute top-[-2px] bottom-[-2px] w-1 rounded-full bg-gray-900"
                {...cs({
                  left: `${Math.max(0, Math.min(100, ((inv.value - inv.seasonal_min) / (inv.seasonal_max - inv.seasonal_min)) * 100))}%`,
                })}
              />
            )}
          </div>
          <div className="flex justify-between text-[8px] text-gray-500 mt-0.5">
            <span>{(inv.seasonal_min / 1000).toFixed(0)}M</span>
            <span>{(inv.seasonal_max / 1000).toFixed(0)}M</span>
          </div>
        </div>
      )}
    </div>
  );
}
