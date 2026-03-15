'use client';
import { Fragment, useEffect, useState } from 'react';
import { api, type ThematicIdea, type ThemeSummary } from '@/lib/api';

const THEME_META: Record<string, { label: string; color: string }> = {
  ai_infrastructure: { label: 'AI INFRA', color: 'text-blue-400' },
  energy_buildout: { label: 'ENERGY', color: 'text-amber-400' },
  fintech_stablecoins: { label: 'FINTECH', color: 'text-emerald-400' },
  defense_tech: { label: 'DEFENSE', color: 'text-red-400' },
  reshoring_chips: { label: 'RESHORING', color: 'text-purple-400' },
};

const scoreColor = (s: number) => s >= 70 ? 'text-emerald-600' : s >= 55 ? 'text-amber-600' : 'text-gray-500';

export default function TradingIdeasTab() {
  const [ideas, setIdeas] = useState<ThematicIdea[]>([]);
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [topIdeas, setTopIdeas] = useState<ThematicIdea[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.tradingIdeasThemes().catch(() => []), api.tradingIdeasTop(20).catch(() => [])]).then(([t, top]) => { setThemes(t); setTopIdeas(top); setLoading(false); });
  }, []);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading ideas...</div>;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-5 gap-3">
        {Object.entries(THEME_META).map(([key, meta]) => {
          const theme = themes.find(t => t.theme === key);
          return (
            <div key={key} className="panel px-4 py-3">
              <span className={`text-[10px] tracking-widest ${meta.color}`}>{meta.label}</span>
              {theme ? <><div className="text-xl font-display font-bold text-emerald-600">{theme.strong_ideas}</div><div className="text-[9px] text-gray-500">/ {theme.num_stocks} total</div></> : <div className="text-gray-500 text-xs">No data</div>}
            </div>
          );
        })}
      </div>
      {topIdeas.length === 0 ? <div className="panel p-8 text-center text-gray-500">No ideas. Run the scanner first.</div> : (
        <div className="panel overflow-hidden"><table className="w-full text-xs"><thead><tr className="border-b border-gray-200 text-[9px] tracking-widest text-gray-500"><th className="text-left px-4 py-3">#</th><th className="text-left px-3 py-3">SYMBOL</th><th className="text-left px-3 py-3">THEME</th><th className="text-right px-3 py-3">SCORE</th><th className="text-right px-3 py-3">POLICY</th><th className="text-right px-3 py-3">GROWTH</th><th className="text-right px-3 py-3">TECH</th><th className="text-right px-3 py-3">MCAP</th></tr></thead>
          <tbody>{topIdeas.map((idea, idx) => {
            const meta = THEME_META[idea.theme] || { label: idea.theme, color: 'text-gray-500' };
            return (
              <tr key={`${idea.symbol}-${idea.theme}`} className="border-b border-gray-200/50 hover:bg-white/[0.02] cursor-pointer" onClick={() => (window.location.href = `/asset/${idea.symbol}`)}>
                <td className="px-4 py-2.5 text-gray-500">{idx + 1}</td>
                <td className="px-3 py-2.5 font-mono font-bold text-gray-900">{idea.symbol}</td>
                <td className={`px-3 py-2.5 ${meta.color} text-[10px] tracking-wider`}>{meta.label}</td>
                <td className={`px-3 py-2.5 text-right font-mono font-bold ${scoreColor(idea.composite_score)}`}>{idea.composite_score.toFixed(1)}</td>
                <td className={`px-3 py-2.5 text-right font-mono ${scoreColor(idea.policy_score)}`}>{idea.policy_score.toFixed(0)}</td>
                <td className={`px-3 py-2.5 text-right font-mono ${scoreColor(idea.growth_score)}`}>{idea.growth_score.toFixed(0)}</td>
                <td className={`px-3 py-2.5 text-right font-mono ${scoreColor(idea.technical_score)}`}>{idea.technical_score.toFixed(0)}</td>
                <td className="px-3 py-2.5 text-right font-mono text-gray-500">{idea.market_cap >= 1e9 ? `$${(idea.market_cap / 1e9).toFixed(1)}B` : idea.market_cap >= 1e6 ? `$${(idea.market_cap / 1e6).toFixed(0)}M` : 'N/A'}</td>
              </tr>
            );
          })}</tbody></table></div>
      )}
    </div>
  );
}
