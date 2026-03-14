'use client';

import { useEffect, useState } from 'react';
import { api, type Position } from '@/lib/api';

export default function PortfolioPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.portfolio().then(data => {
      setPositions(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">LOADING PORTFOLIO...</div>
      </div>
    );
  }

  const totalInvested = positions.reduce((s, p) => s + p.entry_price * p.shares, 0);
  const totalCurrent = positions.reduce((s, p) => s + p.current_value, 0);
  const totalPnl = positions.reduce((s, p) => s + p.pnl, 0);
  const portfolioValue = 50000;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          PORTFOLIO
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          PRESERVATION OF CAPITAL AND HOME RUNS
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="panel p-5">
          <div className="text-[10px] text-terminal-dim tracking-wider uppercase mb-1">Total Invested</div>
          <div className="text-2xl font-display font-bold text-terminal-bright">
            ${totalInvested.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
        </div>
        <div className="panel p-5">
          <div className="text-[10px] text-terminal-dim tracking-wider uppercase mb-1">Current Value</div>
          <div className="text-2xl font-display font-bold text-terminal-bright">
            ${totalCurrent.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
        </div>
        <div className="panel p-5">
          <div className="text-[10px] text-terminal-dim tracking-wider uppercase mb-1">Total P&L</div>
          <div className={`text-2xl font-display font-bold ${totalPnl >= 0 ? 'text-terminal-green glow-green' : 'text-terminal-red glow-red'}`}>
            {totalPnl >= 0 ? '+' : ''}${totalPnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
          <div className={`text-[10px] font-mono ${totalPnl >= 0 ? 'text-terminal-green' : 'text-terminal-red'}`}>
            {totalInvested > 0 ? `${((totalPnl / totalInvested) * 100).toFixed(2)}%` : '0%'}
          </div>
        </div>
        <div className="panel p-5">
          <div className="text-[10px] text-terminal-dim tracking-wider uppercase mb-1">Exposure</div>
          <div className="text-2xl font-display font-bold text-terminal-amber">
            {((totalCurrent / portfolioValue) * 100).toFixed(0)}%
          </div>
          <div className="text-[10px] text-terminal-dim">of ${portfolioValue.toLocaleString()}</div>
        </div>
      </div>

      {/* Positions */}
      {positions.length === 0 ? (
        <div className="panel p-8 text-center">
          <div className="text-terminal-green text-2xl mb-4 glow-green">◆</div>
          <p className="text-terminal-dim text-sm">
            No open positions. Use the screener to find setups and log trades via the API.
          </p>
          <pre className="mt-4 text-[10px] text-terminal-green bg-terminal-bg p-3 rounded inline-block">
            POST /api/portfolio — symbol, entry_price, shares
          </pre>
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <span className="text-[10px] text-terminal-dim tracking-widest uppercase">
              Open Positions — {positions.length}
            </span>
          </div>
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                <th className="text-left py-3 px-4 font-normal">Symbol</th>
                <th className="text-left py-3 px-2 font-normal">Class</th>
                <th className="text-right py-3 px-2 font-normal">Entry</th>
                <th className="text-right py-3 px-2 font-normal">Current</th>
                <th className="text-right py-3 px-2 font-normal">Shares</th>
                <th className="text-right py-3 px-2 font-normal">Value</th>
                <th className="text-right py-3 px-2 font-normal">P&L</th>
                <th className="text-right py-3 px-2 font-normal">P&L %</th>
                <th className="text-right py-3 px-2 font-normal">Stop</th>
                <th className="text-right py-3 px-4 font-normal">Target</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(pos => {
                const hitStop = pos.stop_loss && pos.current_price <= pos.stop_loss;
                const hitTarget = pos.target_price && pos.current_price >= pos.target_price;

                return (
                  <tr
                    key={pos.id}
                    className={`border-b border-terminal-border/50 transition-colors ${
                      hitStop ? 'bg-terminal-red/5' : hitTarget ? 'bg-terminal-green/5' : 'hover:bg-terminal-green/[0.03]'
                    }`}
                  >
                    <td className="py-3 px-4">
                      <a href={`/asset/${pos.symbol}`} className="font-mono font-bold text-terminal-bright hover:text-terminal-green">
                        {pos.symbol}
                      </a>
                      {hitStop && <span className="ml-2 text-[9px] text-terminal-red font-mono">STOP HIT</span>}
                      {hitTarget && <span className="ml-2 text-[9px] text-terminal-green font-mono">TARGET HIT</span>}
                    </td>
                    <td className="py-3 px-2 text-terminal-dim">{pos.asset_class}</td>
                    <td className="py-3 px-2 text-right font-mono">${pos.entry_price.toFixed(2)}</td>
                    <td className="py-3 px-2 text-right font-mono text-terminal-bright">${pos.current_price.toFixed(2)}</td>
                    <td className="py-3 px-2 text-right font-mono">{pos.shares.toFixed(2)}</td>
                    <td className="py-3 px-2 text-right font-mono">${pos.current_value.toLocaleString()}</td>
                    <td className={`py-3 px-2 text-right font-mono font-bold ${pos.pnl >= 0 ? 'text-terminal-green' : 'text-terminal-red'}`}>
                      {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString()}
                    </td>
                    <td className={`py-3 px-2 text-right font-mono ${pos.pnl_pct >= 0 ? 'text-terminal-green' : 'text-terminal-red'}`}>
                      {pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct.toFixed(2)}%
                    </td>
                    <td className="py-3 px-2 text-right font-mono text-terminal-red">
                      {pos.stop_loss ? `$${pos.stop_loss.toFixed(2)}` : '—'}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-terminal-green">
                      {pos.target_price ? `$${pos.target_price.toFixed(2)}` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
