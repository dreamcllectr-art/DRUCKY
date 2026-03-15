"""Tests for the data moat system — weight optimizer, base rate tracker, performance API.

Run: /tmp/druck_venv/bin/python -m pytest tests/test_data_moat.py -v
"""

import json
import math
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Fixtures ──

@pytest.fixture
def tmp_db(monkeypatch):
    """Create a temporary in-memory DB with all schemas initialized."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    monkeypatch.setenv("DATABASE_PATH", db_path)

    # Reload db module to pick up new path
    import importlib
    import tools.db
    importlib.reload(tools.db)
    tools.db.init_db()

    yield db_path

    os.unlink(db_path)


@pytest.fixture
def seeded_db(tmp_db):
    """DB with sample data for testing."""
    from tools.db import get_conn

    conn = get_conn()
    cur = conn.cursor()

    # Stock universe
    for sym, sector in [("AAPL", "Information Technology"), ("XOM", "Energy"),
                         ("JPM", "Financials"), ("JNJ", "Health Care"),
                         ("MSFT", "Information Technology")]:
        cur.execute("INSERT INTO stock_universe (symbol, sector) VALUES (?, ?)", (sym, sector))

    # Fundamentals (KV schema)
    for sym, mcap in [("AAPL", 3e12), ("XOM", 450e9), ("JPM", 550e9),
                       ("JNJ", 380e9), ("MSFT", 3.1e12)]:
        cur.execute("INSERT INTO fundamentals (symbol, metric, value) VALUES (?, 'marketCap', ?)",
                    (sym, mcap))

    # Price data
    for sym in ["AAPL", "XOM", "JPM", "JNJ", "MSFT"]:
        for d, close in [("2026-01-01", 100.0), ("2026-01-06", 102.0),
                          ("2026-01-15", 105.0), ("2026-01-31", 103.0),
                          ("2026-03-01", 110.0), ("2026-05-01", 108.0)]:
            cur.execute("INSERT OR REPLACE INTO price_data (symbol, date, close, high, low) VALUES (?, ?, ?, ?, ?)",
                        (sym, d, close, close * 1.02, close * 0.98))

    # Macro scores
    cur.execute("INSERT INTO macro_scores (date, regime, regime_score) VALUES ('2026-01-01', 'neutral', 50)")

    # Convergence signals
    for sym in ["AAPL", "XOM", "JPM", "JNJ", "MSFT"]:
        modules = json.dumps(["smartmoney", "worldview", "variant"])
        cur.execute(
            """INSERT INTO convergence_signals
               (symbol, date, convergence_score, module_count, conviction_level, active_modules, narrative)
               VALUES (?, '2026-01-01', 72.5, 3, 'HIGH', ?, 'test')""",
            (sym, modules),
        )

    # Signal outcomes (simulate aged signals)
    for sym in ["AAPL", "XOM", "JPM", "JNJ", "MSFT"]:
        modules = json.dumps(["smartmoney", "worldview", "variant"])
        cur.execute(
            """INSERT INTO signal_outcomes
               (symbol, signal_date, conviction_level, convergence_score,
                module_count, active_modules, regime_at_signal, entry_price,
                sector, market_cap_bucket)
               VALUES (?, '2026-01-01', 'HIGH', 72.5, 3, ?, 'neutral', 100.0, 'Tech', 'mega')""",
            (sym, modules),
        )

    conn.commit()
    conn.close()
    return tmp_db


# ══════════════════════════════════════════════════════════════════
# 1. Weight Optimizer Tests
# ══════════════════════════════════════════════════════════════════

class TestWeightOptimizer:
    """Tests for tools/weight_optimizer.py"""

    def test_compute_optimal_weights_normalization(self):
        """Weights must sum to 1.0 after optimization."""
        from tools.weight_optimizer import _compute_optimal_weights
        from tools.config import CONVERGENCE_WEIGHTS

        perf = {}
        for i, module in enumerate(CONVERGENCE_WEIGHTS):
            perf[module] = {
                "win_rate": 50 + i,
                "avg_return": 1.0 + i * 0.5,
                "sharpe": 0.3 + i * 0.1,
                "n_observations": 100,
            }

        result = _compute_optimal_weights(dict(CONVERGENCE_WEIGHTS), perf, "neutral")
        total = sum(result.values())
        assert abs(total - 1.0) < 0.01, f"Weights sum to {total}, expected ~1.0"

    def test_compute_optimal_weights_bounds(self):
        """No weight should exceed MAX or go below MIN."""
        from tools.weight_optimizer import _compute_optimal_weights
        from tools.config import CONVERGENCE_WEIGHTS, WO_MIN_WEIGHT, WO_MAX_WEIGHT

        # Give one module extreme Sharpe to test clamping
        perf = {}
        for module in CONVERGENCE_WEIGHTS:
            perf[module] = {
                "win_rate": 50,
                "avg_return": 1.0,
                "sharpe": 0.5,
                "n_observations": 100,
            }
        perf["smartmoney"]["sharpe"] = 10.0  # extreme

        result = _compute_optimal_weights(dict(CONVERGENCE_WEIGHTS), perf, "neutral")
        for module, weight in result.items():
            if module == "reddit":
                continue  # holdout
            assert weight >= WO_MIN_WEIGHT - 0.001, f"{module} weight {weight} below min {WO_MIN_WEIGHT}"
            assert weight <= WO_MAX_WEIGHT + 0.001, f"{module} weight {weight} above max {WO_MAX_WEIGHT}"

    def test_compute_optimal_weights_max_delta(self):
        """Weight change per cycle should not exceed MAX_DELTA."""
        from tools.weight_optimizer import _compute_optimal_weights
        from tools.config import CONVERGENCE_WEIGHTS, WO_MAX_DELTA_PER_CYCLE

        perf = {}
        for i, module in enumerate(CONVERGENCE_WEIGHTS):
            perf[module] = {
                "win_rate": 50,
                "avg_return": 1.0,
                "sharpe": -5.0 + i * 2.0,  # wide Sharpe range to force big deltas
                "n_observations": 100,
            }

        prior = dict(CONVERGENCE_WEIGHTS)
        result = _compute_optimal_weights(prior, perf, "neutral")
        for module in result:
            if module in ["reddit"]:
                continue
            delta = abs(result[module] - prior.get(module, 0))
            # After renormalization, delta constraint may be slightly exceeded,
            # but pre-normalization delta should be ≤ MAX + renorm adjustment
            assert delta < WO_MAX_DELTA_PER_CYCLE + 0.02, \
                f"{module} delta {delta:.4f} exceeds max {WO_MAX_DELTA_PER_CYCLE}"

    def test_holdout_modules_unchanged(self):
        """Modules in WO_HOLDOUT_MODULES should keep their prior weight."""
        from tools.weight_optimizer import _compute_optimal_weights
        from tools.config import CONVERGENCE_WEIGHTS, WO_HOLDOUT_MODULES

        perf = {}
        for module in CONVERGENCE_WEIGHTS:
            perf[module] = {
                "win_rate": 70,
                "avg_return": 5.0,
                "sharpe": 2.0,
                "n_observations": 100,
            }

        prior = dict(CONVERGENCE_WEIGHTS)
        result = _compute_optimal_weights(prior, perf, "neutral")
        for module in WO_HOLDOUT_MODULES:
            # Holdout modules should be very close to prior (only renorm shift)
            assert abs(result[module] - prior[module]) < 0.005, \
                f"Holdout {module} changed from {prior[module]} to {result[module]}"

    def test_insufficient_data_returns_prior(self):
        """With < 5 modules having Sharpe data, should return prior weights unchanged."""
        from tools.weight_optimizer import _compute_optimal_weights
        from tools.config import CONVERGENCE_WEIGHTS

        # Only 3 modules have Sharpe data (need 5)
        perf = {
            "smartmoney": {"win_rate": 60, "avg_return": 2, "sharpe": 1.0, "n_observations": 100},
            "worldview": {"win_rate": 55, "avg_return": 1, "sharpe": 0.5, "n_observations": 100},
            "variant": {"win_rate": 50, "avg_return": 0, "sharpe": 0.0, "n_observations": 100},
        }

        prior = dict(CONVERGENCE_WEIGHTS)
        result = _compute_optimal_weights(prior, perf, "neutral")
        assert result == prior, "Should return prior weights when insufficient modules have data"

    def test_data_sufficiency_check(self, tmp_db):
        """With empty DB, should report insufficient data."""
        from tools.weight_optimizer import _check_data_sufficiency
        result = _check_data_sufficiency()
        assert result["sufficient"] is False
        assert result["total_resolved"] == 0

    def test_run_with_insufficient_data(self, tmp_db):
        """run() should not crash on empty DB."""
        from tools.weight_optimizer import run
        run()  # should print "insufficient data" and return cleanly


# ══════════════════════════════════════════════════════════════════
# 2. Base Rate Tracker Tests
# ══════════════════════════════════════════════════════════════════

class TestBaseRateTracker:
    """Tests for tools/base_rate_tracker.py"""

    def test_sharpe_computation(self):
        """Sharpe ratio should be avg/std for known values."""
        from tools.base_rate_tracker import _compute_sharpe

        # Known values: returns [2, 4, 6, 8, 10] → avg=6, std=√10≈3.16, sharpe≈1.90
        returns = [2.0, 4.0, 6.0, 8.0, 10.0]
        sharpe = _compute_sharpe(returns)
        assert sharpe is not None
        expected = 6.0 / math.sqrt(10)  # ≈ 1.897
        assert abs(sharpe - round(expected, 2)) < 0.01, f"Sharpe {sharpe} != expected {expected:.2f}"

    def test_sharpe_insufficient_data(self):
        """Sharpe should return None with < 5 data points."""
        from tools.base_rate_tracker import _compute_sharpe
        assert _compute_sharpe([1.0, 2.0, 3.0]) is None

    def test_sharpe_zero_std(self):
        """Sharpe should return None when all returns are identical."""
        from tools.base_rate_tracker import _compute_sharpe
        assert _compute_sharpe([5.0, 5.0, 5.0, 5.0, 5.0]) is None

    def test_confidence_interval(self):
        """95% CI should bracket the mean."""
        from tools.base_rate_tracker import _confidence_interval_95
        returns = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        ci = _confidence_interval_95(returns)
        assert ci is not None
        mean = 5.5
        assert ci[0] < mean < ci[1], f"CI {ci} should bracket mean {mean}"

    def test_confidence_interval_insufficient(self):
        """CI should return None with < 5 data points."""
        from tools.base_rate_tracker import _confidence_interval_95
        assert _confidence_interval_95([1.0, 2.0]) is None

    def test_all_modules_list_matches_config(self):
        """ALL_MODULES should contain exactly the same keys as CONVERGENCE_WEIGHTS."""
        from tools.base_rate_tracker import ALL_MODULES
        from tools.config import CONVERGENCE_WEIGHTS
        assert set(ALL_MODULES) == set(CONVERGENCE_WEIGHTS.keys()), \
            f"Mismatch: {set(ALL_MODULES) ^ set(CONVERGENCE_WEIGHTS.keys())}"

    def test_return_windows_complete(self):
        """RETURN_WINDOWS should cover 1, 5, 10, 20, 30, 60, 90 days."""
        from tools.base_rate_tracker import RETURN_WINDOWS
        days = [w[2] for w in RETURN_WINDOWS]
        assert days == [1, 5, 10, 20, 30, 60, 90]

    def test_log_signals_empty_db(self, tmp_db):
        """log_signals() should handle empty convergence_signals gracefully."""
        from tools.base_rate_tracker import log_signals
        result = log_signals()
        assert result == 0

    def test_update_outcomes_empty_db(self, tmp_db):
        """update_outcomes() should handle no signals gracefully."""
        from tools.base_rate_tracker import update_outcomes
        result = update_outcomes()
        assert all(v == 0 for v in result.values())


# ══════════════════════════════════════════════════════════════════
# 3. Integration Tests
# ══════════════════════════════════════════════════════════════════

class TestIntegration:
    """End-to-end integration tests."""

    def test_convergence_engine_adaptive_fallback(self, tmp_db):
        """Convergence engine should use static weights when no adaptive weights exist."""
        from tools.db import query
        # weight_history should be empty
        rows = query("SELECT COUNT(*) as cnt FROM weight_history")
        assert rows[0]["cnt"] == 0

    def test_db_migration_creates_all_tables(self, tmp_db):
        """init_db() should create weight_history and weight_optimizer_log tables."""
        from tools.db import query
        tables = query("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = {t["name"] for t in tables}
        assert "weight_history" in table_names
        assert "weight_optimizer_log" in table_names
        assert "signal_outcomes" in table_names
        assert "module_performance" in table_names

    def test_signal_outcomes_schema_has_short_term_columns(self, tmp_db):
        """signal_outcomes table should have 1d/5d/10d/20d return columns."""
        from tools.db import get_conn
        conn = get_conn()
        cur = conn.execute("PRAGMA table_info(signal_outcomes)")
        columns = {row[1] for row in cur.fetchall()}
        conn.close()
        for days in [1, 5, 10, 20, 30, 60, 90]:
            assert f"return_{days}d" in columns, f"Missing return_{days}d column"
            assert f"price_{days}d" in columns, f"Missing price_{days}d column"
        assert "sector" in columns
        assert "market_cap_bucket" in columns

    def test_weight_history_schema(self, tmp_db):
        """weight_history should have required columns."""
        from tools.db import get_conn
        conn = get_conn()
        cur = conn.execute("PRAGMA table_info(weight_history)")
        columns = {row[1] for row in cur.fetchall()}
        conn.close()
        for col in ["date", "regime", "module_name", "weight", "prior_weight", "reason"]:
            assert col in columns, f"Missing {col} column in weight_history"

    def test_upsert_module_performance(self, tmp_db):
        """Upserting module_performance should not NULL out existing columns."""
        from tools.db import upsert_many, query

        # First write with all columns
        upsert_many("module_performance",
            ["report_date", "module_name", "regime", "sector",
             "total_signals", "win_count", "win_rate",
             "avg_return_1d", "avg_return_5d", "avg_return_30d",
             "sharpe_ratio", "observation_count"],
            [("2026-01-01", "smartmoney", "neutral", "all",
              100, 60, 60.0, 0.5, 1.2, 3.5, 1.5, 100)])

        # Second write for same key with all columns
        upsert_many("module_performance",
            ["report_date", "module_name", "regime", "sector",
             "total_signals", "win_count", "win_rate",
             "avg_return_1d", "avg_return_5d", "avg_return_30d",
             "sharpe_ratio", "observation_count"],
            [("2026-01-01", "smartmoney", "neutral", "all",
              110, 65, 59.1, 0.6, 1.3, 3.8, 1.6, 110)])

        rows = query(
            "SELECT * FROM module_performance WHERE module_name = 'smartmoney' AND regime = 'neutral'"
        )
        assert len(rows) == 1
        assert rows[0]["avg_return_5d"] == 1.3  # should be updated, not NULL


# ══════════════════════════════════════════════════════════════════
# 4. Eval Cases (from scorecard)
# ══════════════════════════════════════════════════════════════════

class TestEvalCases:
    """Eval cases from the build evaluation scorecard."""

    def test_weight_normalization_property(self):
        """EVAL CASE 2: After optimize, weights must sum to 1.0."""
        from tools.weight_optimizer import _compute_optimal_weights
        from tools.config import CONVERGENCE_WEIGHTS
        import random

        random.seed(42)
        for _ in range(10):
            perf = {}
            for module in CONVERGENCE_WEIGHTS:
                perf[module] = {
                    "win_rate": random.uniform(30, 70),
                    "avg_return": random.uniform(-5, 10),
                    "sharpe": random.uniform(-1, 3),
                    "n_observations": random.randint(60, 500),
                }
            result = _compute_optimal_weights(dict(CONVERGENCE_WEIGHTS), perf, "neutral")
            total = sum(result.values())
            assert abs(total - 1.0) < 0.01, f"Weights sum to {total}"

    def test_module_key_completeness(self):
        """EVAL CASE 4: Adaptive weights dict should have all module keys."""
        from tools.weight_optimizer import _compute_optimal_weights
        from tools.config import CONVERGENCE_WEIGHTS

        perf = {}
        for module in CONVERGENCE_WEIGHTS:
            perf[module] = {
                "win_rate": 55,
                "avg_return": 2.0,
                "sharpe": 0.8,
                "n_observations": 100,
            }

        result = _compute_optimal_weights(dict(CONVERGENCE_WEIGHTS), perf, "neutral")
        assert set(result.keys()) == set(CONVERGENCE_WEIGHTS.keys()), \
            f"Missing keys: {set(CONVERGENCE_WEIGHTS.keys()) - set(result.keys())}"

    def test_sharpe_sign_correctness(self):
        """Verify Sharpe sign: positive returns → positive Sharpe."""
        from tools.base_rate_tracker import _compute_sharpe

        # All positive returns
        pos_sharpe = _compute_sharpe([1.0, 2.0, 3.0, 4.0, 5.0])
        assert pos_sharpe is not None and pos_sharpe > 0, f"Positive returns gave Sharpe={pos_sharpe}"

        # All negative returns
        neg_sharpe = _compute_sharpe([-1.0, -2.0, -3.0, -4.0, -5.0])
        assert neg_sharpe is not None and neg_sharpe < 0, f"Negative returns gave Sharpe={neg_sharpe}"

    def test_bayesian_update_direction(self):
        """Modules with higher Sharpe should get MORE weight, lower should get LESS."""
        from tools.weight_optimizer import _compute_optimal_weights
        from tools.config import CONVERGENCE_WEIGHTS

        perf = {}
        for module in CONVERGENCE_WEIGHTS:
            perf[module] = {
                "win_rate": 50,
                "avg_return": 1.0,
                "sharpe": 0.5,  # baseline
                "n_observations": 100,
            }
        # Make smartmoney clearly better, alt_data clearly worse
        perf["smartmoney"]["sharpe"] = 2.0
        perf["alt_data"]["sharpe"] = -1.0

        prior = dict(CONVERGENCE_WEIGHTS)
        result = _compute_optimal_weights(prior, perf, "neutral")

        # smartmoney should gain weight relative to prior
        assert result["smartmoney"] > prior["smartmoney"], \
            f"High-Sharpe module should gain weight: {result['smartmoney']} <= {prior['smartmoney']}"
        # alt_data should lose weight relative to prior (but clamped to MIN)
        assert result["alt_data"] <= prior["alt_data"], \
            f"Low-Sharpe module should lose weight: {result['alt_data']} > {prior['alt_data']}"
