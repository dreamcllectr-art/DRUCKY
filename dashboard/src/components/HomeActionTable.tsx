'use client';

import type { Signal, ConvergenceSignal } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';
import TradeRangeBar from '@/components/TradeRangeBar';
import ModuleStrip from '@/components/ModuleStrip';
import { scoreColor } from '@/lib/modules';
import { fg, barW } from '@/lib/styles';

type ActionStock = Signal & { conv?: ConvergenceSignal };

interface ActionTableProps {
  actionStocks: ActionStock[];
  expandedAction: string | null;
  setExpandedAction: (s: string | null) => void;
}

export function HomeActionTable({ actionStocks, expandedAction, setExpandedAction }: ActionTableProps) {
  if (actionStocks.length === 0) return null;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs text-gray-500 tracking-[0.2em] uppercase">Full Action Table</h2>
        <span className="text-[9px] text-gray-500">Top {actionStocks.length} STRONG BUY · click row to expand</span>
      </div>
      <div className="panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase">
                <th className="text-left py-3 px-4 font-normal">Symbol</th>
                <th className="text-center py-3 px-2 font-normal">Signal</th>
                <th className="text-right py-3 px-2 font-normal">Composite</th>
                <th className="text-right py-3 px-2 font-normal">Conv.</th>
                <th className="text-center py-3 px-2 font-normal w-[200px]">Modules</th>
                <th className="text-center py-3 px-2 font-normal w-[140px]">Trade Setup</th>
                <th className="text-right py-3 px-4 font-normal">Size</th>
              </tr>
            </thead>
            <tbody>
              {actionStocks.map((s) => (
                <>
                  <tr
                    key={s.symbol}
                    className={`border-b border-gray-200/50 hover:bg-emerald-600/[0.03] transition-colors cursor-pointer ${
                      s.conv && s.conv.convergence_score >= 80 ? 'bg-emerald-600/[0.02]' : ''
                    }`}
                    onClick={() => setExpandedAction(expandedAction === s.symbol ? null : s.symbol)}
                  >
                    <td className="py-2.5 px-4">
                      <a
                        href={`/asset/${s.symbol}`}
                        className="font-mono font-bold text-gray-900 hover:text-emerald-600 transition-colors"
                        onClick={e => e.stopPropagation()}
                      >
                        {s.symbol}
                      </a>
                    </td>
                    <td className="py-2.5 px-2 text-center"><SignalBadge signal={s.signal} size="sm" /></td>
                    <td className="py-2.5 px-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-12 h-[3px] bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            {...barW(s.composite_score, scoreColor(s.composite_score))}
                          />
                        </div>
                        <span className="font-mono text-gray-700 w-8 text-right">{s.composite_score.toFixed(0)}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-12 h-[3px] bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full"
                            {...barW(s.conv?.convergence_score ?? 0, s.conv ? scoreColor(s.conv.convergence_score) : '#d1d5db')}
                          />
                        </div>
                        <span className="font-mono w-8 text-right" {...fg(s.conv ? scoreColor(s.conv.convergence_score) : '#9ca3af')}>
                          {s.conv?.convergence_score?.toFixed(0) ?? '\u2014'}
                        </span>
                      </div>
                    </td>
                    <td className="py-2.5 px-2">
                      {s.conv ? <ModuleStrip convergence={s.conv} mode="compact" /> : <span className="text-gray-500 text-[9px]">\u2014</span>}
                    </td>
                    <td className="py-2.5 px-2">
                      <div className="flex justify-center">
                        {s.entry_price != null ? <TradeRangeBar entry={s.entry_price} stop={s.stop_loss ?? s.entry_price * 0.95} target={s.target_price ?? s.entry_price * 1.1} width={130} height={14} showRR /> : <span className="text-gray-400 text-[9px]">{'\u2014'}</span>}
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-gray-500">
                      {s.position_size_dollars ? `$${(s.position_size_dollars / 1000).toFixed(0)}K` : '\u2014'}
                    </td>
                  </tr>
                  {expandedAction === s.symbol && s.conv && (
                    <tr key={`${s.symbol}-exp`} className="bg-gray-50/50">
                      <td colSpan={7} className="px-4 py-4">
                        <div className="grid grid-cols-2 gap-6">
                          <div className="space-y-3">
                            <div>
                              <div className="text-[9px] text-gray-500 tracking-wider mb-1">NARRATIVE</div>
                              <p className="text-[11px] text-gray-700 leading-relaxed">{s.conv.narrative || 'No narrative available.'}</p>
                            </div>
                            <div className="flex gap-6 text-[10px]">
                              <div>
                                <span className="text-gray-500">Entry </span>
                                <span className="text-blue-600 font-mono">{s.entry_price ? `$${s.entry_price.toFixed(2)}` : '—'}</span>
                              </div>
                              {s.stop_loss != null && s.entry_price != null && (
                              <div>
                                <span className="text-gray-500">Stop </span>
                                <span className="text-rose-600 font-mono">${s.stop_loss.toFixed(2)}</span>
                                <span className="text-gray-500 text-[8px] ml-1">({((1 - s.stop_loss / s.entry_price) * 100).toFixed(1)}%)</span>
                              </div>
                              )}
                              {s.target_price != null && s.entry_price != null && (
                              <div>
                                <span className="text-gray-500">Target </span>
                                <span className="text-emerald-600 font-mono">${s.target_price.toFixed(2)}</span>
                                <span className="text-gray-500 text-[8px] ml-1">(+{((s.target_price / s.entry_price - 1) * 100).toFixed(1)}%)</span>
                              </div>
                              )}
                              {s.rr_ratio != null && (
                              <div>
                                <span className="text-gray-500">R:R </span>
                                <span className="text-amber-600 font-mono font-bold">{s.rr_ratio.toFixed(1)}</span>
                              </div>
                              )}
                            </div>
                          </div>
                          <div>
                            <div className="text-[9px] text-gray-500 tracking-wider mb-2">MODULE BREAKDOWN</div>
                            <ModuleStrip convergence={s.conv} mode="expanded" />
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
