"""Catalyst Engine — Gate 9 logic.

Aggregates catalyst signals from all modules:
- M&A signals, insider cluster buys, earnings catalysts,
- Regulatory catalysts, technical pattern breakouts,
- Analyst upgrades, short squeeze triggers
Table: catalyst_scores
"""
import logging
from datetime import date, timedelta
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS catalyst_scores (
    symbol TEXT, date TEXT,
    catalyst_type TEXT, catalyst_strength REAL,
    days_to_event INTEGER, score REAL,
    catalyst_detail TEXT,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _load_catalysts():
    """Load all catalyst signals from various modules."""
    today = date.today().isoformat()
    lookback_7 = (date.today() - timedelta(days=7)).isoformat()
    lookback_14 = (date.today() - timedelta(days=14)).isoformat()
    lookback_30 = (date.today() - timedelta(days=30)).isoformat()
    horizon_14 = (date.today() + timedelta(days=14)).isoformat()

    catalysts = {}  # symbol -> list of catalyst events

    def add(symbol, catalyst_type, strength, days_to_event, detail=""):
        if symbol not in catalysts:
            catalysts[symbol] = []
        catalysts[symbol].append({
            "type": catalyst_type,
            "strength": strength,
            "days": days_to_event,
            "detail": detail,
        })

    # 1. M&A signals
    for r in query(
        f"SELECT symbol, ma_score, deal_stage FROM ma_signals WHERE ma_score > 50 "
        f"AND date >= '{lookback_7}' AND status = 'active'"
    ):
        add(r["symbol"], "M&A", r["ma_score"], 0, f"Deal stage: {r.get('deal_stage', 'rumor')}")

    # 2. Insider cluster buy
    for r in query(
        f"SELECT symbol, cluster_buy, total_buy_value_30d, cluster_count "
        f"FROM insider_signals WHERE cluster_buy = 1 AND date >= '{lookback_30}'"
    ):
        strength = min(100, 60 + (r.get("cluster_count", 2) - 2) * 10)
        add(r["symbol"], "INSIDER_CLUSTER", strength, 0,
            f"${r.get('total_buy_value_30d', 0):,.0f} cluster buy")

    # 3. Earnings catalyst (upcoming + upward revision)
    for r in query(
        f"SELECT e.symbol, e.date as earn_date, em.em_score "
        f"FROM earnings_calendar e "
        f"LEFT JOIN estimate_momentum_signals em ON e.symbol = em.symbol "
        f"AND em.date >= '{lookback_7}' "
        f"WHERE e.date BETWEEN '{today}' AND '{horizon_14}' "
        f"AND (em.em_score IS NULL OR em.em_score > 50)"
    ):
        earn_date = r.get("earn_date", today)
        try:
            days_to = (date.fromisoformat(earn_date) - date.today()).days
        except (ValueError, TypeError):
            days_to = 7
        strength = 70 + (r.get("em_score", 50) or 50 - 50) * 0.5
        add(r["symbol"], "EARNINGS", round(strength, 0), days_to,
            f"Earnings in {days_to}d, EM score: {r.get('em_score', 'N/A')}")

    # 4. Pattern breakout
    for r in query(
        f"SELECT symbol, pattern_options_score, top_pattern "
        f"FROM pattern_options_signals WHERE pattern_options_score >= 65 "
        f"AND date >= '{lookback_7}' AND status = 'active'"
    ):
        add(r["symbol"], "PATTERN_BREAKOUT", r["pattern_options_score"], 0,
            f"Pattern: {r.get('top_pattern', 'breakout')}")

    # 5. Analyst upgrade
    for r in query(
        f"SELECT symbol, composite_score, consensus_grade "
        f"FROM analyst_scores WHERE composite_score >= 70 "
        f"AND date >= '{lookback_14}'"
    ):
        add(r["symbol"], "ANALYST_UPGRADE", r["composite_score"], 0,
            f"Consensus: {r.get('consensus_grade', 'BUY')}")

    # 6. Short squeeze trigger
    for r in query(
        f"SELECT sis.symbol, sis.short_float_pct, sis.days_to_cover, ts.total_score "
        f"FROM short_interest_scores sis "
        f"LEFT JOIN technical_scores ts ON sis.symbol = ts.symbol "
        f"AND ts.date = (SELECT MAX(date) FROM technical_scores WHERE symbol = sis.symbol) "
        f"WHERE sis.short_float_pct > 15 "
        f"AND sis.date >= '{lookback_7}'"
    ):
        tech_score = r.get("total_score", 0) or 0
        if tech_score > 50:  # Price above 50dma proxy
            strength = min(100, 55 + r["short_float_pct"] * 1.5)
            add(r["symbol"], "SHORT_SQUEEZE", round(strength, 0), 0,
                f"SI: {r['short_float_pct']:.1f}%, DTC: {r.get('days_to_cover', '?')}")

    # 7. Regulatory catalyst (FDA approval etc.)
    for r in query(
        f"SELECT symbol, reg_score, event_count "
        f"FROM regulatory_signals WHERE reg_score > 60 "
        f"AND date >= '{lookback_14}' AND status = 'active'"
    ):
        add(r["symbol"], "REGULATORY", r["reg_score"], 0,
            f"{r.get('event_count', 1)} regulatory events")

    return catalysts


def _score_catalysts(catalyst_list):
    """Aggregate multiple catalysts into a single score (0-100)."""
    if not catalyst_list:
        return 0, "NONE", ""

    # Sort by strength descending
    sorted_cats = sorted(catalyst_list, key=lambda x: x["strength"], reverse=True)
    top = sorted_cats[0]

    # Base score from top catalyst
    base_score = top["strength"]

    # Bonus for multiple catalysts (stacking)
    if len(catalyst_list) > 1:
        secondary_bonus = sum(c["strength"] * 0.1 for c in sorted_cats[1:3])
        base_score = min(100, base_score + secondary_bonus)

    # Proximity bonus (nearer event = higher urgency)
    if top["days"] is not None and 0 < top["days"] <= 7:
        base_score = min(100, base_score + 8)

    # Best catalyst type
    best_type = top["type"]
    best_detail = top["detail"]

    return round(base_score, 1), best_type, best_detail


def run():
    _ensure_tables()
    today = date.today().isoformat()

    catalysts = _load_catalysts()
    if not catalysts:
        print("  Catalyst Engine: no catalysts found")
        return

    rows = []
    for sym, cat_list in catalysts.items():
        score, cat_type, cat_detail = _score_catalysts(cat_list)
        # Use min days_to_event from catalyst list
        days_to = min((c["days"] for c in cat_list if c["days"] is not None), default=0)
        rows.append((sym, today, cat_type, cat_list[0]["strength"],
                     days_to, score, cat_detail[:200] if cat_detail else ""))

    if rows:
        upsert_many("catalyst_scores",
                    ["symbol", "date", "catalyst_type", "catalyst_strength",
                     "days_to_event", "score", "catalyst_detail"],
                    rows)

    high_score = sum(1 for r in rows if r[5] >= 70)
    catalyst_types = {}
    for r in rows:
        catalyst_types[r[2]] = catalyst_types.get(r[2], 0) + 1

    print(f"  Catalyst Engine: {len(rows)} catalysts | {high_score} high-strength (>=70)")
    for ct, cnt in sorted(catalyst_types.items(), key=lambda x: -x[1]):
        print(f"    {ct}: {cnt}")
