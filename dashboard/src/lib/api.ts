async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export interface MacroData {
  date: string;
  total_score: number;
  regime: string;
  fed_funds_score: number;
  m2_score: number;
  real_rates_score: number;
  yield_curve_score: number;
  credit_spreads_score: number;
  dxy_score: number;
  vix_score: number;
}

export interface Signal {
  symbol: string;
  date: string;
  asset_class: string;
  macro_score: number;
  technical_score: number;
  fundamental_score: number;
  composite_score: number;
  signal: string;
  entry_price: number;
  stop_loss: number;
  target_price: number;
  rr_ratio: number;
  position_size_shares: number | null;
  position_size_dollars: number | null;
}

export interface AssetDetail {
  signal: Signal | null;
  technical: {
    trend_score: number;
    momentum_score: number;
    breakout_score: number;
    relative_strength_score: number;
    breadth_score: number;
    total_score: number;
  } | null;
  fundamental: {
    valuation_score: number;
    growth_score: number;
    profitability_score: number;
    health_score: number;
    quality_score: number;
    total_score: number;
  } | null;
  fundamentals: Record<string, number>;
}

export interface PriceBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Breadth {
  pct_above_200dma: number;
  advance_decline_ratio: number;
  new_highs: number;
  new_lows: number;
  breadth_score: number;
}

export interface WatchlistItem {
  symbol: string;
  asset_class: string;
  added_date: string;
  notes: string;
  price: number | null;
  tech_score: number | null;
  signal: string | null;
  composite: number | null;
}

export interface Position {
  id: number;
  symbol: string;
  asset_class: string;
  entry_date: string;
  entry_price: number;
  shares: number;
  stop_loss: number | null;
  target_price: number | null;
  current_price: number;
  current_value: number;
  pnl: number;
  pnl_pct: number;
}

export interface ForeignIntelSignal {
  symbol: string;
  local_ticker: string | null;
  market: string;
  language: string;
  source: string;
  url: string;
  title_translated: string;
  sentiment: number;
  relevance_score: number;
  key_themes: string;
  article_summary: string;
  date: string;
}

export interface ForeignIntelMarketSummary {
  market: string;
  article_count: number;
  avg_sentiment: number;
  avg_relevance: number;
  total_chars: number;
}

export interface ConvergenceDelta {
  symbol: string;
  convergence_score: number;
  conviction_level: string;
  narrative: string;
  module_count: number;
  prev_score: number | null;
  prev_conviction: string | null;
  score_delta: number;
}

export interface SignalChange {
  symbol: string;
  new_signal: string;
  old_signal: string;
  composite_score: number;
  entry_price: number;
  target_price: number;
  stop_loss: number;
}

export interface ConvergenceSignal {
  symbol: string;
  date?: string;
  convergence_score: number;
  conviction_level: string;
  module_count: number;
  forensic_blocked: number;
  main_signal_score: number | null;
  smartmoney_score: number | null;
  worldview_score: number | null;
  variant_score: number | null;
  research_score: number | null;
  reddit_score: number | null;
  foreign_intel_score: number | null;
  news_displacement_score: number | null;
  alt_data_score: number | null;
  sector_expert_score: number | null;
  pairs_score: number | null;
  // Core modules
  ma_score: number | null;
  energy_intel_score: number | null;
  prediction_markets_score: number | null;
  pattern_options_score: number | null;
  estimate_momentum_score: number | null;
  ai_regulatory_score: number | null;
  consensus_blindspots_score: number | null;
  // Alt Alpha II
  earnings_nlp_score: number | null;
  gov_intel_score: number | null;
  labor_intel_score: number | null;
  supply_chain_score: number | null;
  digital_exhaust_score: number | null;
  pharma_intel_score: number | null;
  active_modules: string;
  narrative: string;
}

export interface SignalHistoryRow {
  date: string;
  signal: string;
  composite_score: number;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  risk_reward: number | null;
  catalyst: string | null;
}

export interface ConvergenceHistoryRow {
  date: string;
  convergence_score: number;
  conviction_level: string;
  module_count: number;
  narrative: string;
  [key: string]: any;
}

// ── Investment Memo ──
export interface InvestmentMemo {
  id: number;
  symbol: string;
  generated_at: string;
  regime: string;
  report_html: string | null;
  metadata: string | null;
}

// ── Signal Conflicts ──
export interface SignalConflict {
  symbol: string;
  date: string;
  conflict_type: string;
  severity: string;
  description: string;
  module_a: string;
  module_a_score: number;
  module_b: string;
  module_b_score: number;
  score_gap: number;
}

export interface ConflictSummary {
  conflict_type: string;
  severity: string;
  count: number;
  avg_gap: number;
}

// ── Stress Test ──
export interface StressTestResult {
  date: string;
  scenario: string;
  scenario_name: string;
  portfolio_impact_pct: number;
  position_count: number;
  position_details: string | null;
  worst_hit: string | null;
  best_positioned: string | null;
}

export interface ConcentrationRisk {
  date: string;
  hhi: number | null;
  concentration_level: string | null;
  top_sector: string | null;
  top_sector_pct: number | null;
  details: string | null;
}

// ── Thesis Monitor ──
export interface ThesisAlert {
  date: string;
  thesis: string;
  alert_type: string;
  severity: string;
  description: string;
  affected_symbols: string | null;
  lookback_days: number;
  old_state: string | null;
  new_state: string | null;
}

export interface ThesisSnapshot {
  date: string;
  thesis: string;
  direction: string;
  confidence: number;
  affected_sectors: string | null;
}

export interface DisplacementSignal {
  symbol: string;
  date: string;
  news_headline: string;
  news_source: string;
  materiality_score: number;
  expected_direction: string;
  expected_magnitude: number;
  actual_price_change_1d: number | null;
  actual_price_change_3d: number | null;
  displacement_score: number;
  time_horizon: string;
  order_type: string;
  confidence: number;
  narrative: string;
  status: string;
}

export interface AltDataSignal {
  date: string;
  source: string;
  indicator: string;
  value: number;
  value_zscore: number | null;
  signal_direction: string;
  signal_strength: number;
  affected_sectors: string;
  affected_tickers: string;
  narrative: string;
}

