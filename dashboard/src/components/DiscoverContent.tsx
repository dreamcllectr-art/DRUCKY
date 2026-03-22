'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { api, type DiscoverStock, type MacroData, type SentimentCycle } from '@/lib/api';
import Link from 'next/link';
import { cs } from '@/lib/styles';

const scoreColor = (v: number) => v >= 70 ? '#059669' : v >= 50 ? '#10b981' : v >= 30 ? '#d97706' : '#e11d48';
const convictionColor = (c: string) => {
  if (c === 'HIGH') return { bg: 'rgba(5,150,105,0.1)', border: 'rgba(5,150,105,0.3)', text: '#059669' };
  if (c === 'NOTABLE') return { bg: 'rgba(217,119,6,0.08)', border: 'rgba(217,119,6,0.2)', text: '#d97706' };
  return { bg: 'rgba(85,85,85,0.1)', border: 'rgba(85,85,85,0.2)', text: '#6b7280' };
};
const moduleDisplayName: Record<string, string> = {
  main_signal: 'Signal', smartmoney: 'Smart $', worldview: 'Macro', variant: 'Variant',
  research: 'Research', reddit: 'Reddit', news_displacement: 'News', alt_data: 'Alt Data',
  sector_expert: 'Sector', pairs: 'Pairs', ma: 'M&A', energy_intel: 'Energy',
  prediction_markets: 'Prediction', pattern_options: 'Patterns', ai_exec: 'AI Exec',
  estimate_momentum: 'Est. Mom', ai_regulatory: 'AI Reg', consensus_blindspots: 'Blindspots',
};

function ScoreArc({ score, size = 56 }: { score: number; size?: number }) {
  const r = (size - 6) / 2;
  const circ = 2 * Math.PI * r;
  const dashOffset = circ * (1 - Math.min(score, 100) / 100 * 0.75);
  const color = scoreColor(score);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="flex-shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(0,0,0,0.06)" strokeWidth={3} strokeDasharray={`${circ * 0.75} ${circ * 0.25}`} transform={`rotate(135 ${size / 2} ${size / 2})`} strokeLinecap="round" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={3} strokeDasharray={`${circ * 0.75} ${circ * 0.25}`} strokeDashoffset={dashOffset} transform={`rotate(135 ${size / 2} ${size / 2})`} strokeLinecap="round" {...cs({ filter: `drop-shadow(0 0 4px ${color}40)`, transition: 'stroke-dashoffset 0.6s ease' })} />
      <text x={size / 2} y={size / 2 + 1} textAnchor="middle" dominantBaseline="middle" fill={color} fontSize={14} fontFamily="JetBrains Mono" fontWeight="bold">{score.toFixed(0)}</text>
    </svg>
  );
}

function Chip({ label, active, count, onClick }: { label: string; active: boolean; count?: number; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`transition-all flex items-center gap-1.5 whitespace-nowrap px-3 py-1 rounded-lg text-[10px] font-semibold tracking-wider uppercase border ${active ? 'bg-emerald-600/10 border-emerald-600/35 text-emerald-600' : 'bg-transparent border-gray-200 text-[#9ca3af]'}`}>
      {label}{count !== undefined && <span className="text-[10px] opacity-60">{count}</span>}
    </button>
  );
}

const PAGE_SIZE = 60;

