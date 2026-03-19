'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { FunnelState } from '@/lib/api';
import FunnelProgressBar from './FunnelProgressBar';
import ConvictionFilter from './ConvictionFilter';
import TechnicalGate from './TechnicalGate';
import FilterPanel from './FilterPanel';
import SlideOverPanel from '@/components/shared/SlideOverPanel';
import { fg } from '@/lib/styles';

// Lazy-loaded stage components for stages 1-3
function UniverseStage({ state }: { state: FunnelState }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm text-center">
      <div className="text-3xl font-bold text-gray-900">{state.universe}</div>
      <div className="text-xs text-gray-500 mt-1">equities in universe</div>
      <div className="text-[10px] text-gray-400 mt-2">29 convergence modules active</div>
    </div>
  );
}

function AssetClassStage() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.environment().then(setData); }, []);
  if (!data) return <div className="text-gray-400 text-sm p-4 text-center">Loading...</div>;
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-3">Asset Class Regime Tilt</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {(data.asset_classes || []).map((ac: any, i: number) => (
          <div key={i} className="border border-gray-100 rounded-lg p-3 bg-gray-50">
            <div className="text-xs font-semibold text-gray-700">{ac.asset_class}</div>
            <div className="text-sm font-bold mt-1" {...fg(ac.regime_signal === 'overweight' ? '#059669' : ac.regime_signal === 'underweight' ? '#e11d48' : '#d97706')}>
              {(ac.regime_signal || 'neutral').toUpperCase()}
            </div>
          </div>
        ))}
        {(!data.asset_classes || data.asset_classes.length === 0) && (
          <div className="col-span-4 text-[10px] text-gray-400 text-center py-4">Equities: Active | Bonds: Neutral | Commodities: Neutral | Crypto: Neutral</div>
        )}
      </div>
    </div>
  );
}

function SectorStage({ onSymbolClick }: { onSymbolClick: (s: string) => void }) {
  const [sectors, setSectors] = useState<any[]>([]);
  useEffect(() => { api.funnelStage(3).then(setSectors); }, []);
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {sectors.map((s, i) => {
        const flagged = (s.rotation_score || 50) < 30;
        return (
          <div key={i} className={`bg-white rounded-xl border shadow-sm p-4 transition-opacity ${flagged ? 'opacity-50 border-amber-200' : 'border-gray-200'}`}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-900">{s.sector}</span>
              {flagged && <span className="text-[8px] text-amber-600 bg-amber-50 px-1 py-0.5 rounded uppercase">flagged</span>}
            </div>
            <div className="text-lg font-bold mt-1" {...fg(s.rotation_score >= 50 ? '#059669' : s.rotation_score >= 30 ? '#d97706' : '#e11d48')}>
              {s.rotation_score?.toFixed(0) || '?'}
            </div>
            <div className="text-[9px] text-gray-400 mt-1">{s.stock_count || 0} stocks | {s.quadrant || '?'}</div>
            {s.thesis && <div className="text-[9px] text-gray-500 mt-1 truncate">{s.thesis}</div>}
          </div>
        );
      })}
      {sectors.length === 0 && <div className="col-span-4 text-gray-400 text-sm text-center p-8">Loading sectors...</div>}
    </div>
  );
}

