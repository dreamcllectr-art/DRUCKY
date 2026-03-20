'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { ConvictionBoardItem } from '@/lib/api';
import Dossier from './Dossier';
import { fg, cs } from '@/lib/styles';
import { scoreColor } from '@/lib/modules';

export default function ConvictionBoard() {
  const [items, setItems] = useState<ConvictionBoardItem[]>([]);
  const [blocked, setBlocked] = useState<any[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [showBlocked, setShowBlocked] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.convictionBoard(), api.convictionBlocked()])
      .then(([board, bl]) => { setItems(board); setBlocked(bl); if (board.length > 0) setSelected(board[0].symbol); })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-400 text-sm p-8 text-center">Loading conviction board...</div>;

  // Stats
  const totalExposure = items.reduce((sum, i) => sum + ((i as any).position_size_dollars || 0), 0);
  const sectors = new Set(items.map(i => i.sector));
  const avgRR = items.filter(i => (i as any).rr_ratio).reduce((sum, i) => sum + ((i as any).rr_ratio || 0), 0) / Math.max(items.filter(i => (i as any).rr_ratio).length, 1);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm flex items-center gap-6">
        <div>
          <div className="text-[9px] text-gray-400 tracking-widest uppercase">Actionable</div>
          <div className="text-xl font-bold text-emerald-600">{items.length}</div>
        </div>
        <div>
          <div className="text-[9px] text-gray-400 tracking-widest uppercase">Total Exposure</div>
          <div className="text-sm font-mono text-gray-700">{totalExposure > 0 ? `$${(totalExposure / 1000).toFixed(0)}k` : '\u2014'}</div>
        </div>
        <div>
          <div className="text-[9px] text-gray-400 tracking-widest uppercase">Sectors</div>
          <div className="text-sm font-mono text-gray-700">{sectors.size}</div>
        </div>
        <div>
          <div className="text-[9px] text-gray-400 tracking-widest uppercase">Avg R:R</div>
          <div className="text-sm font-mono text-gray-700">{items.length > 0 ? avgRR.toFixed(1) : '\u2014'}</div>
        </div>
        {blocked.length > 0 && (
          <button onClick={() => setShowBlocked(!showBlocked)} className="ml-auto text-[10px] text-rose-600 hover:underline">
            {blocked.length} blocked
          </button>
        )}
      </div>

      {/* Master-Detail Layout */}
      <div className="flex gap-4" style={{ minHeight: '600px' }}>
        {/* Left: Tiered Position List */}
        <div className="w-[30%] shrink-0 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 280px)' }}>
            {items.length === 0 ? (
              <div className="text-center py-8 px-4">
                <div className="text-gray-400 text-xs">No assets meet conviction threshold</div>
                <div className="text-[10px] text-gray-300 mt-1">Top assets will appear here when scores reach HIGH conviction. Check the Funnel view for WATCH-level candidates.</div>
              </div>
            ) : (
              (['HIGH', 'NOTABLE', 'WATCH'] as const).map(tier => {
                const tierItems = items.filter(i => ((i as any).effective_conviction ?? i.conviction_level ?? 'WATCH') === tier);
                if (tierItems.length === 0) return null;
                const tierColors: Record<string, string> = { HIGH: '#059669', NOTABLE: '#d97706', WATCH: '#9ca3af' };
                return (
                  <div key={tier}>
                    <div className="px-4 py-1.5 bg-gray-50 border-y border-gray-100 flex items-center gap-2">
                      <span className="text-[8px] font-bold tracking-widest uppercase" style={{ color: tierColors[tier] }}>{tier}</span>
                      <span className="text-[8px] text-gray-400">{tierItems.length}</span>
                    </div>
                    {tierItems.map(item => (
                      <button
                        key={item.symbol}
                        onClick={() => setSelected(item.symbol)}
                        className={`w-full text-left px-4 py-2.5 border-b border-gray-50 transition-colors ${
                          selected === item.symbol ? 'bg-emerald-50 border-l-2 border-l-emerald-500' : 'hover:bg-gray-50'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-gray-900">{item.symbol}</span>
                          <span className="text-xs font-mono font-bold" {...fg(scoreColor((item as any).best_score ?? item.convergence_score))}>
                            {((item as any).best_score ?? item.convergence_score)?.toFixed(0)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between mt-0.5">
                          <span className="text-[9px] text-gray-400 truncate">{item.sector}</span>
                          <div className="flex items-center gap-1.5">
                            {(item as any).asset_class && (item as any).asset_class !== 'stock' && (
                              <span className="text-[7px] font-bold uppercase tracking-wider px-1 py-0.5 rounded bg-blue-50 text-blue-600">
                                {(item as any).asset_class}
                              </span>
                            )}
                            <span className="text-[9px] text-gray-400">R:R {(item as any).rr_ratio?.toFixed(1) || '\u2014'}</span>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Dossier */}
        <div className="flex-1 bg-white rounded-xl border border-gray-200 shadow-sm p-5 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 220px)' }}>
          {selected ? <Dossier symbol={selected} /> : (
            <div className="text-gray-400 text-sm text-center py-12">
              {items.length > 0 ? 'Select a position' : 'No HIGH conviction stocks yet. Use the Funnel to explore WATCH-level candidates.'}
            </div>
          )}
        </div>
      </div>

      {/* Blocked */}
      {showBlocked && blocked.length > 0 && (
        <div className="bg-rose-50 rounded-xl border border-rose-200 p-4">
          <div className="text-[9px] text-rose-600 tracking-widest uppercase font-semibold mb-2">Forensic Blocked ({blocked.length})</div>
          <div className="space-y-1">
            {blocked.map((b: any) => (
              <div key={b.symbol} className="flex items-center gap-3 text-[11px]">
                <span className="font-semibold text-gray-900 w-16">{b.symbol}</span>
                <span className="text-gray-500">{b.company_name}</span>
                <span className="text-rose-600 ml-auto">{b.alert_type}: {b.forensic_detail?.slice(0, 80)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
