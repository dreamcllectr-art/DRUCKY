'use client';
import { useEffect, useState } from 'react';
import { api, type WatchlistItem } from '@/lib/api';
import SignalBadge from '@/components/SignalBadge';

export default function WatchlistTab() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = () => { api.watchlist().then(d => { setItems(d); }).catch((e) => setError(e.message || 'Failed to load watchlist')).finally(() => setLoading(false)); };
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
    form.reset(); loadData();
  };

  const handleRemove = async (symbol: string) => { await fetch(`/api/watchlist/${symbol}`, { method: 'DELETE' }); loadData(); };

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading watchlist...</div>;

  return (
    <div className="space-y-4">
      {error && (
        <div className="panel p-4 border-rose-200 bg-rose-50">
          <div className="text-rose-600 text-sm font-bold mb-1">Failed to load data</div>
          <p className="text-[11px] text-gray-500">{error}</p>
        </div>
      )}
      <form onSubmit={handleAdd} className="panel p-4"><div className="flex gap-3 items-end">
        <div className="flex-1"><label className="text-[10px] text-gray-500 tracking-widest uppercase block mb-1">Symbol</label><input name="symbol" required placeholder="AAPL" className="w-full bg-gray-50 border border-gray-200 text-gray-700 text-sm font-mono px-3 py-2 rounded-lg focus:border-emerald-600/50 focus:outline-none" /></div>
        <div><label className="text-[10px] text-gray-500 tracking-widest uppercase block mb-1">Class</label><select name="asset_class" className="bg-gray-50 border border-gray-200 text-gray-700 text-sm font-mono px-3 py-2 rounded-lg"><option value="stock">Stock</option><option value="crypto">Crypto</option></select></div>
        <div className="flex-1"><label className="text-[10px] text-gray-500 tracking-widest uppercase block mb-1">Notes</label><input name="notes" placeholder="Thesis..." className="w-full bg-gray-50 border border-gray-200 text-gray-700 text-sm font-mono px-3 py-2 rounded-lg focus:border-emerald-600/50 focus:outline-none" /></div>
        <button type="submit" className="px-5 py-2 bg-emerald-600/10 border border-emerald-600/30 text-emerald-600 text-[10px] tracking-widest uppercase hover:bg-emerald-600/20 transition-colors rounded-lg">+ ADD</button>
      </div></form>
      {items.length === 0 ? <div className="panel p-8 text-center text-gray-500 text-sm">Watchlist empty.</div> : (
        <div className="panel overflow-hidden"><table className="w-full text-[11px]"><thead><tr className="border-b border-gray-200 text-gray-500 tracking-widest uppercase"><th className="text-left py-3 px-4 font-normal">Symbol</th><th className="text-right py-3 px-2 font-normal">Price</th><th className="text-center py-3 px-2 font-normal">Signal</th><th className="text-right py-3 px-2 font-normal">Composite</th><th className="text-left py-3 px-2 font-normal">Notes</th><th className="py-3 px-4 font-normal"></th></tr></thead>
          <tbody>{items.map(item => (
            <tr key={item.symbol} className="border-b border-gray-200/50 hover:bg-emerald-600/[0.03]">
              <td className="py-3 px-4"><a href={`/asset/${item.symbol}`} className="font-mono font-bold text-gray-900 hover:text-emerald-600">{item.symbol}</a></td>
              <td className="py-3 px-2 text-right font-mono text-gray-700">{item.price ? `$${item.price.toFixed(2)}` : '--'}</td>
              <td className="py-3 px-2 text-center">{item.signal ? <SignalBadge signal={item.signal} size="sm" /> : '--'}</td>
              <td className="py-3 px-2 text-right font-mono text-gray-700">{item.composite?.toFixed(1) || '--'}</td>
              <td className="py-3 px-2 text-gray-500 max-w-[200px] truncate">{item.notes || '--'}</td>
              <td className="py-3 px-4"><button onClick={() => handleRemove(item.symbol)} className="text-gray-500 hover:text-rose-600 transition-colors text-[10px]">X</button></td>
            </tr>))}</tbody></table></div>
      )}
    </div>
  );
}
