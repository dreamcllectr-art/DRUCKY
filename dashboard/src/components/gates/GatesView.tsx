'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { useStockPanel } from '@/contexts/StockPanelContext';

// ─── Types ───────────────────────────────────────────────────────────────────

interface GateCascade {
  gate: number;
  name: string;
  count: number;
  pct_of_universe: number;
  pct_of_prev: number;
  threshold: string;
}

interface CascadeData {
  run_date: string;
  run_id: string;
  cascade: GateCascade[];
  fat_pitches: number;
}

interface GateAsset {
  symbol: string;
  name?: string;
  sector?: string;
  asset_class: string;
  last_gate_passed: number;
  fail_reason?: string;
  composite_score?: number;
  signal?: string;
}

interface SymbolGateDetail {
  symbol: string;
  date: string;
  last_gate_passed: number;
  fail_reason?: string;
  asset_class: string;
  is_fat_pitch: boolean;
  gates: { gate: number; name: string; passed: number | null; is_last_failed: boolean }[];
  overrides: { gate: number; direction: string; reason: string }[];
  catalyst?: { catalyst_type: string; catalyst_strength: number; catalyst_detail: string };
}

interface FatPitch {
  symbol: string;
  name?: string;
  sector?: string;
  asset_class: string;
  composite_score?: number;
  signal?: string;
  rr_ratio?: number;
  convergence_score?: number;
  module_count?: number;
  conviction_level?: string;
  narrative?: string;
  catalyst_type?: string;
  catalyst_detail?: string;
  short_float_pct?: number;
  consensus_grade?: string;
  pt_upside_pct?: number;
}

// ─── Constants ───────────────────────────────────────────────────────────────

// Semantic gradient: gate 0 = full universe (slate), 1-9 progressively emerald, 10 = fat pitch (vivid)
const GATE_COLORS: Record<number, string> = {
  0:  '#94a3b8',
  1:  '#a7f3d0',
  2:  '#6ee7b7',
  3:  '#34d399',
  4:  '#10b981',
  5:  '#059669',
  6:  '#047857',
  7:  '#065f46',
  8:  '#064e3b',
  9:  '#022c22',
  10: '#059669',
};

