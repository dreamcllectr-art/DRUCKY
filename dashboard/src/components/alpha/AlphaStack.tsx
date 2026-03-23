'use client';

import { useState, useEffect, useMemo } from 'react';
import { useStockPanel } from '@/contexts/StockPanelContext';
import { fmtM as _fmtM, fmt as _fmt, GATE_COLORS, scoreTextCls, fmtTopBuyer } from '@/lib/utils';
import { Tooltip, InfoTip } from '@/components/shared/Tooltip';
import { SIGNAL_MODULE_DEFS, GATE_DEFS } from '@/lib/definitions';

const API = '';

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

function scoreBg(s?: number | null): string {
  if (s == null) return 'bg-gray-100 text-gray-400';
  if (s >= 70) return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
  if (s >= 50) return 'bg-amber-50 text-amber-700 border border-amber-200';
  return 'bg-rose-50 text-rose-600 border border-rose-200';
}

const fmt = _fmt;
const fmtM = _fmtM;

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
        <span className="text-[10px] font-bold tracking-widest text-gray-400 uppercase">{title}</span>
        {score != null && (
          <span className={`text-xs font-bold font-mono ${scoreTextCls(score)}`}>{fmt(score)}</span>
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
        {data.top_buyer && <div className="text-[10px] text-gray-400 truncate">{fmtTopBuyer(data.top_buyer)}</div>}
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
            <span className="text-[10px] text-gray-400 uppercase tracking-wider">Wyckoff</span>
            <span className="text-[10px] font-semibold text-blue-600">{data.wyckoff_phase}</span>
            {data.wyckoff_confidence > 0 && (
              <span className="text-[10px] text-gray-400">{fmt(data.wyckoff_confidence)}% conf</span>
            )}
          </div>
        )}
        {patterns.length > 0 && (
          <div className="space-y-1">
            {patterns.slice(0, 4).map((p, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className={`text-[10px] px-1.5 py-0.5 rounded border font-semibold ${
                  p.direction === 'bullish' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                  p.direction === 'bearish' ? 'bg-rose-50 text-rose-600 border-rose-200' :
                  'bg-blue-50 text-blue-600 border-blue-100'
                }`}>
                  {p.pattern.replace(/_/g, ' ')}
                </span>
                {p.confidence > 0 && (
                  <span className="text-[10px] text-gray-400">{fmt(p.confidence * 100)}% conf</span>
                )}
                {p.price_target != null && (
                  <span className="text-[10px] text-gray-500 ml-auto">tgt ${fmt(p.price_target, 2)}</span>
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
                <div className="text-[10px] text-amber-500 uppercase tracking-wider">{source?.replace(/_/g, ' ')}</div>
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
            <span className="text-[10px] bg-rose-50 text-rose-600 border border-rose-100 px-1.5 py-0.5 rounded font-semibold uppercase tracking-wide">
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
              <span className={`px-1 py-0.5 rounded text-[10px] font-semibold ${
                p.direction === 'long_a' ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'
              }`}>{p.direction}</span>
              <span className="ml-auto text-gray-500 font-mono">z={fmt(p.spread_zscore, 2)}</span>
            </div>
            {p.narrative && <p className="text-[10px] text-gray-400 mt-0.5 truncate">{p.narrative}</p>}
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

// ─── Verdict Row ──────────────────────────────────────────────────────────────

type Verdict = 'BULLISH' | 'BEARISH' | 'WATCH' | 'NEUTRAL' | 'NO DATA';

function VerdictPill({ v }: { v: Verdict }) {
  const cls: Record<Verdict, string> = {
    BULLISH:  'bg-emerald-100 text-emerald-700 border-emerald-300',
    BEARISH:  'bg-rose-100 text-rose-700 border-rose-300',
    WATCH:    'bg-amber-100 text-amber-700 border-amber-300',
    NEUTRAL:  'bg-gray-100 text-gray-500 border-gray-300',
    'NO DATA':'bg-gray-50 text-gray-300 border-gray-200',
  };
  return (
    <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full border ${cls[v]} shrink-0 w-16 text-center inline-block`}>
      {v === 'NO DATA' ? '—' : v}
    </span>
  );
}

function SignalRow({ icon, label, verdict, fact, detail, tooltipText, onClick }: {
  icon: string; label: string; verdict: Verdict; fact: string;
  detail?: string; tooltipText?: string; onClick?: () => void;
}) {
  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 border-b border-gray-100 last:border-0 ${onClick ? 'cursor-pointer hover:bg-gray-50' : ''}`}
      onClick={onClick}
    >
      <span className="text-[10px] font-bold tracking-wider uppercase bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded shrink-0 mt-0.5 w-9 text-center">
        {icon}
      </span>
      <div className="w-28 shrink-0">
        <div className="text-[10px] font-semibold text-gray-700">
          {tooltipText ? <Tooltip text={tooltipText} position="right" width="w-80">{label}</Tooltip> : label}
        </div>
      </div>
      <VerdictPill v={verdict} />
      <div className="flex-1 min-w-0">
        <div className="text-[10px] text-gray-600 leading-relaxed">{fact}</div>
        {detail && <div className="text-[10px] text-gray-400 mt-0.5 truncate">{detail}</div>}
      </div>
    </div>
  );
}

function toVerdict(score?: number | null, highThresh = 60, lowThresh = 40): Verdict {
  if (score == null) return 'NO DATA';
  if (score >= highThresh) return 'BULLISH';
  if (score >= lowThresh) return 'WATCH';
  return 'NEUTRAL';
}

// ─── Gate Badge ───────────────────────────────────────────────────────────────

function GateBadge({ gate }: { gate: number }) {
  const cls = GATE_COLORS[gate] ?? 'bg-gray-200 text-gray-600';
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded font-mono ${cls}`}>
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
  // renders compact signal source chips — active=green, inactive=gray
  return (
    <div className="flex gap-1 mt-1">
      {SIG_SOURCES.map(k => {
        const has = k === 'pairs' ? !!(signals.pairs && signals.pairs.length > 0) : !!signals[k];
        return (
          <span
            key={k}
            title={k.replace(/_/g, ' ')}
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded tracking-wide ${
              has ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-gray-50 text-gray-300 border border-gray-100'
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

interface PerfData {
  total_signals: number; track_record_days: number; resolved_count: number;
  optimizer_status: string; win_rate_5d?: number; avg_return_5d?: number;
  win_rate_20d?: number; avg_return_20d?: number;
  module_leaderboard?: { module: string; ic: number; win_rate: number; signal_count: number }[];
}

export default function AlphaStack() {
  const [view, setView] = useState<'stack' | 'performance'>('stack');
  const [minGate, setMinGate] = useState(5);
  const [data, setData] = useState<AlphaEntry[]>([]);
  const [selected, setSelected] = useState<AlphaEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [perfData, setPerfData] = useState<PerfData | null>(null);
  const [perfLoading, setPerfLoading] = useState(false);
  const { open: openStock } = useStockPanel();

  useEffect(() => {
    setLoading(true);
    setSelected(null);
    fetch(`${API}/api/alpha/stack?min_gate=${minGate}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [minGate]);

  useEffect(() => {
    if (view !== 'performance' || perfData) return;
    setPerfLoading(true);
    fetch(`${API}/api/performance/overview`)
      .then(r => r.json())
      .then(d => { setPerfData(d); })
      .catch(() => {})
      .finally(() => setPerfLoading(false));
  }, [view]);

  // Auto-select first fat pitch or top result
  useEffect(() => {
    if (data.length > 0 && !selected) setSelected(data[0]);
  }, [data]);

  const totalSources = useMemo(() => selected ? SIG_SOURCES.filter(k =>
    k === 'pairs' ? !!(selected.signals.pairs?.length) : !!selected.signals[k]
  ).length : 0, [selected]);

  return (
    <div className="flex flex-col h-[calc(100vh-88px)] overflow-hidden bg-gray-50">

      {/* ── View toggle ── */}
      <div className="shrink-0 bg-white border-b border-gray-200 px-5 flex items-center gap-1 h-9">
        {([
          { id: 'stack',       label: 'Alpha Stack' },
          { id: 'performance', label: 'Performance — Data Moat' },
        ] as const).map(v => (
          <button
            key={v.id}
            onClick={() => setView(v.id)}
            className={`px-3 py-1 text-[10px] font-bold tracking-widest uppercase rounded transition-colors ${
              view === v.id ? 'bg-gray-900 text-white' : 'text-gray-400 hover:text-gray-700'
            }`}
          >
            {v.label}
          </button>
        ))}
      </div>

      {view === 'performance' && (
        <div className="flex-1 overflow-y-auto p-6">
          {perfLoading && <div className="animate-pulse text-gray-400 text-[11px]">Loading performance data...</div>}
          {!perfLoading && !perfData && <div className="text-gray-400 text-[11px] text-center py-16">No performance data yet — signals resolve after 5 trading days.</div>}
          {perfData && (
            <div className="max-w-3xl space-y-6">
              {/* Summary stats */}
              <div className="grid grid-cols-4 gap-3">
                {[
                  { label: 'TOTAL SIGNALS', val: perfData.total_signals?.toLocaleString() ?? '—', color: 'text-emerald-600' },
                  { label: 'TRACK RECORD', val: perfData.track_record_days != null ? `${perfData.track_record_days}d` : '—', color: 'text-blue-600' },
                  { label: 'RESOLVED (5D)', val: perfData.resolved_count?.toLocaleString() ?? '—', color: 'text-gray-700' },
                  { label: 'OPTIMIZER', val: perfData.optimizer_status ?? '—', color: perfData.optimizer_status === 'LIVE' ? 'text-emerald-600' : 'text-amber-600' },
                ].map(({ label, val, color }) => (
                  <div key={label} className="bg-white border border-gray-200 rounded-xl p-4">
                    <div className="text-[10px] text-gray-400 tracking-widest uppercase mb-1">{label}</div>
                    <div className={`text-xl font-bold font-mono ${color}`}>{val}</div>
                  </div>
                ))}
              </div>

              {/* Win rate by holding period */}
              <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-gray-100">
                  <div className="text-[10px] text-gray-400 tracking-widest uppercase font-semibold">Win Rate by Holding Period</div>
                </div>
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="border-b border-gray-100">
                      {['PERIOD', '5D WIN%', '5D AVG', '20D WIN%', '20D AVG'].map(h => (
                        <th key={h} className="text-left text-[10px] text-gray-400 px-5 py-2.5 font-semibold tracking-widest uppercase">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[{ level: 'HIGH', wr5: perfData.win_rate_5d, avg5: perfData.avg_return_5d, wr20: perfData.win_rate_20d, avg20: perfData.avg_return_20d }].map(row => (
                      <tr key={row.level} className="border-b border-gray-50">
                        <td className="px-5 py-3 font-bold text-emerald-600">{row.level}</td>
                        <td className={`px-5 py-3 font-mono font-bold ${(row.wr5 ?? 0) >= 50 ? 'text-emerald-600' : 'text-rose-500'}`}>{row.wr5 != null ? `${row.wr5.toFixed(1)}%` : '—'}</td>
                        <td className={`px-5 py-3 font-mono ${(row.avg5 ?? 0) >= 0 ? 'text-emerald-600' : 'text-rose-500'}`}>{row.avg5 != null ? `${row.avg5 >= 0 ? '+' : ''}${row.avg5.toFixed(2)}%` : '—'}</td>
                        <td className={`px-5 py-3 font-mono font-bold ${(row.wr20 ?? 0) >= 50 ? 'text-emerald-600' : row.wr20 == null ? 'text-gray-300' : 'text-rose-500'}`}>{row.wr20 != null ? `${row.wr20.toFixed(1)}%` : '—'}</td>
                        <td className={`px-5 py-3 font-mono ${(row.avg20 ?? 0) >= 0 ? 'text-emerald-600' : row.avg20 == null ? 'text-gray-300' : 'text-rose-500'}`}>{row.avg20 != null ? `${row.avg20 >= 0 ? '+' : ''}${row.avg20.toFixed(2)}%` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Module leaderboard */}
              {(perfData.module_leaderboard ?? []).length > 0 && (
                <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                  <div className="px-5 py-3 border-b border-gray-100">
                    <div className="text-[10px] text-gray-400 tracking-widest uppercase font-semibold">Module Leaderboard — IC Attribution</div>
                  </div>
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="border-b border-gray-100">
                        {['MODULE', 'IC', 'WIN RATE', 'SIGNALS'].map(h => (
                          <th key={h} className="text-left text-[10px] text-gray-400 px-5 py-2.5 font-semibold tracking-widest uppercase">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(perfData.module_leaderboard ?? []).map((mod, i) => (
                        <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                          <td className="px-5 py-2.5 font-semibold text-gray-800">{mod.module}</td>
                          <td className={`px-5 py-2.5 font-mono font-bold ${mod.ic >= 0.05 ? 'text-emerald-600' : mod.ic >= 0 ? 'text-amber-600' : 'text-rose-500'}`}>{mod.ic.toFixed(3)}</td>
                          <td className={`px-5 py-2.5 font-mono ${mod.win_rate >= 50 ? 'text-emerald-600' : 'text-rose-500'}`}>{mod.win_rate.toFixed(1)}%</td>
                          <td className="px-5 py-2.5 font-mono text-gray-500">{mod.signal_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {view === 'stack' && <div className="flex flex-1 overflow-hidden">

      {/* ── Left Panel: Ranked Stock List ── */}
      <div className="w-[260px] shrink-0 border-r border-gray-200 bg-white flex flex-col">

        {/* Gate filter — compact horizontal pills */}
        {(() => {
          const GATES = [
            { g: 4,  label: 'Sector + Macro',     sub: 'regime · liquidity · forensics' },
            { g: 5,  label: 'Trending',            sub: '+ technical momentum' },
            { g: 6,  label: 'Fundamental',         sub: '+ earnings quality' },
            { g: 7,  label: 'Smart Money',         sub: '+ institutional accumulation' },
            { g: 8,  label: 'High Conviction',     sub: '+ convergence across signals' },
            { g: 9,  label: 'Catalyst',            sub: '+ near-term catalyst' },
            { g: 10, label: 'Fat Pitch',           sub: 'all 10 gates — max conviction' },
          ];
          const active = GATES.find(x => x.g === minGate);
          return (
            <div className="px-3 pt-3 pb-2 border-b border-gray-100">
              <div className="flex flex-wrap gap-1 mb-2">
                {GATES.map(({ g }) => (
                  <button
                    key={g}
                    onClick={() => setMinGate(g)}
                    className={`text-[10px] font-bold font-mono px-2 py-1 rounded transition-colors ${
                      minGate === g
                        ? (GATE_COLORS[g] || 'bg-gray-700 text-white')
                        : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
                    }`}
                  >
                    G{g}+
                  </button>
                ))}
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-[11px] font-semibold text-gray-700">
                  {active && GATE_DEFS[active.g]
                    ? <Tooltip text={GATE_DEFS[active.g].description} position="bottom" width="w-80">{active.label}</Tooltip>
                    : active?.label}
                </span>
                <span className="text-[10px] text-gray-400">{active?.sub}</span>
              </div>
              <div className="text-[10px] text-gray-400 mt-0.5">
                {loading ? 'Loading...' : `${data.length} stocks`}
              </div>
            </div>
          );
        })()}

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
                    <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1 py-0.5 rounded font-bold">FAT</span>
                  )}
                  <GateBadge gate={entry.last_gate_passed} />
                  <span className={`ml-auto text-[10px] font-mono font-bold ${scoreTextCls(entry.composite_score)}`}>
                    {fmt(entry.composite_score)}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-gray-400 truncate flex-1">{entry.sector || entry.name || ''}</span>
                  <span className="text-[10px] text-gray-300 font-mono">{entry.signal_count}/9 src</span>
                </div>
                <SignalBreadthBar signals={entry.signals} />
              </button>
            ))
          )}
        </div>
      </div>

      {/* ── Right Panel: Signal Verdict Table ── */}
      <div className="flex-1 overflow-y-auto bg-gray-50">
        {!selected ? (
          <div className="flex items-center justify-center h-full text-[11px] text-gray-400">
            Select a stock to see its signal breakdown
          </div>
        ) : <VerdictPanel selected={selected} totalSources={totalSources} onOpenStock={openStock} />}
      </div>
    </div>}
    </div>
  );
}

function VerdictPanel({ selected, totalSources, onOpenStock }: {
  selected: AlphaEntry;
  totalSources: number;
  onOpenStock: (sym: string) => void;
}) {
  const s = selected.signals;
  const ins = s.insider;
  const pat = s.patterns;
  const opt = s.options;
  const alt = s.alt_data;
  const sc = s.supply_chain;
  const ma = s.ma;
  const pairs = s.pairs;
  const pm = s.prediction_markets;
  const de = s.digital_exhaust;

  // ─── Verdict derivations ───────────────────────────────
  const insVerdict = toVerdict(ins?.score);
  const insNetFlow = ins ? (ins.total_buy_value_30d || 0) - (ins.total_sell_value_30d || 0) : 0;
  const insFact = ins
    ? ins.cluster_buy
      ? `${ins.cluster_count || 'Multiple'} insiders buying · net ${fmtM(insNetFlow)} in 30d`
      : insNetFlow > 0 ? `Net buying: ${fmtM(insNetFlow)} · ${ins.top_buyer || ''}`
      : `Net selling: ${fmtM(insNetFlow)}`
    : 'No insider data';

  const patVerdict = toVerdict(pat?.score);
  const rawPats = pat?.patterns_detected;
  const patList = Array.isArray(rawPats) ? rawPats.map((p: unknown) =>
    typeof p === 'object' && p !== null ? (p as { pattern: string }).pattern : String(p)
  ) : [];
  const patFact = pat
    ? pat.wyckoff_phase
      ? `${pat.wyckoff_phase.replace(/_/g, ' ')} phase · ${patList.slice(0, 2).map((p: string) => p.replace(/_/g, ' ')).join(', ') || 'no patterns'}`
      : patList.length > 0 ? patList.slice(0, 2).map((p: string) => p.replace(/_/g, ' ')).join(', ') : 'No chart patterns'
    : 'No technical data';

  const optVerdict = toVerdict(opt?.score);
  const optFact = opt
    ? `${opt.pc_signal || 'Neutral flow'} · IV rank ${opt.iv_rank?.toFixed(0) ?? '—'}% · ${opt.unusual_activity_count ? `${opt.unusual_activity_count} unusual trades` : 'no unusual activity'}`
    : 'No options data';

  const altVerdict = toVerdict(alt?.score);
  const altSignals = alt?.signals;
  const altList = Array.isArray(altSignals) ? (altSignals as string[]).map((sig: string) => sig.split(':').pop()?.replace(/_/g, ' ') || sig) : [];
  const altFact = alt
    ? altList.length > 0 ? altList.slice(0, 3).join(' · ') : 'Score present, no specific signals'
    : 'No alternative data';

  const scVerdict = toVerdict(sc?.score);
  const scFact = sc
    ? `Rail ${sc.rail_score?.toFixed(0) ?? '—'} · Shipping ${sc.shipping_score?.toFixed(0) ?? '—'} · Trucking ${sc.trucking_score?.toFixed(0) ?? '—'}`
    : 'No supply chain data';

  const maVerdict: Verdict = ma?.score != null ? toVerdict(ma.score, 50, 30) : 'NO DATA';
  const maFact = ma
    ? ma.deal_stage
      ? `${ma.deal_stage.replace(/_/g, ' ')} · ${ma.acquirer_name || 'undisclosed acquirer'}${ma.expected_premium_pct ? ` · +${ma.expected_premium_pct.toFixed(0)}% est. premium` : ''}`
      : ma.best_headline || 'M&A signal present'
    : 'No M&A activity';

  const firstPair = pairs?.[0];
  const pairsVerdict: Verdict = firstPair ? (Math.abs(firstPair.spread_zscore || 0) >= 2 ? 'BULLISH' : 'WATCH') : 'NO DATA';
  const pairsFact = firstPair
    ? `${firstPair.symbol_a}/${firstPair.symbol_b} · ${firstPair.direction?.replace(/_/g, ' ')} · spread Z=${firstPair.spread_zscore?.toFixed(1) ?? '—'}`
    : 'No pairs signals';

  const pmVerdict = toVerdict(pm?.score);
  const pmFact = pm
    ? `${pm.market_count || 0} active markets · net impact ${pm.net_impact != null ? (pm.net_impact > 0 ? `+${pm.net_impact.toFixed(1)}` : pm.net_impact.toFixed(1)) : '—'}`
    : 'No prediction market data';

  // Treat as NO DATA if all sub-scores are exactly 50 (API default — real fetch failed)
  const deHasRealData = de != null && !(de.app_score === 50 && de.github_score === 50 && de.pricing_score === 50);
  const deVerdict: Verdict = deHasRealData ? toVerdict(de!.score) : 'NO DATA';
  const deFact = deHasRealData
    ? `App ${de!.app_score?.toFixed(0) ?? '—'} · GitHub ${de!.github_score?.toFixed(0) ?? '—'} · Pricing ${de!.pricing_score?.toFixed(0) ?? '—'}`
    : 'Not covered (tech/consumer stocks only)';

  const verdicts = [insVerdict, patVerdict, optVerdict, altVerdict, scVerdict, maVerdict, pairsVerdict, pmVerdict, deVerdict];
  const bullishCount = useMemo(() => verdicts.filter(v => v === 'BULLISH').length, [verdicts.join()]);  // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="max-w-[820px]">
      {/* Stock header */}
      <div className="bg-white border-b border-gray-200 px-5 py-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="text-xl font-bold text-gray-900 font-mono">{selected.symbol}</span>
            {selected.is_fat_pitch && (
              <span className="text-[10px] font-bold bg-emerald-500 text-white px-2 py-0.5 rounded-full uppercase tracking-widest">
                Fat Pitch
              </span>
            )}
            <GateBadge gate={selected.last_gate_passed} />
            {selected.signal && (
              <span className={`text-[10px] font-bold border px-1.5 py-0.5 rounded uppercase ${SIGNAL_COLOR[selected.signal] || ''}`}>
                {SIGNAL_LABELS[selected.signal] || selected.signal}
              </span>
            )}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            {selected.name}{selected.sector ? ` · ${selected.sector}` : ''}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-[10px] text-gray-400 tracking-widest uppercase mb-1">Signal Consensus</div>
            <div className="flex items-center gap-1">
              {Array.from({ length: 9 }, (_, i) => (
                <div key={i} className={`w-2.5 h-2.5 rounded-full ${i < bullishCount ? 'bg-emerald-500' : 'bg-gray-200'}`} />
              ))}
              <span className={`ml-2 text-[11px] font-bold font-mono ${bullishCount >= 6 ? 'text-emerald-600' : bullishCount >= 3 ? 'text-amber-600' : 'text-gray-400'}`}>
                {bullishCount}/9
              </span>
            </div>
          </div>
          <button
            onClick={() => onOpenStock(selected.symbol)}
            className="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-1.5 rounded-lg hover:bg-emerald-100 transition-colors font-semibold"
          >
            Price Chart →
          </button>
        </div>
      </div>

      {/* Verdict table */}
      <div className="bg-white border border-gray-200 rounded-xl m-4 overflow-hidden shadow-sm">
        <div className="px-4 py-2.5 border-b border-gray-100 flex items-center justify-between">
          <span className="text-[10px] text-gray-400 uppercase tracking-widest font-semibold">Independent Signal Sources</span>
          <span className="text-[10px] text-gray-400">{totalSources} of 9 active</span>
        </div>

        <SignalRow icon="INS" label="Insider Trading"    verdict={insVerdict}    fact={insFact}    detail={ins?.top_buyer || undefined} tooltipText={SIGNAL_MODULE_DEFS.insider}            onClick={() => onOpenStock(selected.symbol)} />
        <SignalRow icon="PAT" label="Chart Patterns"     verdict={patVerdict}    fact={patFact}    detail={pat?.vol_regime ? `Vol regime: ${pat.vol_regime}` : undefined} tooltipText={SIGNAL_MODULE_DEFS.patterns} />
        <SignalRow icon="OPT" label="Options Flow"       verdict={optVerdict}    fact={optFact}    detail={opt?.dealer_regime ? `Dealer: ${opt.dealer_regime}` : undefined} tooltipText={SIGNAL_MODULE_DEFS.options} />
        <SignalRow icon="ALT" label="Alternative Data"   verdict={altVerdict}    fact={altFact}    tooltipText={SIGNAL_MODULE_DEFS.alt_data} />
        <SignalRow icon="SUP" label="Supply Chain"       verdict={scVerdict}     fact={scFact}     tooltipText={SIGNAL_MODULE_DEFS.supply_chain} />
        <SignalRow icon="M&A" label="M&A Activity"       verdict={maVerdict}     fact={maFact}     detail={ma?.narrative || undefined} tooltipText={SIGNAL_MODULE_DEFS.ma} />
        <SignalRow icon="PAI" label="Pairs / Stat Arb"   verdict={pairsVerdict}  fact={pairsFact}  tooltipText={SIGNAL_MODULE_DEFS.pairs} />
        <SignalRow icon="PM"  label="Prediction Markets" verdict={pmVerdict}     fact={pmFact}     detail={pm?.narrative || undefined} tooltipText={SIGNAL_MODULE_DEFS.prediction_markets} />
        <SignalRow icon="DIG" label="Digital Footprint"  verdict={deVerdict}     fact={deFact}     tooltipText={SIGNAL_MODULE_DEFS.digital_exhaust} />
      </div>

      {totalSources === 0 && (
        <div className="mx-4 bg-amber-50 border border-amber-200 rounded-xl p-5 text-center">
          <div className="text-sm font-semibold text-amber-700 mb-1">No signal data yet</div>
          <p className="text-[11px] text-amber-600">Run the pipeline to populate all signal sources.</p>
        </div>
      )}
    </div>
  );
}

