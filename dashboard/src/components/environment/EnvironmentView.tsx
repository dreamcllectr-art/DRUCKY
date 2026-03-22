'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { cs, fg } from '@/lib/styles';

function regimeColor(regime: string): string {
  const r = (regime || '').toUpperCase();
  if (r.includes('RISK_ON') || r.includes('BULLISH')) return '#059669';
  if (r.includes('RISK_OFF') || r.includes('BEARISH')) return '#e11d48';
  return '#d97706';
}

function scoreColor(v: number | null, inverse = false): string {
  if (v == null) return '#9ca3af';
  const eff = inverse ? -v : v;
  if (eff >= 6) return '#059669';
  if (eff >= 0) return '#d97706';
  return '#e11d48';
}

function rotationColor(score: number): string {
  if (score >= 60) return '#059669';
  if (score >= 40) return '#d97706';
  return '#e11d48';
}

function quadrantLabel(q: string): { label: string; color: string } {
  const map: Record<string, { label: string; color: string }> = {
    leading:   { label: 'Leading',   color: '#059669' },
    improving: { label: 'Improving', color: '#10b981' },
    weakening: { label: 'Weakening', color: '#d97706' },
    lagging:   { label: 'Lagging',   color: '#e11d48' },
  };
  return map[(q || '').toLowerCase()] || { label: q || '?', color: '#9ca3af' };
}

