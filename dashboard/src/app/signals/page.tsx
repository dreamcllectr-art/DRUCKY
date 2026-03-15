'use client';

import { useState } from 'react';
import InsiderTab from '@/components/InsiderTab';
import AltDataTab from '@/components/AltDataTab';
import DisplacementTab from '@/components/DisplacementTab';
import EstimateMomentumTab from '@/components/EstimateMomentumTab';
import ConsensusBlindspotTab from '@/components/ConsensusBlindspotTab';
import PairsTab from '@/components/PairsTab';
import MATab from '@/components/MATab';

const TABS = [
  'Insider',
  'Blindspots',
  'Displacement',
  'Pairs',
  'Est. Momentum',
  'M&A',
  'Alt Data',
] as const;

type Tab = (typeof TABS)[number];

export default function SignalsPage() {
  const [tab, setTab] = useState<Tab>('Insider');

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-gray-900 tracking-tight">
          SIGNAL INTELLIGENCE
        </h1>
        <p className="text-[10px] text-gray-500 tracking-widest mt-1">
          INSIDER ACTIVITY | BLINDSPOTS | DISPLACEMENT | PAIRS | ESTIMATES | M&A | ALT DATA
        </p>
      </div>

      <div className="flex gap-1 border-b border-gray-200 overflow-x-auto">
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

      {tab === 'Insider' && <InsiderTab />}
      {tab === 'Blindspots' && <ConsensusBlindspotTab />}
      {tab === 'Displacement' && <DisplacementTab />}
      {tab === 'Pairs' && <PairsTab />}
      {tab === 'Est. Momentum' && <EstimateMomentumTab />}
      {tab === 'M&A' && <MATab />}
      {tab === 'Alt Data' && <AltDataTab />}
    </div>
  );
}
