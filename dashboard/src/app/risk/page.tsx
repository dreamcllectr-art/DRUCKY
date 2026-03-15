'use client';

import { useState } from 'react';
import SignalConflictsTab from '@/components/SignalConflictsTab';
import StressTestTab from '@/components/StressTestTab';
import ThesisTab from '@/components/ThesisTab';

const TABS = ['Conflicts', 'Stress Test', 'Thesis Lab'] as const;
type Tab = (typeof TABS)[number];

export default function RiskPage() {
  const [tab, setTab] = useState<Tab>('Conflicts');

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-gray-900 tracking-tight">
          RISK & THESIS
        </h1>
        <p className="text-[10px] text-gray-500 tracking-widest mt-1">
          SIGNAL CONFLICTS | STRESS TESTING | THESIS LAB
        </p>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-[10px] tracking-widest whitespace-nowrap transition-all border-b-2 ${
              tab === t
                ? 'text-emerald-600 border-emerald-600'
                : 'text-gray-500 border-transparent hover:text-gray-700'
            }`}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      {tab === 'Conflicts' && <SignalConflictsTab />}
      {tab === 'Stress Test' && <StressTestTab />}
      {tab === 'Thesis Lab' && <ThesisTab />}
    </div>
  );
}
