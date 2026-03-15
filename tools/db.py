"""Database helpers for the Druckenmiller Alpha System.
SQLite connection management, query helpers, and bulk upsert.
DB path: .tmp/druckenmiller.db (relative to project root).
"""
import os, sqlite3
from pathlib import Path
from contextlib import contextmanager

_project_root = str(Path(__file__).parent.parent)
if os.environ.get("DATABASE_PATH"):
    DB_PATH = os.environ["DATABASE_PATH"]
    DB_DIR = os.path.dirname(DB_PATH)
else:
    DB_DIR = os.path.join(_project_root, ".tmp")
    DB_PATH = os.path.join(DB_DIR, "druckenmiller.db")


def get_conn():
    """Return a sqlite3 connection with row_factory = Row."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Ensure all core tables exist (CREATE IF NOT EXISTS)."""
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
CREATE TABLE IF NOT EXISTS stock_universe (symbol TEXT PRIMARY KEY, name TEXT, sector TEXT, industry TEXT, market_cap REAL);
CREATE TABLE IF NOT EXISTS price_data (symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, adj_close REAL, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS technical_scores (symbol TEXT, date TEXT, trend_score REAL, momentum_score REAL, volatility_score REAL, volume_score REAL, total_score REAL, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS fundamental_scores (symbol TEXT, date TEXT, value_score REAL, quality_score REAL, growth_score REAL, total_score REAL, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS fundamentals (symbol TEXT NOT NULL, metric TEXT NOT NULL, value REAL, updated_at TEXT DEFAULT (datetime('now')), PRIMARY KEY (symbol, metric));
CREATE TABLE IF NOT EXISTS signals (symbol TEXT, date TEXT, composite_score REAL, signal TEXT, sector TEXT, technical_score REAL, fundamental_score REAL, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS macro_indicators (indicator TEXT, date TEXT, value REAL, PRIMARY KEY (indicator, date));
CREATE TABLE IF NOT EXISTS macro_scores (date TEXT PRIMARY KEY, regime TEXT, regime_score REAL, details TEXT);
CREATE TABLE IF NOT EXISTS market_breadth (date TEXT PRIMARY KEY, advancers INTEGER, decliners INTEGER, new_highs INTEGER, new_lows INTEGER, adv_dec_ratio REAL, breadth_score REAL, sector_rotation TEXT);
CREATE TABLE IF NOT EXISTS sector_rotation (sector TEXT, date TEXT, rs_ratio REAL, rs_momentum REAL, quadrant TEXT, rotation_score REAL, score REAL, PRIMARY KEY (sector, date));
CREATE TABLE IF NOT EXISTS news_sentiment (symbol TEXT, date TEXT, headline TEXT, source TEXT, sentiment REAL, relevance REAL, PRIMARY KEY (symbol, date, headline));
CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, notes TEXT, alert_price_above REAL, alert_price_below REAL, alert_tech_above REAL);
CREATE TABLE IF NOT EXISTS portfolio (symbol TEXT PRIMARY KEY, shares REAL, entry_price REAL, entry_date TEXT, stop_loss REAL, target REAL, notes TEXT);
CREATE TABLE IF NOT EXISTS smart_money_scores (symbol TEXT, date TEXT, manager_count INTEGER, conviction_score REAL, top_holders TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS filings_13f (manager TEXT, symbol TEXT, date TEXT, shares REAL, value REAL, change_pct REAL, PRIMARY KEY (manager, symbol, date));
CREATE TABLE IF NOT EXISTS worldview_signals (date TEXT, thesis TEXT, direction TEXT, confidence REAL, affected_sectors TEXT, details TEXT, PRIMARY KEY (date, thesis));
CREATE TABLE IF NOT EXISTS foreign_intel_signals (symbol TEXT, date TEXT, source_country TEXT, signal_type TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date, source_country));
CREATE TABLE IF NOT EXISTS foreign_intel_url_cache (url TEXT PRIMARY KEY, fetched_date TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS foreign_ticker_map (foreign_symbol TEXT PRIMARY KEY, us_symbol TEXT, exchange TEXT, country TEXT);
CREATE TABLE IF NOT EXISTS research_signals (symbol TEXT, date TEXT, source TEXT, signal_type TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date, source));
CREATE TABLE IF NOT EXISTS research_url_cache (url TEXT PRIMARY KEY, fetched_date TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS news_displacement (symbol TEXT, date TEXT, displacement_score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS reddit_signals (symbol TEXT, date TEXT, subreddit TEXT, mention_count INTEGER, sentiment REAL, score REAL, PRIMARY KEY (symbol, date, subreddit));
CREATE TABLE IF NOT EXISTS alt_data_scores (symbol TEXT, date TEXT, source TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date, source));
CREATE TABLE IF NOT EXISTS alternative_data (symbol TEXT, date TEXT, source TEXT, metric TEXT, value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric));
CREATE TABLE IF NOT EXISTS convergence_signals (symbol TEXT NOT NULL, date TEXT NOT NULL, convergence_score REAL NOT NULL, module_count INTEGER, conviction_level TEXT, forensic_blocked INTEGER DEFAULT 0, main_signal_score REAL, smartmoney_score REAL, worldview_score REAL, variant_score REAL, research_score REAL, reddit_score REAL, active_modules TEXT, narrative TEXT, news_displacement_score REAL, alt_data_score REAL, sector_expert_score REAL, foreign_intel_score REAL, pairs_score REAL, ma_score REAL, energy_intel_score REAL, prediction_markets_score REAL, pattern_options_score REAL, estimate_momentum_score REAL, ai_regulatory_score REAL, consensus_blindspots_score REAL, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS signal_outcomes (symbol TEXT NOT NULL, signal_date TEXT NOT NULL, conviction_level TEXT, convergence_score REAL, module_count INTEGER, active_modules TEXT, regime_at_signal TEXT, sector TEXT, market_cap_bucket TEXT, entry_price REAL, price_1d REAL, return_1d REAL, price_5d REAL, return_5d REAL, price_10d REAL, return_10d REAL, price_20d REAL, return_20d REAL, price_30d REAL, return_30d REAL, price_60d REAL, return_60d REAL, price_90d REAL, return_90d REAL, hit_target INTEGER, hit_stop INTEGER, da_risk_score REAL, da_warning INTEGER DEFAULT 0, PRIMARY KEY (symbol, signal_date));
CREATE TABLE IF NOT EXISTS module_performance (report_date TEXT NOT NULL, module_name TEXT NOT NULL, regime TEXT DEFAULT 'all', sector TEXT DEFAULT 'all', total_signals INTEGER, win_count INTEGER, win_rate REAL, avg_return_1d REAL, avg_return_5d REAL, avg_return_10d REAL, avg_return_20d REAL, avg_return_30d REAL, avg_return_60d REAL, avg_return_90d REAL, sharpe_ratio REAL, max_drawdown REAL, observation_count INTEGER, confidence_interval_low REAL, confidence_interval_high REAL, PRIMARY KEY (report_date, module_name, regime, sector));
CREATE TABLE IF NOT EXISTS weight_history (date TEXT NOT NULL, regime TEXT NOT NULL, module_name TEXT NOT NULL, weight REAL NOT NULL, prior_weight REAL, reason TEXT, PRIMARY KEY (date, regime, module_name));
CREATE TABLE IF NOT EXISTS weight_optimizer_log (date TEXT NOT NULL, action TEXT NOT NULL, details TEXT, PRIMARY KEY (date, action));
CREATE TABLE IF NOT EXISTS sector_expert_signals (symbol TEXT, date TEXT, sector TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS pattern_scan (symbol TEXT, date TEXT, regime TEXT, regime_score REAL, vix_percentile REAL, sector_quadrant TEXT, rotation_score REAL, rs_ratio REAL, rs_momentum REAL, patterns_detected TEXT, pattern_score REAL, sr_proximity TEXT, volume_profile_score REAL, hurst_exponent REAL, mr_score REAL, momentum_score REAL, compression_score REAL, squeeze_active INTEGER, wyckoff_phase TEXT, wyckoff_confidence REAL, earnings_days_to_next INTEGER, vol_regime TEXT, pattern_scan_score REAL, layer_scores TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS pattern_options_signals (symbol TEXT, date TEXT, pattern_scan_score REAL, options_score REAL, pattern_options_score REAL, top_pattern TEXT, top_signal TEXT, narrative TEXT, status TEXT, score REAL, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS options_intel (symbol TEXT, date TEXT, atm_iv REAL, hv_20d REAL, iv_premium REAL, iv_rank REAL, iv_percentile REAL, expected_move_pct REAL, straddle_cost REAL, volume_pc_ratio REAL, oi_pc_ratio REAL, pc_signal TEXT, unusual_activity_count INTEGER, unusual_activity TEXT, unusual_direction_bias TEXT, skew_25d REAL, skew_direction TEXT, term_structure_signal TEXT, net_gex REAL, gamma_flip_level REAL, vanna_exposure REAL, max_pain REAL, put_wall REAL, call_wall REAL, dealer_regime TEXT, options_score REAL, put_call_ratio REAL, unusual_volume INTEGER, score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS variant_analysis (symbol TEXT, date TEXT, variant_score REAL, thesis TEXT, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS devils_advocate (symbol TEXT, date TEXT, bear_thesis TEXT, kill_scenario TEXT, historical_analog TEXT, risk_score REAL, bull_context TEXT, regime_at_signal TEXT, warning_flag INTEGER, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS transcript_analysis (symbol TEXT, date TEXT, quarter TEXT, score REAL, summary TEXT, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS letter_analysis (symbol TEXT, date TEXT, score REAL, summary TEXT, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS forensic_alerts (symbol TEXT, date TEXT, alert_type TEXT, severity TEXT, details TEXT, PRIMARY KEY (symbol, date, alert_type));
CREATE TABLE IF NOT EXISTS earnings_calendar (symbol TEXT, date TEXT, estimate REAL, actual REAL, surprise REAL, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS pair_relationships (symbol_a TEXT, symbol_b TEXT, sector TEXT, coint_pvalue REAL, hedge_ratio REAL, half_life REAL, correlation REAL, updated_date TEXT, PRIMARY KEY (symbol_a, symbol_b));
CREATE TABLE IF NOT EXISTS pair_spreads (symbol_a TEXT, symbol_b TEXT, date TEXT, spread REAL, z_score REAL, PRIMARY KEY (symbol_a, symbol_b, date));
CREATE TABLE IF NOT EXISTS pair_signals (symbol_a TEXT, symbol_b TEXT, date TEXT, signal_type TEXT, z_score REAL, direction TEXT, details TEXT, PRIMARY KEY (symbol_a, symbol_b, date, signal_type));
CREATE TABLE IF NOT EXISTS ma_signals (symbol TEXT, date TEXT, ma_score REAL, target_score REAL, rumor_score REAL, deal_stage TEXT, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS ma_rumors (symbol TEXT, date TEXT, source TEXT, headline TEXT, credibility REAL, deal_stage TEXT, details TEXT, PRIMARY KEY (symbol, date, source));
CREATE TABLE IF NOT EXISTS insider_transactions (symbol TEXT, date TEXT, insider_name TEXT, title TEXT, transaction_type TEXT, shares REAL, value REAL, PRIMARY KEY (symbol, date, insider_name, transaction_type));
CREATE TABLE IF NOT EXISTS insider_signals (symbol TEXT, date TEXT, insider_score REAL, cluster_buy INTEGER, large_csuite INTEGER, unusual_volume INTEGER, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS economic_dashboard (indicator_id TEXT, date TEXT, category TEXT, name TEXT, value REAL, prev_value REAL, mom_change REAL, yoy_change REAL, zscore REAL, trend TEXT, signal TEXT, last_updated TEXT, PRIMARY KEY (indicator_id, date));
CREATE TABLE IF NOT EXISTS economic_heat_index (date TEXT PRIMARY KEY, heat_index REAL, improving_count INTEGER, deteriorating_count INTEGER, stable_count INTEGER, leading_count INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS hl_price_snapshots (ticker TEXT, timestamp TEXT, mid_price REAL, deployer TEXT, PRIMARY KEY (ticker, timestamp, deployer));
CREATE TABLE IF NOT EXISTS hl_gap_signals (ticker TEXT, date TEXT, predicted_gap REAL, actual_gap REAL, signal_time TEXT, details TEXT, PRIMARY KEY (ticker, date));
CREATE TABLE IF NOT EXISTS hl_deployer_spreads (ticker TEXT, date TEXT, deployer_a TEXT, deployer_b TEXT, spread REAL, PRIMARY KEY (ticker, date, deployer_a, deployer_b));
CREATE TABLE IF NOT EXISTS prediction_market_signals (symbol TEXT, date TEXT, pm_score REAL, market_count INTEGER, net_impact REAL, status TEXT, narrative TEXT, sector TEXT, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS prediction_market_raw (market_id TEXT, date TEXT, question TEXT, impact_category TEXT, yes_probability REAL, volume REAL, liquidity REAL, direction TEXT, confidence REAL, specific_symbols TEXT, rationale TEXT, end_date TEXT, probability REAL, category TEXT, relevance TEXT, PRIMARY KEY (market_id, date));
CREATE TABLE IF NOT EXISTS world_macro_indicators (indicator TEXT, country TEXT, date TEXT, value REAL, source TEXT, PRIMARY KEY (indicator, country, date));
CREATE TABLE IF NOT EXISTS estimate_snapshots (symbol TEXT, date TEXT, eps_current REAL, eps_next REAL, rev_current REAL, rev_next REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS estimate_momentum_signals (symbol TEXT, date TEXT, em_score REAL, revision_velocity REAL, surprise_momentum REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS regulatory_signals (symbol TEXT, date TEXT, reg_score REAL, event_count INTEGER, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS regulatory_events (event_id TEXT, date TEXT, title TEXT, source TEXT, severity REAL, category TEXT, direction TEXT, jurisdiction TEXT, affected_symbols TEXT, details TEXT, PRIMARY KEY (event_id, date));
CREATE TABLE IF NOT EXISTS consensus_blindspot_signals (symbol TEXT, date TEXT, cbs_score REAL, gap_type TEXT, cycle_position REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS intelligence_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, topic TEXT, report_type TEXT, content TEXT, metadata TEXT);
CREATE TABLE IF NOT EXISTS thematic_ideas (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, theme TEXT, symbols TEXT, score REAL, details TEXT);
CREATE TABLE IF NOT EXISTS ai_exec_signals (symbol TEXT, date TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS ai_exec_investments (symbol TEXT, date TEXT, company TEXT, investment_type TEXT, amount REAL, details TEXT, PRIMARY KEY (symbol, date, investment_type));
CREATE TABLE IF NOT EXISTS ai_exec_url_cache (url TEXT PRIMARY KEY, fetched_date TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS energy_intel_signals (symbol TEXT, date TEXT, energy_intel_score REAL, inventory_signal REAL, production_signal REAL, demand_signal REAL, trade_flow_signal REAL, global_balance_signal REAL, ticker_category TEXT, narrative TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS energy_eia_enhanced (series_id TEXT, date TEXT, value REAL, category TEXT, description TEXT, wow_change REAL, yoy_change REAL, PRIMARY KEY (series_id, date));
CREATE TABLE IF NOT EXISTS energy_supply_anomalies (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, anomaly_type TEXT, series_id TEXT, description TEXT, zscore REAL, severity REAL, affected_tickers TEXT, details TEXT, status TEXT DEFAULT 'active', detected_at TEXT);
CREATE TABLE IF NOT EXISTS energy_trade_flows (reporter TEXT, partner TEXT, commodity_code TEXT, period TEXT, trade_flow TEXT, value_usd REAL, quantity_kg REAL, last_updated TEXT, date TEXT, country TEXT, product TEXT, flow_type TEXT, value REAL, PRIMARY KEY (reporter, partner, commodity_code, period, trade_flow));
CREATE TABLE IF NOT EXISTS energy_seasonal_norms (series_id TEXT, week_of_year INTEGER, avg_value REAL, std_value REAL, min_value REAL, max_value REAL, sample_count INTEGER, last_updated TEXT, PRIMARY KEY (series_id, week_of_year));
CREATE TABLE IF NOT EXISTS energy_jodi_data (country TEXT, indicator TEXT, date TEXT, value REAL, unit TEXT, mom_change REAL, yoy_change REAL, last_updated TEXT, flow TEXT, product TEXT, PRIMARY KEY (country, indicator, date));
CREATE TABLE IF NOT EXISTS global_energy_benchmarks (benchmark_id TEXT, date TEXT, name TEXT, unit TEXT, region TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, last_updated TEXT, PRIMARY KEY (benchmark_id, date));
CREATE TABLE IF NOT EXISTS global_energy_curves (curve_id TEXT, date TEXT, months_out INTEGER, contract_ticker TEXT, price REAL, last_updated TEXT, PRIMARY KEY (curve_id, date, months_out));
CREATE TABLE IF NOT EXISTS global_energy_spreads (spread_id TEXT, date TEXT, name TEXT, value REAL, leg_a REAL, leg_b REAL, assessment TEXT, unit TEXT, last_updated TEXT, PRIMARY KEY (spread_id, date));
CREATE TABLE IF NOT EXISTS global_energy_carbon (market_id TEXT, date TEXT, source_ticker TEXT, price REAL, unit TEXT, last_updated TEXT, PRIMARY KEY (market_id, date));
CREATE TABLE IF NOT EXISTS global_energy_signals (symbol TEXT, date TEXT, gem_score REAL, category TEXT, term_structure_signal REAL, basis_signal REAL, crack_signal REAL, carbon_signal REAL, narrative TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS signal_conflicts (symbol TEXT, date TEXT, conflict_type TEXT, severity TEXT, description TEXT, module_a TEXT, module_a_score REAL, module_b TEXT, module_b_score REAL, score_gap REAL, PRIMARY KEY (symbol, date, conflict_type));
CREATE TABLE IF NOT EXISTS thesis_snapshots (date TEXT, thesis TEXT, direction TEXT, confidence REAL, affected_sectors TEXT, PRIMARY KEY (date, thesis));
CREATE TABLE IF NOT EXISTS thesis_alerts (date TEXT, thesis TEXT, alert_type TEXT, severity TEXT, description TEXT, affected_symbols TEXT, lookback_days INTEGER, old_state TEXT, new_state TEXT, PRIMARY KEY (date, thesis, alert_type));
CREATE TABLE IF NOT EXISTS earnings_transcripts (symbol TEXT NOT NULL, date TEXT NOT NULL, quarter TEXT, filing_url TEXT, word_count INTEGER, sentiment REAL, hedging_ratio REAL, confidence_ratio REAL, key_phrases TEXT, PRIMARY KEY (symbol, quarter));
CREATE TABLE IF NOT EXISTS earnings_nlp_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, earnings_nlp_score REAL, sentiment_delta REAL, hedging_delta REAL, guidance_score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS gov_intel_raw (symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL, event_type TEXT NOT NULL, severity REAL, details TEXT, PRIMARY KEY (symbol, date, source, event_type));
CREATE TABLE IF NOT EXISTS gov_intel_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, gov_intel_score REAL, warn_score REAL, osha_score REAL, epa_score REAL, fcc_score REAL, lobbying_score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS labor_intel_raw (symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric));
CREATE TABLE IF NOT EXISTS labor_intel_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, labor_intel_score REAL, h1b_score REAL, hiring_score REAL, morale_score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS supply_chain_raw (date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value REAL, sector TEXT, details TEXT, PRIMARY KEY (date, source, metric));
CREATE TABLE IF NOT EXISTS supply_chain_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, supply_chain_score REAL, rail_score REAL, shipping_score REAL, trucking_score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS digital_exhaust_raw (symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value REAL, prior_value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric));
CREATE TABLE IF NOT EXISTS digital_exhaust_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, digital_exhaust_score REAL, app_score REAL, github_score REAL, pricing_score REAL, domain_score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS pharma_intel_raw (symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric));
CREATE TABLE IF NOT EXISTS pharma_intel_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, pharma_intel_score REAL, trial_velocity_score REAL, stage_shift_score REAL, cms_score REAL, rx_score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS stress_test_results (date TEXT, scenario TEXT, scenario_name TEXT, portfolio_impact_pct REAL, position_count INTEGER, position_details TEXT, worst_hit TEXT, best_positioned TEXT, PRIMARY KEY (date, scenario));
CREATE TABLE IF NOT EXISTS concentration_risk (date TEXT PRIMARY KEY, hhi REAL, concentration_level TEXT, top_sector TEXT, top_sector_pct REAL, details TEXT);
CREATE TABLE IF NOT EXISTS cross_asset_opportunities (symbol TEXT, date TEXT, asset_class TEXT, sector TEXT, opportunity_score REAL, technical_score REAL, fundamental_score REAL, momentum_5d REAL, momentum_20d REAL, momentum_60d REAL, regime_fit_score REAL, relative_value_rank REAL, is_fat_pitch INTEGER DEFAULT 0, fat_pitch_reason TEXT, conviction TEXT, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS signal_ic_results (module TEXT, signal_date TEXT, horizon_days INTEGER, ic_value REAL, pvalue REAL, n_stocks INTEGER, regime TEXT, PRIMARY KEY (module, signal_date, horizon_days, regime));
CREATE TABLE IF NOT EXISTS module_ic_summary (module TEXT, regime TEXT, horizon_days INTEGER, mean_ic REAL, std_ic REAL, information_ratio REAL, ic_positive_pct REAL, n_dates INTEGER, avg_n_stocks REAL, ci_low REAL, ci_high REAL, is_significant INTEGER, pvalue REAL, PRIMARY KEY (module, regime, horizon_days));
CREATE TABLE IF NOT EXISTS narrative_signals (narrative_id TEXT, date TEXT, narrative_name TEXT, strength_score REAL, crowding_score REAL, opportunity_score REAL, maturity TEXT, best_expression TEXT, avoid TEXT, macro_confirmations INTEGER, asset_confirmations INTEGER, details TEXT, PRIMARY KEY (narrative_id, date));
CREATE TABLE IF NOT EXISTS narrative_asset_map (narrative_id TEXT, symbol TEXT, date TEXT, asset_class TEXT, role TEXT, quality_score REAL, timing_score REAL, crowding_score REAL, combined_score REAL, PRIMARY KEY (narrative_id, symbol, date));
    """)
    conn.commit()

    # Migrations: add new columns to existing tables safely
    _migrate_columns = [
        ("signal_outcomes", "sector", "TEXT"),
        ("signal_outcomes", "market_cap_bucket", "TEXT"),
        ("signal_outcomes", "price_1d", "REAL"), ("signal_outcomes", "return_1d", "REAL"),
        ("signal_outcomes", "price_5d", "REAL"), ("signal_outcomes", "return_5d", "REAL"),
        ("signal_outcomes", "price_10d", "REAL"), ("signal_outcomes", "return_10d", "REAL"),
        ("signal_outcomes", "price_20d", "REAL"), ("signal_outcomes", "return_20d", "REAL"),
        ("convergence_signals", "earnings_nlp_score", "REAL"),
        ("convergence_signals", "gov_intel_score", "REAL"),
        ("convergence_signals", "labor_intel_score", "REAL"),
        ("convergence_signals", "supply_chain_score", "REAL"),
        ("convergence_signals", "digital_exhaust_score", "REAL"),
        ("convergence_signals", "pharma_intel_score", "REAL"),
        ("energy_eia_enhanced", "description", "TEXT"),
        ("energy_eia_enhanced", "wow_change", "REAL"),
        ("energy_eia_enhanced", "yoy_change", "REAL"),
        ("energy_seasonal_norms", "series_id", "TEXT"),
        ("energy_seasonal_norms", "min_value", "REAL"),
        ("energy_seasonal_norms", "max_value", "REAL"),
        ("energy_seasonal_norms", "sample_count", "INTEGER"),
        ("energy_seasonal_norms", "last_updated", "TEXT"),
        ("economic_dashboard", "category", "TEXT"),
        ("economic_dashboard", "name", "TEXT"),
        ("economic_dashboard", "prev_value", "REAL"),
        ("economic_dashboard", "mom_change", "REAL"),
        ("economic_dashboard", "yoy_change", "REAL"),
        ("economic_dashboard", "zscore", "REAL"),
        ("economic_dashboard", "trend", "TEXT"),
        ("economic_dashboard", "signal", "TEXT"),
        ("economic_dashboard", "last_updated", "TEXT"),
        ("sector_rotation", "rs_ratio", "REAL"),
        ("sector_rotation", "rs_momentum", "REAL"),
        ("sector_rotation", "quadrant", "TEXT"),
        ("sector_rotation", "rotation_score", "REAL"),
        ("energy_jodi_data", "indicator", "TEXT"),
        ("energy_jodi_data", "unit", "TEXT"),
        ("energy_jodi_data", "mom_change", "REAL"),
        ("energy_jodi_data", "yoy_change", "REAL"),
        ("energy_jodi_data", "last_updated", "TEXT"),
        ("energy_trade_flows", "reporter", "TEXT"),
        ("energy_trade_flows", "partner", "TEXT"),
        ("energy_trade_flows", "commodity_code", "TEXT"),
        ("energy_trade_flows", "period", "TEXT"),
        ("energy_trade_flows", "trade_flow", "TEXT"),
        ("energy_trade_flows", "value_usd", "REAL"),
        ("energy_trade_flows", "quantity_kg", "REAL"),
        ("energy_trade_flows", "last_updated", "TEXT"),
        ("energy_supply_anomalies", "series_id", "TEXT"),
        ("energy_supply_anomalies", "description", "TEXT"),
        ("energy_supply_anomalies", "zscore", "REAL"),
        ("energy_supply_anomalies", "affected_tickers", "TEXT"),
        ("energy_supply_anomalies", "status", "TEXT DEFAULT 'active'"),
        ("energy_supply_anomalies", "detected_at", "TEXT"),
        # pattern_scan full schema migrations
        ("pattern_scan", "regime", "TEXT"),
        ("pattern_scan", "regime_score", "REAL"),
        ("pattern_scan", "vix_percentile", "REAL"),
        ("pattern_scan", "sector_quadrant", "TEXT"),
        ("pattern_scan", "rotation_score", "REAL"),
        ("pattern_scan", "rs_ratio", "REAL"),
        ("pattern_scan", "rs_momentum", "REAL"),
        ("pattern_scan", "patterns_detected", "TEXT"),
        ("pattern_scan", "pattern_score", "REAL"),
        ("pattern_scan", "sr_proximity", "TEXT"),
        ("pattern_scan", "volume_profile_score", "REAL"),
        ("pattern_scan", "hurst_exponent", "REAL"),
        ("pattern_scan", "mr_score", "REAL"),
        ("pattern_scan", "momentum_score", "REAL"),
        ("pattern_scan", "compression_score", "REAL"),
        ("pattern_scan", "squeeze_active", "INTEGER"),
        ("pattern_scan", "wyckoff_phase", "TEXT"),
        ("pattern_scan", "wyckoff_confidence", "REAL"),
        ("pattern_scan", "earnings_days_to_next", "INTEGER"),
        ("pattern_scan", "vol_regime", "TEXT"),
        ("pattern_scan", "pattern_scan_score", "REAL"),
        ("pattern_scan", "layer_scores", "TEXT"),
        # pattern_options_signals full schema migrations
        ("pattern_options_signals", "pattern_scan_score", "REAL"),
        ("pattern_options_signals", "options_score", "REAL"),
        ("pattern_options_signals", "pattern_options_score", "REAL"),
        ("pattern_options_signals", "top_pattern", "TEXT"),
        ("pattern_options_signals", "top_signal", "TEXT"),
        ("pattern_options_signals", "narrative", "TEXT"),
        ("pattern_options_signals", "status", "TEXT"),
        # energy_intel_signals full schema migrations
        ("energy_intel_signals", "energy_intel_score", "REAL"),
        ("energy_intel_signals", "inventory_signal", "REAL"),
        ("energy_intel_signals", "production_signal", "REAL"),
        ("energy_intel_signals", "demand_signal", "REAL"),
        ("energy_intel_signals", "trade_flow_signal", "REAL"),
        ("energy_intel_signals", "global_balance_signal", "REAL"),
        ("energy_intel_signals", "ticker_category", "TEXT"),
        ("energy_intel_signals", "narrative", "TEXT"),
        ("consensus_blindspot_signals", "cycle_score", "REAL"),
        ("consensus_blindspot_signals", "consensus_gap_score", "REAL"),
        ("consensus_blindspot_signals", "positioning_score", "REAL"),
        ("consensus_blindspot_signals", "positioning_flags", "TEXT"),
        ("consensus_blindspot_signals", "divergence_score", "REAL"),
        ("consensus_blindspot_signals", "divergence_type", "TEXT"),
        ("consensus_blindspot_signals", "divergence_magnitude", "REAL"),
        ("consensus_blindspot_signals", "fat_pitch_score", "REAL"),
        ("consensus_blindspot_signals", "fat_pitch_count", "INTEGER"),
        ("consensus_blindspot_signals", "fat_pitch_conditions", "TEXT"),
        ("consensus_blindspot_signals", "anti_pitch_count", "INTEGER"),
        ("consensus_blindspot_signals", "anti_pitch_conditions", "TEXT"),
        ("consensus_blindspot_signals", "analyst_buy_pct", "REAL"),
        ("consensus_blindspot_signals", "analyst_sell_pct", "REAL"),
        ("consensus_blindspot_signals", "analyst_target_upside", "REAL"),
        ("consensus_blindspot_signals", "short_interest_pct", "REAL"),
        ("consensus_blindspot_signals", "institutional_pct", "REAL"),
        ("consensus_blindspot_signals", "our_convergence_score", "REAL"),
        ("consensus_blindspot_signals", "narrative", "TEXT"),
        # ai_exec_investments full schema
        ("ai_exec_investments", "exec_name", "TEXT"),
        ("ai_exec_investments", "exec_org", "TEXT"),
        ("ai_exec_investments", "exec_prominence", "TEXT"),
        ("ai_exec_investments", "activity_type", "TEXT"),
        ("ai_exec_investments", "target_company", "TEXT"),
        ("ai_exec_investments", "target_sector", "TEXT"),
        ("ai_exec_investments", "target_ticker", "TEXT"),
        ("ai_exec_investments", "ipo_timeline", "TEXT"),
        ("ai_exec_investments", "date_reported", "TEXT"),
        ("ai_exec_investments", "confidence", "REAL"),
        ("ai_exec_investments", "summary", "TEXT"),
        ("ai_exec_investments", "source_url", "TEXT"),
        ("ai_exec_investments", "source", "TEXT"),
        ("ai_exec_investments", "raw_score", "REAL"),
        ("ai_exec_investments", "scan_date", "TEXT"),
        # ai_exec_signals full schema
        ("ai_exec_signals", "ai_exec_score", "REAL"),
        ("ai_exec_signals", "exec_count", "INTEGER"),
        ("ai_exec_signals", "top_exec", "TEXT"),
        ("ai_exec_signals", "narrative", "TEXT"),
        # convergence_signals full module score columns
        ("convergence_signals", "energy_intel_score", "REAL"),
        ("convergence_signals", "prediction_markets_score", "REAL"),
        ("convergence_signals", "pattern_options_score", "REAL"),
        ("convergence_signals", "estimate_momentum_score", "REAL"),
        ("convergence_signals", "ai_regulatory_score", "REAL"),
        ("convergence_signals", "consensus_blindspots_score", "REAL"),
        ("convergence_signals", "aar_rail_score", "REAL"),
        ("convergence_signals", "ship_tracking_score", "REAL"),
        ("convergence_signals", "patent_intel_score", "REAL"),
        ("convergence_signals", "ucc_filings_score", "REAL"),
        ("convergence_signals", "board_interlocks_score", "REAL"),
        ("signal_ic_results", "computed_date", "TEXT"),
        ("module_ic_summary", "computed_date", "TEXT"),
        ("intelligence_reports", "topic_type", "TEXT"),
        ("intelligence_reports", "expert_type", "TEXT"),
        ("intelligence_reports", "regime", "TEXT"),
        ("intelligence_reports", "symbols_covered", "TEXT"),
        ("intelligence_reports", "report_html", "TEXT"),
        ("intelligence_reports", "report_markdown", "TEXT"),
        # prediction_market_signals full schema migrations
        ("prediction_market_signals", "symbol", "TEXT"),
        ("prediction_market_signals", "net_impact", "REAL"),
        ("prediction_market_signals", "status", "TEXT"),
        ("prediction_market_signals", "narrative", "TEXT"),
        # prediction_market_raw full schema migrations
        ("prediction_market_raw", "impact_category", "TEXT"),
        ("prediction_market_raw", "yes_probability", "REAL"),
        ("prediction_market_raw", "liquidity", "REAL"),
        ("prediction_market_raw", "direction", "TEXT"),
        ("prediction_market_raw", "confidence", "REAL"),
        ("prediction_market_raw", "specific_symbols", "TEXT"),
        ("prediction_market_raw", "rationale", "TEXT"),
        ("prediction_market_raw", "end_date", "TEXT"),
        # options_intel full schema migrations
        ("options_intel", "atm_iv", "REAL"),
        ("options_intel", "hv_20d", "REAL"),
        ("options_intel", "iv_premium", "REAL"),
        ("options_intel", "iv_percentile", "REAL"),
        ("options_intel", "expected_move_pct", "REAL"),
        ("options_intel", "straddle_cost", "REAL"),
        ("options_intel", "volume_pc_ratio", "REAL"),
        ("options_intel", "oi_pc_ratio", "REAL"),
        ("options_intel", "pc_signal", "TEXT"),
        ("options_intel", "unusual_activity_count", "INTEGER"),
        ("options_intel", "unusual_activity", "TEXT"),
        ("options_intel", "unusual_direction_bias", "TEXT"),
        ("options_intel", "skew_25d", "REAL"),
        ("options_intel", "skew_direction", "TEXT"),
        ("options_intel", "term_structure_signal", "TEXT"),
        ("options_intel", "net_gex", "REAL"),
        ("options_intel", "gamma_flip_level", "REAL"),
        ("options_intel", "vanna_exposure", "REAL"),
        ("options_intel", "max_pain", "REAL"),
        ("options_intel", "put_wall", "REAL"),
        ("options_intel", "call_wall", "REAL"),
        ("options_intel", "dealer_regime", "TEXT"),
        ("options_intel", "options_score", "REAL"),
        ("economic_heat_index", "improving_count", "INTEGER"),
        ("economic_heat_index", "deteriorating_count", "INTEGER"),
        ("economic_heat_index", "stable_count", "INTEGER"),
        ("economic_heat_index", "leading_count", "INTEGER"),
        ("economic_heat_index", "detail", "TEXT"),
        # signals table: columns expected by signal_generator and frontend
        ("signals", "asset_class", "TEXT"),
        ("signals", "macro_score", "REAL"),
        ("signals", "entry_price", "REAL"),
        ("signals", "stop_loss", "REAL"),
        ("signals", "target_price", "REAL"),
        ("signals", "rr_ratio", "REAL"),
        ("signals", "position_size_shares", "REAL"),
        ("signals", "position_size_dollars", "REAL"),
        # technical_scores table: columns expected by frontend
        ("technical_scores", "breakout_score", "REAL"),
        ("technical_scores", "relative_strength_score", "REAL"),
        ("technical_scores", "breadth_score", "REAL"),
    ]
    for table, col, col_type in _migrate_columns:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    # Backfill sector/market_cap_bucket for existing rows
    try:
        cur.execute("""UPDATE signal_outcomes SET sector = (SELECT sector FROM stock_universe
            WHERE stock_universe.symbol = signal_outcomes.symbol) WHERE sector IS NULL OR sector = ''""")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("""UPDATE signal_outcomes SET market_cap_bucket = CASE
            WHEN (SELECT value FROM fundamentals WHERE fundamentals.symbol = signal_outcomes.symbol AND metric = 'marketCap') > 200000000000 THEN 'mega'
            WHEN (SELECT value FROM fundamentals WHERE fundamentals.symbol = signal_outcomes.symbol AND metric = 'marketCap') > 10000000000 THEN 'large'
            WHEN (SELECT value FROM fundamentals WHERE fundamentals.symbol = signal_outcomes.symbol AND metric = 'marketCap') > 2000000000 THEN 'mid'
            ELSE 'small' END WHERE market_cap_bucket IS NULL""")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def query(sql, params=None):
    """Execute SQL and return list of dicts."""
    conn = get_conn()
    try:
        cur = conn.execute(sql, params or [])
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_df(sql, params=None):
    """Execute SQL and return a pandas DataFrame."""
    import pandas as _pd
    conn = get_conn()
    try:
        return _pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def upsert_many(table, columns, rows):
    """INSERT OR REPLACE many rows into a table."""
    if not rows:
        return
    placeholders = ", ".join(["?"] * len(columns))
    col_str = ", ".join(columns)
    sql = f"INSERT OR REPLACE INTO {table} ({col_str}) VALUES ({placeholders})"
    conn = get_conn()
    try:
        conn.executemany(sql, rows)
        conn.commit()
    finally:
        conn.close()
