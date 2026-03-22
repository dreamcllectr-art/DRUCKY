import type { EnergySupplyData } from '@/lib/api';
import { EnergyInventoryCard } from '@/components/EnergyInventoryCard';
import { cs } from '@/lib/styles';

export function EnergySupplyTab({ supply }: { supply: EnergySupplyData }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {(supply.inventories ?? []).map((inv) => (
          <EnergyInventoryCard key={inv.series_id} inv={inv} />
        ))}
      </div>
      {supply.days_of_supply && (
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Days of Crude Supply</div>
          <span className="text-2xl font-display font-bold text-gray-900">
            {supply.days_of_supply.value.toFixed(1)}
            <span className="text-xs text-gray-500 ml-1">days</span>
          </span>
        </div>
      )}
      {(supply.crude_history ?? []).length > 0 && (
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-3">US Crude Stocks -- 12 Month Trend</div>
          <div className="h-40 flex items-end gap-[2px]">
            {(() => {
              const slice = (supply.crude_history ?? []).slice(-52);
              const vals = slice.map((v) => v.value);
              const mn = Math.min(...vals);
              const mx = Math.max(...vals);
              const range = mx - mn || 1;
              return slice.map((h, i) => {
                const pct = ((h.value - mn) / range) * 100;
                return (
                  <div
                    key={i}
                    className="flex-1 rounded-t bg-emerald-600/30 hover:bg-emerald-600/60 transition-colors"
                    {...cs({ height: `${Math.max(4, pct)}%` })}
                    title={`${h.date}: ${(h.value / 1000).toFixed(1)}M bbl`}
                  />
                );
              });
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
