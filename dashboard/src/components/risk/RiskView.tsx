'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { EdgeDecay } from '@/lib/api';
import { fg, cs } from '@/lib/styles';

export default function RiskView() {
  const [overview, setOverview] = useState<any>(null);
  const [edgeDecay, setEdgeDecay] = useState<EdgeDecay[]>([]);
  const [trackRecord, setTrackRecord] = useState<any[]>([]);
  const [stress, setStress] = useState<any[]>([]);
  const [conflicts, setConflicts] = useState<any[]>([]);
  const [weights, setWeights] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.riskOverview(),
      api.riskEdgeDecay(),
      api.riskTrackRecord(),
      api.stressTest(),
      api.signalConflicts(),
      api.performanceWeightHistory(),
    ]).then(([ov, ed, tr, st, co, wt]) => {
      setOverview(ov); setEdgeDecay(ed); setTrackRecord(tr); setStress(st); setConflicts(co); setWeights(wt);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-400 text-sm p-8 text-center">Loading risk overview...</div>;

  const concentration = overview?.concentration || {};

  return (
    <div className="space-y-6">
      {/* Exposure Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Exposure', value: overview?.total_exposure ? `$${(overview.total_exposure / 1000).toFixed(0)}k` : '\u2014', sub: overview?.position_count ? `${overview.position_count} positions` : 'No positions \u2014 add via Journal' },
          { label: 'Concentration (HHI)', value: concentration.hhi?.toFixed(0) || '\u2014', sub: concentration.concentration_level || 'N/A', color: concentration.concentration_level === 'HIGH' ? '#e11d48' : undefined },
          { label: 'Edge Health', value: `${overview?.edge_health || 0} / 24`, sub: 'modules with +IC', color: (overview?.edge_health || 0) >= 15 ? '#059669' : '#d97706' },
          { label: 'Top Sector', value: concentration.top_sector || '\u2014', sub: concentration.top_sector_pct ? `${(concentration.top_sector_pct * 100).toFixed(0)}% weight` : '' },
        ].map(card => (
          <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
            <div className="text-[9px] text-gray-400 tracking-widest uppercase">{card.label}</div>
            <div className="text-xl font-bold mt-1" {...fg(card.color || '#1f2937')}>{card.value}</div>
            <div className="text-[10px] text-gray-400 mt-0.5">{card.sub}</div>
          </div>
        ))}
      </div>

      {/* Stress Scenarios */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Stress Scenarios</div>
        {stress.length > 0 ? (
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-100 text-[8px] text-gray-400 tracking-widest uppercase">
                <th className="text-left py-2">Scenario</th>
                <th className="text-right py-2">Portfolio Impact</th>
                <th className="text-left py-2 px-4">Worst Hit</th>
                <th className="text-left py-2">Best Positioned</th>
              </tr>
            </thead>
            <tbody>
              {stress.map((s, i) => (
                <tr key={i} className="border-b border-gray-50">
                  <td className="py-2 font-medium text-gray-700">{s.scenario_name || s.scenario}</td>
                  <td className="py-2 text-right font-mono font-bold" {...fg(s.portfolio_impact_pct < -5 ? '#e11d48' : s.portfolio_impact_pct < 0 ? '#d97706' : '#059669')}>
                    {s.portfolio_impact_pct?.toFixed(1)}%
                  </td>
                  <td className="py-2 px-4 text-gray-500">{s.worst_hit}</td>
                  <td className="py-2 text-gray-500">{s.best_positioned}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-[10px] text-gray-400 text-center py-4">No stress test results yet. Add positions via Journal to see portfolio stress scenarios.</div>
        )}
      </div>

      {/* Signal Conflicts */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Active Signal Conflicts ({conflicts.length})</div>
        {conflicts.length > 0 ? (
          <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
            {conflicts.slice(0, 20).map((c, i) => (
              <div key={i} className={`text-[10px] rounded px-3 py-1.5 ${c.severity === 'HIGH' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-700'}`}>
                <span className="font-semibold">{c.symbol}</span>: {c.description}
                <span className="text-gray-400 ml-2">({c.module_a} vs {c.module_b}, gap: {c.score_gap?.toFixed(0)})</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[10px] text-gray-400 text-center py-4">No signal conflicts detected across modules.</div>
        )}
      </div>

      {/* Edge Decay */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Module Edge (IC at 20d)</div>
        {edgeDecay.length > 0 ? (
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-100 text-[8px] text-gray-400 tracking-widest uppercase">
                <th className="text-left py-2">Module</th>
                <th className="text-right py-2">Mean IC</th>
                <th className="text-right py-2">IR</th>
                <th className="text-right py-2">+IC Rate</th>
                <th className="text-right py-2">Samples</th>
                <th className="text-center py-2">Sig?</th>
              </tr>
            </thead>
            <tbody>
              {edgeDecay.filter(e => e.horizon_days === 20).map((e, i) => (
                <tr key={i} className="border-b border-gray-50">
                  <td className="py-1.5 text-gray-700 font-medium uppercase text-[9px] tracking-wider">{e.module.replace(/_/g, ' ')}</td>
                  <td className="py-1.5 text-right font-mono" {...fg(e.mean_ic != null && e.mean_ic > 0 ? '#059669' : '#e11d48')}>
                    {e.mean_ic?.toFixed(3) || '\u2014'}
                  </td>
                  <td className="py-1.5 text-right font-mono text-gray-600">{e.information_ratio?.toFixed(2) || '\u2014'}</td>
                  <td className="py-1.5 text-right font-mono text-gray-600">{e.ic_positive_pct != null ? `${(e.ic_positive_pct * 100).toFixed(0)}%` : '\u2014'}</td>
                  <td className="py-1.5 text-right text-gray-400">{e.n_dates}</td>
                  <td className="py-1.5 text-center">{e.is_significant ? '\u2713' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="text-[10px] text-gray-400 text-center py-4">Edge decay data will appear after sufficient pipeline runs. Tracks information coefficient (IC) by module over time.</div>
        )}
      </div>

      {/* Track Record */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Monthly Track Record</div>
        {trackRecord.length > 0 ? (
          <div className="grid grid-cols-6 md:grid-cols-12 gap-1">
            {trackRecord.slice(0, 24).map((m, i) => {
              const wr = m.total_signals > 0 && m.wins_20d != null ? (m.wins_20d / m.total_signals) * 100 : 0;
              return (
                <div key={i} className="text-center">
                  <div
                    className="h-8 rounded-sm flex items-center justify-center text-[8px] font-mono font-bold text-white"
                    {...cs({ backgroundColor: wr >= 60 ? '#059669' : wr >= 45 ? '#d97706' : wr > 0 ? '#e11d48' : '#e5e7eb' })}
                  >
                    {wr > 0 ? `${wr.toFixed(0)}%` : ''}
                  </div>
                  <div className="text-[7px] text-gray-400 mt-0.5">{m.month?.slice(5) || ''}</div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-[10px] text-gray-400 text-center py-4">No track record data yet. Monthly win rates will populate as signals mature past their 20-day horizon.</div>
        )}
      </div>
    </div>
  );
}
