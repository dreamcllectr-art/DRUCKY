'use client';

import type { ConvergenceDelta, SignalChange } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import { scoreColor } from '@/lib/modules';
import { cs, fg } from '@/lib/styles';

interface Props {
  deltas: ConvergenceDelta[];
  signalChanges: SignalChange[];
}

export default function DailyDelta({ deltas, signalChanges }: Props) {
  const upgrades = deltas.filter(d => d.score_delta > 0);
  const downgrades = deltas.filter(d => d.score_delta < 0);

  // Signal upgrades (e.g., BUY → STRONG BUY)
  const signalUpgrades = signalChanges.filter(c => {
    const rank: Record<string, number> = { 'STRONG SELL': 0, 'SELL': 1, 'NEUTRAL': 2, 'BUY': 3, 'STRONG BUY': 4 };
    return (rank[c.new_signal] ?? 0) > (rank[c.old_signal] ?? 0);
  });
  const signalDowngrades = signalChanges.filter(c => {
    const rank: Record<string, number> = { 'STRONG SELL': 0, 'SELL': 1, 'NEUTRAL': 2, 'BUY': 3, 'STRONG BUY': 4 };
    return (rank[c.new_signal] ?? 0) < (rank[c.old_signal] ?? 0);
  });

  const hasChanges = upgrades.length > 0 || downgrades.length > 0 || signalChanges.length > 0;

  if (!hasChanges) {
    return (
      <div className="panel p-4 flex items-center justify-center gap-3">
        <div className="w-2 h-2 rounded-full bg-emerald-600/50" />
        <span className="text-[11px] text-gray-500 tracking-wider">
          NO MATERIAL CHANGES TODAY — SIGNALS STABLE
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse" />
        <h2 className="text-xs text-gray-500 tracking-[0.2em] uppercase">
          What Changed Today
        </h2>
        <span className="text-[9px] text-gray-500">
          {upgrades.length + signalUpgrades.length} up · {downgrades.length + signalDowngrades.length} down
        </span>
      </div>

      {/* Upgrades row */}
      {(upgrades.length > 0 || signalUpgrades.length > 0) && (
        <div className="overflow-x-auto scrollbar-hide">
          <div className="flex gap-2 pb-1" {...cs({ minWidth: 'min-content' })}>
            {/* Signal upgrades first */}
            {signalUpgrades.map(c => (
              <a
                key={`sig-${c.symbol}`}
                href={`/asset/${c.symbol}`}
                className="panel p-3 shrink-0 w-[170px] border-l-2 border-l-emerald-600 hover:border-emerald-600/40 transition-colors group"
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono font-bold text-sm text-gray-900 group-hover:text-emerald-600 transition-colors">
                    {c.symbol}
                  </span>
                  <span className="text-[8px] text-emerald-600 font-bold tracking-wider bg-emerald-600/10 px-1.5 py-0.5 rounded-lg">
                    UPGRADE
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-[9px]">
                  <span className="text-gray-500 line-through">{c.old_signal}</span>
                  <span className="text-emerald-600">→</span>
                  <SignalBadge signal={c.new_signal} size="sm" />
                </div>
              </a>
            ))}

            {/* Convergence score upgrades */}
            {upgrades.slice(0, 10).map(d => (
              <a
                key={`conv-${d.symbol}`}
                href={`/asset/${d.symbol}`}
                className="panel p-3 shrink-0 w-[170px] border-l-2 border-l-emerald-600/60 hover:border-emerald-600/40 transition-colors group"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono font-bold text-sm text-gray-900 group-hover:text-emerald-600 transition-colors">
                    {d.symbol}
                  </span>
                  <span className="text-emerald-600 font-mono font-bold text-sm">
                    +{d.score_delta.toFixed(1)}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[9px]">
                  <span className="text-gray-500">{d.prev_score?.toFixed(0) ?? '—'}</span>
                  <span className="text-emerald-600">→</span>
                  <span className="font-mono font-bold" {...fg(scoreColor(d.convergence_score))}>
                    {d.convergence_score.toFixed(0)}
                  </span>
                  <span className="text-gray-500 ml-auto">{d.module_count} sources</span>
                </div>
                {d.narrative && (
                  <p className="text-[8px] text-gray-500 mt-1 line-clamp-1">{d.narrative}</p>
                )}
              </a>
            ))}
          </div>
        </div>
      )}

      {/* Downgrades row */}
      {(downgrades.length > 0 || signalDowngrades.length > 0) && (
        <div className="overflow-x-auto scrollbar-hide">
          <div className="flex gap-2 pb-1" {...cs({ minWidth: 'min-content' })}>
            {/* Signal downgrades first */}
            {signalDowngrades.map(c => (
              <a
                key={`sig-${c.symbol}`}
                href={`/asset/${c.symbol}`}
                className="panel p-3 shrink-0 w-[170px] border-l-2 border-l-rose-600 hover:border-rose-600/40 transition-colors group"
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="font-mono font-bold text-sm text-gray-900 group-hover:text-rose-600 transition-colors">
                    {c.symbol}
                  </span>
                  <span className="text-[8px] text-rose-600 font-bold tracking-wider bg-rose-600/10 px-1.5 py-0.5 rounded-lg">
                    DOWNGRADE
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-[9px]">
                  <span className="text-gray-500 line-through">{c.old_signal}</span>
                  <span className="text-rose-600">→</span>
                  <SignalBadge signal={c.new_signal} size="sm" />
                </div>
              </a>
            ))}

            {/* Convergence score downgrades */}
            {downgrades.slice(0, 10).map(d => (
              <a
                key={`conv-${d.symbol}`}
                href={`/asset/${d.symbol}`}
                className="panel p-3 shrink-0 w-[170px] border-l-2 border-l-rose-600/60 hover:border-rose-600/40 transition-colors group"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono font-bold text-sm text-gray-900 group-hover:text-rose-600 transition-colors">
                    {d.symbol}
                  </span>
                  <span className="text-rose-600 font-mono font-bold text-sm">
                    {d.score_delta > 0 ? '+' : ''}{d.score_delta.toFixed(1)}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-[9px]">
                  <span className="text-gray-500">{d.prev_score?.toFixed(0) ?? '—'}</span>
                  <span className="text-rose-600">→</span>
                  <span className="font-mono font-bold" {...fg(scoreColor(d.convergence_score))}>
                    {d.convergence_score.toFixed(0)}
                  </span>
                  <span className="text-gray-500 ml-auto">{d.module_count} sources</span>
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
