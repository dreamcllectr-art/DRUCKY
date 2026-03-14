"""Economic Indicators Dashboard — processes raw FRED data into dashboard-ready format.

Computes: latest value, MoM/YoY changes, z-scores, trend direction, signal classification.
Also produces a composite Macro Heat Index from leading indicators.
"""

import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from tools.config import ECONOMIC_INDICATORS, INDICATOR_METADATA, HEAT_INDEX_WEIGHTS
from tools.db import init_db, upsert_many, query_df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_series(df, series_id):
    """Extract sorted time series for one indicator."""
    sub = df[df["indicator_id"] == series_id].copy()
    if sub.empty:
        return sub
    sub["date"] = pd.to_datetime(sub["date"])
    sub = sub.sort_values("date").drop_duplicates(subset="date", keep="last")
    return sub


def _value_near_date(series, target_date, tolerance_days=15):
    """Get value closest to target_date within tolerance."""
    if series.empty:
        return None
    mask = (series["date"] >= target_date - timedelta(days=tolerance_days)) & \
           (series["date"] <= target_date + timedelta(days=tolerance_days))
    nearby = series[mask]
    if nearby.empty:
        return None
    # Closest to target
    idx = (nearby["date"] - target_date).abs().idxmin()
    return nearby.loc[idx, "value"]


def _compute_mom(series, latest_val, frequency):
    """Compute month-over-month change (%), frequency-aware."""
    if latest_val is None or series.empty:
        return None
    latest_date = series["date"].max()

    if frequency == "daily":
        lookback = timedelta(days=30)
    elif frequency == "weekly":
        lookback = timedelta(days=28)  # ~4 weeks
    else:  # monthly
        lookback = timedelta(days=35)  # generous window for monthly lag

    prev = _value_near_date(series, latest_date - lookback, tolerance_days=15)
    if prev is None or prev == 0:
        return None
    return round(((latest_val - prev) / abs(prev)) * 100, 2)


def _compute_yoy(series, latest_val):
    """Compute year-over-year change (%)."""
    if latest_val is None or series.empty:
        return None
    latest_date = series["date"].max()
    prev = _value_near_date(series, latest_date - timedelta(days=365), tolerance_days=20)
    if prev is None or prev == 0:
        return None
    return round(((latest_val - prev) / abs(prev)) * 100, 2)


def _compute_zscore(series, min_points=26):
    """Z-score of latest value vs trailing 5 years."""
    if len(series) < min_points:
        return None
    vals = series["value"].values
    mean = np.mean(vals)
    std = np.std(vals)
    if std == 0:
        return 0.0
    return round((vals[-1] - mean) / std, 2)


def _compute_trend(series, frequency):
    """Compare 3-month vs 6-month moving average to determine trend.

    Returns: 'improving', 'stable', or 'deteriorating'
    """
    if len(series) < 10:
        return "stable"

    latest_date = series["date"].max()

    # Get values for recent 3 months and prior 3-6 months
    three_mo_ago = latest_date - timedelta(days=90)
    six_mo_ago = latest_date - timedelta(days=180)

    recent = series[series["date"] >= three_mo_ago]["value"]
    older = series[(series["date"] >= six_mo_ago) & (series["date"] < three_mo_ago)]["value"]

    if recent.empty or older.empty:
        return "stable"

    recent_avg = recent.mean()
    older_avg = older.mean()

    if older_avg == 0:
        return "stable"

    pct_change = ((recent_avg - older_avg) / abs(older_avg)) * 100

    if abs(pct_change) < 1.0:
        return "stable"
    elif pct_change > 0:
        return "improving"
    else:
        return "deteriorating"


def _classify_signal(series_id, trend, zscore, latest_val, meta):
    """Map trend + direction to bullish/neutral/bearish signal."""
    direction = meta.get("bullish_direction", "up")

    # Special cases
    if series_id == "SAHMREALTIME":
        if latest_val is not None:
            if latest_val >= 0.5:
                return "bearish"
            elif latest_val <= 0.3:
                return "bullish"
        return "neutral"

    if series_id == "NFCI":
        # Negative = loose conditions = bullish
        if latest_val is not None:
            if latest_val < -0.3:
                return "bullish"
            elif latest_val > 0.3:
                return "bearish"
        return "neutral"

    if series_id == "STLFSI4":
        # Negative = low stress = bullish
        if latest_val is not None:
            if latest_val < -0.5:
                return "bullish"
            elif latest_val > 0.5:
                return "bearish"
        return "neutral"

    # Inflation indicators: stable ~2% is bullish, >3% bearish, <1% deflationary risk
    if series_id in ("CPILFESL", "PCEPILFE"):
        # These are index levels, not rates — use YoY change via trend
        if direction == "down":
            if trend == "deteriorating":
                return "bullish"  # falling inflation = bullish
            elif trend == "improving":
                return "bearish"  # rising inflation = bearish
        return "neutral"

    # Breakeven / forward inflation: stable is good
    if direction == "stable":
        if zscore is not None:
            if abs(zscore) <= 1.0:
                return "bullish"
            elif abs(zscore) > 2.0:
                return "bearish"
        return "neutral"

    # Standard: map trend to signal based on bullish_direction
    if direction == "up":
        if trend == "improving":
            return "bullish"
        elif trend == "deteriorating":
            return "bearish"
    elif direction == "down":
        if trend == "deteriorating":
            return "bullish"  # falling = good (e.g. jobless claims)
        elif trend == "improving":
            return "bearish"  # rising = bad

    return "neutral"


