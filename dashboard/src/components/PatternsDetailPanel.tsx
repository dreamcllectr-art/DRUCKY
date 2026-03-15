import type { PatternLayerDetail } from '@/lib/api';
import { QUADRANT_COLORS, QUADRANT_BG, DEALER_COLORS, ScorePill, Badge } from '@/components/PatternsShared';

export function PatternsDetailPanel({ detail }: { detail: PatternLayerDetail }) {
  const scan = detail.scan;
  const opt = detail.options;

  if (!scan) return <div className="text-gray-500">No data</div>;

  const layerScores = scan.layer_scores ? JSON.parse(scan.layer_scores) : {};
  const detectedPatterns = scan.patterns_detected ? JSON.parse(scan.patterns_detected) : [];

  return (
    <div className="grid grid-cols-5 gap-4 text-[10px]">
      {/* L1: Regime */}
      <div>
        <div className="text-gray-500 tracking-widest mb-2">L1: REGIME</div>
        <div className="space-y-1">
          <div>Regime: <span className="text-gray-900">{scan.regime}</span></div>
          <div>Score: <ScorePill value={layerScores.L1_regime} /></div>
          <div>VIX Pctl: {scan.vix_percentile?.toFixed(0)}%</div>
        </div>
      </div>

      {/* L2: Rotation */}
      <div>
        <div className="text-gray-500 tracking-widest mb-2">L2: ROTATION</div>
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
        <div className="text-gray-500 tracking-widest mb-2">L3: TECHNICAL</div>
        <div className="space-y-1">
          {detectedPatterns.length > 0 ? (
            detectedPatterns.map((p: any, i: number) => (
              <div key={i}>
                <Badge
                  text={p.pattern}
                  color={p.direction === 'bullish' ? QUADRANT_BG.leading : QUADRANT_BG.lagging}
                />
                <span className="ml-1 text-gray-500">{(p.confidence * 100).toFixed(0)}%</span>
              </div>
            ))
          ) : (
            <div className="text-gray-500">No patterns</div>
          )}
          <div>S/R: {scan.sr_proximity}</div>
          <div>Vol Profile: <ScorePill value={scan.volume_profile_score} /></div>
        </div>
      </div>

      {/* L4: Statistics */}
      <div>
        <div className="text-gray-500 tracking-widest mb-2">L4: STATISTICS</div>
        <div className="space-y-1">
          <div>Hurst: <span className="text-gray-900">{scan.hurst_exponent?.toFixed(3)}</span>
            <span className="text-gray-500 ml-1">
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
        <div className="text-gray-500 tracking-widest mb-2">L5: OPTIONS</div>
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
          <div className="text-gray-500">Below options gate</div>
        )}
      </div>
    </div>
  );
}
