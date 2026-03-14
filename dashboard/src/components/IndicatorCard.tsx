'use client';

interface Props {
  name: string;
  score: number;
  description: string;
}

export default function IndicatorCard({ name, score, description }: Props) {
  const color =
    score >= 70 ? '#00FF41' :
    score >= 40 ? '#FFB800' :
    '#FF073A';
  const glow = score >= 70 || score < 20;

  return (
    <div className="panel p-4 hover:border-terminal-green/20 transition-colors">
      <div className="text-[10px] text-terminal-dim tracking-wider uppercase mb-2">
        {name}
      </div>
      <div
        className="text-2xl font-display font-bold mb-1"
        style={{
          color,
          textShadow: glow ? `0 0 10px ${color}40` : 'none',
        }}
      >
        {score.toFixed(0)}
      </div>
      <div className="text-[9px] text-terminal-dim leading-relaxed">
        {description}
      </div>
    </div>
  );
}
