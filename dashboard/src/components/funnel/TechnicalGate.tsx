'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { cs, fg } from '@/lib/styles';
import { scoreColor } from '@/lib/modules';

interface Props {
  onSymbolClick: (symbol: string) => void;
}

export default function TechnicalGate({ onSymbolClick }: Props) {
  const [stocks, setStocks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.funnelStage(4).then(setStocks).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-gray-400 text-sm p-8 text-center">Loading technical gate...</div>;

  const passed = stocks.filter(s => s.status === 'passed');
  const flagged = stocks.filter(s => s.status === 'flagged');

  const StockRow = ({ stock }: { stock: any }) => (
    <button
      onClick={() => onSymbolClick(stock.symbol)}
      className="flex items-center justify-between w-full px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-900">{stock.symbol}</span>
        <span className="text-[9px] text-gray-400">{stock.sector}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-[10px] font-mono font-bold" {...fg(scoreColor(stock.total_score))}>
          {stock.total_score?.toFixed(0)}
        </span>
        {stock.conviction_level && (
          <span className="text-[8px] text-gray-400 uppercase tracking-wider">{stock.conviction_level}</span>
        )}
      </div>
    </button>
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Passed */}
      <div className="bg-white rounded-xl border-2 border-emerald-100 shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-emerald-50 border-b border-emerald-100 flex items-center justify-between">
          <span className="text-[10px] text-emerald-700 font-semibold uppercase tracking-widest">Passed</span>
          <span className="text-[10px] text-emerald-600 font-mono">{passed.length}</span>
        </div>
        <div className="p-2 max-h-[600px] overflow-y-auto space-y-0.5">
          {passed.slice(0, 100).map(s => <StockRow key={s.symbol} stock={s} />)}
          {passed.length === 0 && <div className="text-[10px] text-gray-400 p-4 text-center">No stocks passed</div>}
        </div>
      </div>

      {/* Flagged */}
      <div className="bg-white rounded-xl border-2 border-amber-100 shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-amber-50 border-b border-amber-100 flex items-center justify-between">
          <span className="text-[10px] text-amber-700 font-semibold uppercase tracking-widest">Flagged</span>
          <span className="text-[10px] text-amber-600 font-mono">{flagged.length}</span>
        </div>
        <div className="p-2 max-h-[600px] overflow-y-auto space-y-0.5">
          {flagged.slice(0, 100).map(s => <StockRow key={s.symbol} stock={s} />)}
          {flagged.length === 0 && <div className="text-[10px] text-gray-400 p-4 text-center">No stocks flagged</div>}
        </div>
      </div>
    </div>
  );
}
