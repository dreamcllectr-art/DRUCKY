'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { FunnelData, ThesisDetail as ThesisDetailType } from '@/lib/api';
import { cs, animDelay } from '@/lib/styles';

interface Props {
  data: FunnelData;
  onSelectSymbol: (symbol: string) => void;
  selectedSymbol: string | null;
}

const FUNNEL_STEPS = [
  { key: 'universe', label: 'UNIVERSE', icon: '01' },
  { key: 'theses', label: 'ACTIVE THESES', icon: '02' },
  { key: 'sectors', label: 'SECTOR TILT', icon: '03' },
  { key: 'expressions', label: 'STOCK EXPRESSION', icon: '04' },
  { key: 'convergent', label: 'CONVERGENCE', icon: '05' },
  { key: 'actionable', label: 'ACTIONABLE', icon: '06' },
] as const;

export default function FunnelView({ data, onSelectSymbol, selectedSymbol }: Props) {
  const [expandedStep, setExpandedStep] = useState<string | null>(null);

  const counts = data.funnel_counts;
  const stepCounts = [
    counts.universe,
    data.active_theses.length,
    counts.favored_sectors,
    counts.expressions,
    counts.convergent,
    counts.actionable,
  ];

  const maxCount = counts.universe || 1;

  return (
    <div className="space-y-0">
      {/* Regime Header */}
      <div className="panel p-4 mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] text-gray-500 tracking-widest uppercase">MACRO REGIME</span>
          <span className="text-[10px] text-gray-500">{data.regime.date}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className={`font-display text-xl font-bold tracking-wide ${
            data.regime.score > 20 ? 'text-emerald-600 glow-green' :
            data.regime.score < -20 ? 'text-rose-600 glow-red' :
            'text-amber-600 glow-amber'
          }`}>
            {data.regime.label.replace(/_/g, ' ').toUpperCase()}
          </span>
          <span className="font-mono text-sm text-gray-500">
            {data.regime.score > 0 ? '+' : ''}{data.regime.score.toFixed(0)}
          </span>
        </div>
        <p className="text-[10px] text-gray-500 mt-2 leading-relaxed">
          {data.regime.implications}
        </p>
      </div>

      {/* Funnel Steps */}
      {FUNNEL_STEPS.map((step, i) => {
        const count = stepCounts[i];
        const isExpanded = expandedStep === step.key;
        // Bar width: first step is 100%, then proportional
        const barPct = i === 0 ? 100 :
          i === 1 ? 80 : // theses — not a count comparison
          Math.max(8, (count / maxCount) * 100);

        return (
          <div key={step.key} className="animate-fade-in" {...animDelay(i * 80)}>
            {/* Step bar */}
            <button
              onClick={() => setExpandedStep(isExpanded ? null : step.key)}
              className="w-full text-left group"
            >
              <div className="flex items-center gap-3 py-2 px-1">
                <span className="text-[10px] text-gray-500 font-mono w-5">{step.icon}</span>
                <span className="text-[10px] text-gray-500 tracking-widest uppercase w-32 shrink-0">
                  {step.label}
                </span>
                <div className="flex-1 h-6 bg-gray-100/30 rounded-lg overflow-hidden relative">
                  <div
                    className="h-full rounded-lg transition-all duration-700 ease-out funnel-bar"
                    {...cs({
                      width: `${barPct}%`,
                      background: i <= 1
                        ? 'rgba(5, 150, 105, 0.15)'
                        : i <= 3
                        ? 'rgba(5, 150, 105, 0.25)'
                        : 'rgba(5, 150, 105, 0.4)',
                      borderRight: '2px solid rgba(5, 150, 105, 0.6)',
                    })}
                  />
                  <span className="absolute inset-0 flex items-center px-3 text-[11px] font-mono text-gray-900">
                    {i === 1 ? `${count} thesis${count !== 1 ? 'es' : ''} active` :
                     i === 2 ? `${count} sector${count !== 1 ? 's' : ''} favored` :
                     `${count} stock${count !== 1 ? 's' : ''}`}
                  </span>
                </div>
                <span className="text-gray-500 text-[10px] group-hover:text-emerald-600 transition-colors">
                  {isExpanded ? '▾' : '▸'}
                </span>
              </div>
            </button>

            {/* Connector line */}
            {i < FUNNEL_STEPS.length - 1 && !isExpanded && (
              <div className="ml-[22px] w-px h-2 bg-gray-200" />
            )}

            {/* Expanded Detail */}
            {isExpanded && (
              <div className="ml-8 mr-2 mb-2 panel p-3 animate-slide-up">
                {step.key === 'theses' && <ThesisDetail theses={data.active_theses} />}
                {step.key === 'sectors' && <SectorDetail tilts={data.sector_tilts} />}
                {step.key === 'expressions' && (
                  <StockList
                    items={data.stock_expressions.map(e => ({
                      symbol: e.symbol,
                      score: e.thesis_score,
                      label: e.sector,
                      narrative: e.narrative,
                    }))}
                    onSelect={onSelectSymbol}
                    selectedSymbol={selectedSymbol}
                  />
                )}
                {step.key === 'convergent' && (
                  <StockList
                    items={data.convergent_stocks.map(c => ({
                      symbol: c.symbol,
                      score: c.convergence_score,
                      label: `${c.conviction} | ${c.module_count} modules`,
                      narrative: c.narrative,
                    }))}
                    onSelect={onSelectSymbol}
                    selectedSymbol={selectedSymbol}
                  />
                )}
                {step.key === 'actionable' && (
                  <ActionableDetail
                    stocks={data.actionable}
                    onSelect={onSelectSymbol}
                    selectedSymbol={selectedSymbol}
                  />
                )}
                {step.key === 'universe' && (
                  <p className="text-[10px] text-gray-500">
                    S&P 500 + S&P 400 constituents, crypto majors, and commodity futures.
                    Total: {counts.universe} instruments scanned daily.
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Funnel summary */}
      <div className="mt-4 pt-3 border-t border-gray-200">
        <div className="flex items-center gap-2 text-[10px] text-gray-500 tracking-widest">
          <span>{counts.universe}</span>
          <span className="text-emerald-600">→</span>
          <span>{counts.expressions}</span>
          <span className="text-emerald-600">→</span>
          <span>{counts.convergent}</span>
          <span className="text-emerald-600">→</span>
          <span className="text-emerald-600 font-bold">{counts.actionable} ACTIONABLE</span>
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ── */

function ThesisDetail({ theses }: { theses: ThesisDetailType[] }) {
  if (!theses.length) {
    return (
      <p className="text-[10px] text-gray-500">
        No strong macro theses active. Neutral regime — stock-picking and convergence matter most.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {theses.map((t) => (
        <div key={t.key} className="flex items-start gap-2">
          <span className="text-emerald-600 text-[10px] mt-0.5">▸</span>
          <div>
            <span className="text-[11px] text-gray-900 font-bold tracking-wider uppercase">
              {t.key.replace(/_/g, ' ')}
            </span>
            <p className="text-[10px] text-gray-500 mt-0.5">{t.description}</p>
            <div className="flex gap-2 mt-1 flex-wrap">
              {t.bullish_sectors.map((s) => (
                <span key={s} className="text-[10px] px-1.5 py-0.5 rounded-lg bg-emerald-600/10 text-emerald-600 border border-emerald-600/20">
                  {s}
                </span>
              ))}
              {t.bearish_sectors.map((s) => (
                <span key={s} className="text-[10px] px-1.5 py-0.5 rounded-lg bg-rose-600/10 text-rose-600 border border-rose-600/20">
                  {s}
                </span>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function SectorDetail({ tilts }: { tilts: { sector: string; tilt: number; stock_count: number; favored: boolean }[] }) {
  const sorted = [...tilts].sort((a, b) => b.tilt - a.tilt);
  return (
    <div className="grid grid-cols-2 gap-1">
      {sorted.map((s) => (
        <div
          key={s.sector}
          className={`flex items-center justify-between px-2 py-1.5 rounded-lg text-[10px] ${
            s.favored
              ? 'bg-emerald-600/5 border border-emerald-600/20'
              : s.tilt < 0
              ? 'bg-rose-600/5 border border-rose-600/10'
              : 'bg-gray-100/20 border border-gray-200'
          }`}
        >
          <span className={s.favored ? 'text-emerald-600' : s.tilt < 0 ? 'text-rose-600' : 'text-gray-500'}>
            {s.sector}
          </span>
          <span className="text-gray-500 font-mono">
            {s.tilt > 0 ? '+' : ''}{s.tilt} | {s.stock_count}
          </span>
        </div>
      ))}
    </div>
  );
}

function StockList({
  items,
  onSelect,
  selectedSymbol,
}: {
  items: { symbol: string; score: number; label: string; narrative: string }[];
  onSelect: (s: string) => void;
  selectedSymbol: string | null;
}) {
  const shown = items.slice(0, 15);
  return (
    <div className="space-y-1">
      {shown.map((item) => (
        <button
          key={item.symbol}
          onClick={() => onSelect(item.symbol)}
          className={`w-full text-left flex items-center gap-3 px-2 py-1.5 rounded-lg transition-colors ${
            selectedSymbol === item.symbol
              ? 'bg-emerald-600/10 border border-emerald-600/30'
              : 'hover:bg-white/[0.02] border border-transparent'
          }`}
        >
          <Link
            href={`/asset/${item.symbol}`}
            onClick={(e) => e.stopPropagation()}
            className="text-[11px] font-bold text-gray-900 hover:text-emerald-600 transition-colors w-14 shrink-0"
          >
            {item.symbol}
          </Link>
          <span className="text-[10px] text-gray-500 flex-1 truncate">{item.label}</span>
          <span className="text-[10px] font-mono text-emerald-600 w-8 text-right">
            {item.score.toFixed(0)}
          </span>
        </button>
      ))}
      {items.length > 15 && (
        <p className="text-[10px] text-gray-500 text-center mt-1">
          +{items.length - 15} more
        </p>
      )}
    </div>
  );
}

function ActionableDetail({
  stocks,
  onSelect,
  selectedSymbol,
}: {
  stocks: FunnelData['actionable'];
  onSelect: (s: string) => void;
  selectedSymbol: string | null;
}) {
  if (!stocks.length) {
    return (
      <p className="text-[10px] text-gray-500">
        No stocks pass all filters. Check convergence and risk gate requirements.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {stocks.map((s) => (
        <button
          key={s.symbol}
          onClick={() => onSelect(s.symbol)}
          className={`w-full text-left panel p-3 transition-colors ${
            selectedSymbol === s.symbol ? 'border-emerald-600/50' : ''
          }`}
        >
          <div className="flex items-center justify-between mb-1">
            <Link
              href={`/asset/${s.symbol}`}
              onClick={(e) => e.stopPropagation()}
              className="font-display text-sm font-bold text-emerald-600 hover:underline"
            >
              {s.symbol}
            </Link>
            <span className={`text-[10px] px-2 py-0.5 rounded-lg font-bold tracking-wider ${
              s.conviction === 'HIGH'
                ? 'bg-emerald-600/20 text-emerald-600 border border-emerald-600/30'
                : 'bg-amber-600/20 text-amber-600 border border-amber-600/30'
            }`}>
              {s.conviction}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-2 text-[10px] mt-2">
            <div>
              <span className="text-gray-500 block">Entry</span>
              <span className="text-gray-900">${s.entry?.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500 block">Stop</span>
              <span className="text-rose-600">${s.stop?.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500 block">Target</span>
              <span className="text-emerald-600">${s.target?.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-gray-500 block">R:R</span>
              <span className="text-emerald-600 font-bold">{s.rr}:1</span>
            </div>
          </div>
          <p className="text-[10px] text-gray-500 mt-2 truncate">{s.narrative}</p>
        </button>
      ))}
    </div>
  );
}
