'use client';
import { useEffect, useState } from 'react';
import { api, type Signal } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import { fg } from '@/lib/styles';

export default function ScreenerTab() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [filtered, setFiltered] = useState<Signal[]>([]);
  const [signalFilter, setSignalFilter] = useState('All');
  const [sortBy, setSortBy] = useState('composite_score');
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.signals().then(d => { setSignals(d); setLoading(false); }).catch(() => setLoading(false)); }, []);

  useEffect(() => {
    let r = [...signals];
    if (signalFilter !== 'All') r = r.filter(s => s.signal === signalFilter);
    r.sort((a, b) => (b[sortBy as keyof Signal] as number ?? 0) - (a[sortBy as keyof Signal] as number ?? 0));
    setFiltered(r);
  }, [signals, signalFilter, sortBy]);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading screener...</div>;

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        {['STRONG BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG SELL'].map(sig => (
          <div key={sig} onClick={() => setSignalFilter(signalFilter === sig ? 'All' : sig)} className={`panel px-4 py-2 cursor-pointer transition-all ${signalFilter === sig ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}>
            <div className="text-xl font-display font-bold text-gray-700">{signals.filter(s => s.signal === sig).length}</div>
            <SignalBadge signal={sig} size="sm" />
          </div>
        ))}
      </div>
      <div className="flex gap-4 items-center">
        <select value={sortBy} onChange={e => setSortBy(e.target.value)} className="bg-white border border-gray-200 text-gray-700 text-[10px] tracking-wider px-3 py-1.5 rounded-lg">
          <option value="composite_score">COMPOSITE</option><option value="technical_score">TECHNICAL</option><option value="rr_ratio">R:R</option>
        </select>
        <span className="text-[10px] text-gray-500">{filtered.length} assets</span>
      </div>
      <div className="panel overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-center py-3 px-2 font-normal">Signal</th><th className="text-right py-3 px-2 font-normal">Composite</th><th className="text-right py-3 px-2 font-normal">Technical</th><th className="text-right py-3 px-2 font-normal">Entry</th><th className="text-right py-3 px-2 font-normal">R:R</th></tr></thead>
        <tbody>{filtered.slice(0, 100).map(s => (
          <tr key={s.symbol} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${s.symbol}`)}>
            <td className="py-2.5 px-4 font-mono font-bold text-gray-900">{s.symbol}</td>
            <td className="py-2.5 px-2 text-center"><SignalBadge signal={s.signal} size="sm" /></td>
            <td className="py-2.5 px-2 text-right font-mono text-gray-700">{s.composite_score.toFixed(1)}</td>
            <td className="py-2.5 px-2 text-right font-mono" {...fg(s.technical_score > 70 ? '#059669' : s.technical_score > 40 ? '#d97706' : '#e11d48')}>{s.technical_score.toFixed(1)}</td>
            <td className="py-2.5 px-2 text-right font-mono text-gray-700">${s.entry_price.toFixed(2)}</td>
            <td className="py-2.5 px-2 text-right font-mono text-amber-600">{s.rr_ratio.toFixed(1)}</td>
          </tr>))}</tbody></table></div>
      </div>
    </div>
  );
}
