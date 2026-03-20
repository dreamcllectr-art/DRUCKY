"""Gate Engine — formal 10-gate cascade for 923 assets.

Each gate is a binary pass/fail. Results stored in gate_results table.
Overrides stored in gate_overrides table.

GATE 0:  Universe          903 equities + 14 commodities + 6 crypto = 923 assets
GATE 1:  Macro Regime      Environment favorable for asset class?
GATE 2:  Liquidity         ADV > $5M, market cap > $500M (equities only)
GATE 3:  Forensic/Fraud    No CRITICAL accounting alert
GATE 4:  Sector Rotation   Sector in Leading or Improving quadrant
GATE 5:  Technical Trend   technical_score >= 45 (chart confirmation)
GATE 6:  Fundamental       fundamental_score >= 42
GATE 7:  Smart Money       smartmoney_score >= 50 OR net insider buying
GATE 8:  Signal Convergence convergence_score >= 55 AND module_count >= 2
GATE 9:  Catalyst          catalyst_score >= 40 (event trigger)
GATE 10: Fat Pitch         composite_score >= 65, BUY/STRONG_BUY, R:R >= 2.0
"""
import json
import logging
import time
import uuid
from datetime import date
from tools.db import get_conn, query, upsert_many
from tools.config import GATE_THRESHOLDS, GATE_NAMES

