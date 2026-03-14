"""Energy Intelligence Scoring — supply-demand signals for energy tickers.

Computes energy_intel_score (0-100) per energy ticker based on:
  1. Inventory signal (30%): EIA stocks vs 5yr seasonal, Cushing premium
  2. Production signal (20%): US production trend + JODI OPEC compliance
  3. Demand signal (20%): Refinery util + product supplied (implied demand)
  4. Trade flow signal (15%): PADD flow anomalies, import concentration
  5. Global balance signal (15%): JODI supply-demand, Comtrade structural trends

Ticker differentiation:
  - Upstream E&Ps: raw score (tracks crude directly)
  - Downstream refiners: inverse-crude + demand blend (high crude hurts margins)
  - Midstream: volume-driven (production + flow)
  - OFS: activity proxy (score + production trend)
  - LNG: nat gas signal + trade flow

Pipeline phase: 2.7 (after energy_intel_data.py ingestion)
Convergence: 13th module at 5% weight
"""

import sys
import logging
from datetime import date, datetime
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import (
    ENERGY_SCORE_WEIGHTS,
    ENERGY_CUSHING_PREMIUM,
    ENERGY_INTEL_TICKERS,
    ENERGY_JODI_MAX_LAG_DAYS,
    ENERGY_JODI_BLEND_WEIGHT,
    GEM_BLEND_WEIGHT,
)
from tools.db import init_db, get_conn, query

logger = logging.getLogger(__name__)


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


# ─────────────────────────────────────────────────────────
# Sub-Signal 1: Inventory (30%)
# ─────────────────────────────────────────────────────────

def _compute_inventory_signal() -> float:
    """Score 0-100 based on EIA inventory levels vs seasonal norms.

    Draws = bullish (score > 50), builds = bearish (score < 50).
    """
    today = date.today()
    current_week = today.isocalendar()[1]

    # Check key inventory series
    series_checks = [
        ("PET.WCESTUS1.W",  "macro_indicators",   "indicator_id", 1.0),    # US crude
        ("PET.WGTSTUS1.W",  "macro_indicators",   "indicator_id", 0.6),    # Gasoline
        ("PET.WDISTUS1.W",  "macro_indicators",   "indicator_id", 0.5),    # Distillate
        ("PET.WCESTP21.W",  "energy_eia_enhanced", "series_id",   ENERGY_CUSHING_PREMIUM),  # Cushing
    ]

    signals = []
    weights = []

    for series_id, table, id_col, weight in series_checks:
        # Latest value
        rows = query(f"""
            SELECT value FROM {table}
            WHERE {id_col} = ?
            ORDER BY date DESC LIMIT 1
        """, [series_id])
        if not rows:
            continue

        current_val = rows[0]["value"]

        # Seasonal norm
        norms = query("""
            SELECT avg_value, std_value FROM energy_seasonal_norms
            WHERE series_id = ? AND week_of_year = ?
        """, [series_id, current_week])

        if not norms or not norms[0]["std_value"] or norms[0]["std_value"] == 0:
            continue

        avg = norms[0]["avg_value"]
        std = norms[0]["std_value"]
        zscore = (current_val - avg) / std

        # Negative z-score = below seasonal = tighter supply = bullish
        # Map z-score to 0-100: z=-3 → 100 (very bullish), z=+3 → 0 (very bearish)
        signal = _clamp(50 - zscore * 16.67)
        signals.append(signal)
        weights.append(weight)

    if not signals:
        return 50.0  # No data → neutral

    weighted_sum = sum(s * w for s, w in zip(signals, weights))
    weight_sum = sum(weights)
    return weighted_sum / weight_sum


# ─────────────────────────────────────────────────────────
# Sub-Signal 2: Production (20%)
# ─────────────────────────────────────────────────────────