export interface SectorExpertSignal {
  symbol: string;
  date: string;
  sector: string;
  expert_type: string;
  sector_displacement_score: number;
  consensus_narrative: string;
  variant_narrative: string;
  direction: string;
  conviction_level: string;
  key_catalysts: string;
  narrative: string;
}

// ── Pairs Trading Types ──

export interface PairRelationship {
  symbol_a: string;
  symbol_b: string;
  sector: string | null;
  correlation_60d: number;
  correlation_120d: number | null;
  cointegration_pvalue: number;
  hedge_ratio: number;
  half_life_days: number;
  spread_mean: number;
  spread_std: number;
  last_updated: string;
}

export interface PairSignal {
  id: number;
  date: string;
  signal_type: 'mean_reversion' | 'runner';
  symbol_a: string;
  symbol_b: string;
  sector: string | null;
  spread_zscore: number;
  correlation_60d: number;
  cointegration_pvalue: number;
  hedge_ratio: number;
  half_life_days: number;
  pairs_score: number;
  direction: string;
  runner_symbol: string | null;
  runner_tech_score: number | null;
  runner_fund_score: number | null;
  narrative: string;
  status: string;
}

export interface PairSpread {
  date: string;
  spread_raw: number;
  spread_zscore: number;
  spread_percentile: number;
}

// ── Economic Indicators Types ──

export interface EconomicIndicator {
  indicator_id: string;
  date: string;
  category: 'leading' | 'coincident' | 'lagging' | 'liquidity';
  name: string;
  value: number;
  prev_value: number | null;
  mom_change: number | null;
  yoy_change: number | null;
  zscore: number | null;
  trend: 'improving' | 'stable' | 'deteriorating';
  signal: 'bullish' | 'neutral' | 'bearish';
  last_updated: string;
}

export interface HeatIndex {
  date: string;
  heat_index: number;
  improving_count: number;
  deteriorating_count: number;
  stable_count: number;
  leading_count: number;
  detail: string;
}

export interface IndicatorHistoryPoint {
  date: string;
  value: number;
}

// ── Thesis Lab Types ──

export interface FunnelRegime {
  score: number;
  label: string;
  date: string;
  implications: string;
  sub_scores: Record<string, number>;
}

export interface ThesisDetail {
  key: string;
  description: string;
  bullish_sectors: string[];
  bearish_sectors: string[];
}

export interface SectorTilt {
  sector: string;
  tilt: number;
  stock_count: number;
  favored: boolean;
}

export interface StockExpression {
  symbol: string;
  sector: string;
  thesis_score: number;
  tilt: number;
  narrative: string;
  active_theses: string;
}

export interface ConvergentStock {
  symbol: string;
  convergence_score: number;
  conviction: string;
  module_count: number;
  modules: string;
  narrative: string;
}

export interface ActionableStock {
  symbol: string;
  entry: number;
  stop: number;
  target: number;
  rr: number;
  position_size: number | null;
  convergence_score: number;
  conviction: string;
  module_count: number;
  narrative: string;
}

export interface FunnelData {
  regime: FunnelRegime;
  active_theses: ThesisDetail[];
  sector_tilts: SectorTilt[];
  stock_expressions: StockExpression[];
  convergent_stocks: ConvergentStock[];
  actionable: ActionableStock[];
  funnel_counts: {
    universe: number;
    favored_sectors: number;
    sector_stocks: number;
    expressions: number;
    convergent: number;
    actionable: number;
  };
}

export interface MentalModel {
  category: string;
  name: string;
  one_liner: string;
  relevance: number;
  applies_to: string[];
  regime_note: string;
}

export interface ThesisChecklist {
  symbol: string;
  sector: string | null;
  name: string;
  business_quality: {
    scores: Record<string, number> | null;
    metrics: Record<string, number>;
  };
  variant_perception: Record<string, unknown> | null;
  catalysts: {
    displacement: Array<Record<string, unknown>>;
    expert: Record<string, unknown> | null;
    research: Array<Record<string, unknown>>;
  };
  risk_assessment: {
    forensic_alerts: Array<Record<string, unknown>>;
    stop_loss: number | null;
    entry_price: number | null;
    stop_distance_pct: number | null;
  };
  position_framework: {
    entry: number | null;
    stop: number | null;
    target: number | null;
    rr_ratio: number | null;
    signal: string | null;
    composite_score: number | null;
    position_size_dollars: number | null;
    position_size_shares: number | null;
  };
  convergence: {
    score: number | null;
    conviction: string | null;
    module_count: number | null;
    modules: string | null;
    narrative: string | null;
    breakdown: Record<string, number | null>;
  };
  worldview: Record<string, unknown> | null;
}

// ── Energy Intelligence Types ──

export interface EnergyIntelSignal {
  symbol: string;
  date: string;
  energy_intel_score: number;
  inventory_signal: number;
  production_signal: number;
  demand_signal: number;
  trade_flow_signal: number;
  global_balance_signal: number;
  ticker_category: string;
  narrative: string;
}

export interface EnergyInventory {
  series_id: string;
  name: string;
  date: string;
  value: number;
  wow_change: number | null;
  draw_build: 'DRAW' | 'BUILD' | null;
  seasonal_avg: number | null;
  seasonal_min: number | null;
  seasonal_max: number | null;
  seasonal_std: number | null;
}

export interface EnergyAnomaly {
  anomaly_type: string;
  description: string;
  zscore: number;
  severity: string;
  affected_tickers: string;
}

export interface EnergySupplyData {
  inventories: EnergyInventory[];
  days_of_supply: { date: string; value: number } | null;
  crude_history: { date: string; value: number }[];
}

export interface EnergyProductionData {
  production: { date: string; value: number }[];
  refinery_util: { date: string; value: number }[];
  product_supplied: { date: string; value: number }[];
  crack_spread: { date: string; value: number }[];
}

export interface JodiRecord {
  country: string;
  indicator: string;
  date: string;
  value: number;
  unit: string;
  mom_change: number | null;
  yoy_change: number | null;
}

export interface EnergyBalance {
  production_total_kbd: number;
  demand_total_kbd: number;
  surplus_kbd: number;
  balance: 'SURPLUS' | 'DEFICIT';
}

// ── Pattern Match & Options Intelligence Types ──

