'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { api, type DiscoverStock, type MacroData, type SentimentCycle } from '@/lib/api';
import Link from 'next/link';

/* ═══ Helpers ═══ */
const scoreColor = (v: number) =>
  v >= 70 ? '#00FF41' : v >= 50 ? '#69F0AE' : v >= 30 ? '#FFB800' : '#FF073A';

const scoreLabel = (v: number) =>
  v >= 70 ? 'STRONG' : v >= 50 ? 'GOOD' : v >= 30 ? 'MIXED' : 'WEAK';

const convictionColor = (c: string) => {
  if (c === 'HIGH') return { bg: 'rgba(0,255,65,0.1)', border: 'rgba(0,255,65,0.3)', text: '#00FF41' };
  if (c === 'NOTABLE') return { bg: 'rgba(255,184,0,0.08)', border: 'rgba(255,184,0,0.2)', text: '#FFB800' };
  return { bg: 'rgba(85,85,85,0.1)', border: 'rgba(85,85,85,0.2)', text: '#888' };
};

const formatModules = (active: string) => {
  if (!active) return [];
  return active.split(',').map(m => m.trim()).filter(Boolean);
};

const moduleDisplayName: Record<string, string> = {
  main_signal: 'Signal', smartmoney: 'Smart $', worldview: 'Macro', variant: 'Variant',
  research: 'Research', reddit: 'Reddit', news_displacement: 'News', alt_data: 'Alt Data',
  sector_expert: 'Sector', foreign_intel: 'Foreign', pairs: 'Pairs', ma: 'M&A',
  energy_intel: 'Energy', prediction_markets: 'Prediction', pattern_options: 'Patterns',
  ai_exec: 'AI Exec', estimate_momentum: 'Est. Mom', ai_regulatory: 'AI Reg',
  consensus_blindspots: 'Blindspots',
};

const PAGE_SIZE = 60;

/* ═══ Score Arc Component ═══ */
function ScoreArc({ score, size = 56 }: { score: number; size?: number }) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const pct = Math.min(score, 100) / 100;
  const dashOffset = circ * (1 - pct * 0.75);
  const color = scoreColor(score);

  return (
    <svg
      width={size} height={size} viewBox={`0 0 ${size} ${size}`}
      className="flex-shrink-0"
      role="img"
      aria-label={`Convergence score: ${score.toFixed(0)} out of 100`}
    >
      <circle
        cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth={3}
        strokeDasharray={`${circ * 0.75} ${circ * 0.25}`}
        strokeDashoffset={0}
        transform={`rotate(135 ${size / 2} ${size / 2})`}
        strokeLinecap="round"
      />
      <circle
        cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={3}
        strokeDasharray={`${circ * 0.75} ${circ * 0.25}`}
        strokeDashoffset={dashOffset}
        transform={`rotate(135 ${size / 2} ${size / 2})`}
        strokeLinecap="round"
        style={{ filter: `drop-shadow(0 0 4px ${color}40)`, transition: 'stroke-dashoffset 0.6s ease' }}
      />
      <text
        x={size / 2} y={size / 2 + 1}
        textAnchor="middle" dominantBaseline="middle"
        fill={color}
        fontSize={size > 48 ? 14 : 11}
        fontFamily="JetBrains Mono"
        fontWeight="bold"
        aria-hidden="true"
      >
        {score.toFixed(0)}
      </text>
    </svg>
  );
}

