'use client';

import { useEffect, useState, useMemo } from 'react';
import { api, type SignalConflict, type ConflictSummary } from '@/lib/api';
import Link from 'next/link';

/* ═══ Helpers ═══ */
const severityColor = (s: string) => {
  if (s === 'critical' || s === 'CRITICAL') return '#FF073A';
  if (s === 'high' || s === 'HIGH') return '#FF8A65';
  if (s === 'medium' || s === 'MEDIUM') return '#FFB800';
  return '#555';
};

const severityBg = (s: string) => {
  if (s === 'critical' || s === 'CRITICAL') return 'rgba(255,7,58,0.08)';
  if (s === 'high' || s === 'HIGH') return 'rgba(255,138,101,0.08)';
  if (s === 'medium' || s === 'MEDIUM') return 'rgba(255,184,0,0.06)';
  return 'rgba(85,85,85,0.06)';
};

const gapBar = (score: number, maxScore = 100) => {
  const pct = Math.min(Math.abs(score) / maxScore * 100, 100);
  return pct;
};

type Tab = 'all' | 'critical' | 'summary';

/* ═══ Main Page ═══ */
export default function SignalConflictsPage() {
  const [conflicts, setConflicts] = useState<SignalConflict[]>([]);
  const [summary, setSummary] = useState<ConflictSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('all');
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);

  useEffect(() => {
    Promise.allSettled([
      api.signalConflicts(),
      api.signalConflictsSummary(),
    ]).then(([c, s]) => {
      if (c.status === 'fulfilled') setConflicts(c.value);
      if (s.status === 'fulfilled') setSummary(s.value);
      setLoading(false);
    });
  }, []);

  const criticalConflicts = useMemo(() =>
    conflicts.filter(c => c.severity === 'critical' || c.severity === 'CRITICAL' || c.severity === 'high' || c.severity === 'HIGH'),
    [conflicts]
  );

  const displayConflicts = tab === 'critical' ? criticalConflicts : conflicts;

  // Group by symbol for the expanded view
  const symbolGroups = useMemo(() => {
    const map = new Map<string, SignalConflict[]>();
    displayConflicts.forEach(c => {
      const arr = map.get(c.symbol) || [];
      arr.push(c);
      map.set(c.symbol, arr);
    });
    return Array.from(map.entries()).sort((a, b) => {
      // Sort by worst severity, then by count
      const sevOrder = (s: string) => s === 'critical' || s === 'CRITICAL' ? 3 : s === 'high' || s === 'HIGH' ? 2 : s === 'medium' || s === 'MEDIUM' ? 1 : 0;
      const aMax = Math.max(...a[1].map(c => sevOrder(c.severity)));
      const bMax = Math.max(...b[1].map(c => sevOrder(c.severity)));
      if (aMax !== bMax) return bMax - aMax;
      return b[1].length - a[1].length;
    });
  }, [displayConflicts]);

  const stats = useMemo(() => ({
    total: conflicts.length,
    critical: conflicts.filter(c => c.severity === 'critical' || c.severity === 'CRITICAL').length,
    high: conflicts.filter(c => c.severity === 'high' || c.severity === 'HIGH').length,
    medium: conflicts.filter(c => c.severity === 'medium' || c.severity === 'MEDIUM').length,
    uniqueSymbols: new Set(conflicts.map(c => c.symbol)).size,
    avgGap: conflicts.length > 0 ? conflicts.reduce((s, c) => s + c.score_gap, 0) / conflicts.length : 0,
  }), [conflicts]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full" role="status" aria-label="Loading conflict data">
        <div className="space-y-3 text-center">
          <div className="text-terminal-amber text-2xl font-display font-bold glow-amber animate-pulse">
            SCANNING CONFLICTS
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest">
            Detecting cross-signal contradictions...
          </div>
        </div>
      </div>
    );
  }

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'all', label: 'ALL CONFLICTS', count: conflicts.length },
    { key: 'critical', label: 'CRITICAL / HIGH', count: criticalConflicts.length },
    { key: 'summary', label: 'BY TYPE', count: summary.length },
  ];

  return (
    <div className="p-6 space-y-0">
      {/* ═══ Header ═══ */}
      <div className="pb-6">
        <h1 className="text-[22px] font-display font-bold text-terminal-bright tracking-wider">
          SIGNAL CONFLICTS
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1 opacity-60">
          Cross-module contradictions — where your signals disagree
        </p>
      </div>

      {/* ═══ Summary Strip ═══ */}
      <div className="grid grid-cols-5 gap-3 mb-6">
        <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '14px 16px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50">TOTAL</div>
          <div className="text-[18px] font-bold font-mono text-terminal-text mt-1">{stats.total}</div>
        </div>
        <div style={{ background: '#111', border: '1px solid rgba(255,7,58,0.15)', borderRadius: '3px', padding: '14px 16px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50">CRITICAL</div>
          <div className="text-[18px] font-bold font-mono mt-1" style={{ color: '#FF073A' }}>{stats.critical}</div>
        </div>
        <div style={{ background: '#111', border: '1px solid rgba(255,138,101,0.15)', borderRadius: '3px', padding: '14px 16px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50">HIGH</div>
          <div className="text-[18px] font-bold font-mono mt-1" style={{ color: '#FF8A65' }}>{stats.high}</div>
        </div>
        <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '14px 16px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50">SYMBOLS</div>
          <div className="text-[18px] font-bold font-mono text-terminal-text mt-1">{stats.uniqueSymbols}</div>
        </div>
        <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '14px 16px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-50">AVG GAP</div>
          <div className="text-[18px] font-bold font-mono text-terminal-amber mt-1">{stats.avgGap.toFixed(0)}pt</div>
        </div>
      </div>

      {/* ═══ Tabs ═══ */}
      <div className="flex gap-1 mb-5" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '1px' }}>
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className="transition-colors"
            style={{
              padding: '8px 16px',
              fontSize: '10px',
              letterSpacing: '0.12em',
              color: tab === t.key ? '#FFB800' : '#555',
              borderBottom: tab === t.key ? '2px solid #FFB800' : '2px solid transparent',
              background: 'transparent',
            }}
          >
            {t.label} ({t.count})
          </button>
        ))}
      </div>

      {/* ═══ Summary Tab ═══ */}
      {tab === 'summary' && (
        <div className="space-y-2">
          {summary.map(s => (
            <div
              key={`${s.conflict_type}-${s.severity}`}
              style={{
                background: '#111',
                border: `1px solid ${severityColor(s.severity)}20`,
                borderRadius: '3px',
                padding: '14px 20px',
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span
                    className="text-[9px] font-bold tracking-widest"
                    style={{
                      padding: '2px 8px',
                      borderRadius: '2px',
                      background: severityBg(s.severity),
                      border: `1px solid ${severityColor(s.severity)}30`,
                      color: severityColor(s.severity),
                    }}
                  >
                    {s.severity.toUpperCase()}
                  </span>
                  <span className="text-[11px] text-terminal-text font-medium tracking-wide">
                    {s.conflict_type.replace(/_/g, ' ').toUpperCase()}
                  </span>
                </div>
                <div className="flex items-center gap-4 text-[10px]">
                  <span className="text-terminal-dim">{s.count} conflict{s.count > 1 ? 's' : ''}</span>
                  <span className="font-mono text-terminal-amber">avg gap: {s.avg_gap.toFixed(0)}pt</span>
                </div>
              </div>
            </div>
          ))}
          {summary.length === 0 && (
            <div className="text-center py-16 text-terminal-dim text-sm">No conflict types found</div>
          )}
        </div>
      )}

      {/* ═══ Conflict List ═══ */}
      {tab !== 'summary' && (
        <div className="space-y-2">
          {symbolGroups.length === 0 && (
            <div className="text-center py-16">
              <div className="text-[40px] mb-4 opacity-10">✓</div>
              <div className="text-terminal-green text-sm font-medium">No conflicts detected</div>
              <div className="text-[10px] text-terminal-dim opacity-50 mt-1">All modules are in agreement</div>
            </div>
          )}
          {symbolGroups.map(([symbol, symbolConflicts]) => {
            const isExpanded = expandedSymbol === symbol;
            const worstSeverity = symbolConflicts.reduce((worst, c) => {
              const order = ['low', 'medium', 'high', 'HIGH', 'critical', 'CRITICAL'];
              return order.indexOf(c.severity) > order.indexOf(worst) ? c.severity : worst;
            }, 'low');

            return (
              <div key={symbol}>
                <button
                  onClick={() => setExpandedSymbol(isExpanded ? null : symbol)}
                  className="w-full text-left transition-all duration-200"
                  style={{
                    background: '#111',
                    border: `1px solid ${isExpanded ? severityColor(worstSeverity) + '30' : 'rgba(255,255,255,0.04)'}`,
                    borderRadius: '3px',
                    padding: '14px 20px',
                  }}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Link
                        href={`/asset/${symbol}`}
                        className="text-[13px] font-bold tracking-wide hover:underline"
                        style={{ color: '#00FF41' }}
                        onClick={e => e.stopPropagation()}
                      >
                        {symbol}
                      </Link>
                      <span
                        className="text-[9px] font-bold tracking-widest"
                        style={{
                          padding: '2px 8px',
                          borderRadius: '2px',
                          background: severityBg(worstSeverity),
                          border: `1px solid ${severityColor(worstSeverity)}30`,
                          color: severityColor(worstSeverity),
                        }}
                      >
                        {worstSeverity.toUpperCase()}
                      </span>
                      <span className="text-[10px] text-terminal-dim">
                        {symbolConflicts.length} conflict{symbolConflicts.length > 1 ? 's' : ''}
                      </span>
                    </div>
                    <div className="flex items-center gap-4">
                      {/* Preview: first conflict modules */}
                      <span className="text-[9px] text-terminal-dim opacity-60">
                        {symbolConflicts[0].module_a} vs {symbolConflicts[0].module_b}
                      </span>
                      <span className="text-terminal-dim text-[10px]">
                        {isExpanded ? '▾' : '▸'}
                      </span>
                    </div>
                  </div>
                </button>

                {isExpanded && (
                  <div className="mt-1 space-y-1">
                    {symbolConflicts.map((c, i) => (
                      <div
                        key={i}
                        style={{
                          background: 'rgba(17,17,17,0.6)',
                          border: '1px solid rgba(255,255,255,0.03)',
                          borderRadius: '3px',
                          padding: '12px 20px',
                        }}
                      >
                        <div className="flex items-center gap-3 mb-2">
                          <span className="text-[9px] text-terminal-dim tracking-wider">
                            {c.conflict_type.replace(/_/g, ' ').toUpperCase()}
                          </span>
                          <span
                            className="text-[8px] tracking-widest"
                            style={{ color: severityColor(c.severity) }}
                          >
                            {c.severity.toUpperCase()}
                          </span>
                        </div>

                        {/* Module vs Module visualization */}
                        <div className="flex items-center gap-4 mb-2">
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-[10px] text-terminal-text">{c.module_a}</span>
                              <span className="text-[10px] font-mono font-bold" style={{ color: '#00FF41' }}>
                                {c.module_a_score.toFixed(0)}
                              </span>
                            </div>
                            <div className="h-[4px] rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${gapBar(c.module_a_score)}%`,
                                  background: '#00FF41',
                                  opacity: 0.6,
                                }}
                              />
                            </div>
                          </div>
                          <div className="text-[10px] font-mono font-bold text-terminal-amber flex-shrink-0 w-12 text-center">
                            {c.score_gap.toFixed(0)}pt
                          </div>
                          <div className="flex-1">
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-[10px] text-terminal-text">{c.module_b}</span>
                              <span className="text-[10px] font-mono font-bold" style={{ color: '#FF073A' }}>
                                {c.module_b_score.toFixed(0)}
                              </span>
                            </div>
                            <div className="h-[4px] rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${gapBar(c.module_b_score)}%`,
                                  background: '#FF073A',
                                  opacity: 0.6,
                                }}
                              />
                            </div>
                          </div>
                        </div>

                        {c.description && (
                          <p className="text-[10px] text-terminal-dim opacity-60 leading-relaxed">
                            {c.description}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
