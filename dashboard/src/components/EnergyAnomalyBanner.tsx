import type { EnergyAnomaly } from '@/lib/api';

const severityStyles: Record<string, { border: string; badge: string }> = {
  critical: { border: 'border-l-[3px] border-l-[#e11d48]', badge: 'bg-[#e11d4820] text-[#e11d48]' },
  high: { border: 'border-l-[3px] border-l-[#f97316]', badge: 'bg-[#f9731620] text-[#f97316]' },
  medium: { border: 'border-l-[3px] border-l-[#d97706]', badge: 'bg-[#d9770620] text-[#d97706]' },
  low: { border: 'border-l-[3px] border-l-[#3b82f6]', badge: 'bg-[#3b82f620] text-[#3b82f6]' },
};

const defaultStyle = { border: 'border-l-[3px] border-l-[#d97706]', badge: 'bg-[#d9770620] text-[#d97706]' };

export function EnergyAnomalyBanner({ anomalies }: { anomalies: EnergyAnomaly[] }) {
  if (!anomalies.length) return null;

  return (
    <div className="space-y-2 mb-4">
      {anomalies.map((a, i) => {
        const s = severityStyles[a.severity] || defaultStyle;
        return (
          <div key={i} className={`panel p-3 flex items-start gap-3 ${s.border}`}>
            <span className={`text-[10px] tracking-widest font-bold px-1.5 py-0.5 rounded shrink-0 ${s.badge}`}>
              {a.severity.toUpperCase()}
            </span>
            <div>
              <div className="text-xs text-gray-700">{a.description}</div>
              <div className="text-[10px] text-gray-500 mt-0.5">
                z-score: {a.zscore != null ? a.zscore.toFixed(2) : '—'} | Affected: {a.affected_tickers}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
