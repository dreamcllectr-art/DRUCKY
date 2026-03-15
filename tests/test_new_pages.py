"""Smoke tests for new dashboard pages and API endpoints.

Run: venv/bin/python -m pytest tests/test_new_pages.py -v
"""

import os
import sys

import pytest

# Ensure tools/ is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 1. New API routes exist ──

def test_new_api_routes_registered():
    """Discover, signal-conflicts, stress-test, portfolio routes are registered."""
    from tools.api import app
    route_paths = {r.path for r in app.routes}

    new_routes = {
        "/api/discover",
        "/api/discover/sectors",
        "/api/signal-conflicts",
        "/api/signal-conflicts/summary",
        "/api/signal-conflicts/{symbol}",
        "/api/stress-test",
        "/api/stress-test/concentration",
        "/api/stress-test/{scenario}",
        "/api/portfolio",
        "/api/portfolio/closed",
        "/api/portfolio/stats",
        "/api/portfolio/sync",
    }
    missing = new_routes - route_paths
    assert not missing, f"Missing API routes: {missing}"


# ── 2. Discover endpoint graceful degradation ──

def test_discover_endpoint_handles_missing_tables():
    """Discover endpoint should not crash when enrichment tables are empty."""
    os.environ["DATABASE_PATH"] = ":memory:"
    import tools.db as db
    db._DB_PATH = None
    db.init_db()

    # Insert minimal convergence data
    conn = db.get_conn()
    try:
        conn.execute("INSERT INTO stock_universe (symbol, name, sector) VALUES ('TEST', 'Test Corp', 'Technology')")
        conn.execute("""
            INSERT INTO convergence_signals (symbol, date, convergence_score, module_count, conviction_level, active_modules, narrative)
            VALUES ('TEST', '2026-03-14', 75.0, 5, 'HIGH', 'main_signal,smartmoney', 'Test narrative')
        """)
        conn.commit()
    finally:
        conn.close()

    from tools.api import discover
    result = discover()
    assert isinstance(result, list)
    assert len(result) >= 1
    stock = result[0]
    assert stock["symbol"] == "TEST"
    assert stock["company_name"] == "Test Corp"
    assert stock["sector"] == "Technology"
    # Enrichment defaults when tables are empty
    assert stock["conflict_count"] == 0
    assert stock["is_fat_pitch"] == 0
    assert stock["has_insider_cluster"] == 0
    assert stock["is_ma_target"] == 0
    assert stock["has_unusual_options"] == 0


# ── 3. Portfolio stats handle empty state ──

def test_portfolio_stats_empty():
    """Portfolio stats should return zeros when no trades exist."""
    os.environ["DATABASE_PATH"] = ":memory:"
    import tools.db as db
    db._DB_PATH = None
    db.init_db()

    from tools.api import portfolio_stats
    result = portfolio_stats()
    assert result["open_count"] == 0
    assert result["closed_count"] == 0
    assert result["win_rate"] == 0
    assert result["profit_factor"] == 0


# ── 4. Signal conflicts handle empty state ──

def test_signal_conflicts_empty():
    """Signal conflicts endpoint should return empty list, not error."""
    os.environ["DATABASE_PATH"] = ":memory:"
    import tools.db as db
    db._DB_PATH = None
    db.init_db()

    from tools.api import signal_conflicts_list
    result = signal_conflicts_list()
    assert isinstance(result, list)
    assert len(result) == 0


# ── 5. Stress test handles empty state ──

def test_stress_test_empty():
    """Stress test endpoint should return empty list, not error."""
    os.environ["DATABASE_PATH"] = ":memory:"
    import tools.db as db
    db._DB_PATH = None
    db.init_db()

    from tools.api import stress_test_results
    result = stress_test_results()
    assert isinstance(result, list)


# ── 6. Concentration risk handles empty state ──

def test_concentration_risk_empty():
    """Concentration risk endpoint should return empty dict, not error."""
    os.environ["DATABASE_PATH"] = ":memory:"
    import tools.db as db
    db._DB_PATH = None
    db.init_db()

    from tools.api import concentration_risk
    result = concentration_risk()
    assert isinstance(result, dict)


# ── 7. Portfolio sync creates positions from HIGH conviction ──

