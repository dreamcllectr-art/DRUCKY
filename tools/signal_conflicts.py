"""Cross-Signal Conflict Detector — surfaces contradictions between modules."""
import json, logging
from datetime import date
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)
CONFLICT_MIN_SCORE = 55.0
CONFLICT_WEAK_THRESHOLD = 30.0
CONFLICT_SEVERITY_HIGH = 70.0

def _ensure_tables():
    conn = get_conn()
    conn.executescript("""CREATE TABLE IF NOT EXISTS signal_conflicts (
        symbol TEXT, date TEXT, conflict_type TEXT, severity TEXT, description TEXT,
        module_a TEXT, module_a_score REAL, module_b TEXT, module_b_score REAL,
        score_gap REAL, PRIMARY KEY (symbol, date, conflict_type));""")
    conn.commit(); conn.close()

def _mk(ctype, sev, desc, ma, ma_s, mb, mb_s, gap):
    return {"conflict_type": ctype, "severity": sev, "description": desc,
            "module_a": ma, "module_a_score": ma_s, "module_b": mb, "module_b_score": mb_s, "score_gap": gap}

def _detect_conflicts(symbol: str, scores: dict, insider_score: float = 0) -> list[dict]:
    conflicts = []
    _s = lambda mod: scores.get(mod, 0) or 0
    variant, worldview = _s("variant"), _s("worldview")
    main, smartmoney = _s("main_signal"), _s("smartmoney")
    cbs, em = _s("consensus_blindspots"), _s("estimate_momentum")
    insider, pattern = insider_score or 0, _s("pattern_options")
    foreign, research = _s("foreign_intel"), _s("research")
    pm = _s("prediction_markets")
    def _sev(gap): return "HIGH" if gap >= CONFLICT_SEVERITY_HIGH else "MODERATE"
    # 1. VARIANT vs WORLDVIEW
    if variant >= CONFLICT_MIN_SCORE and worldview <= CONFLICT_WEAK_THRESHOLD:
        g = variant - worldview
        conflicts.append(_mk("MACRO_VS_MICRO", _sev(g),
            f"Variant bullish ({variant:.0f}) but Worldview bearish ({worldview:.0f}). Macro headwind may overpower micro opportunity.",
            "variant", variant, "worldview", worldview, g))
    elif worldview >= CONFLICT_MIN_SCORE and variant <= CONFLICT_WEAK_THRESHOLD:
        g = worldview - variant
        conflicts.append(_mk("MACRO_VS_MICRO", _sev(g),
            f"Worldview bullish ({worldview:.0f}) but Variant overvalued ({variant:.0f}). Stock may not be best expression of macro view.",
            "worldview", worldview, "variant", variant, g))
    # 2. SMART MONEY vs CONSENSUS
    if smartmoney >= CONFLICT_MIN_SCORE and cbs <= CONFLICT_WEAK_THRESHOLD:
        g = smartmoney - cbs
        conflicts.append(_mk("SMART_MONEY_VS_CONSENSUS", _sev(g),
            f"Smart Money accumulating ({smartmoney:.0f}) but CBS flags crowded agreement ({cbs:.0f}).",
            "smartmoney", smartmoney, "consensus_blindspots", cbs, g))
    # 3. MOMENTUM vs VALUE
    if main >= CONFLICT_MIN_SCORE and variant <= CONFLICT_WEAK_THRESHOLD and main - variant >= 40:
        conflicts.append(_mk("MOMENTUM_VALUE_DIVERGENCE", "MODERATE",
            f"Tech momentum strong ({main:.0f}) but valuation poor ({variant:.0f}). Momentum vs value tension.",
            "main_signal", main, "variant", variant, main - variant))
    elif variant >= CONFLICT_MIN_SCORE and main <= CONFLICT_WEAK_THRESHOLD and variant - main >= 40:
        conflicts.append(_mk("MOMENTUM_VALUE_DIVERGENCE", "MODERATE",
            f"Value attractive ({variant:.0f}) but momentum weak ({main:.0f}). Value trap risk.",
            "variant", variant, "main_signal", main, variant - main))
    # 4. ESTIMATE vs VARIANT
    if em <= CONFLICT_WEAK_THRESHOLD and variant >= CONFLICT_MIN_SCORE and variant - em >= 40:
        conflicts.append(_mk("ESTIMATE_VS_VARIANT", "HIGH",
            f"Variant sees undervaluation ({variant:.0f}) but estimates declining ({em:.0f}). Cheap may get cheaper.",
            "variant", variant, "estimate_momentum", em, variant - em))
    # 5. INSIDER vs TECHNICALS
    if insider >= CONFLICT_MIN_SCORE and pattern <= CONFLICT_WEAK_THRESHOLD and insider - pattern >= 35:
        conflicts.append(_mk("INSIDER_VS_TECHNICALS", "MODERATE",
            f"Insiders buying ({insider:.0f}) but technicals weak ({pattern:.0f}). Insiders may be early.",
            "insider", insider, "pattern_options", pattern, insider - pattern))
    # 6. FOREIGN vs DOMESTIC
    if foreign >= CONFLICT_MIN_SCORE and research <= CONFLICT_WEAK_THRESHOLD and foreign - research >= 40:
        conflicts.append(_mk("BULL_BEAR_CLASH", "MODERATE",
            f"Foreign intel bullish ({foreign:.0f}) but domestic research bearish ({research:.0f}).",
            "foreign_intel", foreign, "research", research, foreign - research))
    # 7. PREDICTION MARKETS vs WORLDVIEW
    if pm >= CONFLICT_MIN_SCORE and worldview <= CONFLICT_WEAK_THRESHOLD and pm - worldview >= 40:
        conflicts.append(_mk("BULL_BEAR_CLASH", "MODERATE",
            f"Prediction markets signal opportunity ({pm:.0f}) but worldview unfavorable ({worldview:.0f}).",
            "prediction_markets", pm, "worldview", worldview, pm - worldview))
    return conflicts

