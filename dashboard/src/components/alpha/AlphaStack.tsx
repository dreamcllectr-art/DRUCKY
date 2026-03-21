'use client';

import { useState, useEffect } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── Types ────────────────────────────────────────────────────────────────────

interface InsiderSignal {
  score: number; cluster_buy: number; cluster_count: number;
  large_buys_count: number; total_buy_value_30d: number; total_sell_value_30d: number;
  unusual_volume_flag: number; top_buyer: string; narrative: string; date: string;
}
interface PatternSignal {
  score: number; wyckoff_phase: string; wyckoff_confidence: number;
  patterns_detected: string[]; momentum_score: number; compression_score: number;
  squeeze_active: number; hurst_exponent: number; vol_regime: string;
  rotation_score: number; date: string;
}
interface AltDataSignal { score: number; signals: Record<string, unknown>; date: string; }
interface OptionsSignal {
  score: number; iv_rank: number; iv_percentile: number; pc_signal: string;
  unusual_activity_count: number; unusual_direction_bias: string; dealer_regime: string;
  skew_direction: string; expected_move_pct: number; date: string;
}
interface SupplyChainSignal {
  score: number; rail_score: number; shipping_score: number; trucking_score: number; date: string;
}
interface MASignal {
  score: number; deal_stage: string; rumor_credibility: number; acquirer_name: string;
  expected_premium_pct: number; best_headline: string; narrative: string; date: string;
}
interface PairSignal {
  symbol_a: string; symbol_b: string; direction: string; spread_zscore: number;
  score: number; narrative: string; date: string;
}
interface PredictionSignal { score: number; market_count: number; net_impact: number; status: string; narrative: string; }
interface DigitalExhaustSignal {
  score: number; app_score: number; github_score: number; pricing_score: number; domain_score: number; date: string;
}