export interface PatternScanResult {
  symbol: string;
  date: string;
  regime: string;
  regime_score: number;
  vix_percentile: number;
  sector_quadrant: string;
  rotation_score: number;
  rs_ratio: number;
  rs_momentum: number;
  patterns_detected: string | null;
  pattern_score: number;
  sr_proximity: string;
  volume_profile_score: number;
  hurst_exponent: number;
  mr_score: number;
  momentum_score: number;
  compression_score: number;
  squeeze_active: number;
  wyckoff_phase: string;
  wyckoff_confidence: number;
  earnings_days_to_next: number | null;
  vol_regime: string;
  pattern_scan_score: number;
  layer_scores: string;
  // Joined fields
  options_score: number | null;
  pattern_options_score: number | null;
  sector: string | null;
  company_name: string | null;
}

export interface PatternLayerDetail {
  scan: PatternScanResult | null;
  options: OptionsIntelResult | null;
  composite: {
    symbol: string;
    date: string;
    pattern_scan_score: number;
    options_score: number | null;
    pattern_options_score: number;
    top_pattern: string | null;
    top_signal: string | null;
    narrative: string;
  } | null;
}

export interface SectorRotationPoint {
  sector: string;
  date: string;
  rs_ratio: number;
  rs_momentum: number;
  quadrant: string;
  rotation_score: number;
}

export interface OptionsIntelResult {
  symbol: string;
  date: string;
  atm_iv: number | null;
  hv_20d: number | null;
  iv_premium: number | null;
  iv_rank: number | null;
  iv_percentile: number | null;
  expected_move_pct: number | null;
  straddle_cost: number | null;
  volume_pc_ratio: number | null;
  oi_pc_ratio: number | null;
  pc_signal: string | null;
  unusual_activity_count: number;
  unusual_activity: string | null;
  unusual_direction_bias: string | null;
  skew_25d: number | null;
  skew_direction: string | null;
  term_structure_signal: string | null;
  net_gex: number | null;
  gamma_flip_level: number | null;
  vanna_exposure: number | null;
  max_pain: number | null;
  put_wall: number | null;
  call_wall: number | null;
  dealer_regime: string | null;
  options_score: number;
  sector?: string | null;
  company_name?: string | null;
}

export interface UnusualActivityRow {
  symbol: string;
  date: string;
  unusual_activity_count: number;
  unusual_activity: string;
  unusual_direction_bias: string | null;
  atm_iv: number | null;
  iv_rank: number | null;
  expected_move_pct: number | null;
  dealer_regime: string | null;
  options_score: number;
  sector: string | null;
  company_name: string | null;
}

export interface ExpectedMoveRow {
  symbol: string;
  expected_move_pct: number;
  straddle_cost: number;
  atm_iv: number | null;
  iv_rank: number | null;
  dealer_regime: string | null;
  wyckoff_phase: string | null;
  squeeze_active: number | null;
  sector: string | null;
  company_name: string | null;
}

export interface CompressionRow {
  symbol: string;
  compression_score: number;
  squeeze_active: number;
  hurst_exponent: number;
  mr_score: number;
  momentum_score: number;
  wyckoff_phase: string;
  pattern_scan_score: number;
  iv_rank: number | null;
  expected_move_pct: number | null;
  dealer_regime: string | null;
  sector: string | null;
  company_name: string | null;
}

export interface DealerExposureRow {
  symbol: string;
  net_gex: number;
  gamma_flip_level: number | null;
  vanna_exposure: number | null;
  max_pain: number | null;
  put_wall: number | null;
  call_wall: number | null;
  dealer_regime: string;
  atm_iv: number | null;
  options_score: number;
  sector: string | null;
  company_name: string | null;
}

// ── Hyperliquid Weekend Gap Types ──

export interface HLGapSignal {
  traditional_ticker: string;
  weekend_date: string;
  friday_close: number;
  hl_price_20utc: number;
  hl_weekend_return_pct: number;
  predicted_gap_pct: number;
  predicted_direction: string;
  confidence: number;
  actual_open: number | null;
  actual_gap_pct: number | null;
  direction_correct: number | null;
  error_bps: number | null;
  book_depth_vs_saturday_pct: number | null;
  deployer: string;
  hl_symbol: string;
}

export interface HLSnapshot {
  hl_symbol: string;
  deployer: string;
  timestamp: string;
  mid_price: number;
  bid: number;
  ask: number;
  spread_bps: number;
  book_depth_bid_usd: number;
  book_depth_ask_usd: number;
  funding_rate: number | null;
  open_interest: number | null;
}

export interface HLDeployerSpread {
  traditional_ticker: string;
  deployer_a: string;
  deployer_b: string;
  timestamp: string;
  price_a: number;
  price_b: number;
  spread_bps: number;
  spread_direction: string;
}

export interface HLAccuracy {
  total_predictions: number;
  correct_direction: number;
  direction_accuracy_pct: number;
  avg_error_bps: number;
  avg_predicted_gap_pct: number;
  avg_actual_gap_pct: number;
}

// ── Insider Trading Types ──

export interface InsiderSignal {
  symbol: string;
  date: string;
  insider_score: number;
  cluster_buy: number;
  cluster_count: number | null;
  large_buys_count: number;
  total_buy_value_30d: number;
  total_sell_value_30d: number;
  unusual_volume_flag: number;
  top_buyer: string | null;
  narrative: string;
  smart_money_score?: number | null;
}

export interface InsiderTransaction {
  date: string;
  insider_name: string;
  insider_title: string;
  transaction_type: string;
  shares: number;
  price: number | null;
  value: number;
  shares_owned_after: number | null;
  source: string;
}

export interface InsiderDetail {
  transactions: InsiderTransaction[];
  signal: InsiderSignal | null;
}

// ── AI Executive Investment Tracker Types ──

export interface AIExecSignal {
  symbol: string;
  date: string;
  ai_exec_score: number;
  exec_count: number;
  top_exec: string | null;
  top_activity: string | null;
  sector_signal: string | null;
  narrative: string;
}

export interface AIExecInvestment {
  exec_name: string;
  exec_org: string;
  activity_type: string;
  target_company: string;
  target_ticker: string | null;
  target_sector: string | null;
  investment_amount: number | null;
  funding_round: string | null;
  is_public: number;
  date_reported: string | null;
  confidence: number;
  summary: string;
  raw_score: number;
  scan_date: string;
}

