'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import ModuleHeatstrip from '@/components/shared/ModuleHeatstrip';
import { MODULES, getModuleScore, scoreColor } from '@/lib/modules';
import { fg } from '@/lib/styles';

interface Props {
  onSymbolClick: (symbol: string) => void;
}

export default function FilterPanel({ onSymbolClick }: Props) {
  const [sectors, setSectors] = useState('');
  const [conviction, setConviction] = useState('');
  const [minScore, setMinScore] = useState('50');
  const [module, setModule] = useState('');
  const [minModuleScore, setMinModuleScore] = useState('60');
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const search = () => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (sectors) params.sectors = sectors;
    if (conviction) params.conviction = conviction;
    if (minScore) params.min_convergence = minScore;
    if (module) { params.module = module; params.min_module_score = minModuleScore; }
    api.funnelFilter(params).then(setResults).finally(() => setLoading(false));
  };

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
        <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Ad-Hoc Screener</div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div>
            <label className="text-[9px] text-gray-500 block mb-1">Sectors (comma-sep)</label>
            <input value={sectors} onChange={e => setSectors(e.target.value)} placeholder="Technology, Healthcare" className="w-full text-[11px] px-2 py-1.5 border border-gray-200 rounded-lg" />
          </div>
          <div>
            <label className="text-[9px] text-gray-500 block mb-1">Conviction</label>
            <select value={conviction} onChange={e => setConviction(e.target.value)} className="w-full text-[11px] px-2 py-1.5 border border-gray-200 rounded-lg">
              <option value="">All</option>
              <option value="HIGH">HIGH</option>
              <option value="NOTABLE">NOTABLE</option>
              <option value="WATCH">WATCH</option>
            </select>
          </div>
          <div>
            <label className="text-[9px] text-gray-500 block mb-1">Min Convergence</label>
            <input type="number" value={minScore} onChange={e => setMinScore(e.target.value)} className="w-full text-[11px] px-2 py-1.5 border border-gray-200 rounded-lg" />
          </div>
          <div>
            <label className="text-[9px] text-gray-500 block mb-1">Module</label>
            <select value={module} onChange={e => setModule(e.target.value)} className="w-full text-[11px] px-2 py-1.5 border border-gray-200 rounded-lg">
              <option value="">Any</option>
              {MODULES.filter(m => m.weight > 0).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <button onClick={search} className="w-full px-3 py-1.5 bg-emerald-600 text-white text-[11px] rounded-lg font-semibold hover:bg-emerald-700 transition-colors">
              {loading ? 'Searching...' : 'Search'}
            </button>
          </div>
        </div>
      </div>

      {results.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-2 border-b border-gray-100 text-[10px] text-gray-500">{results.length} results</div>
          <div className="divide-y divide-gray-50">
            {results.slice(0, 50).map(stock => {
              const moduleScores: Record<string, number> = {};
              for (const m of MODULES) {
                const v = getModuleScore(stock, m.key);
                if (v != null) moduleScores[m.key] = v;
              }
              return (
                <div key={stock.symbol} className="flex items-center gap-4 px-4 py-2.5 hover:bg-gray-50 transition-colors">
                  <button onClick={() => onSymbolClick(stock.symbol)} className="font-semibold text-xs text-gray-900 hover:text-emerald-600 w-16">
                    {stock.symbol}
                  </button>
                  <span className="text-[10px] text-gray-400 w-24 truncate">{stock.sector}</span>
                  <span className="text-xs font-mono font-bold w-8 text-right" {...fg(scoreColor(stock.convergence_score))}>
                    {stock.convergence_score?.toFixed(0)}
                  </span>
                  <span className="text-[9px] text-gray-500 uppercase tracking-wider w-16">{stock.conviction_level}</span>
                  <div className="flex-1"><ModuleHeatstrip scores={moduleScores} compact /></div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
