'use client';

import { fgGlow } from '@/lib/styles';

interface Props {
  name: string;
  score: number;
  description: string;
  rate?: string | null;
  inverse?: boolean;
}

export default function IndicatorCard({ name, score, description, rate }: Props) {
  if (score == null) return null;
  // Scores are signed regime contributions (range ~-20 to +20).
  // Positive = bullish, negative = bearish.
  const color = score > 5 ? '#059669' : score >= -5 ? '#d97706' : '#e11d48';
  const glow = Math.abs(score) >= 10;
  const sign = score > 0 ? '+' : '';

  return (
    <div className="panel p-4 hover:border-emerald-600/20 transition-colors">
      <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-2">
        {name}
      </div>
      <div className="flex items-baseline gap-1 mb-1">
        <div
          className="text-2xl font-display font-bold"
          {...fgGlow(color, glow ? `0 0 10px ${color}40` : 'none')}
        >
          {sign}{score.toFixed(0)}
        </div>
        <div className="text-[10px] text-gray-400 font-mono">pts</div>
      </div>
      {rate && (
        <div className="text-[10px] font-mono text-gray-500 mb-1 leading-relaxed">{rate}</div>
      )}
      <div className="text-[10px] text-gray-400 leading-relaxed">
        Regime score contribution · {description}
      </div>
    </div>
  );
}
