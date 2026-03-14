'use client';

import { useState } from 'react';
import Link from 'next/link';
import ScoreBar from './ScoreBar';
import SignalBadge from './SignalBadge';
import type { ThesisChecklist } from '@/lib/api';

interface Props {
  data: ThesisChecklist;
  onClose: () => void;
}

interface SectionProps {
  title: string;
  icon: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

function Section({ title, icon, defaultOpen = false, children }: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b border-terminal-border last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <span className="text-[10px]">{icon}</span>
        <span className="text-[10px] font-bold text-terminal-bright tracking-widest uppercase flex-1">
          {title}
        </span>
        <span className="text-terminal-dim text-[10px]">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="px-4 pb-4 animate-slide-up">{children}</div>}
    </div>
  );
}

function MetricRow({ label, value, color }: { label: string; value: string | number | null; color?: string }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[10px] text-terminal-dim uppercase tracking-wider">{label}</span>
      <span className={`text-[11px] font-mono ${color || 'text-terminal-bright'}`}>
        {typeof value === 'number' ? value.toFixed(2) : value}
      </span>
    </div>
  );
}

export default function BottomUpChecklist({ data, onClose }: Props) {
  const pos = data.position_framework;
  const conv = data.convergence;
  const variant = data.variant_perception as Record<string, unknown> | null;
  const bq = data.business_quality;

  return (
    <div className="panel animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-terminal-border">
        <div className="flex items-center gap-3">
          <Link
            href={`/asset/${data.symbol}`}
            className="font-display text-lg font-bold text-terminal-green hover:underline"
          >
            {data.symbol}
          </Link>
          <span className="text-[10px] text-terminal-dim">{data.name}</span>
          {data.sector && (
            <span className="text-[9px] px-2 py-0.5 rounded-sm bg-terminal-muted/30 text-terminal-dim border border-terminal-border">
              {data.sector}
            </span>
          )}
          {pos.signal && <SignalBadge signal={pos.signal} size="sm" />}
        </div>
        <button
          onClick={onClose}
          className="text-terminal-dim hover:text-terminal-bright text-sm transition-colors"
        >
          x
        </button>
      </div>

      {/* Sections */}
      <Section title="Business Quality" icon="01" defaultOpen>
        {bq.scores ? (
          <div className="space-y-1.5">
            <ScoreBar value={bq.scores.valuation_score || 0} max={20} label="Valuation" />
            <ScoreBar value={bq.scores.growth_score || 0} max={20} label="Growth" />
            <ScoreBar value={bq.scores.profitability_score || 0} max={20} label="Profitability" />
            <ScoreBar value={bq.scores.health_score || 0} max={20} label="Health" />
            <ScoreBar value={bq.scores.quality_score || 0} max={20} label="Quality" />
            <div className="mt-2 pt-2 border-t border-terminal-border">
              <ScoreBar value={bq.scores.total_score || 0} max={100} label="TOTAL" />
            </div>
          </div>
        ) : (
          <p className="text-[10px] text-terminal-dim">No fundamental data available (crypto/commodity).</p>
        )}
        {Object.keys(bq.metrics).length > 0 && (
          <div className="mt-2 pt-2 border-t border-terminal-border grid grid-cols-2 gap-x-4">
            {['pe_ratio', 'pb_ratio', 'roe', 'gross_margin', 'debt_equity', 'market_cap'].map((k) =>
              bq.metrics[k] !== undefined ? (
                <MetricRow
                  key={k}
                  label={k.replace(/_/g, ' ')}
                  value={bq.metrics[k]}
                />
              ) : null
            )}
          </div>
        )}
      </Section>

      <Section title="Variant Perception" icon="02">
        {variant ? (
          <div className="space-y-1">
            <MetricRow label="Implied Growth" value={variant.implied_growth as number} />
            <MetricRow label="Growth Gap" value={variant.growth_gap as number} color={
              (variant.growth_gap as number) > 0 ? 'text-terminal-green' : 'text-terminal-red'
            } />
            <MetricRow label="Upside %" value={variant.upside_pct as number} color={
              (variant.upside_pct as number) > 0 ? 'text-terminal-green' : 'text-terminal-red'
            } />
            <MetricRow label="Variant Score" value={variant.variant_score as number} />
            <MetricRow label="Estimate Bias" value={variant.estimate_bias as string} />
            {variant.narrative ? (
              <p className="text-[10px] text-terminal-dim mt-2 italic leading-relaxed">
                {String(variant.narrative)}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-[10px] text-terminal-dim">No variant analysis available.</p>
        )}
      </Section>

      <Section title="Catalyst Map" icon="03">
        {/* Displacement signals */}
        {data.catalysts.displacement.length > 0 && (
          <div className="mb-3">
            <span className="text-[9px] text-terminal-amber tracking-widest uppercase block mb-1">NEWS DISPLACEMENT</span>
            {data.catalysts.displacement.map((d, i) => (
              <div key={i} className="text-[10px] py-1 border-b border-terminal-border/50 last:border-0">
                <span className="text-terminal-bright">{d.news_headline as string}</span>
                <span className="text-terminal-dim ml-2">Score: {(d.displacement_score as number)?.toFixed(0)}</span>
              </div>
            ))}
          </div>
        )}
        {/* Expert consensus */}
        {data.catalysts.expert && (
          <div className="mb-3">
            <span className="text-[9px] text-terminal-cyan tracking-widest uppercase block mb-1">SECTOR EXPERT</span>
            <p className="text-[10px] text-terminal-dim">
              <span className="text-terminal-bright">Consensus:</span> {data.catalysts.expert.consensus_narrative as string}
            </p>
            <p className="text-[10px] text-terminal-dim mt-1">
              <span className="text-terminal-amber">Variant:</span> {data.catalysts.expert.variant_narrative as string}
            </p>
            {data.catalysts.expert.key_catalysts ? (
              <p className="text-[10px] text-terminal-green mt-1">
                Catalysts: {String(data.catalysts.expert.key_catalysts)}
              </p>
            ) : null}
          </div>
        )}
        {/* Research */}
        {data.catalysts.research.length > 0 && (
          <div>
            <span className="text-[9px] text-terminal-dim tracking-widest uppercase block mb-1">RESEARCH</span>
            {data.catalysts.research.map((r, i) => (
              <div key={i} className="text-[10px] py-1 flex items-center gap-2">
                <span className="text-terminal-dim">{r.source as string}</span>
                <span className="text-terminal-bright flex-1 truncate">{r.title as string}</span>
              </div>
            ))}
          </div>
        )}
        {!data.catalysts.displacement.length && !data.catalysts.expert && !data.catalysts.research.length && (
          <p className="text-[10px] text-terminal-dim">No active catalysts identified.</p>
        )}
      </Section>

      <Section title="Risk Assessment" icon="04">
        {/* Forensic alerts */}
        {data.risk_assessment.forensic_alerts.length > 0 ? (
          <div className="mb-3">
            {data.risk_assessment.forensic_alerts.map((a, i) => (
              <div key={i} className={`text-[10px] py-1 flex items-center gap-2 ${
                a.severity === 'CRITICAL' ? 'text-terminal-red' :
                a.severity === 'WARNING' ? 'text-terminal-amber' : 'text-terminal-dim'
              }`}>
                <span className="font-bold">{a.severity as string}</span>
                <span>{(a.detail ?? a.description) as string}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-[10px] text-terminal-green mb-2">No forensic red flags detected.</p>
        )}
        <div className="grid grid-cols-2 gap-x-4">
          <MetricRow label="Entry" value={data.risk_assessment.entry_price} />
          <MetricRow label="Stop Loss" value={data.risk_assessment.stop_loss} color="text-terminal-red" />
          <MetricRow label="Stop Distance" value={
            data.risk_assessment.stop_distance_pct
              ? `${data.risk_assessment.stop_distance_pct}%`
              : null
          } />
        </div>
      </Section>

      <Section title="Position Framework" icon="05">
        <div className="grid grid-cols-2 gap-x-4">
          <MetricRow label="Entry" value={pos.entry ? `$${pos.entry.toFixed(2)}` : null} />
          <MetricRow label="Stop" value={pos.stop ? `$${pos.stop.toFixed(2)}` : null} color="text-terminal-red" />
          <MetricRow label="Target" value={pos.target ? `$${pos.target.toFixed(2)}` : null} color="text-terminal-green" />
          <MetricRow label="R:R Ratio" value={pos.rr_ratio ? `${pos.rr_ratio.toFixed(1)}:1` : null} color="text-terminal-green" />
          <MetricRow label="Composite" value={pos.composite_score} />
          <MetricRow label="Position $" value={pos.position_size_dollars ? `$${pos.position_size_dollars.toFixed(0)}` : null} />
        </div>
      </Section>

      <Section title="Convergence Context" icon="06">
        {conv.score ? (
          <>
            <div className="flex items-center gap-3 mb-2">
              <span className="font-mono text-sm text-terminal-green font-bold">
                {conv.score.toFixed(1)}
              </span>
              <span className={`text-[9px] px-2 py-0.5 rounded-sm font-bold tracking-wider ${
                conv.conviction === 'HIGH'
                  ? 'bg-terminal-green/20 text-terminal-green border border-terminal-green/30'
                  : 'bg-terminal-amber/20 text-terminal-amber border border-terminal-amber/30'
              }`}>
                {conv.conviction}
              </span>
              <span className="text-[10px] text-terminal-dim">
                {conv.module_count} modules agree
              </span>
            </div>
            {conv.modules && (
              <p className="text-[10px] text-terminal-dim mb-2">Active: {conv.modules}</p>
            )}
            {/* Module breakdown */}
            <div className="space-y-1">
              {Object.entries(conv.breakdown).map(([key, val]) =>
                val !== null && val !== undefined ? (
                  <ScoreBar key={key} value={val} max={100} label={key.replace(/_/g, ' ')} />
                ) : null
              )}
            </div>
            {conv.narrative && (
              <p className="text-[10px] text-terminal-dim mt-3 italic leading-relaxed border-t border-terminal-border pt-2">
                {conv.narrative}
              </p>
            )}
          </>
        ) : (
          <p className="text-[10px] text-terminal-dim">No convergence data available.</p>
        )}
      </Section>
    </div>
  );
}
