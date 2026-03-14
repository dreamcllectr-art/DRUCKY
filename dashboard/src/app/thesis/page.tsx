'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { FunnelData, MentalModel, ThesisChecklist } from '@/lib/api';
import FunnelView from '@/components/FunnelView';
import MentalModelCard from '@/components/MentalModelCard';
import BottomUpChecklist from '@/components/BottomUpChecklist';

export default function ThesisLabPage() {
  const [funnelData, setFunnelData] = useState<FunnelData | null>(null);
  const [models, setModels] = useState<MentalModel[]>([]);
  const [regime, setRegime] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [checklist, setChecklist] = useState<ThesisChecklist | null>(null);
  const [loading, setLoading] = useState(true);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [modelFilter, setModelFilter] = useState<string | null>(null);

  // Load funnel + models on mount
  useEffect(() => {
    Promise.allSettled([api.thesisFunnel(), api.thesisModels()])
      .then(([funnelRes, modelsRes]) => {
        if (funnelRes.status === 'fulfilled') setFunnelData(funnelRes.value);
        if (modelsRes.status === 'fulfilled') {
          setModels(modelsRes.value.models);
          setRegime(modelsRes.value.regime);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  // Load checklist when symbol selected
  useEffect(() => {
    if (!selectedSymbol) {
      setChecklist(null);
      return;
    }
    setChecklistLoading(true);
    api.thesisChecklist(selectedSymbol)
      .then(setChecklist)
      .catch(() => setChecklist(null))
      .finally(() => setChecklistLoading(false));
  }, [selectedSymbol]);

  const categories = [...new Set(models.map((m) => m.category))];
  const filteredModels = modelFilter
    ? models.filter((m) => m.category === modelFilter)
    : models;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-terminal-green glow-green font-display text-lg tracking-widest animate-pulse-green">
            BUILDING THESIS...
          </p>
          <p className="text-[10px] text-terminal-dim mt-2 tracking-widest">
            ANALYZING MACRO REGIME / FILTERING UNIVERSE / SCORING MODELS
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-[1400px]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-wide">
            THESIS LAB
          </h1>
          <p className="text-[10px] text-terminal-dim mt-1 tracking-widest uppercase">
            Top-down funnel + mental models + bottom-up checklist
          </p>
        </div>
        {regime && (
          <span className={`text-[10px] px-3 py-1.5 rounded-sm font-bold tracking-widest uppercase ${
            regime.includes('risk_on')
              ? 'bg-terminal-green/10 text-terminal-green border border-terminal-green/20'
              : regime.includes('risk_off')
              ? 'bg-terminal-red/10 text-terminal-red border border-terminal-red/20'
              : 'bg-terminal-amber/10 text-terminal-amber border border-terminal-amber/20'
          }`}>
            {regime.replace(/_/g, ' ')}
          </span>
        )}
      </div>

      {/* Main content: Two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left: Funnel (2/3) */}
        <div className="lg:col-span-2">
          {funnelData ? (
            <FunnelView
              data={funnelData}
              onSelectSymbol={setSelectedSymbol}
              selectedSymbol={selectedSymbol}
            />
          ) : (
            <div className="panel p-6 text-center">
              <p className="text-terminal-dim text-[11px]">
                No funnel data available. Run the daily pipeline first.
              </p>
            </div>
          )}
        </div>

        {/* Right: Mental Models (1/3) */}
        <div className="lg:col-span-1">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[10px] text-terminal-dim tracking-widest uppercase font-bold">
              MENTAL MODELS
            </h2>
            <span className="text-[9px] text-terminal-dim">
              {filteredModels.length} models
            </span>
          </div>

          {/* Category filters */}
          <div className="flex gap-1.5 mb-3 flex-wrap">
            <button
              onClick={() => setModelFilter(null)}
              className={`text-[9px] px-2 py-1 rounded-sm tracking-wider transition-colors ${
                !modelFilter
                  ? 'bg-terminal-green/10 text-terminal-green border border-terminal-green/20'
                  : 'text-terminal-dim border border-terminal-border hover:border-terminal-dim'
              }`}
            >
              ALL
            </button>
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setModelFilter(modelFilter === cat ? null : cat)}
                className={`text-[9px] px-2 py-1 rounded-sm tracking-wider transition-colors ${
                  modelFilter === cat
                    ? 'bg-terminal-green/10 text-terminal-green border border-terminal-green/20'
                    : 'text-terminal-dim border border-terminal-border hover:border-terminal-dim'
                }`}
              >
                {cat.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Model cards */}
          <div className="space-y-2 max-h-[calc(100vh-220px)] overflow-y-auto pr-1">
            {filteredModels.map((m) => (
              <MentalModelCard key={m.name} {...m} />
            ))}
          </div>
        </div>
      </div>

      {/* Bottom: Checklist (appears when stock selected) */}
      {selectedSymbol && (
        <div className="mt-6">
          <div className="flex items-center gap-2 mb-3">
            <h2 className="text-[10px] text-terminal-dim tracking-widest uppercase font-bold">
              BOTTOM-UP CHECKLIST
            </h2>
            <span className="text-[10px] text-terminal-green font-bold">{selectedSymbol}</span>
          </div>
          {checklistLoading ? (
            <div className="panel p-6 text-center">
              <p className="text-terminal-green glow-green text-[11px] animate-pulse-green tracking-widest">
                LOADING CHECKLIST...
              </p>
            </div>
          ) : checklist ? (
            <BottomUpChecklist data={checklist} onClose={() => setSelectedSymbol(null)} />
          ) : (
            <div className="panel p-6 text-center">
              <p className="text-terminal-dim text-[11px]">No data available for {selectedSymbol}.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
