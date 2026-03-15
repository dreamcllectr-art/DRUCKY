'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';

interface SearchResult {
  type: 'stock' | 'page';
  symbol?: string;
  label: string;
  sublabel?: string;
  href: string;
  score?: number;
  signal?: string;
}

const PAGES: SearchResult[] = [
  { type: 'page', label: 'Home', sublabel: 'Synthesis & top actions', href: '/' },
  { type: 'page', label: 'Macro Regime', sublabel: 'Market regime & indicators', href: '/macro' },
  { type: 'page', label: 'Trading Ideas', sublabel: 'Thematic alpha scanner', href: '/trading-ideas' },
  { type: 'page', label: 'Convergence', sublabel: 'Full convergence heatmap', href: '/synthesis' },
  { type: 'page', label: 'Fat Pitches', sublabel: 'Consensus blindspots', href: '/consensus-blindspots' },
  { type: 'page', label: 'Pairs Trading', sublabel: 'Runners & mean reversion', href: '/pairs' },
  { type: 'page', label: 'M&A Intelligence', sublabel: 'Acquisition targets', href: '/ma' },
  { type: 'page', label: 'Insider Activity', sublabel: 'SEC Form 4 cluster buys', href: '/insider' },
  { type: 'page', label: 'Patterns', sublabel: 'Technical patterns & options', href: '/patterns' },
  { type: 'page', label: 'Estimate Momentum', sublabel: 'EPS revision velocity', href: '/estimate-momentum' },
  { type: 'page', label: 'Predictions', sublabel: 'Polymarket signals', href: '/predictions' },
  { type: 'page', label: 'Regulatory', sublabel: 'AI regulatory intelligence', href: '/regulatory' },
  { type: 'page', label: 'Displacement', sublabel: 'News displacement signals', href: '/displacement' },
  { type: 'page', label: 'Economic', sublabel: 'FRED indicators & heat index', href: '/economic' },
  { type: 'page', label: 'Worldview', sublabel: 'Global macro theses', href: '/worldview' },
  { type: 'page', label: 'Portfolio', sublabel: 'Position P&L tracker', href: '/portfolio' },
  { type: 'page', label: 'Watchlist', sublabel: 'Custom watchlist', href: '/watchlist' },
  { type: 'page', label: 'Hyperliquid', sublabel: 'Weekend gap predictions', href: '/hyperliquid' },
  { type: 'page', label: 'Energy Intel', sublabel: 'Energy supply & demand', href: '/energy' },
  { type: 'page', label: 'Reports', sublabel: 'Intelligence reports', href: '/reports' },
];

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [stocks, setStocks] = useState<SearchResult[]>([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  // Load stock universe once
  useEffect(() => {
    fetch('/api/signals?limit=1000', { cache: 'no-store' })
      .then(r => r.ok ? r.json() : [])
      .then((signals: any[]) => {
        setStocks(
          signals.map(s => ({
            type: 'stock' as const,
            symbol: s.symbol,
            label: s.symbol,
            sublabel: s.asset_class || '',
            href: `/asset/${s.symbol}`,
            score: s.composite_score,
            signal: s.signal,
          }))
        );
      })
      .catch(() => {});
  }, []);

  // Keyboard shortcut: Cmd+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(prev => !prev);
        setQuery('');
        setSelectedIdx(0);
      }
      if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Filter results
  const results: SearchResult[] = (() => {
    if (!query.trim()) return PAGES.slice(0, 8);
    const q = query.toLowerCase();
    const matched: SearchResult[] = [];

    // Search stocks first (exact prefix match)
    stocks
      .filter(s => s.symbol?.toLowerCase().startsWith(q))
      .slice(0, 6)
      .forEach(s => matched.push(s));

    // Then fuzzy stock matches
    if (matched.length < 6) {
      stocks
        .filter(s =>
          !s.symbol?.toLowerCase().startsWith(q) &&
          (s.symbol?.toLowerCase().includes(q) || s.sublabel?.toLowerCase().includes(q))
        )
        .slice(0, 6 - matched.length)
        .forEach(s => matched.push(s));
    }

    // Pages
    PAGES
      .filter(p => p.label.toLowerCase().includes(q) || p.sublabel?.toLowerCase().includes(q))
      .slice(0, 4)
      .forEach(p => matched.push(p));

    return matched;
  })();

  const navigate = useCallback((href: string) => {
    setOpen(false);
    setQuery('');
    router.push(href);
  }, [router]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIdx(prev => Math.min(prev + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIdx(prev => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter' && results[selectedIdx]) {
      navigate(results[selectedIdx].href);
    }
  };

  // Reset selection when query changes
  useEffect(() => setSelectedIdx(0), [query]);

  if (!open) return null;

  const signalColor = (sig?: string) => {
    if (!sig) return '';
    if (sig.includes('STRONG BUY')) return 'text-emerald-600 glow-green';
    if (sig.includes('BUY')) return 'text-emerald-600';
    if (sig.includes('STRONG SELL')) return 'text-rose-600 glow-red';
    if (sig.includes('SELL')) return 'text-rose-600';
    return 'text-amber-600';
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={() => setOpen(false)}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      {/* Palette */}
      <div
        className="relative w-[520px] bg-white border border-gray-200 rounded-lg shadow-2xl overflow-hidden animate-fade-in"
        onClick={e => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-200">
          <span className="text-emerald-600 text-sm">⌘</span>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search stocks or pages..."
            className="flex-1 bg-transparent text-gray-700 text-sm font-mono outline-none placeholder:text-gray-500"
            autoComplete="off"
            spellCheck={false}
          />
          <span className="text-[9px] text-gray-500 px-1.5 py-0.5 border border-gray-200 rounded-lg">
            ESC
          </span>
        </div>

        {/* Results */}
        <div className="max-h-[360px] overflow-y-auto">
          {results.length === 0 && (
            <div className="px-4 py-6 text-center text-gray-500 text-[11px]">
              No results for &ldquo;{query}&rdquo;
            </div>
          )}
          {results.map((r, i) => (
            <button
              key={r.href + r.label}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                i === selectedIdx
                  ? 'bg-emerald-600/[0.08] text-emerald-600'
                  : 'text-gray-700 hover:bg-emerald-600/[0.03]'
              }`}
              onClick={() => navigate(r.href)}
              onMouseEnter={() => setSelectedIdx(i)}
            >
              {r.type === 'stock' ? (
                <>
                  <span className="text-[10px] text-gray-500 w-4">$</span>
                  <span className="font-mono font-bold text-[13px] w-16">{r.symbol}</span>
                  <span className="text-[10px] text-gray-500 flex-1 truncate">{r.sublabel}</span>
                  {r.signal && (
                    <span className={`text-[9px] font-bold ${signalColor(r.signal)}`}>
                      {r.signal}
                    </span>
                  )}
                  {r.score != null && (
                    <span className="text-[10px] font-mono text-gray-500 w-8 text-right">
                      {r.score.toFixed(0)}
                    </span>
                  )}
                </>
              ) : (
                <>
                  <span className="text-[10px] text-gray-500 w-4">→</span>
                  <span className="text-[12px] font-display font-bold">{r.label}</span>
                  <span className="text-[10px] text-gray-500 flex-1 truncate">{r.sublabel}</span>
                </>
              )}
            </button>
          ))}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-gray-200 flex gap-4 text-[8px] text-gray-500 tracking-wider">
          <span>↑↓ navigate</span>
          <span>↵ select</span>
          <span>esc close</span>
        </div>
      </div>
    </div>
  );
}