def _compute_production_signal() -> float:
    """Score 0-100 based on US production trend.

    Rising production = bearish (more supply), falling = bullish.
    """
    # US crude production WoW change from macro_indicators
    rows = query("""
        SELECT value FROM macro_indicators
        WHERE indicator_id = 'PET.WCRFPUS2.W'
        ORDER BY date DESC LIMIT 13
    """)

    if len(rows) < 5:
        return 50.0

    current = rows[0]["value"]
    four_weeks_ago = rows[4]["value"] if len(rows) > 4 else current
    twelve_weeks_ago = rows[12]["value"] if len(rows) > 12 else current

    # 4-week production trend
    short_change_pct = ((current - four_weeks_ago) / four_weeks_ago * 100) if four_weeks_ago else 0
    # 12-week production trend
    long_change_pct = ((current - twelve_weeks_ago) / twelve_weeks_ago * 100) if twelve_weeks_ago else 0

    # Rising production = bearish: negative score
    # Typical range: -2% to +2% per quarter
    short_signal = _clamp(50 - short_change_pct * 25)  # 1% rise → 25pt drop
    long_signal = _clamp(50 - long_change_pct * 12.5)

    # Blend short and long term
    return short_signal * 0.6 + long_signal * 0.4


# ─────────────────────────────────────────────────────────
# Sub-Signal 3: Demand (20%)
# ─────────────────────────────────────────────────────────

def _compute_demand_signal() -> float:
    """Score 0-100 based on refinery utilization + product supplied.

    High refinery util = strong demand pull = bullish.
    """
    today = date.today()
    current_week = today.isocalendar()[1]
    signals = []

    # Refinery utilization vs seasonal
    util_rows = query("""
        SELECT value FROM macro_indicators
        WHERE indicator_id = 'PET.WPULEUS3.W'
        ORDER BY date DESC LIMIT 1
    """)

    util_norms = query("""
        SELECT avg_value, std_value FROM energy_seasonal_norms
        WHERE series_id = 'PET.WPULEUS3.W' AND week_of_year = ?
    """, [current_week])

    if util_rows and util_norms and util_norms[0]["std_value"]:
        util_val = util_rows[0]["value"]
        util_avg = util_norms[0]["avg_value"]
        util_std = util_norms[0]["std_value"]
        util_z = (util_val - util_avg) / util_std
        # Above seasonal util = strong demand = bullish
        signals.append(_clamp(50 + util_z * 16.67))

    # Product supplied (implied demand) from enhanced EIA
    for series_id in ["PET.WRPUPUS2.W", "PET.WGFUPUS2.W", "PET.WDIUPUS2.W"]:
        demand_rows = query("""
            SELECT value FROM energy_eia_enhanced
            WHERE series_id = ?
            ORDER BY date DESC LIMIT 5
        """, [series_id])

        demand_norms = query("""
            SELECT avg_value, std_value FROM energy_seasonal_norms
            WHERE series_id = ? AND week_of_year = ?
        """, [series_id, current_week])

        if demand_rows and demand_norms and demand_norms[0]["std_value"]:
            val = demand_rows[0]["value"]
            avg = demand_norms[0]["avg_value"]
            std = demand_norms[0]["std_value"]
            z = (val - avg) / std
            signals.append(_clamp(50 + z * 16.67))

    if not signals:
        return 50.0

    return sum(signals) / len(signals)


# ─────────────────────────────────────────────────────────
# Sub-Signal 4: Trade Flows (15%)
# ─────────────────────────────────────────────────────────

