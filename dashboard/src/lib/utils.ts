/** Shared formatting and constants used across V2 components. */

export function fmtM(v: number | null | undefined): string {
  if (v == null) return '—';
  const n = Math.abs(v);
  if (n >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

export function fmt(v: number | null | undefined, decimals = 0): string {
  if (v == null) return '—';
  return v.toFixed(decimals);
}

/** Tailwind classes for gate badge background + text. */
export const GATE_COLORS: Record<number, string> = {
  10: 'bg-emerald-600 text-white',
  9:  'bg-emerald-500 text-white',
  8:  'bg-teal-500 text-white',
  7:  'bg-sky-500 text-white',
  6:  'bg-blue-500 text-white',
  5:  'bg-indigo-400 text-white',
  4:  'bg-violet-400 text-white',
  3:  'bg-purple-400 text-white',
};

export function gateBadgeCls(gate: number): string {
  return GATE_COLORS[gate] ?? 'bg-gray-200 text-gray-600';
}

/** Tailwind text-color class based on a 0–100 score. */
export function scoreTextCls(s: number | null | undefined): string {
  if (s == null) return 'text-gray-300';
  if (s >= 70) return 'text-emerald-600';
  if (s >= 50) return 'text-amber-600';
  return 'text-rose-500';
}