export default function EnvironmentView() {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.environment().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <div className="text-rose-600 text-sm p-4">{error}</div>;
  if (!data) return <div className="text-gray-400 text-sm p-8 text-center">Loading environment...</div>;

  const regime = data.regime || {};
  const heat = data.heat_index || {};
  const sectors: any[] = data.sector_rotation || [];
  const themes: any[] = data.themes || [];
  const intel: any[] = data.intel_reports || [];
  const crossCutting: any[] = data.cross_cutting || [];

  const INDICATORS = [
    { label: 'Liquidity (M2)',    key: 'm2_score',            inverse: false },
    { label: 'Rates (Fed Funds)', key: 'fed_funds_score',     inverse: false },
    { label: 'Credit Spreads',    key: 'credit_spreads_score',inverse: true  },
    { label: 'Volatility (VIX)', key: 'vix_score',            inverse: true  },
    { label: 'Dollar (DXY)',      key: 'dxy_score',            inverse: true  },
    { label: 'Yield Curve',       key: 'yield_curve_score',   inverse: false },
    { label: 'Real Rates',        key: 'real_rates_score',    inverse: true  },
  ];

  const leadingSectors = sectors.filter(s => (s.quadrant || '').toLowerCase() === 'leading' || (s.quadrant || '').toLowerCase() === 'improving');
  const laggingSectors = sectors.filter(s => (s.quadrant || '').toLowerCase() === 'lagging' || (s.quadrant || '').toLowerCase() === 'weakening');

  return (
    <div className="space-y-4">

      {/* Regime Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div
              className="w-14 h-14 rounded-xl flex items-center justify-center text-white text-xl font-bold shadow-sm"
              {...cs({ backgroundColor: regimeColor(regime.regime) })}
            >
              {regime.total_score != null ? Math.round(regime.total_score) : '?'}
            </div>
            <div>
              <div className="text-[10px] text-gray-400 tracking-widest uppercase">Macro Regime</div>
              <div className="text-lg font-semibold text-gray-900 tracking-wide capitalize">
                {(regime.regime || 'UNKNOWN').replace(/_/g, ' ')}
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">{regime.date || ''}</div>
            </div>
          </div>
          <div className="flex items-center gap-8">
            {heat.heat_index != null && (
              <div className="text-right">
                <div className="text-[10px] text-gray-400 tracking-widest uppercase">Economic Heat</div>
                <div className="text-2xl font-bold" {...fg(heat.heat_index >= 60 ? '#059669' : heat.heat_index >= 40 ? '#d97706' : '#e11d48')}>
                  {heat.heat_index.toFixed(0)}
                </div>
                <div className="text-[10px] text-gray-400">
                  {heat.improving_count || 0} improving / {heat.deteriorating_count || 0} worsening
                </div>
              </div>
            )}
            {/* Asset class tilt pills */}
            {data.asset_classes && data.asset_classes.length > 0 ? (
              <div className="flex gap-2">
                {data.asset_classes.map((ac: any, i: number) => (
                  <div key={i} className="text-center px-3 py-1.5 rounded-lg border border-gray-100 bg-gray-50">
                    <div className="text-[8px] text-gray-400 uppercase tracking-wider">{ac.asset_class}</div>
                    <div className="text-[10px] font-bold uppercase tracking-wider mt-0.5"
                      {...fg(ac.regime_signal === 'overweight' ? '#059669' : ac.regime_signal === 'underweight' ? '#e11d48' : '#d97706')}>
                      {ac.regime_signal || 'N/A'}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex gap-2">
                {[{n:'Equities',s:'ACTIVE',c:'#059669'},{n:'Bonds',s:'NEUTRAL',c:'#d97706'},{n:'Commodities',s:'NEUTRAL',c:'#d97706'},{n:'Crypto',s:'NEUTRAL',c:'#d97706'}].map(ac => (
                  <div key={ac.n} className="text-center px-3 py-1.5 rounded-lg border border-gray-100 bg-gray-50">
                    <div className="text-[8px] text-gray-400 uppercase tracking-wider">{ac.n}</div>
                    <div className="text-[10px] font-bold uppercase tracking-wider mt-0.5" {...fg(ac.c)}>{ac.s}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Alerts */}
      {data.alerts && data.alerts.length > 0 && (
        <div className="space-y-1.5">
          {data.alerts.map((a: any, i: number) => (
            <div key={i} className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-amber-600">⚠</span>
              <span className="text-[10px] text-amber-700 font-semibold uppercase tracking-wider">{a.type}</span>
              <span className="text-xs text-amber-800">{a.message}</span>
              <span className="ml-auto text-[10px] text-amber-500 uppercase">{a.severity}</span>
            </div>
          ))}
        </div>
      )}

      {/* Macro Indicator Strip */}
      <div className="grid grid-cols-7 gap-2">
        {INDICATORS.map(ind => {
          const val = (regime as any)[ind.key];
          return (
            <div key={ind.key} className="bg-white rounded-lg border border-gray-200 p-3 shadow-sm">
              <div className="text-[8px] text-gray-400 tracking-widest uppercase leading-tight mb-1">{ind.label}</div>
              <div className="text-xl font-bold" {...fg(scoreColor(val, ind.inverse))}>
                {val != null ? (val > 0 ? '+' : '') + Math.round(val) : '—'}
              </div>
              {ind.inverse && <div className="text-[8px] text-gray-300 mt-0.5">inverted</div>}
            </div>
          );
        })}
      </div>

      {/* Two-column: Sector Rotation + Active Themes */}
      <div className="grid grid-cols-2 gap-4">

        {/* Sector Rotation — 2×2 Quadrant */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100 text-[10px] text-gray-400 tracking-widest uppercase">
            Sector Rotation
          </div>
          {sectors.length > 0 ? (
            <div className="p-3">
              {/* Axis labels */}
              <div className="grid grid-cols-2 gap-2 mb-2">
                <div className="text-[8px] text-emerald-600 font-semibold uppercase tracking-wider text-center">Leading / Improving</div>
                <div className="text-[8px] text-rose-400 font-semibold uppercase tracking-wider text-center">Weakening / Lagging</div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {/* Left: Leading + Improving */}
                <div className="space-y-1">
                  {sectors.filter((s: any) => ['leading', 'improving'].includes((s.quadrant || '').toLowerCase())).map((s: any, i: number) => {
                    const q = quadrantLabel(s.quadrant);
                    return (
                      <div key={i} className="flex items-center justify-between bg-emerald-50/60 rounded-lg px-2.5 py-1.5">
                        <div>
                          <div className="text-[10px] font-semibold text-gray-800 leading-tight">{s.sector}</div>
                          <div className="text-[8px] font-medium mt-0.5" {...fg(q.color)}>{q.label}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-xs font-bold font-mono" {...fg(rotationColor(s.rotation_score))}>{s.rotation_score?.toFixed(0)}</div>
                        </div>
                      </div>
                    );
                  })}
                  {sectors.filter((s: any) => ['leading', 'improving'].includes((s.quadrant || '').toLowerCase())).length === 0 && (
                    <div className="text-[10px] text-gray-300 text-center py-4">—</div>
                  )}
                </div>
                {/* Right: Weakening + Lagging */}
                <div className="space-y-1">
                  {sectors.filter((s: any) => ['weakening', 'lagging'].includes((s.quadrant || '').toLowerCase())).map((s: any, i: number) => {
                    const q = quadrantLabel(s.quadrant);
                    return (
                      <div key={i} className="flex items-center justify-between bg-rose-50/60 rounded-lg px-2.5 py-1.5">
                        <div>
                          <div className="text-[10px] font-semibold text-gray-800 leading-tight">{s.sector}</div>
                          <div className="text-[8px] font-medium mt-0.5" {...fg(q.color)}>{q.label}</div>
                        </div>
                        <div className="text-right">
                          <div className="text-xs font-bold font-mono" {...fg(rotationColor(s.rotation_score))}>{s.rotation_score?.toFixed(0)}</div>
                        </div>
                      </div>
                    );
                  })}
                  {sectors.filter((s: any) => ['weakening', 'lagging'].includes((s.quadrant || '').toLowerCase())).length === 0 && (
                    <div className="text-[10px] text-gray-300 text-center py-4">—</div>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-gray-400 text-xs text-center p-6">No sector rotation data</div>
          )}
        </div>

        {/* Right column: Themes + Intel */}
        <div className="space-y-4">

          {/* Active Investment Themes */}
          {themes.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 text-[10px] text-gray-400 tracking-widest uppercase">
                Active Investment Themes
              </div>
              <div className="divide-y divide-gray-50">
                {themes.map((t: any, i: number) => (
                  <div key={i} className="px-4 py-3">
                    <div className="flex items-center justify-between">
                      <div className="text-xs font-semibold text-gray-800">{t.theme}</div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-gray-400">{t.stock_count} stocks</span>
                        <span className="text-[10px] font-bold" {...fg(t.confidence >= 60 ? '#059669' : t.confidence >= 40 ? '#d97706' : '#9ca3af')}>
                          {t.confidence?.toFixed(0)}% confidence
                        </span>
                      </div>
                    </div>
                    {t.top_symbols && t.top_symbols.length > 0 && (
                      <div className="flex gap-1.5 mt-1.5">
                        {t.top_symbols.map((sym: string) => (
                          <span key={sym} className="text-[10px] font-mono bg-emerald-50 text-emerald-700 px-1.5 py-0.5 rounded">
                            {sym}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="text-[10px] text-gray-400 mt-1 capitalize">
                      Status: <span className="font-medium text-gray-600">{t.direction}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Intelligence Reports */}
          {intel.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 text-[10px] text-gray-400 tracking-widest uppercase">
                Recent Intelligence Reports
              </div>
              <div className="divide-y divide-gray-50">
                {intel.map((r: any, i: number) => (
                  <div key={i} className="px-4 py-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-gray-800 capitalize">{r.topic}</span>
                      <span className="text-[8px] text-gray-400 uppercase tracking-wider bg-gray-100 px-1.5 py-0.5 rounded">{r.type}</span>
                    </div>
                    {r.symbols && r.symbols.length > 0 && (
                      <div className="text-[10px] text-gray-400 mt-1">
                        {r.symbols.slice(0, 6).join(', ')}{r.symbols.length > 6 ? ' +more' : ''}
                      </div>
                    )}
                    <div className="text-[10px] text-gray-300 mt-0.5">
                      {r.date ? new Date(r.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Cross-cutting intel (narrative signals) */}
          {crossCutting.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 text-[10px] text-gray-400 tracking-widest uppercase">
                Cross-Cutting Signals
              </div>
              <div className="divide-y divide-gray-50">
                {crossCutting.map((item: any, i: number) => (
                  <div key={i} className="px-4 py-2.5 border-l-2 border-emerald-200">
                    <div className="flex items-center gap-2">
                      <span className="text-[8px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded uppercase tracking-wider font-semibold">
                        {item.source}
                      </span>
                      <span className="text-xs font-semibold text-gray-800">{item.headline}</span>
                    </div>
                    <div className="text-[10px] text-gray-500 mt-1">{item.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Empty state when no themes/intel */}
          {themes.length === 0 && intel.length === 0 && crossCutting.length === 0 && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 text-center">
              <div className="text-xs text-gray-400">Run the daily pipeline to populate themes and intelligence.</div>
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