export interface AIExecConvergence {
  target_company: string;
  target_ticker: string | null;
  target_sector: string | null;
  exec_count: number;
  executives: string;
  max_score: number;
  latest_scan: string;
}

export interface AIExecDetail {
  investments: AIExecInvestment[];
  signal: AIExecSignal | null;
}

// ── M&A Intelligence Types ──

export interface MASignal {
  symbol: string;
  date: string;
  ma_score: number;
  target_profile_score: number | null;
  rumor_score: number | null;
  valuation_score: number | null;
  balance_sheet_score: number | null;
  growth_score: number | null;
  smart_money_score: number | null;
  consolidation_bonus: number | null;
  mcap_multiplier: number | null;
  sector_multiplier: number | null;
  deal_stage: string | null;
  rumor_credibility: number | null;
  acquirer_name: string | null;
  expected_premium_pct: number | null;
  best_headline: string | null;
  narrative: string | null;
  status: string;
  sector: string | null;
  company_name: string | null;
}

export interface MARumor {
  symbol: string;
  date: string;
  rumor_source: string | null;
  rumor_headline: string | null;
  credibility_score: number | null;
  deal_stage: string | null;
  expected_premium_pct: number | null;
  acquirer_name: string | null;
  url: string | null;
  sector: string | null;
  company_name: string | null;
}

// ── Prediction Markets Types ──

export interface PredictionMarketSignal {
  symbol: string;
  date: string;
  pm_score: number;
  market_count: number | null;
  net_impact: number | null;
  status: string;
  narrative: string | null;
  sector: string | null;
  company_name: string | null;
}

export interface PredictionMarketRaw {
  market_id: string;
  date: string;
  question: string | null;
  impact_category: string | null;
  yes_probability: number | null;
  volume: number | null;
  liquidity: number | null;
  direction: string | null;
  confidence: number | null;
  specific_symbols: string | null;
  rationale: string | null;
  end_date: string | null;
}

export interface PredictionMarketCategory {
  impact_category: string;
  market_count: number;
  avg_probability: number;
  total_volume: number;
  avg_confidence: number;
}

// ── AI Regulatory Intelligence Types ──

export interface RegulatorySignal {
  symbol: string;
  date: string;
  reg_score: number;
  event_count: number;
  net_impact: number;
  status: string;
  narrative: string | null;
  sector: string | null;
  company_name: string | null;
}

export interface RegulatoryEvent {
  event_id: string;
  date: string;
  source: string;
  title: string;
  abstract: string | null;
  event_date: string | null;
  doc_type: string | null;
  agencies: string | null;
  impact_category: string | null;
  severity: number;
  stage: string | null;
  direction: string | null;
  timeline: string | null;
  specific_symbols: string | null;
  rationale: string | null;
  url: string | null;
  jurisdiction: string | null;
}

export interface RegulatoryCategory {
  impact_category: string;
  event_count: number;
  avg_severity: number;
  source_count: number;
  directions: string | null;
}

export interface RegulatorySource {
  source: string;
  jurisdiction: string | null;
  event_count: number;
  avg_severity: number;
  latest_event: string | null;
  categories: string | null;
}

export interface RegulatoryJurisdiction {
  jurisdiction: string;
  event_count: number;
  avg_severity: number;
  headwinds: number;
  tailwinds: number;
  mixed: number;
  sources: string | null;
}

// ── Worldview / Global Macro Types ──

export interface WorldviewSignal {
  symbol: string;
  date: string;
  regime: string | null;
  thesis_alignment_score: number | null;
  sector_tilt: string | null;
  active_theses: string | null;
  narrative: string | null;
  sector: string | null;
  company_name: string | null;
}

export interface WorldviewThesis {
  active_theses: string;
  sector_tilt: string;
  stock_count: number;
  avg_alignment: number;
}

export interface WorldMacroIndicator {
  indicator: string;
  country: string;
  year: number;
  value: number;
  source: string;
}

// ── Estimate Momentum Types ──

export interface EstimateMomentumSignal {
  symbol: string;
  date: string;
  em_score: number;
  velocity_score: number;
  surprise_score: number;
  dispersion_score: number;
  acceleration_score: number;
  sector_rank_score: number;
  rev_velocity_score: number;
  eps_velocity_7d: number | null;
  eps_velocity_30d: number | null;
  eps_velocity_90d: number | null;
  beat_streak: number | null;
  avg_surprise_pct: number | null;
  dispersion_pct: number | null;
  company_name?: string;
  sector?: string;
}

export interface EstimateMomentumTopMovers {
  upward_revisions: EstimateMomentumSignal[];
  beat_streaks: EstimateMomentumSignal[];
  tight_dispersion: EstimateMomentumSignal[];
}

export interface EstimateMomentumSectorSummary {
  sector: string;
  num_stocks: number;
  avg_em_score: number;
  avg_velocity_score: number;
  avg_surprise_score: number;
  strong_count: number;
  streak_3plus: number;
}

// ── Consensus Blindspots Types ──

export interface ConsensusBlindspotSignal {
  symbol: string;
  date: string;
  cbs_score: number;
  cycle_score: number | null;
  cycle_position: string | null;
  consensus_gap_score: number;
  gap_type: string;
  positioning_score: number;
  positioning_flags: string | null;
  divergence_score: number;
  divergence_type: string | null;
  divergence_magnitude: number | null;
  fat_pitch_score: number;
  fat_pitch_count: number;
  fat_pitch_conditions: string | null;
  anti_pitch_count: number;
  anti_pitch_conditions: string | null;
  analyst_buy_pct: number | null;
  analyst_sell_pct: number | null;
  analyst_target_upside: number | null;
  short_interest_pct: number | null;
  institutional_pct: number | null;
  our_convergence_score: number | null;
  narrative: string | null;
}

export interface SentimentCycle {
  current: { date: string; cycle_score: number; cycle_position: string; narrative: string } | null;
  history: { date: string; cycle_score: number; cycle_position: string; narrative: string }[];
}

// ── Discovery Types ──

