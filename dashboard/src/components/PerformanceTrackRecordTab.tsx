import type { TrackRecordMonth } from '@/lib/api';
import { cs } from '@/lib/styles';

function wrColor(wr: number | null) {
  if (wr == null) return 'text-gray-500';
  return wr >= 50 ? 'text-[#059669]' : 'text-[#e11d48]';
}

function retColor(val: number | null | undefined) {
  if (val == null) return 'text-gray-500';
  return val > 0 ? 'text-[#059669]' : 'text-[#e11d48]';
}

export function PerformanceTrackRecordTab({ data }: { data: TrackRecordMonth[] }) {
  if (!data.length) {
    return (
      <div className="panel p-8 text-center text-gray-500">
        No track record data yet. Run the pipeline daily to accumulate signal outcomes.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="panel p-4">
        <h3 className="text-xs text-gray-500 tracking-[0.2em] uppercase mb-4">CUMULATIVE WIN RATE OVER TIME</h3>
        <div className="flex items-end gap-1 h-32">
          {data.map((d) => {
            const height = Math.max(4, (d.cumulative_win_rate / 100) * 100);
            const barColor = d.cumulative_win_rate >= 55 ? 'bg-[#059669]/70' : d.cumulative_win_rate >= 45 ? 'bg-[#d97706]/70' : 'bg-[#e11d48]/70';
            return (
              <div key={d.month} className="flex-1 flex flex-col items-center gap-1 group relative">
                <div className="text-[9px] text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity">{d.cumulative_win_rate.toFixed(1)}%</div>
                <div className={`w-full rounded-t transition-all duration-500 ${barColor}`} {...cs({ height: `${height}%` })} />
                <div className="text-[8px] text-gray-500 -rotate-45 origin-top-left mt-1 whitespace-nowrap">{d.month}</div>
              </div>
            );
          })}
        </div>
        <div className="flex justify-between text-[9px] text-gray-500 mt-6"><span>0%</span><span>50%</span><span>100%</span></div>
      </div>

      <div className="panel p-4">
        <h3 className="text-xs text-gray-500 tracking-[0.2em] uppercase mb-4">MONTHLY SIGNAL BREAKDOWN</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-gray-500 tracking-wider">
              <th className="text-left pb-2">MONTH</th>
              <th className="text-right pb-2">SIGNALS</th>
              <th className="text-right pb-2">5D WIN%</th>
              <th className="text-right pb-2">5D AVG</th>
              <th className="text-right pb-2">20D WIN%</th>
              <th className="text-right pb-2">20D AVG</th>
              <th className="text-right pb-2">CUM WIN%</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => {
              const wr5 = d.resolved_5d > 0 ? ((d.wins_5d || 0) / d.resolved_5d * 100) : null;
              const wr20 = d.resolved_20d > 0 ? ((d.wins_20d || 0) / d.resolved_20d * 100) : null;
              return (
                <tr key={d.month} className="border-t border-gray-200">
                  <td className="py-2 font-display text-gray-700">{d.month}</td>
                  <td className="py-2 text-right font-mono text-gray-500">{d.total_signals}</td>
                  <td className={`py-2 text-right font-mono ${wrColor(wr5)}`}>{wr5 != null ? `${wr5.toFixed(0)}%` : '\u2014'}</td>
                  <td className={`py-2 text-right font-mono ${retColor(d.avg_5d)}`}>{d.avg_5d != null ? `${d.avg_5d > 0 ? '+' : ''}${d.avg_5d.toFixed(2)}%` : '\u2014'}</td>
                  <td className={`py-2 text-right font-mono ${wrColor(wr20)}`}>{wr20 != null ? `${wr20.toFixed(0)}%` : '\u2014'}</td>
                  <td className={`py-2 text-right font-mono ${retColor(d.avg_20d)}`}>{d.avg_20d != null ? `${d.avg_20d > 0 ? '+' : ''}${d.avg_20d.toFixed(2)}%` : '\u2014'}</td>
                  <td className={`py-2 text-right font-mono ${d.cumulative_win_rate >= 50 ? 'text-[#059669]' : 'text-[#e11d48]'}`}>{d.cumulative_win_rate.toFixed(1)}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
