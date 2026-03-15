'use client';

import { cs, fgGlow } from '@/lib/styles';

interface Props {
  score: number;
  regime: string;
}

const regimeLabels: Record<string, string> = {
  strong_risk_on: 'STRONG RISK-ON',
  risk_on: 'RISK-ON',
  neutral: 'NEUTRAL',
  risk_off: 'RISK-OFF',
  strong_risk_off: 'STRONG RISK-OFF',
};

const regimeColors: Record<string, string> = {
  strong_risk_on: '#059669',
  risk_on: '#10b981',
  neutral: '#d97706',
  risk_off: '#ea580c',
  strong_risk_off: '#e11d48',
};

export default function MacroGauge({ score, regime }: Props) {
  const color = regimeColors[regime] || '#d97706';
  const label = regimeLabels[regime] || regime;
  // Map -100..+100 to 0..180 degrees for the gauge
  const angle = ((score + 100) / 200) * 180;

  return (
    <div className="panel p-6 flex flex-col items-center">
      {/* Gauge SVG */}
      <div className="relative w-64 h-36">
        <svg viewBox="0 0 200 110" className="w-full h-full">
          {/* Background arc */}
          <path
            d="M 10 100 A 90 90 0 0 1 190 100"
            fill="none"
            stroke="#e5e7eb"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Colored segments */}
          <path d="M 10 100 A 90 90 0 0 1 46 32" fill="none" stroke="#e11d48" strokeWidth="3" opacity="0.4" />
          <path d="M 46 32 A 90 90 0 0 1 82 12" fill="none" stroke="#ea580c" strokeWidth="3" opacity="0.4" />
          <path d="M 82 12 A 90 90 0 0 1 118 12" fill="none" stroke="#d97706" strokeWidth="3" opacity="0.4" />
          <path d="M 118 12 A 90 90 0 0 1 154 32" fill="none" stroke="#10b981" strokeWidth="3" opacity="0.4" />
          <path d="M 154 32 A 90 90 0 0 1 190 100" fill="none" stroke="#059669" strokeWidth="3" opacity="0.4" />

          {/* Needle */}
          <line
            x1="100"
            y1="100"
            x2={100 + 75 * Math.cos(((180 - angle) * Math.PI) / 180)}
            y2={100 - 75 * Math.sin(((180 - angle) * Math.PI) / 180)}
            stroke={color}
            strokeWidth="2"
            strokeLinecap="round"
            {...cs({ filter: `drop-shadow(0 0 4px ${color})` })}
          />
          <circle cx="100" cy="100" r="4" fill={color} />
        </svg>
      </div>

      {/* Score */}
      <div className="text-center -mt-2">
        <span className="text-4xl font-display font-bold" {...fgGlow(color, `0 0 20px ${color}40`)}>
          {score > 0 ? '+' : ''}{score.toFixed(0)}
        </span>
        <div
          className="text-xs tracking-[0.3em] font-mono mt-2 px-4 py-1 rounded-lg inline-block"
          {...cs({ color, background: `${color}15`, border: `1px solid ${color}30` })}
        >
          {label}
        </div>
      </div>
    </div>
  );
}
