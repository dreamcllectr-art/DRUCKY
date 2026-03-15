'use client';
import { useEffect, useState } from 'react';
import { api, type DisplacementSignal } from '@/lib/api';
import { scorePillSty, fg } from '@/lib/styles';

export default function DisplacementTab() {
  const [displacements, setDisplacements] = useState<DisplacementSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.displacement().then(setDisplacements).catch((e) => setError(e.message || 'Failed to load displacement data')).finally(() => setLoading(false)); }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading displacements...</div>;

  return (
    <div className="panel overflow-hidden">
      {error && (
        <div className="panel p-4 border-rose-200 bg-rose-50">
          <div className="text-rose-600 text-sm font-bold mb-1">Failed to load data</div>
          <p className="text-[11px] text-gray-500">{error}</p>
        </div>
      )}
      <div className="px-4 py-3 border-b border-gray-200">
        <h2 className="text-xs text-gray-900 tracking-widest font-bold">NEWS DISPLACEMENT SIGNALS</h2>
        <p className="text-[10px] text-gray-500 mt-0.5">Material news + no price response = opportunity</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase">
            <th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">Score</th><th className="text-center py-3 px-2 font-normal">Direction</th><th className="text-right py-3 px-2 font-normal">Expected</th><th className="text-right py-3 px-2 font-normal">Actual 1d</th><th className="text-left py-3 px-4 font-normal">Narrative</th>
          </tr></thead>
          <tbody>
            {displacements.length === 0 ? <tr><td colSpan={6} className="text-center py-8 text-gray-500">No displacements.</td></tr> : displacements.map((d, i) => (
              <tr key={`${d.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${d.symbol}`)}>
                <td className="py-2.5 px-4 font-mono font-bold text-gray-900">{d.symbol}</td>
                <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(d.displacement_score)}>{d.displacement_score.toFixed(0)}</span></td>
                <td className={`py-2.5 px-2 text-center text-[10px] font-bold ${d.expected_direction === 'bullish' ? 'text-emerald-600' : 'text-rose-600'}`}>{d.expected_direction === 'bullish' ? 'BULL' : 'BEAR'}</td>
                <td className="py-2.5 px-2 text-right font-mono text-amber-600">{d.expected_magnitude.toFixed(1)}%</td>
                <td className="py-2.5 px-2 text-right font-mono" {...fg(d.actual_price_change_1d != null ? (d.actual_price_change_1d > 0 ? '#059669' : '#e11d48') : '#9ca3af')}>{d.actual_price_change_1d != null ? `${d.actual_price_change_1d > 0 ? '+' : ''}${d.actual_price_change_1d.toFixed(1)}%` : '--'}</td>
                <td className="py-2.5 px-4 text-gray-500 max-w-[300px] truncate">{d.narrative}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
