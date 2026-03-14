'use client';

import { useEffect, useState, useMemo } from 'react';
import { api, type Position, type ClosedPosition, type PortfolioStats } from '@/lib/api';
import Link from 'next/link';

/* ═══ Helpers ═══ */
const pnlColor = (v: number) => v > 0 ? '#00FF41' : v < 0 ? '#FF073A' : '#555';
const pctFormat = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(2)}%`;
const dollarFormat = (v: number) => {
  const abs = Math.abs(v);
  const prefix = v < 0 ? '-' : v > 0 ? '+' : '';
  if (abs >= 1e6) return `${prefix}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${prefix}$${(abs / 1e3).toFixed(1)}K`;
  return `${prefix}$${abs.toFixed(0)}`;
};

type Tab = 'open' | 'closed' | 'performance';

/* ═══ Stat Card ═══ */
function StatCard({ label, value, color, sub }: { label: string; value: string; color: string; sub?: string }) {
  return (
    <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '20px' }}>
      <div className="text-[9px] text-terminal-dim tracking-widest opacity-50 mb-2">{label}</div>
      <div className="text-[20px] font-bold font-mono" style={{ color }}>{value}</div>
      {sub && <div className="text-[10px] text-terminal-dim mt-1 opacity-60">{sub}</div>}
    </div>
  );
}

/* ═══ Position Row ═══ */
function PositionRow({ p, showExit }: { p: Position | ClosedPosition; showExit?: boolean }) {
  const pnl = p.pnl ?? 0;
  const pnlPct = p.pnl_pct ?? 0;

  return (
    <tr
      className="transition-colors"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,255,65,0.015)'; }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
    >
      <td className="py-3 px-4">
        <Link href={`/asset/${p.symbol}`} className="font-bold tracking-wide hover:underline focus:outline-none focus-visible:underline" style={{ color: '#00FF41' }}>
          {p.symbol}
        </Link>
        <div className="text-[9px] text-terminal-dim opacity-50 mt-0.5">{p.entry_date}</div>
      </td>
      <td className="py-3 px-4 text-right font-mono text-terminal-dim">
        ${(p.entry_price ?? 0).toFixed(2)}
      </td>
      {showExit ? (
        <td className="py-3 px-4 text-right font-mono text-terminal-text">
          {(p as ClosedPosition).exit_price != null ? `$${((p as ClosedPosition).exit_price!).toFixed(2)}` : '—'}
        </td>
      ) : (
        <td className="py-3 px-4 text-right font-mono text-terminal-text">
          ${(p.current_price ?? 0).toFixed(2)}
        </td>
      )}
      <td className="py-3 px-4 text-right font-mono text-terminal-dim">
        {p.shares}
      </td>
      <td className="py-3 px-4 text-right font-mono font-bold" style={{ color: pnlColor(pnlPct) }}>
        {pctFormat(pnlPct)}
      </td>
      <td className="py-3 px-4 text-right font-mono" style={{ color: pnlColor(pnl) }}>
        {dollarFormat(pnl)}
      </td>
      <td className="py-3 px-4 text-right font-mono text-terminal-dim">
        {p.stop_loss ? `$${p.stop_loss.toFixed(2)}` : '—'}
      </td>
      <td className="py-3 px-4 text-right font-mono text-terminal-dim">
        {p.target_price ? `$${p.target_price.toFixed(2)}` : '—'}
      </td>
    </tr>
  );
}

/* ═══ Main Page ═══ */
export default function PaperTraderPage() {
  const [openPositions, setOpenPositions] = useState<Position[]>([]);
  const [closedTrades, setClosedTrades] = useState<ClosedPosition[]>([]);
  const [stats, setStats] = useState<PortfolioStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('open');
  const [sortCol, setSortCol] = useState<'pnl_pct' | 'current_value' | 'symbol'>('pnl_pct');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const loadData = () => {
    setLoading(true);
    Promise.allSettled([
      api.portfolioOpen(),
      api.portfolioClosed(),
      api.portfolioStats(),
    ]).then(([o, c, s]) => {
      if (o.status === 'fulfilled') setOpenPositions(o.value);
      if (c.status === 'fulfilled') setClosedTrades(c.value);
      if (s.status === 'fulfilled') setStats(s.value);
      setLoading(false);
    });
  };

  useEffect(loadData, []);

  const handleSync = async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await api.portfolioSync();
      if (result.synced > 0) {
        setSyncMessage(`Synced ${result.synced} position${result.synced > 1 ? 's' : ''}: ${result.symbols.join(', ')}`);
        loadData(); // Refresh
      } else {
        setSyncMessage('No new HIGH conviction signals to sync');
      }
    } catch {
      setSyncMessage('Sync failed — check backend connection');
    } finally {
      setSyncing(false);
    }
  };

  const sorted = useMemo(() => {
    return [...openPositions].sort((a, b) => {
      const dir = sortDir === 'desc' ? -1 : 1;
      if (sortCol === 'symbol') return dir * a.symbol.localeCompare(b.symbol);
      return dir * ((a[sortCol] ?? 0) - (b[sortCol] ?? 0));
    });
  }, [openPositions, sortCol, sortDir]);

  const toggleSort = (col: typeof sortCol) => {
    if (sortCol === col) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  // Portfolio aggregates from live positions
  const liveStats = useMemo(() => {
    if (openPositions.length === 0) return null;
    const totalValue = openPositions.reduce((s, p) => s + (p.current_value ?? 0), 0);
    const totalPnl = openPositions.reduce((s, p) => s + (p.pnl ?? 0), 0);
    const totalCost = openPositions.reduce((s, p) => s + (p.entry_price ?? 0) * (p.shares ?? 0), 0);
    const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;
    return { totalValue, totalPnl, totalPnlPct };
  }, [openPositions]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full" role="status">
        <div className="space-y-3 text-center">
          <div className="text-terminal-cyan text-2xl font-display font-bold glow-cyan animate-pulse">
            LOADING PORTFOLIO
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest">
            Fetching paper trading positions...
          </div>
        </div>
      </div>
    );
  }

  const isEmpty = openPositions.length === 0 && closedTrades.length === 0;
  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'open', label: 'OPEN', count: openPositions.length },
    { key: 'closed', label: 'CLOSED', count: closedTrades.length },
    { key: 'performance', label: 'PERFORMANCE', count: 0 },
  ];

  return (
    <div className="p-6 space-y-0">
      {/* ═══ Header ═══ */}
      <div className="flex items-center justify-between pb-6">
        <div>
          <h1 className="text-[22px] font-display font-bold text-terminal-bright tracking-wider">
            PAPER TRADER
          </h1>
          <p className="text-[10px] text-terminal-dim tracking-widest mt-1 opacity-60">
            Simulated portfolio — tracking system performance
          </p>
        </div>
        <div className="flex items-center gap-3">
          {syncMessage && (
            <span className="text-[10px] text-terminal-dim" aria-live="polite">{syncMessage}</span>
          )}
          <button
            onClick={handleSync}
            disabled={syncing}
            className="text-[10px] tracking-widest transition-all duration-200 focus:outline-none focus-visible:ring-1 focus-visible:ring-terminal-green disabled:opacity-40"
            style={{
              padding: '8px 16px',
              border: '1px solid rgba(0,229,255,0.3)',
              borderRadius: '2px',
              color: '#00E5FF',
              background: 'rgba(0,229,255,0.06)',
            }}
            aria-label="Sync new HIGH conviction signals into paper portfolio"
          >
            {syncing ? 'SYNCING...' : 'SYNC FROM SIGNALS'}
          </button>
        </div>
      </div>

      {/* ═══ Stats Row ═══ */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard
          label="OPEN VALUE"
          value={liveStats ? dollarFormat(liveStats.totalValue) : '$0'}
          color="#C8C8C8"
          sub={`${openPositions.length} position${openPositions.length !== 1 ? 's' : ''}`}
        />
        <StatCard
          label="OPEN P&L"
          value={liveStats ? dollarFormat(liveStats.totalPnl) : '$0'}
          color={pnlColor(liveStats?.totalPnl ?? 0)}
          sub={liveStats ? pctFormat(liveStats.totalPnlPct) : '0%'}
        />
        <StatCard
          label="WIN RATE"
          value={stats ? `${stats.win_rate.toFixed(0)}%` : '—'}
          color={stats && stats.win_rate >= 60 ? '#00FF41' : stats && stats.win_rate >= 40 ? '#FFB800' : '#FF073A'}
          sub={stats ? `${stats.win_count}W / ${stats.loss_count}L (${stats.closed_count} closed)` : 'No closed trades'}
        />
        <StatCard
          label="PROFIT FACTOR"
          value={stats?.profit_factor ? stats.profit_factor.toFixed(2) : '—'}
          color={stats && stats.profit_factor >= 2 ? '#00FF41' : stats && stats.profit_factor >= 1 ? '#FFB800' : '#FF073A'}
          sub={stats ? `Avg win: +${stats.avg_win_pct.toFixed(1)}% / Avg loss: ${stats.avg_loss_pct.toFixed(1)}%` : undefined}
        />
      </div>

      {/* ═══ P&L Distribution ═══ */}
      {openPositions.length > 0 && liveStats && (
        <div className="mb-6" style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '16px 20px' }}>
          <div className="text-[9px] text-terminal-dim tracking-widest opacity-40 mb-3">P&L DISTRIBUTION</div>
          <div className="flex h-[28px] rounded-sm overflow-hidden gap-px" role="img" aria-label="P&L distribution across positions">
            {sorted.map(p => {
              const weight = Math.abs(p.current_value ?? 0) / (liveStats.totalValue || 1) * 100;
              return (
                <div
                  key={p.id ?? p.symbol}
                  className="relative group transition-opacity"
                  style={{
                    width: `${Math.max(weight, 1)}%`,
                    background: pnlColor(p.pnl ?? 0),
                    opacity: 0.7,
                    minWidth: '3px',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.opacity = '0.7'; }}
                  title={`${p.symbol}: ${pctFormat(p.pnl_pct ?? 0)}`}
                />
              );
            })}
          </div>
          <div className="flex justify-between mt-2 text-[8px] text-terminal-dim tracking-widest opacity-30">
            <span>LOSERS</span>
            <span>WINNERS</span>
          </div>
        </div>
      )}

      {/* ═══ Tabs ═══ */}
      <div className="flex gap-1 mb-5" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '1px' }} role="tablist">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            role="tab"
            aria-selected={tab === t.key}
            className="transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-terminal-green"
            style={{
              padding: '8px 16px',
              fontSize: '10px',
              letterSpacing: '0.12em',
              color: tab === t.key ? '#00E5FF' : '#555',
              borderBottom: tab === t.key ? '2px solid #00E5FF' : '2px solid transparent',
              background: 'transparent',
            }}
          >
            {t.label} {t.key !== 'performance' && `(${t.count})`}
          </button>
        ))}
      </div>

      {/* ═══ Open Positions ═══ */}
      {tab === 'open' && (
        isEmpty ? (
          <div className="text-center py-20">
            <div className="text-[40px] mb-4 opacity-20">◇</div>
            <div className="text-terminal-dim text-sm mb-2">No open positions</div>
            <div className="text-[10px] text-terminal-dim opacity-50 mb-4">
              Click &quot;Sync from Signals&quot; to generate paper positions from HIGH conviction signals
            </div>
            <button
              onClick={handleSync}
              disabled={syncing}
              className="text-[10px] tracking-widest transition-all duration-200 focus:outline-none focus-visible:ring-1 focus-visible:ring-terminal-green disabled:opacity-40"
              style={{ padding: '8px 20px', border: '1px solid rgba(0,229,255,0.3)', borderRadius: '2px', color: '#00E5FF', background: 'rgba(0,229,255,0.06)' }}
            >
              {syncing ? 'SYNCING...' : 'SYNC NOW'}
            </button>
          </div>
        ) : (
          <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', overflow: 'hidden' }}>
            <table className="w-full text-[11px]">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  {[
                    { key: 'symbol' as const, label: 'SYMBOL' },
                    { key: null, label: 'ENTRY' },
                    { key: null, label: 'CURRENT' },
                    { key: null, label: 'SHARES' },
                    { key: 'pnl_pct' as const, label: 'P&L %' },
                    { key: null, label: 'P&L $' },
                    { key: null, label: 'STOP' },
                    { key: null, label: 'TARGET' },
                  ].map((col, i) => (
                    <th
                      key={col.label}
                      className={`py-3 px-4 text-[9px] text-terminal-dim tracking-widest opacity-50 ${i === 0 ? 'text-left' : 'text-right'} ${col.key ? 'cursor-pointer hover:opacity-80' : ''}`}
                      onClick={() => col.key && toggleSort(col.key)}
                      scope="col"
                    >
                      {col.label}
                      {col.key === sortCol && <span className="ml-1">{sortDir === 'desc' ? '▾' : '▴'}</span>}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map(p => <PositionRow key={p.id ?? p.symbol} p={p} />)}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ═══ Closed Trades ═══ */}
      {tab === 'closed' && (
        closedTrades.length === 0 ? (
          <div className="text-center py-16 text-terminal-dim text-sm">No closed trades yet</div>
        ) : (
          <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', overflow: 'hidden' }}>
            <table className="w-full text-[11px]">
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  {['SYMBOL', 'ENTRY', 'EXIT', 'SHARES', 'P&L %', 'P&L $', 'STOP', 'TARGET'].map((label, i) => (
                    <th key={label} className={`py-3 px-4 text-[9px] text-terminal-dim tracking-widest opacity-50 ${i === 0 ? 'text-left' : 'text-right'}`} scope="col">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {closedTrades.map(p => <PositionRow key={p.id ?? p.symbol} p={p} showExit />)}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* ═══ Performance Tab ═══ */}
      {tab === 'performance' && stats && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '20px' }}>
              <div className="text-[9px] text-terminal-dim tracking-widest opacity-50 mb-4">TRADE OUTCOMES</div>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-terminal-dim">Total Trades</span>
                  <span className="text-[12px] font-mono text-terminal-text">{stats.closed_count}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-terminal-dim">Win Rate</span>
                  <span className="text-[12px] font-mono font-bold" style={{ color: stats.win_rate >= 50 ? '#00FF41' : '#FF073A' }}>
                    {stats.win_rate.toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-terminal-dim">Winners</span>
                  <span className="text-[12px] font-mono" style={{ color: '#00FF41' }}>{stats.win_count}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-terminal-dim">Losers</span>
                  <span className="text-[12px] font-mono" style={{ color: '#FF073A' }}>{stats.loss_count}</span>
                </div>
              </div>
            </div>

            <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '20px' }}>
              <div className="text-[9px] text-terminal-dim tracking-widest opacity-50 mb-4">EDGE ANALYSIS</div>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-terminal-dim">Profit Factor</span>
                  <span className="text-[12px] font-mono font-bold" style={{ color: stats.profit_factor >= 1.5 ? '#00FF41' : stats.profit_factor >= 1 ? '#FFB800' : '#FF073A' }}>
                    {stats.profit_factor.toFixed(2)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-terminal-dim">Avg Winner</span>
                  <span className="text-[12px] font-mono" style={{ color: '#00FF41' }}>+{stats.avg_win_pct.toFixed(2)}%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-terminal-dim">Avg Loser</span>
                  <span className="text-[12px] font-mono" style={{ color: '#FF073A' }}>{stats.avg_loss_pct.toFixed(2)}%</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-terminal-dim">Expectancy</span>
                  <span className="text-[12px] font-mono font-bold" style={{
                    color: pnlColor((stats.avg_win_pct * stats.win_rate / 100) + (stats.avg_loss_pct * (100 - stats.win_rate) / 100))
                  }}>
                    {((stats.avg_win_pct * stats.win_rate / 100) + (stats.avg_loss_pct * (100 - stats.win_rate) / 100)).toFixed(2)}%
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Win Rate Visual Bar */}
          {stats.closed_count > 0 && (
            <div style={{ background: '#111', border: '1px solid rgba(255,255,255,0.04)', borderRadius: '3px', padding: '20px' }}>
              <div className="text-[9px] text-terminal-dim tracking-widest opacity-40 mb-3">WIN / LOSS RATIO</div>
              <div className="flex h-[12px] rounded-sm overflow-hidden">
                <div
                  className="h-full transition-all duration-500"
                  style={{ width: `${stats.win_rate}%`, background: '#00FF41', opacity: 0.7 }}
                  title={`Winners: ${stats.win_count}`}
                />
                <div
                  className="h-full transition-all duration-500"
                  style={{ width: `${100 - stats.win_rate}%`, background: '#FF073A', opacity: 0.7 }}
                  title={`Losers: ${stats.loss_count}`}
                />
              </div>
              <div className="flex justify-between mt-2 text-[8px] text-terminal-dim tracking-widest opacity-40">
                <span>{stats.win_count} WINS ({stats.win_rate.toFixed(0)}%)</span>
                <span>{stats.loss_count} LOSSES ({(100 - stats.win_rate).toFixed(0)}%)</span>
              </div>
            </div>
          )}

          {stats.closed_count === 0 && (
            <div className="text-center py-12 text-terminal-dim text-sm">
              No closed trades yet — performance metrics will appear after positions are closed
            </div>
          )}
        </div>
      )}

      {tab === 'performance' && !stats && (
        <div className="text-center py-16 text-terminal-dim text-sm">Loading performance data...</div>
      )}
    </div>
  );
}
