'use client';

import { useEffect, useState, useMemo } from 'react';
import {
  api,
  type PatternScanResult,
  type SectorRotationPoint,
  type OptionsIntelResult,
  type UnusualActivityRow,
  type ExpectedMoveRow,
  type CompressionRow,
  type DealerExposureRow,
  type PatternLayerDetail,
} from '@/lib/api';

type Tab = 'scanner' | 'rotation' | 'options' | 'cycles';

const QUADRANT_COLORS: Record<string, string> = {
  leading: 'text-terminal-green',
  weakening: 'text-amber-400',
  lagging: 'text-red-400',
  improving: 'text-cyan-400',
  neutral: 'text-terminal-dim',
};

const QUADRANT_BG: Record<string, string> = {
  leading: 'bg-terminal-green/10 border-terminal-green/30',
  weakening: 'bg-amber-400/10 border-amber-400/30',
  lagging: 'bg-red-400/10 border-red-400/30',
  improving: 'bg-cyan-400/10 border-cyan-400/30',
  neutral: 'bg-white/5 border-white/10',
};

const WYCKOFF_COLORS: Record<string, string> = {
  accumulation: 'text-terminal-green',
  markup: 'text-cyan-400',
  distribution: 'text-amber-400',
  markdown: 'text-red-400',
  unknown: 'text-terminal-dim',
};

const DEALER_COLORS: Record<string, string> = {
  pinning: 'text-amber-400',
  amplifying: 'text-red-400',
  neutral: 'text-terminal-dim',
};

function ScorePill({ value, max = 100 }: { value: number | null; max?: number }) {
  if (value == null) return <span className="text-terminal-dim">--</span>;
  const pct = value / max;
  const color =
    pct >= 0.7 ? 'text-terminal-green' : pct >= 0.5 ? 'text-amber-400' : 'text-red-400';
  return <span className={`font-mono text-xs ${color}`}>{value.toFixed(0)}</span>;
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span
      className={`text-[9px] font-mono tracking-wider px-1.5 py-0.5 rounded border ${color}`}
    >
      {text.toUpperCase()}
    </span>
  );
}