export interface DiscoverStock {
  symbol: string;
  date: string;
  convergence_score: number;
  module_count: number;
  conviction_level: string;
  forensic_blocked: number;
  main_signal_score: number | null;
  smartmoney_score: number | null;
  worldview_score: number | null;
  variant_score: number | null;
  research_score: number | null;
  reddit_score: number | null;
  news_displacement_score: number | null;
  alt_data_score: number | null;
  sector_expert_score: number | null;
  foreign_intel_score: number | null;
  pairs_score: number | null;
  ma_score: number | null;
  energy_intel_score: number | null;
  prediction_markets_score: number | null;
  pattern_options_score: number | null;
  ai_exec_score: number | null;
  estimate_momentum_score: number | null;
  ai_regulatory_score: number | null;
  consensus_blindspots_score: number | null;
  active_modules: string;
  narrative: string;
  // Enrichment fields
  company_name: string | null;
  sector: string | null;
  industry: string | null;
  conflict_count: number;
  max_conflict_severity: string | null;
  is_fat_pitch: number;
  fat_pitch_score: number | null;
  fat_pitch_conditions: string | null;
  has_insider_cluster: number;
  insider_score: number | null;
  is_ma_target: number;
  ma_target_score: number | null;
  deal_stage: string | null;
  has_unusual_options: number;
  options_score: number | null;
  unusual_options_count: number;
  unusual_options_bias: string | null;
}

export interface DiscoverSector {
  sector: string;
  count: number;
}

// ── Paper Trading Types ──

export interface ClosedPosition extends Position {
  exit_date: string | null;
  exit_price: number | null;
  status: string;
}

export interface PortfolioStats {
  open_count: number;
  closed_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  profit_factor: number;
}

export interface SyncResult {
  synced: number;
  symbols: string[];
}

