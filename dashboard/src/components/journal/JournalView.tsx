'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { JournalPosition } from '@/lib/api';
import Dossier from '@/components/conviction/Dossier';
import SlideOverPanel from '@/components/shared/SlideOverPanel';
import { fg, cs } from '@/lib/styles';

export default function JournalView() {
  const [openPositions, setOpenPositions] = useState<JournalPosition[]>([]);
  const [closedPositions, setClosedPositions] = useState<any[]>([]);
  const [selected, setSelected] = useState<JournalPosition | null>(null);
  const [tab, setTab] = useState<'open' | 'closed'>('open');
  const [noteText, setNoteText] = useState('');
  const [addingPosition, setAddingPosition] = useState(false);
  const [newPos, setNewPos] = useState({ symbol: '', shares: '', entry_price: '', stop_loss: '', target_price: '', entry_thesis: '' });
  const [dossierSymbol, setDossierSymbol] = useState<string | null>(null);
  const [closingId, setClosingId] = useState<number | null>(null);
  const [closePrice, setClosePrice] = useState('');
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    Promise.all([api.journalOpen(), api.journalClosed()])
      .then(([o, c]) => { setOpenPositions(o); setClosedPositions(c); })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, []);

  const addNote = async () => {
    if (!selected || !noteText.trim()) return;
    await api.journalNote({ portfolio_id: selected.id, symbol: selected.symbol, entry_type: 'note', content: noteText });
    setNoteText('');
    refresh();
  };

  const closePosition = async (id: number, exitPrice: string) => {
    if (!exitPrice) return;
    await api.portfolioClose(id, { exit_price: parseFloat(exitPrice) });
    refresh();
  };

  const createPosition = async () => {
    if (!newPos.symbol) return;
    await api.portfolioCreate({
      symbol: newPos.symbol.toUpperCase(),
      shares: parseFloat(newPos.shares) || 100,
      entry_price: parseFloat(newPos.entry_price) || 0,
      stop_loss: parseFloat(newPos.stop_loss) || null,
      target_price: parseFloat(newPos.target_price) || null,
      entry_thesis: newPos.entry_thesis,
    });
    setAddingPosition(false);
    setNewPos({ symbol: '', shares: '', entry_price: '', stop_loss: '', target_price: '', entry_thesis: '' });
    refresh();
  };

  if (loading) return <div className="text-gray-400 text-sm p-8 text-center">Loading journal...</div>;

  return (
    <div className="space-y-4">
      {/* Tabs + Add button */}
      <div className="flex items-center gap-3">
        {(['open', 'closed'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1.5 rounded-lg transition-colors ${
              tab === t ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'text-gray-500 hover:bg-gray-50 border border-transparent'
            }`}
          >
            {t === 'open' ? `Open (${openPositions.length})` : `Closed (${closedPositions.length})`}
          </button>
        ))}
        <button onClick={() => setAddingPosition(true)} className="ml-auto text-[10px] px-3 py-1.5 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 transition-colors">
          + Add Position
        </button>
      </div>

      {/* Add Position Form */}
      {addingPosition && (
        <div className="bg-white rounded-xl border border-emerald-200 p-4 shadow-sm">
          <div className="text-[10px] text-gray-400 tracking-widest uppercase mb-3">New Position</div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            {[
              { key: 'symbol', label: 'Symbol', placeholder: 'AAPL' },
              { key: 'shares', label: 'Shares', placeholder: '100' },
              { key: 'entry_price', label: 'Entry Price', placeholder: '150.00' },
              { key: 'stop_loss', label: 'Stop Loss', placeholder: '140.00' },
              { key: 'target_price', label: 'Target', placeholder: '180.00' },
            ].map(f => (
              <div key={f.key}>
                <label className="text-[10px] text-gray-500 block mb-1">{f.label}</label>
                <input
                  value={(newPos as any)[f.key]}
                  onChange={e => setNewPos(prev => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  className="w-full text-[11px] px-2 py-1.5 border border-gray-200 rounded-lg"
                />
              </div>
            ))}
            <div className="flex items-end gap-2">
              <button onClick={createPosition} className="px-3 py-1.5 bg-emerald-600 text-white text-[10px] rounded-lg font-semibold">Create</button>
              <button onClick={() => setAddingPosition(false)} className="px-3 py-1.5 text-gray-500 text-[10px] rounded-lg hover:bg-gray-50">Cancel</button>
            </div>
          </div>
          <div className="mt-2">
            <label className="text-[10px] text-gray-500 block mb-1">Entry Thesis</label>
            <textarea
              value={newPos.entry_thesis}
              onChange={e => setNewPos(prev => ({ ...prev, entry_thesis: e.target.value }))}
              placeholder="Why are you taking this position?"
              className="w-full text-[11px] px-2 py-1.5 border border-gray-200 rounded-lg h-16"
            />
          </div>
        </div>
      )}

      {/* Open Positions */}
      {tab === 'open' && (
        <div className="flex gap-4" style={{ minHeight: '500px' }}>
          {/* Position List */}
          <div className="w-[40%] bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
              {openPositions.map(pos => (
                <button
                  key={pos.id}
                  onClick={() => setSelected(pos)}
                  className={`w-full text-left px-4 py-3 border-b border-gray-50 transition-colors ${
                    selected?.id === pos.id ? 'bg-emerald-50 border-l-2 border-l-emerald-500' : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-gray-900">{pos.symbol}</span>
                    <span className="text-xs font-mono" {...fg(pos.pnl_pct >= 0 ? '#059669' : '#e11d48')}>
                      {pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct?.toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex items-center justify-between mt-0.5 text-[10px] text-gray-400">
                    <span>{pos.days_held}d held</span>
                    <span>
                      {pos.score_delta != null && (
                        <span {...fg(pos.score_delta >= 0 ? '#059669' : '#e11d48')}>
                          {pos.score_delta >= 0 ? '+' : ''}{pos.score_delta?.toFixed(0)} score
                        </span>
                      )}
                    </span>
                  </div>
                </button>
              ))}
              {openPositions.length === 0 && !addingPosition && (
                <div className="text-center py-12 px-6">
                  <div className="text-gray-900 text-sm font-semibold mb-2">Your Trading Journal</div>
                  <div className="text-[11px] text-gray-400 leading-relaxed mb-4">
                    Track positions, record entry theses, add notes as trades develop, and review your closed trade history. The journal connects to convergence scores so you can see how conviction evolved during a hold.
                  </div>
                  <button
                    onClick={() => setAddingPosition(true)}
                    className="px-4 py-2 bg-emerald-600 text-white text-xs rounded-lg font-semibold hover:bg-emerald-700 transition-colors"
                  >
                    + Add Your First Position
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Detail Panel */}
          <div className="flex-1 bg-white rounded-xl border border-gray-200 shadow-sm p-5 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 220px)' }}>
            {selected ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-lg font-bold text-gray-900">{selected.symbol}</div>
                    <div className="text-[10px] text-gray-400">Entry: {selected.entry_date} @ ${selected.entry_price?.toFixed(2)} | {selected.days_held}d held</div>
                  </div>
                  <button onClick={() => setDossierSymbol(selected.symbol)} className="text-[10px] text-emerald-600 hover:underline">Full Dossier</button>
                </div>

                {/* P&L + Convergence Delta */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-[10px] text-gray-400 uppercase tracking-widest">P&L</div>
                    <div className="text-lg font-bold font-mono" {...fg(selected.pnl_pct >= 0 ? '#059669' : '#e11d48')}>
                      {selected.pnl_pct >= 0 ? '+' : ''}{selected.pnl_pct?.toFixed(1)}%
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-[10px] text-gray-400 uppercase tracking-widest">Score Delta</div>
                    <div className="text-lg font-bold font-mono" {...fg(selected.score_delta != null && selected.score_delta >= 0 ? '#059669' : '#e11d48')}>
                      {selected.score_delta != null ? `${selected.score_delta >= 0 ? '+' : ''}${selected.score_delta.toFixed(0)}` : '\u2014'}
                    </div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="text-[10px] text-gray-400 uppercase tracking-widest">Current Score</div>
                    <div className="text-lg font-bold font-mono text-gray-700">{selected.current_convergence?.toFixed(0) || '\u2014'}</div>
                  </div>
                </div>

                {/* Entry Thesis */}
                {selected.entry_thesis && (
                  <div>
                    <div className="text-[10px] text-gray-400 tracking-widest uppercase mb-1">Entry Thesis</div>
                    <div className="text-xs text-gray-700 bg-gray-50 rounded-lg p-3 leading-relaxed">{selected.entry_thesis}</div>
                  </div>
                )}

                {/* Add Note */}
                <div>
                  <div className="text-[10px] text-gray-400 tracking-widest uppercase mb-1">Add Note</div>
                  <div className="flex gap-2">
                    <input
                      value={noteText}
                      onChange={e => setNoteText(e.target.value)}
                      placeholder="Market context, thesis update, decision rationale..."
                      className="flex-1 text-[11px] px-3 py-2 border border-gray-200 rounded-lg"
                      onKeyDown={e => e.key === 'Enter' && addNote()}
                    />
                    <button onClick={addNote} className="px-3 py-2 bg-emerald-600 text-white text-[10px] rounded-lg font-semibold hover:bg-emerald-700">Add</button>
                  </div>
                </div>

                {/* Close Position */}
                <div className="pt-2 border-t border-gray-100">
                  {closingId === selected.id ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        step="0.01"
                        value={closePrice}
                        onChange={e => setClosePrice(e.target.value)}
                        placeholder={selected.current_price?.toFixed(2) || 'Exit price'}
                        className="w-28 text-[11px] px-2 py-1.5 border border-gray-200 rounded-lg"
                        onKeyDown={e => {
                          if (e.key === 'Enter' && closePrice) { closePosition(selected.id, closePrice); setClosingId(null); setClosePrice(''); }
                          if (e.key === 'Escape') { setClosingId(null); setClosePrice(''); }
                        }}
                        autoFocus
                      />
                      <button
                        onClick={() => { if (closePrice) { closePosition(selected.id, closePrice); setClosingId(null); setClosePrice(''); } }}
                        className="px-2 py-1.5 bg-rose-600 text-white text-[10px] rounded-lg font-semibold hover:bg-rose-700"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => { setClosingId(null); setClosePrice(''); }}
                        className="text-[10px] text-gray-400 hover:text-gray-600"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => { setClosingId(selected.id); setClosePrice(selected.current_price?.toFixed(2) || ''); }}
                      className="text-[10px] text-rose-600 hover:underline"
                    >
                      Close Position
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-gray-400 text-sm text-center py-12">
                {openPositions.length > 0 ? 'Select a position to view details' : 'Add a position to get started. Use the Funnel view to find high-conviction candidates.'}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Closed Positions */}
      {tab === 'closed' && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-100 text-[10px] text-gray-400 tracking-widest uppercase">
                <th className="text-left px-4 py-2.5">Symbol</th>
                <th className="text-right px-2 py-2.5">Entry</th>
                <th className="text-right px-2 py-2.5">Exit</th>
                <th className="text-right px-2 py-2.5">Return</th>
                <th className="text-left px-2 py-2.5">Entry Date</th>
                <th className="text-left px-2 py-2.5">Exit Date</th>
                <th className="text-left px-4 py-2.5">Notes</th>
              </tr>
            </thead>
            <tbody>
              {closedPositions.map((pos, i) => (
                <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-4 py-2 font-semibold text-gray-900">{pos.symbol}</td>
                  <td className="px-2 py-2 text-right font-mono">${pos.entry_price?.toFixed(2)}</td>
                  <td className="px-2 py-2 text-right font-mono">${pos.exit_price?.toFixed(2)}</td>
                  <td className="px-2 py-2 text-right font-mono font-bold" {...fg(pos.return_pct >= 0 ? '#059669' : '#e11d48')}>
                    {pos.return_pct >= 0 ? '+' : ''}{pos.return_pct?.toFixed(1)}%
                  </td>
                  <td className="px-2 py-2 text-gray-500">{pos.entry_date}</td>
                  <td className="px-2 py-2 text-gray-500">{pos.exit_date}</td>
                  <td className="px-4 py-2 text-gray-400 truncate max-w-[200px]">{pos.notes}</td>
                </tr>
              ))}
              {closedPositions.length === 0 && (
                <tr><td colSpan={7} className="text-center py-6 text-gray-400 text-xs">No closed positions</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Dossier Slide-Over */}
      <SlideOverPanel open={!!dossierSymbol} onClose={() => setDossierSymbol(null)} title={dossierSymbol || ''}>
        {dossierSymbol && <Dossier symbol={dossierSymbol} />}
      </SlideOverPanel>
    </div>
  );
}
