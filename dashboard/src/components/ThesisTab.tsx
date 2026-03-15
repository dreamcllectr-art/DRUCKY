'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { FunnelData, MentalModel, ThesisChecklist } from '@/lib/api';
import FunnelView from '@/components/FunnelView';
import MentalModelCard from '@/components/MentalModelCard';
import BottomUpChecklist from '@/components/BottomUpChecklist';

export default function ThesisTab() {
  const [funnelData, setFunnelData] = useState<FunnelData | null>(null);
  const [models, setModels] = useState<MentalModel[]>([]);
  const [regime, setRegime] = useState('');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [checklist, setChecklist] = useState<ThesisChecklist | null>(null);
  const [loading, setLoading] = useState(true);
  const [checklistLoading, setChecklistLoading] = useState(false);

  useEffect(() => {
    Promise.allSettled([api.thesisFunnel(), api.thesisModels()]).then(([f, m]) => {
      if (f.status === 'fulfilled') setFunnelData(f.value);
      if (m.status === 'fulfilled') { setModels(m.value.models); setRegime(m.value.regime); }
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedSymbol) { setChecklist(null); return; }
    setChecklistLoading(true);
    api.thesisChecklist(selectedSymbol).then(setChecklist).catch(() => setChecklist(null)).finally(() => setChecklistLoading(false));
  }, [selectedSymbol]);

  if (loading) return <div className="text-gray-500 animate-pulse py-8 text-center">Loading thesis...</div>;

  return (
    <div className="space-y-6">
      {regime && <span className={`text-[10px] px-3 py-1.5 rounded-lg font-bold tracking-widest uppercase ${regime.includes('risk_on') ? 'bg-emerald-600/10 text-emerald-600 border border-emerald-600/20' : regime.includes('risk_off') ? 'bg-rose-600/10 text-rose-600 border border-rose-600/20' : 'bg-amber-600/10 text-amber-600 border border-amber-600/20'}`}>{regime.replace(/_/g, ' ')}</span>}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {funnelData ? <FunnelView data={funnelData} onSelectSymbol={setSelectedSymbol} selectedSymbol={selectedSymbol} /> : <div className="panel p-6 text-center text-gray-500 text-[11px]">No funnel data.</div>}
        </div>
        <div className="lg:col-span-1">
          <h2 className="text-[10px] text-gray-500 tracking-widest uppercase font-bold mb-3">MENTAL MODELS</h2>
          <div className="space-y-2 max-h-[calc(100vh-300px)] overflow-y-auto pr-1">
            {models.map(m => <MentalModelCard key={m.name} {...m} />)}
          </div>
        </div>
      </div>
      {selectedSymbol && (
        <div>
          <h2 className="text-[10px] text-gray-500 tracking-widest uppercase font-bold mb-3">CHECKLIST: <span className="text-emerald-600">{selectedSymbol}</span></h2>
          {checklistLoading ? <div className="panel p-6 text-center text-emerald-600 animate-pulse">Loading...</div>
            : checklist ? <BottomUpChecklist data={checklist} onClose={() => setSelectedSymbol(null)} />
            : <div className="panel p-6 text-center text-gray-500 text-[11px]">No data for {selectedSymbol}.</div>}
        </div>
      )}
    </div>
  );
}
