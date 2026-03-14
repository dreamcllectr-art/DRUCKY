'use client';

interface Props {
  entry: number;
  stop: number;
  target: number;
  currentPrice?: number;
  width?: number;
  height?: number;
  showLabels?: boolean;
  showRR?: boolean;
}

export default function TradeRangeBar({
  entry,
  stop,
  target,
  currentPrice,
  width = 120,
  height = 16,
  showLabels = false,
  showRR = true,
}: Props) {
  if (!entry || !stop || !target || target <= stop) return null;

  const totalRange = target - stop;
  const riskPct = ((entry - stop) / totalRange) * 100;
  const rewardPct = ((target - entry) / totalRange) * 100;
  const rr = (target - entry) / Math.max(entry - stop, 0.01);

  // Current price position (clamped to bar range)
  let pricePct: number | null = null;
  if (currentPrice != null) {
    pricePct = Math.max(0, Math.min(100, ((currentPrice - stop) / totalRange) * 100));
  }

  const labelH = showLabels ? 18 : 0;
  const totalH = height + labelH;

  return (
    <div style={{ width, position: 'relative' }}>
      <svg width={width} height={totalH} viewBox={`0 0 ${width} ${totalH}`}>
        {/* Risk zone (stop → entry): red */}
        <rect
          x={0}
          y={0}
          width={(riskPct / 100) * width}
          height={height}
          rx={2}
          fill="rgba(255,7,58,0.35)"
        />
        {/* Reward zone (entry → target): green */}
        <rect
          x={(riskPct / 100) * width}
          y={0}
          width={(rewardPct / 100) * width}
          height={height}
          rx={2}
          fill="rgba(0,255,65,0.30)"
        />

        {/* Entry tick (cyan) */}
        <line
          x1={(riskPct / 100) * width}
          y1={0}
          x2={(riskPct / 100) * width}
          y2={height}
          stroke="#00E5FF"
          strokeWidth={2}
        />

        {/* Current price dot */}
        {pricePct != null && (
          <circle
            cx={(pricePct / 100) * width}
            cy={height / 2}
            r={Math.max(3, height / 4)}
            fill="#F0F0F0"
            stroke={currentPrice! >= entry ? '#00FF41' : '#FF073A'}
            strokeWidth={1.5}
          />
        )}

        {/* R:R label overlaid on green zone */}
        {showRR && rewardPct > 20 && (
          <text
            x={(riskPct / 100) * width + (rewardPct / 100) * width * 0.5}
            y={height / 2 + 1}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="#00FF41"
            fontSize={Math.max(8, height * 0.55)}
            fontFamily="'JetBrains Mono', monospace"
            fontWeight="bold"
          >
            {rr.toFixed(1)}
          </text>
        )}

        {/* Labels below bar */}
        {showLabels && (
          <>
            <text x={1} y={height + 13} fill="#FF073A" fontSize={9} fontFamily="'JetBrains Mono', monospace">
              ${stop.toFixed(0)}
            </text>
            <text
              x={(riskPct / 100) * width}
              y={height + 13}
              textAnchor="middle"
              fill="#00E5FF"
              fontSize={9}
              fontFamily="'JetBrains Mono', monospace"
            >
              ${entry.toFixed(0)}
            </text>
            <text
              x={width - 1}
              y={height + 13}
              textAnchor="end"
              fill="#00FF41"
              fontSize={9}
              fontFamily="'JetBrains Mono', monospace"
            >
              ${target.toFixed(0)}
            </text>
          </>
        )}
      </svg>
    </div>
  );
}
