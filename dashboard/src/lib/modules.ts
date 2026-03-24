// Shared module definitions for the 35-module convergence engine.
// Used by ModuleStrip, ConvergenceHeatmap, and expanded score grids.
// Weights must match tools/config_modules.py CONVERGENCE_WEIGHTS (neutral regime).

export interface ModuleDef {
  key: string;
  label: string;
  shortLabel: string;
  weight: number; // neutral regime weight (%)
}

export const MODULES: ModuleDef[] = [
  { key: 'smartmoney_score',              label: 'Smart Money',        shortLabel: 'SMART$',  weight: 9 },
  { key: 'worldview_score',               label: 'Worldview',          shortLabel: 'WORLD',   weight: 9 },
  { key: 'variant_score',                 label: 'Variant',            shortLabel: 'VARIANT', weight: 7 },
  { key: 'analyst_intel_score',           label: 'Analyst Intel',      shortLabel: 'ANLST',   weight: 5 },
  { key: 'capital_flows_score',           label: 'Capital Flows',      shortLabel: 'CFLOW',   weight: 5 },
  { key: 'short_interest_score',          label: 'Short Interest',     shortLabel: 'SHORT',   weight: 4 },
  { key: 'options_flow_score',            label: 'Options Flow',       shortLabel: 'OPTS',    weight: 4 },
  { key: 'foreign_intel_score',           label: 'Foreign Intel',      shortLabel: 'F.INTEL', weight: 3 },
  { key: 'research_score',               label: 'Research',           shortLabel: 'RSRCH',   weight: 3 },
  { key: 'news_displacement_score',       label: 'Displacement',       shortLabel: 'DISPL',   weight: 3 },
  { key: 'sector_expert_score',           label: 'Sector Expert',      shortLabel: 'SECTOR',  weight: 3 },
  { key: 'pairs_score',                   label: 'Pairs Trading',      shortLabel: 'PAIRS',   weight: 3 },
  { key: 'ma_score',                      label: 'M&A Intel',          shortLabel: 'M&A',     weight: 3 },
  { key: 'energy_intel_score',            label: 'Energy Intel',       shortLabel: 'ENERGY',  weight: 3 },
  { key: 'pattern_options_score',         label: 'Patterns/Options',   shortLabel: 'PATTN',   weight: 3 },
  { key: 'estimate_momentum_score',       label: 'Est. Momentum',      shortLabel: 'EST.M',   weight: 3 },
  { key: 'earnings_nlp_score',            label: 'Earnings NLP',       shortLabel: 'EARN',    weight: 3 },
  { key: 'retail_sentiment_score',        label: 'Retail Sentiment',   shortLabel: 'RETAIL',  weight: 3 },
  { key: 'main_signal_score',             label: 'Main Signal',        shortLabel: 'SIGNAL',  weight: 2 },
  { key: 'prediction_markets_score',      label: 'Prediction Mkts',    shortLabel: 'PRED',    weight: 2 },
  { key: 'ai_regulatory_score',           label: 'AI Regulatory',      shortLabel: 'REG',     weight: 2 },
  { key: 'consensus_blindspots_score',    label: 'Blindspots',         shortLabel: 'CBS',     weight: 2 },
  { key: 'gov_intel_score',               label: 'Gov Intel',          shortLabel: 'GOV',     weight: 2 },
  { key: 'labor_intel_score',             label: 'Labor Intel',        shortLabel: 'LABOR',   weight: 2 },
  { key: 'supply_chain_score',            label: 'Supply Chain',       shortLabel: 'SUPPLY',  weight: 2 },
  { key: 'digital_exhaust_score',         label: 'Digital Exhaust',    shortLabel: 'DIGI',    weight: 2 },
  { key: 'pharma_intel_score',            label: 'Pharma Intel',       shortLabel: 'PHARMA',  weight: 2 },
  { key: 'alt_data_score',                label: 'Alt Data',           shortLabel: 'ALT',     weight: 2 },
  { key: 'aar_rail_score',                label: 'AAR Rail',           shortLabel: 'RAIL',    weight: 2 },
  { key: 'ship_tracking_score',           label: 'Ship Tracking',      shortLabel: 'SHIP',    weight: 2 },
  { key: 'patent_intel_score',            label: 'Patent Intel',       shortLabel: 'PATENT',  weight: 2 },
  { key: 'ucc_filings_score',             label: 'UCC Filings',        shortLabel: 'UCC',     weight: 2 },
  { key: 'board_interlocks_score',         label: 'Board Interlocks',   shortLabel: 'BOARD',   weight: 2 },
  { key: 'onchain_intel_score',           label: 'On-Chain Intel',     shortLabel: 'ONCH',    weight: 2 },
  { key: 'reddit_score',                  label: 'Reddit',             shortLabel: 'REDDIT',  weight: 1 },
];

export const TOTAL_WEIGHT = MODULES.reduce((sum, m) => sum + m.weight, 0);

/** Type-safe module score accessor. Avoids `as any` casts. */
export type ModuleScoreKey = (typeof MODULES)[number]['key'];
export function getModuleScore<T extends object>(
  convergence: T,
  key: string,
): number | null {
  const val = (convergence as Record<string, unknown>)[key];
  return typeof val === 'number' ? val : null;
}

export function scoreColor(v: number | null | undefined): string {
  if (v == null || v === 0) return '#9ca3af';
  if (v >= 70) return '#059669';
  if (v >= 50) return '#059669CC';
  if (v >= 25) return '#d97706';
  return '#e11d48';
}

export function scoreBg(v: number | null | undefined): string {
  if (v == null || v === 0) return 'rgba(156,163,175,0.15)';
  if (v >= 70) return 'rgba(5,150,105,0.15)';
  if (v >= 50) return 'rgba(5,150,105,0.08)';
  if (v >= 25) return 'rgba(217,119,6,0.10)';
  return 'rgba(225,29,72,0.10)';
}