def test_portfolio_sync_creates_positions():
    """Sync should create paper positions from HIGH conviction signals."""
    os.environ["DATABASE_PATH"] = ":memory:"
    import tools.db as db
    db._DB_PATH = None
    db.init_db()

    conn = db.get_conn()
    try:
        conn.execute("INSERT INTO stock_universe (symbol, name, sector) VALUES ('AAPL', 'Apple Inc', 'Technology')")
        conn.execute("""
            INSERT INTO convergence_signals (symbol, date, convergence_score, module_count, conviction_level, active_modules, narrative)
            VALUES ('AAPL', '2026-03-14', 85.0, 8, 'HIGH', 'main_signal,smartmoney', 'Strong conviction')
        """)
        conn.execute("""
            INSERT INTO signals (symbol, date, asset_class, macro_score, technical_score, fundamental_score, composite_score, signal, entry_price, stop_loss, target_price, rr_ratio)
            VALUES ('AAPL', '2026-03-14', 'equity', 70, 80, 75, 75, 'STRONG_BUY', 185.50, 175.00, 210.00, 2.3)
        """)
        conn.commit()
    finally:
        conn.close()

    from tools.api import portfolio_sync
    result = portfolio_sync()
    assert result["synced"] == 1
    assert "AAPL" in result["symbols"]

    # Verify position was created
    positions = db.query("SELECT * FROM portfolio WHERE symbol = 'AAPL'")
    assert len(positions) == 1
    assert positions[0]["entry_price"] == 185.50
    assert positions[0]["stop_loss"] == 175.00
    assert positions[0]["status"] == "open"


# ── 8. Portfolio sync is idempotent ──

def test_portfolio_sync_idempotent():
    """Running sync twice should not duplicate positions."""
    os.environ["DATABASE_PATH"] = ":memory:"
    import tools.db as db
    db._DB_PATH = None
    db.init_db()

    conn = db.get_conn()
    try:
        conn.execute("INSERT INTO stock_universe (symbol, name, sector) VALUES ('MSFT', 'Microsoft', 'Technology')")
        conn.execute("""
            INSERT INTO convergence_signals (symbol, date, convergence_score, module_count, conviction_level, active_modules, narrative)
            VALUES ('MSFT', '2026-03-14', 80.0, 7, 'HIGH', 'main_signal', 'High conviction')
        """)
        conn.execute("""
            INSERT INTO signals (symbol, date, asset_class, macro_score, technical_score, fundamental_score, composite_score, signal, entry_price, stop_loss, target_price, rr_ratio)
            VALUES ('MSFT', '2026-03-14', 'equity', 65, 70, 72, 70, 'BUY', 420.00, 400.00, 460.00, 2.0)
        """)
        conn.commit()
    finally:
        conn.close()

    from tools.api import portfolio_sync
    result1 = portfolio_sync()
    assert result1["synced"] == 1

    result2 = portfolio_sync()
    assert result2["synced"] == 0  # Already open, should not duplicate

    positions = db.query("SELECT * FROM portfolio WHERE symbol = 'MSFT'")
    assert len(positions) == 1  # Only one position


# ── 9. Frontend page files exist and are valid ──

@pytest.mark.parametrize("page", [
    "discover", "stress-test", "paper-trader", "signal-conflicts",
])
def test_frontend_page_exists(page):
    """Each new dashboard page should exist as a valid TSX file."""
    page_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dashboard", "src", "app", page, "page.tsx"
    )
    assert os.path.exists(page_path), f"Missing page: {page_path}"

    content = open(page_path).read()
    # Basic structural checks
    assert "'use client'" in content, f"{page} missing 'use client' directive"
    assert "export default function" in content, f"{page} missing default export"
    assert "aria-" in content or "role=" in content, f"{page} missing accessibility attributes"

    # Balanced braces
    opens = content.count('{')
    closes = content.count('}')
    assert opens == closes, f"{page} has unbalanced braces: {opens} opens, {closes} closes"


# ── 10. TypeScript types align with backend ──

def test_discover_stock_type_has_all_enrichment_fields():
    """DiscoverStock type should include all fields set by the backend."""
    api_ts_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "dashboard", "src", "lib", "api.ts"
    )
    content = open(api_ts_path).read()

    # Fields set by the discover endpoint enrichment loop
    required_fields = [
        "conflict_count", "max_conflict_severity",
        "is_fat_pitch", "fat_pitch_score", "fat_pitch_conditions",
        "has_insider_cluster", "insider_score",
        "is_ma_target", "ma_target_score", "deal_stage",
        "has_unusual_options", "options_score", "unusual_options_count", "unusual_options_bias",
    ]
    for field in required_fields:
        assert field in content, f"DiscoverStock type missing field: {field}"
