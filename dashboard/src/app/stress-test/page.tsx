'use client';

import { useEffect, useState } from 'react';
import { api, type StressTestResult, type ConcentrationRisk } from '@/lib/api';

/* ═══ Helpers ═══ */
const impactColor = (v: number) =>
  v <= -15 ? '#FF073A' : v <= -10 ? '#FF8A65' : v <= -5 ? '#FFB800' : v <= 0 ? '#69F0AE' : '#00FF41';

const impactLabel = (v: number) =>
  v <= -15 ? 'SEVERE' : v <= -10 ? 'HIGH' : v <= -5 ? 'MODERATE' : v <= 0 ? 'LOW' : 'POSITIVE';

const concentrationColor = (hhi: number) =>
  hhi >= 2500 ? '#FF073A' : hhi >= 1500 ? '#FFB800' : '#00FF41';

const concentrationLabel = (hhi: number) =>
  hhi >= 2500 ? 'CONCENTRATED' : hhi >= 1500 ? 'MODERATE' : 'DIVERSIFIED';

const scenarioIcon: Record<string, string> = {
  recession: '📉', rate_shock: '📈', usd_rally: '💵', china_slowdown: '🌏',
  credit_crunch: '💳', inflation_spike: '🔥', tech_selloff: '💻',
};

/* ═══ Impact Bar ═══ */
function ImpactBar({ value, maxAbs = 30 }: { value: number; maxAbs?: number }) {
  const pct = Math.min(Math.abs(value) / maxAbs * 100, 100);
  const color = impactColor(value);

  return (
    <div className="flex items-center gap-3 w-full">
      <div className="flex-1 h-[6px] rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{
            width: `${pct}%`,
            background: color,
            boxShadow: `0 0 8px ${color}40`,
          }}
        />
      </div>
      <span
        className="text-[13px] font-mono font-bold flex-shrink-0 w-16 text-right"
        style={{ color }}
      >
        {value > 0 ? '+' : ''}{value.toFixed(1)}%
      </span>
    </div>
  );
}

