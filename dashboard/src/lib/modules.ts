// Shared module definitions for the 18-module convergence engine.
// Used by ModuleStrip, ConvergenceHeatmap, and expanded score grids.

export interface ModuleDef {
  key: string;
  label: string;
  shortLabel: string;
  weight: number; // neutral regime weight (%)
}

export const MODULES: ModuleDef[] = [
  { key: 'smartmoney_score',             label: 'Smart Money',        shortLabel: 'SMART$',  weight: 15 },
  { key: 'worldview_score',              label: 'Worldview',          shortLabel: 'WORLD',   weight: 13 },
  { key: 'variant_score',                label: 'Variant',            shortLabel: 'VARIANT', weight: 9 },
  { key: 'foreign_intel_score',          label: 'Foreign Intel',      shortLabel: 'F.INTEL', weight: 7 },
  { key: 'news_displacement_score',      label: 'Displacement',       shortLabel: 'DISPL',   weight: 6 },
  { key: 'research_score',               label: 'Research',           shortLabel: 'RSRCH',   weight: 6 },
  { key: 'prediction_markets_score',     label: 'Prediction Mkts',    shortLabel: 'PRED',    weight: 5 },
  { key: 'pairs_score',                  label: 'Pairs Trading',      shortLabel: 'PAIRS',   weight: 5 },
  { key: 'energy_intel_score',           label: 'Energy Intel',       shortLabel: 'ENERGY',  weight: 5 },
  { key: 'sector_expert_score',          label: 'Sector Expert',      shortLabel: 'SECTOR',  weight: 5 },
  { key: 'pattern_options_score',        label: 'Patterns/Options',   shortLabel: 'PATTN',   weight: 4 },
  { key: 'estimate_momentum_score',      label: 'Est. Momentum',      shortLabel: 'EST.M',   weight: 4 },
  { key: 'ma_score',                     label: 'M&A Intel',          shortLabel: 'M&A',     weight: 4 },
  { key: 'consensus_blindspots_score',   label: 'Blindspots',         shortLabel: 'CBS',     weight: 4 },
  { key: 'main_signal_score',            label: 'Main Signal',        shortLabel: 'SIGNAL',  weight: 3 },
  { key: 'ai_regulatory_score',          label: 'AI Regulatory',      shortLabel: 'REG',     weight: 3 },
  { key: 'alt_data_score',               label: 'Alt Data',           shortLabel: 'ALT',     weight: 2 },
  { key: 'reddit_score',                 label: 'Reddit',             shortLabel: 'REDDIT',  weight: 0 },
];

export const TOTAL_WEIGHT = MODULES.reduce((sum, m) => sum + m.weight, 0);

export function scoreColor(v: number | null | undefined): string {
  if (v == null || v === 0) return '#333333';
  if (v >= 70) return '#00FF41';
  if (v >= 50) return '#00FF41CC';
  if (v >= 25) return '#FFB800';
  return '#FF073A';
}

export function scoreBg(v: number | null | undefined): string {
  if (v == null || v === 0) return 'rgba(51,51,51,0.3)';
  if (v >= 70) return 'rgba(0,255,65,0.15)';
  if (v >= 50) return 'rgba(0,255,65,0.08)';
  if (v >= 25) return 'rgba(255,184,0,0.10)';
  return 'rgba(255,7,58,0.10)';
}
