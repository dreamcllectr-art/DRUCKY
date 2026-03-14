'use client';

import React, { useEffect, useState } from 'react';
import {
  api,
  type PerformanceSummary,
  type ModulePerformance,
  type TrackRecordMonth,
  type WeightHistoryEntry,
} from '@/lib/api';

// ── Error Boundary ──
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="p-8">
          <div className="panel p-6 text-center">
            <div className="text-red-400 mb-2">Something went wrong</div>
            <div className="text-sm text-terminal-dim mb-4">{this.state.error.message}</div>
            <button
              onClick={() => this.setState({ error: null })}
              className="px-4 py-2 text-xs font-display text-terminal-green border border-terminal-green rounded hover:bg-terminal-green/10"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

const TABS = [
  { key: 'overview', label: 'OVERVIEW' },
  { key: 'modules', label: 'MODULE LEADERBOARD' },
  { key: 'track-record', label: 'TRACK RECORD' },
  { key: 'weights', label: 'WEIGHT EVOLUTION' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

// ── Stat Card ──
function StatCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="panel p-4">
      <div className="text-[10px] text-terminal-dim tracking-[0.2em] uppercase mb-1">{label}</div>
      <div className="text-2xl font-display font-bold" style={{ color: color || '#00FF41' }}>
        {value}
      </div>
      {sub && <div className="text-xs text-terminal-dim mt-1">{sub}</div>}
    </div>
  );
}