def _compute_trade_flow_signal() -> float:
    """Score 0-100 based on PADD flow patterns and import concentration.

    Falling imports + rising exports = tighter domestic supply = bullish.
    Concentration risk (single-source dependency) = bearish.
    """
    signals = []

    # US crude imports trend (from existing macro_indicators)
    import_rows = query("""
        SELECT value FROM macro_indicators
        WHERE indicator_id = 'PET.WCRRIUS2.W'
        ORDER BY date DESC LIMIT 5
    """)
    export_rows = query("""
        SELECT value FROM macro_indicators
        WHERE indicator_id = 'PET.MCREXUS2.W'
        ORDER BY date DESC LIMIT 5
    """)

    if import_rows and len(import_rows) >= 2:
        imp_current = import_rows[0]["value"]
        imp_prev = import_rows[1]["value"]
        imp_change = (imp_current - imp_prev) / imp_prev * 100 if imp_prev else 0
        # Falling imports = tighter supply = bullish
        signals.append(_clamp(50 - imp_change * 15))

    if export_rows and len(export_rows) >= 2:
        exp_current = export_rows[0]["value"]
        exp_prev = export_rows[1]["value"]
        exp_change = (exp_current - exp_prev) / exp_prev * 100 if exp_prev else 0
        # Rising exports = more demand for US crude = bullish
        signals.append(_clamp(50 + exp_change * 15))

    # PADD district anomalies — check if any PADD has a severe z-score
    anomalies = query("""
        SELECT zscore, severity FROM energy_supply_anomalies
        WHERE anomaly_type IN ('inventory_deficit', 'inventory_surplus')
        AND date >= date('now', '-7 days')
        AND series_id LIKE 'PET.WCESTP%'
        AND status = 'active'
    """)

    for a in anomalies:
        z = a["zscore"] or 0
        # Deficit in a PADD = tighter regional supply = bullish
        signals.append(_clamp(50 - z * 12))

    # Days of supply from enhanced EIA
    dos_rows = query("""
        SELECT value FROM energy_eia_enhanced
        WHERE series_id = 'PET.WCSDSUS2.W'
        ORDER BY date DESC LIMIT 1
    """)
    dos_norms = query("""
        SELECT avg_value, std_value FROM energy_seasonal_norms
        WHERE series_id = 'PET.WCSDSUS2.W'
        AND week_of_year = ?
    """, [date.today().isocalendar()[1]])

    if dos_rows and dos_norms and dos_norms[0]["std_value"]:
        dos_z = (dos_rows[0]["value"] - dos_norms[0]["avg_value"]) / dos_norms[0]["std_value"]
        # Below-average days of supply = bullish
        signals.append(_clamp(50 - dos_z * 16.67))

    if not signals:
        return 50.0

    return sum(signals) / len(signals)


# ─────────────────────────────────────────────────────────
# Sub-Signal 5: Global Balance (15%)
# ─────────────────────────────────────────────────────────

def _compute_global_balance() -> float:
    """Score 0-100 based on JODI global supply-demand and Comtrade trends.

    Global deficit (demand > supply) = bullish.
    Apply staleness discount for lagged data.
    """
    # JODI: sum production vs sum demand for key countries
    jodi_prod = query("""
        SELECT SUM(value) as total FROM energy_jodi_data
        WHERE indicator = 'production'
        AND date = (SELECT MAX(date) FROM energy_jodi_data WHERE indicator = 'production')
    """)
    jodi_demand = query("""
        SELECT SUM(value) as total FROM energy_jodi_data
        WHERE indicator = 'demand'
        AND date = (SELECT MAX(date) FROM energy_jodi_data WHERE indicator = 'demand')
    """)

    jodi_signal = 50.0  # neutral default
    if jodi_prod and jodi_demand and jodi_prod[0]["total"] and jodi_demand[0]["total"]:
        prod_total = jodi_prod[0]["total"]
        demand_total = jodi_demand[0]["total"]
        surplus_kbd = prod_total - demand_total  # positive = oversupply

        # Typical range: ±2000 kbd swing
        jodi_signal = _clamp(50 - surplus_kbd / 2000 * 50)

        # Staleness discount
        latest_date = query("""
            SELECT MAX(date) as d FROM energy_jodi_data WHERE indicator = 'production'
        """)
        if latest_date and latest_date[0]["d"]:
            try:
                jodi_date = datetime.strptime(latest_date[0]["d"], "%Y-%m")
                days_stale = (datetime.now() - jodi_date).days
                freshness = max(0.3, 1.0 - days_stale / ENERGY_JODI_MAX_LAG_DAYS)
                # Discount by moving toward neutral
                jodi_signal = 50 + (jodi_signal - 50) * freshness
            except ValueError:
                pass

    # Comtrade structural trends — check if crude imports are trending up/down
    comtrade_rows = query("""
        SELECT period, SUM(value_usd) as total
        FROM energy_trade_flows
        WHERE commodity_code = '2709'
        AND trade_flow LIKE '%Import%'
        GROUP BY period
        ORDER BY period DESC
        LIMIT 4
    """)

    comtrade_signal = 50.0
    if len(comtrade_rows) >= 2:
        recent = comtrade_rows[0]["total"] or 0
        prior = comtrade_rows[1]["total"] or 0
        if prior > 0:
            change_pct = (recent - prior) / prior * 100
            # Rising global crude imports = growing demand = bullish
            comtrade_signal = _clamp(50 + change_pct * 5)

    # Blend JODI (primary) and Comtrade (structural)
    return jodi_signal * 0.7 + comtrade_signal * 0.3


