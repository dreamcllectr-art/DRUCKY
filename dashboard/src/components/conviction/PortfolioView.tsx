'use client';

import { useState, useEffect } from 'react';
import { useStockPanel } from '@/contexts/StockPanelContext';

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

function fmt(v?: number | null, d = 2): string {
  if (v == null) return '—';
  return v.toFixed(d);
}

function fmtPct(v?: number | null): string {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

const GATE_COLORS: Record<number, string> = {
  10: 'bg-emerald-600 text-white',
  9: 'bg-emerald-500 text-white',
  8: 'bg-teal-500 text-white',
  7: 'bg-sky-500 text-white',
};

function GateBadge({ gate }: { gate: number }) {
  const cls = GATE_COLORS[gate] || 'bg-gray-200 text-gray-600';
  return (
    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${cls}`}>G{gate}</span>
  );
}

export default function PortfolioView() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [onDeck, setOnDeck] = useState<OnDeckEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const { open: openStock } = useStockPanel();

  useEffect(() => {
    Promise.all([
      fetch(`${API}/api/portfolio`).then(r => r.json()).catch(() => []),
      fetch(`${API}/api/alpha/stack?min_gate=8`).then(r => r.json()).catch(() => []),
    ]).then(([pos, stack]) => {
      setPositions(Array.isArray(pos) ? pos : pos.positions || []);
      const posSymbols = new Set((Array.isArray(pos) ? pos : pos.positions || []).map((p: Position) => p.symbol));
      setOnDeck((Array.isArray(stack) ? stack : []).filter((s: OnDeckEntry) => !posSymbols.has(s.symbol)));
      setLoading(false);
    });
  }, []);

  const openPositions = positions.filter(p => p.status === 'open' || !p.status);
  const totalPnl = openPositions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const fatPitches = onDeck.filter(s => s.is_fat_pitch || s.last_gate_passed >= 10);
  const highConv = onDeck.filter(s => !s.is_fat_pitch && s.last_gate_passed < 10);

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-[11px] text-gray-400">Loading portfolio...</div>;
  }

  return (
    <div className="h-[calc(100vh-88px)] overflow-y-auto bg-gray-50 p-5 space-y-5">

      {/* ── Active Positions ── */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] font-bold tracking-widest text-gray-500 uppercase">Active Positions</h2>
          {openPositions.length > 0 && (
            <span className={`text-[11px] font-mono font-bold ${totalPnl >= 0 ? 'text-emerald-600' : 'text-rose-500'}`}>
              Total P&L: {totalPnl >= 0 ? '+' : ''}{totalPnl >= 1000 ? `$${(totalPnl / 1000).toFixed(1)}k` : `$${totalPnl.toFixed(0)}`}
            </span>
          )}
        </div>

        {openPositions.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
            <div className="text-2xl mb-2">📭</div>
            <div className="text-[12px] font-semibold text-gray-500 mb-1">No open positions</div>
            <p className="text-[10px] text-gray-400 max-w-xs mx-auto">
              Positions entered via the pipeline will appear here. High-conviction candidates are in the On Deck section below.
            </p>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left px-4 py-2 text-[9px] font-bold tracking-widest text-gray-400 uppercase">Symbol</th>
                  <th className="text-right px-4 py-2 text-[9px] font-bold tracking-widest text-gray-400 uppercase">Entry</th>
                  <th className="text-right px-4 py-2 text-[9px] font-bold tracking-widest text-gray-400 uppercase">Current</th>
                  <th className="text-right px-4 py-2 text-[9px] font-bold tracking-widest text-gray-400 uppercase">Stop</th>
                  <th className="text-right px-4 py-2 text-[9px] font-bold tracking-widest text-gray-400 uppercase">Target</th>
                  <th className="text-right px-4 py-2 text-[9px] font-bold tracking-widest text-gray-400 uppercase">P&L</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {openPositions.map(pos => {
                  const pnl = pos.unrealized_pnl_pct;
                  return (
                    <tr key={pos.symbol} className="border-b border-gray-50 last:border-0 hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3">
                        <button onClick={() => openStock(pos.symbol)} className="text-left hover:text-emerald-600 transition-colors">
                          <div className="text-[12px] font-bold text-gray-900 font-mono">{pos.symbol}</div>
                          {pos.entry_date && <div className="text-[9px] text-gray-400">{pos.entry_date}</div>}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="text-[11px] font-mono text-gray-600">${fmt(pos.entry_price)}</span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="text-[11px] font-mono text-gray-800">{pos.current_price ? `$${fmt(pos.current_price)}` : '—'}</span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="text-[11px] font-mono text-rose-500">{pos.stop_loss ? `$${fmt(pos.stop_loss)}` : '—'}</span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="text-[11px] font-mono text-emerald-600">{pos.target_price ? `$${fmt(pos.target_price)}` : '—'}</span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`text-[11px] font-mono font-bold ${pnl == null ? 'text-gray-400' : pnl >= 0 ? 'text-emerald-600' : 'text-rose-500'}`}>
                          {fmtPct(pnl)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => openStock(pos.symbol)}
                          className="text-[9px] text-gray-400 hover:text-emerald-600 transition-colors"
                        >
                          Chart →
                        </button>
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
        <div className="mb-3">
          <h2 className="text-[10px] font-bold tracking-widest text-gray-500 uppercase">On Deck</h2>
          <p className="text-[10px] text-gray-400 mt-0.5">High-conviction stocks that passed Gate 8+ — waiting for entry trigger</p>
        </div>

        {onDeck.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 p-6 text-center text-[10px] text-gray-400">
            No stocks currently at Gate 8+. Run the pipeline to refresh.
          </div>
        ) : (
          <div className="space-y-3">
            {/* Fat Pitches */}
            {fatPitches.length > 0 && (
              <div>
                <div className="text-[9px] font-bold tracking-widest text-emerald-600 uppercase mb-2 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
                  Fat Pitches — Gate 10 · Maximum Conviction
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {fatPitches.map(s => <OnDeckCard key={s.symbol} entry={s} onOpen={openStock} />)}
                </div>
              </div>
            )}

            {/* High Conviction */}
            {highConv.length > 0 && (
              <div>
                <div className="text-[9px] font-bold tracking-widest text-sky-600 uppercase mb-2 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-sky-500 inline-block" />
                  High Conviction — Gate 8–9
                </div>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {highConv.slice(0, 12).map(s => <OnDeckCard key={s.symbol} entry={s} onOpen={openStock} />)}
                </div>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function OnDeckCard({ entry, onOpen }: { entry: OnDeckEntry; onOpen: (sym: string) => void }) {
  const score = entry.convergence_score ?? entry.composite_score;
  const scoreColor = score == null ? 'text-gray-400' : score >= 70 ? 'text-emerald-600' : score >= 50 ? 'text-amber-600' : 'text-rose-500';

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:border-gray-300 transition-colors">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <button
            onClick={() => onOpen(entry.symbol)}
            className="text-[13px] font-bold text-gray-900 font-mono hover:text-emerald-600 transition-colors"
          >
            {entry.symbol}
          </button>
          {entry.is_fat_pitch && (
            <span className="text-[7px] font-bold bg-emerald-500 text-white px-1.5 py-0.5 rounded-full uppercase tracking-widest">Fat Pitch</span>
          )}
          <GateBadge gate={entry.last_gate_passed} />
        </div>
        <span className={`text-[12px] font-bold font-mono ${scoreColor}`}>{score?.toFixed(0) ?? '—'}</span>
      </div>
      <div className="text-[10px] text-gray-400 truncate">{entry.name || entry.sector || ''}</div>
      {entry.sector && entry.name && (
        <div className="text-[9px] text-gray-300 mt-0.5">{entry.sector}</div>
      )}
      <button
        onClick={() => onOpen(entry.symbol)}
        className="mt-3 w-full text-[9px] text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg py-1.5 hover:bg-emerald-100 transition-colors font-semibold"
      >
        View Chart & Setup →
      </button>
    </div>
  );
}
