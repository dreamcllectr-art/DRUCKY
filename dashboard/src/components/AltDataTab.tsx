'use client';
import { useEffect, useState } from 'react';
import { api, type AltDataSignal } from '@/lib/api';
import { bgFg } from '@/lib/styles';

export default function AltDataTab() {
  const [signals, setSignals] = useState<AltDataSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState<string>('all');

  useEffect(() => {
    api.altData(30).then(setSignals).catch(() => setSignals([])).finally(() => setLoading(false));
  }, []);

  const sources = [...new Set(signals.map(s => s.source))];
  const filtered = sourceFilter === 'all' ? signals : signals.filter(s => s.source === sourceFilter);
  const dirColor = (dir: string) => dir === 'bullish' ? 'text-emerald-600' : dir === 'bearish' ? 'text-rose-600' : 'text-amber-600';
  const strengthColor = (v: number) => v >= 70 ? { bg: 'rgba(5,150,105,0.15)', fg: '#059669' } : v >= 40 ? { bg: 'rgba(217,119,6,0.15)', fg: '#d97706' } : { bg: 'rgba(243,244,246,1)', fg: '#6b7280' };

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading alt data...</div>;

  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        <button onClick={() => setSourceFilter('all')} className={`px-3 py-1.5 rounded text-[10px] tracking-widest font-bold transition-all ${sourceFilter === 'all' ? 'bg-emerald-600/15 text-emerald-600 border border-emerald-600/30' : 'bg-white text-gray-500 border border-gray-200'}`}>ALL ({signals.length})</button>
        {sources.map(src => (
          <button key={src} onClick={() => setSourceFilter(src)} className={`px-3 py-1.5 rounded text-[10px] tracking-widest font-bold transition-all ${sourceFilter === src ? 'bg-emerald-600/15 text-emerald-600 border border-emerald-600/30' : 'bg-white text-gray-500 border border-gray-200'}`}>{src.toUpperCase()} ({signals.filter(s => s.source === src).length})</button>
        ))}
      </div>
      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase">
              <th className="text-left py-3 px-4 font-normal">Date</th><th className="text-left py-3 px-2 font-normal">Indicator</th><th className="text-right py-3 px-2 font-normal">Value</th><th className="text-center py-3 px-2 font-normal">Direction</th><th className="text-right py-3 px-2 font-normal">Strength</th><th className="text-left py-3 px-4 font-normal">Narrative</th>
            </tr></thead>
            <tbody>
              {filtered.length === 0 ? <tr><td colSpan={6} className="text-center py-8 text-gray-500">No signals.</td></tr> : filtered.map((s, i) => {
                const sc = strengthColor(s.signal_strength);
                return (
                  <tr key={`alt-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03]">
                    <td className="py-2.5 px-4 font-mono text-gray-500 text-[10px]">{s.date}</td>
                    <td className="py-2.5 px-2 text-gray-700 text-[10px]">{s.indicator}</td>
                    <td className="py-2.5 px-2 text-right font-mono text-gray-900">{s.value?.toFixed(2) || '--'}</td>
                    <td className={`py-2.5 px-2 text-center font-bold text-[10px] ${dirColor(s.signal_direction)}`}>{s.signal_direction.toUpperCase()}</td>
                    <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...bgFg(sc.bg, sc.fg)}>{s.signal_strength.toFixed(0)}</span></td>
                    <td className="py-2.5 px-4 text-gray-500 max-w-[300px] truncate">{s.narrative || '--'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
