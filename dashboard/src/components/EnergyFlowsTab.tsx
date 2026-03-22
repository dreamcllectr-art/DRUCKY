interface FlowsTabProps {
  tradeFlows: Record<string, unknown>;
}

export function EnergyFlowsTab({ tradeFlows }: FlowsTabProps) {
  const paddStocks = (tradeFlows as Record<string, { description: string; value: number }[]>).padd_stocks || [];
  const importByCountry = (tradeFlows as Record<string, { description: string; value: number }[]>).import_by_country || [];

  return (
    <div className="space-y-4">
      {paddStocks.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="p-4 border-b border-gray-200">
            <h3 className="text-xs tracking-widest text-gray-500 uppercase">PADD District Crude Stocks</h3>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[10px] text-gray-500 tracking-widest uppercase">
                <th className="text-left px-4 py-2">District</th>
                <th className="text-right px-4 py-2">Stocks (M bbl)</th>
              </tr>
            </thead>
            <tbody>
              {paddStocks.map((p, i) => (
                <tr key={i} className="border-b border-gray-200/30">
                  <td className="px-4 py-2 text-gray-700">{p.description}</td>
                  <td className="px-4 py-2 text-right font-mono text-gray-900">{(p.value / 1000).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {importByCountry.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="p-4 border-b border-gray-200">
            <h3 className="text-xs tracking-widest text-gray-500 uppercase">US Crude Import Origins</h3>
          </div>
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[10px] text-gray-500 tracking-widest uppercase">
                <th className="text-left px-4 py-2">Source</th>
                <th className="text-right px-4 py-2">Volume (Mb/d)</th>
              </tr>
            </thead>
            <tbody>
              {importByCountry.map((c, i) => (
                <tr key={i} className="border-b border-gray-200/30">
                  <td className="px-4 py-2 text-gray-700">{c.description}</td>
                  <td className="px-4 py-2 text-right font-mono text-gray-900">{c.value.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