logger = logging.getLogger(__name__)


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS gate_results (
    symbol TEXT,
    date TEXT,
    gate_0 INTEGER DEFAULT 1,
    gate_1 INTEGER,
    gate_2 INTEGER,
    gate_3 INTEGER,
    gate_4 INTEGER,
    gate_5 INTEGER,
    gate_6 INTEGER,
    gate_7 INTEGER,
    gate_8 INTEGER,
    gate_9 INTEGER,
    gate_10 INTEGER,
    last_gate_passed INTEGER,
    fail_reason TEXT,
    asset_class TEXT,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS gate_overrides (
    symbol TEXT,
    gate INTEGER,
    direction TEXT,
    reason TEXT,
    expires TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (symbol, gate)
);

CREATE TABLE IF NOT EXISTS gate_run_history (
    run_id TEXT PRIMARY KEY,
    date TEXT,
    total_assets INTEGER,
    gate_1_passed INTEGER,
    gate_2_passed INTEGER,
    gate_3_passed INTEGER,
    gate_4_passed INTEGER,
    gate_5_passed INTEGER,
    gate_6_passed INTEGER,
    gate_7_passed INTEGER,
    gate_8_passed INTEGER,
    gate_9_passed INTEGER,
    gate_10_passed INTEGER,
    run_time_seconds REAL
);
    """)
    conn.commit()
    conn.close()


def _load_asset_scores():
    """Load all relevant scores from DB for gate evaluation."""
    scores = {}

    # 1. Universe — all assets
    for r in query("SELECT symbol, sector FROM stock_universe"):
        scores[r["symbol"]] = {"asset_class": "equity", "sector": r.get("sector", "")}

    # Crypto assets
    from tools.config import CRYPTO_TICKERS
    for ticker in CRYPTO_TICKERS:
        scores[ticker] = {"asset_class": "crypto", "sector": "Crypto"}

    # Commodities
    from tools.config import COMMODITIES
    for ticker in COMMODITIES:
        scores[ticker] = {"asset_class": "commodity", "sector": "Commodities"}

    # 2. Macro regime score
    macro_rows = query("SELECT regime, total_score FROM macro_scores ORDER BY date DESC LIMIT 1")
    macro_regime_score = 50.0
    macro_regime = "neutral"
    if macro_rows:
        macro_regime_score = macro_rows[0].get("total_score") or 50.0
        macro_regime = macro_rows[0].get("regime", "neutral")
    for sym in scores:
        scores[sym]["macro_regime_score"] = macro_regime_score
        scores[sym]["macro_regime"] = macro_regime

    # 3. Liquidity / fundamentals — compute ADV from 20-day price_data
    market_caps = {r["symbol"]: r["value"] for r in query(
        "SELECT symbol, value FROM fundamentals WHERE metric = 'marketCap'"
    )}
    # ADV = avg(close * volume) over last 20 trading days
    adv_rows = query(
        """SELECT symbol,
                  AVG(close * volume) / 1e6 as adv_m
           FROM price_data
           WHERE date >= date('now', '-30 days')
           GROUP BY symbol"""
    )
    adv_map = {r["symbol"]: r["adv_m"] or 0 for r in adv_rows}

    for sym in list(scores.keys()):
        mc = market_caps.get(sym, 0) or 0
        adv = adv_map.get(sym, 0) or 0
        scores[sym]["market_cap_m"] = mc / 1e6
        scores[sym]["adv_m"] = adv

    # 4. Forensic scores
    forensic_rows = query(
        """SELECT f.symbol, f.total_score
           FROM fundamental_scores f
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM fundamental_scores GROUP BY symbol) m
           ON f.symbol = m.symbol AND f.date = m.mx"""
    )
    for r in forensic_rows:
        if r["symbol"] in scores:
            scores[r["symbol"]]["forensic_score"] = r.get("total_score", 50)

    # CRITICAL forensic blocks
    blocked = {r["symbol"] for r in query(
        "SELECT DISTINCT symbol FROM forensic_alerts WHERE severity = 'CRITICAL'"
    )}
    for sym in blocked:
        if sym in scores:
            scores[sym]["forensic_blocked"] = True

    # 5. Sector rotation
    sector_rows = query(
        """SELECT sr.sector, sr.quadrant, sr.rotation_score
           FROM sector_rotation sr
           INNER JOIN (SELECT sector, MAX(date) as mx FROM sector_rotation GROUP BY sector) m
           ON sr.sector = m.sector AND sr.date = m.mx"""
    )
    sector_rotation = {r["sector"]: r for r in sector_rows}
    for sym, data in scores.items():
        sector = data.get("sector", "")
        sr = sector_rotation.get(sector, {})
        data["rotation_score"] = sr.get("rotation_score") or sr.get("score") or 30
        data["rotation_quadrant"] = sr.get("quadrant", "")

    # 6. Technical scores
    tech_rows = query(
        """SELECT t.symbol, t.total_score
           FROM technical_scores t
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM technical_scores GROUP BY symbol) m
           ON t.symbol = m.symbol AND t.date = m.mx"""
    )
    for r in tech_rows:
        if r["symbol"] in scores:
            scores[r["symbol"]]["technical_score"] = r.get("total_score", 0)

    # 7. Fundamental scores
    fscore_rows = query(
        """SELECT f.symbol, f.total_score
           FROM fundamental_scores f
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM fundamental_scores GROUP BY symbol) m
           ON f.symbol = m.symbol AND f.date = m.mx"""
    )
    for r in fscore_rows:
        if r["symbol"] in scores:
            scores[r["symbol"]]["fundamental_score"] = r.get("total_score", 0)

    # 8. Smart money / insider
    sm_rows = query(
        """SELECT s.symbol, s.conviction_score
           FROM smart_money_scores s
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM smart_money_scores GROUP BY symbol) m
           ON s.symbol = m.symbol AND s.date = m.mx"""
    )
    for r in sm_rows:
        if r["symbol"] in scores:
            scores[r["symbol"]]["smartmoney_score"] = r.get("conviction_score", 0)

    # Insider buying (recent 90d net)
    insider_rows = query(
        """SELECT symbol, SUM(CASE WHEN transaction_type = 'P' THEN value ELSE -value END) as net_buy
           FROM insider_transactions
           WHERE date >= date('now', '-90 days') AND transaction_type IN ('P', 'S')
           GROUP BY symbol"""
    )
    for r in insider_rows:
        if r["symbol"] in scores:
            scores[r["symbol"]]["insider_net_buy"] = r.get("net_buy", 0) or 0

    # 9. Convergence scores
    conv_rows = query(
        """SELECT c.symbol, c.convergence_score, c.module_count
           FROM convergence_signals c
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM convergence_signals GROUP BY symbol) m
           ON c.symbol = m.symbol AND c.date = m.mx"""
    )
    for r in conv_rows:
        if r["symbol"] in scores:
            scores[r["symbol"]]["convergence_score"] = r.get("convergence_score", 0)
            scores[r["symbol"]]["module_count"] = r.get("module_count", 0)

    # 10. Catalyst scores
    cat_rows = query(
        """SELECT cs.symbol, cs.score as catalyst_score
           FROM catalyst_scores cs
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM catalyst_scores GROUP BY symbol) m
           ON cs.symbol = m.symbol AND cs.date = m.mx"""
    )
    for r in cat_rows:
        if r["symbol"] in scores:
            scores[r["symbol"]]["catalyst_score"] = r.get("catalyst_score", 0)

    # On-chain scores for crypto
    onchain_rows = query(
        """SELECT o.asset, o.composite
           FROM onchain_scores o
           INNER JOIN (SELECT asset, MAX(date) as mx FROM onchain_scores GROUP BY asset) m
           ON o.asset = m.asset AND o.date = m.mx"""
    )
    for r in onchain_rows:
        if r["asset"] in scores:
            scores[r["asset"]]["onchain_score"] = r.get("composite", 50)

    # 11. Final signals (composite_score, signal, rr_ratio)
    sig_rows = query(
        """SELECT s.symbol, s.composite_score, s.signal, s.rr_ratio
           FROM signals s
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM signals GROUP BY symbol) m
           ON s.symbol = m.symbol AND s.date = m.mx"""
    )
    for r in sig_rows:
        if r["symbol"] in scores:
            scores[r["symbol"]]["composite_score"] = r.get("composite_score", 0)
            scores[r["symbol"]]["signal"] = r.get("signal", "")
            scores[r["symbol"]]["rr_ratio"] = r.get("rr_ratio", 0) or 0

    # 12. Short interest scores (supplements Gate 7 + 9)
    for r in query(
        """SELECT si.symbol, si.short_float_pct, si.squeeze_score, si.direction
           FROM short_interest_scores si
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM short_interest_scores GROUP BY symbol) m
           ON si.symbol = m.symbol AND si.date = m.mx"""
    ):
        if r["symbol"] in scores:
            scores[r["symbol"]]["short_float_pct"] = r.get("short_float_pct", 0)
            scores[r["symbol"]]["squeeze_score"] = r.get("squeeze_score", 50)

    # 13. Analyst scores (supplements Gate 6)
    for r in query(
        """SELECT a.symbol, a.composite_score as analyst_composite, a.pt_upside_pct
           FROM analyst_scores a
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM analyst_scores GROUP BY symbol) m
           ON a.symbol = m.symbol AND a.date = m.mx"""
    ):
        if r["symbol"] in scores:
            scores[r["symbol"]]["analyst_score"] = r.get("analyst_composite", 50)
            scores[r["symbol"]]["pt_upside_pct"] = r.get("pt_upside_pct")

    # 14. Capital flow scores (supplements Gate 7)
    for r in query(
        """SELECT cf.symbol, cf.composite as capital_flow_score, cf.smart_manager_count
           FROM capital_flow_scores cf
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM capital_flow_scores GROUP BY symbol) m
           ON cf.symbol = m.symbol AND cf.date = m.mx"""
    ):
        if r["symbol"] in scores:
            scores[r["symbol"]]["capital_flow_score"] = r.get("capital_flow_score", 50)
            scores[r["symbol"]]["smart_manager_count"] = r.get("smart_manager_count", 0)

    # 15. Options flow (supplements Gate 9)
    for r in query(
        """SELECT of_.symbol, of_.score as options_flow_score, of_.flow_direction
           FROM options_flow_scores of_
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM options_flow_scores GROUP BY symbol) m
           ON of_.symbol = m.symbol AND of_.date = m.mx"""
    ):
        if r["symbol"] in scores:
            scores[r["symbol"]]["options_flow_score"] = r.get("options_flow_score", 50)
            scores[r["symbol"]]["options_direction"] = r.get("flow_direction", "")

    # 16. Retail sentiment (used in convergence context, supplements Gate 8)
    for r in query(
        """SELECT rs.symbol, rs.score as retail_sentiment_score, rs.contrarian_flag
           FROM retail_sentiment_scores rs
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM retail_sentiment_scores GROUP BY symbol) m
           ON rs.symbol = m.symbol AND rs.date = m.mx"""
    ):
        if r["symbol"] in scores:
            scores[r["symbol"]]["retail_sentiment_score"] = r.get("retail_sentiment_score", 50)
            scores[r["symbol"]]["retail_contrarian_flag"] = r.get("contrarian_flag", 0)

    # 17. Alt-data scores already in convergence, but load for direct gate use
    for r in query(
        """SELECT e.symbol, e.earnings_nlp_score FROM earnings_nlp_scores e
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM earnings_nlp_scores GROUP BY symbol) m
           ON e.symbol = m.symbol AND e.date = m.mx"""
    ):
        if r["symbol"] in scores:
            scores[r["symbol"]]["earnings_nlp_score"] = r.get("earnings_nlp_score", 50)

    # 18. Patent intel (innovation signal for tech/pharma Gate 6)
    for r in query(
        """SELECT p.symbol, p.patent_intel_score FROM patent_intel_scores p
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM patent_intel_scores GROUP BY symbol) m
           ON p.symbol = m.symbol AND p.date = m.mx"""
    ):
        if r["symbol"] in scores:
            scores[r["symbol"]]["patent_score"] = r.get("patent_intel_score", 50)

    # 19. Cross-asset screener (regime fit for alt assets)
    for r in query(
        """SELECT ca.symbol, ca.regime_fit_score, ca.opportunity_score, ca.is_fat_pitch
           FROM cross_asset_opportunities ca
           INNER JOIN (SELECT symbol, MAX(date) as mx FROM cross_asset_opportunities GROUP BY symbol) m
           ON ca.symbol = m.symbol AND ca.date = m.mx"""
    ):
        if r["symbol"] in scores:
            scores[r["symbol"]]["cross_asset_regime_fit"] = r.get("regime_fit_score", 50)
            scores[r["symbol"]]["cross_asset_fat_pitch"] = r.get("is_fat_pitch", 0)

    # 20. Macro regime per cross-asset class
    asset_class_rows = query(
        """SELECT ac.asset_class, ac.score as asset_class_score, ac.regime_signal
           FROM asset_class_signals ac
           INNER JOIN (SELECT asset_class, MAX(date) as mx FROM asset_class_signals GROUP BY asset_class) m
           ON ac.asset_class = m.asset_class AND ac.date = m.mx"""
    )
    asset_class_scores = {r["asset_class"]: r for r in asset_class_rows}
    for sym, data in scores.items():
        ac = data.get("asset_class", "equity")
        ac_data = asset_class_scores.get(ac, {})
        if ac_data.get("asset_class_score"):
            # Override macro regime score for non-equity asset classes
            data["macro_regime_score"] = ac_data["asset_class_score"]

    return scores


def _load_overrides():
    """Load active gate overrides (not expired)."""
    rows = query(
        "SELECT symbol, gate, direction FROM gate_overrides "
        "WHERE expires IS NULL OR expires >= date('now')"
    )
    overrides = {}
    for r in rows:
        overrides[(r["symbol"], r["gate"])] = r["direction"]
    return overrides


def _evaluate_gates(symbol, data, thresholds, overrides):
    """Evaluate all 10 gates for a single asset. Returns gate results dict."""
    asset_class = data.get("asset_class", "equity")
    gates = {i: None for i in range(11)}
    gates[0] = 1  # Universe: always passes
    last_gate = 0
    fail_reason = ""

    def check(gate_num, condition, reason):
        nonlocal last_gate, fail_reason
        # Check for override
        override = overrides.get((symbol, gate_num))
        if override == "force_pass":
            gates[gate_num] = 1
            last_gate = gate_num
            return True
        if override == "force_fail":
            gates[gate_num] = 0
            fail_reason = f"Gate {gate_num} force-failed by override"
            return False
        # Evaluate condition
        if condition:
            gates[gate_num] = 1
            last_gate = gate_num
            return True
        else:
            gates[gate_num] = 0
            fail_reason = f"Gate {gate_num} ({GATE_NAMES[gate_num]}): {reason}"
            return False

    # GATE 1: Macro Regime
    g1 = thresholds[1]
    regime_score = data.get("macro_regime_score", 50)
    macro_ok = regime_score >= g1["regime_fit_score"]
    # Crypto/commodities have separate regime logic
    if asset_class in ("crypto", "commodity"):
        macro_ok = True  # Always pass macro for now (they have separate regime logic)
    if not check(1, macro_ok,
                 f"regime_score={regime_score:.0f} < {g1['regime_fit_score']}"):
        return gates, last_gate, fail_reason

    # GATE 2: Liquidity (equities only)
    g2 = thresholds[2]
    if asset_class == "equity":
        adv = data.get("adv_m", 0) or 0
        mc = data.get("market_cap_m", 0) or 0
        liq_ok = adv >= g2["min_adv_m"] and mc >= g2["min_mktcap_m"]
        if not check(2, liq_ok,
                     f"ADV=${adv:.1f}M (min {g2['min_adv_m']}M) or "
                     f"mktcap=${mc:.0f}M (min {g2['min_mktcap_m']}M)"):
            return gates, last_gate, fail_reason
    else:
        # Crypto/commodities pass liquidity gate by default
        check(2, True, "")

    # GATE 3: Forensic / Fraud
    g3 = thresholds[3]
    if data.get("forensic_blocked"):
        if not check(3, False, "CRITICAL forensic alert"):
            return gates, last_gate, fail_reason
    else:
        forensic = data.get("forensic_score", 50) or 50
        if not check(3, forensic >= g3["min_forensic_score"],
                     f"forensic_score={forensic:.0f} < {g3['min_forensic_score']}"):
            return gates, last_gate, fail_reason

    # GATE 4: Sector Rotation
    g4 = thresholds[4]
    rotation = data.get("rotation_score", 30) or 30
    quadrant = data.get("rotation_quadrant", "")
    # Leading or Improving quadrant passes
    rotation_ok = rotation >= g4["min_rotation_score"] or quadrant in ("Leading", "Improving")
    if asset_class in ("crypto", "commodity"):
        rotation_ok = True  # No sector rotation for crypto/commodities
    if not check(4, rotation_ok,
                 f"rotation_score={rotation:.0f} < {g4['min_rotation_score']} "
                 f"quadrant={quadrant}"):
        return gates, last_gate, fail_reason

    # GATE 5: Technical Trend (Chart confirmation)
    g5 = thresholds[5]
    tech = data.get("technical_score", 0) or 0
    onchain = data.get("onchain_score", 50) or 50
    if asset_class == "crypto":
        # For crypto, blend technical score with on-chain
        tech_ok = tech >= g5["min_technical_score"] or onchain >= 55
    else:
        tech_ok = tech >= g5["min_technical_score"]
    if not check(5, tech_ok,
                 f"technical_score={tech:.0f} < {g5['min_technical_score']}"):
        return gates, last_gate, fail_reason

    # GATE 6: Fundamental Quality (enhanced with analyst score + patent intel)
    g6 = thresholds[6]
    fund = data.get("fundamental_score", 0) or 0
    analyst_score = data.get("analyst_score", 0) or 0
    patent_score = data.get("patent_score", 0) or 0
    if asset_class in ("crypto", "commodity"):
        fund_ok = True  # No traditional fundamentals
    else:
        # Pass if fundamental score meets threshold, OR if analyst consensus is strong
        # OR if cross-asset screener flagged as fat pitch
        fund_ok = (fund >= g6["min_fundamental_score"] or
                   analyst_score >= 65 or
                   data.get("cross_asset_fat_pitch", 0) == 1)
    if not check(6, fund_ok,
                 f"fundamental_score={fund:.0f} < {g6['min_fundamental_score']} "
                 f"analyst_score={analyst_score:.0f}"):
        return gates, last_gate, fail_reason

    # GATE 7: Smart Money (enhanced with capital flows + on-chain)
    g7 = thresholds[7]
    sm = data.get("smartmoney_score", 0) or 0
    insider_net = data.get("insider_net_buy", 0) or 0
    capital_flow = data.get("capital_flow_score", 0) or 0
    smart_mgr_count = data.get("smart_manager_count", 0) or 0
    onchain_score = data.get("onchain_score", 50) or 50

    if asset_class in ("crypto", "commodity"):
        # Crypto: use on-chain score as proxy for smart money
        sm_ok = sm >= g7["min_smartmoney_score"] or onchain_score >= 55
    else:
        # Equity: 13F smart money, insider net buy, strong capital flows,
        # OR convergence_score >= 50 (convergence already incorporates smart money signals)
        convergence = data.get("convergence_score", 0) or 0
        sm_ok = (sm >= g7["min_smartmoney_score"] or
                 insider_net > 0 or
                 capital_flow >= 65 or
                 smart_mgr_count >= 2 or
                 convergence >= 50)
    if not check(7, sm_ok,
                 f"smartmoney={sm:.0f} < {g7['min_smartmoney_score']}, "
                 f"capital_flow={capital_flow:.0f}, insider_net={insider_net:.0f}"):
        return gates, last_gate, fail_reason

    # GATE 8: Signal Convergence
    g8 = thresholds[8]
    conv = data.get("convergence_score", 0) or 0
    mods = data.get("module_count", 0) or 0
    if not check(8, conv >= g8["min_convergence_score"] and mods >= g8["min_modules"],
                 f"convergence={conv:.0f} < {g8['min_convergence_score']} "
                 f"or modules={mods} < {g8['min_modules']}"):
        return gates, last_gate, fail_reason

    # GATE 9: Catalyst (enhanced with options flow + short squeeze + convergence fallback)
    g9 = thresholds[9]
    catalyst = data.get("catalyst_score", 0) or 0
    options_flow = data.get("options_flow_score", 0) or 0
    options_dir = data.get("options_direction", "")
    squeeze_score = data.get("squeeze_score", 0) or 0
    convergence_9 = data.get("convergence_score", 0) or 0
    composite_9 = data.get("composite_score", 0) or 0
    # Unusual bullish options flow, high squeeze, or strong multi-signal convergence
    # (convergence >= 54 + composite >= 55 = sufficient signal evidence, catalyst implied)
    catalyst_ok = (catalyst >= g9["min_catalyst_score"] or
                   (options_flow >= 70 and options_dir == "bullish") or
                   squeeze_score >= 75 or
                   (convergence_9 >= 54 and composite_9 >= 55))
    if not check(9, catalyst_ok,
                 f"catalyst={catalyst:.0f} < {g9['min_catalyst_score']}, "
                 f"options_flow={options_flow:.0f}, squeeze={squeeze_score:.0f}"):
        return gates, last_gate, fail_reason

    # GATE 10: Fat Pitch
    g10 = thresholds[10]
    composite = data.get("composite_score", 0) or 0
    signal = data.get("signal", "") or ""
    rr = data.get("rr_ratio", 0) or 0
    is_buy = signal in ("BUY", "STRONG_BUY")
    fat_ok = (
        composite >= g10["min_composite_score"] and
        rr >= g10["min_rr"] and
        (is_buy or not g10["require_buy_signal"])
    )
    check(10, fat_ok,
          f"composite={composite:.0f} < {g10['min_composite_score']} or "
          f"rr={rr:.1f} < {g10['min_rr']} or signal={signal}")

    return gates, last_gate, fail_reason


def run():
    """Run the full 10-gate cascade for all 923 assets."""
    _ensure_tables()
    t0 = time.time()
    today = date.today().isoformat()
    run_id = str(uuid.uuid4())[:8]

    print("\n" + "=" * 60)
    print("  GATE ENGINE — 10-Gate Cascade")
    print("=" * 60)

    # Load all scores
    asset_scores = _load_asset_scores()
    overrides = _load_overrides()
    thresholds = GATE_THRESHOLDS
    total = len(asset_scores)
    print(f"  Assets loaded: {total} | Overrides: {len(overrides)}")

    # Track per-gate counts
    gate_counts = {i: 0 for i in range(11)}
    gate_counts[0] = total  # All pass gate 0

    rows = []
    for symbol, data in asset_scores.items():
        gates, last_gate, fail_reason = _evaluate_gates(
            symbol, data, thresholds, overrides
        )
        for g in range(1, 11):
            if gates[g] == 1:
                gate_counts[g] += 1

        rows.append((
            symbol, today,
            gates[0], gates[1], gates[2], gates[3], gates[4], gates[5],
            gates[6], gates[7], gates[8], gates[9], gates[10],
            last_gate, fail_reason[:500] if fail_reason else "",
            data.get("asset_class", "equity"),
        ))

    # Write results
    if rows:
        upsert_many("gate_results",
                    ["symbol", "date", "gate_0", "gate_1", "gate_2", "gate_3",
                     "gate_4", "gate_5", "gate_6", "gate_7", "gate_8", "gate_9",
                     "gate_10", "last_gate_passed", "fail_reason", "asset_class"],
                    rows)

    elapsed = time.time() - t0

    # Write run history
    history_row = (
        run_id, today, total,
        gate_counts[1], gate_counts[2], gate_counts[3], gate_counts[4],
        gate_counts[5], gate_counts[6], gate_counts[7], gate_counts[8],
        gate_counts[9], gate_counts[10], round(elapsed, 1),
    )
    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO gate_run_history
        (run_id, date, total_assets, gate_1_passed, gate_2_passed, gate_3_passed,
         gate_4_passed, gate_5_passed, gate_6_passed, gate_7_passed, gate_8_passed,
         gate_9_passed, gate_10_passed, run_time_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, history_row)
    conn.commit()
    conn.close()

    # Print waterfall
    print(f"\n  {'Gate':<25} {'Count':>6}  {'% of prev':>9}  Bar")
    prev = total
    for g in range(11):
        count = gate_counts[g]
        pct = (count / prev * 100) if prev > 0 else 0
        bar = "█" * int(count / total * 30) if total > 0 else ""
        name = GATE_NAMES[g]
        print(f"  Gate {g} {name:<20} {count:>6}  {pct:>8.1f}%  {bar}")
        prev = count

    fat_pitches = gate_counts[10]
    print(f"\n  FAT PITCHES: {fat_pitches}")
    print(f"  Run time: {elapsed:.1f}s")
    print(f"  Run ID: {run_id}")

    return {
        "run_id": run_id,
        "total": total,
        "gate_counts": gate_counts,
        "fat_pitches": fat_pitches,
    }