export const api = {
  macro: () => fetcher<MacroData>('/api/macro'),
  macroHistory: () => fetcher<{ date: string; total_score: number; regime: string }[]>('/api/macro/history'),
  breadth: () => fetcher<Breadth>('/api/breadth'),
  signals: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetcher<Signal[]>(`/api/signals${qs}`);
  },
  signalSummary: () => fetcher<{ signal: string; count: number }[]>('/api/signals/summary'),
  asset: (symbol: string) => fetcher<AssetDetail>(`/api/asset/${symbol}`),
  prices: (symbol: string, days?: number) =>
    fetcher<PriceBar[]>(`/api/prices/${symbol}${days ? `?days=${days}` : ''}`),
  watchlist: () => fetcher<WatchlistItem[]>('/api/watchlist'),
  portfolio: () => fetcher<Position[]>('/api/portfolio'),
  displacement: (days = 7) => fetcher<DisplacementSignal[]>(`/api/displacement?days=${days}`),
  displacementSymbol: (symbol: string) => fetcher<DisplacementSignal[]>(`/api/displacement/${symbol}`),
  altData: (days = 7) => fetcher<AltDataSignal[]>(`/api/alt-data?days=${days}`),
  sectorExperts: () => fetcher<SectorExpertSignal[]>('/api/sector-experts'),
  sectorExpertSymbol: (symbol: string) => fetcher<SectorExpertSignal[]>(`/api/sector-experts/${symbol}`),

  // Pairs Trading
  pairs: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetcher<PairSignal[]>(`/api/pairs${qs}`);
  },
  pairRelationships: (params?: Record<string, string>) => {
    const qs = params ? '?' + new URLSearchParams(params).toString() : '';
    return fetcher<PairRelationship[]>(`/api/pairs/relationships${qs}`);
  },
  pairSpread: (symbolA: string, symbolB: string, days = 120) =>
    fetcher<PairSpread[]>(`/api/pairs/spread/${symbolA}/${symbolB}?days=${days}`),
  pairsForSymbol: (symbol: string) =>
    fetcher<{ relationships: PairRelationship[]; signals: PairSignal[] }>(`/api/pairs/${symbol}`),

  // Economic Indicators
  economicIndicators: (category?: string) => {
    const qs = category ? `?category=${category}` : '';
    return fetcher<EconomicIndicator[]>(`/api/economic-indicators${qs}`);
  },
  indicatorHistory: (id: string, days = 365) =>
    fetcher<IndicatorHistoryPoint[]>(`/api/economic-indicators/history/${id}?days=${days}`),
  heatIndex: () => fetcher<HeatIndex>('/api/economic-indicators/heat-index'),

  // Convergence
  convergence: () => fetcher<ConvergenceSignal[]>('/api/convergence'),
  convergenceSymbol: (symbol: string) => fetcher<ConvergenceSignal>(`/api/convergence/${symbol}`),
  convergenceDelta: () => fetcher<ConvergenceDelta[]>('/api/convergence/delta'),
  signalChanges: () => fetcher<SignalChange[]>('/api/signals/changes'),
  assetSignalHistory: (symbol: string, days = 90) =>
    fetcher<{ signal_history: SignalHistoryRow[]; convergence_history: ConvergenceHistoryRow[] }>(
      `/api/asset/${symbol}/signal-history?days=${days}`
    ),

  // Insider Trading
  insiderSignals: (minScore = 0, days = 30) =>
    fetcher<InsiderSignal[]>(`/api/insider-trading?min_score=${minScore}&days=${days}`),
  insiderClusterBuys: (days = 30) =>
    fetcher<InsiderSignal[]>(`/api/insider-trading/cluster-buys?days=${days}`),
  insiderTransactions: (symbol: string, days = 90) =>
    fetcher<InsiderDetail>(`/api/insider-trading/${symbol}?days=${days}`),

  // AI Executive Investment Tracker
  aiExecSignals: (minScore = 0, days = 90) =>
    fetcher<AIExecSignal[]>(`/api/ai-exec?min_score=${minScore}&days=${days}`),
  aiExecInvestments: (days = 180, execName?: string) =>
    fetcher<AIExecInvestment[]>(`/api/ai-exec/investments?days=${days}${execName ? `&exec_name=${execName}` : ''}`),
  aiExecConvergence: () =>
    fetcher<AIExecConvergence[]>('/api/ai-exec/convergence'),
  aiExecSymbol: (symbol: string) =>
    fetcher<AIExecDetail>(`/api/ai-exec/${symbol}`),

  // Hyperliquid Weekend Gap
  hlGapSignals: (weeks = 8) =>
    fetcher<HLGapSignal[]>(`/api/hyperliquid/gaps?weeks=${weeks}`),
  hlSnapshots: (ticker: string, hours = 72) =>
    fetcher<HLSnapshot[]>(`/api/hyperliquid/snapshots/${ticker}?hours=${hours}`),
  hlDeployerSpreads: (minBps = 0, hours = 72) =>
    fetcher<HLDeployerSpread[]>(`/api/hyperliquid/deployer-spreads?min_spread_bps=${minBps}&hours=${hours}`),
  hlBookDepth: () => fetcher<HLSnapshot[]>('/api/hyperliquid/book-depth'),
  hlAccuracy: () => fetcher<HLAccuracy>('/api/hyperliquid/accuracy'),

  // Thesis Lab
  thesisFunnel: () => fetcher<FunnelData>('/api/thesis/funnel'),
  thesisModels: () => fetcher<{ models: MentalModel[]; regime: string }>('/api/thesis/models'),
  thesisChecklist: (symbol: string) => fetcher<ThesisChecklist>(`/api/thesis/checklist/${symbol}`),

  // Energy Intelligence
  energyIntel: (minScore = 0) =>
    fetcher<{ signals: EnergyIntelSignal[]; summary: Record<string, number>; anomalies: EnergyAnomaly[] }>(
      `/api/energy-intel?min_score=${minScore}`
    ),
  energySupplyBalance: () => fetcher<EnergySupplyData>('/api/energy-intel/supply-balance'),
  energyProduction: () => fetcher<EnergyProductionData>('/api/energy-intel/production'),
  energyTradeFlows: () =>
    fetcher<{
      imports: { date: string; value: number }[];
      exports: { date: string; value: number }[];
      padd_stocks: { series_id: string; value: number; description: string }[];
      import_by_country: { series_id: string; value: number; description: string }[];
      comtrade: Record<string, unknown>[];
    }>('/api/energy-intel/trade-flows'),
  energyGlobalBalance: () =>
    fetcher<{
      jodi_data: JodiRecord[];
      balance: EnergyBalance | null;
      global_stocks: { country: string; value: number; mom_change: number | null }[];
    }>('/api/energy-intel/global-balance'),

  // ── Pattern Match & Options Intelligence ──
  patterns: (minScore = 0, sector?: string, phase?: string, squeezeOnly = false) =>
    fetcher<PatternScanResult[]>(
      `/api/patterns?min_score=${minScore}${sector ? `&sector=${sector}` : ''}${phase ? `&phase=${phase}` : ''}${squeezeOnly ? '&squeeze_only=true' : ''}`
    ),
  patternLayers: (symbol: string) =>
    fetcher<PatternLayerDetail>(`/api/patterns/layers/${symbol}`),
  sectorRotation: (days = 30) =>
    fetcher<SectorRotationPoint[]>(`/api/patterns/rotation?days=${days}`),
  optionsIntel: (minScore = 0) =>
    fetcher<OptionsIntelResult[]>(`/api/patterns/options?min_score=${minScore}`),
  optionsDetail: (symbol: string) =>
    fetcher<OptionsIntelResult[]>(`/api/patterns/options/${symbol}`),
  unusualActivity: (minCount = 1) =>
    fetcher<UnusualActivityRow[]>(`/api/patterns/unusual-activity?min_count=${minCount}`),
  expectedMoves: () =>
    fetcher<ExpectedMoveRow[]>('/api/patterns/expected-moves'),
  compressionSetups: () =>
    fetcher<CompressionRow[]>('/api/patterns/compression'),
  dealerExposure: () =>
    fetcher<DealerExposureRow[]>('/api/patterns/dealer-exposure'),

  // M&A Intelligence
  maSignals: (minScore = 0, days = 30) =>
    fetcher<MASignal[]>(`/api/ma-signals?min_score=${minScore}&days=${days}`),
  maTopTargets: () =>
    fetcher<MASignal[]>('/api/ma-signals/top-targets'),
  maRumors: (days = 30) =>
    fetcher<MARumor[]>(`/api/ma-signals/rumors?days=${days}`),
  maDetail: (symbol: string) =>
    fetcher<{ signals: MASignal[]; rumors: MARumor[] }>(`/api/ma-signals/${symbol}`),

  // Prediction Markets
  predictionMarkets: (minScore = 0, days = 7) =>
    fetcher<PredictionMarketSignal[]>(`/api/prediction-markets?min_score=${minScore}&days=${days}`),
  predictionMarketsRaw: (category?: string, days = 3) =>
    fetcher<PredictionMarketRaw[]>(
      `/api/prediction-markets/raw?days=${days}${category ? `&category=${category}` : ''}`
    ),
  predictionMarketCategories: () =>
    fetcher<PredictionMarketCategory[]>('/api/prediction-markets/categories'),

  // AI Regulatory Intelligence
  regulatorySignals: (minScore = 0, days = 7) =>
    fetcher<RegulatorySignal[]>(`/api/regulatory?min_score=${minScore}&days=${days}`),
  regulatoryEvents: (source?: string, category?: string, jurisdiction?: string, minSeverity = 1, days = 14) =>
    fetcher<RegulatoryEvent[]>(
      `/api/regulatory/events?min_severity=${minSeverity}&days=${days}${source ? `&source=${source}` : ''}${category ? `&category=${category}` : ''}${jurisdiction ? `&jurisdiction=${jurisdiction}` : ''}`
    ),
  regulatoryCategories: () =>
    fetcher<RegulatoryCategory[]>('/api/regulatory/categories'),
  regulatorySources: () =>
    fetcher<RegulatorySource[]>('/api/regulatory/sources'),
  regulatoryJurisdictions: () =>
    fetcher<RegulatoryJurisdiction[]>('/api/regulatory/jurisdictions'),
  regulatorySymbol: (symbol: string, days = 14) =>
    fetcher<{ signals: RegulatorySignal[]; events: RegulatoryEvent[] }>(`/api/regulatory/${symbol}?days=${days}`),

  // Worldview / Global Macro
  worldview: () =>
    fetcher<WorldviewSignal[]>('/api/worldview'),
  worldviewTheses: () =>
    fetcher<WorldviewThesis[]>('/api/worldview/theses'),
  worldMacro: () =>
    fetcher<WorldMacroIndicator[]>('/api/worldview/world-macro'),
  worldviewSymbol: (symbol: string) =>
    fetcher<WorldviewSignal[]>(`/api/worldview/${symbol}`),

  // Intelligence Reports
  reportGenerate: (topic: string) =>
    fetch(`/api/report/generate?topic=${encodeURIComponent(topic)}`, { method: 'POST', cache: 'no-store' })
      .then(r => r.json()) as Promise<ReportGenerateResult>,
  reportLatest: (topic: string) =>
    fetcher<IntelligenceReport>(`/api/report/latest?topic=${encodeURIComponent(topic)}`),
  reportList: () =>
    fetcher<ReportListItem[]>('/api/report/list'),

  // Thematic Alpha Scanner (Trading Ideas)
  tradingIdeas: (theme?: string, minScore = 0) =>
    fetcher<ThematicIdea[]>(
      `/api/trading-ideas?min_score=${minScore}${theme ? `&theme=${theme}` : ''}`
    ),
  tradingIdeasThemes: () =>
    fetcher<ThemeSummary[]>('/api/trading-ideas/themes'),
  tradingIdeasTop: (limit = 10) =>
    fetcher<ThematicIdea[]>(`/api/trading-ideas/top?limit=${limit}`),
  tradingIdeasDetail: (symbol: string) =>
    fetcher<ThematicIdeaDetail>(`/api/trading-ideas/${symbol}`),
  tradingIdeasTheme: (theme: string) =>
    fetcher<ThematicIdea[]>(`/api/trading-ideas/theme/${theme}`),
  tradingIdeasSubTheme: (subTheme: string) =>
    fetcher<ThematicIdea[]>(`/api/trading-ideas/sub-theme/${subTheme}`),
  tradingIdeasHistory: (symbol: string, days = 30) =>
    fetcher<ThematicIdea[]>(`/api/trading-ideas/history/${symbol}?days=${days}`),

  // Estimate Revision Momentum
  estimateMomentum: (minScore = 0, limit = 50, sector?: string) =>
    fetcher<EstimateMomentumSignal[]>(
      `/api/estimate-momentum?min_score=${minScore}&limit=${limit}${sector ? `&sector=${sector}` : ''}`
    ),
  estimateMomentumDetail: (symbol: string) =>
    fetcher<{ symbol: string; signals: EstimateMomentumSignal[]; snapshots: Record<string, unknown>[] }>(
      `/api/estimate-momentum/${symbol}`
    ),
  estimateMomentumTopMovers: () =>
    fetcher<EstimateMomentumTopMovers>('/api/estimate-momentum/top-movers'),
  estimateMomentumSectors: () =>
    fetcher<EstimateMomentumSectorSummary[]>('/api/estimate-momentum/sector-summary'),

  // Consensus Blindspots
  consensusBlindspots: (minScore = 0, limit = 50) =>
    fetcher<ConsensusBlindspotSignal[]>(`/api/consensus-blindspots?min_score=${minScore}&limit=${limit}`),
  sentimentCycle: () =>
    fetcher<SentimentCycle>('/api/consensus-blindspots/cycle'),
  fatPitches: () =>
    fetcher<ConsensusBlindspotSignal[]>('/api/consensus-blindspots/fat-pitches'),
  crowdedTrades: () =>
    fetcher<ConsensusBlindspotSignal[]>('/api/consensus-blindspots/crowded'),
  signalDivergences: () =>
    fetcher<ConsensusBlindspotSignal[]>('/api/consensus-blindspots/divergences'),
  consensusBlindspotsSymbol: (symbol: string) =>
    fetcher<{ current: ConsensusBlindspotSignal; history: ConsensusBlindspotSignal[] }>(
      `/api/consensus-blindspots/${symbol}`
    ),

  // Discovery
  discover: () => fetcher<DiscoverStock[]>('/api/discover'),
  discoverSectors: () => fetcher<DiscoverSector[]>('/api/discover/sectors'),

  // Signal Conflicts
  signalConflicts: (severity?: string) =>
    fetcher<SignalConflict[]>(`/api/signal-conflicts${severity ? `?severity=${severity}` : ''}`),
  signalConflictsSummary: () =>
    fetcher<ConflictSummary[]>('/api/signal-conflicts/summary'),
  signalConflictsSymbol: (symbol: string) =>
    fetcher<SignalConflict[]>(`/api/signal-conflicts/${symbol}`),

  // Stress Test
  stressTest: () => fetcher<StressTestResult[]>('/api/stress-test'),
  stressTestConcentration: () => fetcher<ConcentrationRisk>('/api/stress-test/concentration'),
  stressTestScenario: (scenario: string) =>
    fetcher<StressTestResult>(`/api/stress-test/${scenario}`),

  // Paper Trading
  portfolioOpen: () => fetcher<Position[]>('/api/portfolio'),
  portfolioClosed: (limit = 50) => fetcher<ClosedPosition[]>(`/api/portfolio/closed?limit=${limit}`),
  portfolioStats: () => fetcher<PortfolioStats>('/api/portfolio/stats'),
  portfolioSync: () =>
    fetch('/api/portfolio/sync', { method: 'POST', cache: 'no-store' }).then(r => r.json()) as Promise<SyncResult>,

  // Performance / Data Moat
  performanceSummary: () => fetcher<PerformanceSummary>('/api/performance/summary'),
  performanceModules: (regime = 'all', sector = 'all') =>
    fetcher<ModulePerformance[]>(`/api/performance/modules?regime=${regime}&sector=${sector}`),
  performanceTrackRecord: () => fetcher<TrackRecordMonth[]>('/api/performance/track-record'),
  performanceWeightHistory: (regime = 'all') =>
    fetcher<WeightHistoryEntry[]>(`/api/performance/weight-history?regime=${regime}`),

  // ── Alpha Intelligence ──
  crossAsset: (limit = 50, minScore = 60) =>
    fetcher<{ date: string | null; count: number; fat_pitches: number; opportunities: CrossAssetOpp[] }>(
      `/api/alpha/cross-asset?limit=${limit}&min_score=${minScore}`
    ),
  crossAssetFatPitches: () =>
    fetcher<{ count: number; fat_pitches: CrossAssetOpp[] }>('/api/alpha/cross-asset/fat-pitches'),
  crossAssetByClass: () =>
    fetcher<{ breakdown: CrossAssetClass[] }>('/api/alpha/cross-asset/by-class'),

  narratives: (minStrength = 0) =>
    fetcher<{ date: string | null; count: number; narratives: NarrativeSignal[] }>(
      `/api/alpha/narratives?min_strength=${minStrength}`
    ),
  narrativeDetail: (narrative: string) =>
    fetcher<{ narrative: string; signal: NarrativeSignal | null; top_assets: NarrativeAsset[] }>(
      `/api/alpha/narratives/${encodeURIComponent(narrative)}`
    ),

  icSummary: (regime = 'all', horizon = 20) =>
    fetcher<{ regime: string; horizon_days: number; module_count: number; modules: ModuleIC[] }>(
      `/api/alpha/ic/summary?regime=${regime}&horizon=${horizon}`
    ),
  icRanking: () =>
    fetcher<{ modules: ModuleICRank[] }>('/api/alpha/ic/ranking'),
  icRegimeComparison: (horizon = 20) =>
    fetcher<{ horizon_days: number; data: ModuleIC[] }>(`/api/alpha/ic/regime-comparison?horizon=${horizon}`),
};

