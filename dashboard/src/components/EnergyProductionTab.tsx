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
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {/* US Production */}
        <div className="panel p-4">
          <div className="text-[9px] text-gray-500 tracking-wider uppercase mb-2">US Crude Production (Mb/d)</div>
          {production.production[0] && (
            <div className="text-2xl font-display font-bold text-gray-900 mb-3">{production.production[0].value.toFixed(1)}</div>
          )}
          <BarChart data={production.production.slice().reverse().slice(-26)} />
        </div>

        {/* Refinery Utilization */}
        <div className="panel p-4">
          <div className="text-[9px] text-gray-500 tracking-wider uppercase mb-2">Refinery Utilization (%)</div>
          {production.refinery_util[0] && (
            <div className="text-2xl font-display font-bold text-gray-900 mb-3">{production.refinery_util[0].value.toFixed(1)}%</div>
          )}
          <BarChart
            data={production.refinery_util.slice().reverse().slice(-26)}
            colorFn={(v) => `${v >= 92 ? '#059669' : v >= 85 ? '#d97706' : '#e11d48'}40`}
          />
        </div>

        {/* Product Supplied */}
        <div className="panel p-4">
          <div className="text-[9px] text-gray-500 tracking-wider uppercase mb-2">Total Product Supplied (Mb/d)</div>
          {production.product_supplied[0] && (
            <div className="text-2xl font-display font-bold text-gray-900 mb-3">{production.product_supplied[0].value.toFixed(1)}</div>
          )}
          <div className="h-24 flex items-end gap-[2px]">
            {production.product_supplied.slice().reverse().slice(-26).map((d, i) => {
              const vals = production.product_supplied.map(v => v.value);
              const mn = Math.min(...vals); const mx = Math.max(...vals); const range = mx - mn || 1;
              const pct = ((d.value - mn) / range) * 100;
              return <div key={i} className="flex-1 rounded-t bg-purple-500/30" {...cs({ height: `${Math.max(4, pct)}%` })} title={`${d.date}: ${d.value.toFixed(1)}`} />;
            })}
          </div>
        </div>

        {/* Crack Spread */}
        <div className="panel p-4">
          <div className="text-[9px] text-gray-500 tracking-wider uppercase mb-2">Crack Spread (Gasoline - WTI)</div>
          {production.crack_spread[0] && (
            <div className="text-2xl font-display font-bold text-gray-900 mb-3">${production.crack_spread[0].value.toFixed(2)}</div>
          )}
          <div className="h-24 flex items-end gap-[2px]">
            {production.crack_spread.slice().reverse().slice(-26).map((c, i) => {
              const vals = production.crack_spread.map(v => v.value);
              const mn = Math.min(...vals); const mx = Math.max(...vals); const range = mx - mn || 1;
              const pct = ((c.value - mn) / range) * 100;
              const color = c.value > 0 ? '#059669' : '#e11d48';
              return <div key={i} className="flex-1 rounded-t" {...cs({ height: `${Math.max(4, Math.abs(pct))}%`, backgroundColor: `${color}40` })} title={`${c.date}: $${c.value.toFixed(2)}`} />;
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
