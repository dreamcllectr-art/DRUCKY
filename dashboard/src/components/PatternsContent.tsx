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
import { PatternsScannerTab } from '@/components/PatternsScannerTab';
import { PatternsRotationTab } from '@/components/PatternsRotationTab';
import { PatternsOptionsTab } from '@/components/PatternsOptionsTab';
import { PatternsCyclesTab } from '@/components/PatternsCyclesTab';

type Tab = 'scanner' | 'rotation' | 'options' | 'cycles';

export default function PatternsContent() {
  const [tab, setTab] = useState<Tab>('scanner');
  const [patterns, setPatterns] = useState<PatternScanResult[]>([]);
  const [rotation, setRotation] = useState<SectorRotationPoint[]>([]);
  const [options, setOptions] = useState<OptionsIntelResult[]>([]);
  const [unusual, setUnusual] = useState<UnusualActivityRow[]>([]);
  const [expectedMoves, setExpectedMoves] = useState<ExpectedMoveRow[]>([]);
  const [compression, setCompression] = useState<CompressionRow[]>([]);
  const [dealers, setDealers] = useState<DealerExposureRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [sectorFilter, setSectorFilter] = useState('');
  const [phaseFilter, setPhaseFilter] = useState('');
  const [squeezeOnly, setSqueezeOnly] = useState(false);
  const [layers, setLayers] = useState({
    regime: true, rotation: true, patterns: true, statistics: true, options: true,
  });
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
      setPatterns(p); setRotation(r); setOptions(o); setUnusual(u);
      setExpectedMoves(em); setCompression(c); setDealers(d); setLoading(false);
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

  const latestRotation = useMemo(() => {
    const map: Record<string, SectorRotationPoint> = {};
    rotation.forEach((r) => {
      if (!map[r.sector] || r.date > map[r.sector].date) map[r.sector] = r;
    });
    return Object.values(map);
  }, [rotation]);

  const totalSetups = patterns.filter((p) => (p.pattern_options_score ?? p.pattern_scan_score) > 50).length;
  const activeSqueeze = patterns.filter((p) => p.squeeze_active).length;
  const unusualCount = unusual.length;
  const leadingSectors = latestRotation.filter((r) => r.quadrant === 'leading').length;

  const loadDetail = async (sym: string) => {
    if (expandedSymbol === sym) { setExpandedSymbol(null); return; }
    setExpandedSymbol(sym);
    try { setDetail(await api.patternLayers(sym)); } catch { setDetail(null); }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-emerald-600 animate-pulse glow-green">
          SCANNING PATTERNS & OPTIONS FLOW...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-gray-900 tracking-tight">
          PATTERN MATCH & OPTIONS INTELLIGENCE
        </h1>
        <p className="text-[10px] text-gray-500 tracking-widest mt-1">
          5-LAYER CASCADE: REGIME {'>'} ROTATION {'>'} PATTERNS {'>'} STATISTICS {'>'} DERIVATIVES
        </p>
      </div>

      {/* Layer Toggle Bar */}
      <div className="flex items-center gap-4 p-3 bg-white border border-gray-200 rounded">
        <span className="text-[10px] text-gray-500 tracking-widest">LAYERS:</span>
        {Object.entries(layers).map(([key, active]) => (
          <button
            key={key}
            onClick={() => setLayers((prev) => ({ ...prev, [key]: !prev[key as keyof typeof prev] }))}
            className={`text-[10px] tracking-widest px-2 py-1 rounded border transition-all ${
              active
                ? 'text-emerald-600 border-emerald-600/40 bg-emerald-600/10'
                : 'text-gray-500 border-gray-200 hover:text-gray-700'
            }`}
          >
            {key.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: 'SETUPS (>50)', value: totalSetups, color: 'text-emerald-600' },
          { label: 'ACTIVE SQUEEZES', value: activeSqueeze, color: 'text-cyan-400' },
          { label: 'UNUSUAL OPTIONS', value: unusualCount, color: 'text-amber-400' },
          { label: 'LEADING SECTORS', value: leadingSectors, color: 'text-emerald-600' },
        ].map((card) => (
          <div key={card.label} className="bg-white border border-gray-200 rounded p-3">
            <div className={`font-mono text-2xl font-bold ${card.color}`}>{card.value}</div>
            <div className="text-[9px] text-gray-500 tracking-widest mt-1">{card.label}</div>
          </div>
        ))}
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-gray-200">
        {(['scanner', 'rotation', 'options', 'cycles'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-xs tracking-widest transition-all border-b-2 ${
              tab === t
                ? 'text-emerald-600 border-emerald-600'
                : 'text-gray-500 border-transparent hover:text-gray-700'
            }`}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {tab === 'scanner' && (
        <PatternsScannerTab
          patterns={filteredPatterns} sectors={sectors}
          sectorFilter={sectorFilter} setSectorFilter={setSectorFilter}
          phaseFilter={phaseFilter} setPhaseFilter={setPhaseFilter}
          squeezeOnly={squeezeOnly} setSqueezeOnly={setSqueezeOnly}
          expandedSymbol={expandedSymbol} detail={detail} onExpand={loadDetail} layers={layers}
        />
      )}
      {tab === 'rotation' && <PatternsRotationTab rotation={rotation} latest={latestRotation} />}
      {tab === 'options' && (
        <PatternsOptionsTab options={options} unusual={unusual} expectedMoves={expectedMoves} dealers={dealers} />
      )}
      {tab === 'cycles' && <PatternsCyclesTab patterns={patterns} compression={compression} />}
    </div>
  );
}
