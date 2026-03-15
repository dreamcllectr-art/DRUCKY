"""Smoke tests — verify every module imports and core functions work.

Run: venv/bin/python -m pytest tests/test_smoke.py -v
"""

import importlib
import os
import sys

import pytest

# Ensure tools/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 1. Every tool module should import without errors ──

TOOL_MODULES = [
    "tools.config",
    "tools.db",
    "tools.fetch_prices",
    "tools.fetch_stock_universe",
    "tools.fetch_macro",
    "tools.fetch_fmp_fundamentals",
    "tools.fetch_news_sentiment",
    "tools.fetch_eia_data",
    "tools.technical_scoring",
    "tools.fundamental_scoring",
    "tools.macro_regime",
    "tools.market_breadth",
    "tools.economic_dashboard",
    "tools.accounting_forensics",
    "tools.variant_perception",
    "tools.filings_13f",
    "tools.insider_trading",
    "tools.research_sources",
    "tools.reddit_scanner",
    "tools.earnings_transcript_analyzer",
    "tools.founder_letter_analyzer",
    "tools.foreign_intel",
    "tools.news_displacement",
    "tools.sector_experts",
    "tools.pairs_trading",
    "tools.ma_signals",
    "tools.energy_intel",
    "tools.energy_intel_data",
    "tools.alternative_data",
    "tools.prediction_markets",
    "tools.worldview_model",
    "tools.pattern_scanner",
    "tools.pattern_options",
    "tools.options_intel",
    "tools.signal_generator",
    "tools.position_sizer",
    "tools.convergence_engine",
    "tools.devils_advocate",
    "tools.base_rate_tracker",
    "tools.paper_trader",
    "tools.check_alerts",
    "tools.send_alerts",
    "tools.hyperliquid_gap",
    "tools.ticker_mapper",
    "tools.ta_gate",
    "tools.daily_pipeline",
    "tools.api",
]


@pytest.mark.parametrize("module_name", TOOL_MODULES)
def test_module_imports(module_name):
    """Every tool module should import without errors."""
    mod = importlib.import_module(module_name)
    assert mod is not None


# ── 2. Database schema should initialize cleanly ──

def test_db_init():
    """Database init_db() should create all tables without errors."""
    os.environ.setdefault("DATABASE_PATH", ":memory:")
    # Force re-init in memory
    import tools.db as db
    db._DB_PATH = None
    os.environ["DATABASE_PATH"] = ":memory:"
    db._DB_PATH = None
    db.init_db()

    # Verify critical tables exist
    rows = db.query("SELECT name FROM sqlite_master WHERE type='table'")
    table_names = {r["name"] for r in rows}

    required_tables = {
        "stock_universe", "price_data", "signals", "macro_scores",
        "technical_scores", "fundamental_scores", "convergence_signals",
        "pair_relationships", "pair_signals", "pair_spreads",
        "ma_signals", "ma_rumors",
        "insider_transactions", "insider_signals",
        "economic_dashboard", "economic_heat_index",
        "prediction_market_signals", "prediction_market_raw",
        "worldview_signals", "world_macro_indicators",
        "alternative_data", "alt_data_scores",
        "energy_intel_signals",
        "hl_price_snapshots", "hl_gap_signals",
        "pattern_scan", "options_intel",
        "devils_advocate", "signal_outcomes",
    }

    missing = required_tables - table_names
    assert not missing, f"Missing tables: {missing}"


# ── 3. Config should load all API key variables ──

def test_config_loads():
    """Config module should define all expected API key variables."""
    from tools.config import (
        FRED_API_KEY, FMP_API_KEY, FINNHUB_API_KEY,
        ALPHA_VANTAGE_API_KEY, EIA_API_KEY, GEMINI_API_KEY,
        SERPER_API_KEY, FIRECRAWL_API_KEY, DEEPL_API_KEY,
        NASA_FIRMS_API_KEY, USDA_API_KEY,
        REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET,
        SMTP_USER, SMTP_PASS, EMAIL_TO,
    )
    # They can be empty strings (not configured) but must exist
    assert FRED_API_KEY is not None
    assert FMP_API_KEY is not None


# ── 4. API app should instantiate ──

def test_api_app_creates():
    """FastAPI app should instantiate and have health endpoint."""
    from tools.api import app
    assert app is not None
    assert app.title == "Druckenmiller Alpha API"

    # Check routes exist
    route_paths = {r.path for r in app.routes}
    required_routes = {
        "/api/health",
        "/api/signals",
        "/api/macro",
        "/api/convergence",
        "/api/ma-signals",
        "/api/prediction-markets",
        "/api/worldview",
        "/api/economic-indicators",
        "/api/insider-trading",
        "/api/pairs",
        "/api/hyperliquid/gaps",
        "/api/energy-intel",
        "/api/patterns",
        "/api/alt-data",
    }
    missing = required_routes - route_paths
    assert not missing, f"Missing API routes: {missing}"


# ── 5. Pipeline function should exist ──

def test_pipeline_exists():
    """Daily pipeline main() should be callable."""
    from tools.daily_pipeline import main
    assert callable(main)


# ── 6. Convergence engine weights should sum to 1.0 ──

def test_convergence_weights():
    """Convergence module weights should sum to ~1.0."""
    from tools.config import CONVERGENCE_WEIGHTS
    total = sum(CONVERGENCE_WEIGHTS.values())
    assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected ~1.0"
