import { ErrorBoundary } from '@/components/ErrorBoundary';

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      <div className="px-4 py-2 border-b border-gray-100 bg-white">
        <div className="flex items-center gap-3 max-w-[1600px] mx-auto">
          <span className="text-[9px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded font-bold tracking-widest">V2</span>
          <span className="text-[10px] text-gray-400 tracking-wider">Decision Funnel</span>
        </div>
      </div>
      <ErrorBoundary>{children}</ErrorBoundary>
    </div>
  );
}
