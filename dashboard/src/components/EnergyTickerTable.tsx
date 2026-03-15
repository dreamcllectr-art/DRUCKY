import type { EnergyIntelSignal } from '@/lib/api';
import { EnergyScoreBar } from '@/components/EnergyScoreBar';

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

  return (
    <div className="panel overflow-hidden">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-xs tracking-widest text-gray-500 uppercase">Energy Ticker Scores</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 text-[9px] text-gray-500 tracking-widest uppercase">
              <th className="text-left px-4 py-2">Symbol</th>
              <th className="text-left px-4 py-2">Category</th>
              <th className="text-left px-4 py-2 w-48">Score</th>
              <th className="text-right px-4 py-2">Inventory</th>
              <th className="text-right px-4 py-2">Production</th>
              <th className="text-right px-4 py-2">Demand</th>
              <th className="text-right px-4 py-2">Flows</th>
              <th className="text-right px-4 py-2">Global</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s) => {
              const cc = scoreColorClass(s.energy_intel_score);
              const catClass = CATEGORY_BG[s.ticker_category] || 'bg-[#6b728015] text-[#6b7280]';
              return (
                <tr key={s.symbol} className="border-b border-gray-200/30 hover:bg-white/[0.02]">
                  <td className="px-4 py-2 font-mono font-bold text-gray-900">{s.symbol}</td>
                  <td className="px-4 py-2">
                    <span className={`text-[9px] tracking-wider px-1.5 py-0.5 rounded ${catClass}`}>
                      {s.ticker_category.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-2"><EnergyScoreBar score={s.energy_intel_score} /></td>
                  <td className={`px-4 py-2 text-right font-mono ${cc}`}>{s.inventory_signal?.toFixed(0)}</td>
                  <td className={`px-4 py-2 text-right font-mono ${cc}`}>{s.production_signal?.toFixed(0)}</td>
                  <td className={`px-4 py-2 text-right font-mono ${cc}`}>{s.demand_signal?.toFixed(0)}</td>
                  <td className={`px-4 py-2 text-right font-mono ${cc}`}>{s.trade_flow_signal?.toFixed(0)}</td>
                  <td className={`px-4 py-2 text-right font-mono ${cc}`}>{s.global_balance_signal?.toFixed(0)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
