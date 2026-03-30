"""Data freshness gates for pipeline modules.

Stale or missing data returns None (absent from convergence denominator),
not score=50 (false neutral that dilutes high-conviction signals).

Usage:
    from tools.utils.data_quality import check_data_freshness, FRESHNESS_CONFIG

    result = check_data_freshness("stocktwits_sentiment", "date", max_age_days=1)
    if not result["fresh"]:
        log_module_error(module="stocktwits", phase="freshness",
                         exc=ValueError(f"Stale: {result['age_days']}d"), severity="WARNING")
        return None
"""

from datetime import date, datetime, timedelta

from tools.db import query

# Per-module staleness thresholds (days). Tune as data velocity warrants.
FRESHNESS_CONFIG: dict[str, int] = {
    "prices":        1,
    "fundamentals":  7,
    "fmp_v2":        1,
    "stocktwits":    1,
    "alpha_vantage": 1,
    "edgar":         7,
    "finnhub_news":  1,
    "alt_data":      3,
    "macro_fred":    3,
}


def check_data_freshness(table: str, date_col: str,
                         max_age_days: int) -> dict:
    """Check whether a DB table has data within max_age_days.

    Args:
        table:        DB table name to check.
        date_col:     Name of the date column (TEXT 'YYYY-MM-DD' or DATE).
        max_age_days: Maximum acceptable age in calendar days.

    Returns:
        {
          "fresh":    bool   — True if data exists and is within threshold,
          "age_days": int    — days since latest row (999 if table empty),
          "latest":   str    — latest date as 'YYYY-MM-DD' or None,
        }
    """
    try:
        rows = query(f"SELECT MAX({date_col}) AS latest FROM {table}")
        latest_str: str | None = rows[0]["latest"] if rows else None
    except Exception:
        return {"fresh": False, "age_days": 999, "latest": None}

    if not latest_str:
        return {"fresh": False, "age_days": 999, "latest": None}

    try:
        latest = datetime.strptime(latest_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return {"fresh": False, "age_days": 999, "latest": latest_str}

    age_days = (date.today() - latest).days
    return {
        "fresh":    age_days <= max_age_days,
        "age_days": age_days,
        "latest":   latest_str[:10],
    }
