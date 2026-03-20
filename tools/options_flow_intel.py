"""Options Flow Intelligence.

Sources: existing pattern_options.py + options_intel data.
Detects unusual call/put activity, IV crush, dealer hedging flows.
Table: options_flow_scores
"""
import logging
from datetime import date
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS options_flow_scores (
    symbol TEXT, date TEXT,
    call_put_ratio REAL, iv_rank REAL,
    unusual_activity_flag INTEGER, flow_direction TEXT,
    dealer_regime TEXT, score REAL,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _compute_flow_score(cp_ratio, iv_rank, unusual_flag, dealer_regime, unusual_dir):
    """
    Score 0-100 from options flow signals.
    - Unusual call buying (cp > 2 std dev) = bullish
    - Put surge = potential reversal/fear
    - IV rank high + unusual activity = big move expected
    """
    score = 50.0
    direction = "neutral"

    # Call/put ratio signal
    if cp_ratio is not None:
        if cp_ratio > 2.0:  # Heavy call buying
            score += 20
            direction = "bullish"
        elif cp_ratio > 1.5:
            score += 12
            direction = "bullish"
        elif cp_ratio < 0.5:  # Heavy put buying (fear or hedge)
            score -= 15
            direction = "bearish"
        elif cp_ratio < 0.7:
            score -= 8
            direction = "bearish"

    # Unusual activity flag
    if unusual_flag:
        if direction == "bullish":
            score += 10
        elif direction == "bearish":
            score -= 10

    # IV rank: high IV rank + unusual bullish = conviction
    if iv_rank is not None:
        if iv_rank > 80 and direction == "bullish":
            score += 8  # High conviction options bet
        elif iv_rank > 80:
            score += 5  # Expected move = catalyst approaching

    # Dealer regime
    if dealer_regime:
        if "long_gamma" in dealer_regime.lower():
            score += 5  # Dealers long gamma = natural stabilizer
        elif "short_gamma" in dealer_regime.lower():
            score -= 5  # Short gamma = volatility amplifier

    # Unusual direction bias override
    if unusual_dir == "bullish":
        score = max(score, 60)
    elif unusual_dir == "bearish":
        score = min(score, 40)

    return round(max(0, min(100, score)), 1), direction


def run():
    _ensure_tables()
    today = date.today().isoformat()

    # Load existing options intelligence
    options_data = {r["symbol"]: r for r in query(
        """SELECT symbol, put_call_ratio, iv_rank, unusual_volume,
                  unusual_direction_bias, dealer_regime, options_score
           FROM options_intel
           WHERE date = (SELECT MAX(date) FROM options_intel)"""
    )}

    # Also load pattern_options signals for additional context
    pattern_data = {r["symbol"]: r for r in query(
        """SELECT symbol, options_score, pattern_options_score
           FROM pattern_options_signals
           WHERE date = (SELECT MAX(date) FROM pattern_options_signals)
           AND status = 'active'"""
    )}

    all_symbols = set(options_data.keys()) | set(pattern_data.keys())
    if not all_symbols:
        print("  Options Flow: no data available")
        return

    rows = []
    for sym in all_symbols:
        opt = options_data.get(sym, {})
        pat = pattern_data.get(sym, {})

        cp_ratio = opt.get("put_call_ratio")
        iv_rank = opt.get("iv_rank")
        unusual_flag = opt.get("unusual_volume", 0) or 0
        dealer_regime = opt.get("dealer_regime", "")
        unusual_dir = opt.get("unusual_direction_bias", "")

        # If we have pattern_options score, blend it in
        if pat.get("options_score"):
            base_options_score = pat["options_score"]
        else:
            base_options_score = opt.get("options_score", 50) or 50

        flow_score, flow_direction = _compute_flow_score(
            cp_ratio, iv_rank, unusual_flag, dealer_regime, unusual_dir
        )

        # Blend with pattern_options score (60/40)
        final_score = flow_score * 0.60 + base_options_score * 0.40

        rows.append((sym, today, cp_ratio, iv_rank, unusual_flag,
                     flow_direction, dealer_regime, round(final_score, 1)))

    if rows:
        upsert_many("options_flow_scores",
                    ["symbol", "date", "call_put_ratio", "iv_rank",
                     "unusual_activity_flag", "flow_direction",
                     "dealer_regime", "score"],
                    rows)

    unusual = sum(1 for r in rows if r[4])
    bullish = sum(1 for r in rows if r[5] == "bullish")
    print(f"  Options Flow: {len(rows)} symbols | {unusual} unusual activity | {bullish} bullish flow")
