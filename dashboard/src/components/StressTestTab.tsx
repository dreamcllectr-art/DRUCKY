'use client';
import { useEffect, useState } from 'react';
import { api, type StressTestResult, type ConcentrationRisk } from '@/lib/api';
import { cs, fg, bgFg, barW } from '@/lib/styles';

const impactColor = (v: number) => v <= -15 ? '#e11d48' : v <= -10 ? '#ea580c' : v <= -5 ? '#d97706' : v <= 0 ? '#10b981' : '#059669';

export default function StressTestTab() {
  const [scenarios, setScenarios] = useState<StressTestResult[]>([]);
  const [concentration, setConcentration] = useState<ConcentrationRisk | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([api.stressTest(), api.stressTestConcentration()]).then(([s, c]) => {
      if (s.status === 'fulfilled') setScenarios(s.value);
      if (c.status === 'fulfilled') setConcentration(c.value);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading stress tests...</div>;
  if (scenarios.length === 0) return <div className="text-center py-16 text-gray-500">No stress test results. Run the pipeline.</div>;

  const worstScenario = scenarios.reduce((w, s) => s.portfolio_impact_pct < (w?.portfolio_impact_pct ?? 0) ? s : w, scenarios[0]);
  const avgImpact = scenarios.reduce((sum, s) => sum + s.portfolio_impact_pct, 0) / scenarios.length;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white border border-[rgba(225,29,72,0.15)] rounded p-4"><div className="text-[9px] text-gray-500 tracking-widest opacity-50 mb-2">WORST SCENARIO</div><div className="text-[20px] font-bold font-mono text-[#e11d48]">{worstScenario?.portfolio_impact_pct.toFixed(1)}%</div><div className="text-[10px] text-gray-500 mt-1">{worstScenario?.scenario_name ?? worstScenario?.scenario}</div></div>
        <div className="bg-white border border-[rgba(217,119,6,0.15)] rounded p-4"><div className="text-[9px] text-gray-500 tracking-widest opacity-50 mb-2">AVG IMPACT</div><div className="text-[20px] font-bold font-mono" {...fg(impactColor(avgImpact))}>{avgImpact.toFixed(1)}%</div><div className="text-[10px] text-gray-500 mt-1">{scenarios.length} scenarios</div></div>
        <div className="bg-white border border-gray-200 rounded p-4"><div className="text-[9px] text-gray-500 tracking-widest opacity-50 mb-2">CONCENTRATION</div>{concentration?.hhi != null ? <><div className="text-[20px] font-bold font-mono" {...fg(concentration.hhi >= 2500 ? '#e11d48' : concentration.hhi >= 1500 ? '#d97706' : '#059669')}>{concentration.concentration_level ?? (concentration.hhi >= 2500 ? 'CONCENTRATED' : 'DIVERSIFIED')}</div><div className="text-[10px] text-gray-500 mt-1">HHI: {concentration.hhi.toFixed(0)}</div></> : <div className="text-[20px] font-bold text-gray-500">N/A</div>}</div>
      </div>
      <div className="space-y-3">
        {[...scenarios].sort((a, b) => a.portfolio_impact_pct - b.portfolio_impact_pct).map(s => (
          <div key={s.scenario}>
            <button onClick={() => setExpanded(expanded === s.scenario ? null : s.scenario)} className="w-full text-left bg-white border border-gray-200 rounded p-4 transition-all">
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-[12px] font-bold text-gray-900 tracking-wide">{(s.scenario_name ?? s.scenario).toUpperCase()}</span>
                    <span className="text-[8px] font-bold tracking-widest px-1.5 py-0.5 rounded" {...cs({ background: `${impactColor(s.portfolio_impact_pct)}12`, border: `1px solid ${impactColor(s.portfolio_impact_pct)}30`, color: impactColor(s.portfolio_impact_pct) })}>{s.portfolio_impact_pct <= -15 ? 'SEVERE' : s.portfolio_impact_pct <= -5 ? 'MODERATE' : 'LOW'}</span>
                  </div>
                  <div className="flex items-center gap-3 w-full">
                    <div className="flex-1 h-[6px] rounded-full overflow-hidden bg-gray-50"><div className="h-full rounded-full transition-all duration-700" {...cs({ width: `${Math.min(Math.abs(s.portfolio_impact_pct) / 30 * 100, 100)}%`, background: impactColor(s.portfolio_impact_pct) })} /></div>
                    <span className="text-[13px] font-mono font-bold w-16 text-right" {...fg(impactColor(s.portfolio_impact_pct))}>{s.portfolio_impact_pct > 0 ? '+' : ''}{s.portfolio_impact_pct.toFixed(1)}%</span>
                  </div>
                </div>
              </div>
            </button>
            {expanded === s.scenario && (
              <div className="mt-1 bg-gray-50 border border-gray-200 rounded p-4">
                <div className="grid grid-cols-2 gap-4">
                  {s.worst_hit && <div><div className="text-[8px] text-gray-500 tracking-widest opacity-40 mb-1">WORST HIT</div><div className="text-[11px] text-rose-600">{s.worst_hit}</div></div>}
                  {s.best_positioned && <div><div className="text-[8px] text-gray-500 tracking-widest opacity-40 mb-1">BEST POSITIONED</div><div className="text-[11px] text-emerald-600">{s.best_positioned}</div></div>}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
