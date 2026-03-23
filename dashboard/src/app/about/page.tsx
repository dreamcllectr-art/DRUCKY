import { MODULES } from '@/lib/modules';

const GATES = [
  { n: 0,  name: 'Universe',           what: '903 equities (S&P 500 + 400) + 14 commodities + 6 crypto', threshold: '923 assets total', equity: true, crypto: true, commodity: true },
  { n: 1,  name: 'Macro Regime',       what: 'Fed policy, yield curve, credit spreads, VIX, breadth composite', threshold: 'regime_score ≥ 30', equity: true, crypto: true, commodity: true },
  { n: 2,  name: 'Liquidity',          what: 'ADV ≥ $15M, market cap ≥ $500M', threshold: 'Skipped for crypto/commodities', equity: true, crypto: false, commodity: false },
  { n: 3,  name: 'Forensic',           what: 'Accruals ratio, earnings quality, Benford\'s Law, auditor flags', threshold: 'forensic_score ≥ 45', equity: true, crypto: true, commodity: true },
  { n: 4,  name: 'Sector Rotation',    what: 'Relative strength quadrant vs. sector peers (Leading / Improving / Weakening / Lagging)', threshold: 'Leading or Improving quadrant', equity: true, crypto: false, commodity: false },
  { n: 5,  name: 'Technical Trend',    what: 'Price vs. 50/200 DMA, RSI, MACD, volume confirmation. Crypto blends on-chain.', threshold: 'technical_score ≥ 58', equity: true, crypto: true, commodity: true },
  { n: 6,  name: 'Fundamental Quality', what: 'ROE, debt/equity, free cash flow yield, earnings growth, balance sheet score', threshold: 'fundamental_score ≥ 42 (bypassed for crypto/commodities)', equity: true, crypto: false, commodity: false },
  { n: 7,  name: 'Smart Money',        what: 'Equity: SEC 13F filings + insider Form 4 net buying + capital flows. Commodity: CFTC commercial hedger COT net percentile. Crypto: bypassed.', threshold: 'Equity: 13F conviction or insider net buy or capital_flow ≥ 65. Commodity: commercial COT pctl ≥ 55.', equity: true, crypto: false, commodity: true },
  { n: 8,  name: 'Signal Convergence', what: '24-module convergence engine — weighted agreement across all active signals', threshold: 'convergence_score ≥ 58 AND modules ≥ 5', equity: true, crypto: true, commodity: true },
  { n: 9,  name: 'Catalyst',           what: 'Earnings events, FDA dates, M&A rumours, options flow, short squeeze score', threshold: 'catalyst_score ≥ 50 or options flow bullish or squeeze ≥ 75', equity: true, crypto: true, commodity: true },
  { n: 10, name: 'Fat Pitch',          what: 'Final filter: composite score, signal grade, risk/reward ratio', threshold: 'composite ≥ 65, BUY/STRONG BUY, R:R ≥ 2.0', equity: true, crypto: true, commodity: true },
];

const MODULE_SOURCES: Record<string, string> = {
  smartmoney_score:          'SEC 13F filings (7 tracked managers), Form 4 insider transactions, capital flow aggregates',
  worldview_score:           'Macro thesis alignment — Fed policy, sector tilt, geopolitical regime',
  variant_score:             'Consensus deviation — where our view diverges from sell-side',
  foreign_intel_score:       'ADR premiums, cross-listed equity flows, FX positioning',
  news_displacement_score:   'NLP on news — displacement events that structurally reset fundamentals',
  research_score:            'Earnings estimate revisions, analyst rating changes, PT momentum',
  prediction_markets_score:  'Polymarket macro event probabilities (Fed, CPI, elections)',
  pairs_score:               'Relative value vs. sector peers — mean reversion and divergence',
  energy_intel_score:        'EU gas storage (GIE), ENTSO-G flows, LNG utilisation, EIA storage surprise',
  sector_expert_score:       'Sector ETF flow proxy, peer group relative strength, rotation quadrant',
  pattern_options_score:     'Technical patterns (flags, wedges, breakouts) + options flow score',
  estimate_momentum_score:   'EPS revision momentum, revenue beat rate, guidance trajectory',
  ma_score:                  'M&A activity signals — rumour NLP, deal premium comps, sector consolidation',
  consensus_blindspots_score:'High-quality names below consensus radar — low coverage, underowned',
  main_signal_score:         'Primary composite signal (BUY/STRONG BUY/HOLD/SELL) from main pipeline',
  ai_regulatory_score:       'AI/regulatory event risk — patent filings, lobbying activity, agency actions',
  alt_data_score:            'Satellite imagery, ENSO/climate signals, web traffic proxies',
  reddit_score:              'WallStreetBets + Reddit sentiment (unweighted — informational only)',
  earnings_nlp_score:        'Earnings call transcript NLP — tone, language shift, management confidence',
  gov_intel_score:           'Government contract awards, federal spending, defence procurement',
  labor_intel_score:         'Job posting trends (LinkedIn/Indeed proxy), layoff signals, wage data',
  supply_chain_score:        'Supplier network stress, port congestion, freight rate signals',
  digital_exhaust_score:     'App downloads, web traffic, credit card spend proxies',
  pharma_intel_score:        'FDA calendar, clinical trial registrations, drug approval pipeline',
};

