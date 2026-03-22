'use client';
import { useEffect, useState } from 'react';
import { api, type MASignal, type MARumor } from '@/lib/api';
import { scorePillSty } from '@/lib/styles';

export default function MATab() {
  const [signals, setSignals] = useState<MASignal[]>([]);
  const [rumors, setRumors] = useState<MARumor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'targets' | 'rumors'>('targets');

  useEffect(() => {
    Promise.all([api.maTopTargets(), api.maRumors(30)]).then(([s, r]) => { setSignals(s); setRumors(r); }).catch((e) => setError(e.message || 'Failed to load M&A data')).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading M&A data...</div>;

  return (
    <div className="space-y-4">
      {error && (
        <div className="panel p-4 border-rose-200 bg-rose-50">
          <div className="text-rose-600 text-sm font-bold mb-1">Failed to load data</div>
          <p className="text-[11px] text-gray-500">{error}</p>
        </div>
      )}
      <div className="grid grid-cols-3 gap-3">
        <div onClick={() => setTab('targets')} className={`panel px-4 py-3 cursor-pointer transition-all ${tab === 'targets' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-emerald-600">{signals.filter(s => s.ma_score >= 50).length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">HIGH M&A SCORE</div></div>
        <div onClick={() => setTab('rumors')} className={`panel px-4 py-3 cursor-pointer transition-all ${tab === 'rumors' ? 'border-emerald-600/50' : 'hover:border-gray-300'}`}><div className="text-2xl font-display font-bold text-amber-600">{rumors.length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">ACTIVE RUMORS</div></div>
        <div className="panel px-4 py-3"><div className="text-2xl font-display font-bold text-blue-600">{signals.filter(s => s.deal_stage === 'definitive').length}</div><div className="text-[10px] text-gray-500 tracking-widest mt-1">DEFINITIVE DEALS</div></div>
      </div>
      {tab === 'targets' && (
        <div className="panel overflow-hidden"><div className="px-4 py-3 border-b border-gray-200"><h2 className="text-xs text-gray-900 tracking-widest font-bold">TOP M&A TARGETS</h2></div>
          <div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">Score</th><th className="text-center py-3 px-2 font-normal">Stage</th><th className="text-right py-3 px-2 font-normal">Premium</th><th className="text-left py-3 px-4 font-normal">Acquirer</th></tr></thead>
            <tbody>{signals.length === 0 ? <tr><td colSpan={5} className="text-center py-8 text-gray-500">No M&A signals.</td></tr> : signals.map((s, i) => (
              <tr key={`ma-${s.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03] cursor-pointer" onClick={() => (window.location.href = `/asset/${s.symbol}`)}>
                <td className="py-2.5 px-4 font-mono font-bold text-emerald-600">{s.symbol}{s.company_name && <span className="ml-2 text-[10px] text-gray-500">{s.company_name}</span>}</td>
                <td className="py-2.5 px-2 text-right"><span className="px-1.5 py-0.5 rounded-lg text-[10px] font-bold" {...scorePillSty(s.ma_score)}>{s.ma_score.toFixed(0)}</span></td>
                <td className="py-2.5 px-2 text-center">{s.deal_stage && <span className={`px-1.5 py-0.5 rounded-lg text-[10px] font-bold uppercase ${s.deal_stage === 'definitive' ? 'bg-emerald-600/15 text-emerald-600' : 'bg-amber-600/15 text-amber-600'}`}>{s.deal_stage}</span>}</td>
                <td className="py-2.5 px-2 text-right font-mono text-blue-600">{s.expected_premium_pct ? `+${s.expected_premium_pct.toFixed(0)}%` : '--'}</td>
                <td className="py-2.5 px-4 text-gray-500 max-w-[250px] truncate">{s.acquirer_name || s.narrative || '--'}</td>
              </tr>))}</tbody></table></div>
        </div>
      )}
      {tab === 'rumors' && (
        <div className="panel overflow-hidden"><div className="px-4 py-3 border-b border-gray-200"><h2 className="text-xs text-gray-900 tracking-widest font-bold">M&A RUMOR TRACKER</h2></div>
          <div className="overflow-x-auto"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-left py-3 px-2 font-normal">Date</th><th className="text-center py-3 px-2 font-normal">Credibility</th><th className="text-left py-3 px-4 font-normal">Headline</th></tr></thead>
            <tbody>{rumors.length === 0 ? <tr><td colSpan={4} className="text-center py-8 text-gray-500">No rumors.</td></tr> : rumors.map((r, i) => (
              <tr key={`rum-${r.symbol}-${i}`} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03]">
                <td className="py-2.5 px-4 font-mono font-bold text-amber-600">{r.symbol}</td>
                <td className="py-2.5 px-2 font-mono text-gray-500 text-[10px]">{r.date}</td>
                <td className="py-2.5 px-2 text-center"><span className={`px-1.5 py-0.5 rounded-lg text-[10px] font-bold ${(r.credibility_score || 0) >= 7 ? 'bg-emerald-600/15 text-emerald-600' : 'bg-amber-600/15 text-amber-600'}`}>{r.credibility_score || '--'}/10</span></td>
                <td className="py-2.5 px-4 text-gray-500 max-w-[400px] truncate">{r.rumor_headline || '--'}</td>
              </tr>))}</tbody></table></div>
        </div>
      )}
    </div>
  );
}
