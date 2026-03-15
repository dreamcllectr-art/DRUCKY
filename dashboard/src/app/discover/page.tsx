'use client';

import { useState } from 'react';
import ScreenerTab from '@/components/ScreenerTab';
import SignalBadge from '@/components/SignalBadge';
import DiscoverContent from '@/components/DiscoverContent';

const TABS = ['Discover', 'Screener'] as const;
type Tab = (typeof TABS)[number];

export default function DiscoverPage() {
  const [tab, setTab] = useState<Tab>('Discover');

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-[22px] font-display font-bold text-gray-900 tracking-wider">
          DISCOVER
        </h1>
        <p className="text-[10px] text-gray-500 tracking-widest mt-1 opacity-60">
          Progressive intelligence filter + full universe screener
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

      {tab === 'Discover' && <DiscoverContent />}
      {tab === 'Screener' && <ScreenerTab />}
    </div>
  );
}
