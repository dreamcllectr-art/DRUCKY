"""Database helpers for the Druckenmiller Alpha System.
PostgreSQL connection management, query helpers, and bulk upsert.
Connection: DATABASE_URL env var (postgresql://user:pass@host:5432/db).
"""
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://druck:druck@localhost:5432/druckenmiller")

_pool: pg_pool.ThreadedConnectionPool | None = None


def _get_pool() -> pg_pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = pg_pool.ThreadedConnectionPool(2, 30, _DATABASE_URL)
    return _pool


class _PgConnWrapper:
    """Thin wrapper adding SQLite-compat shims (executescript, execute) to psycopg2 conn."""

    def __init__(self, conn):
        self._conn = conn

    # --- SQLite compat ---
    def executescript(self, sql: str):
        """Run multiple semicolon-separated DDL statements (SQLite compat)."""
        with self._conn.cursor() as cur:
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        self._conn.commit()

    def execute(self, sql: str, params=None):
        """Single-statement execute returning a cursor-like object (SQLite compat)."""
        sql = _to_pg(sql)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params or [])
        return cur

    # --- psycopg2 passthrough ---
    def cursor(self, *args, **kwargs):
        return self._conn.cursor(*args, **kwargs)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_conn():
    """Return a psycopg2 connection (wrapped for SQLite API compat) from the thread pool."""
    return _PgConnWrapper(_get_pool().getconn())


def _release(conn):
    try:
        raw = conn._conn if isinstance(conn, _PgConnWrapper) else conn
        _get_pool().putconn(raw)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Column cache — avoids hitting information_schema on every upsert_many call.
# ---------------------------------------------------------------------------
_col_cache: dict[str, set[str]] = {}


