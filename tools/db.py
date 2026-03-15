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
CREATE TABLE IF NOT EXISTS sector_rotation (date TEXT, sector TEXT, score REAL, PRIMARY KEY (date, sector));
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
CREATE TABLE IF NOT EXISTS pattern_scan (symbol TEXT, date TEXT, pattern TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date, pattern));
CREATE TABLE IF NOT EXISTS pattern_options_signals (symbol TEXT, date TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date));
CREATE TABLE IF NOT EXISTS options_intel (symbol TEXT, date TEXT, put_call_ratio REAL, iv_rank REAL, unusual_volume INTEGER, score REAL, details TEXT, PRIMARY KEY (symbol, date));
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
CREATE TABLE IF NOT EXISTS economic_dashboard (indicator_id TEXT, date TEXT, value REAL, category TEXT, PRIMARY KEY (indicator_id, date));
CREATE TABLE IF NOT EXISTS economic_heat_index (date TEXT PRIMARY KEY, heat_index REAL, regime TEXT, details TEXT);
CREATE TABLE IF NOT EXISTS hl_price_snapshots (ticker TEXT, timestamp TEXT, mid_price REAL, deployer TEXT, PRIMARY KEY (ticker, timestamp, deployer));
CREATE TABLE IF NOT EXISTS hl_gap_signals (ticker TEXT, date TEXT, predicted_gap REAL, actual_gap REAL, signal_time TEXT, details TEXT, PRIMARY KEY (ticker, date));
CREATE TABLE IF NOT EXISTS hl_deployer_spreads (ticker TEXT, date TEXT, deployer_a TEXT, deployer_b TEXT, spread REAL, PRIMARY KEY (ticker, date, deployer_a, deployer_b));
CREATE TABLE IF NOT EXISTS prediction_market_signals (sector TEXT, date TEXT, pm_score REAL, market_count INTEGER, details TEXT, PRIMARY KEY (sector, date));
CREATE TABLE IF NOT EXISTS prediction_market_raw (market_id TEXT, date TEXT, question TEXT, probability REAL, volume REAL, category TEXT, relevance TEXT, PRIMARY KEY (market_id, date));
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
CREATE TABLE IF NOT EXISTS energy_intel_signals (symbol TEXT, date TEXT, score REAL, signal_type TEXT, details TEXT, PRIMARY KEY (symbol, date, signal_type));
CREATE TABLE IF NOT EXISTS energy_eia_enhanced (series_id TEXT, date TEXT, value REAL, category TEXT, description TEXT, wow_change REAL, yoy_change REAL, PRIMARY KEY (series_id, date));
CREATE TABLE IF NOT EXISTS energy_supply_anomalies (date TEXT, anomaly_type TEXT, severity REAL, details TEXT, PRIMARY KEY (date, anomaly_type));
CREATE TABLE IF NOT EXISTS energy_trade_flows (date TEXT, country TEXT, product TEXT, flow_type TEXT, value REAL, PRIMARY KEY (date, country, product, flow_type));
CREATE TABLE IF NOT EXISTS energy_seasonal_norms (week_of_year INTEGER, product TEXT, avg_value REAL, std_value REAL, PRIMARY KEY (week_of_year, product));
CREATE TABLE IF NOT EXISTS energy_jodi_data (country TEXT, product TEXT, date TEXT, value REAL, flow TEXT, PRIMARY KEY (country, product, date, flow));
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
