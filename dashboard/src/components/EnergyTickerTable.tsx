import type { EnergyIntelSignal } from '@/lib/api';
import { EnergyScoreBar } from '@/components/EnergyScoreBar';
import { Tooltip } from '@/components/shared/Tooltip';
import { ENERGY_DEFS } from '@/lib/definitions';

const CATEGORY_BG: Record<string, string> = {
  upstream: 'bg-[#05966915] text-[#059669]',
  downstream: 'bg-[#d9770615] text-[#d97706]',
  midstream: 'bg-[#3b82f615] text-[#3b82f6]',
  ofs: 'bg-[#f9731615] text-[#f97316]',
  lng: 'bg-[#a78bfa15] text-[#a78bfa]',
};

function scoreColorClass(score: number) {
  return score >= 65 ? 'text-[#059669]' : score >= 45 ? 'text-[#d97706]' : 'text-[#e11d48]';
}

export function EnergyTickerTable({ signals }: { signals: EnergyIntelSignal[] }) {
  if (signals.length === 0) return null;

  // Group by category — scores are sector-level (EIA/JODI commodity data), not stock-specific
  const grouped = signals.reduce<Record<string, { rep: EnergyIntelSignal; tickers: string[] }>>((acc, s) => {
    const cat = s.ticker_category;
    if (!acc[cat]) acc[cat] = { rep: s, tickers: [] };
    if (!acc[cat].tickers.includes(s.symbol)) acc[cat].tickers.push(s.symbol);
    return acc;
  }, {});

  return (
    <div className="panel overflow-hidden">
      <div className="p-4 border-b border-gray-200 flex items-center justify-between">
        <h2 className="text-xs tracking-widest text-gray-500 uppercase">Energy Sector Scores</h2>
        <span className="text-[9px] text-gray-400">Scores are sector-level (EIA/JODI data) · stock differentiation via other modules</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 text-[9px] text-gray-500 tracking-widest uppercase">
              <th className="text-left px-4 py-2">Category</th>
              <th className="text-left px-4 py-2 w-48">Score</th>
              <th className="text-right px-4 py-2"><Tooltip text={ENERGY_DEFS.inventory} position="bottom">Inventory</Tooltip></th>
              <th className="text-right px-4 py-2"><Tooltip text={ENERGY_DEFS.production} position="bottom">Production</Tooltip></th>
              <th className="text-right px-4 py-2"><Tooltip text={ENERGY_DEFS.demand} position="bottom">Demand</Tooltip></th>
              <th className="text-right px-4 py-2"><Tooltip text={ENERGY_DEFS.trade_flows} position="bottom">Flows</Tooltip></th>
              <th className="text-right px-4 py-2"><Tooltip text={ENERGY_DEFS.global} position="bottom">Global</Tooltip></th>
              <th className="text-left px-4 py-2">Tickers</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(grouped).map(([cat, { rep, tickers }]) => {
              const cc = scoreColorClass(rep.energy_intel_score);
              const catClass = CATEGORY_BG[cat] || 'bg-[#6b728015] text-[#6b7280]';
              return (
                <tr key={cat} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3">
                    <span className={`text-[9px] tracking-wider px-1.5 py-0.5 rounded font-semibold ${catClass}`}>
                      {cat.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3"><EnergyScoreBar score={rep.energy_intel_score} /></td>
                  <td className={`px-4 py-3 text-right font-mono ${cc}`}>{rep.inventory_signal?.toFixed(0)}</td>
                  <td className={`px-4 py-3 text-right font-mono ${cc}`}>{rep.production_signal?.toFixed(0)}</td>
                  <td className={`px-4 py-3 text-right font-mono ${cc}`}>{rep.demand_signal?.toFixed(0)}</td>
                  <td className={`px-4 py-3 text-right font-mono ${cc}`}>{rep.trade_flow_signal?.toFixed(0)}</td>
                  <td className={`px-4 py-3 text-right font-mono ${cc}`}>{rep.global_balance_signal?.toFixed(0)}</td>
                  <td className="px-4 py-3 text-[9px] text-gray-500 font-mono">{tickers.join(' · ')}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
