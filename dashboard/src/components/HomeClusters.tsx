import { scoreColor } from '@/lib/modules';
import { cs, fg } from '@/lib/styles';

export interface ClusterStock {
  symbol: string;
  sector: string | null;
  sources: string[];
  convergenceScore: number | null;
  conviction: string | null;
  narrative: string | null;
  displacementScore: number | null;
  pairsDirection: string | null;
  sectorDirection: string | null;
}

interface ClustersProps {
  clusters: ClusterStock[];
}

export function HomeClusters({ clusters }: ClustersProps) {
  if (clusters.length === 0) return null;

  const sectorMap = new Map<string, ClusterStock[]>();
  clusters.slice(0, 12).forEach(c => {
    const sec = c.sector || 'Other';
    if (!sectorMap.has(sec)) sectorMap.set(sec, []);
    sectorMap.get(sec)!.push(c);
  });
  const sectors = Array.from(sectorMap.entries())
    .sort((a, b) => b[1].length - a[1].length);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs text-gray-500 tracking-[0.2em] uppercase">Cross-Signal Clusters</h2>
        <span className="text-[10px] text-gray-500">{clusters.length} stocks with 2+ signal sources</span>
      </div>
      <div className="space-y-4">
        {sectors.map(([sector, stocks]) => {
          const avgScore = stocks.reduce((s, c) => s + (c.convergenceScore ?? 0), 0) / stocks.length;
          return (
            <div key={sector}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] text-amber-600 font-bold tracking-wider uppercase">{sector}</span>
                <span className="text-[10px] text-gray-500">({stocks.length})</span>
                <span
                  className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded-lg"
                  {...cs({
                    color: scoreColor(avgScore),
                    backgroundColor: avgScore >= 50 ? 'rgba(5,150,105,0.08)' : 'rgba(217,119,6,0.08)',
                  })}
                >
                  {avgScore.toFixed(0)}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-3">
                {stocks.map(c => (
                  <a key={c.symbol} href={`/asset/${c.symbol}`} className="panel p-3 hover:border-emerald-600/30 transition-colors group">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono font-bold text-gray-900 text-sm group-hover:text-emerald-600 transition-colors">{c.symbol}</span>
                      <div className="flex gap-1">
                        {c.sources.map(src => (
                          <span
                            key={src}
                            className={`text-[7px] px-1 py-0.5 rounded-lg font-bold tracking-wider border ${
                              src === 'CONVERGENCE' ? 'bg-emerald-600/10 text-emerald-600 border-emerald-600/20' :
                              src === 'DISPLACEMENT' ? 'bg-blue-600/10 text-blue-600 border-blue-600/20' :
                              src === 'PAIRS' ? 'bg-amber-600/10 text-amber-600 border-amber-600/20' :
                              'bg-gray-900/10 text-gray-900 border-gray-900/20'
                            }`}
                          >
                            {src}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-[10px]">
                      {c.convergenceScore !== null && (
                        <div>
                          <span className="text-gray-500">Conv</span>
                          <div className="font-mono" {...fg(scoreColor(c.convergenceScore))}>{c.convergenceScore.toFixed(1)}</div>
                        </div>
                      )}
                      {c.displacementScore !== null && (
                        <div>
                          <span className="text-gray-500">Displ</span>
                          <div className="text-blue-600 font-mono">{c.displacementScore.toFixed(0)}</div>
                        </div>
                      )}
                      {c.conviction && (
                        <div>
                          <span className="text-gray-500">Conv.</span>
                          <div className={`font-mono ${
                            c.conviction === 'high' ? 'text-emerald-600' :
                            c.conviction === 'medium' ? 'text-amber-600' : 'text-gray-500'
                          }`}>
                            {c.conviction.toUpperCase()}
                          </div>
                        </div>
                      )}
                    </div>
                  </a>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
