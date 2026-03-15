'use client';

import React, { useEffect, useState } from 'react';
import { api, type PerformanceSummary, type ModulePerformance, type TrackRecordMonth, type WeightHistoryEntry } from '@/lib/api';
import { PerformanceSufficiencyBadge } from '@/components/PerformanceShared';
import { PerformanceOverviewTab } from '@/components/PerformanceOverviewTab';
import { PerformanceModuleTab } from '@/components/PerformanceModuleTab';
import { PerformanceTrackRecordTab } from '@/components/PerformanceTrackRecordTab';
import { PerformanceWeightsTab } from '@/components/PerformanceWeightsTab';
import ErrorBoundary from '@/components/ErrorBoundary';

const TABS = [
  { key: 'overview', label: 'OVERVIEW' },
  { key: 'modules', label: 'MODULE LEADERBOARD' },
  { key: 'track-record', label: 'TRACK RECORD' },
  { key: 'weights', label: 'WEIGHT EVOLUTION' },
] as const;
type TabKey = (typeof TABS)[number]['key'];

function PerformancePageInner() {
  const [tab, setTab] = useState<TabKey>('overview');
  const [summary, setSummary] = useState<PerformanceSummary | null>(null);
  const [modules, setModules] = useState<ModulePerformance[]>([]);
  const [trackRecord, setTrackRecord] = useState<TrackRecordMonth[]>([]);
  const [weightHistory, setWeightHistory] = useState<WeightHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.performanceSummary().catch(() => null),
      api.performanceModules().catch(() => []),
      api.performanceTrackRecord().catch(() => []),
      api.performanceWeightHistory().catch(() => []),
    ]).then(([s, m, tr, wh]) => {
      if (s) setSummary(s);
      setModules(m as ModulePerformance[]); setTrackRecord(tr as TrackRecordMonth[]); setWeightHistory(wh as WeightHistoryEntry[]);
    }).catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="p-8"><div className="panel p-6 text-center">
        <div className="text-red-400 mb-2">Failed to load performance data</div>
        <div className="text-sm text-gray-500">{error}</div>
      </div></div>
    );
  }

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-display font-bold text-emerald-600 tracking-wider">PERFORMANCE -- DATA MOAT</h1>
          <p className="text-xs text-gray-500 mt-1">Signal accuracy, module performance, and adaptive weight optimization</p>
        </div>
        {summary && <PerformanceSufficiencyBadge sufficient={summary.data_sufficient} days={summary.days_running} signals={summary.total_signals} />}
      </div>
      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-xs font-display tracking-wider transition-colors ${tab === t.key ? 'text-emerald-600 border-b-2 border-emerald-600' : 'text-gray-500 hover:text-gray-700'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {!summary ? (
        <div className="panel p-8 text-center text-gray-500 animate-pulse">Loading...</div>
      ) : tab === 'overview' ? (
        <PerformanceOverviewTab summary={summary} />
      ) : tab === 'modules' ? (
        <PerformanceModuleTab modules={modules} />
      ) : tab === 'track-record' ? (
        <PerformanceTrackRecordTab data={trackRecord} />
      ) : (
        <PerformanceWeightsTab history={weightHistory} />
      )}
    </div>
  );
}

export default function PerformanceContent() {
  return <ErrorBoundary><PerformancePageInner /></ErrorBoundary>;
}
