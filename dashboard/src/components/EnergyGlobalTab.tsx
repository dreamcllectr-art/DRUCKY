import type { JodiRecord, EnergyBalance } from '@/lib/api';
import { fg, bgFg } from '@/lib/styles';

interface GlobalTabProps {
  globalBalance: {
    jodi_data: JodiRecord[];
    balance: EnergyBalance | null;
    global_stocks: { country: string; value: number; mom_change: number | null }[];
  };
}

export function EnergyGlobalTab({ globalBalance }: GlobalTabProps) {
  return (
    <div className="space-y-4">
      {globalBalance.balance && (
        <div className="panel p-6">
          <div className="text-[9px] text-gray-500 tracking-wider uppercase mb-2">Global Supply-Demand Balance (JODI)</div>
          <div className="grid grid-cols-3 gap-6">
            <div>
              <div className="text-[9px] text-gray-500 uppercase mb-1">Production</div>
              <span className="text-2xl font-display font-bold text-gray-900">
                {globalBalance.balance.production_total_kbd.toFixed(0)}<span className="text-xs text-gray-500 ml-1">kbd</span>
              </span>
            </div>
            <div>
              <div className="text-[9px] text-gray-500 uppercase mb-1">Demand</div>
              <span className="text-2xl font-display font-bold text-gray-900">
                {globalBalance.balance.demand_total_kbd.toFixed(0)}<span className="text-xs text-gray-500 ml-1">kbd</span>
              </span>
            </div>
            <div>
              <div className="text-[9px] text-gray-500 uppercase mb-1">Balance</div>
              <span className="text-2xl font-display font-bold" {...fg(globalBalance.balance.balance === 'DEFICIT' ? '#059669' : '#e11d48')}>
                {globalBalance.balance.surplus_kbd > 0 ? '+' : ''}{globalBalance.balance.surplus_kbd.toFixed(0)}<span className="text-xs ml-1">kbd</span>
              </span>
              <span className="ml-2 text-[10px] tracking-widest font-bold px-2 py-0.5 rounded"
                {...bgFg(
                  globalBalance.balance.balance === 'DEFICIT' ? '#05966920' : '#e11d4820',
                  globalBalance.balance.balance === 'DEFICIT' ? '#059669' : '#e11d48',
                )}
              >
                {globalBalance.balance.balance}
              </span>
            </div>
          </div>
        </div>
      )}

      {globalBalance.jodi_data.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="p-4 border-b border-gray-200">
            <h3 className="text-xs tracking-widest text-gray-500 uppercase">Country-Level Data (JODI)</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-gray-200 text-[9px] text-gray-500 tracking-widest uppercase">
                  <th className="text-left px-4 py-2">Country</th>
                  <th className="text-left px-4 py-2">Indicator</th>
                  <th className="text-right px-4 py-2">Value</th>
                  <th className="text-right px-4 py-2">Unit</th>
                  <th className="text-right px-4 py-2">MoM</th>
                  <th className="text-right px-4 py-2">YoY</th>
                </tr>
              </thead>
              <tbody>
                {globalBalance.jodi_data.map((j, i) => (
                  <tr key={i} className="border-b border-gray-200/30">
                    <td className="px-4 py-2 text-gray-700">{j.country}</td>
                    <td className="px-4 py-2 text-gray-500 capitalize">{j.indicator}</td>
                    <td className="px-4 py-2 text-right font-mono text-gray-900">{j.value?.toFixed(0)}</td>
                    <td className="px-4 py-2 text-right text-gray-500">{j.unit}</td>
                    <td className="px-4 py-2 text-right font-mono">
                      {j.mom_change != null && (
                        <span className={j.mom_change > 0 ? 'text-[#059669]' : 'text-[#e11d48]'}>
                          {j.mom_change > 0 ? '+' : ''}{j.mom_change.toFixed(0)}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">
                      {j.yoy_change != null && (
                        <span className={j.yoy_change > 0 ? 'text-[#059669]' : 'text-[#e11d48]'}>
                          {j.yoy_change > 0 ? '+' : ''}{j.yoy_change.toFixed(0)}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {globalBalance.global_stocks.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="p-4 border-b border-gray-200">
            <h3 className="text-xs tracking-widest text-gray-500 uppercase">Global Oil Stocks by Country</h3>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[9px] text-gray-500 tracking-widest uppercase">
                <th className="text-left px-4 py-2">Country</th>
                <th className="text-right px-4 py-2">Stocks</th>
                <th className="text-right px-4 py-2">MoM Change</th>
              </tr>
            </thead>
            <tbody>
              {globalBalance.global_stocks.map((s, i) => (
                <tr key={i} className="border-b border-gray-200/30">
                  <td className="px-4 py-2 text-gray-700">{s.country}</td>
                  <td className="px-4 py-2 text-right font-mono text-gray-900">{s.value?.toFixed(0)}</td>
                  <td className="px-4 py-2 text-right font-mono">
                    {s.mom_change != null && (
                      <span className={s.mom_change < 0 ? 'text-[#059669]' : 'text-[#e11d48]'}>
                        {s.mom_change > 0 ? '+' : ''}{s.mom_change.toFixed(0)}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {globalBalance.jodi_data.length === 0 && !globalBalance.balance && (
        <div className="panel p-8 text-center text-gray-500 text-xs">
          No JODI data available yet. Run the pipeline to fetch international oil statistics.
        </div>
      )}
    </div>
  );
}
