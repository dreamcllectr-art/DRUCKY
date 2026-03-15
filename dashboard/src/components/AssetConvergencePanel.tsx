import type { ConvergenceSignal } from '@/lib/api';
import ModuleStrip from '@/components/ModuleStrip';
import { MODULES } from '@/lib/modules';

interface ConvergencePanelProps {
  conv: ConvergenceSignal;
}

export function AssetConvergencePanel({ conv }: ConvergencePanelProps) {
  const bullishModules = MODULES.filter(m => {
    const val = (conv as any)[m.key] as number | null;
    return val != null && val >= 50;
  }).sort((a, b) => ((conv as any)[b.key] ?? 0) - ((conv as any)[a.key] ?? 0));

  const bearishModules = MODULES.filter(m => {
    const val = (conv as any)[m.key] as number | null;
    return val != null && val > 0 && val < 25;
  }).sort((a, b) => ((conv as any)[a.key] ?? 0) - ((conv as any)[b.key] ?? 0));

  return (
    <div className="panel p-5">
      <div className="flex items-center justify-between mb-4">
        <span className="text-[10px] text-gray-500 tracking-widest uppercase">Module Convergence · {conv.module_count} agreeing</span>
      </div>
      {conv.narrative && <p className="text-[12px] text-gray-700 leading-relaxed mb-4">{conv.narrative}</p>}
      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2"><ModuleStrip convergence={conv} mode="expanded" /></div>
        <div className="space-y-4">
          {bullishModules.length > 0 && (
            <div>
              <div className="text-[9px] text-emerald-600 tracking-wider mb-2 font-bold">BULLISH MODULES</div>
              <div className="space-y-1">
                {bullishModules.map(m => {
                  const val = (conv as any)[m.key] as number;
                  return (
                    <div key={m.key} className="flex items-center justify-between text-[9px]">
                      <div className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                        <span className="text-gray-700">{m.label}</span>
                      </div>
                      <span className="font-mono text-emerald-600 font-bold">{val.toFixed(0)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {bearishModules.length > 0 && (
            <div>
              <div className="text-[9px] text-rose-600 tracking-wider mb-2 font-bold">BEARISH MODULES</div>
              <div className="space-y-1">
                {bearishModules.map(m => {
                  const val = (conv as any)[m.key] as number;
                  return (
                    <div key={m.key} className="flex items-center justify-between text-[9px]">
                      <div className="flex items-center gap-2">
                        <div className="w-1.5 h-1.5 rounded-full bg-rose-600" />
                        <span className="text-gray-700">{m.label}</span>
                      </div>
                      <span className="font-mono text-rose-600 font-bold">{val.toFixed(0)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {bullishModules.length === 0 && bearishModules.length === 0 && (
            <div className="text-[9px] text-gray-500">No strong directional signals</div>
          )}
        </div>
      </div>
    </div>
  );
}