# ─────────────────────────────────────────────────────────
# Nat Gas Signal (for LNG tickers)
# ─────────────────────────────────────────────────────────

def _compute_natgas_signal() -> float:
    """Score for nat gas based on storage vs seasonal."""
    today = date.today()
    current_week = today.isocalendar()[1]

    rows = query("""
        SELECT value FROM macro_indicators
        WHERE indicator_id = 'NG.NW2_EPG0_SWO_R48_BCF.W'
        ORDER BY date DESC LIMIT 1
    """)
    norms = query("""
        SELECT avg_value, std_value FROM energy_seasonal_norms
        WHERE series_id = 'NG.NW2_EPG0_SWO_R48_BCF.W' AND week_of_year = ?
    """, [current_week])

    if not rows or not norms or not norms[0]["std_value"]:
        return 50.0

    z = (rows[0]["value"] - norms[0]["avg_value"]) / norms[0]["std_value"]
    # Below-seasonal storage = bullish for nat gas prices
    return _clamp(50 - z * 16.67)


# ─────────────────────────────────────────────────────────
# Ticker Differentiation
# ─────────────────────────────────────────────────────────

def _score_ticker(
    symbol: str,
    category: str,
    inv: float,
    prod: float,
    demand: float,
    flows: float,
    balance: float,
    natgas: float,
) -> tuple[float, str]:
    """Apply category-specific scoring. Returns (score, narrative)."""

    # Base composite (used for upstream)
    w = ENERGY_SCORE_WEIGHTS
    base_score = (
        inv * w["inventory"]
        + prod * w["production"]
        + demand * w["demand"]
        + flows * w["trade_flows"]
        + balance * w["global_balance"]
    )

    if category == "upstream":
        score = base_score
        narrative = (
            f"Upstream E&P: inventory={inv:.0f}, production={prod:.0f}, "
            f"demand={demand:.0f}, flows={flows:.0f}, global={balance:.0f}"
        )

    elif category == "downstream":
        # High crude prices hurt refiner margins (unless demand is strong)
        # Invert the crude-bullish signal, emphasize demand
        score = 0.4 * (100 - base_score) + 0.6 * demand
        narrative = (
            f"Refiner: margin pressure={(100-base_score):.0f}, "
            f"demand pull={demand:.0f} (blended {score:.0f})"
        )

    elif category == "midstream":
        # Volume-driven: production levels + flow volumes
        score = 0.5 * prod + 0.5 * flows
        # Midstream benefits from HIGH production (more throughput)
        # So invert the production signal (which is bearish for crude price)
        score = 0.5 * (100 - prod) + 0.5 * flows
        narrative = f"Midstream: volume proxy (prod trend={100-prod:.0f}, flows={flows:.0f})"

    elif category == "ofs":
        # OFS tracks drilling activity → production trend
        # High production = high activity = bullish for OFS
        score = 0.5 * (100 - prod) + 0.3 * base_score + 0.2 * demand
        narrative = f"OFS: activity={(100-prod):.0f}, crude={base_score:.0f}, demand={demand:.0f}"

    elif category == "lng":
        # LNG driven by nat gas fundamentals + trade flows
        score = 0.6 * natgas + 0.4 * flows
        narrative = f"LNG: nat gas={natgas:.0f}, trade flows={flows:.0f}"

    else:
        score = base_score
        narrative = f"Energy: composite={base_score:.0f}"

    return _clamp(score), narrative


