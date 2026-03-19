'use client';

import { useState, useEffect, Fragment } from 'react';
import { api } from '@/lib/api';
import ModuleHeatstrip from '@/components/shared/ModuleHeatstrip';
import EvidencePanel from './EvidencePanel';
import { cs, fg } from '@/lib/styles';
import { scoreColor, MODULES, getModuleScore } from '@/lib/modules';

interface Props {
  onSymbolClick: (symbol: string) => void;
}

function convictionBadge(level: string) {
  const colors: Record<string, { bg: string; fg: string }> = {
    HIGH: { bg: 'rgba(5,150,105,0.1)', fg: '#059669' },
    NOTABLE: { bg: 'rgba(217,119,6,0.1)', fg: '#d97706' },
    WATCH: { bg: 'rgba(156,163,175,0.1)', fg: '#6b7280' },
  };
  const c = colors[level] || colors.WATCH;
  return (
    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded" {...cs({ backgroundColor: c.bg, color: c.fg })}>
      {level}
    </span>
  );
}

export default function ConvictionFilter({ onSymbolClick }: Props) {
  const [stocks, setStocks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [filterConviction, setFilterConviction] = useState<string>('');

  useEffect(() => {
    api.funnelStage(5).then(setStocks).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-400 text-sm p-8 text-center">Loading conviction data...</div>;

  const filtered = filterConviction
    ? stocks.filter(s => s.conviction_level === filterConviction)
    : stocks;

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <span className="text-[9px] text-gray-400 tracking-widest uppercase">Filter:</span>
        {['', 'HIGH', 'NOTABLE', 'WATCH'].map(level => (
          <button
            key={level}
            onClick={() => setFilterConviction(level)}
            className={`text-[10px] px-2 py-1 rounded-md transition-colors ${
              filterConviction === level
                ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                : 'text-gray-500 hover:bg-gray-50 border border-transparent'
            }`}
          >
            {level || 'All'}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-gray-400">{filtered.length} stocks</span>
      </div>

      {/* Stock list */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-[80px_100px_50px_70px_40px_1fr_60px_50px] gap-1 px-4 py-2 border-b border-gray-100 text-[8px] text-gray-400 tracking-widest uppercase">
          <div>Symbol</div>
          <div>Sector</div>
          <div className="text-right">Score</div>
          <div className="text-center">Conviction</div>
          <div className="text-right">Mod</div>
          <div>Module Agreement</div>
          <div className="text-right">Signal</div>
          <div className="text-right">R:R</div>
        </div>

        {/* Rows */}
        <div className="divide-y divide-gray-50">
          {filtered.slice(0, 100).map(stock => {
            const expanded = expandedSymbol === stock.symbol;
            const moduleScores: Record<string, number> = {};
            for (const m of MODULES) {
              const v = getModuleScore(stock, m.key);
              if (v != null) moduleScores[m.key] = v;
            }

            return (
              <div key={stock.symbol}>
                <div
                  className={`grid grid-cols-[80px_100px_50px_70px_40px_1fr_60px_50px] gap-1 items-center px-4 py-2.5 cursor-pointer transition-colors ${
                    expanded ? 'bg-emerald-50/30' : 'hover:bg-gray-50/50'
                  }`}
                  onClick={() => setExpandedSymbol(expanded ? null : stock.symbol)}
                >
                  <div>
                    <button
                      onClick={e => { e.stopPropagation(); onSymbolClick(stock.symbol); }}
                      className="font-semibold text-xs text-gray-900 hover:text-emerald-600 transition-colors"
                    >
                      {stock.symbol}
                    </button>
                    <div className="text-[9px] text-gray-400 truncate">{stock.company_name}</div>
                  </div>
                  <div className="text-[10px] text-gray-500 truncate">{stock.sector}</div>
                  <div className="text-right text-xs font-mono font-bold" {...fg(scoreColor(stock.convergence_score))}>
                    {stock.convergence_score?.toFixed(0)}
                  </div>
                  <div className="text-center">{convictionBadge(stock.conviction_level)}</div>
                  <div className="text-right text-[10px] text-gray-500">{stock.module_count}</div>
                  <div><ModuleHeatstrip scores={moduleScores} compact /></div>
                  <div className="text-right">
                    {stock.signal && (
                      <span className={`text-[9px] font-bold uppercase tracking-wider ${
                        stock.signal.includes('BUY') ? 'text-emerald-600' : stock.signal.includes('SELL') ? 'text-rose-600' : 'text-gray-500'
                      }`}>
                        {stock.signal}
                      </span>
                    )}
                  </div>
                  <div className="text-right text-xs font-mono text-gray-600">
                    {stock.rr_ratio != null ? stock.rr_ratio.toFixed(1) : '\u2014'}
                  </div>
                </div>
                {expanded && (
                  <div className="px-6 py-0 bg-gray-50/50 border-t border-gray-100">
                    <EvidencePanel symbol={stock.symbol} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
