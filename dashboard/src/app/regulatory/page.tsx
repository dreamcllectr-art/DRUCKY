'use client';

import { useEffect, useState } from 'react';
import { api, RegulatorySignal, RegulatoryEvent, RegulatoryCategory, RegulatorySource, RegulatoryJurisdiction } from '@/lib/api';

const TABS = ['Signals', 'Events', 'Categories', 'Sources', 'Global'] as const;
type Tab = (typeof TABS)[number];

const JURISDICTION_LABELS: Record<string, string> = {
  US: 'United States',
  EU: 'European Union',
  UK: 'United Kingdom',
  CN: 'China',
  JP: 'Japan',
  KR: 'South Korea',
  SG: 'Singapore',
  CA: 'Canada',
  GLOBAL: 'Multilateral',
};

const JURISDICTION_FLAGS: Record<string, string> = {
  US: 'US', EU: 'EU', UK: 'UK', CN: 'CN', JP: 'JP',
  KR: 'KR', SG: 'SG', CA: 'CA', GLOBAL: 'G7',
};

function severityColor(s: number): string {
  if (s >= 4) return 'text-red-400';
  if (s >= 3) return 'text-amber-400';
  if (s >= 2) return 'text-cyan-400';
  return 'text-gray-400';
}

function severityBg(s: number): string {
  if (s >= 4) return 'bg-red-500/20 border-red-500/40';
  if (s >= 3) return 'bg-amber-500/20 border-amber-500/40';
  if (s >= 2) return 'bg-cyan-500/20 border-cyan-500/40';
  return 'bg-gray-500/20 border-gray-500/40';
}

function scoreColor(score: number): string {
  if (score >= 60) return 'text-green-400';
  if (score >= 40) return 'text-amber-400';
  return 'text-red-400';
}

function directionBadge(dir: string | null): JSX.Element | null {
  if (!dir) return null;
  const colors: Record<string, string> = {
    headwind: 'bg-red-500/20 text-red-400 border-red-500/40',
    tailwind: 'bg-green-500/20 text-green-400 border-green-500/40',
    mixed: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
  };
  return (
    <span className={`px-2 py-0.5 text-xs border rounded ${colors[dir] || colors.mixed}`}>
      {dir}
    </span>
  );
}

function jurisdictionBadge(jur: string | null): JSX.Element {
  const j = jur || 'US';
  const label = JURISDICTION_FLAGS[j] || j;
  const colors: Record<string, string> = {
    US: 'bg-blue-500/20 text-blue-400 border-blue-500/40',
    EU: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/40',
    UK: 'bg-sky-500/20 text-sky-400 border-sky-500/40',
    CN: 'bg-red-500/20 text-red-400 border-red-500/40',
    JP: 'bg-pink-500/20 text-pink-400 border-pink-500/40',
    KR: 'bg-violet-500/20 text-violet-400 border-violet-500/40',
    SG: 'bg-teal-500/20 text-teal-400 border-teal-500/40',
    CA: 'bg-rose-500/20 text-rose-400 border-rose-500/40',
    GLOBAL: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
  };
  return (
    <span className={`px-1.5 py-0.5 text-[10px] font-mono border rounded ${colors[j] || 'bg-gray-500/20 text-gray-400 border-gray-500/40'}`}>
      {label}
    </span>
  );
}

