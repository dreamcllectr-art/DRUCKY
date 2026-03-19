'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { EnvironmentData } from '@/lib/api';
import { cs, fg } from '@/lib/styles';

function regimeColor(regime: string): string {
  const r = (regime || '').toUpperCase();
  if (r.includes('RISK_ON') || r.includes('BULLISH')) return '#059669';
  if (r.includes('RISK_OFF') || r.includes('BEARISH')) return '#e11d48';
  return '#d97706';
}

function indicatorColor(score: number | null, inverse = false): string {
  if (score == null) return '#9ca3af';
  const effective = inverse ? 100 - score : score;
  if (effective >= 65) return '#059669';
  if (effective >= 40) return '#d97706';
  return '#e11d48';
}

export default function EnvironmentView() {
  const [data, setData] = useState<EnvironmentData | null>(null);
  const [error, setError] = useState('');
  const [expandedCross, setExpandedCross] = useState<number | null>(null);

  useEffect(() => {
    api.environment().then(setData).catch(e => setError(e.message));
  }, []);

  if (error) return <div className="text-rose-600 text-sm p-4">{error}</div>;
  if (!data) return <div className="text-gray-400 text-sm p-8 text-center">Loading environment...</div>;

  const regime = data.regime || {} as any;
  const heat = data.heat_index || {} as any;

  const INDICATORS = [
    { label: 'Liquidity (M2)', key: 'm2_score', inverse: false },
    { label: 'Rates (Fed Funds)', key: 'fed_funds_score', inverse: false },
    { label: 'Credit Spreads', key: 'credit_spreads_score', inverse: true },
    { label: 'Volatility (VIX)', key: 'vix_score', inverse: true },
    { label: 'Dollar (DXY)', key: 'dxy_score', inverse: true },
    { label: 'Yield Curve', key: 'yield_curve_score', inverse: false },
    { label: 'Real Rates', key: 'real_rates_score', inverse: true },
  ];

  return (
    <div className="space-y-6">
      {/* Regime Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div
              className="w-14 h-14 rounded-xl flex items-center justify-center text-white text-xl font-bold shadow-sm"
              {...cs({ backgroundColor: regimeColor(regime.regime) })}
            >
              {regime.total_score != null ? Math.round(regime.total_score) : '?'}
            </div>
            <div>
              <div className="text-xs text-gray-400 tracking-widest uppercase">Macro Regime</div>
              <div className="text-lg font-semibold text-gray-900 tracking-wide">
                {(regime.regime || 'UNKNOWN').replace(/_/g, ' ')}
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">{regime.date || ''}</div>
            </div>
          </div>
          {heat.heat_index != null && (
            <div className="text-right">
              <div className="text-xs text-gray-400 tracking-widest uppercase">Economic Heat</div>
              <div className="text-2xl font-bold" {...fg(heat.heat_index >= 60 ? '#059669' : heat.heat_index >= 40 ? '#d97706' : '#e11d48')}>
                {heat.heat_index.toFixed(0)}
              </div>
              <div className="text-[10px] text-gray-400">
                {heat.improving_count || 0} improving / {heat.deteriorating_count || 0} worsening
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Regime Alerts */}
      {data.alerts.length > 0 && (
        <div className="space-y-2">
          {data.alerts.map((a, i) => (
            <div key={i} className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-amber-600 text-sm">{'\u26A0'}</span>
              <div>
                <span className="text-[10px] text-amber-700 font-semibold uppercase tracking-wider">{a.type}</span>
                <span className="text-xs text-amber-800 ml-2">{a.message}</span>
              </div>
              <span className="ml-auto text-[9px] text-amber-500 uppercase tracking-wider">{a.severity}</span>
            </div>
          ))}
        </div>
      )}

      {/* Indicator Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {INDICATORS.map(ind => {
          const val = (regime as any)[ind.key];
          return (
            <div key={ind.key} className="bg-white rounded-lg border border-gray-200 p-3 shadow-sm">
              <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-1">{ind.label}</div>
              <div className="text-xl font-bold" {...fg(indicatorColor(val, ind.inverse))}>
                {val != null ? Math.round(val) : '\u2014'}
              </div>
              {ind.inverse && <div className="text-[8px] text-gray-300 mt-0.5">inverted</div>}
            </div>
          );
        })}
      </div>

      {/* Asset Class Signals */}
      {data.asset_classes.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Asset Class Regime Signals</div>
          <div className="flex flex-wrap gap-3">
            {data.asset_classes.map((ac: any, i: number) => (
              <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-100 bg-gray-50">
                <span className="text-xs font-semibold text-gray-700">{ac.asset_class}</span>
                <span
                  className="text-[10px] font-bold uppercase tracking-wider"
                  {...fg(ac.regime_signal === 'overweight' ? '#059669' : ac.regime_signal === 'underweight' ? '#e11d48' : '#d97706')}
                >
                  {ac.regime_signal || 'neutral'}
                </span>
                <span className="text-[9px] text-gray-400">{ac.score != null ? ac.score.toFixed(0) : ''}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Cross-Cutting Intelligence */}
      {data.cross_cutting.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Cross-Cutting Intelligence</div>
          <div className="space-y-2">
            {data.cross_cutting.map((item, i) => (
              <div key={i} className="border-l-2 border-emerald-200 pl-3">
                <button
                  onClick={() => setExpandedCross(expandedCross === i ? null : i)}
                  className="w-full text-left flex items-center gap-2"
                >
                  <span className="text-[8px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded uppercase tracking-wider font-semibold">
                    {item.source}
                  </span>
                  <span className="text-xs text-gray-800">{item.headline}</span>
                  <span className="ml-auto text-[8px] text-gray-300">{expandedCross === i ? '\u25B4' : '\u25BE'}</span>
                </button>
                {expandedCross === i && (
                  <div className="text-[11px] text-gray-500 mt-1 pl-1">{item.detail}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
