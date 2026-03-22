import type { Signal, ConvergenceSignal } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import TradeRangeBar from '@/components/TradeRangeBar';
import ModuleStrip from '@/components/ModuleStrip';
import Sparkline from '@/components/Sparkline';
import { scoreColor } from '@/lib/modules';
import { fgGlow, fg } from '@/lib/styles';

function convictionBorder(score: number | undefined) {
  if (!score) return '';
  if (score >= 80) return 'border-emerald-600/40';
  if (score >= 60) return 'border-emerald-600/20';
  return '';
}

type ActionStock = Signal & { conv?: ConvergenceSignal };

interface ConvictionCardsProps {
  actionStocks: ActionStock[];
  sparkPrices: Record<string, { date: string; close: number }[]>;
}

export function HomeConvictionCards({ actionStocks, sparkPrices }: ConvictionCardsProps) {
  const hero = actionStocks[0];
  const mediums = actionStocks.slice(1, 3);
  const smalls = actionStocks.slice(3, 6);

  return (
    <div className="col-span-3 space-y-3">
      <h2 className="text-xs text-gray-500 tracking-[0.2em] uppercase">
        Highest Conviction Setups
      </h2>

      {/* Hero Card */}
      {hero && (
        <a
          href={`/asset/${hero.symbol}`}
          className={`panel p-5 block hover:border-emerald-600/40 transition-all group ${convictionBorder(hero.conv?.convergence_score)}`}
        >
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <span className="text-lg font-display font-bold text-gray-900 group-hover:text-emerald-600 transition-colors">
                {hero.symbol}
              </span>
              <SignalBadge signal={hero.signal} size="md" />
              {hero.conv && (
                <span className={`text-[10px] font-bold tracking-wider px-2 py-0.5 rounded-lg ${
                  hero.conv.conviction_level === 'high'
                    ? 'text-emerald-600 bg-emerald-600/10'
                    : hero.conv.conviction_level === 'medium'
                    ? 'text-amber-600 bg-amber-600/10'
                    : 'text-gray-500 bg-gray-400/10'
                }`}>
                  {hero.conv.conviction_level?.toUpperCase()} · {hero.conv.module_count} MODULES
                </span>
              )}
            </div>
            {hero.conv && (
              <span
                className="text-3xl font-display font-bold"
                {...fgGlow(scoreColor(hero.conv.convergence_score), hero.conv.convergence_score >= 70 ? `0 0 20px ${scoreColor(hero.conv.convergence_score)}30` : 'none')}
              >
                {hero.conv.convergence_score.toFixed(1)}
              </span>
            )}
          </div>

          <div className="flex items-center gap-4 mb-3">
            {sparkPrices[hero.symbol] && (
              <Sparkline prices={sparkPrices[hero.symbol]} width={140} height={44} />
            )}
            <div className="flex-1">
              {hero.conv && <ModuleStrip convergence={hero.conv} mode="compact" />}
            </div>
          </div>

          <div className="flex items-center gap-6 mb-3">
            {hero.entry_price != null ? <TradeRangeBar entry={hero.entry_price} stop={hero.stop_loss ?? hero.entry_price * 0.95} target={hero.target_price ?? hero.entry_price * 1.1} width={240} height={20} showLabels showRR /> : <span className="text-gray-400 text-[10px]">{'\u2014'}</span>}
            <div className="text-[10px] text-gray-500">
              <span className="text-gray-700 font-mono">${hero.position_size_dollars ? `${(hero.position_size_dollars / 1000).toFixed(0)}K` : '\u2014'}</span>
              <span className="ml-1">SIZE</span>
            </div>
          </div>

          {hero.conv?.narrative && (
            <p className="text-[10px] text-gray-500 leading-relaxed line-clamp-3">
              {hero.conv.narrative}
            </p>
          )}
        </a>
      )}

      {/* Medium Cards */}
      <div className="grid grid-cols-2 gap-3">
        {mediums.map(s => (
          <a
            key={s.symbol}
            href={`/asset/${s.symbol}`}
            className={`panel p-4 block hover:border-emerald-600/30 transition-all group ${convictionBorder(s.conv?.convergence_score)}`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-display font-bold text-gray-900 group-hover:text-emerald-600 transition-colors">
                  {s.symbol}
                </span>
                <SignalBadge signal={s.signal} size="sm" />
              </div>
              {s.conv && (
                <span className="text-xl font-display font-bold" {...fg(scoreColor(s.conv.convergence_score))}>
                  {s.conv.convergence_score.toFixed(1)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mb-2">
              {sparkPrices[s.symbol] && <Sparkline prices={sparkPrices[s.symbol]} width={90} height={32} />}
              <div className="flex-1">{s.conv && <ModuleStrip convergence={s.conv} mode="compact" />}</div>
            </div>
            {s.entry_price != null && <TradeRangeBar entry={s.entry_price} stop={s.stop_loss ?? s.entry_price * 0.95} target={s.target_price ?? s.entry_price * 1.1} width={180} height={14} showRR />}
            {s.conv?.narrative && (
              <p className="text-[10px] text-gray-500 mt-2 line-clamp-2 leading-relaxed">{s.conv.narrative}</p>
            )}
          </a>
        ))}
      </div>

      {/* Small Cards */}
      <div className="grid grid-cols-3 gap-3">
        {smalls.map(s => (
          <a key={s.symbol} href={`/asset/${s.symbol}`} className="panel p-3 block hover:border-emerald-600/30 transition-all group">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-sm font-display font-bold text-gray-900 group-hover:text-emerald-600 transition-colors">{s.symbol}</span>
              {s.conv && (
                <span className="text-base font-display font-bold" {...fg(scoreColor(s.conv.convergence_score))}>
                  {s.conv.convergence_score.toFixed(0)}
                </span>
              )}
            </div>
            {s.entry_price != null && <TradeRangeBar entry={s.entry_price} stop={s.stop_loss ?? s.entry_price * 0.95} target={s.target_price ?? s.entry_price * 1.1} width={140} height={10} showRR />}
            {s.conv?.narrative && (
              <p className="text-[8px] text-gray-500 mt-1.5 line-clamp-1 leading-relaxed">{s.conv.narrative}</p>
            )}
          </a>
        ))}
      </div>
    </div>
  );
}
