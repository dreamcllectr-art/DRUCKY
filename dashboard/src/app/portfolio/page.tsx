'use client';

import { useEffect, useState } from 'react';
import { api, type Position } from '@/lib/api';
import WatchlistTab from '@/components/WatchlistTab';

const TABS = ['Positions', 'Watchlist'] as const;

export default function PortfolioPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Positions');
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.portfolio().then(d => { setPositions(d); setLoading(false); }).catch(() => setLoading(false)); }, []);

  const totalInvested = positions.reduce((s, p) => s + p.entry_price * p.shares, 0);
  const totalCurrent = positions.reduce((s, p) => s + p.current_value, 0);
  const totalPnl = positions.reduce((s, p) => s + p.pnl, 0);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-gray-900 tracking-tight">PORTFOLIO</h1>
        <p className="text-[10px] text-gray-500 tracking-widest mt-1">POSITIONS + WATCHLIST</p>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map(t => (<button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-[10px] tracking-widest border-b-2 transition-all ${tab === t ? 'text-emerald-600 border-emerald-600' : 'text-gray-500 border-transparent hover:text-gray-700'}`}>{t.toUpperCase()}</button>))}
      </div>

      {tab === 'Positions' && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <div className="panel p-5"><div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Total Invested</div><div className="text-2xl font-display font-bold text-gray-900">${totalInvested.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div></div>
            <div className="panel p-5"><div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Current Value</div><div className="text-2xl font-display font-bold text-gray-900">${totalCurrent.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div></div>
            <div className="panel p-5"><div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Total P&L</div><div className={`text-2xl font-display font-bold ${totalPnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{totalPnl >= 0 ? '+' : ''}${totalPnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}</div></div>
            <div className="panel p-5"><div className="text-[10px] text-gray-500 tracking-wider uppercase mb-1">Exposure</div><div className="text-2xl font-display font-bold text-amber-600">{((totalCurrent / 50000) * 100).toFixed(0)}%</div></div>
          </div>
          {loading ? <div className="text-gray-500 animate-pulse text-center py-8">Loading...</div> : positions.length === 0 ? (
            <div className="panel p-8 text-center"><p className="text-gray-500 text-sm">No open positions.</p></div>
          ) : (
            <div className="panel overflow-hidden">
              <table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">Entry</th><th className="text-right py-3 px-2 font-normal">Current</th><th className="text-right py-3 px-2 font-normal">Value</th><th className="text-right py-3 px-2 font-normal">P&L</th><th className="text-right py-3 px-2 font-normal">P&L %</th><th className="text-right py-3 px-2 font-normal">Stop</th><th className="text-right py-3 px-4 font-normal">Target</th></tr></thead>
                <tbody>{positions.map(pos => (
                  <tr key={pos.id} className={`border-b border-gray-200/50 transition-colors ${pos.stop_loss && pos.current_price <= pos.stop_loss ? 'bg-rose-600/5' : pos.target_price && pos.current_price >= pos.target_price ? 'bg-emerald-600/5' : 'hover:bg-emerald-600/[0.03]'}`}>
                    <td className="py-3 px-4"><a href={`/asset/${pos.symbol}`} className="font-mono font-bold text-gray-900 hover:text-emerald-600">{pos.symbol}</a></td>
                    <td className="py-3 px-2 text-right font-mono">${pos.entry_price.toFixed(2)}</td>
                    <td className="py-3 px-2 text-right font-mono text-gray-900">${pos.current_price.toFixed(2)}</td>
                    <td className="py-3 px-2 text-right font-mono">${pos.current_value.toLocaleString()}</td>
                    <td className={`py-3 px-2 text-right font-mono font-bold ${pos.pnl >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString()}</td>
                    <td className={`py-3 px-2 text-right font-mono ${pos.pnl_pct >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct.toFixed(2)}%</td>
                    <td className="py-3 px-2 text-right font-mono text-rose-600">{pos.stop_loss ? `$${pos.stop_loss.toFixed(2)}` : '--'}</td>
                    <td className="py-3 px-4 text-right font-mono text-emerald-600">{pos.target_price ? `$${pos.target_price.toFixed(2)}` : '--'}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      )}
      {tab === 'Watchlist' && <WatchlistTab />}
    </div>
  );
}