export default function DiscoverContent() {
  const [stocks, setStocks] = useState<DiscoverStock[]>([]);
  const [loading, setLoading] = useState(true);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [selectedConviction, setSelectedConviction] = useState<string | null>(null);
  const [showFatPitchesOnly, setShowFatPitchesOnly] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [sortKey, setSortKey] = useState<'score' | 'modules' | 'name'>('score');
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    setLoading(true); setError(null);
    api.discover()
      .then(setStocks)
      .catch(e => setError(e.message || 'Failed to load universe'))
      .finally(() => setLoading(false));
  }, [retryCount]);
  useEffect(() => { setVisibleCount(PAGE_SIZE); }, [selectedSector, selectedConviction, showFatPitchesOnly, minScore, sortKey, searchQuery]);

  const sectors = useMemo(() => {
    const map = new Map<string, number>();
    stocks.forEach(s => { if (s.sector) map.set(s.sector, (map.get(s.sector) || 0) + 1); });
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1]).map(([sector, count]) => ({ sector, count }));
  }, [stocks]);

  const filtered = useMemo(() => {
    let result = [...stocks];
    if (searchQuery) { const q = searchQuery.toUpperCase(); result = result.filter(s => s.symbol.includes(q) || s.company_name?.toUpperCase().includes(q) || s.sector?.toUpperCase().includes(q)); }
    if (selectedSector) result = result.filter(s => s.sector === selectedSector);
    if (selectedConviction) result = result.filter(s => s.conviction_level === selectedConviction);
    if (showFatPitchesOnly) result = result.filter(s => s.is_fat_pitch);
    if (minScore > 0) result = result.filter(s => s.convergence_score >= minScore);
    if (sortKey === 'score') result.sort((a, b) => b.convergence_score - a.convergence_score);
    else if (sortKey === 'modules') result.sort((a, b) => b.module_count - a.module_count);
    else result.sort((a, b) => a.symbol.localeCompare(b.symbol));
    return result;
  }, [stocks, searchQuery, selectedSector, selectedConviction, showFatPitchesOnly, minScore, sortKey]);

  const clearAll = useCallback(() => { setSelectedSector(null); setSelectedConviction(null); setShowFatPitchesOnly(false); setMinScore(0); setSearchQuery(''); }, []);

  if (loading) return <div className="flex items-center justify-center h-[40vh]"><div className="text-gray-400 text-sm font-display tracking-widest animate-pulse">Loading coverage universe...</div></div>;
  if (error) return <div className="panel p-8 text-center"><div className="text-rose-600 text-sm font-bold mb-2">Failed to load universe</div><p className="text-[11px] text-gray-500 mb-4">{error}</p><button onClick={() => setRetryCount(c => c + 1)} className="px-4 py-2 text-[10px] tracking-widest text-emerald-600 border border-emerald-600/30 rounded-lg hover:bg-emerald-600/5">RETRY</button></div>;

  return (
    <div className="space-y-4">
      <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search symbol, company, or sector..." className="w-full text-[11px] tracking-wide outline-none px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-[#374151] font-mono focus:border-emerald-600/20" />
      <div className="space-y-2">
        <div className="flex items-center gap-2"><span className="text-[8px] text-gray-500 tracking-widest w-16 opacity-40">CONVICTION</span>
          <Chip label="All" active={!selectedConviction} onClick={() => setSelectedConviction(null)} />
          <Chip label="High" active={selectedConviction === 'HIGH'} count={stocks.filter(s => s.conviction_level === 'HIGH').length} onClick={() => setSelectedConviction(selectedConviction === 'HIGH' ? null : 'HIGH')} />
        </div>
        <div className="flex items-center gap-2"><span className="text-[8px] text-gray-500 tracking-widest w-16 opacity-40">SECTOR</span>
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            <Chip label="All" active={!selectedSector} onClick={() => setSelectedSector(null)} />
            {sectors.slice(0, 10).map(s => <Chip key={s.sector} label={s.sector} count={s.count} active={selectedSector === s.sector} onClick={() => setSelectedSector(selectedSector === s.sector ? null : s.sector)} />)}
          </div>
        </div>
        <div className="flex items-center gap-2"><span className="text-[8px] text-gray-500 tracking-widest w-16 opacity-40">MIN SCORE</span>
          {[0, 40, 60, 80].map(v => <Chip key={v} label={v === 0 ? 'Any' : `${v}+`} active={minScore === v} onClick={() => setMinScore(v)} />)}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-[28px] font-display font-bold text-gray-900 leading-none">{filtered.length}</span>
          <span className="text-[10px] text-gray-500 tracking-widest opacity-50">SECURITIES</span>
          {(selectedSector || selectedConviction || showFatPitchesOnly || minScore > 0) && <button onClick={clearAll} className="text-[10px] text-gray-500 tracking-wider hover:text-emerald-600 px-2 py-0.5 border border-gray-200 rounded-lg">CLEAR</button>}
        </div>
        <div className="flex items-center gap-1.5"><span className="text-[8px] text-gray-500 tracking-widest opacity-40 mr-1">SORT</span>
          <Chip label="Score" active={sortKey === 'score'} onClick={() => setSortKey('score')} />
          <Chip label="Modules" active={sortKey === 'modules'} onClick={() => setSortKey('modules')} />
          <Chip label="A-Z" active={sortKey === 'name'} onClick={() => setSortKey('name')} />
        </div>
      </div>
      {filtered.length === 0 ? <div className="text-center py-20 text-gray-400 text-sm">No securities match the current filter criteria. <button onClick={clearAll} className="text-emerald-600 text-[11px] ml-2 hover:underline">Reset Filters</button></div> : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
            {filtered.slice(0, visibleCount).map(stock => {
              const conv = convictionColor(stock.conviction_level);
              let modules: string[] = [];
              try { modules = JSON.parse(stock.active_modules || '[]'); } catch { modules = (stock.active_modules || '').split(',').map(m => m.trim()).filter(Boolean); }
              return (
                <Link key={stock.symbol} href={`/asset/${stock.symbol}`}>
                  <div className="group relative overflow-hidden transition-all duration-300 hover:border-emerald-600/15 bg-white border border-gray-200 rounded-lg p-5 cursor-pointer">
                    <div className="flex items-start gap-4">
                      <ScoreArc score={stock.convergence_score} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2.5">
                          <span className="text-[15px] font-bold text-gray-900 tracking-wide">{stock.symbol}</span>
                          <span className="text-[10px] font-semibold tracking-widest px-2 py-0.5 rounded-lg" {...cs({ background: conv.bg, border: `1px solid ${conv.border}`, color: conv.text })}>{stock.conviction_level}</span>
                        </div>
                        <div className="text-[10px] text-gray-500 truncate mt-1" title={stock.company_name ?? stock.symbol}>{stock.company_name ?? stock.symbol} {stock.sector && <span className="opacity-50 ml-1">{stock.sector}</span>}</div>
                      </div>
                      <div className="text-right flex-shrink-0"><div className="text-[10px] text-gray-500">{stock.module_count} sources</div></div>
                    </div>
                    {stock.is_fat_pitch && <span className="text-[8px] font-bold tracking-widest mt-2 inline-block px-1.5 py-0.5 rounded-lg bg-[#05966912] border border-[#05966930] text-[#059669]">ASYMMETRIC SETUP</span>}
                    <div className="flex flex-wrap gap-1 mt-3">{modules.slice(0, 8).map(m => <span key={m} className="text-[8px] tracking-wider px-1 py-0.5 rounded-lg bg-gray-50 text-gray-500">{moduleDisplayName[m] ?? m}</span>)}</div>
                    {stock.narrative && <p className="text-[10px] text-gray-500 mt-3 leading-relaxed line-clamp-2 opacity-60">{stock.narrative}</p>}
                  </div>
                </Link>
              );
            })}
          </div>
          {filtered.length > visibleCount && <div className="text-center py-6"><button onClick={() => setVisibleCount(v => v + PAGE_SIZE)} className="text-[10px] tracking-widest px-6 py-2 border border-emerald-600/20 rounded-lg text-emerald-600 bg-[rgba(5,150,105,0.04)]">LOAD MORE ({filtered.length - visibleCount} remaining)</button></div>}
        </>
      )}
    </div>
  );
}