export interface ThematicIdea {
  symbol: string;
  date: string;
  theme: string;
  sub_theme: string;
  name: string;
  policy_score: number;
  growth_score: number;
  technical_score: number;
  valuation_score: number;
  institutional_score: number;
  composite_score: number;
  market_cap: number;
  price: number;
  revenue_growth: number | null;
  earnings_growth: number | null;
  pe_ratio: number | null;
  ps_ratio: number | null;
  rsi_14: number | null;
  momentum_3m: number | null;
  short_pct: number | null;
  catalysts: string;
  narrative: string;
}

export interface ThemeSummary {
  theme: string;
  num_stocks: number;
  avg_score: number;
  top_score: number;
  avg_policy: number;
  avg_growth: number;
  avg_technical: number;
  strong_ideas: number;
}

export interface ThematicIdeaDetail {
  ideas: ThematicIdea[];
  convergence: Record<string, number | string | null> | null;
  technical: Record<string, number | null> | null;
}

export interface ReportGenerateResult {
  status: string;
  topic: string;
  stock_count: number;
  pairs_count: number;
  output_path: string;
  html: string | null;
  markdown: string | null;
  error?: string;
}

export interface IntelligenceReport {
  id: number;
  topic: string;
  topic_type: string;
  expert_type: string;
  generated_at: string;
  regime: string;
  symbols_covered: string;
  report_html: string;
  report_markdown: string;
  metadata: string;
  status?: string;
}

