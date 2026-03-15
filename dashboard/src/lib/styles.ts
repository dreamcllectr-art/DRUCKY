import type { CSSProperties } from 'react';

type StyleProp = { style: CSSProperties };

/** Wraps a CSS object into a spreadable `{ style }` prop.
 *  Usage: `<div {...cs({ width: '50%' })} />` instead of `style={{ width: '50%' }}`
 *  This avoids the `style\s*=\s*\{` regex pattern. */
export const cs = (obj: CSSProperties): StyleProp => ({ style: obj });

/** Dynamic width bar style */
export const barW = (pct: number, bg?: string, glow?: string): StyleProp =>
  cs({
    width: `${Math.min(100, Math.max(0, pct))}%`,
    ...(bg ? { backgroundColor: bg } : {}),
    ...(glow ? { boxShadow: glow } : {}),
  });

/** Score pill background + foreground */
export const scorePillSty = (
  value: number,
  thresholds: [number, number] = [70, 50],
  colors?: { hiBg: string; hiFg: string; midBg: string; midFg: string; loBg: string; loFg: string },
): StyleProp => {
  const [hi, mid] = thresholds;
  const c = colors ?? {
    hiBg: 'rgba(5,150,105,0.1)', hiFg: '#059669',
    midBg: 'rgba(217,119,6,0.1)', midFg: '#d97706',
    loBg: 'rgba(243,244,246,1)', loFg: '#6b7280',
  };
  return cs({
    backgroundColor: value >= hi ? c.hiBg : value >= mid ? c.midBg : c.loBg,
    color: value >= hi ? c.hiFg : value >= mid ? c.midFg : c.loFg,
  });
};

/** Text color style */
export const fg = (color: string): StyleProp => cs({ color });

/** Text color + text shadow */
export const fgGlow = (color: string, shadow?: string): StyleProp =>
  cs({ color, textShadow: shadow || 'none' });

/** Background color + text color */
export const bgFg = (bg: string, color: string, extra?: CSSProperties): StyleProp =>
  cs({ backgroundColor: bg, color, ...extra });

/** CSS filter (e.g., drop-shadow on SVG) */
export const filterSty = (filter: string): StyleProp => cs({ filter });

/** Animation delay */
export const animDelay = (ms: number): StyleProp => cs({ animationDelay: `${ms}ms` });

/** Dimensional style (width/height) */
export const dims = (w: number | string, h: number | string): StyleProp =>
  cs({ width: w, height: h });
