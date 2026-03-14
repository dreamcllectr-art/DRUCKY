"""Convergence Engine — master signal synthesis.

Asks: how many independent modules agree on the same stock?
Weights modules, produces conviction levels (HIGH/NOTABLE/WATCH/BLOCKED).

Module weights (must sum to 1.0):
  Smart Money (13F):        15%
  Worldview Model:          13%
  Variant Perception:        9%
  Foreign Intel:             7%
  News Displacement:         6%
  Research Sources:          6%
  Prediction Markets:        5%
  Pairs Trading:             5%
  Energy Intelligence:       5%
  Sector Expert:             5%
  Pattern & Options:         4%
  Estimate Momentum:         4%
  M&A Intelligence:          4%
  Consensus Blindspots:      4%   ← Howard Marks second-level thinking
  Main Signal:               3%
  AI Regulatory Intel:       3%
  Alternative Data:          2%
  Reddit:                    0%
"""

import json
import logging
from datetime import date

from tools.db import get_conn, query
from tools.config import (
    CONVERGENCE_WEIGHTS, CONVICTION_HIGH, CONVICTION_NOTABLE,
    REGIME_CONVERGENCE_WEIGHTS,
)

logger = logging.getLogger(__name__)

# Score threshold for a module to "count" as agreeing
MODULE_THRESHOLD = 50.0


