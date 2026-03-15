'use client';
import { useEffect, useState } from 'react';
import { api, type AIExecSignal, type AIExecConvergence } from '@/lib/api';
import { scorePillSty } from '@/lib/styles';

export default function AIExecTab() {
  const [signals, setSignals] = useState<AIExecSignal[]>([]);
  const [convergence, setConvergence] = useState<AIExecConvergence[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'signals' | 'convergence'>('signals');

  useEffect(() => {
    Promise.all([api.aiExecSignals(0, 180), api.aiExecConvergence()]).then(([s, c]) => { setSignals(s); setConvergence(c); }).catch((e) => setError(e.message || 'Failed to load AI exec data')).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading AI exec data...</div>;

  return (
    <div className="space-y-4">
      {error && (
        <div className="panel p-4 border-rose-200 bg-rose-50">
          <div className="text-rose-600 text-sm font-bold mb-1">Failed to load data</div>
          <p className="text-[11px] text-gray-500">{error}</p>
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        <div onClick={() => setTab('signals')} className={`panel px-4 py-3 cursor-pointer transition-all ${tab === 'signals' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-emerald-600">{signals.filter(s => s.ai_exec_score >= 50).length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">HIGH SCORE</div></div>
        <div onClick={() => setTab('convergence')} className={`panel px-4 py-3 cursor-pointer transition-all ${tab === 'convergence' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-blue-600">{convergence.length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">MULTI-EXEC</div></div>
        <div className="panel px-4 py-3"><div className="text-2xl font-display font-bold text-gray-500">{signals.length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">TOTAL SIGNALS</div></div>
      </div>
      {tab === 'signals' && (
        <div className="panel overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">Score</th><th className="text-right py-3 px-2 font-normal">Execs</th><th className="text-left py-3 px-2 font-normal">Top Exec</th><th className="text-left py-3 px-4 font-normal">Narrative</th></tr></thead>
          <tbody>{signals.length === 0 ? <tr><td colSpan={5} className="text-center py-8 text-gray-500">No signals.</td></tr> : signals.map((s, i) => (
            <tr key={`${s.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${s.symbol}`)}>
              <td className="py-2.5 px-4 font-mono font-bold text-emerald-600">{s.symbol}</td>
              <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(s.ai_exec_score)}>{s.ai_exec_score.toFixed(0)}</span></td>
              <td className="py-2.5 px-2 text-right font-mono text-gray-900">{s.exec_count}</td>
              <td className="py-2.5 px-2 text-gray-700 text-[10px]">{s.top_exec || '--'}</td>
              <td className="py-2.5 px-4 text-gray-500 max-w-[300px] truncate">{s.narrative}</td>
            </tr>))}</tbody></table></div>
        </div>
      )}
      {tab === 'convergence' && (
        <div className="panel overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Company</th><th className="text-left py-3 px-2 font-normal">Ticker</th><th className="text-right py-3 px-2 font-normal">Execs</th><th className="text-left py-3 px-2 font-normal">Who</th><th className="text-right py-3 px-2 font-normal">Score</th></tr></thead>
          <tbody>{convergence.length === 0 ? <tr><td colSpan={5} className="text-center py-8 text-gray-500">No multi-exec convergence.</td></tr> : convergence.map((c, i) => (
            <tr key={`conv-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => c.target_ticker && (window.location.href = `/asset/${c.target_ticker}`)}>
              <td className="py-2.5 px-4 text-gray-900 font-bold">{c.target_company}</td>
              <td className="py-2.5 px-2 font-mono text-emerald-600">{c.target_ticker || 'PRIVATE'}</td>
              <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold bg-blue-600/15 text-blue-600">{c.exec_count}</span></td>
              <td className="py-2.5 px-2 text-gray-700 text-[10px] max-w-[250px] truncate">{c.executives}</td>
              <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(c.max_score)}>{c.max_score.toFixed(0)}</span></td>
            </tr>))}</tbody></table></div>
        </div>
      )}
    </div>
  );
}