/* ═══ Filter Chip ═══ */
function Chip({
  label, active, count, onClick, color = 'green',
}: {
  label: string; active: boolean; count?: number; onClick: () => void; color?: 'green' | 'amber' | 'red' | 'cyan' | 'dim';
}) {
  const colors = {
    green: { activeBg: 'rgba(0,255,65,0.1)', activeBorder: 'rgba(0,255,65,0.35)', activeText: '#00FF41' },
    amber: { activeBg: 'rgba(255,184,0,0.1)', activeBorder: 'rgba(255,184,0,0.3)', activeText: '#FFB800' },
    red: { activeBg: 'rgba(255,7,58,0.1)', activeBorder: 'rgba(255,7,58,0.3)', activeText: '#FF073A' },
    cyan: { activeBg: 'rgba(0,229,255,0.1)', activeBorder: 'rgba(0,229,255,0.3)', activeText: '#00E5FF' },
    dim: { activeBg: 'rgba(85,85,85,0.15)', activeBorder: 'rgba(85,85,85,0.3)', activeText: '#AAA' },
  };
  const c = colors[color];

  return (
    <button
      onClick={onClick}
      role="switch"
      aria-checked={active}
      aria-label={count !== undefined ? `${label}: ${count} stocks` : label}
      className="transition-all duration-200 flex items-center gap-1.5 whitespace-nowrap focus:outline-none focus-visible:ring-1 focus-visible:ring-terminal-green"
      style={{
        padding: '5px 12px',
        borderRadius: '2px',
        fontSize: '10px',
        fontWeight: 600,
        letterSpacing: '0.08em',
        textTransform: 'uppercase' as const,
        background: active ? c.activeBg : 'transparent',
        border: `1px solid ${active ? c.activeBorder : 'rgba(255,255,255,0.06)'}`,
        color: active ? c.activeText : '#555',
        boxShadow: active ? `0 0 12px ${c.activeBg}` : 'none',
      }}
    >
      {label}
      {count !== undefined && (
        <span style={{ fontSize: '9px', opacity: 0.6, fontWeight: 400, marginLeft: '2px' }} aria-hidden="true">
          {count}
        </span>
      )}
    </button>
  );
}

