'use client';

import { useMemo } from 'react';
import type { SectorRotationPoint } from '@/lib/api';
import { QUADRANT_COLORS, QUADRANT_BG, ScorePill, Badge } from '@/components/PatternsShared';
import { cs } from '@/lib/styles';

interface RotationTabProps {
  rotation: SectorRotationPoint[];
  latest: SectorRotationPoint[];
}

export function PatternsRotationTab({ rotation, latest }: RotationTabProps) {
  return (
    <div className="space-y-4">
      {/* RRG Scatter Plot */}
      <div className="bg-white border border-gray-200 rounded p-4">
        <div className="text-[10px] text-gray-500 tracking-widest mb-3">
          RELATIVE ROTATION GRAPH (RRG) -- 4 QUADRANTS
        </div>
        <div className="relative w-full h-[400px]">
          {/* Quadrant labels */}
          <div className="absolute top-2 right-2 text-[10px] text-emerald-600 tracking-widest">LEADING</div>
          <div className="absolute top-2 left-2 text-[10px] text-cyan-400 tracking-widest">IMPROVING</div>
          <div className="absolute bottom-2 left-2 text-[10px] text-red-400 tracking-widest">LAGGING</div>
          <div className="absolute bottom-2 right-2 text-[10px] text-amber-400 tracking-widest">WEAKENING</div>

          {/* Axes */}
          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-200" />
          <div className="absolute top-1/2 left-0 right-0 h-px bg-gray-200" />

          {/* Sector dots */}
          {latest.map((r) => {
            const x = Math.max(5, Math.min(95, 50 + r.rs_ratio * 15));
            const y = Math.max(5, Math.min(95, 50 - r.rs_momentum * 15));
            const color = QUADRANT_COLORS[r.quadrant] || 'text-gray-500';

            return (
              <div
                key={r.sector}
                className={`absolute ${color} font-mono text-[10px] font-bold -translate-x-1/2 -translate-y-1/2`}
                {...cs({ left: `${x}%`, top: `${y}%` })}
                title={`${r.sector}: RS=${r.rs_ratio.toFixed(2)}, Mom=${r.rs_momentum.toFixed(2)}`}
              >
                {r.sector.substring(0, 6).toUpperCase()}
              </div>
            );
          })}
        </div>

        {/* Axis labels */}
        <div className="flex justify-between text-[10px] text-gray-500 mt-1">
          <span>{'<'} RS-RATIO {'>'}</span>
          <span>{'<'} RS-MOMENTUM {'>'}</span>
        </div>
      </div>

      {/* Sector Table */}
      <div className="bg-white border border-gray-200 rounded overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500 text-[10px] tracking-widest">
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
                <tr key={r.sector} className="border-b border-gray-200/50 hover:bg-white/[0.02]">
                  <td className="p-3 font-mono text-gray-900">{r.sector}</td>
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