function PositionSizingStage({ onSymbolClick }: { onSymbolClick: (s: string) => void }) {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => { api.convictionBoard().then(setItems); }, []);
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 text-[9px] text-gray-400 tracking-widest uppercase">Position Sizing</div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-gray-100 text-[8px] text-gray-400 tracking-widest uppercase">
            <th className="text-left px-4 py-2">Symbol</th>
            <th className="text-right px-2 py-2">Entry</th>
            <th className="text-right px-2 py-2">Stop</th>
            <th className="text-right px-2 py-2">Target</th>
            <th className="text-right px-2 py-2">R:R</th>
            <th className="text-right px-2 py-2">Shares</th>
            <th className="text-right px-4 py-2">$ Size</th>
          </tr>
        </thead>
        <tbody>
          {items.map(item => (
            <tr key={item.symbol} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
              <td className="px-4 py-2">
                <button onClick={() => onSymbolClick(item.symbol)} className="font-semibold text-gray-900 hover:text-emerald-600">{item.symbol}</button>
              </td>
              <td className="px-2 py-2 text-right font-mono text-gray-600">{item.entry_price?.toFixed(2) || '\u2014'}</td>
              <td className="px-2 py-2 text-right font-mono text-rose-600">{item.stop_loss?.toFixed(2) || '\u2014'}</td>
              <td className="px-2 py-2 text-right font-mono text-emerald-600">{item.target_price?.toFixed(2) || '\u2014'}</td>
              <td className="px-2 py-2 text-right font-mono font-bold text-gray-700">{item.rr_ratio?.toFixed(1) || '\u2014'}</td>
              <td className="px-2 py-2 text-right font-mono text-gray-600">{item.position_size_shares?.toFixed(0) || '\u2014'}</td>
              <td className="px-4 py-2 text-right font-mono text-gray-600">{item.position_size_dollars ? `$${(item.position_size_dollars / 1000).toFixed(0)}k` : '\u2014'}</td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr><td colSpan={7} className="text-center py-8 text-gray-400">
              <div className="text-xs">No positions sized yet</div>
              <div className="text-[10px] text-gray-300 mt-1">171 WATCH-conviction stocks are in the pipeline. Position sizing activates when stocks reach HIGH conviction with valid entry/stop/target levels.</div>
            </td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function FunnelView() {
  const [funnelState, setFunnelState] = useState<FunnelState | null>(null);
  const [activeStage, setActiveStage] = useState(5);
  const [dossierSymbol, setDossierSymbol] = useState<string | null>(null);
  const [dossierData, setDossierData] = useState<any>(null);

  useEffect(() => {
    api.funnel().then(setFunnelState);
  }, []);

  const openDossier = (symbol: string) => {
    setDossierSymbol(symbol);
    api.dossier(symbol).then(setDossierData);
  };

  if (!funnelState) return <div className="text-gray-400 text-sm p-8 text-center">Loading funnel...</div>;

  return (
    <div className="space-y-4">
      <FunnelProgressBar state={funnelState} activeStage={activeStage} onStageClick={setActiveStage} />

      {/* Stage Content */}
      {activeStage === 1 && <UniverseStage state={funnelState} />}
      {activeStage === 2 && <AssetClassStage />}
      {activeStage === 3 && <SectorStage onSymbolClick={openDossier} />}
      {activeStage === 4 && <TechnicalGate onSymbolClick={openDossier} />}
      {activeStage === 5 && <ConvictionFilter onSymbolClick={openDossier} />}
      {activeStage === 6 && <PositionSizingStage onSymbolClick={openDossier} />}

      {/* Filter (always accessible) */}
      {activeStage === 0 && <FilterPanel onSymbolClick={openDossier} />}

      {/* Dossier Slide-Over */}
      <SlideOverPanel open={!!dossierSymbol} onClose={() => { setDossierSymbol(null); setDossierData(null); }} title={dossierSymbol || ''}>
        {dossierData ? (
          <DossierQuick data={dossierData} />
        ) : (
          <div className="text-gray-400 text-sm text-center py-8">Loading dossier...</div>
        )}
      </SlideOverPanel>
    </div>
  );
}

function DossierQuick({ data }: { data: any }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="text-lg font-bold text-gray-900">{data.symbol}</div>
        <div className="text-xs text-gray-500">{data.meta?.name || ''}{data.meta?.sector ? ` | ${data.meta.sector}` : ''}{data.meta?.industry ? ` | ${data.meta.industry}` : ''}</div>
      </div>
      {data.convergence ? (
        <div className="flex items-center gap-4">
          <div>
            <div className="text-[9px] text-gray-400 tracking-widest uppercase">Convergence</div>
            <div className="text-2xl font-bold" {...fg((data.convergence.convergence_score ?? 0) >= 60 ? '#059669' : '#d97706')}>
              {data.convergence.convergence_score?.toFixed(0) ?? '\u2014'}
            </div>
          </div>
          <div>
            <div className="text-[9px] text-gray-400 tracking-widest uppercase">Conviction</div>
            <div className="text-sm font-semibold text-gray-700">{data.convergence.conviction_level || 'N/A'}</div>
          </div>
          <div>
            <div className="text-[9px] text-gray-400 tracking-widest uppercase">Modules</div>
            <div className="text-sm font-semibold text-gray-700">{data.convergence.module_count ?? '\u2014'}</div>
          </div>
        </div>
      ) : (
        <div className="bg-gray-50 rounded-lg p-3 text-[10px] text-gray-400">No convergence data available for this symbol</div>
      )}
      {data.signal ? (
        <div className="bg-gray-50 rounded-lg p-3">
          <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-1">Trade Setup</div>
          <div className="grid grid-cols-4 gap-3 text-[11px]">
            <div><span className="text-gray-400">Entry:</span> <span className="font-mono">{data.signal.entry_price != null ? `$${data.signal.entry_price.toFixed(2)}` : '\u2014'}</span></div>
            <div><span className="text-gray-400">Stop:</span> <span className="font-mono text-rose-600">{data.signal.stop_loss != null ? `$${data.signal.stop_loss.toFixed(2)}` : '\u2014'}</span></div>
            <div><span className="text-gray-400">Target:</span> <span className="font-mono text-emerald-600">{data.signal.target_price != null ? `$${data.signal.target_price.toFixed(2)}` : '\u2014'}</span></div>
            <div><span className="text-gray-400">R:R:</span> <span className="font-mono font-bold">{data.signal.rr_ratio?.toFixed(1) || '\u2014'}</span></div>
          </div>
        </div>
      ) : (
        <div className="bg-gray-50 rounded-lg p-3 text-[10px] text-gray-400">No active trade setup for this symbol</div>
      )}
      <div>
        <div className="text-[9px] text-gray-400 tracking-widest uppercase mb-1">Thesis</div>
        <div className="text-xs text-gray-700 leading-relaxed">{data.thesis || 'No thesis generated yet.'}</div>
      </div>
    </div>
  );
}
