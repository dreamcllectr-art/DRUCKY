'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type WorldviewSignal,
  type WorldviewThesis,
  type WorldMacroIndicator,
} from '@/lib/api';

type Tab = 'expressions' | 'theses' | 'macro';

export default function WorldviewPage() {
  const [signals, setSignals] = useState<WorldviewSignal[]>([]);
  const [theses, setTheses] = useState<WorldviewThesis[]>([]);
  const [macroData, setMacroData] = useState<WorldMacroIndicator[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('expressions');

  useEffect(() => {
    Promise.all([
      api.worldview().catch(() => []),
      api.worldviewTheses().catch(() => []),
      api.worldMacro().catch(() => []),
    ]).then(([sigs, th, macro]) => {
      setSignals(sigs);
      setTheses(th);
      setMacroData(macro);
      setLoading(false);
    });
  }, []);

  // Group macro data by indicator for display
  const macroByIndicator = macroData.reduce<Record<string, WorldMacroIndicator[]>>((acc, m) => {
    if (!acc[m.indicator]) acc[m.indicator] = [];
    acc[m.indicator].push(m);
    return acc;
  }, {});

  const indicatorNames: Record<string, string> = {
    'NY.GDP.MKTP.KD.ZG': 'GDP Growth (%)',
    'NE.TRD.GNFS.ZS': 'Trade / GDP (%)',
    'GC.DOD.TOTL.GD.ZS': 'Govt Debt / GDP (%)',
    'BN.CAB.XOKA.GD.ZS': 'Current Account / GDP (%)',
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          LOADING WORLDVIEW MODEL...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          WORLDVIEW / GLOBAL MACRO
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          MACRO THESIS TO STOCK EXPRESSION — WORLD BANK / IMF DATA — SECTOR TILTS
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        <div
          onClick={() => setActiveTab('expressions')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'expressions' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-green">
            {signals.filter((s) => (s.thesis_alignment_score || 0) >= 50).length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">HIGH ALIGNMENT</div>
        </div>
        <div
          onClick={() => setActiveTab('expressions')}
          className="panel px-4 py-3 cursor-pointer transition-all hover:border-terminal-muted"
        >
          <div className="text-2xl font-display font-bold text-terminal-cyan">
            {signals.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            STOCK EXPRESSIONS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('theses')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'theses' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-amber">
            {theses.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">ACTIVE THESES</div>
        </div>
        <div
          onClick={() => setActiveTab('macro')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'macro' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-red">
            {Object.keys(macroByIndicator).length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            MACRO INDICATORS
          </div>
        </div>
      </div>

      {/* Stock Expressions Tab */}
      {activeTab === 'expressions' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              MACRO-TO-STOCK EXPRESSIONS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              How macro theses translate into specific stock positions via sector tilts
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-left py-3 px-2 font-normal">Sector</th>
                  <th className="text-right py-3 px-2 font-normal">Alignment</th>
                  <th className="text-center py-3 px-2 font-normal">Regime</th>
                  <th className="text-left py-3 px-2 font-normal">Sector Tilt</th>
                  <th className="text-left py-3 px-2 font-normal">Active Theses</th>
                  <th className="text-left py-3 px-4 font-normal">Narrative</th>
                </tr>
              </thead>
              <tbody>
                {signals.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center py-8 text-terminal-dim">
                      No worldview expressions. Run the pipeline to generate macro thesis signals.
                    </td>
                  </tr>
                ) : (
                  signals.map((s, i) => (
                    <tr
                      key={`wv-${s.symbol}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => (window.location.href = `/asset/${s.symbol}`)}
                    >
                      <td className="py-2.5 px-4">
                        <span className="font-mono font-bold text-terminal-green">{s.symbol}</span>
                        {s.company_name && (
                          <span className="ml-2 text-[9px] text-terminal-dim">{s.company_name}</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[10px] tracking-wider uppercase">
                        {s.sector || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span
                          className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                          style={{
                            backgroundColor:
                              (s.thesis_alignment_score || 0) >= 60
                                ? 'rgba(0,255,65,0.15)'
                                : (s.thesis_alignment_score || 0) >= 30
                                ? 'rgba(255,184,0,0.15)'
                                : 'rgba(255,255,255,0.05)',
                            color:
                              (s.thesis_alignment_score || 0) >= 60
                                ? '#00FF41'
                                : (s.thesis_alignment_score || 0) >= 30
                                ? '#FFB800'
                                : '#888',
                          }}
                        >
                          {s.thesis_alignment_score?.toFixed(0) || '—'}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-center text-[10px] text-terminal-dim uppercase">
                        {s.regime || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-cyan text-[10px]">
                        {s.sector_tilt || '—'}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-amber text-[10px] max-w-[200px] truncate">
                        {s.active_theses || '—'}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[300px] truncate">
                        {s.narrative || '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Theses Tab */}
      {activeTab === 'theses' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              ACTIVE MACRO THESES
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Current thesis-sector mappings and stock coverage counts
            </p>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 p-4">
            {theses.length === 0 ? (
              <div className="col-span-full text-center py-8 text-terminal-dim">
                No active theses.
              </div>
            ) : (
              theses.map((t, i) => (
                <div key={`thesis-${i}`} className="panel px-4 py-3">
                  <div className="text-xs font-bold text-terminal-amber tracking-wider uppercase">
                    {t.active_theses.replace(/_/g, ' ')}
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-[10px]">
                    <span className="text-terminal-cyan">
                      Sector: {t.sector_tilt}
                    </span>
                    <span className="text-terminal-dim">
                      {t.stock_count} stocks
                    </span>
                    <span className="text-terminal-green">
                      Avg alignment: {t.avg_alignment.toFixed(0)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* World Macro Tab */}
      {activeTab === 'macro' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              WORLD BANK / IMF INDICATORS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Structural macro data — GDP growth, trade openness, sovereign debt, current account balances
            </p>
          </div>
          <div className="space-y-4 p-4">
            {Object.keys(macroByIndicator).length === 0 ? (
              <div className="text-center py-8 text-terminal-dim">
                No World Bank / IMF data available.
              </div>
            ) : (
              Object.entries(macroByIndicator).map(([indicator, rows]) => {
                // Show top countries by most recent year
                const sorted = [...rows].sort((a, b) => b.year - a.year);
                const latestYear = sorted[0]?.year;
                const latest = sorted.filter((r) => r.year === latestYear).slice(0, 10);

                return (
                  <div key={indicator} className="panel px-4 py-3">
                    <div className="text-xs font-bold text-terminal-bright tracking-wider mb-2">
                      {indicatorNames[indicator] || indicator}
                      <span className="ml-2 text-terminal-dim font-normal text-[10px]">
                        ({latestYear})
                      </span>
                    </div>
                    <div className="grid grid-cols-5 gap-2">
                      {latest.map((r) => (
                        <div
                          key={`${indicator}-${r.country}`}
                          className="flex items-center justify-between text-[10px] px-2 py-1 bg-terminal-panel/50 rounded"
                        >
                          <span className="text-terminal-dim font-mono">{r.country}</span>
                          <span
                            className={`font-mono font-bold ${
                              r.value >= 0 ? 'text-terminal-green' : 'text-terminal-red'
                            }`}
                          >
                            {r.value?.toFixed(1)}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
