'use client';

import { useEffect, useState } from 'react';
import {
  api,
  type HLGapSignal,
  type HLSnapshot,
  type HLDeployerSpread,
  type HLAccuracy,
} from '@/lib/api';

type Tab = 'gaps' | 'live' | 'spreads' | 'accuracy';

export default function HyperliquidPage() {
  const [gaps, setGaps] = useState<HLGapSignal[]>([]);
  const [bookDepth, setBookDepth] = useState<HLSnapshot[]>([]);
  const [spreads, setSpreads] = useState<HLDeployerSpread[]>([]);
  const [accuracy, setAccuracy] = useState<HLAccuracy | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<Tab>('gaps');

  // Snapshot detail
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<HLSnapshot[]>([]);
  const [snapshotLoading, setSnapshotLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      api.hlGapSignals(8).catch(() => []),
      api.hlBookDepth().catch(() => []),
      api.hlDeployerSpreads(0, 72).catch(() => []),
      api.hlAccuracy().catch(() => null),
    ]).then(([g, b, s, a]) => {
      setGaps(g);
      setBookDepth(b);
      setSpreads(s);
      setAccuracy(a);
      setLoading(false);
    });
  }, []);

  const loadSnapshots = async (ticker: string) => {
    if (expandedTicker === ticker) {
      setExpandedTicker(null);
      return;
    }
    setSnapshotLoading(true);
    setExpandedTicker(ticker);
    try {
      const data = await api.hlSnapshots(ticker, 72);
      setSnapshots(data);
    } catch {
      setSnapshots([]);
    }
    setSnapshotLoading(false);
  };

  const formatPrice = (v: number) => {
    if (v >= 1000) return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    if (v >= 1) return `$${v.toFixed(2)}`;
    return `$${v.toFixed(4)}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          FETCHING HYPERLIQUID WEEKEND DATA...
        </div>
      </div>
    );
  }

  // Summary stats
  const upGaps = gaps.filter((g) => g.predicted_direction === 'UP').length;
  const downGaps = gaps.filter((g) => g.predicted_direction === 'DOWN').length;
  const largeGaps = gaps.filter((g) => Math.abs(g.predicted_gap_pct) >= 1).length;
  const highSpreadCount = spreads.filter((s) => s.spread_bps >= 50).length;

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          HYPERLIQUID WEEKEND GAPS
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          HIP-3 PERP WEEKEND PRICE DISCOVERY — CME/EQUITY GAP PREDICTION — CROSS-DEPLOYER ARBITRAGE
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        <div
          onClick={() => setActiveTab('gaps')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'gaps' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-green">
            {upGaps}
            <span className="text-terminal-red ml-2">{downGaps}</span>
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            GAP PREDICTIONS (UP/DOWN)
          </div>
        </div>
        <div
          onClick={() => setActiveTab('live')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'live' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-amber">
            {bookDepth.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            LIVE INSTRUMENTS
          </div>
        </div>
        <div
          onClick={() => setActiveTab('spreads')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'spreads' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-cyan">
            {highSpreadCount}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            DEPLOYER DIVERGENCES
          </div>
        </div>
        <div
          onClick={() => setActiveTab('accuracy')}
          className={`panel px-4 py-3 cursor-pointer transition-all ${
            activeTab === 'accuracy' ? 'border-terminal-green/50' : 'hover:border-terminal-muted'
          }`}
        >
          <div className="text-2xl font-display font-bold text-terminal-green">
            {accuracy?.direction_accuracy_pct != null
              ? `${accuracy.direction_accuracy_pct}%`
              : largeGaps > 0
              ? `${largeGaps}`
              : '—'}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
            {accuracy?.direction_accuracy_pct != null ? 'DIRECTION ACCURACY' : 'LARGE GAPS (>1%)'}
          </div>
        </div>
      </div>

      {/* Gap Predictions Tab */}
      {activeTab === 'gaps' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              PREDICTED MONDAY GAPS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              HL weekend return at 20:00 UTC (optimal signal window) vs Friday close — slope ~1.0, R2=0.73
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Ticker</th>
                  <th className="text-left py-3 px-2 font-normal">Deployer</th>
                  <th className="text-right py-3 px-2 font-normal">Fri Close</th>
                  <th className="text-right py-3 px-2 font-normal">HL Price</th>
                  <th className="text-right py-3 px-2 font-normal">Gap %</th>
                  <th className="text-center py-3 px-2 font-normal">Direction</th>
                  <th className="text-right py-3 px-2 font-normal">Confidence</th>
                  <th className="text-right py-3 px-2 font-normal">Actual %</th>
                  <th className="text-center py-3 px-2 font-normal">Correct</th>
                  <th className="text-right py-3 px-2 font-normal">Error</th>
                </tr>
              </thead>
              <tbody>
                {gaps.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="text-center py-8 text-terminal-dim">
                      No gap predictions yet. Run the pipeline on a weekend to generate signals.
                    </td>
                  </tr>
                ) : (
                  gaps.map((g, i) => (
                    <tr
                      key={`${g.traditional_ticker}-${g.weekend_date}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors cursor-pointer"
                      onClick={() => loadSnapshots(g.traditional_ticker)}
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-green">
                        {g.traditional_ticker}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[9px] tracking-wider uppercase">
                        {g.deployer}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-dim">
                        {formatPrice(g.friday_close)}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {formatPrice(g.hl_price_20utc)}
                      </td>
                      <td
                        className={`py-2.5 px-2 text-right font-mono font-bold ${
                          g.predicted_gap_pct >= 0 ? 'text-terminal-green' : 'text-terminal-red'
                        }`}
                      >
                        {g.predicted_gap_pct >= 0 ? '+' : ''}
                        {g.predicted_gap_pct.toFixed(2)}%
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        <span
                          className={`px-1.5 py-0.5 rounded-sm text-[9px] font-bold ${
                            g.predicted_direction === 'UP'
                              ? 'bg-terminal-green/15 text-terminal-green'
                              : g.predicted_direction === 'DOWN'
                              ? 'bg-terminal-red/15 text-terminal-red'
                              : 'bg-white/5 text-terminal-dim'
                          }`}
                        >
                          {g.predicted_direction}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span
                          className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                          style={{
                            backgroundColor:
                              g.confidence >= 70
                                ? 'rgba(0,255,65,0.15)'
                                : g.confidence >= 50
                                ? 'rgba(255,184,0,0.15)'
                                : 'rgba(255,255,255,0.05)',
                            color:
                              g.confidence >= 70
                                ? '#00FF41'
                                : g.confidence >= 50
                                ? '#FFB800'
                                : '#888',
                          }}
                        >
                          {g.confidence.toFixed(0)}
                        </span>
                      </td>
                      <td
                        className={`py-2.5 px-2 text-right font-mono ${
                          g.actual_gap_pct != null
                            ? g.actual_gap_pct >= 0
                              ? 'text-terminal-green'
                              : 'text-terminal-red'
                            : 'text-terminal-dim'
                        }`}
                      >
                        {g.actual_gap_pct != null
                          ? `${g.actual_gap_pct >= 0 ? '+' : ''}${g.actual_gap_pct.toFixed(2)}%`
                          : '—'}
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        {g.direction_correct != null ? (
                          <span
                            className={`px-1.5 py-0.5 rounded-sm text-[9px] font-bold ${
                              g.direction_correct === 1
                                ? 'bg-terminal-green/15 text-terminal-green'
                                : 'bg-terminal-red/15 text-terminal-red'
                            }`}
                          >
                            {g.direction_correct === 1 ? 'YES' : 'NO'}
                          </span>
                        ) : (
                          <span className="text-terminal-dim">—</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-dim">
                        {g.error_bps != null ? `${g.error_bps.toFixed(0)}bp` : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Live Prices Tab */}
      {activeTab === 'live' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              LIVE INSTRUMENT PRICES
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Current HL mid prices, spreads, and book depth across all deployers
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Symbol</th>
                  <th className="text-left py-3 px-2 font-normal">Deployer</th>
                  <th className="text-left py-3 px-2 font-normal">Ticker</th>
                  <th className="text-right py-3 px-2 font-normal">Mid</th>
                  <th className="text-right py-3 px-2 font-normal">Spread</th>
                  <th className="text-right py-3 px-2 font-normal">Bid Depth</th>
                  <th className="text-right py-3 px-2 font-normal">Ask Depth</th>
                  <th className="text-left py-3 px-2 font-normal">Updated</th>
                </tr>
              </thead>
              <tbody>
                {bookDepth.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-terminal-dim">
                      No snapshots yet. Run snapshot collection during a weekend.
                    </td>
                  </tr>
                ) : (
                  bookDepth.map((b, i) => {
                    const totalDepth = (b.book_depth_bid_usd || 0) + (b.book_depth_ask_usd || 0);
                    return (
                      <tr
                        key={`${b.hl_symbol}-${i}`}
                        className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors"
                      >
                        <td className="py-2.5 px-4 font-mono font-bold text-terminal-green">
                          {b.hl_symbol}
                        </td>
                        <td className="py-2.5 px-2 text-terminal-dim text-[9px] tracking-wider uppercase">
                          {b.deployer}
                        </td>
                        <td className="py-2.5 px-2 text-terminal-text font-mono">
                          {/* derived from hl_symbol */}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-bright">
                          {formatPrice(b.mid_price)}
                        </td>
                        <td className="py-2.5 px-2 text-right">
                          <span
                            className={`px-1.5 py-0.5 rounded-sm text-[10px] font-bold ${
                              b.spread_bps < 10
                                ? 'bg-terminal-green/15 text-terminal-green'
                                : b.spread_bps < 50
                                ? 'bg-terminal-amber/15 text-terminal-amber'
                                : 'bg-terminal-red/15 text-terminal-red'
                            }`}
                          >
                            {b.spread_bps?.toFixed(1)}bp
                          </span>
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-dim">
                          {b.book_depth_bid_usd
                            ? `$${(b.book_depth_bid_usd / 1000).toFixed(0)}K`
                            : '—'}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-terminal-dim">
                          {b.book_depth_ask_usd
                            ? `$${(b.book_depth_ask_usd / 1000).toFixed(0)}K`
                            : '—'}
                        </td>
                        <td className="py-2.5 px-2 text-terminal-dim text-[9px]">
                          {b.timestamp?.slice(11, 19)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cross-Deployer Spreads Tab */}
      {activeTab === 'spreads' && (
        <div className="panel overflow-hidden">
          <div className="px-4 py-3 border-b border-terminal-border">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
              CROSS-DEPLOYER SPREADS
            </h2>
            <p className="text-[10px] text-terminal-dim mt-0.5">
              Same asset traded on different deployers — divergences = arbitrage opportunities
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                  <th className="text-left py-3 px-4 font-normal">Ticker</th>
                  <th className="text-left py-3 px-2 font-normal">Deployer A</th>
                  <th className="text-left py-3 px-2 font-normal">Deployer B</th>
                  <th className="text-right py-3 px-2 font-normal">Price A</th>
                  <th className="text-right py-3 px-2 font-normal">Price B</th>
                  <th className="text-right py-3 px-2 font-normal">Spread</th>
                  <th className="text-left py-3 px-2 font-normal">Direction</th>
                  <th className="text-left py-3 px-2 font-normal">Time</th>
                </tr>
              </thead>
              <tbody>
                {spreads.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-8 text-terminal-dim">
                      No cross-deployer spreads detected. Run snapshots during a weekend.
                    </td>
                  </tr>
                ) : (
                  spreads.map((s, i) => (
                    <tr
                      key={`${s.traditional_ticker}-${s.deployer_a}-${s.deployer_b}-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors"
                    >
                      <td className="py-2.5 px-4 font-mono font-bold text-terminal-cyan">
                        {s.traditional_ticker}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[9px] tracking-wider uppercase">
                        {s.deployer_a}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[9px] tracking-wider uppercase">
                        {s.deployer_b}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {formatPrice(s.price_a)}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-text">
                        {formatPrice(s.price_b)}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span
                          className={`px-1.5 py-0.5 rounded-sm text-[10px] font-bold ${
                            s.spread_bps >= 100
                              ? 'bg-terminal-red/15 text-terminal-red'
                              : s.spread_bps >= 50
                              ? 'bg-terminal-amber/15 text-terminal-amber'
                              : 'bg-white/5 text-terminal-dim'
                          }`}
                        >
                          {s.spread_bps.toFixed(1)}bp
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[9px]">
                        {s.spread_direction}
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[9px]">
                        {s.timestamp?.slice(11, 19)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Historical Accuracy Tab */}
      {activeTab === 'accuracy' && (
        <div className="space-y-4">
          {/* Accuracy stats */}
          <div className="panel px-6 py-5">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold mb-4">
              PREDICTION ACCURACY
            </h2>
            {accuracy && accuracy.total_predictions > 0 ? (
              <div className="grid grid-cols-3 gap-6">
                <div>
                  <div className="text-3xl font-display font-bold text-terminal-green glow-green">
                    {accuracy.direction_accuracy_pct ?? '—'}%
                  </div>
                  <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
                    DIRECTION ACCURACY
                  </div>
                  <div className="text-[10px] text-terminal-dim mt-0.5">
                    {accuracy.correct_direction}/{accuracy.total_predictions} predictions
                  </div>
                </div>
                <div>
                  <div className="text-3xl font-display font-bold text-terminal-amber">
                    {accuracy.avg_error_bps ?? '—'}
                  </div>
                  <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
                    AVG ERROR (BPS)
                  </div>
                  <div className="text-[10px] text-terminal-dim mt-0.5">
                    Research benchmark: 14bps
                  </div>
                </div>
                <div>
                  <div className="text-3xl font-display font-bold text-terminal-cyan">
                    {accuracy.avg_predicted_gap_pct ?? '—'}%
                  </div>
                  <div className="text-[10px] text-terminal-dim tracking-widest mt-1">
                    AVG PREDICTED GAP
                  </div>
                  <div className="text-[10px] text-terminal-dim mt-0.5">
                    vs actual: {accuracy.avg_actual_gap_pct ?? '—'}%
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-terminal-dim text-center py-8">
                No backfilled accuracy data yet. Predictions need a Monday open to verify against.
                <br />
                <span className="text-[10px] text-terminal-dim mt-2 block">
                  Research baseline: 100% directional accuracy (34/34 assets), 14bps median error, R2=0.973
                </span>
              </div>
            )}
          </div>

          {/* Research context */}
          <div className="panel px-6 py-5">
            <h2 className="text-xs text-terminal-bright tracking-widest font-bold mb-3">
              RESEARCH CONTEXT
            </h2>
            <div className="text-[11px] text-terminal-dim space-y-2 leading-relaxed">
              <p>
                <span className="text-terminal-green font-bold">Key finding:</span> Hyperliquid HIP-3 perps
                predict Monday CME/equity gaps with 100% directional accuracy across 35 instruments
                (R2=0.973, 14bps median error).
              </p>
              <p>
                <span className="text-terminal-amber font-bold">Optimal window:</span> 20:00 UTC Sunday
                (3h before CME open) — slope ~1.0, R2=0.73. After 20:00, metals overshoot as LPs pull
                66-84% of book depth.
              </p>
              <p>
                <span className="text-terminal-cyan font-bold">Cross-deployer edge:</span> Same asset
                on different deployers (XYZ, Kinetiq, Felix, Cash) converges at Monday open but
                diverges during weekends — buy the slow book, sell the fast one.
              </p>
              <p>
                <span className="text-terminal-red font-bold">Opening dislocation:</span> When CME
                reopens, oracle gaps instantly but perp mid stays sticky — creates 193bps (Gold) to
                292bps (Silver) premium that decays in 5-6 minutes.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
