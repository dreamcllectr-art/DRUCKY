'use client';

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface StockPanelContextValue {
  symbol: string | null;
  open: (symbol: string) => void;
  close: () => void;
}

const StockPanelContext = createContext<StockPanelContextValue>({
  symbol: null,
  open: () => {},
  close: () => {},
});

export function StockPanelProvider({ children }: { children: ReactNode }) {
  const [symbol, setSymbol] = useState<string | null>(null);
  const open = useCallback((s: string) => setSymbol(s.toUpperCase()), []);
  const close = useCallback(() => setSymbol(null), []);
  return (
    <StockPanelContext.Provider value={{ symbol, open, close }}>
      {children}
    </StockPanelContext.Provider>
  );
}

export function useStockPanel() {
  return useContext(StockPanelContext);
}
