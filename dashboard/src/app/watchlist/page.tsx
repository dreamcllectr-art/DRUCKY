'use client';

import { useEffect, useState } from 'react';
import { api, type WatchlistItem } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = () => {
    api.watchlist().then(data => {
      setItems(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  };

  useEffect(loadData, []);

  const handleAdd = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    const params = new URLSearchParams();
    params.set('symbol', (data.get('symbol') as string).toUpperCase());
    params.set('asset_class', data.get('asset_class') as string);
    params.set('notes', data.get('notes') as string);

    await fetch(`/api/watchlist?${params}`, { method: 'POST' });
    form.reset();
    loadData();
  };

  const handleRemove = async (symbol: string) => {
    await fetch(`/api/watchlist/${symbol}`, { method: 'DELETE' });
    loadData();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">LOADING WATCHLIST...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          WATCHLIST
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          TRACK HIGH-CONVICTION SETUPS · {items.length} ASSETS
        </p>
      </div>

      {/* Add form */}
      <form onSubmit={handleAdd} className="panel p-4">
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <label className="text-[9px] text-terminal-dim tracking-widest uppercase block mb-1">Symbol</label>
            <input
              name="symbol"
              required
              placeholder="AAPL"
              className="w-full bg-terminal-bg border border-terminal-border text-terminal-text text-sm font-mono px-3 py-2 rounded-sm focus:border-terminal-green/50 focus:outline-none"
            />
          </div>
          <div>
            <label className="text-[9px] text-terminal-dim tracking-widest uppercase block mb-1">Class</label>
            <select
              name="asset_class"
              className="bg-terminal-bg border border-terminal-border text-terminal-text text-sm font-mono px-3 py-2 rounded-sm"
            >
              <option value="stock">Stock</option>
              <option value="crypto">Crypto</option>
              <option value="commodity">Commodity</option>
            </select>
          </div>
          <div className="flex-1">
            <label className="text-[9px] text-terminal-dim tracking-widest uppercase block mb-1">Notes</label>
            <input
              name="notes"
              placeholder="Thesis, catalyst..."
              className="w-full bg-terminal-bg border border-terminal-border text-terminal-text text-sm font-mono px-3 py-2 rounded-sm focus:border-terminal-green/50 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            className="px-5 py-2 bg-terminal-green/10 border border-terminal-green/30 text-terminal-green text-[10px] tracking-widest uppercase hover:bg-terminal-green/20 transition-colors rounded-sm"
          >
            + ADD
          </button>
        </div>
      </form>

      {/* Watchlist items */}
      {items.length === 0 ? (
        <div className="panel p-8 text-center">
          <div className="text-terminal-dim text-sm">
            Watchlist empty. Add assets above or find candidates in the screener.
          </div>
        </div>
      ) : (
        <div className="panel overflow-hidden">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                <th className="text-left py-3 px-4 font-normal">Symbol</th>
                <th className="text-left py-3 px-2 font-normal">Class</th>
                <th className="text-right py-3 px-2 font-normal">Price</th>
                <th className="text-right py-3 px-2 font-normal">Tech Score</th>
                <th className="text-center py-3 px-2 font-normal">Signal</th>
                <th className="text-right py-3 px-2 font-normal">Composite</th>
                <th className="text-left py-3 px-2 font-normal">Notes</th>
                <th className="text-left py-3 px-2 font-normal">Added</th>
                <th className="py-3 px-4 font-normal"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr
                  key={item.symbol}
                  className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors"
                >
                  <td className="py-3 px-4">
                    <a
                      href={`/asset/${item.symbol}`}
                      className="font-mono font-bold text-terminal-bright hover:text-terminal-green transition-colors"
                    >
                      {item.symbol}
                    </a>
                  </td>
                  <td className="py-3 px-2 text-terminal-dim">{item.asset_class}</td>
                  <td className="py-3 px-2 text-right font-mono text-terminal-text">
                    {item.price ? `$${item.price.toFixed(2)}` : '—'}
                  </td>
                  <td className="py-3 px-2 text-right font-mono" style={{
                    color: (item.tech_score || 0) > 70 ? '#00FF41' : (item.tech_score || 0) > 40 ? '#FFB800' : '#FF073A'
                  }}>
                    {item.tech_score?.toFixed(1) || '—'}
                  </td>
                  <td className="py-3 px-2 text-center">
                    {item.signal ? <SignalBadge signal={item.signal} size="sm" /> : '—'}
                  </td>
                  <td className="py-3 px-2 text-right font-mono text-terminal-text">
                    {item.composite?.toFixed(1) || '—'}
                  </td>
                  <td className="py-3 px-2 text-terminal-dim max-w-[200px] truncate">
                    {item.notes || '—'}
                  </td>
                  <td className="py-3 px-2 text-terminal-dim">{item.added_date}</td>
                  <td className="py-3 px-4">
                    <button
                      onClick={() => handleRemove(item.symbol)}
                      className="text-terminal-dim hover:text-terminal-red transition-colors text-[10px]"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
