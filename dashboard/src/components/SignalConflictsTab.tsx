'use client';
import { useEffect, useState, useMemo } from 'react';
import { api, type SignalConflict, type ConflictSummary } from '@/lib/api';
import Link from 'next/link';
import { cs, fg } from '@/lib/styles';

const severityColor = (s: string) => (s === 'critical' || s === 'CRITICAL') ? '#e11d48' : (s === 'high' || s === 'HIGH') ? '#ea580c' : (s === 'medium' || s === 'MEDIUM') ? '#d97706' : '#9ca3af';
const severityBg = (s: string) => (s === 'critical' || s === 'CRITICAL') ? 'rgba(225,29,72,0.08)' : (s === 'high' || s === 'HIGH') ? 'rgba(251,146,60,0.08)' : 'rgba(217,119,6,0.06)';

export default function SignalConflictsTab() {
  const [conflicts, setConflicts] = useState<SignalConflict[]>([]);
  const [summary, setSummary] = useState<ConflictSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([api.signalConflicts(), api.signalConflictsSummary()]).then(([c, s]) => {
      if (c.status === 'fulfilled') setConflicts(c.value);
      if (s.status === 'fulfilled') setSummary(s.value);
      setLoading(false);
    });
  }, []);

  const symbolGroups = useMemo(() => {
    const map = new Map<string, SignalConflict[]>();
    conflicts.forEach(c => { const arr = map.get(c.symbol) || []; arr.push(c); map.set(c.symbol, arr); });
    return Array.from(map.entries()).sort((a, b) => b[1].length - a[1].length).slice(0, 30);
  }, [conflicts]);

  const stats = useMemo(() => ({
    total: conflicts.length,
    critical: conflicts.filter(c => c.severity === 'critical' || c.severity === 'CRITICAL').length,
    high: conflicts.filter(c => c.severity === 'high' || c.severity === 'HIGH').length,
    symbols: new Set(conflicts.map(c => c.symbol)).size,
  }), [conflicts]);

  if (loading) return <div className="text-gray-400 animate-pulse py-8 text-center text-sm">Analyzing inter-module signal conflicts...</div>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-white border border-gray-200 rounded p-3"><div className="text-[9px] text-gray-500 tracking-widest opacity-50">TOTAL</div><div className="text-[18px] font-bold font-mono text-gray-700 mt-1">{stats.total}</div></div>
        <div className="bg-white border border-[rgba(225,29,72,0.15)] rounded p-3"><div className="text-[9px] text-gray-500 tracking-widest opacity-50">CRITICAL</div><div className="text-[18px] font-bold font-mono mt-1 text-[#e11d48]">{stats.critical}</div></div>
        <div className="bg-white border border-[rgba(251,146,60,0.15)] rounded p-3"><div className="text-[9px] text-gray-500 tracking-widest opacity-50">HIGH</div><div className="text-[18px] font-bold font-mono mt-1 text-[#ea580c]">{stats.high}</div></div>
        <div className="bg-white border border-gray-200 rounded p-3"><div className="text-[9px] text-gray-500 tracking-widest opacity-50">SYMBOLS</div><div className="text-[18px] font-bold font-mono text-gray-700 mt-1">{stats.symbols}</div></div>
      </div>
      <div className="space-y-2">
        {symbolGroups.length === 0 && <div className="text-center py-16 text-emerald-600 text-sm">All signals aligned — no inter-module conflicts detected</div>}
        {symbolGroups.map(([symbol, sc]) => (
          <div key={symbol}>
            <button onClick={() => setExpandedSymbol(expandedSymbol === symbol ? null : symbol)} className="w-full text-left bg-white border border-gray-200 rounded p-3 transition-all">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Link href={`/asset/${symbol}`} className="text-[13px] font-bold text-[#059669] hover:underline" onClick={e => e.stopPropagation()}>{symbol}</Link>
                  <span className="text-[9px] font-bold tracking-widest px-2 py-0.5 rounded" {...cs({ background: severityBg(sc[0].severity), color: severityColor(sc[0].severity), border: `1px solid ${severityColor(sc[0].severity)}30` })}>{sc[0].severity.toUpperCase()}</span>
                  <span className="text-[10px] text-gray-500">{sc.length} conflict{sc.length > 1 ? 's' : ''}</span>
                </div>
                <span className="text-gray-500 text-[10px]">{expandedSymbol === symbol ? '\u25BE' : '\u25B8'}</span>
              </div>
            </button>
            {expandedSymbol === symbol && <div className="mt-1 space-y-1">{sc.map((c, i) => (
              <div key={i} className="bg-gray-50 border border-gray-200 rounded p-3">
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-[9px] text-gray-500 tracking-wider">{c.conflict_type.replace(/_/g, ' ').toUpperCase()}</span>
                  <span className="text-[8px] tracking-widest" {...fg(severityColor(c.severity))}>{c.severity.toUpperCase()}</span>
                </div>
                <div className="flex items-center gap-4 text-[10px]">
                  <span className="text-gray-700">{c.module_a}: <span className="font-mono text-[#059669]">{c.module_a_score.toFixed(0)}</span></span>
                  <span className="font-mono font-bold text-amber-600">{c.score_gap.toFixed(0)}pt gap</span>
                  <span className="text-gray-700">{c.module_b}: <span className="font-mono text-[#e11d48]">{c.module_b_score.toFixed(0)}</span></span>
                </div>
                {c.description && <p className="text-[10px] text-gray-500 opacity-60 mt-1">{c.description}</p>}
              </div>
            ))}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
