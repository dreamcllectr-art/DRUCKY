'use client';

import { useState } from 'react';
import SynthesisContent from '@/components/SynthesisContent';
import WorldviewTab from '@/components/WorldviewTab';

const TABS = ['Convergence', 'Worldview'] as const;

export default function SynthesisPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]>('Convergence');

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-gray-900 tracking-tight">SYNTHESIS</h1>
        <p className="text-[10px] text-gray-500 tracking-widest mt-1 uppercase">All signals converged + global macro worldview</p>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map(t => (<button key={t} onClick={() => setTab(t)} className={`px-4 py-2 text-[10px] tracking-widest border-b-2 transition-all ${tab === t ? 'text-emerald-600 border-emerald-600' : 'text-gray-500 border-transparent hover:text-gray-700'}`}>{t.toUpperCase()}</button>))}
      </div>

      {tab === 'Convergence' && <SynthesisContent />}
      {tab === 'Worldview' && <WorldviewTab />}
    </div>
  );
}