def _pg_columns(table: str) -> set[str]:
    """Return the set of column names that exist in the Postgres table."""
    if table not in _col_cache:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT column_name FROM information_schema.columns
                       WHERE table_schema = 'public' AND table_name = %s""",
                    [table],
                )
                _col_cache[table] = {r[0] for r in cur.fetchall()}
        finally:
            _release(conn)
    return _col_cache[table]


def _invalidate_col_cache(table: str):
    """Call after ALTER TABLE to refresh the cache for that table."""
    _col_cache.pop(table, None)


# ---------------------------------------------------------------------------
# PRIMARY KEY MAP — used by upsert_many for ON CONFLICT resolution.
# Tables with SERIAL id (portfolio, intelligence_reports, etc.) are inserted
# directly via SQL by the pipeline, not via upsert_many, so they're omitted.
# ---------------------------------------------------------------------------
TABLE_PKS: dict[str, list[str]] = {
    "stock_universe":              ["symbol"],
    "price_data":                  ["symbol", "date"],
    "technical_scores":            ["symbol", "date"],
    "fundamental_scores":          ["symbol", "date"],
    "fundamentals":                ["symbol", "metric"],
    "signals":                     ["symbol", "date"],
    "macro_indicators":            ["indicator_id", "date"],
    "macro_scores":                ["date"],
    "market_breadth":              ["date"],
    "sector_rotation":             ["sector", "date"],
    "news_sentiment":              ["symbol", "date", "headline"],
    "watchlist":                   ["symbol"],
    "smart_money_scores":          ["symbol", "date"],
    "filings_13f":                 ["manager", "symbol", "date"],
    "worldview_signals":           ["date", "thesis"],
    "foreign_intel_signals":       ["symbol", "date", "source_country"],
    "foreign_intel_url_cache":     ["url"],
    "foreign_ticker_map":          ["foreign_symbol"],
    "research_signals":            ["symbol", "date", "source"],
    "research_url_cache":          ["url"],
    "news_displacement":           ["symbol", "date"],
    "reddit_signals":              ["symbol", "date", "subreddit"],
    "alt_data_scores":             ["symbol", "date", "source"],
    "alternative_data":            ["symbol", "date", "source", "metric"],
    "convergence_signals":         ["symbol", "date"],
    "signal_outcomes":             ["symbol", "signal_date"],
    "module_performance":          ["report_date", "module_name", "regime", "sector"],
    "weight_history":              ["date", "regime", "module_name"],
    "weight_optimizer_log":        ["date", "action"],
    "sector_expert_signals":       ["symbol", "date"],
    "pattern_scan":                ["symbol", "date"],
    "pattern_options_signals":     ["symbol", "date"],
    "options_intel":               ["symbol", "date"],
    "variant_analysis":            ["symbol", "date"],
    "devils_advocate":             ["symbol", "date"],
    "transcript_analysis":         ["symbol", "date"],
    "letter_analysis":             ["symbol", "date"],
    "forensic_alerts":             ["symbol", "date", "alert_type"],
    "earnings_calendar":           ["symbol", "date"],
    "pair_relationships":          ["symbol_a", "symbol_b"],
    "pair_spreads":                ["symbol_a", "symbol_b", "date"],
    "pair_signals":                ["symbol_a", "symbol_b", "date", "signal_type"],
    "ma_signals":                  ["symbol", "date"],
    "ma_rumors":                   ["symbol", "date", "source"],
    "insider_transactions":        ["symbol", "date", "insider_name", "transaction_type"],
    "insider_signals":             ["symbol", "date"],
    "economic_dashboard":          ["indicator_id", "date"],
    "economic_heat_index":         ["date"],
    "hl_price_snapshots":          ["ticker", "timestamp", "deployer"],
    "hl_gap_signals":              ["ticker", "date"],
    "hl_deployer_spreads":         ["ticker", "date", "deployer_a", "deployer_b"],
    "prediction_market_signals":   ["symbol", "date"],
    "prediction_market_raw":       ["market_id", "date"],
    "world_macro_indicators":      ["indicator", "country", "date"],
    "estimate_snapshots":          ["symbol", "date"],
    "estimate_momentum_signals":   ["symbol", "date"],
    "regulatory_signals":          ["symbol", "date"],
    "regulatory_events":           ["event_id", "date"],
    "consensus_blindspot_signals": ["symbol", "date"],
    "ai_exec_signals":             ["symbol", "date"],
    "ai_exec_investments":         ["symbol", "date", "investment_type"],
    "ai_exec_url_cache":           ["url"],
    "energy_intel_signals":        ["symbol", "date"],
    "energy_eia_enhanced":         ["series_id", "date"],
    "energy_trade_flows":          ["reporter", "partner", "commodity_code", "period", "trade_flow"],
    "energy_seasonal_norms":       ["series_id", "week_of_year"],
    "energy_jodi_data":            ["country", "indicator", "date"],
    "global_energy_benchmarks":    ["benchmark_id", "date"],
    "global_energy_curves":        ["curve_id", "date", "months_out"],
    "global_energy_spreads":       ["spread_id", "date"],
    "global_energy_carbon":        ["market_id", "date"],
    "global_energy_signals":       ["symbol", "date"],
    "signal_conflicts":            ["symbol", "date", "conflict_type"],
    "thesis_snapshots":            ["date", "thesis"],
    "thesis_alerts":               ["date", "thesis", "alert_type"],
    "earnings_transcripts":        ["symbol", "quarter"],
    "earnings_nlp_scores":         ["symbol", "date"],
    "gov_intel_raw":               ["symbol", "date", "source", "event_type"],
    "gov_intel_scores":            ["symbol", "date"],
    "labor_intel_raw":             ["symbol", "date", "source", "metric"],
    "labor_intel_scores":          ["symbol", "date"],
    "supply_chain_raw":            ["date", "source", "metric"],
    "supply_chain_scores":         ["symbol", "date"],
    "digital_exhaust_raw":         ["symbol", "date", "source", "metric"],
    "digital_exhaust_scores":      ["symbol", "date"],
    "pharma_intel_raw":            ["symbol", "date", "source", "metric"],
    "pharma_intel_scores":         ["symbol", "date"],
    "stress_test_results":         ["date", "scenario"],
    "concentration_risk":          ["date"],
    "cross_asset_opportunities":   ["symbol", "date"],
    "signal_ic_results":           ["module", "signal_date", "horizon_days", "regime"],
    "module_ic_summary":           ["module", "regime", "horizon_days"],
    "narrative_signals":           ["narrative_id", "date"],
    "narrative_asset_map":         ["narrative_id", "symbol", "date"],
    "stress_backtest_results":     ["crisis", "sector_etf"],
    "stress_calibration":          ["scenario", "sector"],
    "funnel_overrides":            ["symbol", "stage"],
    "asset_class_signals":         ["asset_class", "date"],
    "funnel_snapshot":             ["date", "run_id"],
    "gate_results":                ["symbol", "date"],
    "gate_overrides":              ["symbol", "gate"],
    "gate_run_history":            ["run_id"],
    "fmp_short_interest":          ["symbol", "date"],
    "fmp_analyst_data":            ["symbol", "date"],
    "fmp_dcf":                     ["symbol", "date"],
    "fmp_institutional":           ["symbol", "date"],
    "stocktwits_sentiment":        ["symbol", "date"],
    "coingecko_data":              ["asset", "date"],
    "edgar_insider_raw":           ["accession"],
    "edgar_filing_metadata":       ["accession"],
    "av_technical_indicators":     ["symbol", "date"],
    "finra_short_interest":        ["symbol", "date"],
    "nansen_signals":              ["asset", "date"],
    "etherscan_signals":           ["date"],
    "usda_commodity_data":         ["commodity", "date"],
}


def init_db():
    """Ensure all core tables exist (CREATE IF NOT EXISTS)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        statements = [
            """CREATE TABLE IF NOT EXISTS stock_universe (symbol TEXT PRIMARY KEY, name TEXT, sector TEXT, industry TEXT, market_cap REAL)""",
            """CREATE TABLE IF NOT EXISTS price_data (symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume BIGINT, adj_close REAL, asset_class TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS technical_scores (symbol TEXT, date TEXT, trend_score REAL, momentum_score REAL, volatility_score REAL, volume_score REAL, total_score REAL, breakout_score REAL, relative_strength_score REAL, breadth_score REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS fundamental_scores (symbol TEXT, date TEXT, value_score REAL, quality_score REAL, growth_score REAL, total_score REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS fundamentals (symbol TEXT NOT NULL, metric TEXT NOT NULL, value REAL, updated_at TEXT DEFAULT NOW(), PRIMARY KEY (symbol, metric))""",
            """CREATE TABLE IF NOT EXISTS signals (symbol TEXT, date TEXT, composite_score REAL, signal TEXT, sector TEXT, technical_score REAL, fundamental_score REAL, asset_class TEXT, macro_score REAL, entry_price REAL, stop_loss REAL, target_price REAL, rr_ratio REAL, position_size_shares REAL, position_size_dollars REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS macro_indicators (indicator_id TEXT, date TEXT, value REAL, PRIMARY KEY (indicator_id, date))""",
            """CREATE TABLE IF NOT EXISTS macro_scores (date TEXT PRIMARY KEY, regime TEXT, regime_score REAL, details TEXT)""",
            """CREATE TABLE IF NOT EXISTS market_breadth (date TEXT PRIMARY KEY, advancers INTEGER, decliners INTEGER, new_highs INTEGER, new_lows INTEGER, adv_dec_ratio REAL, breadth_score REAL, sector_rotation TEXT)""",
            """CREATE TABLE IF NOT EXISTS sector_rotation (sector TEXT, date TEXT, rs_ratio REAL, rs_momentum REAL, quadrant TEXT, rotation_score REAL, score REAL, PRIMARY KEY (sector, date))""",
            """CREATE TABLE IF NOT EXISTS news_sentiment (symbol TEXT, date TEXT, headline TEXT, source TEXT, sentiment REAL, relevance REAL, PRIMARY KEY (symbol, date, headline))""",
            """CREATE TABLE IF NOT EXISTS watchlist (symbol TEXT PRIMARY KEY, notes TEXT, alert_price_above REAL, alert_price_below REAL, alert_tech_above REAL)""",
            """CREATE TABLE IF NOT EXISTS portfolio (id SERIAL PRIMARY KEY, symbol TEXT, shares REAL, entry_price REAL, entry_date TEXT, stop_loss REAL, target REAL, target_price REAL, notes TEXT, asset_class TEXT DEFAULT 'equity', status TEXT DEFAULT 'open', exit_price REAL, exit_date TEXT, entry_thesis TEXT, entry_convergence_snapshot TEXT)""",
            """CREATE TABLE IF NOT EXISTS smart_money_scores (symbol TEXT, date TEXT, manager_count INTEGER, conviction_score REAL, top_holders TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS filings_13f (manager TEXT, symbol TEXT, date TEXT, shares REAL, value REAL, change_pct REAL, PRIMARY KEY (manager, symbol, date))""",
            """CREATE TABLE IF NOT EXISTS worldview_signals (date TEXT, thesis TEXT, direction TEXT, confidence REAL, affected_sectors TEXT, details TEXT, PRIMARY KEY (date, thesis))""",
            """CREATE TABLE IF NOT EXISTS foreign_intel_signals (symbol TEXT, date TEXT, source_country TEXT, signal_type TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date, source_country))""",
            """CREATE TABLE IF NOT EXISTS foreign_intel_url_cache (url TEXT PRIMARY KEY, fetched_date TEXT, content TEXT)""",
            """CREATE TABLE IF NOT EXISTS foreign_ticker_map (foreign_symbol TEXT PRIMARY KEY, us_symbol TEXT, exchange TEXT, country TEXT)""",
            """CREATE TABLE IF NOT EXISTS research_signals (symbol TEXT, date TEXT, source TEXT, signal_type TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date, source))""",
            """CREATE TABLE IF NOT EXISTS research_url_cache (url TEXT PRIMARY KEY, fetched_date TEXT, content TEXT)""",
            """CREATE TABLE IF NOT EXISTS news_displacement (symbol TEXT, date TEXT, displacement_score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS reddit_signals (symbol TEXT, date TEXT, subreddit TEXT, mention_count INTEGER, sentiment REAL, score REAL, PRIMARY KEY (symbol, date, subreddit))""",
            """CREATE TABLE IF NOT EXISTS alt_data_scores (symbol TEXT, date TEXT, source TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date, source))""",
            """CREATE TABLE IF NOT EXISTS alternative_data (symbol TEXT, date TEXT, source TEXT, metric TEXT, value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric))""",
            """CREATE TABLE IF NOT EXISTS convergence_signals (symbol TEXT NOT NULL, date TEXT NOT NULL, convergence_score REAL NOT NULL, module_count INTEGER, conviction_level TEXT, forensic_blocked INTEGER DEFAULT 0, main_signal_score REAL, smartmoney_score REAL, worldview_score REAL, variant_score REAL, research_score REAL, reddit_score REAL, active_modules TEXT, narrative TEXT, news_displacement_score REAL, alt_data_score REAL, sector_expert_score REAL, foreign_intel_score REAL, pairs_score REAL, ma_score REAL, energy_intel_score REAL, prediction_markets_score REAL, pattern_options_score REAL, estimate_momentum_score REAL, ai_regulatory_score REAL, consensus_blindspots_score REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS signal_outcomes (symbol TEXT NOT NULL, signal_date TEXT NOT NULL, conviction_level TEXT, convergence_score REAL, module_count INTEGER, active_modules TEXT, regime_at_signal TEXT, sector TEXT, market_cap_bucket TEXT, entry_price REAL, price_1d REAL, return_1d REAL, price_5d REAL, return_5d REAL, price_10d REAL, return_10d REAL, price_20d REAL, return_20d REAL, price_30d REAL, return_30d REAL, price_60d REAL, return_60d REAL, price_90d REAL, return_90d REAL, hit_target INTEGER, hit_stop INTEGER, da_risk_score REAL, da_warning INTEGER DEFAULT 0, PRIMARY KEY (symbol, signal_date))""",
            """CREATE TABLE IF NOT EXISTS module_performance (report_date TEXT NOT NULL, module_name TEXT NOT NULL, regime TEXT DEFAULT 'all', sector TEXT DEFAULT 'all', total_signals INTEGER, win_count INTEGER, win_rate REAL, avg_return_1d REAL, avg_return_5d REAL, avg_return_10d REAL, avg_return_20d REAL, avg_return_30d REAL, avg_return_60d REAL, avg_return_90d REAL, sharpe_ratio REAL, max_drawdown REAL, observation_count INTEGER, confidence_interval_low REAL, confidence_interval_high REAL, PRIMARY KEY (report_date, module_name, regime, sector))""",
            """CREATE TABLE IF NOT EXISTS weight_history (date TEXT NOT NULL, regime TEXT NOT NULL, module_name TEXT NOT NULL, weight REAL NOT NULL, prior_weight REAL, reason TEXT, PRIMARY KEY (date, regime, module_name))""",
            """CREATE TABLE IF NOT EXISTS weight_optimizer_log (date TEXT NOT NULL, action TEXT NOT NULL, details TEXT, PRIMARY KEY (date, action))""",
            """CREATE TABLE IF NOT EXISTS sector_expert_signals (symbol TEXT, date TEXT, sector TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS pattern_scan (symbol TEXT, date TEXT, regime TEXT, regime_score REAL, vix_percentile REAL, sector_quadrant TEXT, rotation_score REAL, rs_ratio REAL, rs_momentum REAL, patterns_detected TEXT, pattern_score REAL, sr_proximity TEXT, volume_profile_score REAL, hurst_exponent REAL, mr_score REAL, momentum_score REAL, compression_score REAL, squeeze_active INTEGER, wyckoff_phase TEXT, wyckoff_confidence REAL, earnings_days_to_next INTEGER, vol_regime TEXT, pattern_scan_score REAL, layer_scores TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS pattern_options_signals (symbol TEXT, date TEXT, pattern_scan_score REAL, options_score REAL, pattern_options_score REAL, top_pattern TEXT, top_signal TEXT, narrative TEXT, status TEXT, score REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS options_intel (symbol TEXT, date TEXT, atm_iv REAL, hv_20d REAL, iv_premium REAL, iv_rank REAL, iv_percentile REAL, expected_move_pct REAL, straddle_cost REAL, volume_pc_ratio REAL, oi_pc_ratio REAL, pc_signal TEXT, unusual_activity_count INTEGER, unusual_activity TEXT, unusual_direction_bias TEXT, skew_25d REAL, skew_direction TEXT, term_structure_signal TEXT, net_gex REAL, gamma_flip_level REAL, vanna_exposure REAL, max_pain REAL, put_wall REAL, call_wall REAL, dealer_regime TEXT, options_score REAL, put_call_ratio REAL, unusual_volume INTEGER, score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS variant_analysis (symbol TEXT, date TEXT, variant_score REAL, thesis TEXT, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS devils_advocate (symbol TEXT, date TEXT, bear_thesis TEXT, kill_scenario TEXT, historical_analog TEXT, risk_score REAL, bull_context TEXT, regime_at_signal TEXT, warning_flag INTEGER, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS transcript_analysis (symbol TEXT, date TEXT, quarter TEXT, score REAL, summary TEXT, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS letter_analysis (symbol TEXT, date TEXT, score REAL, summary TEXT, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS forensic_alerts (symbol TEXT, date TEXT, alert_type TEXT, severity TEXT, details TEXT, PRIMARY KEY (symbol, date, alert_type))""",
            """CREATE TABLE IF NOT EXISTS earnings_calendar (symbol TEXT, date TEXT, estimate REAL, actual REAL, surprise REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS pair_relationships (symbol_a TEXT, symbol_b TEXT, sector TEXT, coint_pvalue REAL, hedge_ratio REAL, half_life REAL, correlation REAL, updated_date TEXT, PRIMARY KEY (symbol_a, symbol_b))""",
            """CREATE TABLE IF NOT EXISTS pair_spreads (symbol_a TEXT, symbol_b TEXT, date TEXT, spread REAL, z_score REAL, PRIMARY KEY (symbol_a, symbol_b, date))""",
            """CREATE TABLE IF NOT EXISTS pair_signals (symbol_a TEXT, symbol_b TEXT, date TEXT, signal_type TEXT, z_score REAL, direction TEXT, details TEXT, PRIMARY KEY (symbol_a, symbol_b, date, signal_type))""",
            """CREATE TABLE IF NOT EXISTS ma_signals (symbol TEXT, date TEXT, ma_score REAL, target_score REAL, rumor_score REAL, deal_stage TEXT, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS ma_rumors (symbol TEXT, date TEXT, source TEXT, headline TEXT, credibility REAL, deal_stage TEXT, details TEXT, PRIMARY KEY (symbol, date, source))""",
            """CREATE TABLE IF NOT EXISTS insider_transactions (symbol TEXT, date TEXT, insider_name TEXT, title TEXT, transaction_type TEXT, shares REAL, value REAL, PRIMARY KEY (symbol, date, insider_name, transaction_type))""",
            """CREATE TABLE IF NOT EXISTS insider_signals (symbol TEXT, date TEXT, insider_score REAL, cluster_buy INTEGER, large_csuite INTEGER, unusual_volume INTEGER, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS economic_dashboard (indicator_id TEXT, date TEXT, category TEXT, name TEXT, value REAL, prev_value REAL, mom_change REAL, yoy_change REAL, zscore REAL, trend TEXT, signal TEXT, last_updated TEXT, PRIMARY KEY (indicator_id, date))""",
            """CREATE TABLE IF NOT EXISTS economic_heat_index (date TEXT PRIMARY KEY, heat_index REAL, improving_count INTEGER, deteriorating_count INTEGER, stable_count INTEGER, leading_count INTEGER, detail TEXT)""",
            """CREATE TABLE IF NOT EXISTS hl_price_snapshots (ticker TEXT, timestamp TEXT, mid_price REAL, deployer TEXT, PRIMARY KEY (ticker, timestamp, deployer))""",
            """CREATE TABLE IF NOT EXISTS hl_gap_signals (ticker TEXT, date TEXT, predicted_gap REAL, actual_gap REAL, signal_time TEXT, details TEXT, PRIMARY KEY (ticker, date))""",
            """CREATE TABLE IF NOT EXISTS hl_deployer_spreads (ticker TEXT, date TEXT, deployer_a TEXT, deployer_b TEXT, spread REAL, PRIMARY KEY (ticker, date, deployer_a, deployer_b))""",
            """CREATE TABLE IF NOT EXISTS prediction_market_signals (symbol TEXT, date TEXT, pm_score REAL, market_count INTEGER, net_impact REAL, status TEXT, narrative TEXT, sector TEXT, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS prediction_market_raw (market_id TEXT, date TEXT, question TEXT, impact_category TEXT, yes_probability REAL, volume REAL, liquidity REAL, direction TEXT, confidence REAL, specific_symbols TEXT, rationale TEXT, end_date TEXT, probability REAL, category TEXT, relevance TEXT, PRIMARY KEY (market_id, date))""",
            """CREATE TABLE IF NOT EXISTS world_macro_indicators (indicator TEXT, country TEXT, date TEXT, value REAL, source TEXT, PRIMARY KEY (indicator, country, date))""",
            """CREATE TABLE IF NOT EXISTS estimate_snapshots (symbol TEXT, date TEXT, eps_current REAL, eps_next REAL, rev_current REAL, rev_next REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS estimate_momentum_signals (symbol TEXT, date TEXT, em_score REAL, revision_velocity REAL, surprise_momentum REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS regulatory_signals (symbol TEXT, date TEXT, reg_score REAL, event_count INTEGER, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS regulatory_events (event_id TEXT, date TEXT, title TEXT, source TEXT, severity REAL, category TEXT, direction TEXT, jurisdiction TEXT, affected_symbols TEXT, details TEXT, PRIMARY KEY (event_id, date))""",
            """CREATE TABLE IF NOT EXISTS consensus_blindspot_signals (symbol TEXT, date TEXT, cbs_score REAL, gap_type TEXT, cycle_position REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS intelligence_reports (id SERIAL PRIMARY KEY, date TEXT, topic TEXT, report_type TEXT, content TEXT, metadata TEXT, topic_type TEXT, expert_type TEXT, regime TEXT, symbols_covered TEXT, report_html TEXT, report_markdown TEXT)""",
            """CREATE TABLE IF NOT EXISTS thematic_ideas (id SERIAL PRIMARY KEY, date TEXT, theme TEXT, symbols TEXT, score REAL, details TEXT)""",
            """CREATE TABLE IF NOT EXISTS ai_exec_signals (symbol TEXT, date TEXT, score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS ai_exec_investments (symbol TEXT, date TEXT, company TEXT, investment_type TEXT, amount REAL, details TEXT, PRIMARY KEY (symbol, date, investment_type))""",
            """CREATE TABLE IF NOT EXISTS ai_exec_url_cache (url TEXT PRIMARY KEY, fetched_date TEXT, content TEXT)""",
            """CREATE TABLE IF NOT EXISTS energy_intel_signals (symbol TEXT, date TEXT, energy_intel_score REAL, inventory_signal REAL, production_signal REAL, demand_signal REAL, trade_flow_signal REAL, global_balance_signal REAL, ticker_category TEXT, narrative TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS energy_eia_enhanced (series_id TEXT, date TEXT, value REAL, category TEXT, description TEXT, wow_change REAL, yoy_change REAL, PRIMARY KEY (series_id, date))""",
            """CREATE TABLE IF NOT EXISTS energy_supply_anomalies (id SERIAL PRIMARY KEY, date TEXT, anomaly_type TEXT, series_id TEXT, description TEXT, zscore REAL, severity REAL, affected_tickers TEXT, details TEXT, status TEXT DEFAULT 'active', detected_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS energy_trade_flows (reporter TEXT, partner TEXT, commodity_code TEXT, period TEXT, trade_flow TEXT, value_usd REAL, quantity_kg REAL, last_updated TEXT, date TEXT, country TEXT, product TEXT, flow_type TEXT, value REAL, PRIMARY KEY (reporter, partner, commodity_code, period, trade_flow))""",
            """CREATE TABLE IF NOT EXISTS energy_seasonal_norms (series_id TEXT, week_of_year INTEGER, avg_value REAL, std_value REAL, min_value REAL, max_value REAL, sample_count INTEGER, last_updated TEXT, PRIMARY KEY (series_id, week_of_year))""",
            """CREATE TABLE IF NOT EXISTS energy_jodi_data (country TEXT, indicator TEXT, date TEXT, value REAL, unit TEXT, mom_change REAL, yoy_change REAL, last_updated TEXT, flow TEXT, product TEXT, PRIMARY KEY (country, indicator, date))""",
            """CREATE TABLE IF NOT EXISTS global_energy_benchmarks (benchmark_id TEXT, date TEXT, name TEXT, unit TEXT, region TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, last_updated TEXT, PRIMARY KEY (benchmark_id, date))""",
            """CREATE TABLE IF NOT EXISTS global_energy_curves (curve_id TEXT, date TEXT, months_out INTEGER, contract_ticker TEXT, price REAL, last_updated TEXT, PRIMARY KEY (curve_id, date, months_out))""",
            """CREATE TABLE IF NOT EXISTS global_energy_spreads (spread_id TEXT, date TEXT, name TEXT, value REAL, leg_a REAL, leg_b REAL, assessment TEXT, unit TEXT, last_updated TEXT, PRIMARY KEY (spread_id, date))""",
            """CREATE TABLE IF NOT EXISTS global_energy_carbon (market_id TEXT, date TEXT, source_ticker TEXT, price REAL, unit TEXT, last_updated TEXT, PRIMARY KEY (market_id, date))""",
            """CREATE TABLE IF NOT EXISTS global_energy_signals (symbol TEXT, date TEXT, gem_score REAL, category TEXT, term_structure_signal REAL, basis_signal REAL, crack_signal REAL, carbon_signal REAL, narrative TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS signal_conflicts (symbol TEXT, date TEXT, conflict_type TEXT, severity TEXT, description TEXT, module_a TEXT, module_a_score REAL, module_b TEXT, module_b_score REAL, score_gap REAL, PRIMARY KEY (symbol, date, conflict_type))""",
            """CREATE TABLE IF NOT EXISTS thesis_snapshots (date TEXT, thesis TEXT, direction TEXT, confidence REAL, affected_sectors TEXT, PRIMARY KEY (date, thesis))""",
            """CREATE TABLE IF NOT EXISTS thesis_alerts (date TEXT, thesis TEXT, alert_type TEXT, severity TEXT, description TEXT, affected_symbols TEXT, lookback_days INTEGER, old_state TEXT, new_state TEXT, PRIMARY KEY (date, thesis, alert_type))""",
            """CREATE TABLE IF NOT EXISTS earnings_transcripts (symbol TEXT NOT NULL, date TEXT NOT NULL, quarter TEXT, filing_url TEXT, word_count INTEGER, sentiment REAL, hedging_ratio REAL, confidence_ratio REAL, key_phrases TEXT, PRIMARY KEY (symbol, quarter))""",
            """CREATE TABLE IF NOT EXISTS earnings_nlp_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, earnings_nlp_score REAL, sentiment_delta REAL, hedging_delta REAL, guidance_score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS gov_intel_raw (symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL, event_type TEXT NOT NULL, severity REAL, details TEXT, PRIMARY KEY (symbol, date, source, event_type))""",
            """CREATE TABLE IF NOT EXISTS gov_intel_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, gov_intel_score REAL, warn_score REAL, osha_score REAL, epa_score REAL, fcc_score REAL, lobbying_score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS labor_intel_raw (symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric))""",
            """CREATE TABLE IF NOT EXISTS labor_intel_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, labor_intel_score REAL, h1b_score REAL, hiring_score REAL, morale_score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS supply_chain_raw (date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value REAL, sector TEXT, details TEXT, PRIMARY KEY (date, source, metric))""",
            """CREATE TABLE IF NOT EXISTS supply_chain_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, supply_chain_score REAL, rail_score REAL, shipping_score REAL, trucking_score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS digital_exhaust_raw (symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value REAL, prior_value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric))""",
            """CREATE TABLE IF NOT EXISTS digital_exhaust_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, digital_exhaust_score REAL, app_score REAL, github_score REAL, pricing_score REAL, domain_score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS pharma_intel_raw (symbol TEXT NOT NULL, date TEXT NOT NULL, source TEXT NOT NULL, metric TEXT NOT NULL, value REAL, details TEXT, PRIMARY KEY (symbol, date, source, metric))""",
            """CREATE TABLE IF NOT EXISTS pharma_intel_scores (symbol TEXT NOT NULL, date TEXT NOT NULL, pharma_intel_score REAL, trial_velocity_score REAL, stage_shift_score REAL, cms_score REAL, rx_score REAL, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS stress_test_results (date TEXT, scenario TEXT, scenario_name TEXT, portfolio_impact_pct REAL, position_count INTEGER, position_details TEXT, worst_hit TEXT, best_positioned TEXT, PRIMARY KEY (date, scenario))""",
            """CREATE TABLE IF NOT EXISTS concentration_risk (date TEXT PRIMARY KEY, hhi REAL, concentration_level TEXT, top_sector TEXT, top_sector_pct REAL, details TEXT)""",
            """CREATE TABLE IF NOT EXISTS cross_asset_opportunities (symbol TEXT, date TEXT, asset_class TEXT, sector TEXT, opportunity_score REAL, technical_score REAL, fundamental_score REAL, momentum_5d REAL, momentum_20d REAL, momentum_60d REAL, regime_fit_score REAL, relative_value_rank REAL, is_fat_pitch INTEGER DEFAULT 0, fat_pitch_reason TEXT, conviction TEXT, details TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS signal_ic_results (module TEXT, signal_date TEXT, horizon_days INTEGER, ic_value REAL, pvalue REAL, n_stocks INTEGER, regime TEXT, PRIMARY KEY (module, signal_date, horizon_days, regime))""",
            """CREATE TABLE IF NOT EXISTS module_ic_summary (module TEXT, regime TEXT, horizon_days INTEGER, mean_ic REAL, std_ic REAL, information_ratio REAL, ic_positive_pct REAL, n_dates INTEGER, avg_n_stocks REAL, ci_low REAL, ci_high REAL, is_significant INTEGER, pvalue REAL, PRIMARY KEY (module, regime, horizon_days))""",
            """CREATE TABLE IF NOT EXISTS narrative_signals (narrative_id TEXT, date TEXT, narrative_name TEXT, strength_score REAL, crowding_score REAL, opportunity_score REAL, maturity TEXT, best_expression TEXT, avoid TEXT, macro_confirmations INTEGER, asset_confirmations INTEGER, details TEXT, PRIMARY KEY (narrative_id, date))""",
            """CREATE TABLE IF NOT EXISTS narrative_asset_map (narrative_id TEXT, symbol TEXT, date TEXT, asset_class TEXT, role TEXT, quality_score REAL, timing_score REAL, crowding_score REAL, combined_score REAL, PRIMARY KEY (narrative_id, symbol, date))""",
            """CREATE TABLE IF NOT EXISTS stress_backtest_results (crisis TEXT, sector_etf TEXT, sector TEXT, peak_date TEXT, trough_date TEXT, peak_price REAL, trough_price REAL, actual_drawdown REAL, assumed_drawdown REAL, calibration_error REAL, PRIMARY KEY (crisis, sector_etf))""",
            """CREATE TABLE IF NOT EXISTS stress_calibration (scenario TEXT, sector TEXT, assumed_impact REAL, calibrated_impact REAL, source_crisis TEXT, calibration_date TEXT, PRIMARY KEY (scenario, sector))""",
            """CREATE TABLE IF NOT EXISTS funnel_overrides (symbol TEXT, stage TEXT, action TEXT, reason TEXT, created_at TEXT DEFAULT NOW(), updated_at TEXT DEFAULT NOW(), expires_at TEXT, PRIMARY KEY (symbol, stage))""",
            """CREATE TABLE IF NOT EXISTS journal_entries (id SERIAL PRIMARY KEY, portfolio_id INTEGER, symbol TEXT NOT NULL, entry_type TEXT, content TEXT, convergence_snapshot TEXT, created_at TEXT DEFAULT NOW())""",
            """CREATE TABLE IF NOT EXISTS asset_class_signals (asset_class TEXT, date TEXT, proxy_symbol TEXT, regime_signal TEXT, score REAL, rationale TEXT, details TEXT, PRIMARY KEY (asset_class, date))""",
            """CREATE TABLE IF NOT EXISTS funnel_snapshot (date TEXT, run_id TEXT DEFAULT NOW(), universe_count INTEGER, sector_passed INTEGER, sector_flagged INTEGER, technical_passed INTEGER, technical_flagged INTEGER, conviction_high INTEGER, conviction_notable INTEGER, conviction_watch INTEGER, actionable_count INTEGER, PRIMARY KEY (date, run_id))""",
            """CREATE TABLE IF NOT EXISTS gate_results (symbol TEXT, date TEXT, gate_0 INTEGER DEFAULT 1, gate_1 INTEGER, gate_2 INTEGER, gate_3 INTEGER, gate_4 INTEGER, gate_5 INTEGER, gate_6 INTEGER, gate_7 INTEGER, gate_8 INTEGER, gate_9 INTEGER, gate_10 INTEGER, last_gate_passed INTEGER, fail_reason TEXT, asset_class TEXT, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS gate_overrides (symbol TEXT, gate INTEGER, direction TEXT, reason TEXT, expires TEXT, created_at TEXT DEFAULT NOW(), PRIMARY KEY (symbol, gate))""",
            """CREATE TABLE IF NOT EXISTS gate_run_history (run_id TEXT PRIMARY KEY, date TEXT, total_assets INTEGER, gate_1_passed INTEGER, gate_2_passed INTEGER, gate_3_passed INTEGER, gate_4_passed INTEGER, gate_5_passed INTEGER, gate_6_passed INTEGER, gate_7_passed INTEGER, gate_8_passed INTEGER, gate_9_passed INTEGER, gate_10_passed INTEGER, run_time_seconds REAL)""",
            """CREATE TABLE IF NOT EXISTS fmp_short_interest (symbol TEXT, date TEXT, short_interest REAL, short_float_pct REAL, days_to_cover REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS fmp_analyst_data (symbol TEXT, date TEXT, analyst_count INTEGER, strong_buy INTEGER, buy INTEGER, hold INTEGER, sell INTEGER, strong_sell INTEGER, consensus TEXT, price_target REAL, price_target_high REAL, price_target_low REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS fmp_dcf (symbol TEXT, date TEXT, dcf_value REAL, stock_price REAL, upside_pct REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS fmp_institutional (symbol TEXT, date TEXT, institutional_pct REAL, institution_count INTEGER, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS stocktwits_sentiment (symbol TEXT, date TEXT, bull_pct REAL, bear_pct REAL, msg_count INTEGER, sentiment_score REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS coingecko_data (asset TEXT, date TEXT, price REAL, volume REAL, market_cap REAL, dominance_pct REAL, fear_greed_idx REAL, price_change_24h REAL, price_change_7d REAL, PRIMARY KEY (asset, date))""",
            """CREATE TABLE IF NOT EXISTS edgar_insider_raw (accession TEXT PRIMARY KEY, symbol TEXT, date TEXT, filer_name TEXT, title TEXT, transaction_type TEXT, shares REAL, price REAL, value REAL, form_type TEXT, filing_url TEXT)""",
            """CREATE TABLE IF NOT EXISTS edgar_filing_metadata (accession TEXT PRIMARY KEY, symbol TEXT, date TEXT, form_type TEXT, filer_name TEXT, filing_url TEXT, description TEXT)""",
            """CREATE TABLE IF NOT EXISTS av_technical_indicators (symbol TEXT, date TEXT, rsi REAL, macd REAL, macd_signal REAL, macd_hist REAL, stoch_k REAL, stoch_d REAL, adx REAL, bb_upper REAL, bb_middle REAL, bb_lower REAL, bb_width REAL, obv REAL, PRIMARY KEY (symbol, date))""",
            """CREATE TABLE IF NOT EXISTS finra_short_interest (symbol TEXT, date TEXT, short_volume REAL, total_volume REAL, short_vol_ratio REAL, short_interest REAL, days_to_cover REAL, PRIMARY KEY (symbol, date))""",
        ]

        # Add columns for future migrations (IF NOT EXISTS is safe to re-run)
        alter_statements = [
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS asset_class TEXT",
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS macro_score REAL",
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS entry_price REAL",
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS stop_loss REAL",
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS target_price REAL",
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS rr_ratio REAL",
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS position_size_shares REAL",
            "ALTER TABLE signals ADD COLUMN IF NOT EXISTS position_size_dollars REAL",
            "ALTER TABLE technical_scores ADD COLUMN IF NOT EXISTS breakout_score REAL",
            "ALTER TABLE technical_scores ADD COLUMN IF NOT EXISTS relative_strength_score REAL",
            "ALTER TABLE technical_scores ADD COLUMN IF NOT EXISTS breadth_score REAL",
            "ALTER TABLE portfolio ADD COLUMN IF NOT EXISTS entry_thesis TEXT",
            "ALTER TABLE portfolio ADD COLUMN IF NOT EXISTS entry_convergence_snapshot TEXT",
            "ALTER TABLE portfolio ADD COLUMN IF NOT EXISTS exit_price REAL",
            "ALTER TABLE portfolio ADD COLUMN IF NOT EXISTS exit_date TEXT",
            "ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS topic_type TEXT",
            "ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS expert_type TEXT",
            "ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS regime TEXT",
            "ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS symbols_covered TEXT",
            "ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS report_html TEXT",
            "ALTER TABLE intelligence_reports ADD COLUMN IF NOT EXISTS report_markdown TEXT",
        ]

        for stmt in statements:
            cur.execute(stmt)
        for stmt in alter_statements:
            cur.execute(stmt)

        conn.commit()
    finally:
        cur.close()
        _release(conn)