export default function RegulatoryPage() {
  const [tab, setTab] = useState<Tab>('Signals');
  const [signals, setSignals] = useState<RegulatorySignal[]>([]);
  const [events, setEvents] = useState<RegulatoryEvent[]>([]);
  const [categories, setCategories] = useState<RegulatoryCategory[]>([]);
  const [sources, setSources] = useState<RegulatorySource[]>([]);
  const [jurisdictions, setJurisdictions] = useState<RegulatoryJurisdiction[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [filterSource, setFilterSource] = useState<string | undefined>();
  const [filterCategory, setFilterCategory] = useState<string | undefined>();
  const [filterJurisdiction, setFilterJurisdiction] = useState<string | undefined>();
  const [expandedEvent, setExpandedEvent] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.regulatorySignals(0, 14),
      api.regulatoryEvents(filterSource, filterCategory, filterJurisdiction, 1, 14),
      api.regulatoryCategories(),
      api.regulatorySources(),
      api.regulatoryJurisdictions(),
    ]).then(([s, e, c, so, j]) => {
      setSignals(s);
      setEvents(e);
      setCategories(c);
      setSources(so);
      setJurisdictions(j);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [filterSource, filterCategory, filterJurisdiction]);

  const headwindCount = signals.filter(s => s.reg_score < 45).length;
  const tailwindCount = signals.filter(s => s.reg_score > 55).length;
  const highSeverityCount = events.filter(e => e.severity >= 4).length;
  const uniqueJurisdictions = new Set(events.map(e => e.jurisdiction || 'US'));

  const hasFilter = filterSource || filterCategory || filterJurisdiction;

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-gray-100 p-6 font-mono">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-green-400 tracking-wider">
          AI REGULATORY INTELLIGENCE
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Global AI regulation tracking — 13+ sources across 9 jurisdictions, 16 impact categories
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">Headwinds</div>
          <div className="text-2xl font-bold text-red-400">{headwindCount}</div>
        </div>
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">Tailwinds</div>
          <div className="text-2xl font-bold text-green-400">{tailwindCount}</div>
        </div>
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">High Severity</div>
          <div className="text-2xl font-bold text-amber-400">{highSeverityCount}</div>
        </div>
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">Categories</div>
          <div className="text-2xl font-bold text-cyan-400">{categories.length}</div>
        </div>
        <div className="bg-[#111] border border-gray-800 rounded-lg p-3">
          <div className="text-xs text-gray-500 uppercase">Jurisdictions</div>
          <div className="text-2xl font-bold text-indigo-400">{uniqueJurisdictions.size}</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-gray-800 pb-2">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm rounded-t transition-colors ${
              tab === t
                ? 'bg-green-500/20 text-green-400 border-b-2 border-green-400'
                : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Active Filter Bar */}
      {hasFilter && (
        <div className="flex items-center gap-2 mb-4 p-2 bg-[#111] border border-gray-800 rounded">
          <span className="text-xs text-gray-500">FILTERS:</span>
          {filterJurisdiction && (
            <span className="px-2 py-0.5 text-xs bg-indigo-500/20 text-indigo-400 border border-indigo-500/40 rounded">
              {JURISDICTION_LABELS[filterJurisdiction] || filterJurisdiction}
            </span>
          )}
          {filterSource && (
            <span className="px-2 py-0.5 text-xs bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 rounded">
              {filterSource}
            </span>
          )}
          {filterCategory && (
            <span className="px-2 py-0.5 text-xs bg-amber-500/20 text-amber-400 border border-amber-500/40 rounded">
              {filterCategory}
            </span>
          )}
          <button
            onClick={() => { setFilterSource(undefined); setFilterCategory(undefined); setFilterJurisdiction(undefined); }}
            className="ml-auto text-xs text-red-400 hover:text-red-300"
          >
            Clear All
          </button>
        </div>
      )}

      {loading ? (
        <div className="text-center py-20 text-gray-500">Loading global regulatory intelligence...</div>
      ) : (
        <>
          {/* SIGNALS TAB */}
          {tab === 'Signals' && (
            <div className="space-y-1">
              <div className="grid grid-cols-[1fr_80px_80px_60px_1fr] gap-2 px-3 py-2 text-xs text-gray-500 uppercase border-b border-gray-800">
                <span>Symbol</span>
                <span className="text-right">Score</span>
                <span className="text-right">Events</span>
                <span className="text-right">Impact</span>
                <span>Narrative</span>
              </div>
              {signals.length === 0 ? (
                <div className="text-center py-10 text-gray-600">No regulatory signals in the last 14 days</div>
              ) : (
                signals
                  .sort((a, b) => Math.abs(b.reg_score - 50) - Math.abs(a.reg_score - 50))
                  .slice(0, 100)
                  .map(s => (
                    <div key={`${s.symbol}-${s.date}`} className="grid grid-cols-[1fr_80px_80px_60px_1fr] gap-2 px-3 py-2 border-b border-gray-800/50 hover:bg-gray-800/30 text-sm">
                      <a href={`/asset/${s.symbol}`} className="font-bold text-white hover:text-green-400">{s.symbol}</a>
                      <span className={`text-right font-mono ${scoreColor(s.reg_score)}`}>
                        {s.reg_score.toFixed(1)}
                      </span>
                      <span className="text-right text-gray-400">{s.event_count}</span>
                      <span className={`text-right ${s.net_impact >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {s.net_impact >= 0 ? '+' : ''}{s.net_impact.toFixed(2)}
                      </span>
                      <span className="text-gray-400 text-xs truncate">{s.narrative}</span>
                    </div>
                  ))
              )}
            </div>
          )}

          {/* EVENTS TAB */}
          {tab === 'Events' && (
            <div className="space-y-1">
              {/* Jurisdiction filter pills */}
              <div className="flex flex-wrap gap-1.5 mb-3">
                <button
                  onClick={() => setFilterJurisdiction(undefined)}
                  className={`px-2.5 py-1 text-xs rounded border transition-colors ${
                    !filterJurisdiction ? 'bg-green-500/20 text-green-400 border-green-500/40' : 'text-gray-500 border-gray-700 hover:border-gray-500'
                  }`}
                >
                  All
                </button>
                {Object.entries(JURISDICTION_LABELS).map(([code, label]) => (
                  <button
                    key={code}
                    onClick={() => setFilterJurisdiction(filterJurisdiction === code ? undefined : code)}
                    className={`px-2.5 py-1 text-xs rounded border transition-colors ${
                      filterJurisdiction === code
                        ? 'bg-indigo-500/20 text-indigo-400 border-indigo-500/40'
                        : 'text-gray-500 border-gray-700 hover:border-gray-500'
                    }`}
                  >
                    {JURISDICTION_FLAGS[code]} {label}
                  </button>
                ))}
              </div>

              <div className="grid grid-cols-[40px_50px_1fr_120px_80px_80px] gap-2 px-3 py-2 text-xs text-gray-500 uppercase border-b border-gray-800">
                <span>Sev</span>
                <span>Jur</span>
                <span>Title</span>
                <span>Category</span>
                <span>Stage</span>
                <span>Dir</span>
              </div>
              {events.length === 0 ? (
                <div className="text-center py-10 text-gray-600">No regulatory events match filters</div>
              ) : (
                events.map(ev => {
                  const isExpanded = expandedEvent === ev.event_id;
                  let symbols: string[] = [];
                  try { symbols = JSON.parse(ev.specific_symbols || '[]'); } catch { /* */ }

                  return (
                    <div key={ev.event_id}>
                      <div
                        onClick={() => setExpandedEvent(isExpanded ? null : ev.event_id)}
                        className="grid grid-cols-[40px_50px_1fr_120px_80px_80px] gap-2 px-3 py-2 border-b border-gray-800/50 hover:bg-gray-800/30 text-sm cursor-pointer"
                      >
                        <span className={`font-bold ${severityColor(ev.severity)}`}>{ev.severity}</span>
                        {jurisdictionBadge(ev.jurisdiction)}
                        <div className="truncate">
                          <span className="text-white">{ev.title}</span>
                          {!isExpanded && ev.rationale && (
                            <span className="text-gray-500 text-xs ml-2">{ev.rationale}</span>
                          )}
                        </div>
                        <button
                          onClick={(e) => { e.stopPropagation(); setFilterCategory(ev.impact_category || undefined); setTab('Events'); }}
                          className="text-xs text-cyan-400 hover:text-cyan-300 truncate text-left"
                        >
                          {ev.impact_category?.replace('ai_', '')}
                        </button>
                        <span className="text-xs text-gray-400">{ev.stage}</span>
                        {directionBadge(ev.direction)}
                      </div>

                      {/* Expanded detail row */}
                      {isExpanded && (
                        <div className="px-6 py-3 bg-[#0d0d0d] border-b border-gray-800 space-y-2">
                          {ev.rationale && (
                            <p className="text-sm text-amber-400/90 italic">{ev.rationale}</p>
                          )}
                          {ev.abstract && (
                            <p className="text-sm text-gray-300 leading-relaxed">{ev.abstract}</p>
                          )}
                          <div className="flex flex-wrap gap-3 text-xs">
                            <span className="text-gray-500">Source: <span className="text-gray-300">{ev.source?.replace(/_/g, ' ')}</span></span>
                            <span className="text-gray-500">Agency: <span className="text-gray-300">{ev.agencies}</span></span>
                            <span className="text-gray-500">Date: <span className="text-gray-300">{ev.event_date}</span></span>
                            <span className="text-gray-500">Timeline: <span className="text-gray-300">{ev.timeline?.replace(/_/g, ' ')}</span></span>
                            <span className="text-gray-500">Jurisdiction: <span className="text-gray-300">{JURISDICTION_LABELS[ev.jurisdiction || 'US'] || ev.jurisdiction}</span></span>
                          </div>
                          {symbols.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              <span className="text-xs text-gray-500 mr-1">Affected tickers:</span>
                              {symbols.map(sym => (
                                <a
                                  key={sym}
                                  href={`/asset/${sym}`}
                                  className="px-1.5 py-0.5 text-[10px] bg-green-500/10 text-green-400 border border-green-500/30 rounded hover:bg-green-500/20"
                                >
                                  {sym}
                                </a>
                              ))}
                            </div>
                          )}
                          {ev.url && (
                            <a
                              href={ev.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-400 hover:underline inline-block mt-1"
                            >
                              View source document &rarr;
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}

          {/* CATEGORIES TAB */}
          {tab === 'Categories' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {categories.map(cat => {
                const dirs = (cat.directions || '').split(',');
                const isHeadwind = dirs.includes('headwind') && !dirs.includes('tailwind');
                const isTailwind = dirs.includes('tailwind') && !dirs.includes('headwind');
                return (
                  <div
                    key={cat.impact_category}
                    onClick={() => { setFilterCategory(cat.impact_category); setTab('Events'); }}
                    className={`p-4 rounded-lg border cursor-pointer hover:bg-gray-800/30 transition-colors ${severityBg(cat.avg_severity)}`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <h3 className="text-sm font-bold text-white">
                        {cat.impact_category?.replace('ai_', '').replace(/_/g, ' ').toUpperCase()}
                      </h3>
                      {isHeadwind && directionBadge('headwind')}
                      {isTailwind && directionBadge('tailwind')}
                      {!isHeadwind && !isTailwind && directionBadge('mixed')}
                    </div>
                    <div className="flex gap-4 text-xs text-gray-400">
                      <span>{cat.event_count} events</span>
                      <span className={severityColor(cat.avg_severity)}>
                        avg sev {cat.avg_severity.toFixed(1)}
                      </span>
                      <span>{cat.source_count} sources</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* SOURCES TAB */}
          {tab === 'Sources' && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {sources.map(src => (
                <div
                  key={src.source}
                  onClick={() => { setFilterSource(src.source); setTab('Events'); }}
                  className="p-4 rounded-lg border border-gray-800 bg-[#111] cursor-pointer hover:bg-gray-800/30 transition-colors"
                >
                  <div className="flex justify-between items-start mb-2">
                    <h3 className="text-sm font-bold text-white">{src.source.replace(/_/g, ' ').toUpperCase()}</h3>
                    {jurisdictionBadge(src.jurisdiction)}
                  </div>
                  <div className="flex gap-4 text-xs text-gray-400">
                    <span>{src.event_count} events</span>
                    <span className={severityColor(src.avg_severity)}>
                      avg sev {src.avg_severity.toFixed(1)}
                    </span>
                  </div>
                  {src.categories && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {src.categories.split(',').slice(0, 4).map(cat => (
                        <span key={cat} className="px-1.5 py-0.5 text-[10px] bg-gray-800 text-gray-400 rounded">
                          {cat.replace('ai_', '')}
                        </span>
                      ))}
                    </div>
                  )}
                  {src.latest_event && (
                    <div className="text-xs text-gray-600 mt-2">Latest: {src.latest_event}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* GLOBAL TAB */}
          {tab === 'Global' && (
            <div className="space-y-4">
              <p className="text-xs text-gray-500 mb-4">
                Jurisdiction breakdown of AI regulatory activity — click any region to filter events
              </p>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {jurisdictions.map(j => {
                  const total = j.headwinds + j.tailwinds + j.mixed;
                  const headwindPct = total > 0 ? (j.headwinds / total * 100) : 0;
                  const tailwindPct = total > 0 ? (j.tailwinds / total * 100) : 0;

                  return (
                    <div
                      key={j.jurisdiction}
                      onClick={() => { setFilterJurisdiction(j.jurisdiction); setTab('Events'); }}
                      className="p-4 rounded-lg border border-gray-800 bg-[#111] cursor-pointer hover:bg-gray-800/30 transition-colors"
                    >
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <h3 className="text-base font-bold text-white">
                            {JURISDICTION_LABELS[j.jurisdiction] || j.jurisdiction}
                          </h3>
                          <span className="text-xs text-gray-500">{j.event_count} events classified</span>
                        </div>
                        {jurisdictionBadge(j.jurisdiction)}
                      </div>

                      {/* Severity bar */}
                      <div className="mb-3">
                        <div className="flex justify-between text-xs text-gray-500 mb-1">
                          <span>Avg Severity</span>
                          <span className={severityColor(j.avg_severity)}>{j.avg_severity.toFixed(1)}/5</span>
                        </div>
                        <div className="w-full bg-gray-800 rounded-full h-1.5">
                          <div
                            className={`h-1.5 rounded-full ${j.avg_severity >= 3.5 ? 'bg-red-500' : j.avg_severity >= 2.5 ? 'bg-amber-500' : 'bg-cyan-500'}`}
                            style={{ width: `${(j.avg_severity / 5) * 100}%` }}
                          />
                        </div>
                      </div>

                      {/* Headwind/Tailwind split */}
                      <div className="flex gap-2 mb-2">
                        <div className="flex-1">
                          <div className="text-xs text-red-400 mb-0.5">{j.headwinds} headwinds ({headwindPct.toFixed(0)}%)</div>
                          <div className="w-full bg-gray-800 rounded-full h-1">
                            <div className="h-1 rounded-full bg-red-500" style={{ width: `${headwindPct}%` }} />
                          </div>
                        </div>
                        <div className="flex-1">
                          <div className="text-xs text-green-400 mb-0.5">{j.tailwinds} tailwinds ({tailwindPct.toFixed(0)}%)</div>
                          <div className="w-full bg-gray-800 rounded-full h-1">
                            <div className="h-1 rounded-full bg-green-500" style={{ width: `${tailwindPct}%` }} />
                          </div>
                        </div>
                      </div>

                      {/* Sources */}
                      {j.sources && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {j.sources.split(',').map(s => (
                            <span key={s} className="px-1.5 py-0.5 text-[10px] bg-gray-800 text-gray-500 rounded">
                              {s.replace(/_/g, ' ')}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {jurisdictions.length === 0 && (
                <div className="text-center py-10 text-gray-600">No jurisdiction data — run the pipeline first</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