# ---------------------------------------------------------------------------
# Heat Index
# ---------------------------------------------------------------------------

def _compute_heat_index(indicator_results):
    """Weighted composite of leading indicator z-scores, normalized to -100/+100."""
    weighted_sum = 0.0
    total_weight = 0.0

    for series_id, weight in HEAT_INDEX_WEIGHTS.items():
        result = indicator_results.get(series_id)
        if result is None or result.get("zscore") is None:
            continue

        zscore = result["zscore"]
        direction = INDICATOR_METADATA.get(series_id, {}).get("bullish_direction", "up")

        # Flip z-score for "down is bullish" indicators so positive = bullish
        if direction == "down":
            zscore = -zscore
        elif direction == "stable":
            zscore = -abs(zscore)  # penalize deviation from normal

        # Clamp to ±3 to prevent outliers dominating
        zscore = max(-3.0, min(3.0, zscore))

        # Normalize to -100/+100 range (z=3 -> 100)
        normalized = (zscore / 3.0) * 100

        weighted_sum += normalized * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    """Process all economic indicators into dashboard-ready format."""
    init_db()
    print("Processing economic indicators...")

    # Load all raw data
    macro_df = query_df("SELECT * FROM macro_indicators")
    if macro_df.empty:
        print("  No macro data. Run fetch_macro first.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    dashboard_rows = []
    indicator_results = {}

    for key, series_id in ECONOMIC_INDICATORS.items():
        meta = INDICATOR_METADATA.get(series_id, {})
        if not meta:
            continue

        series = _get_series(macro_df, series_id)
        if series.empty:
            print(f"  {meta['name']} ({series_id}): no data, skipping")
            continue

        latest_val = series.iloc[-1]["value"]
        prev_val = series.iloc[-2]["value"] if len(series) > 1 else None
        frequency = meta.get("frequency", "monthly")

        mom = _compute_mom(series, latest_val, frequency)
        yoy = _compute_yoy(series, latest_val)
        zscore = _compute_zscore(series)
        trend = _compute_trend(series, frequency)
        signal = _classify_signal(series_id, trend, zscore, latest_val, meta)

        dashboard_rows.append((
            series_id, today, meta["category"], meta["name"],
            latest_val, prev_val, mom, yoy, zscore,
            trend, signal, today,
        ))

        indicator_results[series_id] = {
            "zscore": zscore,
            "trend": trend,
            "signal": signal,
            "value": latest_val,
            "name": meta["name"],
        }

        arrow = "↑" if trend == "improving" else ("↓" if trend == "deteriorating" else "→")
        sig_icon = "●" if signal == "bullish" else ("○" if signal == "bearish" else "◐")
        z_str = f"z={zscore:+.1f}" if zscore is not None else "z=n/a"
        print(f"  {sig_icon} {meta['name']:40s} {latest_val:>12,.1f}  {arrow} {trend:14s} {z_str}")

    # Write dashboard rows
    upsert_many(
        "economic_dashboard",
        ["indicator_id", "date", "category", "name", "value", "prev_value",
         "mom_change", "yoy_change", "zscore", "trend", "signal", "last_updated"],
        dashboard_rows,
    )

    # Compute heat index from leading indicators
    heat = _compute_heat_index(indicator_results)

    # Count trends among leading indicators
    leading_results = {k: v for k, v in indicator_results.items()
                       if INDICATOR_METADATA.get(k, {}).get("category") == "leading"}
    improving = sum(1 for v in leading_results.values() if v["trend"] == "improving")
    deteriorating = sum(1 for v in leading_results.values() if v["trend"] == "deteriorating")
    stable = sum(1 for v in leading_results.values() if v["trend"] == "stable")

    detail = json.dumps({
        sid: {"signal": v["signal"], "trend": v["trend"], "zscore": v["zscore"],
              "name": v["name"]}
        for sid, v in leading_results.items()
    })

    upsert_many(
        "economic_heat_index",
        ["date", "heat_index", "improving_count", "deteriorating_count",
         "stable_count", "leading_count", "detail"],
        [(today, heat, improving, deteriorating, stable, len(leading_results), detail)],
    )

    print(f"\n  === MACRO HEAT INDEX: {heat:+.1f} ===")
    print(f"  Leading indicators: {improving} improving, {stable} stable, {deteriorating} deteriorating")
    print(f"  {len(dashboard_rows)} indicators processed.")

    return {
        "heat_index": heat,
        "improving": improving,
        "deteriorating": deteriorating,
        "stable": stable,
        "count": len(dashboard_rows),
    }


if __name__ == "__main__":
    run()