import re as _re


def _to_pg(sql):
    """Convert SQLite SQL to Postgres-compatible SQL."""
    # Parameter placeholders
    sql = sql.replace("?", "%s")
    # AUTOINCREMENT → SERIAL (DDL)
    sql = _re.sub(r'INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT', 'SERIAL PRIMARY KEY', sql, flags=_re.IGNORECASE)
    sql = sql.replace("AUTOINCREMENT", "")
    # INSERT OR REPLACE / INSERT OR IGNORE → INSERT ... ON CONFLICT
    sql = _re.sub(r'INSERT\s+OR\s+REPLACE\s+INTO', 'INSERT INTO', sql, flags=_re.IGNORECASE)
    sql = _re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', sql, flags=_re.IGNORECASE)
    # SQLite date arithmetic: date('now', '-N days') → CURRENT_DATE - N
    def _date_fn(m):
        arg = m.group(1).strip().strip("'\"")
        if arg.startswith('-') or arg.startswith('+'):
            try:
                n = int(arg.split()[0])
                unit = arg.split()[1].rstrip('s') if len(arg.split()) > 1 else 'day'
                if n < 0:
                    return f"(CURRENT_DATE - INTERVAL '{-n} {unit}s')"
                else:
                    return f"(CURRENT_DATE + INTERVAL '{n} {unit}s')"
            except Exception:
                pass
        return 'CURRENT_DATE'
    sql = _re.sub(r"date\s*\(\s*'now'\s*,\s*([^)]+)\)", _date_fn, sql, flags=_re.IGNORECASE)
    sql = _re.sub(r"date\s*\(\s*'now'\s*\)", 'CURRENT_DATE', sql, flags=_re.IGNORECASE)
    sql = _re.sub(r"datetime\s*\(\s*'now'\s*\)", 'NOW()', sql, flags=_re.IGNORECASE)
    return sql


