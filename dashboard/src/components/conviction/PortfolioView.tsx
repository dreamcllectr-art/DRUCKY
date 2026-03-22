'use client';

import { useState, useEffect } from 'react';
import { useStockPanel } from '@/contexts/StockPanelContext';
import { fmtM, fmt, GATE_COLORS, scoreTextCls } from '@/lib/utils';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Position {
  symbol: string;
  asset_class?: string;
  entry_date?: string;
  entry_price?: number;
  shares?: number;
  stop_loss?: number;
  target_price?: number;
  status?: string;
  current_price?: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
}

interface OnDeckEntry {
  symbol: string;
  name?: string;
  sector?: string;
  last_gate_passed: number;
  convergence_score?: number;
  composite_score?: number;
  signal?: string;
  is_fat_pitch?: boolean;
}

function fmtPct(v?: number | null): string {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function GateBadge({ gate }: { gate: number }) {
  const cls = GATE_COLORS[gate] ?? 'bg-gray-200 text-gray-600';
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded font-mono ${cls}`}>G{gate}</span>
  );
}

// ─── Empty state — no emoji, clean SVG ────────────────────────────────────────
function EmptyPositions() {
  return (
    <div className="bg-white rounded-xl border border-slate-200 px-8 py-10 text-center">
      <svg className="mx-auto mb-4 text-slate-200" width="40" height="40" viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="5" y="8" width="30" height="24" rx="3"/>
        <path d="M5 14h30"/>
        <path d="M13 20h14M13 25h9"/>
      </svg>
      <div className="text-[13px] font-semibold text-slate-500 mb-1">No open positions</div>
      <p className="text-[11px] text-slate-400 max-w-xs mx-auto leading-relaxed">
        Positions entered via the pipeline will appear here. High-conviction candidates are in the On Deck section below.
      </p>
    </div>
  );
}

// ─── Fat Pitch Card — premium 2-column layout ─────────────────────────────────
function FatPitchCard({ entry, onOpen }: { entry: OnDeckEntry; onOpen: (sym: string) => void }) {
  const score = entry.convergence_score ?? entry.composite_score;
  return (
    <div
      className="bg-white rounded-xl border border-slate-200 hover:border-emerald-300 hover:shadow-md transition-all cursor-pointer group"
      onClick={() => onOpen(entry.symbol)}
    >
      <div className="p-4 border-b border-slate-100">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[15px] font-bold text-slate-900 font-mono group-hover:text-emerald-700 transition-colors">
                {entry.symbol}
              </span>
              <span className="text-[7px] font-bold bg-emerald-500 text-white px-1.5 py-0.5 rounded-full uppercase tracking-widest">
                Fat Pitch
              </span>
              <GateBadge gate={entry.last_gate_passed} />
            </div>
            {entry.name && <div className="text-[11px] text-slate-500 leading-tight">{entry.name}</div>}
            {entry.sector && <div className="text-[10px] text-slate-400 mt-0.5">{entry.sector}</div>}
          </div>
          <div className="text-right">
            <div className={`text-[20px] font-bold font-mono leading-none ${scoreTextCls(score)}`}>
              {score?.toFixed(0) ?? '—'}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5 uppercase tracking-wider">Score</div>
          </div>
        </div>
      </div>
      <div className="px-4 py-2.5">
        <span className="text-[10px] font-semibold text-emerald-700 group-hover:text-emerald-600 transition-colors">
          View Chart & Setup →
        </span>
      </div>
    </div>
  );
}

// ─── High Conv Row — compact list style, not card grid ────────────────────────
function ConvictionRow({ entry, onOpen }: { entry: OnDeckEntry; onOpen: (sym: string) => void }) {
  const score = entry.convergence_score ?? entry.composite_score;
  return (
    <div
      className="flex items-center gap-4 px-4 py-3 border-b border-slate-50 last:border-0 hover:bg-slate-50 transition-colors cursor-pointer group"
      onClick={() => onOpen(entry.symbol)}
    >
      <div className="w-[52px] shrink-0">
        <span className="text-[12px] font-bold text-slate-900 font-mono group-hover:text-emerald-700 transition-colors">
          {entry.symbol}
        </span>
      </div>
      <GateBadge gate={entry.last_gate_passed} />
      <div className="flex-1 min-w-0">
        <div className="text-[11px] text-slate-500 truncate">{entry.name ?? '—'}</div>
        {entry.sector && <div className="text-[10px] text-slate-400">{entry.sector}</div>}
      </div>
      <div className={`text-[13px] font-bold font-mono shrink-0 ${scoreTextCls(score)}`}>
        {score?.toFixed(0) ?? '—'}
      </div>
      <svg className="text-slate-300 group-hover:text-emerald-500 transition-colors shrink-0" width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 3l4 4-4 4"/>
      </svg>
    </div>
  );
}

export default function PortfolioView() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [onDeck, setOnDeck] = useState<OnDeckEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { open: openStock } = useStockPanel();

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/portfolio`).then(r => { if (!r.ok) throw new Error('portfolio'); return r.json(); }),
      fetch(`${API}/api/alpha/stack?min_gate=8`).then(r => { if (!r.ok) throw new Error('stack'); return r.json(); }),
    ]).then(([pos, stack]) => {
      const posList: Position[] = Array.isArray(pos) ? pos : [];
      const posSymbols = new Set(posList.map(p => p.symbol));
      setPositions(posList);
      setOnDeck((Array.isArray(stack) ? stack : []).filter((s: OnDeckEntry) => !posSymbols.has(s.symbol)));
    }).catch(e => {
      setError(`Failed to load: ${e.message}`);
    }).finally(() => setLoading(false));
  }, []);

  const openPositions = positions.filter(p => p.status === 'open' || !p.status);
  const totalPnl = openPositions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const fatPitches = onDeck.filter(s => s.is_fat_pitch || s.last_gate_passed >= 10);
  const highConv = onDeck.filter(s => !s.is_fat_pitch && s.last_gate_passed < 10);

  if (loading) {
    return (
      <div className="h-[calc(100vh-88px)] overflow-y-auto bg-slate-50 p-5 space-y-5">
        {[1,2,3].map(i => (
          <div key={i} className="skeleton h-20 rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="bg-rose-50 border border-rose-200 rounded-xl px-6 py-4 text-center">
          <div className="text-[11px] font-semibold text-rose-700 mb-1">Could not load portfolio</div>
          <div className="text-[10px] text-rose-500">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-88px)] overflow-y-auto bg-slate-50 p-5 space-y-6">

      {/* ── Active Positions ── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">Active Positions</h2>
          {openPositions.length > 0 && (
            <span className={`text-[11px] font-mono font-bold ${totalPnl >= 0 ? 'text-emerald-600' : 'text-rose-500'}`}>
              Total P&L: {totalPnl >= 0 ? '+' : ''}{fmtM(totalPnl)}
            </span>
          )}
        </div>

        {openPositions.length === 0 ? <EmptyPositions /> : (
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  {['Symbol','Entry','Current','Stop','Target','P&L',''].map((h,i) => (
                    <th key={i} className={`${i < 6 ? (i === 0 ? 'text-left' : 'text-right') : ''} px-4 py-2.5 text-[10px] font-bold tracking-widest text-slate-400 uppercase`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {openPositions.map(pos => {
                  const pnl = pos.unrealized_pnl_pct;
                  return (
                    <tr key={pos.symbol} className="border-b border-slate-50 last:border-0 hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3">
                        <button onClick={() => openStock(pos.symbol)} className="text-left hover:text-emerald-600 transition-colors">
                          <div className="text-[12px] font-bold text-slate-900 font-mono">{pos.symbol}</div>
                          {pos.entry_date && <div className="text-[10px] text-slate-400">{pos.entry_date}</div>}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right"><span className="text-[11px] font-mono text-slate-500">{pos.entry_price ? `$${fmt(pos.entry_price, 2)}` : '—'}</span></td>
                      <td className="px-4 py-3 text-right"><span className="text-[11px] font-mono text-slate-800 font-semibold">{pos.current_price ? `$${fmt(pos.current_price, 2)}` : '—'}</span></td>
                      <td className="px-4 py-3 text-right"><span className="text-[11px] font-mono text-rose-500">{pos.stop_loss ? `$${fmt(pos.stop_loss, 2)}` : '—'}</span></td>
                      <td className="px-4 py-3 text-right"><span className="text-[11px] font-mono text-emerald-600">{pos.target_price ? `$${fmt(pos.target_price, 2)}` : '—'}</span></td>
                      <td className="px-4 py-3 text-right">
                        <span className={`text-[11px] font-mono font-bold ${pnl == null ? 'text-slate-400' : pnl >= 0 ? 'text-emerald-600' : 'text-rose-500'}`}>
                          {fmtPct(pnl)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => openStock(pos.symbol)} className="text-[10px] text-slate-400 hover:text-emerald-600 transition-colors">Chart →</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── On Deck ── */}
      <section>
        <div className="mb-4">
          <h2 className="text-[10px] font-bold tracking-widest text-slate-500 uppercase">On Deck</h2>
          <p className="text-[11px] text-slate-400 mt-0.5">
            High-conviction stocks that passed Gate 8+ — waiting for entry trigger
          </p>
        </div>

        {onDeck.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200 p-6 text-center text-[11px] text-slate-400">
            No stocks currently at Gate 8+. Run the pipeline to refresh.
          </div>
        ) : (
          <div className="space-y-5">

            {/* Fat Pitches — asymmetric 2-column */}
            {fatPitches.length > 0 && (
              <div>
                <div className="text-[10px] font-bold tracking-widest text-emerald-600 uppercase mb-2.5 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block animate-pulse" />
                  Fat Pitches — Gate 10 · Maximum Conviction
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {fatPitches.map(s => <FatPitchCard key={s.symbol} entry={s} onOpen={openStock} />)}
                </div>
              </div>
            )}

            {/* High Conviction — compact list rows */}
            {highConv.length > 0 && (
              <div>
                <div className="text-[10px] font-bold tracking-widest text-sky-600 uppercase mb-2.5 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-sky-500 inline-block" />
                  High Conviction — Gate 8–9
                </div>
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                  {highConv.slice(0, 12).map(s => (
                    <ConvictionRow key={s.symbol} entry={s} onOpen={openStock} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
