"""Short Interest Intelligence.

Combines FMP short interest + FINRA short interest data.
Generates squeeze scores and directional signals.
Table: short_interest_scores
"""
import logging
from datetime import date
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS short_interest_scores (
    symbol TEXT, date TEXT,
    short_float_pct REAL, days_to_cover REAL,
    short_interest_change REAL, squeeze_score REAL,
    direction TEXT, score REAL,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _compute_score(short_float_pct, days_to_cover, short_change):
    """
    Score 0-100. High short + covering shorts = bullish (potential squeeze).
    High short + rising shorts = bearish.
    Low short = neutral.
    """
    score = 50.0

    if short_float_pct is None:
        return score, "neutral"

    # High short float with price improvement = squeeze potential
    if short_float_pct > 20:
        score += 15  # High short = potential squeeze fuel
    elif short_float_pct > 10:
        score += 8
    elif short_float_pct < 3:
        score -= 5  # Very low short = already covered, less upside

    # Days to cover (higher = more squeeze pressure if price rises)
    if days_to_cover is not None:
        if days_to_cover > 10:
            score += 12
        elif days_to_cover > 5:
            score += 6

    # Change in short interest (shorts covering = bullish)
    if short_change is not None:
        if short_change < -0.15:  # Shorts covering significantly
            score += 15
        elif short_change < -0.05:
            score += 8
        elif short_change > 0.15:  # Shorts piling on = bearish
            score -= 15
        elif short_change > 0.05:
            score -= 8

    score = max(0, min(100, score))
    if score >= 65:
        direction = "bullish"
    elif score <= 35:
        direction = "bearish"
    else:
        direction = "neutral"

    return round(score, 1), direction


def run():
    _ensure_tables()
    today = date.today().isoformat()

    # Load FMP short interest (most detailed)
    fmp_data = {r["symbol"]: r for r in query(
        """SELECT symbol, short_float_pct, days_to_cover
           FROM fmp_short_interest
           WHERE date = (SELECT MAX(date) FROM fmp_short_interest)"""
    )}

    # Load FINRA short interest
    finra_data = {r["symbol"]: r for r in query(
        """SELECT symbol, short_interest, days_to_cover
           FROM finra_short_interest
           WHERE date = (SELECT MAX(date) FROM finra_short_interest)"""
    )}

    # Load previous period FMP for change calculation
    prev_fmp = {r["symbol"]: r for r in query(
        """SELECT s.symbol, s.short_float_pct FROM fmp_short_interest s
           INNER JOIN (
               SELECT symbol, MIN(date) AS min_date FROM fmp_short_interest
               WHERE date < (SELECT MAX(date) FROM fmp_short_interest)
               AND date >= date('now', '-30 days')
               GROUP BY symbol
           ) m ON s.symbol = m.symbol AND s.date = m.min_date"""
    )}

    all_symbols = set(fmp_data.keys()) | set(finra_data.keys())
    if not all_symbols:
        print("  Short interest: no data available")
        return

    rows = []
    for sym in all_symbols:
        fmp = fmp_data.get(sym, {})
        finra = finra_data.get(sym, {})
        prev = prev_fmp.get(sym, {})

        short_float_pct = fmp.get("short_float_pct") or finra.get("short_vol_ratio", 0) * 100
        days_to_cover = fmp.get("days_to_cover") or finra.get("days_to_cover")

        # Calculate change
        short_change = None
        if prev.get("short_float_pct") and short_float_pct:
            prev_val = prev["short_float_pct"]
            if prev_val > 0:
                short_change = (short_float_pct - prev_val) / prev_val

        score, direction = _compute_score(short_float_pct, days_to_cover, short_change)
        squeeze_score = score if short_float_pct and short_float_pct > 10 else 50.0

        rows.append((sym, today, short_float_pct, days_to_cover,
                     short_change, squeeze_score, direction, score))

    if rows:
        upsert_many("short_interest_scores",
                    ["symbol", "date", "short_float_pct", "days_to_cover",
                     "short_interest_change", "squeeze_score", "direction", "score"],
                    rows)

    bullish = sum(1 for r in rows if r[6] == "bullish")
    print(f"  Short interest: {len(rows)} symbols scored, {bullish} bullish (squeeze candidates)")
