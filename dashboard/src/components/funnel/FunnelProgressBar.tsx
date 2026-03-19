'use client';

import type { FunnelState } from '@/lib/api';
import { cs, fg } from '@/lib/styles';

interface Props {
  state: FunnelState;
  activeStage: number;
  onStageClick: (stage: number) => void;
}

export default function FunnelProgressBar({ state, activeStage, onStageClick }: Props) {
  const stages = [
    { id: 1, label: 'Universe', count: state.universe, icon: '\u25C8' },
    { id: 2, label: 'Asset Class', count: state.sector_passed + state.sector_flagged, icon: '\u25A3' },
    { id: 3, label: 'Sector/Theme', count: state.sector_passed, icon: '\u25D0' },
    { id: 4, label: 'Technical', count: state.technical_passed, icon: '\u223F' },
    { id: 5, label: 'Conviction', count: (state.conviction_high ?? 0) + (state.conviction_notable ?? 0) + (state.conviction_watch ?? 0), icon: '\u25C9' },
    { id: 6, label: 'Actionable', count: state.actionable, icon: '\u2605' },
  ];

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
      <div className="flex items-center gap-1">
        {stages.map((s, i) => {
          const active = s.id === activeStage;
          return (
            <div key={s.id} className="flex items-center">
              <button
                onClick={() => onStageClick(s.id)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg transition-all text-xs ${
                  active
                    ? 'bg-emerald-50 border border-emerald-200 text-emerald-700 shadow-sm'
                    : 'hover:bg-gray-50 text-gray-500 border border-transparent'
                }`}
              >
                <span className="text-[10px]">{s.icon}</span>
                <span className="font-medium tracking-wide">{s.label}</span>
                <span
                  className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${
                    active ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-500'
                  }`}
                >
                  {s.count}
                </span>
              </button>
              {i < stages.length - 1 && (
                <span className="text-gray-300 mx-0.5 text-[10px]">{'\u25B8'}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