/* ═══ HHI Gauge ═══ */
function HHIGauge({ hhi }: { hhi: number }) {
  const maxHHI = 5000;
  const pct = Math.min(hhi / maxHHI * 100, 100);
  const color = concentrationColor(hhi);

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative w-full h-[8px] rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
        <div className="absolute left-[30%] top-0 w-px h-full" style={{ background: 'rgba(255,255,255,0.1)' }} />
        <div className="absolute left-[50%] top-0 w-px h-full" style={{ background: 'rgba(255,255,255,0.1)' }} />
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${pct}%`, background: color, boxShadow: `0 0 8px ${color}40` }}
        />
      </div>
      <div className="flex justify-between w-full text-[8px] text-terminal-dim tracking-widest opacity-40">
        <span>DIVERSIFIED</span>
        <span>MODERATE</span>
        <span>CONCENTRATED</span>
      </div>
    </div>
  );
}

/* ═══ Main Page ═══ */
export default function StressTestPage() {
  const [scenarios, setScenarios] = useState<StressTestResult[]>([]);
  const [concentration, setConcentration] = useState<ConcentrationRisk | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      api.stressTest(),
      api.stressTestConcentration(),
    ]).then(([s, c]) => {
      if (s.status === 'fulfilled') setScenarios(s.value);
      if (c.status === 'fulfilled') setConcentration(c.value);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full" role="status" aria-label="Loading stress test data">
        <div className="space-y-3 text-center">
          <div className="text-terminal-red text-2xl font-display font-bold glow-red animate-pulse">
            STRESS TESTING
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest">
            Running macro shock scenarios...
          </div>
        </div>
      </div>
    );
  }

  if (scenarios.length === 0) {
    return (
      <div className="p-6">
        <h1 className="text-[22px] font-display font-bold text-terminal-bright tracking-wider mb-2">
          STRESS TEST
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest opacity-60 mb-12">
          Portfolio resilience under macro shock scenarios
        </p>
        <div className="text-center py-20">
          <div className="text-[40px] mb-4 opacity-20">⊗</div>
          <div className="text-terminal-dim text-sm mb-2">No stress test results yet</div>
          <div className="text-[10px] text-terminal-dim opacity-50">
            Run the daily pipeline to generate scenario analysis
          </div>
        </div>
      </div>
    );
  }

  const worstScenario = scenarios.reduce((w, s) =>
    s.portfolio_impact_pct < (w?.portfolio_impact_pct ?? 0) ? s : w, scenarios[0]);
  const avgImpact = scenarios.reduce((sum, s) => sum + s.portfolio_impact_pct, 0) / scenarios.length;

  return (
    <div className="p-6 space-y-0">
      {/* ═══ Header ═══ */}
      <div className="pb-6">
        <h1 className="text-[22px] font-display font-bold text-terminal-bright tracking-wider">
          STRESS TEST
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1 opacity-60">
          Portfolio resilience under macro shock scenarios
        </p>
      </div>

      {/* ═══ Summary Cards ═══ */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        {/* Worst Case */}
        <div style={{ background: '#111', border: '1px solid rgba(255,7,58,0.15)', borderRadius: '3px', padding: '20px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50 mb-2">WORST SCENARIO</div>
          <div className="text-[20px] font-bold font-mono" style={{ color: '#FF073A' }}>
            {worstScenario?.portfolio_impact_pct.toFixed(1)}%
          </div>
          <div className="text-[10px] text-terminal-dim mt-1">
            {worstScenario?.scenario_name ?? worstScenario?.scenario}
          </div>
        </div>

        {/* Average Impact */}
        <div style={{ background: '#111', border: '1px solid rgba(255,184,0,0.15)', borderRadius: '3px', padding: '20px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50 mb-2">AVG IMPACT</div>
          <div className="text-[20px] font-bold font-mono" style={{ color: impactColor(avgImpact) }}>
            {avgImpact.toFixed(1)}%
          </div>
          <div className="text-[10px] text-terminal-dim mt-1">
            Across {scenarios.length} scenarios
          </div>
        </div>

        {/* Concentration */}
        <div style={{ background: '#111', border: `1px solid ${concentration?.hhi ? concentrationColor(concentration.hhi) + '25' : 'rgba(255,255,255,0.04)'}`, borderRadius: '3px', padding: '20px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50 mb-2">CONCENTRATION</div>
          {concentration?.hhi != null ? (
            <>
              <div className="text-[20px] font-bold font-mono" style={{ color: concentrationColor(concentration.hhi) }}>
                {concentration.concentration_level ?? concentrationLabel(concentration.hhi)}
              </div>
              <div className="text-[10px] text-terminal-dim mt-1">
                HHI: {concentration.hhi.toFixed(0)} — Top: {concentration.top_sector} ({concentration.top_sector_pct?.toFixed(0)}%)
              </div>
            </>
          ) : (
            <div className="text-[20px] font-bold text-terminal-dim">N/A</div>
          )}
        </div>
      </div>

      {/* ═══ HHI Gauge ═══ */}
      {concentration?.hhi != null && (
        <div className="mb-8" style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '20px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50 mb-4">HERFINDAHL-HIRSCHMAN INDEX</div>
          <HHIGauge hhi={concentration.hhi} />
          {concentration.details && (
            <div className="mt-4 flex flex-wrap gap-2">
              {(() => {
                try {
                  const sectors = JSON.parse(concentration.details);
                  return Object.entries(sectors as Record<string, number>)
                    .sort(([, a], [, b]) => (b as number) - (a as number))
                    .slice(0, 8)
                    .map(([sector, pct]) => (
                      <div key={sector} className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full" style={{ background: (pct as number) > 25 ? '#FF073A' : (pct as number) > 15 ? '#FFB800' : '#00FF41', opacity: 0.6 }} />
                        <span className="text-[9px] text-terminal-dim">{sector}</span>
                        <span className="text-[9px] font-mono text-terminal-text">{(pct as number).toFixed(0)}%</span>
                      </div>
                    ));
                } catch { return null; }
              })()}
            </div>
          )}
        </div>
      )}

      {/* ═══ Scenario List ═══ */}
      <div className="space-y-3">
        <div className="text-[9px] text-terminal-dim tracking-widest opacity-40 mb-2">SCENARIOS</div>
        {[...scenarios]
          .sort((a, b) => a.portfolio_impact_pct - b.portfolio_impact_pct)
          .map(s => {
            const isExpanded = expanded === s.scenario;
            const label = impactLabel(s.portfolio_impact_pct);

            return (
              <div key={s.scenario}>
                <button
                  onClick={() => setExpanded(isExpanded ? null : s.scenario)}
                  className="w-full text-left transition-all duration-200"
                  style={{
                    background: '#111',
                    border: `1px solid ${isExpanded ? impactColor(s.portfolio_impact_pct) + '30' : 'rgba(255,255,255,0.04)'}`,
                    borderRadius: '3px',
                    padding: '16px 20px',
                  }}
                >
                  <div className="flex items-center gap-4">
                    <span className="text-[16px] flex-shrink-0">{scenarioIcon[s.scenario] ?? '⊗'}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-[12px] font-bold text-terminal-bright tracking-wide">
                          {(s.scenario_name ?? s.scenario).toUpperCase()}
                        </span>
                        <span
                          className="text-[8px] font-bold tracking-widest"
                          style={{
                            padding: '2px 6px',
                            borderRadius: '2px',
                            background: `${impactColor(s.portfolio_impact_pct)}12`,
                            border: `1px solid ${impactColor(s.portfolio_impact_pct)}30`,
                            color: impactColor(s.portfolio_impact_pct),
                          }}
                        >
                          {label}
                        </span>
                        {s.position_count > 0 && (
                          <span className="text-[9px] text-terminal-dim">{s.position_count} positions affected</span>
                        )}
                      </div>
                      <ImpactBar value={s.portfolio_impact_pct} />
                    </div>
                    <span className="text-terminal-dim text-[10px] flex-shrink-0">
                      {isExpanded ? '▾' : '▸'}
                    </span>
                  </div>
                </button>

                {/* Expanded Detail */}
                {isExpanded && (
                  <div
                    className="mt-1 overflow-hidden"
                    style={{
                      background: 'rgba(17,17,17,0.8)',
                      border: '1px solid rgba(255,255,255,0.04)',
                      borderRadius: '3px',
                      padding: '16px 20px',
                    }}
                  >
                    <div className="grid grid-cols-2 gap-4 mb-3">
                      {s.worst_hit && (
                        <div>
                          <div className="text-[8px] text-terminal-dim tracking-widest opacity-40 mb-1">WORST HIT</div>
                          <div className="text-[11px] text-terminal-red">{s.worst_hit}</div>
                        </div>
                      )}
                      {s.best_positioned && (
                        <div>
                          <div className="text-[8px] text-terminal-dim tracking-widest opacity-40 mb-1">BEST POSITIONED</div>
                          <div className="text-[11px] text-terminal-green">{s.best_positioned}</div>
                        </div>
                      )}
                    </div>
                    {/* Position details if available */}
                    {s.position_details && (() => {
                      try {
                        const positions = JSON.parse(s.position_details) as Array<Record<string, unknown>>;
                        if (!Array.isArray(positions) || positions.length === 0) return null;
                        return (
                          <div className="mt-2">
                            <div className="text-[8px] text-terminal-dim tracking-widest opacity-40 mb-2">POSITION IMPACTS</div>
                            <div className="grid grid-cols-3 gap-1.5">
                              {positions.slice(0, 12).map((p, i) => (
                                <div
                                  key={i}
                                  className="flex items-center justify-between"
                                  style={{
                                    padding: '4px 8px',
                                    background: 'rgba(255,255,255,0.02)',
                                    borderRadius: '2px',
                                  }}
                                >
                                  <span className="text-[9px] text-terminal-text font-mono">
                                    {String(p.symbol ?? p.ticker ?? '')}
                                  </span>
                                  <span
                                    className="text-[9px] font-mono font-bold"
                                    style={{ color: impactColor(Number(p.impact_pct ?? p.impact ?? 0)) }}
                                  >
                                    {Number(p.impact_pct ?? p.impact ?? 0).toFixed(1)}%
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      } catch { return null; }
                    })()}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}
