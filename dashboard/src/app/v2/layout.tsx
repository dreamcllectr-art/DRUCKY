import { ErrorBoundary } from '@/components/ErrorBoundary';
import { StockPanelProvider } from '@/contexts/StockPanelContext';
import StockPanel from '@/components/shared/StockPanel';

export default function V2Layout({ children }: { children: React.ReactNode }) {
  return (
    <StockPanelProvider>
      <div className="flex flex-col h-screen overflow-hidden">
        <div className="flex-1 overflow-hidden">
          <ErrorBoundary>{children}</ErrorBoundary>
        </div>
      </div>
      <StockPanel />
    </StockPanelProvider>
  );
}