const SIGNAL_COLOR: Record<string, string> = {
  STRONG_BUY: 'text-emerald-400',
  BUY: 'text-emerald-300',
  NEUTRAL: 'text-gray-400',
  SELL: 'text-rose-400',
  STRONG_SELL: 'text-rose-500',
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

function ScorePill({ score }: { score?: number }) {
  if (score == null) return <span className="text-gray-400">—</span>;
  const color =
    score >= 70 ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
    score >= 55 ? 'bg-amber-50 text-amber-700 border border-amber-200' :
    'bg-gray-100 text-gray-500 border border-gray-200';
  return (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${color}`}>
      {score.toFixed(0)}
    </span>
  );
}

// ─── Waterfall Panel ─────────────────────────────────────────────────────────

function WaterfallPanel({
  cascade,
  selectedGate,
  onSelectGate,
}: {
  cascade: GateCascade[];
  selectedGate: number;
  onSelectGate: (g: number) => void;
}) {
  const maxCount = cascade[0]?.count || 1;

  return (
    <div className="space-y-0.5">
      {cascade.map((g) => {
        // Log scale so tiny counts (4, 9, 33) still render as readable bars
        const barPct = Math.max(6, (Math.log1p(g.count) / Math.log1p(maxCount)) * 100);
        const isSelected = selectedGate === g.gate;
        const isFatPitch = g.gate === 10;
        const color = GATE_COLORS[g.gate] || '#6b7280';

        return (
          <button
            key={g.gate}
            onClick={() => onSelectGate(g.gate)}
            className={`w-full text-left transition-all duration-150 rounded px-2 py-1.5 ${
              isSelected ? 'bg-gray-50 ring-1 ring-gray-200' : 'hover:bg-gray-50'
            }`}
          >
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-mono text-gray-500 w-4">{g.gate}</span>
              <span className={`text-[10px] font-medium tracking-wide ${isFatPitch ? 'text-emerald-600' : 'text-gray-700'}`}>
                {g.name.toUpperCase()}
              </span>
              <span className="ml-auto text-[10px] font-mono text-gray-500">
                {g.count.toLocaleString()}
              </span>
            </div>

            {/* Bar */}
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden ml-6">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${barPct}%`, backgroundColor: color, opacity: 0.8 }}
              />
            </div>

            {g.gate > 0 && (
              <div className="flex justify-end ml-6 mt-0.5">
                <span className="text-[10px] text-gray-400">
                  {g.pct_of_prev.toFixed(0)}% of prev
                </span>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ─── Asset List Panel ────────────────────────────────────────────────────────

function AssetListPanel({
  gate,
  gateName,
  assets,
  onSelectSymbol,
  selectedSymbol,
  loading,
}: {
  gate: number;
  gateName: string;
  assets: GateAsset[];
  onSelectSymbol: (s: string) => void;
  selectedSymbol: string | null;
  loading: boolean;
}) {
  return (
    <div className="h-full flex flex-col">
      <div className="mb-3 px-1 flex items-center justify-between">
        <div>
          <span className="text-[10px] text-gray-500 tracking-widest">GATE {gate}</span>
          <h2 className="text-sm font-bold text-slate-900 tracking-wide">{gateName}</h2>
        </div>
        <span className="text-[10px] text-gray-500 font-mono">{assets.length} assets</span>
      </div>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-[10px] text-gray-400 animate-pulse">Loading...</span>
        </div>
      ) : assets.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-[10px] text-gray-600">No assets at this gate</span>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-0.5 pr-1">
          {assets.map((a) => (
            <button
              key={a.symbol}
              onClick={() => onSelectSymbol(a.symbol)}
              className={`w-full text-left px-2 py-1.5 rounded transition-all ${
                selectedSymbol === a.symbol
                  ? 'bg-gray-50 ring-1 ring-gray-200'
                  : 'hover:bg-gray-50'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-bold text-gray-900 font-mono w-14 shrink-0">
                  {a.symbol}
                </span>
                <span className="text-[10px] text-gray-500 truncate flex-1">
                  {a.name || a.sector || ''}
                </span>
                <span className={`text-[10px] font-mono shrink-0 ${
                  a.asset_class === 'crypto' ? 'text-purple-400' :
                  a.asset_class === 'commodity' ? 'text-amber-400' :
                  'text-gray-500'
                }`}>
                  {a.asset_class?.[0]?.toUpperCase() || 'E'}
                </span>
                {a.composite_score != null && (
                  <ScorePill score={a.composite_score} />
                )}
                {a.signal && (
                  <span className={`text-[10px] font-mono shrink-0 ${SIGNAL_COLOR[a.signal] || 'text-gray-500'}`}>
                    {a.signal.replace('_', ' ')}
                  </span>
                )}
              </div>
              {a.fail_reason && (
                <div className="mt-0.5 ml-0 text-[10px] text-gray-600 truncate">
                  {a.fail_reason}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Gate Detail Panel ───────────────────────────────────────────────────────

function GateDetailPanel({
  detail,
  loading,
  onOverride,
}: {
  detail: SymbolGateDetail | null;
  loading: boolean;
  onOverride: (symbol: string, gate: number, direction: string, reason: string) => void;
}) {
  const [overrideGate, setOverrideGate] = useState<number | null>(null);
  const [overrideDir, setOverrideDir] = useState<'force_pass' | 'force_fail'>('force_pass');
  const [overrideReason, setOverrideReason] = useState('');

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <span className="text-[10px] text-gray-400 animate-pulse">Loading...</span>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 px-6">
        <svg className="text-slate-200" width="36" height="36" viewBox="0 0 36 36" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 9h24M6 18h18M6 27h12"/>
          <circle cx="28" cy="24" r="6"/>
          <path d="M28 21v3l2 2"/>
        </svg>
        <p className="text-[11px] text-slate-400 text-center leading-relaxed">
          Select an asset<br/>to see gate-by-gate detail
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-y-auto space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link
            href={`/asset/${detail.symbol}`}
            className="text-base font-bold text-gray-900 hover:text-emerald-600 transition-colors font-mono"
          >
            {detail.symbol} ↗
          </Link>
          <div className="text-[10px] text-gray-500 mt-0.5">
            {detail.asset_class} · Gate {detail.last_gate_passed} reached
            {detail.is_fat_pitch && (
              <span className="ml-2 text-emerald-600 font-bold">● FAT PITCH</span>
            )}
          </div>
        </div>
        {detail.fail_reason && (
          <div className="text-[10px] text-rose-600 bg-rose-50 border border-rose-100 px-2 py-1 rounded max-w-[140px] text-right leading-tight">
            {detail.fail_reason}
          </div>
        )}
      </div>

      {/* Gate dots */}
      <div className="space-y-1">
        <span className="text-[10px] text-gray-500 tracking-widest">GATE PROGRESSION</span>
        <div className="grid grid-cols-1 gap-0.5">
          {detail.gates.map((g) => {
            const override = detail.overrides.find(o => o.gate === g.gate);
            const color = GATE_COLORS[g.gate] || '#6b7280';
            const passed = g.passed === 1;
            const failed = g.passed === 0;
            const skipped = g.passed == null;

            return (
              <div
                key={g.gate}
                className={`flex items-center gap-2 px-2 py-1 rounded ${
                  g.is_last_failed ? 'bg-rose-500/10 ring-1 ring-rose-500/30' : ''
                }`}
              >
                {/* Status dot */}
                <div
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    passed ? 'opacity-100' :
                    failed ? 'bg-rose-400 opacity-100' :
                    'bg-gray-200 opacity-100'
                  }`}
                  style={passed ? { backgroundColor: color } : undefined}
                />

                <span className="text-[10px] text-gray-500 w-3 font-mono">{g.gate}</span>
                <span className={`text-[10px] flex-1 ${
                  passed ? 'text-gray-700' :
                  failed ? 'text-rose-500' :
                  'text-gray-400'
                }`}>
                  {g.name}
                </span>

                {/* Override indicator */}
                {override && (
                  <span className="text-[10px] text-amber-400 font-mono">
                    {override.direction === 'force_pass' ? '↑OVR' : '↓OVR'}
                  </span>
                )}

                {/* Pass/fail badge */}
                <span className={`text-[10px] font-mono shrink-0 ${
                  passed ? 'text-emerald-500' :
                  failed ? 'text-rose-500' :
                  'text-gray-700'
                }`}>
                  {passed ? 'PASS' : failed ? 'FAIL' : '—'}
                </span>

                {/* Override button */}
                {g.gate > 0 && (
                  <button
                    onClick={() => setOverrideGate(overrideGate === g.gate ? null : g.gate)}
                    className="text-[10px] text-gray-300 hover:text-amber-500 transition-colors ml-1"
                  >
                    OVR
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Override form */}
      {overrideGate !== null && (
        <div className="bg-amber-500/5 border border-amber-500/20 rounded p-2 space-y-2">
          <span className="text-[10px] text-amber-400 tracking-widest">
            OVERRIDE GATE {overrideGate}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setOverrideDir('force_pass')}
              className={`text-[10px] px-2 py-1 rounded ${
                overrideDir === 'force_pass'
                  ? 'bg-emerald-500/20 text-emerald-400'
                  : 'bg-gray-100 text-gray-500'
              }`}
            >
              FORCE PASS
            </button>
            <button
              onClick={() => setOverrideDir('force_fail')}
              className={`text-[10px] px-2 py-1 rounded ${
                overrideDir === 'force_fail'
                  ? 'bg-rose-50 text-rose-600 border border-rose-200'
                  : 'bg-gray-100 text-gray-500'
              }`}
            >
              FORCE FAIL
            </button>
          </div>
          <input
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            placeholder="Reason for override..."
            className="w-full bg-white border border-gray-200 rounded px-2 py-1 text-[10px] text-gray-700 placeholder-gray-400"
          />
          <button
            onClick={() => {
              if (overrideReason.trim()) {
                onOverride(detail.symbol, overrideGate, overrideDir, overrideReason);
                setOverrideGate(null);
                setOverrideReason('');
              }
            }}
            className="text-[10px] bg-amber-500/20 text-amber-400 px-3 py-1 rounded hover:bg-amber-500/30 transition-colors"
          >
            Apply Override
          </button>
        </div>
      )}

      {/* Catalyst */}
      {detail.catalyst && (
        <div className="bg-purple-50 border border-purple-200 rounded p-2">
          <span className="text-[10px] text-purple-500 tracking-widest">CATALYST</span>
          <div className="mt-1">
            <span className="text-[10px] font-bold text-purple-700">
              {detail.catalyst.catalyst_type}
            </span>
            <span className="text-[10px] text-gray-500 ml-2">
              strength: {detail.catalyst.catalyst_strength?.toFixed(0)}
            </span>
          </div>
          {detail.catalyst.catalyst_detail && (
            <p className="text-[10px] text-gray-500 mt-0.5">
              {detail.catalyst.catalyst_detail}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Fat Pitches Panel ───────────────────────────────────────────────────────

function FatPitchesPanel({ pitches }: { pitches: FatPitch[] }) {
  return (
    <div className="space-y-1">
      {pitches.length === 0 ? (
        <p className="text-[10px] text-gray-600 text-center py-8">
          No fat pitches today — run the pipeline to populate
        </p>
      ) : (
        pitches.map((p, i) => (
          <Link
            key={p.symbol}
            href={`/dossier/${p.symbol}`}
            className="block px-3 py-2 rounded hover:bg-white/5 transition-colors border border-transparent hover:border-emerald-500/20"
          >
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-gray-500 w-4 font-mono">{i + 1}</span>
              <span className="font-mono font-bold text-sm text-slate-900 w-14">{p.symbol}</span>
              <span className={`text-[10px] font-mono ${SIGNAL_COLOR[p.signal || ''] || 'text-gray-400'}`}>
                {p.signal?.replace('_', ' ') || '—'}
              </span>
              <ScorePill score={p.composite_score} />
              <span className="text-[10px] text-gray-600 flex-1 truncate">{p.name}</span>
              {p.rr_ratio != null && (
                <span className="text-[10px] text-amber-400 font-mono shrink-0">
                  R:R {p.rr_ratio.toFixed(1)}×
                </span>
              )}
              {p.catalyst_type && (
                <span className="text-[10px] text-purple-400 shrink-0">{p.catalyst_type}</span>
              )}
              {p.consensus_grade && (
                <span className="text-[10px] text-sky-400 shrink-0">{p.consensus_grade}</span>
              )}
            </div>
            {p.narrative && (
              <p className="text-[10px] text-gray-600 ml-6 mt-0.5 truncate">{p.narrative}</p>
            )}
          </Link>
        ))
      )}
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function GatesView() {
  const [cascadeData, setCascadeData] = useState<CascadeData | null>(null);
  const [selectedGate, setSelectedGate] = useState(10);
  const [gateAssets, setGateAssets] = useState<GateAsset[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [symbolDetail, setSymbolDetail] = useState<SymbolGateDetail | null>(null);
  const [loadingCascade, setLoadingCascade] = useState(true);
  const [loadingAssets, setLoadingAssets] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { open: openStock } = useStockPanel();

  // Load cascade data
  useEffect(() => {
    apiFetch<CascadeData>('/api/gates/cascade')
      .then(setCascadeData)
      .catch((e) => setError(e.message))
      .finally(() => setLoadingCascade(false));
  }, []);

  // Load assets for selected gate
  useEffect(() => {
    setLoadingAssets(true);
    apiFetch<{ gate: number; gate_name: string; assets: GateAsset[] }>(
      `/api/gates/passing/${selectedGate}`
    )
      .then((data) => setGateAssets(data.assets || []))
      .catch(console.error)
      .finally(() => setLoadingAssets(false));
  }, [selectedGate]);

  // Load symbol detail
  useEffect(() => {
    if (!selectedSymbol) { setSymbolDetail(null); return; }
    setLoadingDetail(true);
    apiFetch<SymbolGateDetail>(`/api/gates/results/${selectedSymbol}`)
      .then(setSymbolDetail)
      .catch(console.error)
      .finally(() => setLoadingDetail(false));
  }, [selectedSymbol]);

  const handleOverride = useCallback(async (
    symbol: string, gate: number, direction: string, reason: string
  ) => {
    await fetch(`${API_BASE}/api/gates/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol, gate, direction, reason }),
    });
    // Refresh detail
    apiFetch<SymbolGateDetail>(`/api/gates/results/${symbol}`)
      .then(setSymbolDetail)
      .catch(console.error);
  }, []);

  const lastRun = cascadeData?.run_date;
  const fatCount = cascadeData?.fat_pitches ?? 0;

  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      {/* Top bar */}
      <div className="border-b border-gray-100 bg-white px-4 py-2.5">
        <div className="max-w-[1600px] mx-auto flex items-center gap-4 flex-wrap">
          <h1 className="text-xs font-bold tracking-widest text-gray-800">
            10-GATE CASCADE
          </h1>
          <span className="text-[10px] text-gray-400">
            {lastRun ? `Last run: ${lastRun}` : 'Not yet run'}
          </span>

          {/* Fat pitch counter */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-gray-400">FAT PITCHES</span>
            <span className="text-sm font-bold text-emerald-600 font-mono">{fatCount}</span>
          </div>

          {/* Gate count pills */}
          {cascadeData?.cascade.slice(1).map((g) => (
            <div key={g.gate} className="flex items-center gap-1">
              <span className="text-[10px] text-gray-400 font-mono">G{g.gate}</span>
              <span className="text-[10px] font-mono text-gray-600">{g.count}</span>
            </div>
          ))}

        </div>
      </div>

      {error && (
        <div className="bg-rose-500/10 border-b border-rose-500/20 px-4 py-2 text-[10px] text-rose-400">
          API error: {error} — pipeline may not have run gates yet
        </div>
      )}

      {/* Cascade View — 3 panels */}
      <div className="max-w-[1600px] mx-auto px-4 py-4">
        <div className="grid grid-cols-[220px_1fr_280px] gap-4 h-[calc(100vh-100px)]">

          {/* Left: Waterfall */}
          <div className="overflow-y-auto pr-1">
            <div className="mb-3">
              <span className="text-[10px] text-gray-400 tracking-widest">WATERFALL</span>
            </div>
            {loadingCascade ? (
              <div className="text-[10px] text-gray-400 animate-pulse">Loading...</div>
            ) : cascadeData ? (
              <WaterfallPanel
                cascade={cascadeData.cascade}
                selectedGate={selectedGate}
                onSelectGate={setSelectedGate}
              />
            ) : (
              <p className="text-[10px] text-gray-400">No data — run pipeline first</p>
            )}
          </div>

          {/* Center: Asset list */}
          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm overflow-hidden flex flex-col">
            <AssetListPanel
              gate={selectedGate}
              gateName={cascadeData?.cascade.find(c => c.gate === selectedGate)?.name || `Gate ${selectedGate}`}
              assets={gateAssets}
              onSelectSymbol={(sym) => { setSelectedSymbol(sym); openStock(sym); }}
              selectedSymbol={selectedSymbol}
              loading={loadingAssets}
            />
          </div>

          {/* Right: Gate detail */}
          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm overflow-hidden">
            <GateDetailPanel
              detail={symbolDetail}
              loading={loadingDetail}
              onOverride={handleOverride}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
