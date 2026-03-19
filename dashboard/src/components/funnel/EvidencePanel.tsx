'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { DossierEvidence, DossierRisks } from '@/lib/api';
import ModuleHeatstrip from '@/components/shared/ModuleHeatstrip';
import { cs, fg } from '@/lib/styles';
import { scoreColor } from '@/lib/modules';

interface Props {
  symbol: string;
}

export default function EvidencePanel({ symbol }: Props) {
  const [evidence, setEvidence] = useState<DossierEvidence | null>(null);
  const [risks, setRisks] = useState<DossierRisks | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.dossierEvidence(symbol),
      api.dossierRisks(symbol),
    ]).then(([ev, ri]) => {
      setEvidence(ev);
      setRisks(ri);
    }).finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div className="text-gray-400 text-[10px] py-3 text-center">Loading evidence...</div>;
  if (!evidence) return null;

  return (
    <div className="space-y-4 py-3">
      {/* Module Heatstrip */}
      <div>
        <div className="text-[8px] text-gray-400 tracking-widest uppercase mb-1.5">Module Scores</div>
        <ModuleHeatstrip scores={evidence.modules} />
      </div>

      {/* Top Contributing Modules */}
      {evidence.top_contributors.length > 0 && (
        <div>
          <div className="text-[8px] text-gray-400 tracking-widest uppercase mb-1.5">Key Evidence</div>
          <div className="space-y-1.5">
            {evidence.top_contributors.slice(0, 5).map((tc, i) => (
              <div key={i} className="flex items-start gap-2 text-[11px]">
                <span
                  className="shrink-0 w-8 text-right font-mono font-bold"
                  {...fg(scoreColor(tc.score))}
                >
                  {tc.score.toFixed(0)}
                </span>
                <span className="text-gray-600 font-medium uppercase text-[9px] w-20 shrink-0 tracking-wider">
                  {tc.module.replace(/_/g, ' ')}
                </span>
                <span className="text-gray-500 text-[10px] leading-tight">
                  {tc.detail || 'Signal active'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Risks */}
      {risks && (
        <div>
          <div className="text-[8px] text-gray-400 tracking-widest uppercase mb-1.5">Risks</div>
          {risks.devils_advocate && (
            <div className="bg-rose-50 border border-rose-100 rounded-lg p-3 mb-2">
              <div className="text-[9px] text-rose-600 font-semibold uppercase tracking-wider mb-1">Devil&apos;s Advocate</div>
              <div className="text-[11px] text-rose-800 leading-relaxed">{risks.devils_advocate.bear_thesis || 'No bear thesis'}</div>
              {risks.devils_advocate.kill_scenario && (
                <div className="text-[10px] text-rose-600 mt-1">Kill scenario: {risks.devils_advocate.kill_scenario}</div>
              )}
            </div>
          )}
          {risks.conflicts.length > 0 && (
            <div className="space-y-1">
              {risks.conflicts.slice(0, 3).map((c: any, i: number) => (
                <div key={i} className="text-[10px] text-amber-700 bg-amber-50 rounded px-2 py-1">
                  <span className="font-semibold">{c.conflict_type}</span>: {c.description}
                </div>
              ))}
            </div>
          )}
          {risks.forensic.length > 0 && (
            <div className="mt-2 space-y-1">
              {risks.forensic.map((f: any, i: number) => (
                <div key={i} className="text-[10px] text-rose-700 bg-rose-50 rounded px-2 py-1">
                  <span className="font-semibold">{f.alert_type}</span> ({f.severity}): {f.details}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
