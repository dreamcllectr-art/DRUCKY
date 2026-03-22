import { cs } from '@/lib/styles';

export function EnergyScoreBar({ score, label }: { score: number; label?: string }) {
  const colorClass = score >= 65 ? 'text-[#059669]' : score >= 45 ? 'text-[#d97706]' : 'text-[#e11d48]';
  const bgClass = score >= 65 ? 'bg-[#059669]' : score >= 45 ? 'bg-[#d97706]' : 'bg-[#e11d48]';
  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-[10px] text-gray-500 w-16 uppercase">{label}</span>}
      <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${bgClass}`}
          {...cs({ width: `${score}%` })}
        />
      </div>
      <span className={`text-xs font-mono w-8 text-right ${colorClass}`}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}
