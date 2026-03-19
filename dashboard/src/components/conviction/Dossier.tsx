'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { DossierSummary, DossierEvidence, DossierRisks } from '@/lib/api';
import ModuleHeatstrip from '@/components/shared/ModuleHeatstrip';
import { fg, cs } from '@/lib/styles';
import { scoreColor } from '@/lib/modules';

interface Props {
  symbol: string;
}

function Section({ title, defaultOpen, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  return (
    <div className="border-b border-gray-100 last:border-0">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between px-0 py-3 text-left">
        <span className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold">{title}</span>
        <span className="text-[9px] text-gray-300">{open ? '\u25B4' : '\u25BE'}</span>
      </button>
      {open && <div className="pb-4">{children}</div>}
    </div>
  );
}

export default function Dossier({ symbol }: Props) {
  const [data, setData] = useState<DossierSummary | null>(null);
  const [evidence, setEvidence] = useState<DossierEvidence | null>(null);
  const [risks, setRisks] = useState<DossierRisks | null>(null);
  const [fundamentals, setFundamentals] = useState<Record<string, number> | null>(null);
  const [catalysts, setCatalysts] = useState<any>(null);

  useEffect(() => {
    api.dossier(symbol).then(setData);
  }, [symbol]);

  const loadEvidence = () => { if (!evidence) api.dossierEvidence(symbol).then(setEvidence); };
  const loadRisks = () => { if (!risks) api.dossierRisks(symbol).then(setRisks); };
  const loadFundamentals = () => { if (!fundamentals) api.dossierFundamentals(symbol).then(setFundamentals); };
  const loadCatalysts = () => { if (!catalysts) api.dossierCatalysts(symbol).then(setCatalysts); };

  if (!data) return <div className="text-gray-400 text-sm text-center py-8">Loading dossier...</div>;

  const conv = data.convergence;
  const sig = data.signal;

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center gap-4 pb-3 border-b border-gray-200">
        <div>
          <div className="text-xl font-bold text-gray-900">{symbol}</div>
          <div className="text-xs text-gray-500">{data.meta?.name} | {data.meta?.sector}</div>
        </div>
        {conv && (
          <div className="ml-auto flex items-center gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold" {...fg(scoreColor(conv.convergence_score))}>
                {conv.convergence_score?.toFixed(0)}
              </div>
              <div className="text-[8px] text-gray-400 uppercase tracking-widest">Score</div>
            </div>
            <div className="text-center">
              <div className="text-sm font-bold text-gray-700">{conv.conviction_level}</div>
              <div className="text-[8px] text-gray-400 uppercase tracking-widest">Conviction</div>
            </div>
          </div>
        )}
      </div>

      {/* Thesis */}
      <Section title="Thesis" defaultOpen>
        <div className="text-xs text-gray-700 leading-relaxed">{data.thesis}</div>
      </Section>

      {/* Trade Setup */}
      {sig && (
        <Section title="Trade Setup" defaultOpen>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: 'Signal', value: sig.signal, color: sig.signal?.includes('BUY') ? '#059669' : sig.signal?.includes('SELL') ? '#e11d48' : '#6b7280' },
              { label: 'Entry', value: `$${sig.entry_price?.toFixed(2)}` },
              { label: 'Stop', value: `$${sig.stop_loss?.toFixed(2)}`, color: '#e11d48' },
              { label: 'Target', value: `$${sig.target_price?.toFixed(2)}`, color: '#059669' },
              { label: 'R:R', value: sig.rr_ratio?.toFixed(1) },
              { label: 'Size ($)', value: sig.position_size_dollars ? `$${(sig.position_size_dollars / 1000).toFixed(0)}k` : '\u2014' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-gray-50 rounded-lg p-2.5">
                <div className="text-[8px] text-gray-400 uppercase tracking-widest">{label}</div>
                <div className="text-sm font-mono font-bold" {...fg(color || '#1f2937')}>{value || '\u2014'}</div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Evidence */}
      <Section title="Evidence">
        <div onFocus={loadEvidence} onMouseEnter={loadEvidence}>
          {evidence ? (
            <div className="space-y-3">
              <ModuleHeatstrip scores={evidence.modules} />
              {evidence.top_contributors.slice(0, 7).map((tc, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px]">
                  <span className="shrink-0 w-8 text-right font-mono font-bold" {...fg(scoreColor(tc.score))}>{tc.score.toFixed(0)}</span>
                  <span className="text-gray-600 font-medium uppercase text-[9px] w-20 shrink-0">{tc.module.replace(/_/g, ' ')}</span>
                  <span className="text-gray-500 text-[10px]">{tc.detail || 'Active'}</span>
                </div>
              ))}
            </div>
          ) : (
            <button onClick={loadEvidence} className="text-[10px] text-emerald-600 hover:underline">Load evidence</button>
          )}
        </div>
      </Section>

      {/* Risks */}
      <Section title="Risks">
        <div onMouseEnter={loadRisks}>
          {risks ? (
            <div className="space-y-2">
              {risks.devils_advocate && (
                <div className="bg-rose-50 border border-rose-100 rounded-lg p-3">
                  <div className="text-[9px] text-rose-600 font-semibold uppercase mb-1">Bear Thesis</div>
                  <div className="text-[11px] text-rose-800">{risks.devils_advocate.bear_thesis}</div>
                  {risks.devils_advocate.kill_scenario && <div className="text-[10px] text-rose-600 mt-1">Kill: {risks.devils_advocate.kill_scenario}</div>}
                </div>
              )}
              {risks.conflicts.map((c: any, i: number) => (
                <div key={i} className="text-[10px] text-amber-700 bg-amber-50 rounded px-2 py-1">{c.conflict_type}: {c.description}</div>
              ))}
              {risks.forensic.map((f: any, i: number) => (
                <div key={i} className="text-[10px] text-rose-700 bg-rose-50 rounded px-2 py-1">{f.alert_type} ({f.severity})</div>
              ))}
            </div>
          ) : (
            <button onClick={loadRisks} className="text-[10px] text-emerald-600 hover:underline">Load risks</button>
          )}
        </div>
      </Section>

      {/* Fundamentals */}
      <Section title="Fundamentals">
        <div onMouseEnter={loadFundamentals}>
          {fundamentals ? (
            <div className="grid grid-cols-3 gap-2">
              {Object.entries(fundamentals).slice(0, 12).map(([k, v]) => (
                <div key={k} className="bg-gray-50 rounded p-2">
                  <div className="text-[8px] text-gray-400 uppercase tracking-wider truncate">{k}</div>
                  <div className="text-xs font-mono text-gray-700">{typeof v === 'number' ? v.toFixed(2) : v}</div>
                </div>
              ))}
            </div>
          ) : (
            <button onClick={loadFundamentals} className="text-[10px] text-emerald-600 hover:underline">Load fundamentals</button>
          )}
        </div>
      </Section>

      {/* Catalysts */}
      <Section title="Catalysts">
        <div onMouseEnter={loadCatalysts}>
          {catalysts ? (
            <div className="space-y-2">
              {catalysts.earnings?.map((e: any, i: number) => (
                <div key={i} className="text-[10px] text-gray-700 bg-gray-50 rounded px-2 py-1">Earnings {e.date}: est {e.estimate} | actual {e.actual}</div>
              ))}
              {catalysts.rumors?.map((r: any, i: number) => (
                <div key={i} className="text-[10px] text-amber-700 bg-amber-50 rounded px-2 py-1">M&A: {r.headline} ({r.deal_stage})</div>
              ))}
              {catalysts.insider?.map((ins: any, i: number) => (
                <div key={i} className="text-[10px] text-gray-700 bg-gray-50 rounded px-2 py-1">Insider: score {ins.insider_score} {ins.narrative || ''}</div>
              ))}
              {catalysts.regulatory?.map((r: any, i: number) => (
                <div key={i} className="text-[10px] text-gray-700 bg-gray-50 rounded px-2 py-1">Regulatory: score {r.reg_score}</div>
              ))}
            </div>
          ) : (
            <button onClick={loadCatalysts} className="text-[10px] text-emerald-600 hover:underline">Load catalysts</button>
          )}
        </div>
      </Section>
    </div>
  );
}
