"""Macro regime scoring engine (-100 to +100).

Druckenmiller's core principle: "Earnings don't move the overall market;
it's the Federal Reserve Board. Focus on central banks and liquidity."

7 sub-indicators, each scored -15 to +15.
"""

from datetime import datetime, timedelta
import pandas as pd
from tools.config import FRED_SERIES, MACRO_REGIME
from tools.db import init_db, upsert_many, query_df


def _get_latest_value(df, series_id):
    """Get the most recent non-null value for a FRED series."""
    sub = df[df["indicator_id"] == series_id].sort_values("date", ascending=False)
    if sub.empty:
        return None
    return sub.iloc[0]["value"]


def _get_value_months_ago(df, series_id, months):
    """Get value from approximately N months ago."""
    cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    sub = df[(df["indicator_id"] == series_id) & (df["date"] <= cutoff)].sort_values("date", ascending=False)
    if sub.empty:
        return None
    return sub.iloc[0]["value"]


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def score_fed_funds(df):
    """Fed Funds direction: cutting=bullish, hiking=bearish."""
    current = _get_latest_value(df, FRED_SERIES["federal_funds"])
    three_mo_ago = _get_value_months_ago(df, FRED_SERIES["federal_funds"], 3)
    six_mo_ago = _get_value_months_ago(df, FRED_SERIES["federal_funds"], 6)

    if current is None:
        return 0

    # Weight recent change more heavily
    change_3m = (current - three_mo_ago) if three_mo_ago else 0
    change_6m = (current - six_mo_ago) if six_mo_ago else 0
    avg_change = (change_3m * 0.6 + change_6m * 0.4)

    # Cutting = negative change = bullish
    # Scale: -1% cut -> +15, +1% hike -> -15
    score = -avg_change * 15
    return _clamp(round(score, 1), -15, 15)


def score_m2_growth(df):
    """M2 YoY growth rate: expansion=bullish."""
    current = _get_latest_value(df, FRED_SERIES["m2"])
    year_ago = _get_value_months_ago(df, FRED_SERIES["m2"], 12)

    if current is None or year_ago is None or year_ago == 0:
        return 0

    yoy_growth = ((current - year_ago) / year_ago) * 100

    # Above +5% -> +15, 0-5% -> proportional, negative -> -15
    if yoy_growth >= 10:
        return 15
    elif yoy_growth >= 5:
        return 15
    elif yoy_growth >= 0:
        return round(yoy_growth * 3, 1)
    elif yoy_growth >= -5:
        return round(yoy_growth * 3, 1)
    else:
        return -15


def score_real_rates(df):
    """Real rates (Fed Funds - CPI YoY): negative=stimulative=bullish."""
    fed = _get_latest_value(df, FRED_SERIES["federal_funds"])
    cpi_now = _get_latest_value(df, FRED_SERIES["cpi"])
    cpi_year_ago = _get_value_months_ago(df, FRED_SERIES["cpi"], 12)

    if fed is None or cpi_now is None or cpi_year_ago is None or cpi_year_ago == 0:
        return 0

    cpi_yoy = ((cpi_now - cpi_year_ago) / cpi_year_ago) * 100
    real_rate = fed - cpi_yoy

    # Deeply negative real rates -> +15 (very stimulative)
    # Positive >2% -> -15 (very restrictive)
    if real_rate <= -3:
        return 15
    elif real_rate <= 0:
        return round(-real_rate * 5, 1)
    elif real_rate <= 2:
        return round(-real_rate * 5, 1)
    else:
        return -15


def score_yield_curve(df):
    """2s10s spread: steep=bullish, inverted=bearish."""
    t10 = _get_latest_value(df, FRED_SERIES["treasury_10y"])
    t2 = _get_latest_value(df, FRED_SERIES["treasury_2y"])

    if t10 is None or t2 is None:
        return 0

    spread = t10 - t2  # In percentage points

    # Spread > 1.5% -> +15, 0 -> 0, < -0.5% -> -15
    if spread >= 1.5:
        return 15
    elif spread >= 0:
        return round(spread * 10, 1)
    elif spread >= -0.5:
        return round(spread * 20, 1)
    else:
        return -15


def score_credit_spreads(df):
    """High Yield OAS: tight=risk-on, wide=stress."""
    oas = _get_latest_value(df, FRED_SERIES["hy_oas"])

    if oas is None:
        return 0

    # OAS in basis points (FRED reports in %)
    # Below 3.5% -> +15, above 6% -> -15
    if oas <= 3.0:
        return 15
    elif oas <= 3.5:
        return 10
    elif oas <= 4.5:
        return 0
    elif oas <= 6.0:
        return round(-((oas - 4.5) / 1.5) * 15, 1)
    else:
        return -15


