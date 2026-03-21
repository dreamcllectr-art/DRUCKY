import { ErrorBoundary } from '@/components/ErrorBoundary';
import { StockPanelProvider } from '@/contexts/StockPanelContext';
import StockPanel from '@/components/shared/StockPanel';

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return (
    <StockPanelProvider>
      <div className="flex flex-col h-screen overflow-hidden">
        <div className="px-4 py-1.5 border-b border-gray-100 bg-white shrink-0">
          <div className="flex items-center gap-3 max-w-[1600px] mx-auto">
            <span className="text-[9px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded font-bold tracking-widest">V2</span>
            <span className="text-[10px] text-gray-400 tracking-wider">Druckenmiller Alpha System</span>
          </div>
        </div>
        <div className="flex-1 overflow-hidden">
          <ErrorBoundary>{children}</ErrorBoundary>
        </div>
      </div>
      <StockPanel />
    </StockPanelProvider>
  );
}
