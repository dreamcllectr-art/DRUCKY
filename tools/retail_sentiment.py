"""Retail Sentiment Intelligence.

Combines Stocktwits + Reddit signals into unified retail sentiment score.
Applies contrarian adjustments for extremes.
Table: retail_sentiment_scores
"""
import logging
from datetime import date
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS retail_sentiment_scores (
    symbol TEXT, date TEXT,
    bull_pct REAL, bear_pct REAL,
    stocktwits_score REAL, reddit_score REAL,
    volume_surge INTEGER, contrarian_flag INTEGER,
    score REAL,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _contrarian_adjust(bull_pct, score, reddit_score, volume_surge):
    """
    Apply contrarian logic:
    - Extreme bullishness (>80%) = contrarian warning → reduce score
    - Extreme bearishness (<20%) with institutional buying = contrarian buy
    - Moderate bullishness (55-70%) + volume surge = momentum confirmation
    """
    adjusted = score
    contrarian_flag = 0

    if bull_pct is not None:
        if bull_pct > 80:
            # Extreme greed — contrarian warning
            adjusted = max(20, score - 25)
            contrarian_flag = -1  # Warning
        elif bull_pct < 20:
            # Extreme fear — potential contrarian buy
            adjusted = min(75, score + 20)
            contrarian_flag = 1  # Opportunity flag
        elif 55 <= bull_pct <= 70 and volume_surge:
            # Sweet spot: moderate bullish + volume surge
            adjusted = min(85, score + 10)
            contrarian_flag = 0

    return round(max(0, min(100, adjusted)), 1), contrarian_flag


def run():
    _ensure_tables()
    today = date.today().isoformat()

    # Load Stocktwits data
    st_data = {r["symbol"]: r for r in query(
        """SELECT symbol, bull_pct, bear_pct, msg_count, sentiment_score
           FROM stocktwits_sentiment
           WHERE date = (SELECT MAX(date) FROM stocktwits_sentiment)"""
    )}

    # Load Reddit signals
    reddit_data = {}
    rows_raw = query(
        """SELECT symbol, AVG(sentiment) as avg_sent, AVG(score) as avg_score,
                  SUM(mention_count) as total_mentions
           FROM reddit_signals
           WHERE date >= date('now', '-3 days')
           GROUP BY symbol"""
    )
    for r in rows_raw:
        reddit_data[r["symbol"]] = r

    # Compute average msg volume for surge detection
    avg_volume_rows = query(
        """SELECT symbol, AVG(msg_count) as avg_msgs FROM stocktwits_sentiment
           WHERE date >= date('now', '-7 days') GROUP BY symbol"""
    )
    avg_volume = {r["symbol"]: r["avg_msgs"] for r in avg_volume_rows}

    all_symbols = set(st_data.keys()) | set(reddit_data.keys())
    if not all_symbols:
        print("  Retail sentiment: no data available")
        return

    rows = []
    for sym in all_symbols:
        st = st_data.get(sym, {})
        reddit = reddit_data.get(sym, {})

        bull_pct = st.get("bull_pct")
        bear_pct = st.get("bear_pct")
        st_score = st.get("sentiment_score", 50)
        reddit_score = max(0, min(100, (reddit.get("avg_sent", 0) + 1) * 50))

        # Volume surge: current volume > 2x average
        msg_count = st.get("msg_count", 0) or 0
        avg_msgs = avg_volume.get(sym, 1) or 1
        volume_surge = 1 if msg_count > avg_msgs * 2 else 0

        # Blend Stocktwits + Reddit (70/30)
        blended = st_score * 0.70 + reddit_score * 0.30

        # Apply contrarian adjustment
        adjusted_score, contrarian_flag = _contrarian_adjust(
            bull_pct, blended, reddit_score, volume_surge
        )

        rows.append((sym, today, bull_pct, bear_pct, st_score,
                     reddit_score, volume_surge, contrarian_flag, adjusted_score))

    if rows:
        upsert_many("retail_sentiment_scores",
                    ["symbol", "date", "bull_pct", "bear_pct", "stocktwits_score",
                     "reddit_score", "volume_surge", "contrarian_flag", "score"],
                    rows)

    contrarian_warns = sum(1 for r in rows if r[7] == -1)
    contrarian_opps = sum(1 for r in rows if r[7] == 1)
    print(f"  Retail sentiment: {len(rows)} symbols | {contrarian_warns} contrarian warnings, "
          f"{contrarian_opps} contrarian opportunities")