def query(sql, params=None):
    """Execute SQL and return list of dicts. Accepts both ? and %s placeholders."""
    conn = get_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_to_pg(sql), params or [])
            return [dict(r) for r in cur.fetchall()]
    finally:
        _release(conn)


def query_df(sql, params=None):
    """Execute SQL and return a pandas DataFrame. Accepts both ? and %s placeholders."""
    import pandas as _pd
    from sqlalchemy import create_engine, text
    engine = create_engine(_DATABASE_URL)
    with engine.connect() as conn:
        return _pd.read_sql_query(text(_to_pg(sql)), conn, params=params)


def upsert_many(table, columns, rows):
    """INSERT ... ON CONFLICT (pk_cols) DO UPDATE SET ... for many rows.

    Automatically filters to columns that exist in the Postgres table, adding
    new columns on-the-fly with ALTER TABLE when the pipeline introduces them.
    """
    if not rows:
        return
    pk_cols = TABLE_PKS.get(table)
    if not pk_cols:
        raise ValueError(f"upsert_many: no PK defined for table '{table}'. Add to TABLE_PKS.")

    existing = _pg_columns(table)
    # Add any new columns the pipeline is trying to write (schema evolution)
    new_cols = [c for c in columns if c not in existing]
    if new_cols:
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                for col in new_cols:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} TEXT")
            conn.commit()
        finally:
            _release(conn)
        _invalidate_col_cache(table)
        existing = _pg_columns(table)

    # Only write columns that exist in Postgres
    filtered = [c for c in columns if c in existing]
    if not filtered:
        return
    col_indices = [columns.index(c) for c in filtered]

    col_str = ", ".join(filtered)
    placeholders = ", ".join(["%s"] * len(filtered))
    conflict_cols = ", ".join(pk_cols)
    update_cols = [c for c in filtered if c not in pk_cols]
    if update_cols:
        update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        on_conflict = f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_str}"
    else:
        on_conflict = f"ON CONFLICT ({conflict_cols}) DO NOTHING"
    sql = f"INSERT INTO {table} ({col_str}) VALUES ({placeholders}) {on_conflict}"

    filtered_rows = [tuple(row[i] for i in col_indices) for row in rows]
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, filtered_rows)
        conn.commit()
    finally:
        _release(conn)