export default function PatternsPage() {
  const [tab, setTab] = useState<Tab>('scanner');
  const [patterns, setPatterns] = useState<PatternScanResult[]>([]);
  const [rotation, setRotation] = useState<SectorRotationPoint[]>([]);
  const [options, setOptions] = useState<OptionsIntelResult[]>([]);
  const [unusual, setUnusual] = useState<UnusualActivityRow[]>([]);
  const [expectedMoves, setExpectedMoves] = useState<ExpectedMoveRow[]>([]);
  const [compression, setCompression] = useState<CompressionRow[]>([]);
  const [dealers, setDealers] = useState<DealerExposureRow[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [sectorFilter, setSectorFilter] = useState('');
  const [phaseFilter, setPhaseFilter] = useState('');
  const [squeezeOnly, setSqueezeOnly] = useState(false);

  // Layer toggles
  const [layers, setLayers] = useState({
    regime: true,
    rotation: true,
    patterns: true,
    statistics: true,
    options: true,
  });

  // Detail expansion
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [detail, setDetail] = useState<PatternLayerDetail | null>(null);

  useEffect(() => {
    Promise.all([
      api.patterns(0).catch(() => []),
      api.sectorRotation(30).catch(() => []),
      api.optionsIntel(0).catch(() => []),
      api.unusualActivity(1).catch(() => []),
      api.expectedMoves().catch(() => []),
      api.compressionSetups().catch(() => []),
      api.dealerExposure().catch(() => []),
    ]).then(([p, r, o, u, em, c, d]) => {
      setPatterns(p);
      setRotation(r);
      setOptions(o);
      setUnusual(u);
      setExpectedMoves(em);
      setCompression(c);
      setDealers(d);
      setLoading(false);
    });
  }, []);

  const sectors = useMemo(
    () => Array.from(new Set(patterns.map((p) => p.sector).filter(Boolean))).sort() as string[],
    [patterns]
  );

  const filteredPatterns = useMemo(() => {
    let data = patterns;
    if (sectorFilter) data = data.filter((p) => p.sector === sectorFilter);
    if (phaseFilter) data = data.filter((p) => p.wyckoff_phase === phaseFilter);
    if (squeezeOnly) data = data.filter((p) => p.squeeze_active);
    return data;
  }, [patterns, sectorFilter, phaseFilter, squeezeOnly]);

  // Latest rotation per sector (for RRG)
  const latestRotation = useMemo(() => {
    const map: Record<string, SectorRotationPoint> = {};
    rotation.forEach((r) => {
      if (!map[r.sector] || r.date > map[r.sector].date) {
        map[r.sector] = r;
      }
    });
    return Object.values(map);
  }, [rotation]);

  // Summary stats
  const totalSetups = patterns.filter((p) => (p.pattern_options_score ?? p.pattern_scan_score) > 50).length;
  const activeSqueeze = patterns.filter((p) => p.squeeze_active).length;
  const unusualCount = unusual.length;
  const leadingSectors = latestRotation.filter((r) => r.quadrant === 'leading').length;

  const loadDetail = async (sym: string) => {
    if (expandedSymbol === sym) {
      setExpandedSymbol(null);
      return;
    }
    setExpandedSymbol(sym);
    try {
      const d = await api.patternLayers(sym);
      setDetail(d);
    } catch {
      setDetail(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          SCANNING PATTERNS & OPTIONS FLOW...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          PATTERN MATCH & OPTIONS INTELLIGENCE
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          5-LAYER CASCADE: REGIME {'>'} ROTATION {'>'} PATTERNS {'>'} STATISTICS {'>'} DERIVATIVES
        </p>
      </div>

      {/* Layer Toggle Bar */}
      <div className="flex items-center gap-4 p-3 bg-terminal-panel border border-terminal-border rounded">
        <span className="text-[10px] text-terminal-dim tracking-widest">LAYERS:</span>
        {Object.entries(layers).map(([key, active]) => (
          <button
            key={key}
            onClick={() => setLayers((prev) => ({ ...prev, [key]: !prev[key as keyof typeof prev] }))}
            className={`text-[10px] tracking-widest px-2 py-1 rounded border transition-all ${
              active
                ? 'text-terminal-green border-terminal-green/40 bg-terminal-green/10'
                : 'text-terminal-dim border-terminal-border hover:text-terminal-text'
            }`}
          >
            {key.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'SETUPS (>50)', value: totalSetups, color: 'text-terminal-green' },
          { label: 'ACTIVE SQUEEZES', value: activeSqueeze, color: 'text-cyan-400' },
          { label: 'UNUSUAL OPTIONS', value: unusualCount, color: 'text-amber-400' },
          { label: 'LEADING SECTORS', value: leadingSectors, color: 'text-terminal-green' },
        ].map((card) => (
          <div key={card.label} className="bg-terminal-panel border border-terminal-border rounded p-3">
            <div className={`font-mono text-2xl font-bold ${card.color}`}>{card.value}</div>
            <div className="text-[9px] text-terminal-dim tracking-widest mt-1">{card.label}</div>
          </div>
        ))}
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-terminal-border">
        {(['scanner', 'rotation', 'options', 'cycles'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-xs tracking-widest transition-all border-b-2 ${
              tab === t
                ? 'text-terminal-green border-terminal-green'
                : 'text-terminal-dim border-transparent hover:text-terminal-text'
            }`}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === 'scanner' && (
        <ScannerTab
          patterns={filteredPatterns}
          sectors={sectors}
          sectorFilter={sectorFilter}
          setSectorFilter={setSectorFilter}
          phaseFilter={phaseFilter}
          setPhaseFilter={setPhaseFilter}
          squeezeOnly={squeezeOnly}
          setSqueezeOnly={setSqueezeOnly}
          expandedSymbol={expandedSymbol}
          detail={detail}
          onExpand={loadDetail}
          layers={layers}
        />
      )}

      {tab === 'rotation' && <RotationTab rotation={rotation} latest={latestRotation} />}

      {tab === 'options' && (
        <OptionsTab
          options={options}
          unusual={unusual}
          expectedMoves={expectedMoves}
          dealers={dealers}
        />
      )}

      {tab === 'cycles' && <CyclesTab patterns={patterns} compression={compression} />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 1: SCANNER
// ═══════════════════════════════════════════════════════════════════════════

function ScannerTab({
  patterns,
  sectors,
  sectorFilter,
  setSectorFilter,
  phaseFilter,
  setPhaseFilter,
  squeezeOnly,
  setSqueezeOnly,
  expandedSymbol,
  detail,
  onExpand,
  layers,
}: {
  patterns: PatternScanResult[];
  sectors: string[];
  sectorFilter: string;
  setSectorFilter: (s: string) => void;
  phaseFilter: string;
  setPhaseFilter: (s: string) => void;
  squeezeOnly: boolean;
  setSqueezeOnly: (b: boolean) => void;
  expandedSymbol: string | null;
  detail: PatternLayerDetail | null;
  onExpand: (sym: string) => void;
  layers: Record<string, boolean>;
}) {
  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={sectorFilter}
          onChange={(e) => setSectorFilter(e.target.value)}
          className="bg-terminal-bg border border-terminal-border text-terminal-text text-xs p-1.5 rounded"
        >
          <option value="">ALL SECTORS</option>
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <select
          value={phaseFilter}
          onChange={(e) => setPhaseFilter(e.target.value)}
          className="bg-terminal-bg border border-terminal-border text-terminal-text text-xs p-1.5 rounded"
        >
          <option value="">ALL PHASES</option>
          {['accumulation', 'markup', 'distribution', 'markdown'].map((p) => (
            <option key={p} value={p}>{p.toUpperCase()}</option>
          ))}
        </select>

        <button
          onClick={() => setSqueezeOnly(!squeezeOnly)}
          className={`text-[10px] tracking-widest px-2 py-1 rounded border transition-all ${
            squeezeOnly
              ? 'text-cyan-400 border-cyan-400/40 bg-cyan-400/10'
              : 'text-terminal-dim border-terminal-border'
          }`}
        >
          SQUEEZE ONLY
        </button>

        <span className="text-[10px] text-terminal-dim ml-auto">
          {patterns.length} SYMBOLS
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-terminal-border text-terminal-dim text-[10px] tracking-widest">
              <th className="text-left p-2">SYMBOL</th>
              <th className="text-left p-2">SECTOR</th>
              {layers.rotation && <th className="text-right p-2">RRG</th>}
              {layers.patterns && <th className="text-right p-2">PATTERN</th>}
              {layers.statistics && <th className="text-right p-2">STATS</th>}
              <th className="text-right p-2">SCAN</th>
              {layers.options && <th className="text-right p-2">OPTIONS</th>}
              <th className="text-right p-2">FINAL</th>
              <th className="text-center p-2">PHASE</th>
              <th className="text-center p-2">SQ</th>
            </tr>
          </thead>
          <tbody>
            {patterns.slice(0, 100).map((p) => {
              const layerScores = p.layer_scores ? JSON.parse(p.layer_scores) : {};
              const isExpanded = expandedSymbol === p.symbol;
              return (
                <>
                  <tr
                    key={p.symbol}
                    onClick={() => onExpand(p.symbol)}
                    className={`border-b border-terminal-border/50 cursor-pointer transition-colors
                      ${isExpanded ? 'bg-terminal-green/5' : 'hover:bg-white/[0.02]'}`}
                  >
                    <td className="p-2 font-mono text-terminal-bright">{p.symbol}</td>
                    <td className="p-2 text-terminal-dim">{p.sector || '--'}</td>
                    {layers.rotation && (
                      <td className="p-2 text-right">
                        <Badge text={p.sector_quadrant || 'n/a'} color={QUADRANT_BG[p.sector_quadrant] || QUADRANT_BG.neutral} />
                      </td>
                    )}
                    {layers.patterns && (
                      <td className="p-2 text-right">
                        <ScorePill value={layerScores.L3_technical} />
                      </td>
                    )}
                    {layers.statistics && (
                      <td className="p-2 text-right">
                        <ScorePill value={layerScores.L4_statistical} />
                      </td>
                    )}
                    <td className="p-2 text-right">
                      <ScorePill value={p.pattern_scan_score} />
                    </td>
                    {layers.options && (
                      <td className="p-2 text-right">
                        <ScorePill value={p.options_score} />
                      </td>
                    )}
                    <td className="p-2 text-right font-bold">
                      <ScorePill value={p.pattern_options_score ?? p.pattern_scan_score} />
                    </td>
                    <td className="p-2 text-center">
                      <span className={`text-[10px] ${WYCKOFF_COLORS[p.wyckoff_phase] || 'text-terminal-dim'}`}>
                        {p.wyckoff_phase?.toUpperCase() || '--'}
                      </span>
                    </td>
                    <td className="p-2 text-center">
                      {p.squeeze_active ? (
                        <span className="text-cyan-400 animate-pulse">SQ</span>
                      ) : (
                        <span className="text-terminal-dim">--</span>
                      )}
                    </td>
                  </tr>
                  {isExpanded && detail && (
                    <tr key={`${p.symbol}-detail`}>
                      <td colSpan={10} className="p-4 bg-terminal-panel/50">
                        <DetailPanel detail={detail} />
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// DETAIL PANEL (expandable row)
// ═══════════════════════════════════════════════════════════════════════════

function DetailPanel({ detail }: { detail: PatternLayerDetail }) {
  const scan = detail.scan;
  const opt = detail.options;

  if (!scan) return <div className="text-terminal-dim">No data</div>;

  const layerScores = scan.layer_scores ? JSON.parse(scan.layer_scores) : {};
  const detectedPatterns = scan.patterns_detected ? JSON.parse(scan.patterns_detected) : [];

  return (
    <div className="grid grid-cols-5 gap-4 text-[10px]">
      {/* L1: Regime */}
      <div>
        <div className="text-terminal-dim tracking-widest mb-2">L1: REGIME</div>
        <div className="space-y-1">
          <div>Regime: <span className="text-terminal-bright">{scan.regime}</span></div>
          <div>Score: <ScorePill value={layerScores.L1_regime} /></div>
          <div>VIX Pctl: {scan.vix_percentile?.toFixed(0)}%</div>
        </div>
      </div>

      {/* L2: Rotation */}
      <div>
        <div className="text-terminal-dim tracking-widest mb-2">L2: ROTATION</div>
        <div className="space-y-1">
          <div>
            Quadrant:{' '}
            <span className={QUADRANT_COLORS[scan.sector_quadrant] || ''}>
              {scan.sector_quadrant?.toUpperCase()}
            </span>
          </div>
          <div>RS-Ratio: {scan.rs_ratio?.toFixed(3)}</div>
          <div>RS-Mom: {scan.rs_momentum?.toFixed(3)}</div>
          <div>Score: <ScorePill value={layerScores.L2_rotation} /></div>
        </div>
      </div>

      {/* L3: Technical */}
      <div>
        <div className="text-terminal-dim tracking-widest mb-2">L3: TECHNICAL</div>
        <div className="space-y-1">
          {detectedPatterns.length > 0 ? (
            detectedPatterns.map((p: any, i: number) => (
              <div key={i}>
                <Badge
                  text={p.pattern}
                  color={p.direction === 'bullish' ? QUADRANT_BG.leading : QUADRANT_BG.lagging}
                />
                <span className="ml-1 text-terminal-dim">{(p.confidence * 100).toFixed(0)}%</span>
              </div>
            ))
          ) : (
            <div className="text-terminal-dim">No patterns</div>
          )}
          <div>S/R: {scan.sr_proximity}</div>
          <div>Vol Profile: <ScorePill value={scan.volume_profile_score} /></div>
        </div>
      </div>

      {/* L4: Statistics */}
      <div>
        <div className="text-terminal-dim tracking-widest mb-2">L4: STATISTICS</div>
        <div className="space-y-1">
          <div>Hurst: <span className="text-terminal-bright">{scan.hurst_exponent?.toFixed(3)}</span>
            <span className="text-terminal-dim ml-1">
              ({scan.hurst_exponent < 0.45 ? 'MR' : scan.hurst_exponent > 0.55 ? 'TREND' : 'WALK'})
            </span>
          </div>
          <div>MR Score: <ScorePill value={scan.mr_score} /></div>
          <div>Mom Score: <ScorePill value={scan.momentum_score} /></div>
          <div>Compress: <ScorePill value={scan.compression_score} /></div>
          {scan.squeeze_active ? (
            <div className="text-cyan-400 animate-pulse">SQUEEZE ACTIVE</div>
          ) : null}
        </div>
      </div>

      {/* L5: Options */}
      <div>
        <div className="text-terminal-dim tracking-widest mb-2">L5: OPTIONS</div>
        {opt ? (
          <div className="space-y-1">
            <div>IV Rank: <ScorePill value={opt.iv_rank} /></div>
            <div>Exp Move: <span className="text-amber-400">
              {opt.expected_move_pct ? `\u00B1${opt.expected_move_pct.toFixed(1)}%` : '--'}
            </span></div>
            <div>P/C: {opt.volume_pc_ratio?.toFixed(2) || '--'}</div>
            <div>
              GEX:{' '}
              <span className={DEALER_COLORS[opt.dealer_regime || 'neutral']}>
                {opt.dealer_regime?.toUpperCase() || '--'}
              </span>
            </div>
            {opt.unusual_activity_count > 0 && (
              <div className="text-amber-400">
                {opt.unusual_activity_count} UNUSUAL FLOW
              </div>
            )}
            <div>Max Pain: ${opt.max_pain?.toFixed(0) || '--'}</div>
          </div>
        ) : (
          <div className="text-terminal-dim">Below options gate</div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 2: ROTATION (RRG)
// ═══════════════════════════════════════════════════════════════════════════

function RotationTab({
  rotation,
  latest,
}: {
  rotation: SectorRotationPoint[];
  latest: SectorRotationPoint[];
}) {
  // Group rotation history by sector for trails
  const trailsBySector = useMemo(() => {
    const map: Record<string, SectorRotationPoint[]> = {};
    rotation.forEach((r) => {
      if (!map[r.sector]) map[r.sector] = [];
      map[r.sector].push(r);
    });
    // Sort each trail by date
    Object.values(map).forEach((arr) => arr.sort((a, b) => a.date.localeCompare(b.date)));
    return map;
  }, [rotation]);

  return (
    <div className="space-y-4">
      {/* RRG Scatter Plot */}
      <div className="bg-terminal-panel border border-terminal-border rounded p-4">
        <div className="text-[10px] text-terminal-dim tracking-widest mb-3">
          RELATIVE ROTATION GRAPH (RRG) — 4 QUADRANTS
        </div>
        <div className="relative w-full" style={{ height: 400 }}>
          {/* Quadrant labels */}
          <div className="absolute top-2 right-2 text-[9px] text-terminal-green tracking-widest">LEADING</div>
          <div className="absolute top-2 left-2 text-[9px] text-cyan-400 tracking-widest">IMPROVING</div>
          <div className="absolute bottom-2 left-2 text-[9px] text-red-400 tracking-widest">LAGGING</div>
          <div className="absolute bottom-2 right-2 text-[9px] text-amber-400 tracking-widest">WEAKENING</div>

          {/* Axes */}
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-terminal-border" />
          <div className="absolute top-1/2 left-0 right-0 h-px bg-terminal-border" />

          {/* Sector dots */}
          {latest.map((r) => {
            // Map rs_ratio (-3..3) to x (5%..95%), rs_momentum (-3..3) to y (95%..5%)
            const x = Math.max(5, Math.min(95, 50 + r.rs_ratio * 15));
            const y = Math.max(5, Math.min(95, 50 - r.rs_momentum * 15));
            const color = QUADRANT_COLORS[r.quadrant] || 'text-terminal-dim';

            return (
              <div
                key={r.sector}
                className={`absolute ${color} font-mono text-[10px] font-bold`}
                style={{ left: `${x}%`, top: `${y}%`, transform: 'translate(-50%, -50%)' }}
                title={`${r.sector}: RS=${r.rs_ratio.toFixed(2)}, Mom=${r.rs_momentum.toFixed(2)}`}
              >
                {r.sector.substring(0, 6).toUpperCase()}
              </div>
            );
          })}
        </div>

        {/* Axis labels */}
        <div className="flex justify-between text-[9px] text-terminal-dim mt-1">
          <span>{'<'} RS-RATIO {'>'}</span>
          <span>{'<'} RS-MOMENTUM {'>'}</span>
        </div>
      </div>

      {/* Sector Table */}
      <div className="bg-terminal-panel border border-terminal-border rounded overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-terminal-border text-terminal-dim text-[10px] tracking-widest">
              <th className="text-left p-3">SECTOR</th>
              <th className="text-center p-3">QUADRANT</th>
              <th className="text-right p-3">RS-RATIO</th>
              <th className="text-right p-3">RS-MOMENTUM</th>
              <th className="text-right p-3">ROTATION SCORE</th>
            </tr>
          </thead>
          <tbody>
            {latest
              .sort((a, b) => b.rotation_score - a.rotation_score)
              .map((r) => (
                <tr key={r.sector} className="border-b border-terminal-border/50 hover:bg-white/[0.02]">
                  <td className="p-3 font-mono text-terminal-bright">{r.sector}</td>
                  <td className="p-3 text-center">
                    <Badge text={r.quadrant} color={QUADRANT_BG[r.quadrant]} />
                  </td>
                  <td className="p-3 text-right font-mono">{r.rs_ratio.toFixed(3)}</td>
                  <td className="p-3 text-right font-mono">{r.rs_momentum.toFixed(3)}</td>
                  <td className="p-3 text-right">
                    <ScorePill value={r.rotation_score} />
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 3: OPTIONS
// ═══════════════════════════════════════════════════════════════════════════

function OptionsTab({
  options,
  unusual,
  expectedMoves,
  dealers,
}: {
  options: OptionsIntelResult[];
  unusual: UnusualActivityRow[];
  expectedMoves: ExpectedMoveRow[];
  dealers: DealerExposureRow[];
}) {
  const [subTab, setSubTab] = useState<'moves' | 'unusual' | 'dealer' | 'iv'>('moves');

  return (
    <div className="space-y-4">
      {/* Sub-tabs */}
      <div className="flex gap-2">
        {(['moves', 'unusual', 'dealer', 'iv'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setSubTab(t)}
            className={`text-[10px] tracking-widest px-3 py-1.5 rounded border transition-all ${
              subTab === t
                ? 'text-terminal-green border-terminal-green/40 bg-terminal-green/10'
                : 'text-terminal-dim border-terminal-border hover:text-terminal-text'
            }`}
          >
            {t === 'moves' ? 'EXPECTED MOVES' : t === 'unusual' ? 'UNUSUAL FLOW' : t === 'dealer' ? 'DEALER GEX' : 'IV RANK'}
          </button>
        ))}
      </div>

      {/* Expected Moves */}
      {subTab === 'moves' && (
        <div className="bg-terminal-panel border border-terminal-border rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim text-[10px] tracking-widest">
                <th className="text-left p-3">SYMBOL</th>
                <th className="text-left p-3">SECTOR</th>
                <th className="text-right p-3">EXP MOVE %</th>
                <th className="text-right p-3">STRADDLE</th>
                <th className="text-right p-3">ATM IV</th>
                <th className="text-right p-3">IV RANK</th>
                <th className="text-center p-3">DEALER</th>
                <th className="text-center p-3">PHASE</th>
                <th className="text-center p-3">SQ</th>
              </tr>
            </thead>
            <tbody>
              {expectedMoves.slice(0, 50).map((m) => (
                <tr key={m.symbol} className="border-b border-terminal-border/50 hover:bg-white/[0.02]">
                  <td className="p-3 font-mono text-terminal-bright">{m.symbol}</td>
                  <td className="p-3 text-terminal-dim">{m.sector || '--'}</td>
                  <td className="p-3 text-right font-mono text-amber-400">
                    {'\u00B1'}{m.expected_move_pct?.toFixed(1)}%
                  </td>
                  <td className="p-3 text-right font-mono">${m.straddle_cost?.toFixed(2)}</td>
                  <td className="p-3 text-right font-mono">{(m.atm_iv ? m.atm_iv * 100 : 0).toFixed(0)}%</td>
                  <td className="p-3 text-right"><ScorePill value={m.iv_rank} /></td>
                  <td className="p-3 text-center">
                    <span className={DEALER_COLORS[m.dealer_regime || 'neutral']}>
                      {m.dealer_regime?.toUpperCase() || '--'}
                    </span>
                  </td>
                  <td className="p-3 text-center">
                    <span className={WYCKOFF_COLORS[m.wyckoff_phase || 'unknown']}>
                      {m.wyckoff_phase?.substring(0, 5).toUpperCase() || '--'}
                    </span>
                  </td>
                  <td className="p-3 text-center">
                    {m.squeeze_active ? <span className="text-cyan-400">SQ</span> : '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Unusual Activity */}
      {subTab === 'unusual' && (
        <div className="bg-terminal-panel border border-terminal-border rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim text-[10px] tracking-widest">
                <th className="text-left p-3">SYMBOL</th>
                <th className="text-left p-3">SECTOR</th>
                <th className="text-right p-3"># SIGNALS</th>
                <th className="text-center p-3">DIRECTION</th>
                <th className="text-right p-3">IV RANK</th>
                <th className="text-right p-3">EXP MOVE</th>
                <th className="text-center p-3">DEALER</th>
                <th className="text-right p-3">OPT SCORE</th>
              </tr>
            </thead>
            <tbody>
              {unusual.map((u) => (
                <tr key={u.symbol} className="border-b border-terminal-border/50 hover:bg-white/[0.02]">
                  <td className="p-3 font-mono text-terminal-bright">{u.symbol}</td>
                  <td className="p-3 text-terminal-dim">{u.sector || '--'}</td>
                  <td className="p-3 text-right font-mono text-amber-400">{u.unusual_activity_count}</td>
                  <td className="p-3 text-center">
                    <Badge
                      text={u.unusual_direction_bias || 'mixed'}
                      color={
                        u.unusual_direction_bias === 'bullish'
                          ? QUADRANT_BG.leading
                          : u.unusual_direction_bias === 'bearish'
                          ? QUADRANT_BG.lagging
                          : QUADRANT_BG.neutral
                      }
                    />
                  </td>
                  <td className="p-3 text-right"><ScorePill value={u.iv_rank} /></td>
                  <td className="p-3 text-right font-mono">
                    {u.expected_move_pct ? `\u00B1${u.expected_move_pct.toFixed(1)}%` : '--'}
                  </td>
                  <td className="p-3 text-center">
                    <span className={DEALER_COLORS[u.dealer_regime || 'neutral']}>
                      {u.dealer_regime?.toUpperCase() || '--'}
                    </span>
                  </td>
                  <td className="p-3 text-right"><ScorePill value={u.options_score} /></td>
                </tr>
              ))}
              {unusual.length === 0 && (
                <tr>
                  <td colSpan={8} className="p-4 text-center text-terminal-dim">
                    No unusual options activity detected
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Dealer Exposure */}
      {subTab === 'dealer' && (
        <div className="bg-terminal-panel border border-terminal-border rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim text-[10px] tracking-widest">
                <th className="text-left p-3">SYMBOL</th>
                <th className="text-center p-3">REGIME</th>
                <th className="text-right p-3">NET GEX ($)</th>
                <th className="text-right p-3">GAMMA FLIP</th>
                <th className="text-right p-3">MAX PAIN</th>
                <th className="text-right p-3">PUT WALL</th>
                <th className="text-right p-3">CALL WALL</th>
                <th className="text-right p-3">OPT SCORE</th>
              </tr>
            </thead>
            <tbody>
              {dealers.slice(0, 50).map((d) => (
                <tr key={d.symbol} className="border-b border-terminal-border/50 hover:bg-white/[0.02]">
                  <td className="p-3 font-mono text-terminal-bright">{d.symbol}</td>
                  <td className="p-3 text-center">
                    <Badge
                      text={d.dealer_regime}
                      color={
                        d.dealer_regime === 'amplifying'
                          ? QUADRANT_BG.lagging
                          : d.dealer_regime === 'pinning'
                          ? QUADRANT_BG.weakening
                          : QUADRANT_BG.neutral
                      }
                    />
                  </td>
                  <td className="p-3 text-right font-mono">
                    {d.net_gex ? (d.net_gex > 0 ? '+' : '') + (d.net_gex / 1e6).toFixed(1) + 'M' : '--'}
                  </td>
                  <td className="p-3 text-right font-mono">${d.gamma_flip_level?.toFixed(0) || '--'}</td>
                  <td className="p-3 text-right font-mono">${d.max_pain?.toFixed(0) || '--'}</td>
                  <td className="p-3 text-right font-mono text-red-400">${d.put_wall?.toFixed(0) || '--'}</td>
                  <td className="p-3 text-right font-mono text-terminal-green">${d.call_wall?.toFixed(0) || '--'}</td>
                  <td className="p-3 text-right"><ScorePill value={d.options_score} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* IV Rank Heatmap */}
      {subTab === 'iv' && (
        <div className="space-y-3">
          <div className="text-[10px] text-terminal-dim tracking-widest">
            IV RANK HEATMAP — GREEN = LOW IV (CHEAP OPTIONS) | RED = HIGH IV (EXPENSIVE)
          </div>
          <div className="flex flex-wrap gap-1">
            {options
              .filter((o) => o.iv_rank != null)
              .sort((a, b) => (b.iv_rank || 0) - (a.iv_rank || 0))
              .map((o) => {
                const rank = o.iv_rank || 0;
                const bg =
                  rank > 80
                    ? 'bg-red-500/30 border-red-500/50'
                    : rank > 60
                    ? 'bg-amber-500/20 border-amber-500/40'
                    : rank > 40
                    ? 'bg-white/5 border-white/20'
                    : rank > 20
                    ? 'bg-cyan-500/15 border-cyan-500/30'
                    : 'bg-terminal-green/20 border-terminal-green/40';

                return (
                  <div
                    key={o.symbol}
                    className={`px-2 py-1 rounded border text-[9px] font-mono ${bg}`}
                    title={`${o.symbol}: IV Rank ${rank.toFixed(0)}, IV ${((o.atm_iv || 0) * 100).toFixed(0)}%`}
                  >
                    <div className="text-terminal-bright">{o.symbol}</div>
                    <div className="text-terminal-dim">{rank.toFixed(0)}</div>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// TAB 4: CYCLES
// ═══════════════════════════════════════════════════════════════════════════

function CyclesTab({
  patterns,
  compression,
}: {
  patterns: PatternScanResult[];
  compression: CompressionRow[];
}) {
  // Phase distribution
  const phaseCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    patterns.forEach((p) => {
      const phase = p.wyckoff_phase || 'unknown';
      counts[phase] = (counts[phase] || 0) + 1;
    });
    return counts;
  }, [patterns]);

  const total = patterns.length || 1;

  // Vol regime distribution
  const volCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    patterns.forEach((p) => {
      const regime = p.vol_regime || 'normal';
      counts[regime] = (counts[regime] || 0) + 1;
    });
    return counts;
  }, [patterns]);

  // Earnings proximity
  const nearEarnings = patterns
    .filter((p) => p.earnings_days_to_next != null && p.earnings_days_to_next <= 14)
    .sort((a, b) => (a.earnings_days_to_next || 99) - (b.earnings_days_to_next || 99));

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        {/* Wyckoff Phase Distribution */}
        <div className="bg-terminal-panel border border-terminal-border rounded p-4">
          <div className="text-[10px] text-terminal-dim tracking-widest mb-3">
            WYCKOFF PHASE DISTRIBUTION
          </div>
          <div className="space-y-2">
            {['accumulation', 'markup', 'distribution', 'markdown'].map((phase) => {
              const count = phaseCounts[phase] || 0;
              const pct = (count / total) * 100;
              return (
                <div key={phase} className="flex items-center gap-3">
                  <span className={`text-xs w-28 ${WYCKOFF_COLORS[phase]}`}>
                    {phase.toUpperCase()}
                  </span>
                  <div className="flex-1 bg-terminal-bg rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        phase === 'accumulation'
                          ? 'bg-terminal-green/60'
                          : phase === 'markup'
                          ? 'bg-cyan-400/60'
                          : phase === 'distribution'
                          ? 'bg-amber-400/60'
                          : 'bg-red-400/60'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs text-terminal-dim w-12 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Vol Regime Distribution */}
        <div className="bg-terminal-panel border border-terminal-border rounded p-4">
          <div className="text-[10px] text-terminal-dim tracking-widest mb-3">
            VOLATILITY REGIME DISTRIBUTION
          </div>
          <div className="space-y-2">
            {['low', 'normal', 'high'].map((regime) => {
              const count = volCounts[regime] || 0;
              const pct = (count / total) * 100;
              return (
                <div key={regime} className="flex items-center gap-3">
                  <span className={`text-xs w-20 ${
                    regime === 'low' ? 'text-terminal-green' : regime === 'high' ? 'text-red-400' : 'text-terminal-dim'
                  }`}>
                    {regime.toUpperCase()}
                  </span>
                  <div className="flex-1 bg-terminal-bg rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        regime === 'low'
                          ? 'bg-terminal-green/60'
                          : regime === 'high'
                          ? 'bg-red-400/60'
                          : 'bg-white/20'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs text-terminal-dim w-12 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Compression / Squeeze Setups */}
      {compression.length > 0 && (
        <div className="bg-terminal-panel border border-terminal-border rounded overflow-hidden">
          <div className="p-3 border-b border-terminal-border">
            <div className="text-[10px] text-terminal-dim tracking-widest">
              VOLATILITY COMPRESSION SETUPS ({compression.length})
            </div>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim text-[10px] tracking-widest">
                <th className="text-left p-2">SYMBOL</th>
                <th className="text-left p-2">SECTOR</th>
                <th className="text-right p-2">COMPRESS</th>
                <th className="text-right p-2">HURST</th>
                <th className="text-right p-2">MR</th>
                <th className="text-right p-2">MOM</th>
                <th className="text-center p-2">PHASE</th>
                <th className="text-center p-2">SQ</th>
                <th className="text-right p-2">IV RANK</th>
              </tr>
            </thead>
            <tbody>
              {compression.slice(0, 30).map((c) => (
                <tr key={c.symbol} className="border-b border-terminal-border/50 hover:bg-white/[0.02]">
                  <td className="p-2 font-mono text-terminal-bright">{c.symbol}</td>
                  <td className="p-2 text-terminal-dim">{c.sector || '--'}</td>
                  <td className="p-2 text-right"><ScorePill value={c.compression_score} /></td>
                  <td className="p-2 text-right font-mono">{c.hurst_exponent?.toFixed(3)}</td>
                  <td className="p-2 text-right"><ScorePill value={c.mr_score} /></td>
                  <td className="p-2 text-right"><ScorePill value={c.momentum_score} /></td>
                  <td className="p-2 text-center">
                    <span className={WYCKOFF_COLORS[c.wyckoff_phase]}>
                      {c.wyckoff_phase?.substring(0, 5).toUpperCase()}
                    </span>
                  </td>
                  <td className="p-2 text-center">
                    {c.squeeze_active ? <span className="text-cyan-400">SQ</span> : '--'}
                  </td>
                  <td className="p-2 text-right"><ScorePill value={c.iv_rank} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Earnings Proximity */}
      {nearEarnings.length > 0 && (
        <div className="bg-terminal-panel border border-terminal-border rounded overflow-hidden">
          <div className="p-3 border-b border-terminal-border">
            <div className="text-[10px] text-terminal-dim tracking-widest">
              EARNINGS WITHIN 14 DAYS ({nearEarnings.length})
            </div>
          </div>
          <div className="flex flex-wrap gap-2 p-3">
            {nearEarnings.slice(0, 30).map((p) => (
              <div
                key={p.symbol}
                className="px-2 py-1 rounded border border-amber-400/30 bg-amber-400/10 text-[10px] font-mono"
              >
                <span className="text-terminal-bright">{p.symbol}</span>
                <span className="text-amber-400 ml-1">{p.earnings_days_to_next}d</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