// ── Win Rate Bar ──
function WinRateBar({ rate, n }: { rate: number; n: number }) {
  const color = rate >= 55 ? '#00FF41' : rate >= 45 ? '#FFB800' : '#FF073A';
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 bg-terminal-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-700"
          style={{ width: `${Math.min(100, rate)}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-mono" style={{ color }}>
        {rate.toFixed(1)}%
      </span>
      <span className="text-[10px] text-terminal-dim">n={n}</span>
    </div>
  );
}

// ── Data Sufficiency Indicator ──
function SufficiencyBadge({ sufficient, days, signals }: { sufficient: boolean; days: number; signals: number }) {
  if (sufficient) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#00FF4110] border border-[#00FF4130]">
        <div className="w-2 h-2 rounded-full bg-[#00FF41] animate-pulse" />
        <span className="text-xs text-[#00FF41] font-display tracking-wider">ADAPTIVE WEIGHTS ACTIVE</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#FFB80010] border border-[#FFB80030]">
      <div className="w-2 h-2 rounded-full bg-[#FFB800]" />
      <span className="text-xs text-[#FFB800] font-display tracking-wider">
        COLLECTING DATA — {days}d / {signals} signals
      </span>
    </div>
  );
}

// ── Overview Tab ──
function OverviewTab({ summary }: { summary: PerformanceSummary }) {
  const resolved = summary.resolved_by_window;
  const bestWindow = resolved['5d'] > 0 ? '5d' : resolved['20d'] > 0 ? '20d' : '30d';

  return (
    <div className="space-y-6">
      {/* Top stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Signals" value={summary.total_signals.toLocaleString()} sub={`Since ${summary.first_signal_date || '—'}`} />
        <StatCard label="Days Running" value={`${summary.days_running}`} sub="Data collection period" />
        <StatCard
          label={`Resolved (${bestWindow})`}
          value={`${resolved[bestWindow] || 0}`}
          sub={`Of ${summary.total_signals} total`}
        />
        <StatCard
          label="Optimizer Status"
          value={summary.data_sufficient ? 'ACTIVE' : 'COLLECTING'}
          color={summary.data_sufficient ? '#00FF41' : '#FFB800'}
          sub={summary.latest_optimizer?.action || 'Awaiting data'}
        />
      </div>

      {/* Sufficiency badge */}
      <SufficiencyBadge
        sufficient={summary.data_sufficient}
        days={summary.days_running}
        signals={summary.total_signals}
      />

      {/* Conviction breakdown */}
      <div className="panel p-4">
        <h3 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-4">
          WIN RATE BY CONVICTION LEVEL
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[10px] text-terminal-dim tracking-wider">
                <th className="text-left pb-2">LEVEL</th>
                <th className="text-right pb-2">5D WIN%</th>
                <th className="text-right pb-2">5D AVG</th>
                <th className="text-right pb-2">20D WIN%</th>
                <th className="text-right pb-2">20D AVG</th>
                <th className="text-right pb-2">30D WIN%</th>
                <th className="text-right pb-2">30D AVG</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_conviction.map((c) => (
                <tr key={c.level} className="border-t border-terminal-border">
                  <td className="py-2 font-display font-bold text-terminal-green">{c.level}</td>
                  {[5, 20, 30].map((d) => {
                    const wr = (c as Record<string, number | undefined>)[`win_rate_${d}d`];
                    const ar = (c as Record<string, number | undefined>)[`avg_return_${d}d`];
                    const wrColor = wr !== undefined ? (wr >= 55 ? '#00FF41' : wr >= 45 ? '#FFB800' : '#FF073A') : '#666';
                    const arColor = ar !== undefined ? (ar > 0 ? '#00FF41' : '#FF073A') : '#666';
                    return (
                      <React.Fragment key={d}>
                        <td className="py-2 text-right font-mono" style={{ color: wrColor }}>
                          {wr !== undefined ? `${wr.toFixed(1)}%` : '—'}
                        </td>
                        <td className="py-2 text-right font-mono" style={{ color: arColor }}>
                          {ar !== undefined ? `${ar > 0 ? '+' : ''}${ar.toFixed(2)}%` : '—'}
                        </td>
                      </React.Fragment>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Resolved signals by window */}
      <div className="panel p-4">
        <h3 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-3">
          RESOLVED SIGNALS BY HOLDING PERIOD
        </h3>
        <div className="grid grid-cols-7 gap-2">
          {Object.entries(resolved).map(([window, count]) => (
            <div key={window} className="text-center">
              <div className="text-lg font-display font-bold text-terminal-green">{count}</div>
              <div className="text-[10px] text-terminal-dim">{window}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Module Leaderboard Tab ──
function ModuleLeaderboard({ modules }: { modules: ModulePerformance[] }) {
  const [sortKey, setSortKey] = useState<string>('win_rate');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const sorted = [...modules].sort((a, b) => {
    const av = (a as Record<string, number | null>)[sortKey] ?? -999;
    const bv = (b as Record<string, number | null>)[sortKey] ?? -999;
    return sortDir === 'desc' ? (bv as number) - (av as number) : (av as number) - (bv as number);
  });

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'desc' ? 'asc' : 'desc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const SortHeader = ({ k, label }: { k: string; label: string }) => (
    <th
      className="text-right pb-2 cursor-pointer hover:text-terminal-green transition-colors"
      onClick={() => handleSort(k)}
    >
      {label} {sortKey === k ? (sortDir === 'desc' ? '▼' : '▲') : ''}
    </th>
  );

  return (
    <div className="panel p-4">
      <h3 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-4">
        MODULE PERFORMANCE LEADERBOARD
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-terminal-dim tracking-wider">
              <th className="text-left pb-2">MODULE</th>
              <SortHeader k="win_rate" label="WIN%" />
              <SortHeader k="avg_return_20d" label="AVG 20D" />
              <SortHeader k="sharpe_ratio" label="SHARPE" />
              <th className="text-right pb-2">N</th>
              <th className="text-right pb-2">STATIC W</th>
              <th className="text-right pb-2">ADAPTIVE W</th>
              <th className="text-right pb-2">DELTA</th>
              <th className="text-right pb-2">95% CI</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((m) => {
              const wrColor = m.win_rate >= 55 ? '#00FF41' : m.win_rate >= 45 ? '#FFB800' : '#FF073A';
              const avgRet = m.avg_return_20d ?? m.avg_return_30d ?? m.avg_return_5d;
              const retColor = avgRet && avgRet > 0 ? '#00FF41' : '#FF073A';
              const delta = m.adaptive_weight != null ? m.adaptive_weight - m.static_weight : null;
              const deltaColor = delta != null ? (delta > 0 ? '#00FF41' : delta < 0 ? '#FF073A' : '#666') : '#666';

              return (
                <tr key={m.module_name} className="border-t border-terminal-border hover:bg-terminal-border/30">
                  <td className="py-2 font-display text-terminal-text">{m.module_name}</td>
                  <td className="py-2 text-right font-mono" style={{ color: wrColor }}>
                    {m.win_rate.toFixed(1)}%
                  </td>
                  <td className="py-2 text-right font-mono" style={{ color: retColor }}>
                    {avgRet != null ? `${avgRet > 0 ? '+' : ''}${avgRet.toFixed(2)}%` : '—'}
                  </td>
                  <td className="py-2 text-right font-mono text-terminal-text">
                    {m.sharpe_ratio != null ? m.sharpe_ratio.toFixed(2) : '—'}
                  </td>
                  <td className="py-2 text-right font-mono text-terminal-dim">
                    {m.observation_count ?? m.total_signals}
                  </td>
                  <td className="py-2 text-right font-mono text-terminal-dim">
                    {(m.static_weight * 100).toFixed(0)}%
                  </td>
                  <td className="py-2 text-right font-mono text-terminal-text">
                    {m.adaptive_weight != null ? `${(m.adaptive_weight * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-2 text-right font-mono" style={{ color: deltaColor }}>
                    {delta != null ? `${delta > 0 ? '+' : ''}${(delta * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-2 text-right font-mono text-terminal-dim text-[11px]">
                    {m.confidence_interval_low != null && m.confidence_interval_high != null
                      ? `[${m.confidence_interval_low > 0 ? '+' : ''}${m.confidence_interval_low.toFixed(1)}, +${m.confidence_interval_high.toFixed(1)}]`
                      : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Track Record Tab ──
function TrackRecordTab({ data }: { data: TrackRecordMonth[] }) {
  if (!data.length) {
    return (
      <div className="panel p-8 text-center text-terminal-dim">
        No track record data yet. Run the pipeline daily to accumulate signal outcomes.
      </div>
    );
  }

  const maxSignals = Math.max(...data.map((d) => d.total_signals));

  return (
    <div className="space-y-6">
      {/* Cumulative win rate */}
      <div className="panel p-4">
        <h3 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-4">
          CUMULATIVE WIN RATE OVER TIME
        </h3>
        <div className="flex items-end gap-1 h-32">
          {data.map((d) => {
            const height = Math.max(4, (d.cumulative_win_rate / 100) * 100);
            const color = d.cumulative_win_rate >= 55 ? '#00FF41' : d.cumulative_win_rate >= 45 ? '#FFB800' : '#FF073A';
            return (
              <div key={d.month} className="flex-1 flex flex-col items-center gap-1 group relative">
                <div className="text-[9px] text-terminal-dim opacity-0 group-hover:opacity-100 transition-opacity">
                  {d.cumulative_win_rate.toFixed(1)}%
                </div>
                <div
                  className="w-full rounded-t transition-all duration-500"
                  style={{ height: `${height}%`, backgroundColor: color, opacity: 0.7 }}
                />
                <div className="text-[8px] text-terminal-dim -rotate-45 origin-top-left mt-1 whitespace-nowrap">
                  {d.month}
                </div>
              </div>
            );
          })}
        </div>
        <div className="flex justify-between text-[9px] text-terminal-dim mt-6">
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>

      {/* Monthly breakdown table */}
      <div className="panel p-4">
        <h3 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-4">
          MONTHLY SIGNAL BREAKDOWN
        </h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-terminal-dim tracking-wider">
              <th className="text-left pb-2">MONTH</th>
              <th className="text-right pb-2">SIGNALS</th>
              <th className="text-right pb-2">5D WIN%</th>
              <th className="text-right pb-2">5D AVG</th>
              <th className="text-right pb-2">20D WIN%</th>
              <th className="text-right pb-2">20D AVG</th>
              <th className="text-right pb-2">CUM WIN%</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => {
              const wr5 = d.resolved_5d > 0 ? ((d.wins_5d || 0) / d.resolved_5d * 100) : null;
              const wr20 = d.resolved_20d > 0 ? ((d.wins_20d || 0) / d.resolved_20d * 100) : null;
              return (
                <tr key={d.month} className="border-t border-terminal-border">
                  <td className="py-2 font-display text-terminal-text">{d.month}</td>
                  <td className="py-2 text-right font-mono text-terminal-dim">{d.total_signals}</td>
                  <td className="py-2 text-right font-mono" style={{ color: wr5 != null ? (wr5 >= 50 ? '#00FF41' : '#FF073A') : '#666' }}>
                    {wr5 != null ? `${wr5.toFixed(0)}%` : '—'}
                  </td>
                  <td className="py-2 text-right font-mono" style={{ color: d.avg_5d != null ? (d.avg_5d > 0 ? '#00FF41' : '#FF073A') : '#666' }}>
                    {d.avg_5d != null ? `${d.avg_5d > 0 ? '+' : ''}${d.avg_5d.toFixed(2)}%` : '—'}
                  </td>
                  <td className="py-2 text-right font-mono" style={{ color: wr20 != null ? (wr20 >= 50 ? '#00FF41' : '#FF073A') : '#666' }}>
                    {wr20 != null ? `${wr20.toFixed(0)}%` : '—'}
                  </td>
                  <td className="py-2 text-right font-mono" style={{ color: d.avg_20d != null ? (d.avg_20d > 0 ? '#00FF41' : '#FF073A') : '#666' }}>
                    {d.avg_20d != null ? `${d.avg_20d > 0 ? '+' : ''}${d.avg_20d.toFixed(2)}%` : '—'}
                  </td>
                  <td className="py-2 text-right font-mono" style={{ color: d.cumulative_win_rate >= 50 ? '#00FF41' : '#FF073A' }}>
                    {d.cumulative_win_rate.toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Weight Evolution Tab ──
function WeightEvolutionTab({ history }: { history: WeightHistoryEntry[] }) {
  if (!history.length) {
    return (
      <div className="panel p-8 text-center text-terminal-dim">
        <div className="text-lg mb-2">Adaptive weights not yet active</div>
        <div className="text-sm">
          The optimizer needs {'>'}100 resolved signals and {'>'}30 days of data before adjusting weights.
          Until then, static config weights are used.
        </div>
      </div>
    );
  }

  // Show latest weight snapshot
  const latest = history[0];

  return (
    <div className="space-y-6">
      {/* Latest snapshot */}
      <div className="panel p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs text-terminal-dim tracking-[0.2em] uppercase">
            LATEST WEIGHT UPDATE — {latest.date}
          </h3>
          <div className="text-xs text-terminal-dim">
            Total delta: <span className="text-terminal-green">{latest.total_delta.toFixed(4)}</span>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {latest.modules
            .sort((a, b) => b.weight - a.weight)
            .map((m) => {
              const delta = m.weight - m.prior_weight;
              const barWidth = m.weight * 100 * 4; // scale for visibility
              const deltaColor = delta > 0.001 ? '#00FF41' : delta < -0.001 ? '#FF073A' : '#666';

              return (
                <div key={m.module_name} className="flex items-center gap-2 py-1">
                  <div className="w-28 text-xs text-terminal-text truncate">{m.module_name}</div>
                  <div className="flex-1 h-3 bg-terminal-border rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${Math.min(100, barWidth)}%`,
                        backgroundColor: deltaColor === '#00FF41' ? '#00FF41' : deltaColor === '#FF073A' ? '#FF073A' : '#00FF4180',
                      }}
                    />
                  </div>
                  <div className="w-14 text-right text-xs font-mono text-terminal-text">
                    {(m.weight * 100).toFixed(1)}%
                  </div>
                  <div className="w-14 text-right text-xs font-mono" style={{ color: deltaColor }}>
                    {delta > 0.001 ? '+' : ''}{(delta * 100).toFixed(1)}%
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* History timeline */}
      <div className="panel p-4">
        <h3 className="text-xs text-terminal-dim tracking-[0.2em] uppercase mb-4">
          WEIGHT UPDATE HISTORY
        </h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-terminal-dim tracking-wider">
              <th className="text-left pb-2">DATE</th>
              <th className="text-right pb-2">TOTAL DELTA</th>
              <th className="text-right pb-2">MODULES</th>
              <th className="text-left pb-2 pl-4">TOP CHANGES</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => {
              const topChanges = h.modules
                .filter((m) => Math.abs(m.weight - m.prior_weight) > 0.001)
                .sort((a, b) => Math.abs(b.weight - b.prior_weight) - Math.abs(a.weight - a.prior_weight))
                .slice(0, 3);

              return (
                <tr key={h.date} className="border-t border-terminal-border">
                  <td className="py-2 font-display text-terminal-text">{h.date}</td>
                  <td className="py-2 text-right font-mono text-terminal-green">
                    {h.total_delta.toFixed(4)}
                  </td>
                  <td className="py-2 text-right font-mono text-terminal-dim">
                    {h.modules.length}
                  </td>
                  <td className="py-2 pl-4 text-xs text-terminal-dim">
                    {topChanges.map((m) => {
                      const d = m.weight - m.prior_weight;
                      return `${m.module_name} ${d > 0 ? '+' : ''}${(d * 100).toFixed(1)}%`;
                    }).join(', ') || 'No changes'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main Page ──
function PerformancePageInner() {
  const [tab, setTab] = useState<TabKey>('overview');
  const [summary, setSummary] = useState<PerformanceSummary | null>(null);
  const [modules, setModules] = useState<ModulePerformance[]>([]);
  const [trackRecord, setTrackRecord] = useState<TrackRecordMonth[]>([]);
  const [weightHistory, setWeightHistory] = useState<WeightHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.performanceSummary().catch(() => null),
      api.performanceModules().catch(() => []),
      api.performanceTrackRecord().catch(() => []),
      api.performanceWeightHistory().catch(() => []),
    ]).then(([s, m, tr, wh]) => {
      if (s) setSummary(s);
      setModules(m as ModulePerformance[]);
      setTrackRecord(tr as TrackRecordMonth[]);
      setWeightHistory(wh as WeightHistoryEntry[]);
    }).catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="p-8">
        <div className="panel p-6 text-center">
          <div className="text-red-400 mb-2">Failed to load performance data</div>
          <div className="text-sm text-terminal-dim">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-bold text-terminal-green tracking-wider">
            PERFORMANCE — DATA MOAT
          </h1>
          <p className="text-xs text-terminal-dim mt-1">
            Signal accuracy, module performance, and adaptive weight optimization
          </p>
        </div>
        {summary && (
          <SufficiencyBadge
            sufficient={summary.data_sufficient}
            days={summary.days_running}
            signals={summary.total_signals}
          />
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-terminal-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-xs font-display tracking-wider transition-colors ${
              tab === t.key
                ? 'text-terminal-green border-b-2 border-terminal-green'
                : 'text-terminal-dim hover:text-terminal-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {!summary ? (
        <div className="panel p-8 text-center text-terminal-dim animate-pulse">Loading...</div>
      ) : tab === 'overview' ? (
        <OverviewTab summary={summary} />
      ) : tab === 'modules' ? (
        <ModuleLeaderboard modules={modules} />
      ) : tab === 'track-record' ? (
        <TrackRecordTab data={trackRecord} />
      ) : (
        <WeightEvolutionTab history={weightHistory} />
      )}
    </div>
  );
}

export default function PerformancePage() {
  return (
    <ErrorBoundary>
      <PerformancePageInner />
    </ErrorBoundary>
  );
}