def _load_module_scores() -> dict[str, dict[str, float]]:
    """Load latest scores from each module's table.

    Returns: {module_name: {symbol: score_0_to_100}}
    """
    modules = {}

    # --- Main Signal (composite_score already 0-100) ---
    rows = query("""
        SELECT s.symbol, s.composite_score
        FROM signals s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM signals GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
        WHERE s.composite_score IS NOT NULL
    """)
    modules["main_signal"] = {r["symbol"]: r["composite_score"] for r in rows}

    # --- Smart Money (conviction_score 0-100) ---
    rows = query("""
        SELECT s.symbol, s.conviction_score
        FROM smart_money_scores s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM smart_money_scores GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
        WHERE s.conviction_score IS NOT NULL
    """)
    modules["smartmoney"] = {r["symbol"]: r["conviction_score"] for r in rows}

    # --- Worldview (thesis_alignment_score 0-100) ---
    rows = query("""
        SELECT s.symbol, s.thesis_alignment_score
        FROM worldview_signals s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM worldview_signals GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
        WHERE s.thesis_alignment_score IS NOT NULL
    """)
    modules["worldview"] = {r["symbol"]: r["thesis_alignment_score"] for r in rows}

    # --- Variant Perception (variant_score 0-100) ---
    rows = query("""
        SELECT s.symbol, s.variant_score
        FROM variant_analysis s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM variant_analysis GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
        WHERE s.variant_score IS NOT NULL
    """)
    modules["variant"] = {r["symbol"]: r["variant_score"] for r in rows}

    # --- Research Sources (avg sentiment*relevance over 7 days) ---
    rows = query("""
        SELECT symbol,
               AVG(sentiment * relevance_score) as avg_score,
               COUNT(*) as cnt
        FROM research_signals
        WHERE symbol IS NOT NULL
          AND date >= date('now', '-7 days')
        GROUP BY symbol
    """)
    modules["research"] = {}
    for r in rows:
        # Normalize: sentiment*relevance ranges roughly -100 to 100 → shift to 0-100
        modules["research"][r["symbol"]] = max(0, min(100, (r["avg_score"] + 100) / 2))

    # --- Reddit (social_velocity_score 0-100) ---
    rows = query("""
        SELECT s.symbol, s.social_velocity_score
        FROM reddit_signals s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM reddit_signals GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
        WHERE s.social_velocity_score IS NOT NULL
    """)
    modules["reddit"] = {r["symbol"]: r["social_velocity_score"] for r in rows}

    # --- Foreign Intelligence (computed from foreign_intel_signals) ---
    try:
        from tools.foreign_intel import compute_foreign_intel_scores
        modules["foreign_intel"] = compute_foreign_intel_scores()
    except Exception as e:
        logger.warning(f"Foreign intel scores unavailable: {e}")
        modules["foreign_intel"] = {}

    # --- News Displacement (displacement_score 0-100, max over 7 days) ---
    rows = query("""
        SELECT symbol, MAX(displacement_score) as score
        FROM news_displacement
        WHERE date >= date('now', '-7 days')
          AND status = 'active'
        GROUP BY symbol
    """)
    modules["news_displacement"] = {r["symbol"]: r["score"] for r in rows if r["score"]}

    # --- Alternative Data (alt_data_score 0-100) ---
    rows = query("""
        SELECT s.symbol, s.alt_data_score
        FROM alt_data_scores s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM alt_data_scores GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
        WHERE s.alt_data_score IS NOT NULL
    """)
    modules["alt_data"] = {r["symbol"]: r["alt_data_score"] for r in rows}

    # --- Sector Expert (sector_displacement_score 0-100, max over 7 days) ---
    rows = query("""
        SELECT symbol, MAX(sector_displacement_score) as score
        FROM sector_expert_signals
        WHERE date >= date('now', '-7 days')
        GROUP BY symbol
    """)
    modules["sector_expert"] = {r["symbol"]: r["score"] for r in rows if r["score"]}

    # --- Pairs Trading (max pairs_score over active runner signals, 7 days) ---
    try:
        rows = query("""
            SELECT runner_symbol as symbol, MAX(pairs_score) as score
            FROM pair_signals
            WHERE date >= date('now', '-7 days')
              AND status = 'active'
              AND runner_symbol IS NOT NULL
            GROUP BY runner_symbol
        """)
        modules["pairs"] = {r["symbol"]: r["score"] for r in rows if r["score"]}
    except Exception as e:
        logger.warning(f"Pairs scores unavailable: {e}")
        modules["pairs"] = {}

    # --- M&A Intelligence (max ma_score over 7 days, active signals) ---
    try:
        rows = query("""
            SELECT symbol, MAX(ma_score) as score
            FROM ma_signals
            WHERE date >= date('now', '-7 days')
              AND status = 'active'
            GROUP BY symbol
        """)
        modules["ma"] = {r["symbol"]: r["score"] for r in rows if r["score"]}
    except Exception as e:
        logger.warning(f"M&A scores unavailable: {e}")
        modules["ma"] = {}

    # --- Energy Intelligence (max energy_intel_score over 7 days) ---
    try:
        rows = query("""
            SELECT symbol, MAX(energy_intel_score) as score
            FROM energy_intel_signals
            WHERE date >= date('now', '-7 days')
            GROUP BY symbol
        """)
        modules["energy_intel"] = {r["symbol"]: r["score"] for r in rows if r["score"]}
    except Exception as e:
        logger.warning(f"Energy intel scores unavailable: {e}")
        modules["energy_intel"] = {}

    # --- Prediction Markets (max pm_score over 7 days) ---
    try:
        rows = query("""
            SELECT symbol, MAX(pm_score) as score
            FROM prediction_market_signals
            WHERE date >= date('now', '-7 days')
              AND status = 'active'
            GROUP BY symbol
        """)
        modules["prediction_markets"] = {r["symbol"]: r["score"] for r in rows if r["score"]}
    except Exception as e:
        logger.warning(f"Prediction market scores unavailable: {e}")
        modules["prediction_markets"] = {}

    # --- Pattern & Options Intelligence (max pattern_options_score over 7 days) ---
    try:
        rows = query("""
            SELECT symbol, MAX(pattern_options_score) as score
            FROM pattern_options_signals
            WHERE date >= date('now', '-7 days')
              AND status = 'active'
            GROUP BY symbol
        """)
        modules["pattern_options"] = {r["symbol"]: r["score"] for r in rows if r["score"]}
    except Exception as e:
        logger.warning(f"Pattern options scores unavailable: {e}")
        modules["pattern_options"] = {}

    # --- Estimate Revision Momentum (max em_score over 7 days) ---
    try:
        rows = query("""
            SELECT symbol, MAX(em_score) as score
            FROM estimate_momentum_signals
            WHERE date >= date('now', '-7 days')
            GROUP BY symbol
        """)
        modules["estimate_momentum"] = {r["symbol"]: r["score"] for r in rows if r["score"]}
    except Exception as e:
        logger.warning(f"Estimate momentum scores unavailable: {e}")
        modules["estimate_momentum"] = {}

    # --- AI Regulatory Intelligence (max reg_score over 7 days) ---
    try:
        rows = query("""
            SELECT symbol, MAX(reg_score) as score
            FROM regulatory_signals
            WHERE date >= date('now', '-7 days')
              AND status = 'active'
            GROUP BY symbol
        """)
        modules["ai_regulatory"] = {r["symbol"]: r["score"] for r in rows if r["score"]}
    except Exception as e:
        logger.warning(f"AI regulatory scores unavailable: {e}")
        modules["ai_regulatory"] = {}

    # --- Consensus Blindspots (max cbs_score over 7 days, exclude _MARKET) ---
    try:
        rows = query("""
            SELECT symbol, MAX(cbs_score) as score
            FROM consensus_blindspot_signals
            WHERE date >= date('now', '-7 days')
              AND symbol != '_MARKET'
            GROUP BY symbol
        """)
        modules["consensus_blindspots"] = {r["symbol"]: r["score"] for r in rows if r["score"]}
    except Exception as e:
        logger.warning(f"Consensus blindspots scores unavailable: {e}")
        modules["consensus_blindspots"] = {}

    return modules


