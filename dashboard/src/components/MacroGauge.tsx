'use client';

interface Props { score: number; regime: string }

const REGIME_LABELS: Record<string, string> = {
  strong_risk_on: 'STRONG RISK-ON', risk_on: 'RISK-ON', neutral: 'NEUTRAL',
  risk_off: 'RISK-OFF', strong_risk_off: 'STRONG RISK-OFF',
};
const REGIME_COLORS: Record<string, string> = {
  strong_risk_on: '#059669', risk_on: '#10b981', neutral: '#d97706',
  risk_off: '#ea580c', strong_risk_off: '#e11d48',
};

// Geometry: semicircle with pivot at (100, 105), radius 78
const CX = 100, CY = 105, R = 78;

const p = (deg: number, r = R) => ({
  x: CX + r * Math.cos((deg * Math.PI) / 180),
  y: CY - r * Math.sin((deg * Math.PI) / 180),
});

// Single continuous arc from angle A→B going counter-clockwise (over the top)
const arcD = (a: number, b: number, r = R) => {
  const s = p(a, r), e = p(b, r);
  return `M ${s.x.toFixed(3)} ${s.y.toFixed(3)} A ${r} ${r} 0 0 1 ${e.x.toFixed(3)} ${e.y.toFixed(3)}`;
};

// score 0→180°  score 100→0°
const s2a = (s: number) => 180 - s * 1.8;

export default function MacroGauge({ score, regime }: Props) {
  const color = REGIME_COLORS[regime] || '#d97706';
  const label = REGIME_LABELS[regime] || regime;
  const rawScore = score ?? 0;
  const ds = Math.round((rawScore + 100) / 2); // 0-100 display score

  // Needle from pivot toward tip
  const na = s2a(ds);
  const tip = p(na, 66);
  const b1 = p(na + 90, 6), b2 = p(na - 90, 6);

  return (
    <div className="panel p-6 flex flex-col items-center">
      <div className="w-72 h-48">
        <svg viewBox="0 0 200 132" className="w-full h-full">
          <defs>
            {/* Smooth left-to-right gradient matching the arc's x-span */}
            <linearGradient id="gaugeGrad" gradientUnits="userSpaceOnUse" x1="22" y1="0" x2="178" y2="0">
              <stop offset="0%"   stopColor="#e11d48" />
              <stop offset="20%"  stopColor="#f97316" />
              <stop offset="50%"  stopColor="#d97706" />
              <stop offset="80%"  stopColor="#10b981" />
              <stop offset="100%" stopColor="#059669" />
            </linearGradient>
            {/* Clip to only show the portion up to the needle (filled progress) */}
          </defs>

          {/* 1 — Gray background track (full semicircle) */}
          <path d={arcD(180, 0)} fill="none" stroke="#e9eaec" strokeWidth="16" strokeLinecap="round" />

          {/* 2 — Gradient color track (full semicircle, transparent) */}
          <path d={arcD(180, 0)} fill="none" stroke="url(#gaugeGrad)"
            strokeWidth="16" strokeLinecap="round" opacity="0.45" />

          {/* 3 — Active zone: filled arc from start to current score */}
          <path d={arcD(180, s2a(ds))} fill="none" stroke={color}
            strokeWidth="16" strokeLinecap="round" opacity="0.75" />

          {/* 4 — Thin zone divider ticks */}
          {[20, 35, 65, 80].map((s) => {
            const a = s2a(s);
            const i = p(a, R - 10), o = p(a, R + 10);
            return <line key={s} x1={i.x} y1={i.y} x2={o.x} y2={o.y}
              stroke="white" strokeWidth="2" opacity="0.9" />;
          })}

          {/* 5 — Needle */}
          <polygon points={`${tip.x},${tip.y} ${b1.x},${b1.y} ${b2.x},${b2.y}`}
            fill={color} style={{ filter: `drop-shadow(0 0 6px ${color}90)` }} />

          {/* 6 — Pivot */}
          <circle cx={CX} cy={CY} r="9" fill="white" stroke="#e5e7eb" strokeWidth="1.5" />
          <circle cx={CX} cy={CY} r="4" fill={color} />

          {/* Zone labels */}
          <text x="16" y="120" fontSize="7.5" fill="#e11d48" opacity="0.8"
            fontFamily="ui-monospace,monospace" fontWeight="500">BEAR</text>
          <text x="184" y="120" fontSize="7.5" fill="#059669" opacity="0.8"
            fontFamily="ui-monospace,monospace" fontWeight="500" textAnchor="end">BULL</text>
        </svg>
      </div>

      <div className="text-center -mt-2 flex flex-col items-center gap-2">
        <div className="flex items-baseline gap-1">
          <span className="text-5xl font-display font-bold tabular-nums"
            style={{ color, filter: `drop-shadow(0 0 16px ${color}45)` }}>
            {ds}
          </span>
          <span className="text-sm text-gray-400 font-mono">/100</span>
        </div>
        <div className="text-[11px] tracking-[0.25em] font-mono px-5 py-1.5 rounded-full"
          style={{ color, background: `${color}12`, border: `1px solid ${color}35` }}>
          {label}
        </div>
      </div>
    </div>
  );
}