# ─────────────────────────────────────────────────────────
# Public API for Convergence Engine
# ─────────────────────────────────────────────────────────

def compute_energy_intel_scores() -> dict[str, float]:
    """Called by convergence_engine.py to get latest scores per symbol."""
    rows = query("""
        SELECT symbol, MAX(energy_intel_score) as score
        FROM energy_intel_signals
        WHERE date >= date('now', '-7 days')
        GROUP BY symbol
    """)
    return {r["symbol"]: r["score"] for r in rows if r["score"]}


# ─────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────

def run():
    """Main entry point — called by daily_pipeline.py Phase 2.7."""
    init_db()

    print("\n  === ENERGY INTELLIGENCE SCORING ===")

    # Compute sub-signals (market-wide, not per-ticker)
    inv = _compute_inventory_signal()
    prod = _compute_production_signal()
    demand = _compute_demand_signal()
    flows = _compute_trade_flow_signal()
    balance = _compute_global_balance()
    natgas = _compute_natgas_signal()

    print(f"  Sub-signals: inventory={inv:.1f}, production={prod:.1f}, "
          f"demand={demand:.1f}, flows={flows:.1f}, "
          f"global_balance={balance:.1f}, natgas={natgas:.1f}")

    # Load global energy market adjustments (gem_score)
    gem_scores = {}
    try:
        from tools.global_energy_markets import compute_gem_adjustments
        gem_scores = compute_gem_adjustments()
        if gem_scores:
            print(f"  Global energy adjustment: {len(gem_scores)} tickers with gem_scores")
    except Exception as e:
        logger.warning(f"  Global energy adjustments unavailable: {e}")

    # Score each energy ticker with category differentiation
    today_str = date.today().isoformat()
    results = []

    for category, tickers in ENERGY_INTEL_TICKERS.items():
        for symbol in tickers:
            score, narrative = _score_ticker(
                symbol, category, inv, prod, demand, flows, balance, natgas
            )

            # Blend with global energy market score if available
            gem = gem_scores.get(symbol)
            if gem is not None:
                original = score
                score = score * (1 - GEM_BLEND_WEIGHT) + gem * GEM_BLEND_WEIGHT
                score = _clamp(score)
                narrative += f" | GEM={gem:.0f} (blend {original:.0f}→{score:.0f})"

            results.append((
                symbol, today_str, score,
                inv, prod, demand, flows, balance,
                category, narrative,
            ))

    # Write to DB
    if results:
        with get_conn() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO energy_intel_signals
                (symbol, date, energy_intel_score,
                 inventory_signal, production_signal, demand_signal,
                 trade_flow_signal, global_balance_signal,
                 ticker_category, narrative)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, results)

    # Summary
    scores = [r[2] for r in results]
    if scores:
        avg_score = sum(scores) / len(scores)
        above_50 = sum(1 for s in scores if s >= 50)
        print(f"\n  Results: {len(results)} tickers scored")
        print(f"  Avg score: {avg_score:.1f} | Bullish (>=50): {above_50} | "
              f"Bearish (<50): {len(scores) - above_50}")

        # Top signals
        top = sorted(results, key=lambda r: r[2], reverse=True)[:5]
        print("  Top 5:")
        for r in top:
            print(f"    {r[0]:6s} ({r[8]:10s}): {r[2]:5.1f} — {r[9]}")

    print("  === ENERGY SCORING COMPLETE ===\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
