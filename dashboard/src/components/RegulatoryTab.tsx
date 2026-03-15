'use client';
import { useEffect, useState } from 'react';
import { api, RegulatorySignal, RegulatoryEvent } from '@/lib/api';

function scoreColor(score: number) { return score >= 60 ? 'text-green-400' : score >= 40 ? 'text-amber-400' : 'text-red-400'; }

export default function RegulatoryTab() {
  const [signals, setSignals] = useState<RegulatorySignal[]>([]);
  const [events, setEvents] = useState<RegulatoryEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'signals' | 'events'>('signals');

  useEffect(() => {
    Promise.all([api.regulatorySignals(0, 14), api.regulatoryEvents(undefined, undefined, undefined, 1, 14)]).then(([s, e]) => { setSignals(s); setEvents(e); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading regulatory data...</div>;

  const headwindCount = signals.filter(s => s.reg_score < 45).length;
  const tailwindCount = signals.filter(s => s.reg_score > 55).length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white border border-gray-200 rounded-lg p-3"><div className="text-xs text-gray-500 uppercase">Headwinds</div><div className="text-2xl font-bold text-red-400">{headwindCount}</div></div>
        <div className="bg-white border border-gray-200 rounded-lg p-3"><div className="text-xs text-gray-500 uppercase">Tailwinds</div><div className="text-2xl font-bold text-green-400">{tailwindCount}</div></div>
        <div className="bg-white border border-gray-200 rounded-lg p-3"><div className="text-xs text-gray-500 uppercase">Events</div><div className="text-2xl font-bold text-amber-400">{events.length}</div></div>
      </div>
      <div className="flex gap-1 border-b border-gray-200">
        {[{ key: 'signals' as const, label: 'SIGNALS' }, { key: 'events' as const, label: 'EVENTS' }].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} className={`px-4 py-2 text-sm rounded-t transition-colors ${tab === t.key ? 'bg-green-500/20 text-green-400 border-b-2 border-green-400' : 'text-gray-500 hover:text-gray-600'}`}>{t.label}</button>
        ))}
      </div>
      {tab === 'signals' && (
        <div className="space-y-1">
          {signals.length === 0 ? <div className="text-center py-10 text-gray-600">No signals</div> : signals.sort((a, b) => Math.abs(b.reg_score - 50) - Math.abs(a.reg_score - 50)).slice(0, 50).map(s => (
            <div key={`${s.symbol}-${s.date}`} className="grid grid-cols-[1fr_80px_80px_1fr] gap-2 px-3 py-2 border-b border-gray-200/50 hover:bg-white/30 text-sm">
              <a href={`/asset/${s.symbol}`} className="font-bold text-gray-900 hover:text-green-400">{s.symbol}</a>
              <span className={`text-right font-mono ${scoreColor(s.reg_score)}`}>{s.reg_score.toFixed(1)}</span>
              <span className="text-right text-gray-500">{s.event_count} events</span>
              <span className="text-gray-500 text-xs truncate">{s.narrative}</span>
            </div>
          ))}
        </div>
      )}
      {tab === 'events' && (
        <div className="space-y-1">
          {events.length === 0 ? <div className="text-center py-10 text-gray-600">No events</div> : events.map(ev => (
            <div key={ev.event_id} className="grid grid-cols-[40px_1fr_100px_80px] gap-2 px-3 py-2 border-b border-gray-200/50 hover:bg-white/30 text-sm">
              <span className={`font-bold ${ev.severity >= 4 ? 'text-red-400' : ev.severity >= 3 ? 'text-amber-400' : 'text-gray-500'}`}>{ev.severity}</span>
              <span className="text-gray-900 truncate">{ev.title}</span>
              <span className="text-xs text-cyan-400 truncate">{ev.impact_category?.replace('ai_', '')}</span>
              <span className={ev.direction === 'headwind' ? 'text-red-400' : ev.direction === 'tailwind' ? 'text-green-400' : 'text-amber-400'}>{ev.direction}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
