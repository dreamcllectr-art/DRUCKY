'use client';

import type { PatternScanResult, PatternLayerDetail } from '@/lib/api';
import { QUADRANT_BG, WYCKOFF_COLORS, ScorePill, Badge } from '@/components/PatternsShared';
import { PatternsDetailPanel } from '@/components/PatternsDetailPanel';

interface ScannerTabProps {
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
}

export function PatternsScannerTab({
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
}: ScannerTabProps) {
  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={sectorFilter}
          onChange={(e) => setSectorFilter(e.target.value)}
          className="bg-gray-50 border border-gray-200 text-gray-700 text-xs p-1.5 rounded"
        >
          <option value="">ALL SECTORS</option>
          {sectors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <select
          value={phaseFilter}
          onChange={(e) => setPhaseFilter(e.target.value)}
          className="bg-gray-50 border border-gray-200 text-gray-700 text-xs p-1.5 rounded"
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
              : 'text-gray-500 border-gray-200'
          }`}
        >
          SQUEEZE ONLY
        </button>

        <span className="text-[10px] text-gray-500 ml-auto">
          {patterns.length} SYMBOLS
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500 text-[10px] tracking-widest">
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
                    className={`border-b border-gray-200/50 cursor-pointer transition-colors
                      ${isExpanded ? 'bg-emerald-600/5' : 'hover:bg-white/[0.02]'}`}
                  >
                    <td className="p-2 font-mono text-gray-900">{p.symbol}</td>
                    <td className="p-2 text-gray-500">{p.sector || '--'}</td>
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
                      <span className={`text-[10px] ${WYCKOFF_COLORS[p.wyckoff_phase] || 'text-gray-500'}`}>
                        {p.wyckoff_phase?.toUpperCase() || '--'}
                      </span>
                    </td>
                    <td className="p-2 text-center">
                      {p.squeeze_active ? (
                        <span className="text-cyan-400 animate-pulse">SQ</span>
                      ) : (
                        <span className="text-gray-500">--</span>
                      )}
                    </td>
                  </tr>
                  {isExpanded && detail && (
                    <tr key={`${p.symbol}-detail`}>
                      <td colSpan={10} className="p-4 bg-gray-500">
                        <PatternsDetailPanel detail={detail} />
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