interface AlphaEntry {
  symbol: string; name?: string; sector?: string; asset_class: string;
  last_gate_passed: number; is_fat_pitch: boolean;
  composite_score?: number; convergence_score?: number; signal?: string;
  signal_count: number;
  signals: {
    insider?: InsiderSignal; patterns?: PatternSignal; alt_data?: AltDataSignal;
    options?: OptionsSignal; supply_chain?: SupplyChainSignal; ma?: MASignal;
    pairs?: PairSignal[]; prediction_markets?: PredictionSignal;
    digital_exhaust?: DigitalExhaustSignal;
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function scoreColor(s?: number | null): string {
  if (s == null) return 'text-gray-300';
  if (s >= 70) return 'text-emerald-600';
  if (s >= 50) return 'text-amber-600';
  return 'text-rose-500';
}

function scoreBg(s?: number | null): string {
  if (s == null) return 'bg-gray-100 text-gray-400';
  if (s >= 70) return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
  if (s >= 50) return 'bg-amber-50 text-amber-700 border border-amber-200';
  return 'bg-rose-50 text-rose-600 border border-rose-200';
}

function fmt(v?: number | null, digits = 0): string {
  if (v == null) return '—';
  return v.toFixed(digits);
}

function fmtM(v?: number | null): string {
  if (v == null) return '—';
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

const SIGNAL_LABELS: Record<string, string> = {
  STRONG_BUY: 'STRONG BUY', BUY: 'BUY', NEUTRAL: 'NEUTRAL',
  SELL: 'SELL', STRONG_SELL: 'STRONG SELL',
};
const SIGNAL_COLOR: Record<string, string> = {
  STRONG_BUY: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  BUY: 'text-emerald-600 bg-emerald-50 border-emerald-200',
  NEUTRAL: 'text-gray-500 bg-gray-50 border-gray-200',
  SELL: 'text-rose-600 bg-rose-50 border-rose-200',
  STRONG_SELL: 'text-rose-700 bg-rose-50 border-rose-200',
};

// ─── Signal Modules ───────────────────────────────────────────────────────────

function ScoreChip({ label, score }: { label: string; score?: number | null }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</span>
      <span className={`text-[11px] font-bold font-mono px-1.5 py-0.5 rounded ${scoreBg(score)}`}>
        {fmt(score)}
      </span>
    </div>
  );
}

function ModuleCard({ title, score, children, accent = 'gray' }: {
  title: string; score?: number | null; children: React.ReactNode; accent?: string;
}) {
  const accents: Record<string, string> = {
    gray: 'border-l-gray-300',
    emerald: 'border-l-emerald-400',
    amber: 'border-l-amber-400',
    blue: 'border-l-blue-400',
    purple: 'border-l-purple-400',
    rose: 'border-l-rose-400',
    sky: 'border-l-sky-400',
    indigo: 'border-l-indigo-400',
    teal: 'border-l-teal-400',
  };
  return (
    <div className={`bg-white rounded-lg border border-gray-200 border-l-4 ${accents[accent] || accents.gray} p-3 shadow-sm`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[9px] font-bold tracking-widest text-gray-400 uppercase">{title}</span>
        {score != null && (
          <span className={`text-xs font-bold font-mono ${scoreColor(score)}`}>{fmt(score)}</span>
        )}
      </div>
      {children}
    </div>
  );
}

function InsiderModule({ data }: { data: InsiderSignal }) {
  const netFlow = (data.total_buy_value_30d || 0) - (data.total_sell_value_30d || 0);
  return (
    <ModuleCard title="Insider Trading" score={data.score} accent="emerald">
      <div className="space-y-1">
        <div className="flex gap-3 text-[10px]">
          <span className="text-emerald-600 font-mono font-semibold">+{fmtM(data.total_buy_value_30d)}</span>
          <span className="text-gray-400">/</span>
          <span className="text-rose-500 font-mono">-{fmtM(data.total_sell_value_30d)}</span>
          <span className={`ml-auto font-mono font-bold ${netFlow > 0 ? 'text-emerald-600' : 'text-rose-500'}`}>
            net {fmtM(netFlow)}
          </span>
        </div>
        {data.cluster_count > 0 && (
          <div className="text-[10px] text-gray-500">
            {data.cluster_count} insider{data.cluster_count > 1 ? 's' : ''} buying
            {data.unusual_volume_flag ? ' · unusual volume' : ''}
          </div>
        )}
        {data.top_buyer && <div className="text-[10px] text-gray-400 truncate">{data.top_buyer}</div>}
        {data.narrative && <p className="text-[10px] text-gray-500 mt-1 leading-relaxed">{data.narrative}</p>}
      </div>
    </ModuleCard>
  );
}

function PatternsModule({ data }: { data: PatternSignal }) {
  const raw = data.patterns_detected;
  const patterns: { pattern: string; direction: string; confidence: number; price_target?: number }[] =
    Array.isArray(raw) ? raw.map((p: unknown) =>
      typeof p === 'object' && p !== null ? p as { pattern: string; direction: string; confidence: number; price_target?: number } : { pattern: String(p), direction: '', confidence: 0 }
    ) : [];

  return (
    <ModuleCard title="Pattern Scanner" score={data.score} accent="blue">
      <div className="space-y-1.5">
        {data.wyckoff_phase && (
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-gray-400 uppercase tracking-wider">Wyckoff</span>
            <span className="text-[10px] font-semibold text-blue-600">{data.wyckoff_phase}</span>
            {data.wyckoff_confidence > 0 && (
              <span className="text-[9px] text-gray-400">{fmt(data.wyckoff_confidence)}% conf</span>
            )}
          </div>
        )}
        {patterns.length > 0 && (
          <div className="space-y-1">
            {patterns.slice(0, 4).map((p, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold ${
                  p.direction === 'bullish' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                  p.direction === 'bearish' ? 'bg-rose-50 text-rose-600 border-rose-200' :
                  'bg-blue-50 text-blue-600 border-blue-100'
                }`}>
                  {p.pattern.replace(/_/g, ' ')}
                </span>
                {p.confidence > 0 && (
                  <span className="text-[9px] text-gray-400">{fmt(p.confidence * 100)}% conf</span>
                )}
                {p.price_target != null && (
                  <span className="text-[9px] text-gray-500 ml-auto">tgt ${fmt(p.price_target, 2)}</span>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-3 text-[10px] text-gray-500">
          {data.vol_regime && <span>vol: <span className="text-gray-700">{data.vol_regime}</span></span>}
          {data.squeeze_active ? <span className="text-amber-600 font-semibold">squeeze active</span> : null}
          {data.hurst_exponent > 0 && <span>H={fmt(data.hurst_exponent, 2)}</span>}
        </div>
      </div>
    </ModuleCard>
  );
}

function OptionsModule({ data }: { data: OptionsSignal }) {
  return (
    <ModuleCard title="Options Flow" score={data.score} accent="purple">
      <div className="space-y-1">
        <div className="flex gap-4 text-[10px]">
          <span className="text-gray-500">IV Rank <span className="text-gray-800 font-semibold">{fmt(data.iv_rank)}%</span></span>
          <span className="text-gray-500">P/C <span className={`font-semibold ${data.pc_signal === 'bullish' ? 'text-emerald-600' : data.pc_signal === 'bearish' ? 'text-rose-500' : 'text-gray-700'}`}>{data.pc_signal || '—'}</span></span>
          {data.expected_move_pct != null && (
            <span className="text-gray-500">±<span className="text-gray-800">{fmt(data.expected_move_pct, 1)}%</span></span>
          )}
        </div>
        {data.unusual_activity_count > 0 && (
          <div className="text-[10px]">
            <span className="text-purple-600 font-semibold">{data.unusual_activity_count} unusual trades</span>
            {data.unusual_direction_bias && (
              <span className="text-gray-500"> · bias: {data.unusual_direction_bias}</span>
            )}
          </div>
        )}
        {data.dealer_regime && (
          <div className="text-[10px] text-gray-400">dealer: {data.dealer_regime}</div>
        )}
      </div>
    </ModuleCard>
  );
}

function AltDataModule({ data }: { data: AltDataSignal }) {
  // contributing_signals is a JSON array of "source:signal_name" strings
  const sigs: string[] = Array.isArray(data.signals) ? data.signals as string[] : [];

  return (
    <ModuleCard title="Alternative Data" score={data.score} accent="amber">
      {sigs.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {sigs.map((s, i) => {
            const [source, signal] = String(s).split(':');
            return (
              <div key={i} className="bg-amber-50 border border-amber-100 rounded px-2 py-1">
                <div className="text-[8px] text-amber-500 uppercase tracking-wider">{source?.replace(/_/g, ' ')}</div>
                <div className="text-[10px] font-semibold text-amber-800">{signal?.replace(/_/g, ' ') || String(s)}</div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-[10px] text-gray-400">Score {fmt(data.score)} — no active signals</p>
      )}
    </ModuleCard>
  );
}

function SupplyChainModule({ data }: { data: SupplyChainSignal }) {
  return (
    <ModuleCard title="Supply Chain" score={data.score} accent="teal">
      <div className="flex gap-4">
        <ScoreChip label="Rail" score={data.rail_score} />
        <ScoreChip label="Ship" score={data.shipping_score} />
        <ScoreChip label="Truck" score={data.trucking_score} />
      </div>
    </ModuleCard>
  );
}

function MAModule({ data }: { data: MASignal }) {
  return (
    <ModuleCard title="M&A Intelligence" score={data.score} accent="rose">
      <div className="space-y-1">
        {data.deal_stage && (
          <div className="flex items-center gap-2">
            <span className="text-[9px] bg-rose-50 text-rose-600 border border-rose-100 px-1.5 py-0.5 rounded font-semibold uppercase tracking-wide">
              {data.deal_stage}
            </span>
            {data.rumor_credibility > 0 && (
              <span className="text-[10px] text-gray-500">cred: {fmt(data.rumor_credibility)}%</span>
            )}
          </div>
        )}
        {data.acquirer_name && (
          <div className="text-[10px] text-gray-600">
            Acquirer: <span className="font-semibold">{data.acquirer_name}</span>
            {data.expected_premium_pct != null && (
              <span className="text-emerald-600 ml-2">+{fmt(data.expected_premium_pct)}% prem</span>
            )}
          </div>
        )}
        {data.best_headline && (
          <p className="text-[10px] text-gray-500 italic truncate">{data.best_headline}</p>
        )}
      </div>
    </ModuleCard>
  );
}

function PairsModule({ data }: { data: PairSignal[] }) {
  return (
    <ModuleCard title="Pairs / Stat Arb" accent="indigo">
      <div className="space-y-1.5">
        {data.map((p, i) => (
          <div key={i} className="text-[10px]">
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold text-gray-800">{p.symbol_a} / {p.symbol_b}</span>
              <span className={`px-1 py-0.5 rounded text-[9px] font-semibold ${
                p.direction === 'long_a' ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'
              }`}>{p.direction}</span>
              <span className="ml-auto text-gray-500 font-mono">z={fmt(p.spread_zscore, 2)}</span>
            </div>
            {p.narrative && <p className="text-[9px] text-gray-400 mt-0.5 truncate">{p.narrative}</p>}
          </div>
        ))}
      </div>
    </ModuleCard>
  );
}

function PredictionModule({ data }: { data: PredictionSignal }) {
  return (
    <ModuleCard title="Prediction Markets" score={data.score} accent="sky">
      <div className="space-y-1 text-[10px]">
        {data.market_count > 0 && (
          <span className="text-gray-500">{data.market_count} active market{data.market_count > 1 ? 's' : ''}</span>
        )}
        {data.net_impact != null && (
          <div className={`font-semibold ${data.net_impact > 0 ? 'text-emerald-600' : 'text-rose-500'}`}>
            Net impact: {data.net_impact > 0 ? '+' : ''}{fmt(data.net_impact, 1)}
          </div>
        )}
        {data.narrative && <p className="text-gray-500 leading-relaxed">{data.narrative}</p>}
      </div>
    </ModuleCard>
  );
}

function DigitalExhaustModule({ data }: { data: DigitalExhaustSignal }) {
  return (
    <ModuleCard title="Digital Exhaust" score={data.score} accent="amber">
      <div className="grid grid-cols-2 gap-x-4">
        <ScoreChip label="App" score={data.app_score} />
        <ScoreChip label="GitHub" score={data.github_score} />
        <ScoreChip label="Pricing" score={data.pricing_score} />
        <ScoreChip label="Domain" score={data.domain_score} />
      </div>
    </ModuleCard>
  );
}

// ─── Gate Badge ───────────────────────────────────────────────────────────────

const GATE_COLORS: Record<number, string> = {
  10: 'bg-emerald-600 text-white',
  9: 'bg-emerald-500 text-white',
  8: 'bg-teal-500 text-white',
  7: 'bg-sky-500 text-white',
  6: 'bg-blue-500 text-white',
  5: 'bg-indigo-400 text-white',
  4: 'bg-violet-400 text-white',
  3: 'bg-purple-400 text-white',
};

function GateBadge({ gate }: { gate: number }) {
  const cls = GATE_COLORS[gate] || 'bg-gray-200 text-gray-600';
  return (
    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${cls}`}>
      G{gate}
    </span>
  );
}

// ─── Signal Breadth Bar ───────────────────────────────────────────────────────

const SIG_SOURCES = ['insider', 'patterns', 'alt_data', 'options', 'supply_chain', 'ma', 'pairs', 'prediction_markets', 'digital_exhaust'] as const;
const SIG_LABELS: Record<string, string> = {
  insider: 'INS', patterns: 'PAT', alt_data: 'ALT', options: 'OPT',
  supply_chain: 'SUP', ma: 'M&A', pairs: 'PAI', prediction_markets: 'PM', digital_exhaust: 'DIG',
};

function SignalBreadthBar({ signals }: { signals: AlphaEntry['signals'] }) {
  return (
    <div className="flex gap-1 mt-1">
      {SIG_SOURCES.map(k => {
        const has = k === 'pairs' ? !!(signals.pairs && signals.pairs.length > 0) : !!signals[k];
        return (
          <span
            key={k}
            title={k.replace(/_/g, ' ')}
            className={`text-[8px] font-bold px-1 py-0.5 rounded ${
              has ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-300'
            }`}
          >
            {SIG_LABELS[k]}
          </span>
        );
      })}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function AlphaStack() {
  const [minGate, setMinGate] = useState(5);
  const [data, setData] = useState<AlphaEntry[]>([]);
  const [selected, setSelected] = useState<AlphaEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    setSelected(null);
    fetch(`${API}/api/alpha/stack?min_gate=${minGate}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [minGate]);

  // Auto-select first fat pitch or top result
  useEffect(() => {
    if (data.length > 0 && !selected) setSelected(data[0]);
  }, [data]);

  const totalSources = selected ? SIG_SOURCES.filter(k =>
    k === 'pairs' ? !!(selected.signals.pairs?.length) : !!selected.signals[k]
  ).length : 0;

  return (
    <div className="flex h-[calc(100vh-88px)] overflow-hidden bg-gray-50">

      {/* ── Left Panel: Ranked Stock List ── */}
      <div className="w-[260px] shrink-0 border-r border-gray-200 bg-white flex flex-col">

        {/* Gate filter */}
        <div className="px-4 pt-4 pb-3 border-b border-gray-100">
          <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-2">Conviction Filter</div>
          <div className="flex flex-col gap-1">
            {[
              { g: 4, label: 'Sector + Macro',    sub: 'regime + liquidity + forensics' },
              { g: 5, label: 'Trending',           sub: '+ technical momentum' },
              { g: 6, label: 'Fundamental',        sub: '+ earnings quality' },
              { g: 7, label: 'Smart Money',        sub: '+ institutional accumulation' },
              { g: 8, label: 'High Conviction',    sub: '+ convergence across signals' },
              { g: 9, label: 'Catalyst',           sub: '+ near-term catalyst' },
              { g: 10, label: 'Fat Pitch',         sub: 'all 10 gates — max conviction' },
            ].map(({ g, label, sub }) => (
              <button
                key={g}
                onClick={() => setMinGate(g)}
                className={`w-full text-left px-2.5 py-2 rounded-lg transition-colors ${
                  minGate === g
                    ? 'bg-blue-50 border border-blue-200'
                    : 'hover:bg-gray-50 border border-transparent'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`text-[9px] font-bold font-mono px-1.5 py-0.5 rounded ${
                    minGate === g ? (GATE_COLORS[g] || 'bg-gray-200 text-gray-600') : 'bg-gray-100 text-gray-500'
                  }`}>G{g}+</span>
                  <span className={`text-[11px] font-semibold ${minGate === g ? 'text-blue-700' : 'text-gray-700'}`}>
                    {label}
                  </span>
                </div>
                <div className="text-[9px] text-gray-400 mt-0.5 ml-7">{sub}</div>
              </button>
            ))}
          </div>
          <div className="text-[9px] text-gray-400 mt-2 px-1">
            {loading ? 'Loading...' : `${data.length} stocks`}
          </div>
        </div>

        {/* Stock list */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center h-32 text-[10px] text-gray-400">Loading...</div>
          ) : error ? (
            <div className="p-4 text-[10px] text-rose-500">{error}</div>
          ) : data.length === 0 ? (
            <div className="p-4 text-[10px] text-gray-400">No stocks passed Gate {minGate}+</div>
          ) : (
            data.map(entry => (
              <button
                key={entry.symbol}
                onClick={() => setSelected(entry)}
                className={`w-full text-left px-4 py-2.5 border-b border-gray-50 transition-colors ${
                  selected?.symbol === entry.symbol
                    ? 'bg-gray-50 border-l-2 border-l-emerald-500'
                    : 'hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold text-[12px] text-gray-900">{entry.symbol}</span>
                  {entry.is_fat_pitch && (
                    <span className="text-[8px] bg-emerald-100 text-emerald-700 px-1 py-0.5 rounded font-bold">FAT</span>
                  )}
                  <GateBadge gate={entry.last_gate_passed} />
                  <span className={`ml-auto text-[10px] font-mono font-bold ${scoreColor(entry.composite_score)}`}>
                    {fmt(entry.composite_score)}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[9px] text-gray-400 truncate flex-1">{entry.sector || entry.name || ''}</span>
                  <span className="text-[9px] text-gray-300 font-mono">{entry.signal_count}/9 src</span>
                </div>
                <SignalBreadthBar signals={entry.signals} />
              </button>
            ))
          )}
        </div>
      </div>

      {/* ── Right Panel: Signal Stack ── */}
      <div className="flex-1 overflow-y-auto">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-[11px] text-gray-400">
            Select a stock to see full signal stack
          </div>
        ) : (
          <div className="p-5 space-y-4 max-w-[900px]">

            {/* Header */}
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-2xl font-bold text-gray-900 font-mono">{selected.symbol}</h2>
                    {selected.is_fat_pitch && (
                      <span className="text-[10px] font-bold bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-1 rounded-full uppercase tracking-widest">
                        Fat Pitch
                      </span>
                    )}
                    <GateBadge gate={selected.last_gate_passed} />
                    {selected.signal && (
                      <span className={`text-[9px] font-bold border px-2 py-0.5 rounded uppercase tracking-wide ${SIGNAL_COLOR[selected.signal] || ''}`}>
                        {SIGNAL_LABELS[selected.signal] || selected.signal}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-500 mt-1">
                    {selected.name && <span>{selected.name} · </span>}
                    {selected.sector && <span>{selected.sector}</span>}
                  </p>
                </div>

                {/* Score cluster */}
                <div className="flex gap-4 text-right">
                  <div>
                    <div className="text-[9px] text-gray-400 tracking-widest uppercase">Composite</div>
                    <div className={`text-2xl font-bold font-mono ${scoreColor(selected.composite_score)}`}>
                      {fmt(selected.composite_score)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9px] text-gray-400 tracking-widest uppercase">Convergence</div>
                    <div className={`text-2xl font-bold font-mono ${scoreColor(selected.convergence_score)}`}>
                      {fmt(selected.convergence_score)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9px] text-gray-400 tracking-widest uppercase">Sources</div>
                    <div className={`text-2xl font-bold font-mono ${totalSources >= 5 ? 'text-emerald-600' : totalSources >= 3 ? 'text-amber-600' : 'text-gray-400'}`}>
                      {totalSources}/9
                    </div>
                  </div>
                </div>
              </div>

              {/* Full breadth bar */}
              <div className="mt-4 pt-4 border-t border-gray-100">
                <div className="text-[9px] text-gray-400 uppercase tracking-widest mb-2">Signal Breadth</div>
                <div className="flex gap-2 flex-wrap">
                  {SIG_SOURCES.map(k => {
                    const has = k === 'pairs'
                      ? !!(selected.signals.pairs?.length)
                      : !!selected.signals[k];
                    const score = k !== 'pairs' && selected.signals[k]
                      ? (selected.signals[k] as { score?: number })?.score
                      : undefined;
                    return (
                      <div key={k} className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-semibold ${
                        has ? 'bg-emerald-50 border border-emerald-200 text-emerald-700' : 'bg-gray-50 border border-gray-100 text-gray-300'
                      }`}>
                        <span className="uppercase tracking-wider">{k.replace(/_/g, ' ')}</span>
                        {has && score != null && (
                          <span className={`font-mono text-[9px] ${scoreColor(score)}`}>{fmt(score)}</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Signal modules grid */}
            <div className="grid grid-cols-2 gap-3">
              {selected.signals.insider && <InsiderModule data={selected.signals.insider} />}
              {selected.signals.patterns && <PatternsModule data={selected.signals.patterns} />}
              {selected.signals.options && <OptionsModule data={selected.signals.options} />}
              {selected.signals.alt_data && <AltDataModule data={selected.signals.alt_data} />}
              {selected.signals.supply_chain && <SupplyChainModule data={selected.signals.supply_chain} />}
              {selected.signals.ma && <MAModule data={selected.signals.ma} />}
              {selected.signals.pairs && selected.signals.pairs.length > 0 && <PairsModule data={selected.signals.pairs} />}
              {selected.signals.prediction_markets && <PredictionModule data={selected.signals.prediction_markets} />}
              {selected.signals.digital_exhaust && <DigitalExhaustModule data={selected.signals.digital_exhaust} />}
            </div>

            {/* Empty state */}
            {totalSources === 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-6 text-center">
                <div className="text-sm font-semibold text-amber-700 mb-1">No alternative signal data yet</div>
                <p className="text-[11px] text-amber-600">
                  Run the pipeline to populate insider, patterns, options, and alt data signals.
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