def _check_forensic_block(symbol: str) -> bool:
    """Check if a symbol is blocked by accounting forensics."""
    rows = query("""
        SELECT severity FROM forensic_alerts
        WHERE symbol = ? AND severity = 'CRITICAL'
        ORDER BY date DESC LIMIT 1
    """, [symbol])
    return bool(rows)


def _generate_narrative(symbol: str, active_modules: list[str],
                        module_scores: dict, conviction: str) -> str:
    """Generate a brief human-readable narrative for the convergence signal."""
    parts = []
    for mod in active_modules:
        score = module_scores.get(mod, {}).get(symbol, 0)
        parts.append(f"{mod}={score:.0f}")
    modules_str = ", ".join(parts)
    return f"{conviction} conviction: {len(active_modules)} modules agree ({modules_str})"


def run():
    """Run the convergence engine — compute master convergence signals."""
    print("\n" + "=" * 60)
    print("  CONVERGENCE ENGINE")
    print("=" * 60)

    module_scores = _load_module_scores()

    # Collect all symbols across all modules
    all_symbols = set()
    for mod_data in module_scores.values():
        all_symbols.update(mod_data.keys())

    # Select regime-adaptive weight profile (adaptive > static fallback)
    regime_rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    current_regime = regime_rows[0]["regime"] if regime_rows else "neutral"

    weight_source = "static"
    weights = REGIME_CONVERGENCE_WEIGHTS.get(current_regime, CONVERGENCE_WEIGHTS)

    # Try adaptive weights from weight_optimizer (the data moat flywheel)
    try:
        from tools.config import WO_ENABLE_ADAPTIVE
        if WO_ENABLE_ADAPTIVE:
            adaptive_rows = query(
                """SELECT module_name, weight FROM weight_history
                   WHERE regime = ?
                     AND date = (SELECT MAX(date) FROM weight_history WHERE regime = ?)""",
                [current_regime, current_regime],
            )
            if adaptive_rows and len(adaptive_rows) >= 10:
                adaptive_weights = {r["module_name"]: r["weight"] for r in adaptive_rows}
                # Ensure all static modules are present (fill missing with static defaults)
                static_base = REGIME_CONVERGENCE_WEIGHTS.get(current_regime, CONVERGENCE_WEIGHTS)
                for mod in static_base:
                    if mod not in adaptive_weights:
                        adaptive_weights[mod] = static_base[mod]
                weight_total = sum(adaptive_weights.values())
                if 0.95 <= weight_total <= 1.05:
                    weights = adaptive_weights
                    weight_source = "adaptive"
                else:
                    logger.warning(f"Adaptive weights sum to {weight_total:.3f}, using static")
    except Exception as e:
        logger.warning(f"Adaptive weights unavailable, using static: {e}")

    print(f"  Modules loaded: {list(module_scores.keys())}")
    print(f"  Weight profile: {current_regime} ({weight_source})")
    print(f"  Total symbols across modules: {len(all_symbols)}")

    today = date.today().isoformat()
    results = []

    for symbol in all_symbols:
        # Count active modules (score above threshold)
        active = []
        weighted_sum = 0.0
        weight_sum = 0.0

        for mod_name, weight in weights.items():
            score = module_scores.get(mod_name, {}).get(symbol, 0)
            if score > MODULE_THRESHOLD:
                active.append(mod_name)
            weighted_sum += score * weight
            weight_sum += weight

        convergence_score = weighted_sum / weight_sum if weight_sum else 0
        module_count = len(active)

        # Forensic veto
        forensic_blocked = _check_forensic_block(symbol)

        # Conviction level
        if forensic_blocked:
            conviction = "BLOCKED"
        elif module_count >= CONVICTION_HIGH:
            conviction = "HIGH"
        elif module_count >= CONVICTION_NOTABLE:
            conviction = "NOTABLE"
        elif module_count >= 1:
            conviction = "WATCH"
        else:
            continue  # No signal, skip

        narrative = _generate_narrative(symbol, active, module_scores, conviction)

        results.append((
            symbol, today, convergence_score, module_count, conviction,
            1 if forensic_blocked else 0,
            module_scores.get("main_signal", {}).get(symbol),
            module_scores.get("smartmoney", {}).get(symbol),
            module_scores.get("worldview", {}).get(symbol),
            module_scores.get("variant", {}).get(symbol),
            module_scores.get("research", {}).get(symbol),
            module_scores.get("reddit", {}).get(symbol),
            module_scores.get("foreign_intel", {}).get(symbol),
            module_scores.get("news_displacement", {}).get(symbol),
            module_scores.get("alt_data", {}).get(symbol),
            module_scores.get("sector_expert", {}).get(symbol),
            module_scores.get("pairs", {}).get(symbol),
            module_scores.get("ma", {}).get(symbol),
            module_scores.get("energy_intel", {}).get(symbol),
            module_scores.get("prediction_markets", {}).get(symbol),
            module_scores.get("pattern_options", {}).get(symbol),
            module_scores.get("estimate_momentum", {}).get(symbol),
            module_scores.get("ai_regulatory", {}).get(symbol),
            module_scores.get("consensus_blindspots", {}).get(symbol),
            json.dumps(active),
            narrative,
        ))

    # Write to database
    if results:
        with get_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO convergence_signals
                   (symbol, date, convergence_score, module_count, conviction_level,
                    forensic_blocked, main_signal_score, smartmoney_score,
                    worldview_score, variant_score, research_score, reddit_score,
                    foreign_intel_score, news_displacement_score, alt_data_score,
                    sector_expert_score, pairs_score, ma_score, energy_intel_score,
                    prediction_markets_score, pattern_options_score,
                    estimate_momentum_score, ai_regulatory_score,
                    consensus_blindspots_score,
                    active_modules, narrative)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                results,
            )

    # Summary
    high = sum(1 for r in results if r[4] == "HIGH")
    notable = sum(1 for r in results if r[4] == "NOTABLE")
    watch = sum(1 for r in results if r[4] == "WATCH")
    blocked = sum(1 for r in results if r[4] == "BLOCKED")

    print(f"\n  Results: {len(results)} symbols scored")
    print(f"  HIGH: {high} | NOTABLE: {notable} | WATCH: {watch} | BLOCKED: {blocked}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from tools.db import init_db
    init_db()
    run()
