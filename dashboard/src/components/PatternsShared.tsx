import type { PatternScanResult, PatternLayerDetail } from '@/lib/api';

export const QUADRANT_COLORS: Record<string, string> = {
  leading: 'text-emerald-600',
  weakening: 'text-amber-400',
  lagging: 'text-red-400',
  improving: 'text-cyan-400',
  neutral: 'text-gray-500',
};

export const QUADRANT_BG: Record<string, string> = {
  leading: 'bg-emerald-600/10 border-emerald-600/30',
  weakening: 'bg-amber-400/10 border-amber-400/30',
  lagging: 'bg-red-400/10 border-red-400/30',
  improving: 'bg-cyan-400/10 border-cyan-400/30',
  neutral: 'bg-gray-50 border-white/10',
};

export const WYCKOFF_COLORS: Record<string, string> = {
  accumulation: 'text-emerald-600',
  markup: 'text-cyan-400',
  distribution: 'text-amber-400',
  markdown: 'text-red-400',
  unknown: 'text-gray-500',
};

export const DEALER_COLORS: Record<string, string> = {
  pinning: 'text-amber-400',
  amplifying: 'text-red-400',
  neutral: 'text-gray-500',
};

export function ScorePill({ value, max = 100 }: { value: number | null; max?: number }) {
  if (value == null) return <span className="text-gray-500">--</span>;
  const pct = value / max;
  const color =
    pct >= 0.7 ? 'text-emerald-600' : pct >= 0.5 ? 'text-amber-400' : 'text-red-400';
  return <span className={`font-mono text-xs ${color}`}>{value.toFixed(0)}</span>;
}

export function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span
      className={`text-[10px] font-mono tracking-wider px-1.5 py-0.5 rounded border ${color}`}
    >
      {text.toUpperCase()}
    </span>
  );
}