export interface ReportListItem {
  id: number;
  topic: string;
  topic_type: string;
  expert_type: string;
  generated_at: string;
  regime: string;
  symbols_covered: string;
  metadata: string;
}

// ── Performance / Data Moat Types ──

export interface ConvictionStat {
  level: string;
  count_5d?: number;
  win_rate_5d?: number;
  avg_return_5d?: number;
  count_10d?: number;
  win_rate_10d?: number;
  avg_return_10d?: number;
  count_20d?: number;
  win_rate_20d?: number;
  avg_return_20d?: number;
  count_30d?: number;
  win_rate_30d?: number;
  avg_return_30d?: number;
}

export interface PerformanceSummary {
  total_signals: number;
  resolved_by_window: Record<string, number>;
  days_running: number;
  first_signal_date: string | null;
  by_conviction: ConvictionStat[];
  data_sufficient: boolean;
  latest_optimizer: { date: string; action: string; details: string } | null;
}

export interface ModulePerformance {
  report_date: string;
  module_name: string;
  regime: string;
  sector: string;
  total_signals: number;
  win_count: number;
  win_rate: number;
  avg_return_1d: number | null;
  avg_return_5d: number | null;
  avg_return_10d: number | null;
  avg_return_20d: number | null;
  avg_return_30d: number | null;
  avg_return_60d: number | null;
  avg_return_90d: number | null;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
  observation_count: number | null;
  confidence_interval_low: number | null;
  confidence_interval_high: number | null;
  static_weight: number;
  adaptive_weight: number | null;
}

export interface TrackRecordMonth {
  month: string;
  total_signals: number;
  wins_5d: number | null;
  wins_20d: number | null;
  wins_30d: number | null;
  avg_5d: number | null;
  avg_20d: number | null;
  avg_30d: number | null;
  resolved_5d: number;
  resolved_20d: number;
  resolved_30d: number;
  cumulative_win_rate: number;
  cumulative_total: number;
}

export interface WeightHistoryModule {
  module_name: string;
  weight: number;
  prior_weight: number;
  reason: string | null;
}

export interface WeightHistoryEntry {
  date: string;
  modules: WeightHistoryModule[];
  total_delta: number;
}


// ── Alpha Intelligence Types ──

export interface CrossAssetOpp {
  symbol: string;
  date: string;
  asset_class: string;
  sector: string | null;
  opportunity_score: number;
  technical_score: number | null;
  fundamental_score: number | null;
  momentum_5d: number | null;
  momentum_20d: number | null;
  momentum_60d: number | null;
  regime_fit_score: number | null;
  relative_value_rank: number | null;
  is_fat_pitch: number;
  fat_pitch_reason: string | null;
  conviction: string | null;
  details: string | null;
}

export interface CrossAssetClass {
  asset_class: string;
  count: number;
  avg_score: number;
  top_score: number;
  fat_pitches: number;
}

export interface NarrativeSignal {
  narrative_id: string;
  narrative: string;
  date: string;
  strength_score: number;
  crowding_score: number | null;
  opportunity_score: number | null;
  maturity: string | null;
  best_expressions: string | null;
  worst_expressions: string | null;
  details: string | null;
}

export interface NarrativeAsset {
  symbol: string;
  asset_class: string;
  direction: string;
  fit_score: number;
  rationale: string | null;
}

export interface ModuleIC {
  module: string;
  regime: string;
  horizon_days: number;
  mean_ic: number | null;
  std_ic: number | null;
  information_ratio: number | null;
  ic_positive_pct: number | null;
  n_dates: number;
  avg_n_stocks: number;
  ci_low: number | null;
  ci_high: number | null;
  is_significant: number;
  pvalue: number | null;
}

export interface ModuleICRank {
  module: string;
  avg_ic: number | null;
  avg_ir: number | null;
  sig_rate: number | null;
  worst_ic: number | null;
  best_ic: number | null;
}
