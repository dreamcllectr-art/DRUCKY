'use client';
import { useEffect, useState } from 'react';
import { api, type WorldviewSignal, type WorldviewThesis } from '@/lib/api';
import { scorePillSty } from '@/lib/styles';

export default function WorldviewTab() {
  const [signals, setSignals] = useState<WorldviewSignal[]>([]);
  const [theses, setTheses] = useState<WorldviewThesis[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'expressions' | 'theses'>('expressions');

  useEffect(() => {
    Promise.all([api.worldview().catch(() => []), api.worldviewTheses().catch(() => [])]).then(([s, t]) => { setSignals(s); setTheses(t); setLoading(false); });
  }, []);

  if (loading) return <div className="text-gray-400 animate-pulse py-8 text-center text-sm">Evaluating thesis alignment and sector tilts...</div>;

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-gray-200">
        {[{ key: 'expressions' as const, label: `EXPRESSIONS (${signals.length})` }, { key: 'theses' as const, label: `THESES (${theses.length})` }].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} className={`px-4 py-2 text-[10px] tracking-widest ${tab === t.key ? 'text-emerald-600 border-b-2 border-emerald-600' : 'text-gray-500 hover:text-gray-700'}`}>{t.label}</button>
        ))}
      </div>
      {tab === 'expressions' && (
        <div className="panel overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">Alignment</th><th className="text-left py-3 px-2 font-normal">Sector Tilt</th><th className="text-left py-3 px-4 font-normal">Narrative</th></tr></thead>
          <tbody>{signals.length === 0 ? <tr><td colSpan={4} className="text-center py-8 text-gray-400">No thesis-aligned expressions identified in the current regime.</td></tr> : signals.map((s, i) => (
            <tr key={`wv-${s.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${s.symbol}`)}>
              <td className="py-2.5 px-4 font-mono font-bold text-emerald-600">{s.symbol}</td>
              <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(s.thesis_alignment_score || 0, [60, 50])}>{s.thesis_alignment_score?.toFixed(0) || '--'}</span></td>
              <td className="py-2.5 px-2 text-blue-600 text-[10px]">{s.sector_tilt || '--'}</td>
              <td className="py-2.5 px-4 text-gray-500 max-w-[300px] truncate">{s.narrative || '--'}</td>
            </tr>))}</tbody></table></div>
        </div>
      )}
      {tab === 'theses' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {theses.length === 0 ? <div className="col-span-full text-center py-8 text-gray-400">No active investment theses configured.</div> : theses.map((t, i) => (
            <div key={`thesis-${i}`} className="panel px-4 py-3">
              <div className="text-xs font-bold text-amber-600 tracking-wider uppercase">{t.active_theses.replace(/_/g, ' ')}</div>
              <div className="flex items-center gap-4 mt-2 text-[10px]"><span className="text-blue-600">Sector: {t.sector_tilt}</span><span className="text-gray-500">{t.stock_count} stocks</span><span className="text-emerald-600">Avg: {t.avg_alignment.toFixed(0)}</span></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
