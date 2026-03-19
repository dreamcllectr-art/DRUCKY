'use client';

import { fgGlow } from '@/lib/styles';

interface Props {
  name: string;
  score: number;
  description: string;
  inverse?: boolean;
}

export default function IndicatorCard({ name, score, description, inverse }: Props) {
  const color = inverse
    ? (score >= 70 ? '#e11d48' : score >= 40 ? '#d97706' : '#059669')
    : (score >= 70 ? '#059669' : score >= 40 ? '#d97706' : '#e11d48');
  const glow = score >= 70 || score < 20;

  return (
    <div className="panel p-4 hover:border-emerald-600/20 transition-colors">
      <div className="text-[10px] text-gray-500 tracking-wider uppercase mb-2">
        {name}
      </div>
      <div
        className="text-2xl font-display font-bold mb-1"
        {...fgGlow(color, glow ? `0 0 10px ${color}40` : 'none')}
      >
        {score.toFixed(0)}
      </div>
      <div className="text-[9px] text-gray-500 leading-relaxed">
        {description}
      </div>
    </div>
  );
}