/* ═══ Stock Card ═══ */
function StockCard({ stock }: { stock: DiscoverStock }) {
  const conv = convictionColor(stock.conviction_level);
  const modules = formatModules(stock.active_modules);
  const badges: { label: string; color: string }[] = [];
  if (stock.is_fat_pitch) badges.push({ label: 'FAT PITCH', color: '#00FF41' });
  if (stock.has_insider_cluster) badges.push({ label: 'INSIDER CLUSTER', color: '#00E5FF' });
  if (stock.is_ma_target) badges.push({ label: 'M&A TARGET', color: '#FFB800' });
  if (stock.has_unusual_options) badges.push({ label: `OPTIONS ${stock.unusual_options_bias ?? ''}`.trim(), color: '#E040FB' });

  return (
    <Link
      href={`/asset/${stock.symbol}`}
      aria-label={`${stock.symbol} — ${stock.company_name ?? ''} — Score ${stock.convergence_score.toFixed(0)}, ${stock.conviction_level} conviction, ${stock.module_count} modules`}
    >
      <div
        className="group relative overflow-hidden transition-all duration-300 hover:border-terminal-green/15"
        style={{
          background: '#111111',
          border: '1px solid rgba(255,255,255,0.04)',
          borderRadius: '3px',
          padding: '20px',
          cursor: 'pointer',
        }}
        onMouseEnter={e => {
          (e.currentTarget as HTMLElement).style.borderColor = 'rgba(0,255,65,0.15)';
          (e.currentTarget as HTMLElement).style.boxShadow = '0 0 20px rgba(0,255,65,0.03)';
        }}
        onMouseLeave={e => {
          (e.currentTarget as HTMLElement).style.borderColor = 'rgba(255,255,255,0.04)';
          (e.currentTarget as HTMLElement).style.boxShadow = 'none';
        }}
      >
        <div className="flex items-start gap-4">
          <ScoreArc score={stock.convergence_score} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5">
              <span className="text-[15px] font-bold text-terminal-bright tracking-wide">
                {stock.symbol}
              </span>
              <span
                className="text-[9px] font-semibold tracking-widest"
                style={{
                  padding: '2px 8px', borderRadius: '2px',
                  background: conv.bg, border: `1px solid ${conv.border}`, color: conv.text,
                }}
              >
                {stock.conviction_level}
              </span>
              {stock.conflict_count > 0 && (
                <span
                  className="text-[9px] font-semibold tracking-wider"
                  style={{
                    padding: '2px 6px', borderRadius: '2px',
                    background: 'rgba(255,7,58,0.08)', border: '1px solid rgba(255,7,58,0.2)', color: '#FF073A',
                  }}
                >
                  {stock.conflict_count} CONFLICT{stock.conflict_count > 1 ? 'S' : ''}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] text-terminal-dim truncate">
                {stock.company_name ?? stock.symbol}
              </span>
              {stock.sector && (
                <span className="text-[9px] text-terminal-dim opacity-50">{stock.sector}</span>
              )}
            </div>
          </div>
          <div className="text-right flex-shrink-0">
            <div className="text-[10px] text-terminal-dim">{stock.module_count} modules</div>
            <div className="text-[10px] text-terminal-dim opacity-50">{scoreLabel(stock.convergence_score)}</div>
          </div>
        </div>

        {badges.length > 0 && (
          <div className="flex gap-1.5 mt-3" role="list" aria-label="Special signals">
            {badges.map(b => (
              <span
                key={b.label}
                role="listitem"
                className="text-[8px] font-bold tracking-widest"
                style={{
                  padding: '2px 6px', borderRadius: '2px',
                  background: `${b.color}12`, border: `1px solid ${b.color}30`, color: b.color,
                }}
              >
                {b.label}
              </span>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-1 mt-3">
          {modules.slice(0, 8).map(m => (
            <span
              key={m}
              className="text-[8px] tracking-wider"
              style={{ padding: '1px 5px', borderRadius: '1px', background: 'rgba(255,255,255,0.03)', color: '#666' }}
            >
              {moduleDisplayName[m] ?? m}
            </span>
          ))}
          {modules.length > 8 && (
            <span className="text-[8px] text-terminal-dim">+{modules.length - 8}</span>
          )}
        </div>

        {stock.narrative && (
          <p className="text-[10px] text-terminal-dim mt-3 leading-relaxed line-clamp-2 opacity-60">
            {stock.narrative}
          </p>
        )}
      </div>
    </Link>
  );
}

/* ═══ Main Page ═══ */
type SortKey = 'score' | 'modules' | 'name';

export default function DiscoverPage() {
  const [stocks, setStocks] = useState<DiscoverStock[]>([]);
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [cycle, setCycle] = useState<SentimentCycle | null>(null);
  const [loading, setLoading] = useState(true);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Filters
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [selectedConviction, setSelectedConviction] = useState<string | null>(null);
  const [showFatPitchesOnly, setShowFatPitchesOnly] = useState(false);
  const [showInsiderOnly, setShowInsiderOnly] = useState(false);
  const [showMAOnly, setShowMAOnly] = useState(false);
  const [showOptionsOnly, setShowOptionsOnly] = useState(false);
  const [hideConflicts, setHideConflicts] = useState(false);
  const [hideForensicBlocked, setHideForensicBlocked] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    Promise.allSettled([
      api.discover(),
      api.macro(),
      api.sentimentCycle(),
    ]).then(([d, m, c]) => {
      if (d.status === 'fulfilled') setStocks(d.value);
      if (m.status === 'fulfilled') setMacro(m.value);
      if (c.status === 'fulfilled') setCycle(c.value);
      setLoading(false);
    });
  }, []);

  // Reset pagination when filters change
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [selectedSector, selectedConviction, showFatPitchesOnly, showInsiderOnly, showMAOnly, showOptionsOnly, hideConflicts, hideForensicBlocked, minScore, sortKey, searchQuery]);

  const sectors = useMemo(() => {
    const map = new Map<string, number>();
    stocks.forEach(s => {
      if (s.sector) map.set(s.sector, (map.get(s.sector) || 0) + 1);
    });
    return Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([sector, count]) => ({ sector, count }));
  }, [stocks]);

  const filtered = useMemo(() => {
    let result = [...stocks];

    if (searchQuery) {
      const q = searchQuery.toUpperCase();
      result = result.filter(s =>
        s.symbol.includes(q) ||
        (s.company_name?.toUpperCase().includes(q)) ||
        (s.sector?.toUpperCase().includes(q))
      );
    }
    if (selectedSector) result = result.filter(s => s.sector === selectedSector);
    if (selectedConviction) result = result.filter(s => s.conviction_level === selectedConviction);
    if (showFatPitchesOnly) result = result.filter(s => s.is_fat_pitch);
    if (showInsiderOnly) result = result.filter(s => s.has_insider_cluster);
    if (showMAOnly) result = result.filter(s => s.is_ma_target);
    if (showOptionsOnly) result = result.filter(s => s.has_unusual_options);
    if (hideConflicts) result = result.filter(s => s.conflict_count === 0);
    if (hideForensicBlocked) result = result.filter(s => !s.forensic_blocked);
    if (minScore > 0) result = result.filter(s => s.convergence_score >= minScore);

    if (sortKey === 'score') result.sort((a, b) => b.convergence_score - a.convergence_score);
    else if (sortKey === 'modules') result.sort((a, b) => b.module_count - a.module_count);
    else result.sort((a, b) => a.symbol.localeCompare(b.symbol));

    return result;
  }, [stocks, searchQuery, selectedSector, selectedConviction, showFatPitchesOnly, showInsiderOnly, showMAOnly, showOptionsOnly, hideConflicts, hideForensicBlocked, minScore, sortKey]);

  const activeFilterCount = [
    selectedSector, selectedConviction, showFatPitchesOnly, showInsiderOnly,
    showMAOnly, showOptionsOnly, hideConflicts, hideForensicBlocked, minScore > 0,
  ].filter(Boolean).length;

  const clearAll = useCallback(() => {
    setSelectedSector(null);
    setSelectedConviction(null);
    setShowFatPitchesOnly(false);
    setShowInsiderOnly(false);
    setShowMAOnly(false);
    setShowOptionsOnly(false);
    setHideConflicts(false);
    setHideForensicBlocked(false);
    setMinScore(0);
    setSearchQuery('');
  }, []);

  const stats = useMemo(() => ({
    fatPitches: stocks.filter(s => s.is_fat_pitch).length,
    insiderClusters: stocks.filter(s => s.has_insider_cluster).length,
    maTargets: stocks.filter(s => s.is_ma_target).length,
    unusualOptions: stocks.filter(s => s.has_unusual_options).length,
    withConflicts: stocks.filter(s => s.conflict_count > 0).length,
    highConviction: stocks.filter(s => s.conviction_level === 'HIGH').length,
  }), [stocks]);

  const hasMore = filtered.length > visibleCount;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full" role="status" aria-label="Loading discovery data">
        <div className="space-y-3 text-center">
          <div className="text-terminal-green text-2xl font-display font-bold glow-green animate-pulse">
            SCANNING
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest">
            Loading {'>'}900 instruments across 18 modules...
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-0">
      {/* ═══ Header ═══ */}
      <div className="pb-6">
        <h1 className="text-[22px] font-display font-bold text-terminal-bright tracking-wider">
          DISCOVER
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1 opacity-60">
          Progressive intelligence filter — start broad, narrow to conviction
        </p>
      </div>

      {/* ═══ Context Strip ═══ */}
      <div
        className="flex items-center gap-6 mb-6"
        role="status"
        aria-label="Market context"
        style={{
          padding: '10px 16px',
          background: 'rgba(255,255,255,0.015)',
          border: '1px solid rgba(255,255,255,0.04)',
          borderRadius: '2px',
        }}
      >
        {macro && (
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-terminal-dim tracking-widest">REGIME</span>
            <span
              className="text-[10px] font-bold tracking-wider"
              style={{ color: macro.regime.includes('risk_on') ? '#00FF41' : macro.regime.includes('risk_off') ? '#FF073A' : '#FFB800' }}
            >
              {macro.regime.replace(/_/g, ' ').toUpperCase()}
            </span>
          </div>
        )}
        {cycle?.current && (
          <>
            <div className="w-px h-4" style={{ background: 'rgba(255,255,255,0.06)' }} aria-hidden="true" />
            <div className="flex items-center gap-2">
              <span className="text-[9px] text-terminal-dim tracking-widest">SENTIMENT</span>
              <span
                className="text-[10px] font-bold tracking-wider"
                style={{
                  color: cycle.current.cycle_position.includes('FEAR') ? '#FF073A'
                    : cycle.current.cycle_position.includes('GREED') ? '#00FF41' : '#FFB800',
                }}
              >
                {cycle.current.cycle_position}
              </span>
            </div>
          </>
        )}
        <div className="w-px h-4" style={{ background: 'rgba(255,255,255,0.06)' }} aria-hidden="true" />
        <div className="flex items-center gap-2">
          <span className="text-[9px] text-terminal-dim tracking-widest">UNIVERSE</span>
          <span className="text-[10px] text-terminal-text font-mono">{stocks.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[9px] text-terminal-dim tracking-widest">HIGH CONVICTION</span>
          <span className="text-[10px] font-mono" style={{ color: '#00FF41' }}>{stats.highConviction}</span>
        </div>
      </div>

      {/* ═══ Search ═══ */}
      <div className="mb-5">
        <label htmlFor="discover-search" className="sr-only">Search stocks</label>
        <input
          id="discover-search"
          type="text"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search symbol, company, or sector..."
          className="w-full text-[11px] tracking-wide outline-none transition-colors focus-visible:ring-1 focus-visible:ring-terminal-green"
          style={{
            padding: '10px 14px',
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '2px',
            color: '#C8C8C8',
            fontFamily: 'JetBrains Mono',
          }}
          onFocus={e => (e.target.style.borderColor = 'rgba(0,255,65,0.2)')}
          onBlur={e => (e.target.style.borderColor = 'rgba(255,255,255,0.06)')}
        />
      </div>

      {/* ═══ Filter Layers ═══ */}
      <div className="space-y-3 mb-6" role="group" aria-label="Filters">
        <div className="flex items-center gap-2">
          <span className="text-[8px] text-terminal-dim tracking-widest w-16 flex-shrink-0 opacity-40">CONVICTION</span>
          <div className="flex gap-1.5 flex-wrap" role="group" aria-label="Conviction filter">
            <Chip label="All" active={!selectedConviction} onClick={() => setSelectedConviction(null)} color="dim" />
            <Chip label="High" active={selectedConviction === 'HIGH'} count={stats.highConviction} onClick={() => setSelectedConviction(selectedConviction === 'HIGH' ? null : 'HIGH')} color="green" />
            <Chip label="Notable" active={selectedConviction === 'NOTABLE'} onClick={() => setSelectedConviction(selectedConviction === 'NOTABLE' ? null : 'NOTABLE')} color="amber" />
            <Chip label="Watch" active={selectedConviction === 'WATCH'} onClick={() => setSelectedConviction(selectedConviction === 'WATCH' ? null : 'WATCH')} color="dim" />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[8px] text-terminal-dim tracking-widest w-16 flex-shrink-0 opacity-40">SECTOR</span>
          <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide" role="group" aria-label="Sector filter">
            <Chip label="All" active={!selectedSector} onClick={() => setSelectedSector(null)} color="dim" />
            {sectors.map(s => (
              <Chip
                key={s.sector}
                label={s.sector}
                count={s.count}
                active={selectedSector === s.sector}
                onClick={() => setSelectedSector(selectedSector === s.sector ? null : s.sector)}
                color="cyan"
              />
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[8px] text-terminal-dim tracking-widest w-16 flex-shrink-0 opacity-40">SIGNALS</span>
          <div className="flex gap-1.5 flex-wrap" role="group" aria-label="Signal filters">
            <Chip label="Fat Pitches" active={showFatPitchesOnly} count={stats.fatPitches} onClick={() => setShowFatPitchesOnly(!showFatPitchesOnly)} color="green" />
            <Chip label="Insider Clusters" active={showInsiderOnly} count={stats.insiderClusters} onClick={() => setShowInsiderOnly(!showInsiderOnly)} color="cyan" />
            <Chip label="M&A Targets" active={showMAOnly} count={stats.maTargets} onClick={() => setShowMAOnly(!showMAOnly)} color="amber" />
            <Chip label="Unusual Options" active={showOptionsOnly} count={stats.unusualOptions} onClick={() => setShowOptionsOnly(!showOptionsOnly)} color="amber" />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[8px] text-terminal-dim tracking-widest w-16 flex-shrink-0 opacity-40">QUALITY</span>
          <div className="flex gap-1.5 flex-wrap" role="group" aria-label="Quality filters">
            <Chip label="No Conflicts" active={hideConflicts} onClick={() => setHideConflicts(!hideConflicts)} color="green" />
            <Chip label="Clean Books" active={hideForensicBlocked} onClick={() => setHideForensicBlocked(!hideForensicBlocked)} color="green" />
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[8px] text-terminal-dim tracking-widest w-16 flex-shrink-0 opacity-40">MIN SCORE</span>
          <div className="flex items-center gap-3" role="radiogroup" aria-label="Minimum score">
            {[0, 20, 40, 60, 80].map(v => (
              <Chip
                key={v}
                label={v === 0 ? 'Any' : `${v}+`}
                active={minScore === v}
                onClick={() => setMinScore(v)}
                color={v >= 60 ? 'green' : v >= 40 ? 'amber' : 'dim'}
              />
            ))}
          </div>
        </div>
      </div>

      {/* ═══ Results Bar ═══ */}
      <div className="flex items-center justify-between mb-5" aria-live="polite">
        <div className="flex items-center gap-3">
          <span className="text-[28px] font-display font-bold text-terminal-bright" style={{ lineHeight: 1 }}>
            {filtered.length}
          </span>
          <span className="text-[10px] text-terminal-dim tracking-widest opacity-50">
            OPPORTUNIT{filtered.length === 1 ? 'Y' : 'IES'}
          </span>
          {activeFilterCount > 0 && (
            <button
              onClick={clearAll}
              className="text-[9px] text-terminal-dim tracking-wider hover:text-terminal-green transition-colors ml-2 focus:outline-none focus-visible:ring-1 focus-visible:ring-terminal-green"
              style={{ padding: '2px 8px', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '2px' }}
            >
              CLEAR {activeFilterCount} FILTER{activeFilterCount > 1 ? 'S' : ''}
            </button>
          )}
        </div>
        <div className="flex items-center gap-1.5" role="radiogroup" aria-label="Sort order">
          <span className="text-[8px] text-terminal-dim tracking-widest opacity-40 mr-1">SORT</span>
          <Chip label="Score" active={sortKey === 'score'} onClick={() => setSortKey('score')} color="dim" />
          <Chip label="Modules" active={sortKey === 'modules'} onClick={() => setSortKey('modules')} color="dim" />
          <Chip label="A-Z" active={sortKey === 'name'} onClick={() => setSortKey('name')} color="dim" />
        </div>
      </div>

      {/* ═══ Results Grid ═══ */}
      {filtered.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-terminal-dim text-sm">No stocks match your filters</div>
          <button onClick={clearAll} className="text-terminal-green text-[11px] mt-2 hover:underline focus:outline-none focus-visible:underline">
            Clear all filters
          </button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
            {filtered.slice(0, visibleCount).map(stock => (
              <StockCard key={stock.symbol} stock={stock} />
            ))}
          </div>

          {/* Load More */}
          {hasMore && (
            <div className="text-center py-6">
              <button
                onClick={() => setVisibleCount(v => v + PAGE_SIZE)}
                className="text-[10px] tracking-widest transition-all duration-200 focus:outline-none focus-visible:ring-1 focus-visible:ring-terminal-green"
                style={{
                  padding: '8px 24px',
                  border: '1px solid rgba(0,255,65,0.2)',
                  borderRadius: '2px',
                  color: '#00FF41',
                  background: 'rgba(0,255,65,0.04)',
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,255,65,0.08)'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'rgba(0,255,65,0.04)'; }}
              >
                LOAD MORE ({filtered.length - visibleCount} remaining)
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
