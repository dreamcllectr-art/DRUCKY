import type { ConvergenceSignal } from '@/lib/api';
import TradeRangeBar from '@/components/TradeRangeBar';
import { scoreColor } from '@/lib/modules';
import { fgGlow } from '@/lib/styles';

interface TradeSetupProps {
  signal: { entry_price?: number | null; stop_loss?: number | null; target_price?: number | null; rr_ratio?: number | null; composite_score: number; position_size_dollars?: number | null; position_size_shares?: number | null };
  conv: ConvergenceSignal | null;
  currentPrice: number;
}

export function AssetTradeSetup({ signal: s, conv, currentPrice }: TradeSetupProps) {
  const hasTradeData = s.entry_price != null;
  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="text-[10px] text-gray-500 tracking-widest uppercase">Trade Setup{s.rr_ratio != null ? ` · R:R ${s.rr_ratio.toFixed(1)}:1` : ''}</div>
        {conv && (
          <span className="text-2xl font-display font-bold" {...fgGlow(scoreColor(conv.convergence_score), conv.convergence_score >= 70 ? `0 0 16px ${scoreColor(conv.convergence_score)}25` : 'none')}>
            {conv.convergence_score.toFixed(1)}<span className="text-[10px] text-gray-500 ml-2">CONVERGENCE</span>
          </span>
        )}
      </div>
      {hasTradeData && (
        <div className="flex justify-center mb-4">
          <TradeRangeBar entry={s.entry_price!} stop={s.stop_loss ?? s.entry_price! * 0.95} target={s.target_price ?? s.entry_price! * 1.1} currentPrice={currentPrice} width={500} height={28} showLabels showRR />
        </div>
      )}
      <div className="grid grid-cols-5 gap-6 text-center">
        <div><div className="text-[9px] text-gray-500 mb-1">ENTRY</div><div className="text-sm font-mono text-blue-600">{s.entry_price != null ? `$${s.entry_price.toFixed(2)}` : '\u2014'}</div></div>
        <div>
          <div className="text-[9px] text-gray-500 mb-1">STOP LOSS</div>
          <div className="text-sm font-mono text-rose-600">{s.stop_loss != null ? `$${s.stop_loss.toFixed(2)}` : '\u2014'}</div>
          {s.stop_loss != null && s.entry_price != null && <div className="text-[8px] text-gray-500">{'\u2212'}{((1 - s.stop_loss / s.entry_price) * 100).toFixed(1)}%</div>}
        </div>
        <div>
          <div className="text-[9px] text-gray-500 mb-1">TARGET</div>
          <div className="text-sm font-mono text-emerald-600">{s.target_price != null ? `$${s.target_price.toFixed(2)}` : '\u2014'}</div>
          {s.target_price != null && s.entry_price != null && <div className="text-[8px] text-gray-500">+{((s.target_price / s.entry_price - 1) * 100).toFixed(1)}%</div>}
        </div>
        <div><div className="text-[9px] text-gray-500 mb-1">COMPOSITE</div><div className="text-sm font-mono text-amber-600">{s.composite_score.toFixed(1)}</div></div>
        <div>
          <div className="text-[9px] text-gray-500 mb-1">POSITION SIZE</div>
          <div className="text-sm font-mono text-gray-700">{s.position_size_dollars ? `$${s.position_size_dollars.toLocaleString()}` : '\u2014'}</div>
          {s.position_size_shares && <div className="text-[8px] text-gray-500">{s.position_size_shares.toFixed(1)} shares</div>}
        </div>
      </div>
    </div>
  );
}
