/** Shared formatting and constants used across V2 components. */

export function fmtM(v: number | string | null | undefined): string {
  if (v == null) return '—';
  const num = +v;
  if (!isFinite(num)) return '—';
  const n = Math.abs(num);
  if (n >= 1e9) return `$${(num / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(num / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(num / 1e3).toFixed(0)}K`;
  return `$${num.toFixed(0)}`;
}

export function fmt(v: number | string | null | undefined, decimals = 0): string {
  if (v == null) return '—';
  const num = +v;
  if (!isFinite(num)) return '—';
  return num.toFixed(decimals);
}

/** Tailwind classes for gate badge background + text. Gate 10 = fat pitch (vivid emerald). */
export const GATE_COLORS: Record<number, string> = {
  10: 'bg-emerald-600 text-white',
  9:  'bg-emerald-700 text-white',
  8:  'bg-emerald-700 text-white',
  7:  'bg-emerald-600 text-white',
  6:  'bg-emerald-500 text-emerald-950',
  5:  'bg-emerald-400 text-emerald-950',
  4:  'bg-emerald-300 text-emerald-900',
  3:  'bg-emerald-200 text-emerald-800',
  2:  'bg-emerald-100 text-emerald-700',
  1:  'bg-gray-100 text-gray-600',
};

export function gateBadgeCls(gate: number): string {
  return GATE_COLORS[gate] ?? 'bg-gray-200 text-gray-600';
}

/** Parse top_buyer — DB stores it as JSON string or plain name string. */
export function fmtTopBuyer(v: string | null | undefined): string {
  if (!v) return '—';
  try {
    if (v.startsWith('{')) {
      const b = JSON.parse(v);
      return b.name ? `${b.name}${b.title ? ' · ' + b.title : ''}` : '—';
    }
  } catch { /* fall through */ }
  return v;
}

/** Tailwind text-color class based on a 0–100 score. */
export function scoreTextCls(s: number | null | undefined): string {
  if (s == null) return 'text-gray-300';
  if (s >= 70) return 'text-emerald-600';
  if (s >= 50) return 'text-amber-600';
  return 'text-rose-500';
}
