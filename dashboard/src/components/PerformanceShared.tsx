export function PerformanceSufficiencyBadge({ sufficient, days, signals }: { sufficient: boolean; days: number; signals: number }) {
  if (sufficient) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#05966910] border border-[#05966930]">
        <div className="w-2 h-2 rounded-full bg-[#059669] animate-pulse" />
        <span className="text-xs text-[#059669] font-display tracking-wider">ADAPTIVE WEIGHTS ACTIVE</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#d9770610] border border-[#d9770630]">
      <div className="w-2 h-2 rounded-full bg-[#d97706]" />
      <span className="text-xs text-[#d97706] font-display tracking-wider">
        CALIBRATING &mdash; {days}d collected &middot; {signals.toLocaleString()} signals ingested
      </span>
    </div>
  );
}

export function PerformanceErrorBoundaryFallback({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="p-8">
      <div className="panel p-6 text-center">
        <div className="text-red-400 mb-2">Something went wrong</div>
        <div className="text-sm text-gray-500 mb-4">{error}</div>
        <button onClick={onRetry} className="px-4 py-2 text-xs font-display text-emerald-600 border border-emerald-600 rounded hover:bg-emerald-600/10">
          Try Again
        </button>
      </div>
    </div>
  );
}
