'use client';

import { useEffect, useState, useMemo } from 'react';
import {
  api,
  type CrossAssetOpp,
  type CrossAssetClass,
  type NarrativeSignal,
  type ModuleIC,
  type ModuleICRank,
} from '@/lib/api';

// ── Helpers ────────────────────────────────────────────────────────────────

const fmt = (v: number | null | undefined, decimals = 1, suffix = '') =>
  v == null ? '—' : `${v.toFixed(decimals)}${suffix}`;

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${(v * 100).toFixed(1)}%`;

const scoreColor = (v: number) =>
  v >= 75 ? '#059669' : v >= 55 ? '#10b981' : v >= 40 ? '#d97706' : '#e11d48';

const icColor = (v: number | null) => {
  if (v == null) return '#9ca3af';
  if (v >= 0.05) return '#059669';
  if (v >= 0.02) return '#10b981';
  if (v >= 0) return '#d97706';
  return '#e11d48';
};

const ASSET_CLASS_LABELS: Record<string, string> = {
  equity_growth: 'Growth',
  equity_value: 'Value',
  equity_defensive: 'Defensive',
  commodity_energy: 'Energy',
  commodity_gold: 'Gold',
  commodity_grain: 'Grains',
  commodity_copper: 'Copper',
  commodity_silver: 'Silver',
  commodity_other: 'Commodity',
  crypto: 'Crypto',
};

const NARRATIVE_ICONS: Record<string, string> = {
  commodity_supercycle: '🌾',
  ai_infrastructure: '🤖',
  reshoring: '🏭',
  rate_normalization: '📉',
  energy_transition: '⚡',
  defense_rearmament: '🛡',
  dollar_debasement: '💵',
  consumer_bifurcation: '📊',
  healthcare_innovation: '🧬',
  credit_stress: '⚠️',
  geopolitical_fragmentation: '🌐',
  crypto_adoption: '₿',
};

// ── Sub-components ─────────────────────────────────────────────────────────

function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-xs font-semibold text-gray-900 tracking-widest uppercase">{title}</h2>
      {subtitle && <p className="text-[10px] text-gray-400 mt-0.5">{subtitle}</p>}
    </div>
  );
}

function StatCard({
  label, value, sub, color,
}: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 shadow-sm">
      <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-1">{label}</div>
      <div className="text-xl font-bold" style={{ color: color ?? '#111827' }}>{value}</div>
      {sub && <div className="text-[9px] text-gray-400 mt-0.5">{sub}</div>}
    </div>
  );
}

function AssetClassBar({ data }: { data: CrossAssetClass[] }) {
  const maxScore = Math.max(...data.map(d => d.avg_score), 1);
  return (
    <div className="space-y-2">
      {data.map(d => (
        <div key={d.asset_class} className="flex items-center gap-3">
          <div className="w-24 text-[10px] text-gray-500 text-right shrink-0">
            {ASSET_CLASS_LABELS[d.asset_class] ?? d.asset_class}
          </div>
          <div className="flex-1 h-5 bg-gray-50 rounded-md overflow-hidden border border-gray-100">
            <div
              className="h-full rounded-md transition-all duration-500 flex items-center pl-2"
              style={{
                width: `${(d.avg_score / maxScore) * 100}%`,
                backgroundColor: `${scoreColor(d.avg_score)}18`,
                borderRight: `2px solid ${scoreColor(d.avg_score)}`,
              }}
            >
              <span className="text-[9px] font-mono" style={{ color: scoreColor(d.avg_score) }}>
                {d.avg_score.toFixed(1)}
              </span>
            </div>
          </div>
          <div className="text-[9px] text-gray-400 w-20 shrink-0">
            {d.count} stocks{d.fat_pitches > 0 && <span className="text-emerald-600 ml-1">· {d.fat_pitches} fat</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function FatPitchCard({ opp }: { opp: CrossAssetOpp }) {
  const color = scoreColor(opp.opportunity_score);
  const assetLabel = ASSET_CLASS_LABELS[opp.asset_class] ?? opp.asset_class;
  return (
    <a
      href={`/asset/${opp.symbol}`}
      className="block bg-white border border-gray-100 rounded-xl p-4 shadow-sm hover:shadow-md hover:border-gray-200 transition-all group"
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="font-bold text-gray-900 text-sm group-hover:text-emerald-600 transition-colors">
            {opp.symbol}
          </div>
          <div className="text-[9px] text-gray-400 mt-0.5">{assetLabel}{opp.sector ? ` · ${opp.sector}` : ''}</div>
        </div>
        <div
          className="text-lg font-bold font-mono"
          style={{ color }}
        >
          {opp.opportunity_score.toFixed(0)}
        </div>
      </div>

      {/* Score bars */}
      <div className="grid grid-cols-2 gap-1.5 mb-2">
        {opp.technical_score != null && (
          <div>
            <div className="text-[8px] text-gray-400 mb-0.5">Technical</div>
            <div className="h-1 bg-gray-100 rounded-full">
              <div className="h-1 rounded-full bg-emerald-500" style={{ width: `${Math.min(opp.technical_score, 100)}%` }} />
            </div>
          </div>
        )}
        {opp.fundamental_score != null && (
          <div>
            <div className="text-[8px] text-gray-400 mb-0.5">Fundamental</div>
            <div className="h-1 bg-gray-100 rounded-full">
              <div className="h-1 rounded-full bg-blue-500" style={{ width: `${Math.min(opp.fundamental_score, 100)}%` }} />
            </div>
          </div>
        )}
      </div>

      {opp.momentum_20d != null && (
        <div className="text-[9px]" style={{ color: opp.momentum_20d >= 0 ? '#059669' : '#e11d48' }}>
          20d mom: {opp.momentum_20d >= 0 ? '+' : ''}{(opp.momentum_20d * 100).toFixed(1)}%
        </div>
      )}
      {opp.fat_pitch_reason && (
        <div className="text-[9px] text-amber-600 mt-1 truncate">{opp.fat_pitch_reason}</div>
      )}
    </a>
  );
}

function NarrativeCard({
  sig,
  active,
  onClick,
}: { sig: NarrativeSignal; active: boolean; onClick: () => void }) {
  const icon = NARRATIVE_ICONS[sig.narrative] ?? '◈';
  const strength = sig.strength_score;
  const crowding = sig.crowding_score ?? 0;

  return (
    <button
      onClick={onClick}
      className={`w-full text-left bg-white border rounded-xl p-4 shadow-sm transition-all ${
        active ? 'border-emerald-400 shadow-emerald-100/50' : 'border-gray-100 hover:border-gray-200'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="text-xl shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="text-[11px] font-semibold text-gray-900 capitalize">
            {sig.narrative.replace(/_/g, ' ')}
          </div>
          <div className="flex items-center gap-3 mt-2">
            {/* Strength bar */}
            <div className="flex-1">
              <div className="flex justify-between text-[8px] text-gray-400 mb-0.5">
                <span>Strength</span>
                <span style={{ color: scoreColor(strength * 100) }}>{(strength * 100).toFixed(0)}</span>
              </div>
              <div className="h-1 bg-gray-100 rounded-full">
                <div
                  className="h-1 rounded-full transition-all"
                  style={{
                    width: `${Math.min(strength * 100, 100)}%`,
                    backgroundColor: scoreColor(strength * 100),
                  }}
                />
              </div>
            </div>
            {/* Crowding bar */}
            <div className="flex-1">
              <div className="flex justify-between text-[8px] text-gray-400 mb-0.5">
                <span>Crowded</span>
                <span className={crowding > 0.7 ? 'text-red-500' : 'text-gray-500'}>
                  {(crowding * 100).toFixed(0)}
                </span>
              </div>
              <div className="h-1 bg-gray-100 rounded-full">
                <div
                  className="h-1 rounded-full transition-all"
                  style={{
                    width: `${Math.min(crowding * 100, 100)}%`,
                    backgroundColor: crowding > 0.7 ? '#e11d48' : '#9ca3af',
                  }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}

function ICLeaderboard({ modules }: { modules: ModuleICRank[] }) {
  return (
    <div className="space-y-1">
      {modules.slice(0, 12).map((m, i) => {
        const ic = m.avg_ic ?? 0;
        const color = icColor(ic);
        return (
          <div
            key={m.module}
            className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <span className="text-[9px] text-gray-300 w-4 text-right">{i + 1}</span>
            <span className="text-[10px] font-medium text-gray-700 flex-1 capitalize">
              {m.module.replace(/_/g, ' ')}
            </span>
            <span className="text-[10px] font-mono w-12 text-right" style={{ color }}>
              {ic >= 0 ? '+' : ''}{fmt(ic, 3)}
            </span>
            <span className="text-[9px] text-gray-400 w-14 text-right">
              IR: {fmt(m.avg_ir, 2)}
            </span>
            <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.max(0, Math.min(ic / 0.1, 1)) * 100}%`,
                  backgroundColor: color,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ICHeatmap({ data }: { data: ModuleIC[] }) {
  const regimes = ['risk_on', 'neutral', 'risk_off'];
  const horizons = [1, 5, 10, 20, 30];
  const modules = [...new Set(data.map(d => d.module))];

  const lookup = useMemo(() => {
    const m: Record<string, number | null> = {};
    data.forEach(d => { m[`${d.module}|${d.regime}|${d.horizon_days}`] = d.mean_ic; });
    return m;
  }, [data]);

  if (modules.length === 0) {
    return (
      <div className="text-[11px] text-gray-400 text-center py-8">
        IC data will populate after pipeline runs for several days.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[9px]">
        <thead>
          <tr>
            <th className="text-left text-gray-400 py-1 pr-3 font-normal w-32">Module</th>
            {regimes.map(r => horizons.map(h => (
              <th key={`${r}|${h}`} className="text-center text-gray-400 py-1 px-1 font-normal capitalize">
                <div>{r.replace('_', ' ')}</div>
                <div className="text-gray-300">{h}d</div>
              </th>
            )))}
          </tr>
        </thead>
        <tbody>
          {modules.map(mod => (
            <tr key={mod} className="border-t border-gray-50">
              <td className="text-gray-600 py-1.5 pr-3 capitalize whitespace-nowrap">
                {mod.replace(/_/g, ' ')}
              </td>
              {regimes.map(r => horizons.map(h => {
                const ic = lookup[`${mod}|${r}|${h}`] ?? null;
                const bg = ic == null ? 'transparent' : ic >= 0.05 ? '#05966915' : ic >= 0.02 ? '#10b98115' : ic >= 0 ? '#d9770608' : '#e11d4810';
                return (
                  <td
                    key={`${r}|${h}`}
                    className="text-center py-1.5 px-1 font-mono"
                    style={{ backgroundColor: bg, color: icColor(ic) }}
                  >
                    {ic == null ? '·' : `${ic >= 0 ? '+' : ''}${ic.toFixed(3)}`}
                  </td>
                );
              }))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

type Tab = 'cross-asset' | 'narratives' | 'ic';

export default function AlphaContent() {
  const [tab, setTab] = useState<Tab>('cross-asset');

  // Cross-asset state
  const [crossAsset, setCrossAsset] = useState<CrossAssetOpp[]>([]);
  const [byClass, setByClass] = useState<CrossAssetClass[]>([]);
  const [fatPitches, setFatPitches] = useState<CrossAssetOpp[]>([]);
  const [caDate, setCaDate] = useState<string | null>(null);
  const [caLoading, setCaLoading] = useState(true);

  // Narrative state
  const [narratives, setNarratives] = useState<NarrativeSignal[]>([]);
  const [selectedNarrative, setSelectedNarrative] = useState<string | null>(null);
  const [narLoading, setNarLoading] = useState(true);

  // IC state
  const [icRanking, setIcRanking] = useState<ModuleICRank[]>([]);
  const [icRegime, setIcRegime] = useState<ModuleIC[]>([]);
  const [icLoading, setIcLoading] = useState(true);

  // Filters
  const [assetClassFilter, setAssetClassFilter] = useState<string | null>(null);
  const [showFatOnly, setShowFatOnly] = useState(false);

  useEffect(() => {
    if (tab === 'cross-asset') {
      setCaLoading(true);
      Promise.all([
        api.crossAsset(100, 50),
        api.crossAssetByClass(),
        api.crossAssetFatPitches(),
      ]).then(([ca, bc, fp]) => {
        setCrossAsset(ca.opportunities);
        setCaDate(ca.date);
        setByClass(bc.breakdown);
        setFatPitches(fp.fat_pitches);
      }).catch(() => {}).finally(() => setCaLoading(false));
    }
  }, [tab]);

  useEffect(() => {
    if (tab === 'narratives') {
      setNarLoading(true);
      api.narratives(0).then(r => {
        setNarratives(r.narratives);
        if (r.narratives.length > 0) setSelectedNarrative(r.narratives[0].narrative);
      }).catch(() => {}).finally(() => setNarLoading(false));
    }
  }, [tab]);

  useEffect(() => {
    if (tab === 'ic') {
      setIcLoading(true);
      Promise.all([
        api.icRanking(),
        api.icRegimeComparison(20),
      ]).then(([rank, regime]) => {
        setIcRanking(rank.modules);
        setIcRegime(regime.data);
      }).catch(() => {}).finally(() => setIcLoading(false));
    }
  }, [tab]);

  const filteredOpps = useMemo(() => {
    let list = crossAsset;
    if (assetClassFilter) list = list.filter(o => o.asset_class === assetClassFilter);
    if (showFatOnly) list = list.filter(o => o.is_fat_pitch);
    return list;
  }, [crossAsset, assetClassFilter, showFatOnly]);

  const selectedNarrativeData = useMemo(
    () => narratives.find(n => n.narrative === selectedNarrative) ?? null,
    [narratives, selectedNarrative]
  );

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'cross-asset', label: 'Cross-Asset', icon: '◈' },
    { id: 'narratives', label: 'Narratives', icon: '◐' },
    { id: 'ic', label: 'Signal IC', icon: 'α' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-8 py-5">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold text-gray-900 tracking-tight">
              Alpha Intelligence
            </h1>
            <p className="text-[10px] text-gray-400 mt-0.5">
              Cross-asset discovery · Macro narratives · Module IC backtests
            </p>
          </div>
          {caDate && (
            <div className="text-[9px] text-gray-400 font-mono">{caDate}</div>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-4">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-[11px] font-medium transition-all ${
                tab === t.id
                  ? 'bg-emerald-600/10 text-emerald-600 border border-emerald-600/25'
                  : 'text-gray-500 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              <span>{t.icon}</span>
              <span>{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="px-8 py-6">
        {/* ── CROSS-ASSET TAB ── */}
        {tab === 'cross-asset' && (
          <div className="space-y-6">
            {caLoading ? (
              <div className="text-[11px] text-gray-400 text-center py-16">Loading opportunities...</div>
            ) : (
              <>
                {/* Summary stats */}
                <div className="grid grid-cols-4 gap-4">
                  <StatCard
                    label="Total Opportunities"
                    value={String(crossAsset.length)}
                    sub="score ≥ 50"
                  />
                  <StatCard
                    label="Fat Pitches"
                    value={String(fatPitches.length)}
                    sub="strong tech + fundamental"
                    color="#059669"
                  />
                  <StatCard
                    label="Asset Classes"
                    value={String(byClass.length)}
                    sub="with opportunities"
                  />
                  <StatCard
                    label="Top Score"
                    value={crossAsset.length > 0 ? crossAsset[0].opportunity_score.toFixed(1) : '—'}
                    sub={crossAsset[0]?.symbol}
                    color={crossAsset.length > 0 ? scoreColor(crossAsset[0].opportunity_score) : undefined}
                  />
                </div>

                <div className="grid grid-cols-3 gap-6">
                  {/* Asset class breakdown */}
                  <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                    <SectionHeader title="By Asset Class" subtitle="Average opportunity score" />
                    {byClass.length > 0 ? (
                      <AssetClassBar data={byClass} />
                    ) : (
                      <div className="text-[11px] text-gray-400 text-center py-6">No data yet</div>
                    )}
                  </div>

                  {/* Fat pitches */}
                  <div className="col-span-2 bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                    <SectionHeader
                      title="Fat Pitches"
                      subtitle="Strong fundamentals + technical breakout + regime fit"
                    />
                    {fatPitches.length === 0 ? (
                      <div className="text-[11px] text-gray-400 text-center py-6">
                        No fat pitches today — run pipeline to refresh
                      </div>
                    ) : (
                      <div className="grid grid-cols-3 gap-3">
                        {fatPitches.slice(0, 9).map(opp => (
                          <FatPitchCard key={opp.symbol} opp={opp} />
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Full opportunity list */}
                <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                  <div className="flex items-center justify-between mb-4">
                    <SectionHeader title="All Opportunities" />
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setShowFatOnly(!showFatOnly)}
                        className={`text-[10px] px-3 py-1 rounded-lg border transition-all ${
                          showFatOnly
                            ? 'bg-amber-50 border-amber-300 text-amber-700'
                            : 'border-gray-200 text-gray-500 hover:border-gray-300'
                        }`}
                      >
                        Fat pitches only
                      </button>
                      <select
                        value={assetClassFilter ?? ''}
                        onChange={e => setAssetClassFilter(e.target.value || null)}
                        className="text-[10px] border border-gray-200 rounded-lg px-2 py-1 text-gray-600"
                      >
                        <option value="">All classes</option>
                        {byClass.map(c => (
                          <option key={c.asset_class} value={c.asset_class}>
                            {ASSET_CLASS_LABELS[c.asset_class] ?? c.asset_class}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="border-b border-gray-100">
                        <th className="text-left py-2 text-gray-400 font-normal">Symbol</th>
                        <th className="text-left py-2 text-gray-400 font-normal">Class</th>
                        <th className="text-left py-2 text-gray-400 font-normal">Sector</th>
                        <th className="text-right py-2 text-gray-400 font-normal">Score</th>
                        <th className="text-right py-2 text-gray-400 font-normal">Tech</th>
                        <th className="text-right py-2 text-gray-400 font-normal">Fund</th>
                        <th className="text-right py-2 text-gray-400 font-normal">Mom 20d</th>
                        <th className="text-right py-2 text-gray-400 font-normal">Regime Fit</th>
                        <th className="text-left py-2 text-gray-400 font-normal">Conviction</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredOpps.slice(0, 50).map(opp => (
                        <tr
                          key={opp.symbol}
                          className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                        >
                          <td className="py-2 pr-3">
                            <a
                              href={`/asset/${opp.symbol}`}
                              className="font-semibold text-gray-900 hover:text-emerald-600 transition-colors"
                            >
                              {opp.symbol}
                            </a>
                            {opp.is_fat_pitch === 1 && (
                              <span className="ml-1 text-amber-500 text-[8px]">★</span>
                            )}
                          </td>
                          <td className="py-2 text-gray-400">
                            {ASSET_CLASS_LABELS[opp.asset_class] ?? opp.asset_class}
                          </td>
                          <td className="py-2 text-gray-400">{opp.sector ?? '—'}</td>
                          <td className="py-2 text-right font-mono font-bold" style={{ color: scoreColor(opp.opportunity_score) }}>
                            {opp.opportunity_score.toFixed(1)}
                          </td>
                          <td className="py-2 text-right text-gray-600">{fmt(opp.technical_score)}</td>
                          <td className="py-2 text-right text-gray-600">{fmt(opp.fundamental_score)}</td>
                          <td
                            className="py-2 text-right font-mono"
                            style={{ color: (opp.momentum_20d ?? 0) >= 0 ? '#059669' : '#e11d48' }}
                          >
                            {opp.momentum_20d != null
                              ? `${opp.momentum_20d >= 0 ? '+' : ''}${(opp.momentum_20d * 100).toFixed(1)}%`
                              : '—'}
                          </td>
                          <td className="py-2 text-right text-gray-600">{fmt(opp.regime_fit_score)}</td>
                          <td className="py-2">
                            <span
                              className="text-[9px] px-2 py-0.5 rounded-full"
                              style={{
                                backgroundColor:
                                  opp.conviction === 'HIGH' ? '#05966915' :
                                  opp.conviction === 'NOTABLE' ? '#d9770610' : '#9ca3af10',
                                color:
                                  opp.conviction === 'HIGH' ? '#059669' :
                                  opp.conviction === 'NOTABLE' ? '#d97706' : '#9ca3af',
                              }}
                            >
                              {opp.conviction ?? 'WATCH'}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {filteredOpps.length === 0 && (
                    <div className="text-[11px] text-gray-400 text-center py-8">
                      No opportunities match filters. Run the pipeline to populate data.
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* ── NARRATIVES TAB ── */}
        {tab === 'narratives' && (
          <div className="space-y-6">
            {narLoading ? (
              <div className="text-[11px] text-gray-400 text-center py-16">Loading narratives...</div>
            ) : narratives.length === 0 ? (
              <div className="bg-white border border-gray-100 rounded-xl p-8 text-center">
                <div className="text-2xl mb-2">◐</div>
                <div className="text-[12px] text-gray-500">No narrative data yet</div>
                <div className="text-[10px] text-gray-400 mt-1">Run the pipeline to compute narrative signals</div>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-6">
                {/* Narrative list */}
                <div className="space-y-2">
                  <SectionHeader
                    title="Macro Narratives"
                    subtitle="12 institutional themes — strength vs. crowding"
                  />
                  {narratives.map(sig => (
                    <NarrativeCard
                      key={sig.narrative}
                      sig={sig}
                      active={selectedNarrative === sig.narrative}
                      onClick={() => setSelectedNarrative(sig.narrative)}
                    />
                  ))}
                </div>

                {/* Narrative detail */}
                <div className="col-span-2">
                  {selectedNarrativeData ? (
                    <div className="space-y-4">
                      <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                        <div className="flex items-center gap-3 mb-4">
                          <span className="text-3xl">
                            {NARRATIVE_ICONS[selectedNarrativeData.narrative] ?? '◈'}
                          </span>
                          <div>
                            <h3 className="text-sm font-semibold text-gray-900 capitalize">
                              {selectedNarrativeData.narrative.replace(/_/g, ' ')}
                            </h3>
                            <div className="text-[9px] text-gray-400 mt-0.5">
                              Strength: <span className="font-mono" style={{ color: scoreColor(selectedNarrativeData.strength_score * 100) }}>
                                {(selectedNarrativeData.strength_score * 100).toFixed(1)}
                              </span>
                              {' · '}
                              Crowding: <span className="font-mono text-gray-600">
                                {pct(selectedNarrativeData.crowding_score)}
                              </span>
                            </div>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          {selectedNarrativeData.best_expressions && (
                            <div>
                              <div className="text-[9px] text-emerald-600 font-semibold tracking-wider uppercase mb-2">
                                Best Expressions
                              </div>
                              <div className="flex flex-wrap gap-1.5">
                                {(() => {
                                  try {
                                    const arr = JSON.parse(selectedNarrativeData.best_expressions);
                                    return arr.map((s: string) => (
                                      <a
                                        key={s}
                                        href={`/asset/${s}`}
                                        className="text-[10px] px-2 py-0.5 bg-emerald-50 text-emerald-700 rounded-lg border border-emerald-100 hover:bg-emerald-100 transition-colors font-mono"
                                      >
                                        {s}
                                      </a>
                                    ));
                                  } catch {
                                    return <span className="text-[10px] text-gray-500">{selectedNarrativeData.best_expressions}</span>;
                                  }
                                })()}
                              </div>
                            </div>
                          )}
                          {selectedNarrativeData.worst_expressions && (
                            <div>
                              <div className="text-[9px] text-red-500 font-semibold tracking-wider uppercase mb-2">
                                Worst Expressions (Short/Avoid)
                              </div>
                              <div className="flex flex-wrap gap-1.5">
                                {(() => {
                                  try {
                                    const arr = JSON.parse(selectedNarrativeData.worst_expressions);
                                    return arr.map((s: string) => (
                                      <span
                                        key={s}
                                        className="text-[10px] px-2 py-0.5 bg-red-50 text-red-600 rounded-lg border border-red-100 font-mono"
                                      >
                                        {s}
                                      </span>
                                    ));
                                  } catch {
                                    return <span className="text-[10px] text-gray-500">{selectedNarrativeData.worst_expressions}</span>;
                                  }
                                })()}
                              </div>
                            </div>
                          )}
                        </div>

                        {selectedNarrativeData.details && (() => {
                          try {
                            const d = JSON.parse(selectedNarrativeData.details);
                            return (
                              <div className="mt-4 text-[10px] text-gray-500 leading-relaxed border-t border-gray-100 pt-3">
                                {d.description ?? d.summary ?? ''}
                              </div>
                            );
                          } catch {
                            return null;
                          }
                        })()}
                      </div>
                    </div>
                  ) : (
                    <div className="bg-white border border-gray-100 rounded-xl p-8 text-center text-gray-400 text-[11px]">
                      Select a narrative
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── SIGNAL IC TAB ── */}
        {tab === 'ic' && (
          <div className="space-y-6">
            {icLoading ? (
              <div className="text-[11px] text-gray-400 text-center py-16">Loading IC data...</div>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-6">
                  {/* Module leaderboard */}
                  <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                    <SectionHeader
                      title="Module IC Leaderboard"
                      subtitle="Spearman IC averaged across 5d / 10d / 20d horizons, all regimes"
                    />
                    {icRanking.length === 0 ? (
                      <div className="text-[11px] text-gray-400 text-center py-8">
                        IC data accumulates over time as pipeline runs daily.
                        <br />
                        <span className="text-[9px] text-gray-300 mt-1 block">
                          Needs ~10 days of data minimum.
                        </span>
                      </div>
                    ) : (
                      <ICLeaderboard modules={icRanking} />
                    )}
                  </div>

                  {/* IC legend */}
                  <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                    <SectionHeader title="How to Read IC" subtitle="Information Coefficient interpretation" />
                    <div className="space-y-3 text-[10px] text-gray-600">
                      <div className="flex items-start gap-3">
                        <span className="font-mono text-emerald-600 w-12 shrink-0">IC > 0.05</span>
                        <span>Excellent — rare, indicative of real alpha. Equivalent to professional quant funds.</span>
                      </div>
                      <div className="flex items-start gap-3">
                        <span className="font-mono text-green-500 w-12 shrink-0">0.02–0.05</span>
                        <span>Good — statistically meaningful edge. Worth weighting in convergence.</span>
                      </div>
                      <div className="flex items-start gap-3">
                        <span className="font-mono text-amber-600 w-12 shrink-0">0–0.02</span>
                        <span>Marginal — some predictive power. Use with other signals.</span>
                      </div>
                      <div className="flex items-start gap-3">
                        <span className="font-mono text-red-500 w-12 shrink-0">IC &lt; 0</span>
                        <span>Negative — counter-predictive. Reduce or invert weighting.</span>
                      </div>
                      <div className="mt-3 pt-3 border-t border-gray-100 text-[9px] text-gray-400">
                        <strong>IR (Information Ratio)</strong> = mean IC / std IC. IR &gt; 0.5 is good, IR &gt; 1.0 is excellent.
                        A module can have low mean IC but high IR if it's consistent.
                      </div>
                    </div>
                  </div>
                </div>

                {/* Regime × Horizon heatmap */}
                <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm">
                  <SectionHeader
                    title="IC Heatmap — Regime × Horizon"
                    subtitle="20d Spearman IC by module, regime, and forward horizon"
                  />
                  <ICHeatmap data={icRegime} />
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