export default function AboutPage() {
  return (
    <div className="max-w-4xl mx-auto py-10 px-6 space-y-12 animate-fade-in">

      <div>
        <h1 className="text-xl font-display font-bold text-gray-900 mb-1">System Reference</h1>
        <p className="text-[12px] text-gray-500">What data feeds what. No prose — just the map.</p>
      </div>

      {/* 10-Gate Cascade */}
      <section>
        <h2 className="text-[11px] font-semibold text-gray-500 tracking-widest uppercase mb-4">10-Gate Cascade</h2>
        <div className="panel overflow-hidden">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-200 text-gray-400 tracking-widest uppercase text-[9px]">
                <th className="text-left py-2.5 px-4 font-normal w-6">#</th>
                <th className="text-left py-2.5 px-3 font-normal w-36">Gate</th>
                <th className="text-left py-2.5 px-3 font-normal">Data Sources</th>
                <th className="text-left py-2.5 px-3 font-normal w-56">Pass Condition</th>
                <th className="text-center py-2.5 px-2 font-normal w-8">EQ</th>
                <th className="text-center py-2.5 px-2 font-normal w-8">CM</th>
                <th className="text-center py-2.5 px-2 font-normal w-8">CR</th>
              </tr>
            </thead>
            <tbody>
              {GATES.map(g => (
                <tr key={g.n} className="border-b border-gray-100 hover:bg-gray-50/50">
                  <td className="py-3 px-4 font-mono text-gray-400">{g.n}</td>
                  <td className="py-3 px-3 font-semibold text-gray-800">{g.name}</td>
                  <td className="py-3 px-3 text-gray-600 leading-relaxed">{g.what}</td>
                  <td className="py-3 px-3 text-gray-500 font-mono text-[10px]">{g.threshold}</td>
                  <td className="py-3 px-2 text-center">
                    <span className={g.equity ? 'text-emerald-600 font-bold' : 'text-gray-300'}>
                      {g.equity ? '✓' : '—'}
                    </span>
                  </td>
                  <td className="py-3 px-2 text-center">
                    <span className={g.commodity ? 'text-emerald-600 font-bold' : 'text-gray-300'}>
                      {g.commodity ? '✓' : '—'}
                    </span>
                  </td>
                  <td className="py-3 px-2 text-center">
                    <span className={g.crypto ? 'text-emerald-600 font-bold' : 'text-gray-300'}>
                      {g.crypto ? '✓' : '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 py-2 border-t border-gray-100 text-[9px] text-gray-400 flex gap-4">
            <span><span className="font-bold text-gray-600">EQ</span> = Equity</span>
            <span><span className="font-bold text-gray-600">CM</span> = Commodity</span>
            <span><span className="font-bold text-gray-600">CR</span> = Crypto</span>
            <span>— = gate bypassed for this asset class</span>
          </div>
        </div>
      </section>

      {/* 24-Module Convergence Engine */}
      <section>
        <h2 className="text-[11px] font-semibold text-gray-500 tracking-widest uppercase mb-4">
          24-Module Convergence Engine
        </h2>
        <p className="text-[11px] text-gray-500 mb-4">
          Gate 8 requires ≥ 5 modules firing with convergence_score ≥ 58. Weights are regime-adjusted — Smart Money and Worldview are upweighted in risk-off; Alt Data and Reddit are downweighted.
        </p>
        <div className="panel overflow-hidden">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-200 text-gray-400 tracking-widest uppercase text-[9px]">
                <th className="text-left py-2.5 px-4 font-normal w-40">Module</th>
                <th className="text-right py-2.5 px-3 font-normal w-16">Weight</th>
                <th className="text-left py-2.5 px-3 font-normal">Data Sources</th>
              </tr>
            </thead>
            <tbody>
              {MODULES.map(m => (
                <tr key={m.key} className="border-b border-gray-100 hover:bg-gray-50/50">
                  <td className="py-2.5 px-4 font-semibold text-gray-800">{m.label}</td>
                  <td className="py-2.5 px-3 text-right font-mono text-gray-500">
                    {m.weight > 0 ? `${m.weight}%` : <span className="text-gray-300">info</span>}
                  </td>
                  <td className="py-2.5 px-3 text-gray-600 leading-relaxed">
                    {MODULE_SOURCES[m.key] ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Smart Money breakdown */}
      <section>
        <h2 className="text-[11px] font-semibold text-gray-500 tracking-widest uppercase mb-4">Smart Money — By Asset Class</h2>
        <div className="grid grid-cols-3 gap-4">
          {[
            {
              label: 'Equity',
              items: [
                'SEC 13F filings — 7 tracked hedge fund managers, quarterly (45–135d lag)',
                'Form 4 insider transactions — cluster buying (3+ insiders, 14d window) gets IC boost',
                'Capital flow composite — dark pool + fund flow proxies',
              ],
              note: 'Insider selling > $1M net blocks regardless of other signals.',
            },
            {
              label: 'Commodity',
              items: [
                'CFTC COT disaggregated report — commercial hedger (prod_merc) net positions',
                'Percentile vs. 2-year history — high pctl = producers not hedging = bullish',
                'Markets tracked: WTI Crude, Brent, Nat Gas HH, RBOB, Heating Oil, Corn',
              ],
              note: 'High commercial net long percentile (≥ 55) = Gate 7 pass.',
            },
            {
              label: 'Crypto',
              items: [
                'Gate 7 bypassed — no 13F, no insider filings',
                'Nansen on-chain data not yet live (all fields returning null)',
                'Fear & Greed index available but not used as smart money proxy',
              ],
              note: 'Treated same as Fundamentals and Sector Rotation — gate does not apply.',
            },
          ].map(block => (
            <div key={block.label} className="panel p-4">
              <div className="text-[10px] font-semibold text-gray-500 tracking-widest uppercase mb-3">{block.label}</div>
              <ul className="space-y-2">
                {block.items.map((item, i) => (
                  <li key={i} className="text-[11px] text-gray-700 flex gap-2">
                    <span className="text-gray-300 shrink-0">·</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
              <p className="text-[10px] text-gray-400 mt-3 italic">{block.note}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Update cadence */}
      <section>
        <h2 className="text-[11px] font-semibold text-gray-500 tracking-widest uppercase mb-4">Update Cadence</h2>
        <div className="panel overflow-hidden">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-200 text-gray-400 tracking-widest uppercase text-[9px]">
                <th className="text-left py-2.5 px-4 font-normal">Frequency</th>
                <th className="text-left py-2.5 px-3 font-normal">Data</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Daily (post-close)',   'Prices, technical scores, signals, convergence engine, gate cascade, macro regime, options flow'],
                ['Weekly',              'CFTC COT report (Fridays), FINRA short interest, CoinShares ETP flows, EU gas storage'],
                ['Quarterly (45–135d lag)', 'SEC 13F institutional holdings'],
                ['On event',            'Form 4 insider transactions, FDA calendar, earnings NLP'],
                ['Monthly',             'EIA LNG exports, ENSO/climate signals, labor market proxies'],
              ].map(([freq, data]) => (
                <tr key={freq} className="border-b border-gray-100">
                  <td className="py-2.5 px-4 font-semibold text-gray-700 w-52 shrink-0">{freq}</td>
                  <td className="py-2.5 px-3 text-gray-600">{data}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

    </div>
  );
}