def score_dxy(price_df):
    """DXY rate of change: weakening dollar=bullish for risk assets."""
    dxy = price_df[price_df["symbol"] == "DX-Y.NYB"].sort_values("date", ascending=False)

    if len(dxy) < 60:
        return 0

    current = dxy.iloc[0]["close"]
    three_mo_ago = dxy.iloc[min(60, len(dxy) - 1)]["close"]

    if three_mo_ago == 0:
        return 0

    pct_change = ((current - three_mo_ago) / three_mo_ago) * 100

    # Weakening (negative change) = bullish for risk assets
    # -5% -> +15, +5% -> -15
    score = -pct_change * 3
    return _clamp(round(score, 1), -15, 15)


def score_vix(price_df):
    """VIX level + term structure: low+contango=bullish."""
    vix = price_df[price_df["symbol"] == "^VIX"].sort_values("date", ascending=False)
    vix3m = price_df[price_df["symbol"] == "^VIX3M"].sort_values("date", ascending=False)

    score = 0.0

    if not vix.empty:
        vix_level = vix.iloc[0]["close"]
        # VIX scoring
        if vix_level < 15:
            score += 10
        elif vix_level < 20:
            score += 5
        elif vix_level < 25:
            score += 0
        elif vix_level < 30:
            score -= 5
        else:
            score -= 10

    # Term structure: contango (VIX < VIX3M) = normal = bullish
    if not vix.empty and not vix3m.empty:
        vix_val = vix.iloc[0]["close"]
        vix3m_val = vix3m.iloc[0]["close"]
        if vix3m_val > 0:
            ratio = vix_val / vix3m_val
            if ratio < 0.85:  # Strong contango
                score += 5
            elif ratio < 1.0:  # Normal contango
                score += 3
            elif ratio > 1.1:  # Backwardation (panic)
                score -= 5

    return _clamp(round(score, 1), -15, 15)


def classify_regime(total_score):
    """Map total macro score to regime label."""
    if total_score >= MACRO_REGIME["strong_risk_on"]:
        return "strong_risk_on"
    elif total_score >= MACRO_REGIME["risk_on"]:
        return "risk_on"
    elif total_score >= MACRO_REGIME["neutral"]:
        return "neutral"
    elif total_score >= MACRO_REGIME["risk_off"]:
        return "risk_off"
    else:
        return "strong_risk_off"


def run():
    """Compute macro regime score."""
    init_db()
    print("Computing macro regime score...")

    macro_df = query_df("SELECT * FROM macro_indicators")
    price_df = query_df(
        "SELECT * FROM price_data WHERE symbol IN ('DX-Y.NYB', '^VIX', '^VIX3M')"
    )

    if macro_df.empty:
        print("  No macro data. Run fetch_macro.py first.")
        return None

    # Score each sub-indicator
    scores = {
        "fed_funds": score_fed_funds(macro_df),
        "m2": score_m2_growth(macro_df),
        "real_rates": score_real_rates(macro_df),
        "yield_curve": score_yield_curve(macro_df),
        "credit_spreads": score_credit_spreads(macro_df),
        "dxy": score_dxy(price_df),
        "vix": score_vix(price_df),
    }

    total = sum(scores.values())
    total = _clamp(total, -100, 100)
    regime = classify_regime(total)

    today = datetime.now().strftime("%Y-%m-%d")
    row = (
        today,
        scores["fed_funds"], scores["m2"], scores["real_rates"],
        scores["yield_curve"], scores["credit_spreads"],
        scores["dxy"], scores["vix"],
        total, regime,
    )
    upsert_many(
        "macro_scores",
        ["date", "fed_funds_score", "m2_score", "real_rates_score",
         "yield_curve_score", "credit_spreads_score", "dxy_score", "vix_score",
         "total_score", "regime"],
        [row]
    )

    print(f"\n  === MACRO REGIME: {regime.upper().replace('_', ' ')} ({total:+.0f}) ===")
    for name, val in scores.items():
        bar = "+" * max(0, int(val)) + "-" * max(0, int(-val))
        print(f"  {name:20s}: {val:+6.1f}  {bar}")
    print(f"  {'TOTAL':20s}: {total:+6.1f}")

    return {"scores": scores, "total": total, "regime": regime}


if __name__ == "__main__":
    run()
