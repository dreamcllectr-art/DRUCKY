import type { WeightHistoryEntry } from '@/lib/api';
import { cs } from '@/lib/styles';

export function PerformanceWeightsTab({ history }: { history: WeightHistoryEntry[] }) {
  if (!history.length) {
    return (
      <div className="panel p-8 text-center text-gray-500">
        <div className="text-lg mb-2">Adaptive weights not yet active</div>
        <div className="text-sm">The optimizer needs {'>'}100 resolved signals and {'>'}30 days of data before adjusting weights.</div>
      </div>
    );
  }

  const latest = history[0];

  return (
    <div className="space-y-6">
      <div className="panel p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs text-gray-500 tracking-[0.2em] uppercase">LATEST WEIGHT UPDATE -- {latest.date}</h3>
          <div className="text-xs text-gray-500">Total delta: <span className="text-emerald-600">{latest.total_delta.toFixed(4)}</span></div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {latest.modules.sort((a, b) => b.weight - a.weight).map((m) => {
            const delta = m.weight - m.prior_weight;
            const barWidth = m.weight * 100 * 4;
            const deltaColor = delta > 0.001 ? 'text-[#059669]' : delta < -0.001 ? 'text-[#e11d48]' : 'text-gray-500';
            const barBg = delta > 0.001 ? 'bg-[#059669]' : delta < -0.001 ? 'bg-[#e11d48]' : 'bg-[#05966980]';
            return (
              <div key={m.module_name} className="flex items-center gap-2 py-1">
                <div className="w-28 text-xs text-gray-700 truncate">{m.module_name}</div>
                <div className="flex-1 h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full transition-all duration-700 ${barBg}`} {...cs({ width: `${Math.min(100, barWidth)}%` })} />
                </div>
                <div className="w-14 text-right text-xs font-mono text-gray-700">{(m.weight * 100).toFixed(1)}%</div>
                <div className={`w-14 text-right text-xs font-mono ${deltaColor}`}>{delta > 0.001 ? '+' : ''}{(delta * 100).toFixed(1)}%</div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="panel p-4">
        <h3 className="text-xs text-gray-500 tracking-[0.2em] uppercase mb-4">WEIGHT UPDATE HISTORY</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-gray-500 tracking-wider">
              <th className="text-left pb-2">DATE</th>
              <th className="text-right pb-2">TOTAL DELTA</th>
              <th className="text-right pb-2">MODULES</th>
              <th className="text-left pb-2 pl-4">TOP CHANGES</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => {
              const topChanges = h.modules
                .filter((m) => Math.abs(m.weight - m.prior_weight) > 0.001)
                .sort((a, b) => Math.abs(b.weight - b.prior_weight) - Math.abs(a.weight - a.prior_weight))
                .slice(0, 3);
              return (
                <tr key={h.date} className="border-t border-gray-200">
                  <td className="py-2 font-display text-gray-700">{h.date}</td>
                  <td className="py-2 text-right font-mono text-emerald-600">{h.total_delta.toFixed(4)}</td>
                  <td className="py-2 text-right font-mono text-gray-500">{h.modules.length}</td>
                  <td className="py-2 pl-4 text-xs text-gray-500">
                    {topChanges.map((m) => { const d = m.weight - m.prior_weight; return `${m.module_name} ${d > 0 ? '+' : ''}${(d * 100).toFixed(1)}%`; }).join(', ') || 'No changes'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
