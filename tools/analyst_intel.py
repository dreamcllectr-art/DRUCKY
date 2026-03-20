"""Analyst Intelligence — unified analyst score.

Reads FMP analyst data + existing Finnhub data.
Weights: consensus grade + price target upside + revision direction.
Table: analyst_scores
"""
import logging
from datetime import date
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS analyst_scores (
    symbol TEXT, date TEXT,
    consensus_grade TEXT, pt_upside_pct REAL,
    analyst_count INTEGER, strong_buy_pct REAL,
    sell_pct REAL, revision_score REAL,
    composite_score REAL,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _compute_consensus_score(strong_buy, buy, hold, sell, strong_sell, total):
    """Convert analyst distribution to 0-100 score."""
    if not total or total == 0:
        return 50.0
    # Weighted sum: strong_buy=5, buy=4, hold=3, sell=2, strong_sell=1
    weighted = (
        (strong_buy or 0) * 5 +
        (buy or 0) * 4 +
        (hold or 0) * 3 +
        (sell or 0) * 2 +
        (strong_sell or 0) * 1
    )
    max_possible = total * 5
    if max_possible == 0:
        return 50.0
    return round((weighted / max_possible) * 100, 1)


def _compute_upside_score(pt_upside_pct):
    """Score based on price target upside vs current price."""
    if pt_upside_pct is None:
        return 50.0
    if pt_upside_pct > 30:
        return 85.0
    elif pt_upside_pct > 15:
        return 70.0
    elif pt_upside_pct > 5:
        return 60.0
    elif pt_upside_pct > -5:
        return 45.0
    elif pt_upside_pct > -15:
        return 30.0
    return 15.0


def run():
    _ensure_tables()
    today = date.today().isoformat()

    # Load FMP analyst data
    fmp_data = {r["symbol"]: r for r in query(
        """SELECT symbol, analyst_count, strong_buy, buy, hold, sell, strong_sell,
                  consensus, price_target
           FROM fmp_analyst_data
           WHERE date = (SELECT MAX(date) FROM fmp_analyst_data)"""
    )}

    # Load current prices for upside calculation
    prices = {r["symbol"]: r["close"] for r in query(
        """SELECT p.symbol, p.close FROM price_data p
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM price_data GROUP BY symbol) m
           ON p.symbol = m.symbol AND p.date = m.mx"""
    )}

    # Combine with Finnhub analyst data (consensus_blindspot_signals has some)
    finnhub_data = {r["symbol"]: r for r in query(
        """SELECT symbol, analyst_buy_pct, analyst_sell_pct, analyst_target_upside
           FROM consensus_blindspot_signals
           WHERE date = (SELECT MAX(date) FROM consensus_blindspot_signals)
           AND analyst_buy_pct IS NOT NULL"""
    )}

    all_symbols = set(fmp_data.keys()) | set(finnhub_data.keys())
    if not all_symbols:
        print("  Analyst Intel: no data available")
        return

    rows = []
    for sym in all_symbols:
        fmp = fmp_data.get(sym, {})
        finnhub = finnhub_data.get(sym, {})
        current_price = prices.get(sym)

        total = fmp.get("analyst_count", 0) or 0
        strong_buy = fmp.get("strong_buy", 0) or 0
        buy = fmp.get("buy", 0) or 0
        hold = fmp.get("hold", 0) or 0
        sell = fmp.get("sell", 0) or 0
        strong_sell = fmp.get("strong_sell", 0) or 0

        # If we have Finnhub data but not FMP, synthesize from percentages
        if total == 0 and finnhub:
            buy_pct = finnhub.get("analyst_buy_pct", 50) or 50
            sell_pct = finnhub.get("analyst_sell_pct", 20) or 20
            total = 10  # Synthetic count
            buy = round(total * buy_pct / 100)
            sell = round(total * sell_pct / 100)
            hold = total - buy - sell

        consensus_score = _compute_consensus_score(
            strong_buy, buy, hold, sell, strong_sell, total
        )

        # Price target upside
        pt = fmp.get("price_target")
        pt_upside = None
        if pt and current_price and current_price > 0:
            pt_upside = ((pt / current_price) - 1) * 100
        elif finnhub.get("analyst_target_upside") is not None:
            pt_upside = finnhub["analyst_target_upside"] * 100

        upside_score = _compute_upside_score(pt_upside)

        # Strong buy percentage
        strong_buy_pct = (strong_buy / total * 100) if total > 0 else 0
        sell_pct_val = ((sell + strong_sell) / total * 100) if total > 0 else 0

        # Consensus grade text
        if consensus_score >= 75:
            grade = "STRONG_BUY"
        elif consensus_score >= 60:
            grade = "BUY"
        elif consensus_score >= 45:
            grade = "HOLD"
        elif consensus_score >= 30:
            grade = "SELL"
        else:
            grade = "STRONG_SELL"

        # Composite: 50% consensus, 35% upside, 15% analyst count bonus
        count_bonus = min(10, total / 5) if total else 0  # More analysts = more reliable
        composite = consensus_score * 0.50 + upside_score * 0.35 + 50 * 0.15 + count_bonus

        rows.append((sym, today, grade, round(pt_upside, 1) if pt_upside else None,
                     total, round(strong_buy_pct, 1), round(sell_pct_val, 1),
                     None, round(min(100, composite), 1)))

    if rows:
        upsert_many("analyst_scores",
                    ["symbol", "date", "consensus_grade", "pt_upside_pct",
                     "analyst_count", "strong_buy_pct", "sell_pct",
                     "revision_score", "composite_score"],
                    rows)

    strong_buys = sum(1 for r in rows if r[2] == "STRONG_BUY")
    print(f"  Analyst Intel: {len(rows)} symbols scored, {strong_buys} STRONG_BUY consensus")
