import type { ConsensusBlindspotSignal } from '@/lib/api';
import { scoreColor } from '@/lib/modules';
import { fg } from '@/lib/styles';

function gapTypeBadge(gapType: string) {
  switch (gapType) {
    case 'contrarian_bullish':
      return { label: 'CONTRARIAN BULL', cls: 'bg-emerald-600/12 text-emerald-600 border-emerald-600/25' };
    case 'ahead_of_consensus':
      return { label: 'AHEAD OF STREET', cls: 'bg-blue-600/12 text-blue-600 border-blue-600/25' };
    case 'crowded_agreement':
      return { label: 'CROWDED', cls: 'bg-rose-600/12 text-rose-600 border-rose-600/25' };
    case 'contrarian_bearish_warning':
      return { label: 'BEARISH WARNING', cls: 'bg-rose-600/15 text-rose-600 border-rose-600/30' };
    default:
      return { label: gapType?.replace(/_/g, ' ').toUpperCase() || 'N/A', cls: 'bg-gray-400/10 text-gray-500 border-gray-400/20' };
  }
}

interface FatPitchesProps {
  fatPitches: ConsensusBlindspotSignal[];
}

export function HomeFatPitches({ fatPitches }: FatPitchesProps) {
  return (
    <div className="col-span-2 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xs text-gray-500 tracking-[0.2em] uppercase">Fat Pitches</h2>
        <a href="/consensus-blindspots" className="text-[10px] text-blue-600 hover:text-emerald-600 transition-colors">
          VIEW ALL &rarr;
        </a>
      </div>

      {fatPitches.length === 0 ? (
        <div className="panel p-6 text-center">
          <p className="text-gray-500 text-[11px]">No fat pitches detected today.</p>
          <p className="text-gray-500 text-[10px] mt-1">Extreme fear + undervaluation + smart money convergence = fat pitch</p>
        </div>
      ) : (
        <div className="space-y-2">
          {fatPitches.slice(0, 6).map((fp, idx) => {
            const badge = gapTypeBadge(fp.gap_type);
            const isTop = idx === 0 && fp.fat_pitch_count >= 3;
            return (
              <a
                key={fp.symbol}
                href={`/asset/${fp.symbol}`}
                className={`panel p-3 block hover:border-emerald-600/30 transition-colors group ${
                  isTop ? 'border-emerald-600/30' : ''
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold text-gray-900 text-sm group-hover:text-emerald-600 transition-colors">
                      {fp.symbol}
                    </span>
                    <span className={`text-[8px] px-1.5 py-0.5 rounded-lg font-bold border ${badge.cls}`}>
                      {badge.label}
                    </span>
                  </div>
                  <span className="text-lg font-display font-bold" {...fg(scoreColor(fp.cbs_score))}>
                    {fp.cbs_score.toFixed(0)}
                  </span>
                </div>

                <div className="flex items-center gap-2 mb-1">
                  <div className="flex gap-1">
                    {Array.from({ length: fp.fat_pitch_count || 0 }).map((_, i) => (
                      <div key={i} className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                    ))}
                    {Array.from({ length: Math.max(0, 4 - (fp.fat_pitch_count || 0)) }).map((_, i) => (
                      <div key={`e${i}`} className="w-1.5 h-1.5 rounded-full bg-gray-100" />
                    ))}
                  </div>
                  {fp.fat_pitch_conditions && (
                    <span className="text-[8px] text-gray-500 truncate">{fp.fat_pitch_conditions}</span>
                  )}
                </div>

                <div className="flex gap-3 text-[8px] text-gray-500">
                  {fp.short_interest_pct != null && (
                    <span>SI: <span className={fp.short_interest_pct > 10 ? 'text-amber-600' : ''}>{fp.short_interest_pct.toFixed(1)}%</span></span>
                  )}
                  {fp.analyst_buy_pct != null && <span>Buy: {fp.analyst_buy_pct.toFixed(0)}%</span>}
                  {fp.our_convergence_score != null && (
                    <span>Conv: <span className="text-emerald-600">{fp.our_convergence_score.toFixed(0)}</span></span>
                  )}
                </div>

                {fp.narrative && (
                  <p className="text-[8px] text-gray-500 mt-1 line-clamp-1">{fp.narrative}</p>
                )}
              </a>
            );
          })}
        </div>
      )}
    </div>
  );
}
