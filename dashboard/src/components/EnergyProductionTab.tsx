import type { EnergyProductionData } from '@/lib/api';
import { cs } from '@/lib/styles';

function BarChart({ data, colorFn }: { data: { date: string; value: number }[]; colorFn?: (v: number) => string }) {
  const vals = data.map(v => v.value);
  const mn = Math.min(...vals);
  const mx = Math.max(...vals);
  const range = mx - mn || 1;

  return (
    <div className="h-24 flex items-end gap-[2px]">
      {data.map((p, i) => {
        const pct = ((p.value - mn) / range) * 100;
        const color = colorFn ? colorFn(p.value) : undefined;
        return (
          <div
            key={i}
            className={`flex-1 rounded-t ${!color ? 'bg-blue-500/30' : ''}`}
            {...cs({
              height: `${Math.max(4, pct)}%`,
              ...(color ? { backgroundColor: color } : {}),
            })}
            title={`${p.date}: ${p.value.toFixed(1)}`}
          />
        );
      })}
    </div>
  );
}

export function EnergyProductionTab({ production }: { production: EnergyProductionData }) {
  const prod = production?.production ?? [];
  const refUtil = production?.refinery_util ?? [];
  const prodSupplied = production?.product_supplied ?? [];
  const crack = production?.crack_spread ?? [];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* US Production */}
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-2">US Crude Production (Mb/d)</div>
          {prod[0] && (
            <div className="text-2xl font-display font-bold text-gray-900 mb-3">{prod[0].value.toFixed(1)}</div>
          )}
          {prod.length > 0 ? <BarChart data={prod.slice().reverse().slice(-26)} /> : <div className="text-xs text-gray-400">No production data available</div>}
        </div>

        {/* Refinery Utilization */}
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-2">Refinery Utilization (%)</div>
          {refUtil[0] && (
            <div className="text-2xl font-display font-bold text-gray-900 mb-3">{refUtil[0].value.toFixed(1)}%</div>
          )}
          {refUtil.length > 0 ? (
            <BarChart
              data={refUtil.slice().reverse().slice(-26)}
              colorFn={(v) => `${v >= 92 ? '#059669' : v >= 85 ? '#d97706' : '#e11d48'}40`}
            />
          ) : <div className="text-xs text-gray-400">No refinery utilization data available</div>}
        </div>

        {/* Product Supplied */}
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-2">Total Product Supplied (Mb/d)</div>
          {prodSupplied[0] && (
            <div className="text-2xl font-display font-bold text-gray-900 mb-3">{prodSupplied[0].value.toFixed(1)}</div>
          )}
          {prodSupplied.length > 0 ? (
            <div className="h-24 flex items-end gap-[2px]">
              {prodSupplied.slice().reverse().slice(-26).map((d, i) => {
                const vals = prodSupplied.map(v => v.value);
                const mn = Math.min(...vals); const mx = Math.max(...vals); const range = mx - mn || 1;
                const pct = ((d.value - mn) / range) * 100;
                return <div key={i} className="flex-1 rounded-t bg-purple-500/30" {...cs({ height: `${Math.max(4, pct)}%` })} title={`${d.date}: ${d.value.toFixed(1)}`} />;
              })}
            </div>
          ) : <div className="text-xs text-gray-400">No product supplied data available</div>}
        </div>

        {/* Crack Spread */}
        <div className="panel p-4">
          <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-2">Crack Spread (Gasoline - WTI)</div>
          {crack[0] && (
            <div className="text-2xl font-display font-bold text-gray-900 mb-3">${crack[0].value.toFixed(2)}</div>
          )}
          {crack.length > 0 ? (
            <div className="h-24 flex items-end gap-[2px]">
              {crack.slice().reverse().slice(-26).map((c, i) => {
                const vals = crack.map(v => v.value);
                const mn = Math.min(...vals); const mx = Math.max(...vals); const range = mx - mn || 1;
                const pct = ((c.value - mn) / range) * 100;
                const color = c.value > 0 ? '#059669' : '#e11d48';
                return <div key={i} className="flex-1 rounded-t" {...cs({ height: `${Math.max(4, Math.abs(pct))}%`, backgroundColor: `${color}40` })} title={`${c.date}: $${c.value.toFixed(2)}`} />;
              })}
            </div>
          ) : <div className="text-xs text-gray-400">No crack spread data available</div>}
        </div>
      </div>
    </div>
  );
}