def run():
    """Detect cross-signal conflicts for all convergence symbols."""
    init_db(); _ensure_tables(); today = date.today().isoformat()
    print("\n" + "=" * 60 + "\n  CROSS-SIGNAL CONFLICT DETECTOR\n" + "=" * 60)
    rows = query("""SELECT symbol, convergence_score, conviction_level,
        main_signal_score, smartmoney_score, worldview_score, variant_score,
        research_score, foreign_intel_score, news_displacement_score,
        alt_data_score, sector_expert_score, pairs_score, ma_score,
        energy_intel_score, prediction_markets_score, pattern_options_score,
        estimate_momentum_score, ai_regulatory_score, consensus_blindspots_score
        FROM convergence_signals WHERE date = ? AND conviction_level IN ('HIGH', 'NOTABLE')
        ORDER BY convergence_score DESC""", [today])
    if not rows:
        print("  No HIGH/NOTABLE signals to check for conflicts"); print("=" * 60); return
    print(f"  Checking {len(rows)} positions for internal contradictions...")
    insider_map = {}
    try:
        ir = query("""SELECT i.symbol, i.insider_score FROM insider_signals i
            INNER JOIN (SELECT symbol, MAX(date) as mx FROM insider_signals GROUP BY symbol) m
            ON i.symbol = m.symbol AND i.date = m.mx""")
        insider_map = {r["symbol"]: r["insider_score"] for r in ir}
    except Exception: pass
    all_conflicts = []; symbols_with_conflicts = 0
    for row in rows:
        symbol = row["symbol"]
        scores = {k.replace("_score", ""): row.get(k) for k in [
            "main_signal_score", "smartmoney_score", "worldview_score", "variant_score",
            "research_score", "foreign_intel_score", "news_displacement_score",
            "alt_data_score", "sector_expert_score", "pairs_score", "ma_score",
            "energy_intel_score", "prediction_markets_score", "pattern_options_score",
            "estimate_momentum_score", "ai_regulatory_score", "consensus_blindspots_score"]}
        conflicts = _detect_conflicts(symbol, scores, insider_map.get(symbol, 0))
        if conflicts:
            symbols_with_conflicts += 1
            for c in conflicts:
                c["symbol"] = symbol; c["date"] = today; all_conflicts.append(c)
                sev_icon = "!!" if c["severity"] == "HIGH" else "!"
                print(f"  {sev_icon} {symbol:>6} | {c['conflict_type']}: {c['module_a']}={c['module_a_score']:.0f} vs {c['module_b']}={c['module_b_score']:.0f}")
    if all_conflicts:
        upsert_many("signal_conflicts",
            ["symbol", "date", "conflict_type", "severity", "description",
             "module_a", "module_a_score", "module_b", "module_b_score", "score_gap"],
            [(c["symbol"], c["date"], c["conflict_type"], c["severity"], c["description"],
              c["module_a"], c["module_a_score"], c["module_b"], c["module_b_score"], c["score_gap"])
             for c in all_conflicts])
    high = sum(1 for c in all_conflicts if c["severity"] == "HIGH")
    print(f"\n  Conflicts detected: {len(all_conflicts)} across {symbols_with_conflicts} symbols")
    print(f"  HIGH severity: {high} | MODERATE: {len(all_conflicts) - high}")
    print("=" * 60)
    return all_conflicts

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); init_db(); run()
