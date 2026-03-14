'use client';

interface Props {
  value: number;
  label: string;
  max?: number;
}

export default function ScoreBar({ value, label, max = 100 }: Props) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const color =
    value >= 70 ? '#00FF41' :
    value >= 40 ? '#FFB800' :
    '#FF073A';
  const glow = value >= 70;

  return (
    <div className="flex items-center gap-3">
      <span className="text-[10px] text-terminal-dim w-24 shrink-0 tracking-wider uppercase">
        {label}
      </span>
      <div className="flex-1 h-2 bg-terminal-muted rounded-sm overflow-hidden relative">
        <div
          className="h-full rounded-sm transition-all duration-500"
          style={{
            width: `${pct}%`,
            backgroundColor: color,
            boxShadow: glow ? `0 0 8px ${color}40, 0 0 2px ${color}60` : 'none',
          }}
        />
      </div>
      <span
        className="text-[11px] font-mono w-8 text-right font-bold"
        style={{ color }}
      >
        {value.toFixed(0)}
      </span>
    </div>
  );
}
