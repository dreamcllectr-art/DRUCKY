'use client';

import { useEffect, useState } from 'react';
import { api, type AltDataSignal } from '@/lib/api';

type SourceFilter = 'all' | string;

export default function AltDataPage() {
  const [signals, setSignals] = useState<AltDataSignal[]>([]);
  const [loading, setLoading] = useState(true);
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');

  useEffect(() => {
    api
      .altData(30)
      .then(setSignals)
      .catch(() => setSignals([]))
      .finally(() => setLoading(false));
  }, []);

  const sources = [...new Set(signals.map((s) => s.source))];

  const filtered =
    sourceFilter === 'all' ? signals : signals.filter((s) => s.source === sourceFilter);

  const dirColor = (dir: string) => {
    if (dir === 'bullish') return 'text-terminal-green';
    if (dir === 'bearish') return 'text-terminal-red';
    return 'text-terminal-amber';
  };

  const strengthColor = (v: number) => {
    if (v >= 70) return { bg: 'rgba(0,255,65,0.15)', fg: '#00FF41' };
    if (v >= 40) return { bg: 'rgba(255,184,0,0.15)', fg: '#FFB800' };
    return { bg: 'rgba(255,255,255,0.05)', fg: '#888' };
  };

  const sourceIcon = (src: string) => {
    if (src.includes('enso') || src.includes('noaa')) return 'ENSO';
    if (src.includes('ndvi') || src.includes('modis') || src.includes('nasa')) return 'SAT';
    if (src.includes('weather') || src.includes('noaa_weather')) return 'WX';
    if (src.includes('fire') || src.includes('firms')) return 'FIRE';
    if (src.includes('ship') || src.includes('ais')) return 'SHIP';
    if (src.includes('crop') || src.includes('usda')) return 'CROP';
    return 'ALT';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="text-terminal-green animate-pulse glow-green">
          SCANNING ALTERNATIVE DATA FEEDS...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-terminal-bright tracking-tight">
          ALTERNATIVE DATA & SATELLITE
        </h1>
        <p className="text-[10px] text-terminal-dim tracking-widest mt-1">
          ENSO/ONI INDEX — NASA NDVI CROP HEALTH — WEATHER — WILDFIRES — SHIPPING
        </p>
      </div>

      {/* Source filter pills */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSourceFilter('all')}
          className={`px-3 py-1.5 rounded text-[10px] tracking-widest font-bold transition-all ${
            sourceFilter === 'all'
              ? 'bg-terminal-green/15 text-terminal-green border border-terminal-green/30'
              : 'bg-terminal-panel text-terminal-dim border border-terminal-border hover:border-terminal-muted'
          }`}
        >
          ALL ({signals.length})
        </button>
        {sources.map((src) => (
          <button
            key={src}
            onClick={() => setSourceFilter(src)}
            className={`px-3 py-1.5 rounded text-[10px] tracking-widest font-bold transition-all ${
              sourceFilter === src
                ? 'bg-terminal-green/15 text-terminal-green border border-terminal-green/30'
                : 'bg-terminal-panel text-terminal-dim border border-terminal-border hover:border-terminal-muted'
            }`}
          >
            {src.toUpperCase()} ({signals.filter((s) => s.source === src).length})
          </button>
        ))}
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-3">
        <div className="panel px-4 py-3">
          <div className="text-2xl font-display font-bold text-terminal-green">
            {signals.filter((s) => s.signal_direction === 'bullish').length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">BULLISH SIGNALS</div>
        </div>
        <div className="panel px-4 py-3">
          <div className="text-2xl font-display font-bold text-terminal-red">
            {signals.filter((s) => s.signal_direction === 'bearish').length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">BEARISH SIGNALS</div>
        </div>
        <div className="panel px-4 py-3">
          <div className="text-2xl font-display font-bold text-terminal-amber">
            {signals.filter((s) => s.signal_strength >= 70).length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">STRONG SIGNALS</div>
        </div>
        <div className="panel px-4 py-3">
          <div className="text-2xl font-display font-bold text-terminal-cyan">
            {sources.length}
          </div>
          <div className="text-[10px] text-terminal-dim tracking-widest mt-1">DATA SOURCES</div>
        </div>
      </div>

      {/* Signals table */}
      <div className="panel overflow-hidden">
        <div className="px-4 py-3 border-b border-terminal-border">
          <h2 className="text-xs text-terminal-bright tracking-widest font-bold">
            ALTERNATIVE DATA SIGNALS
          </h2>
          <p className="text-[10px] text-terminal-dim mt-0.5">
            Weather anomalies, satellite imagery, crop health, shipping data, and macro indicators
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-terminal-border text-terminal-dim tracking-widest uppercase">
                <th className="text-left py-3 px-4 font-normal">Date</th>
                <th className="text-center py-3 px-2 font-normal">Source</th>
                <th className="text-left py-3 px-2 font-normal">Indicator</th>
                <th className="text-right py-3 px-2 font-normal">Value</th>
                <th className="text-right py-3 px-2 font-normal">Z-Score</th>
                <th className="text-center py-3 px-2 font-normal">Direction</th>
                <th className="text-right py-3 px-2 font-normal">Strength</th>
                <th className="text-left py-3 px-2 font-normal">Sectors</th>
                <th className="text-left py-3 px-4 font-normal">Narrative</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-8 text-terminal-dim">
                    No alternative data signals. Run the pipeline to ingest satellite + weather data.
                  </td>
                </tr>
              ) : (
                filtered.map((s, i) => {
                  const sc = strengthColor(s.signal_strength);
                  return (
                    <tr
                      key={`alt-${i}`}
                      className="border-b border-terminal-border/50 hover:bg-terminal-green/[0.03] transition-colors"
                    >
                      <td className="py-2.5 px-4 font-mono text-terminal-dim text-[10px]">
                        {s.date}
                      </td>
                      <td className="py-2.5 px-2 text-center">
                        <span className="px-1.5 py-0.5 rounded-sm text-[9px] font-bold bg-terminal-cyan/15 text-terminal-cyan">
                          {sourceIcon(s.source)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-terminal-text text-[10px]">
                        {s.indicator}
                      </td>
                      <td className="py-2.5 px-2 text-right font-mono text-terminal-bright">
                        {s.value?.toFixed(2) || '—'}
                      </td>
                      <td className={`py-2.5 px-2 text-right font-mono ${
                        Math.abs(s.value_zscore || 0) >= 2
                          ? 'text-terminal-red'
                          : Math.abs(s.value_zscore || 0) >= 1.5
                          ? 'text-terminal-amber'
                          : 'text-terminal-dim'
                      }`}>
                        {s.value_zscore ? (s.value_zscore >= 0 ? '+' : '') + s.value_zscore.toFixed(2) : '—'}
                      </td>
                      <td className={`py-2.5 px-2 text-center font-bold text-[10px] ${dirColor(s.signal_direction)}`}>
                        {s.signal_direction.toUpperCase()}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <span
                          className="px-1.5 py-0.5 rounded-sm text-[10px] font-bold"
                          style={{ backgroundColor: sc.bg, color: sc.fg }}
                        >
                          {s.signal_strength.toFixed(0)}
                        </span>
                      </td>
                      <td className="py-2.5 px-2 text-terminal-dim text-[10px] max-w-[150px] truncate">
                        {s.affected_sectors || '—'}
                      </td>
                      <td className="py-2.5 px-4 text-terminal-dim max-w-[300px] truncate">
                        {s.narrative || '—'}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
