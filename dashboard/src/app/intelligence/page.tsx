'use client';

import { useState } from 'react';
import RegulatoryTab from '@/components/RegulatoryTab';
import AIExecTab from '@/components/AIExecTab';
import PredictionsTab from '@/components/PredictionsTab';

const TABS = ['Regulatory', 'AI Exec', 'Predictions'] as const;
type Tab = (typeof TABS)[number];

export default function IntelligencePage() {
  const [tab, setTab] = useState<Tab>('Regulatory');

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-gray-900 tracking-tight">
          INTELLIGENCE
        </h1>
        <p className="text-[10px] text-gray-500 tracking-widest mt-1">
          AI REGULATORY | EXECUTIVE TRACKER | PREDICTION MARKETS
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

      {tab === 'Regulatory' && <RegulatoryTab />}
      {tab === 'AI Exec' && <AIExecTab />}
      {tab === 'Predictions' && <PredictionsTab />}
    </div>
  );
}
