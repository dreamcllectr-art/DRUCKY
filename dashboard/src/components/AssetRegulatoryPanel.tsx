import type { RegulatorySignal, RegulatoryEvent } from '@/lib/api';

interface RegulatoryPanelProps {
  signals: RegulatorySignal[];
  events: RegulatoryEvent[];
}

export function AssetRegulatoryPanel({ signals, events }: RegulatoryPanelProps) {
  if (signals.length === 0) return null;

  const sig = signals[0];
  const dirLabel = sig.reg_score > 55 ? 'TAILWIND' : sig.reg_score < 45 ? 'HEADWIND' : 'NEUTRAL';
  const dirBadgeColor = sig.reg_score > 55 ? 'text-emerald-600 bg-emerald-600/10' : sig.reg_score < 45 ? 'text-rose-600 bg-rose-600/10' : 'text-amber-600 bg-amber-600/10';
  const sc = sig.reg_score >= 60 ? 'text-[#059669]' : sig.reg_score >= 40 ? 'text-[#d97706]' : 'text-[#e11d48]';
  const sBg = sig.reg_score >= 60 ? 'bg-[#05966915]' : sig.reg_score >= 40 ? 'bg-[#d9770615]' : 'bg-[#e11d4815]';

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-gray-500 tracking-widest uppercase">AI Regulatory Risk</span>
          <span className={`px-2 py-0.5 rounded-lg text-[9px] font-bold ${dirBadgeColor}`}>{dirLabel}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-gray-500">{sig.event_count} event{sig.event_count !== 1 ? 's' : ''}</span>
          <span className={`text-xl font-display font-bold px-2 py-0.5 rounded-lg ${sc} ${sBg}`}>{sig.reg_score.toFixed(0)}</span>
        </div>
      </div>
      {sig.narrative && <p className="text-[11px] text-gray-500 leading-relaxed mb-4">{sig.narrative}</p>}
      {events.length > 0 && (
        <div className="space-y-2">
          <div className="text-[9px] text-gray-500 tracking-widest uppercase">CONTRIBUTING EVENTS</div>
          {events.slice(0, 5).map((ev, i) => {
            const sevColor = ev.severity >= 4 ? 'text-[#e11d48] bg-[#e11d4815]' : ev.severity >= 3 ? 'text-[#d97706] bg-[#d9770615]' : ev.severity >= 2 ? 'text-[#2563eb] bg-[#2563eb12]' : 'text-[#6b7280] bg-gray-50';
            return (
              <div key={`reg-ev-${i}`} className="flex items-start gap-3 py-2 border-b border-gray-200/30 last:border-0">
                <span className={`px-1.5 py-0.5 rounded-lg text-[10px] font-bold shrink-0 mt-0.5 ${sevColor}`}>{ev.severity}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[11px] text-gray-700 truncate">
                    {ev.url ? <a href={ev.url} target="_blank" rel="noopener noreferrer" className="hover:text-emerald-600 transition-colors">{ev.title}</a> : ev.title}
                  </div>
                  {ev.rationale && <div className="text-[9px] text-gray-500 mt-0.5 truncate">{ev.rationale}</div>}
                </div>
                <div className={`text-[10px] font-bold shrink-0 ${ev.direction === 'tailwind' ? 'text-emerald-600' : ev.direction === 'headwind' ? 'text-rose-600' : 'text-amber-600'}`}>
                  {ev.direction?.toUpperCase() || '\u2014'}
                </div>
              </div>
            );
          })}
          {events.length > 5 && (
            <a href="/regulatory" className="block text-[10px] text-blue-600 hover:text-emerald-600 transition-colors mt-2">VIEW ALL {events.length} EVENTS &rarr;</a>
          )}
        </div>
      )}
    </div>
  );
}
