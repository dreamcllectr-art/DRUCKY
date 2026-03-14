"""Cross-Signal Conflict Detector — surfaces contradictions between modules.

When high-weight modules directly contradict each other on the same stock,
this is either a warning (the thesis is weak) or an opportunity (one module
sees something others don't). Either way, it must be surfaced.

Conflict Types:
  1. BULL_BEAR_CLASH: High-scoring bullish module + high-scoring bearish module
     e.g., variant says undervalued but worldview says bearish sector thesis
  2. MOMENTUM_VALUE_DIVERGENCE: Technical momentum strong but fundamental value weak
     or vice versa — classic growth vs value tension
  3. SMART_MONEY_VS_CONSENSUS: Smart money accumulating but consensus blindspots
     says crowded agreement (or smart money selling but CBS says contrarian bullish)
  4. INSIDER_VS_TECHNICALS: Insiders buying but technicals deteriorating
  5. MACRO_VS_MICRO: Worldview/macro bearish on sector but stock-level modules bullish
  6. ESTIMATE_VS_VARIANT: Estimate momentum declining but variant says undervalued

Output: signal_conflicts table with conflict_type, severity, description, and
which modules are in tension.

Usage: python -m tools.signal_conflicts
"""

import json
import logging
from datetime import date

from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────
CONFLICT_MIN_SCORE = 55.0      # Module must score above this to be "active"
CONFLICT_WEAK_THRESHOLD = 30.0  # Module below this is "actively bearish"
CONFLICT_SEVERITY_HIGH = 70.0   # Score gap above this = HIGH severity


# ── DB Table ─────────────────────────────────────────────────────────

def _ensure_tables():
    """Create signal conflicts table."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signal_conflicts (
            symbol TEXT,
            date TEXT,
            conflict_type TEXT,
            severity TEXT,
            description TEXT,
            module_a TEXT,
            module_a_score REAL,
            module_b TEXT,
            module_b_score REAL,
            score_gap REAL,
            PRIMARY KEY (symbol, date, conflict_type)
        );
    """)
    conn.commit()
    conn.close()


# ── Conflict Detection Rules ────────────────────────────────────────

def _detect_conflicts(symbol: str, scores: dict) -> list[dict]:
    """Detect all conflicts for a single symbol.

    Args:
        symbol: stock ticker
        scores: {module_name: score_0_to_100} for this symbol

    Returns list of conflict dicts.
    """
    conflicts = []

    # Helper
    def _s(mod):
        return scores.get(mod, 0) or 0

    # ── 1. VARIANT vs WORLDVIEW ──
    # Variant says undervalued but worldview says bearish sector
    variant = _s("variant")
    worldview = _s("worldview")
    if variant >= CONFLICT_MIN_SCORE and worldview <= CONFLICT_WEAK_THRESHOLD:
        gap = variant - worldview
        severity = "HIGH" if gap >= CONFLICT_SEVERITY_HIGH else "MODERATE"
        conflicts.append({
            "conflict_type": "MACRO_VS_MICRO",
            "severity": severity,
            "description": (
                f"Variant Perception is bullish (score={variant:.0f}, "
                f"stock appears undervalued) but Worldview is bearish "
                f"(score={worldview:.0f}, macro thesis unfavorable). "
                f"The macro headwind may overpower the micro opportunity."
            ),
            "module_a": "variant",
            "module_a_score": variant,
            "module_b": "worldview",
            "module_b_score": worldview,
            "score_gap": gap,
        })
    elif worldview >= CONFLICT_MIN_SCORE and variant <= CONFLICT_WEAK_THRESHOLD:
        gap = worldview - variant
        severity = "HIGH" if gap >= CONFLICT_SEVERITY_HIGH else "MODERATE"
        conflicts.append({
            "conflict_type": "MACRO_VS_MICRO",
            "severity": severity,
            "description": (
                f"Worldview is bullish (score={worldview:.0f}, "
                f"macro thesis supportive) but Variant says overvalued "
                f"(score={variant:.0f}). Stock may not be the best "
                f"expression of the macro view."
            ),
            "module_a": "worldview",
            "module_a_score": worldview,
            "module_b": "variant",
            "module_b_score": variant,
            "score_gap": gap,
        })

    # ── 2. SMART MONEY vs CONSENSUS BLINDSPOTS ──
    smartmoney = _s("smartmoney")
    cbs = _s("consensus_blindspots")
    if smartmoney >= CONFLICT_MIN_SCORE and cbs <= CONFLICT_WEAK_THRESHOLD:
        gap = smartmoney - cbs
        severity = "HIGH" if gap >= CONFLICT_SEVERITY_HIGH else "MODERATE"
        conflicts.append({
            "conflict_type": "SMART_MONEY_VS_CONSENSUS",
            "severity": severity,
            "description": (
                f"Smart Money is accumulating (score={smartmoney:.0f}, "
                f"tracked managers buying) but Consensus Blindspots flags "
                f"crowded agreement (score={cbs:.0f}). Either the smart money "
                f"knows something, or they're part of the crowd this time."
            ),
            "module_a": "smartmoney",
            "module_a_score": smartmoney,
            "module_b": "consensus_blindspots",
            "module_b_score": cbs,
            "score_gap": gap,
        })

    # ── 3. MOMENTUM vs VALUE ──
    # main_signal (tech-heavy) vs variant (value-focused)
    main = _s("main_signal")
    if main >= CONFLICT_MIN_SCORE and variant <= CONFLICT_WEAK_THRESHOLD:
        gap = main - variant
        if gap >= 40:
            conflicts.append({
                "conflict_type": "MOMENTUM_VALUE_DIVERGENCE",
                "severity": "MODERATE",
                "description": (
                    f"Technical momentum is strong (main_signal={main:.0f}) "
                    f"but fundamental valuation is poor (variant={variant:.0f}). "
                    f"Classic momentum vs value tension — momentum can persist "
                    f"but the risk/reward may be unfavorable."
                ),
                "module_a": "main_signal",
                "module_a_score": main,
                "module_b": "variant",
                "module_b_score": variant,
                "score_gap": gap,
            })
    elif variant >= CONFLICT_MIN_SCORE and main <= CONFLICT_WEAK_THRESHOLD:
        gap = variant - main
        if gap >= 40:
            conflicts.append({
                "conflict_type": "MOMENTUM_VALUE_DIVERGENCE",
                "severity": "MODERATE",
                "description": (
                    f"Fundamental value is attractive (variant={variant:.0f}) "
                    f"but technical momentum is weak (main_signal={main:.0f}). "
                    f"Value trap risk — stock may be cheap for a reason."
                ),
                "module_a": "variant",
                "module_a_score": variant,
                "module_b": "main_signal",
                "module_b_score": main,
                "score_gap": gap,
            })

    # ── 4. ESTIMATE MOMENTUM vs VARIANT ──
    em = _s("estimate_momentum")
    if em <= CONFLICT_WEAK_THRESHOLD and variant >= CONFLICT_MIN_SCORE:
        gap = variant - em
        if gap >= 40:
            conflicts.append({
                "conflict_type": "ESTIMATE_VS_VARIANT",
                "severity": "HIGH",
                "description": (
                    f"Variant sees undervaluation (score={variant:.0f}) but "
                    f"estimate momentum is declining (score={em:.0f}). "
                    f"Analysts are cutting estimates — the 'cheap' stock may "
                    f"be getting cheaper for fundamental reasons."
                ),
                "module_a": "variant",
                "module_a_score": variant,
                "module_b": "estimate_momentum",
                "module_b_score": em,
                "score_gap": gap,
            })

    # ── 5. INSIDER vs TECHNICALS ──
    # Check insider from separate table
    insider_rows = query("""
        SELECT insider_score FROM insider_signals
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    insider = insider_rows[0]["insider_score"] if insider_rows else 0

    pattern = _s("pattern_options")
    if insider and insider >= CONFLICT_MIN_SCORE and pattern <= CONFLICT_WEAK_THRESHOLD:
        gap = insider - pattern
        if gap >= 35:
            conflicts.append({
                "conflict_type": "INSIDER_VS_TECHNICALS",
                "severity": "MODERATE",
                "description": (
                    f"Insiders are buying (score={insider:.0f}) but "
                    f"technical patterns are weak (pattern_options={pattern:.0f}). "
                    f"Insiders often lead — they may be early. Or the "
                    f"technicals are warning of near-term pain."
                ),
                "module_a": "insider",
                "module_a_score": insider,
                "module_b": "pattern_options",
                "module_b_score": pattern,
                "score_gap": gap,
            })

    # ── 6. FOREIGN INTEL vs DOMESTIC ──
    foreign = _s("foreign_intel")
    research = _s("research")
    if foreign >= CONFLICT_MIN_SCORE and research <= CONFLICT_WEAK_THRESHOLD:
        gap = foreign - research
        if gap >= 40:
            conflicts.append({
                "conflict_type": "BULL_BEAR_CLASH",
                "severity": "MODERATE",
                "description": (
                    f"Foreign intelligence is bullish (score={foreign:.0f}) "
                    f"but domestic research is bearish (score={research:.0f}). "
                    f"International markets may be pricing in information "
                    f"that domestic analysts haven't incorporated."
                ),
                "module_a": "foreign_intel",
                "module_a_score": foreign,
                "module_b": "research",
                "module_b_score": research,
                "score_gap": gap,
            })

    # ── 7. PREDICTION MARKETS vs MODULES ──
    pm = _s("prediction_markets")
    if pm >= CONFLICT_MIN_SCORE and worldview <= CONFLICT_WEAK_THRESHOLD:
        gap = pm - worldview
        if gap >= 40:
            conflicts.append({
                "conflict_type": "BULL_BEAR_CLASH",
                "severity": "MODERATE",
                "description": (
                    f"Prediction markets signal opportunity (score={pm:.0f}) "
                    f"but worldview macro thesis is unfavorable (score={worldview:.0f}). "
                    f"Event-driven opportunity may override macro headwind."
                ),
                "module_a": "prediction_markets",
                "module_a_score": pm,
                "module_b": "worldview",
                "module_b_score": worldview,
                "score_gap": gap,
            })

    return conflicts


# ── Main ─────────────────────────────────────────────────────────────

def run():
    """Detect cross-signal conflicts for all convergence symbols."""
    init_db()
    _ensure_tables()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  CROSS-SIGNAL CONFLICT DETECTOR")
    print("=" * 60)

    # Get latest convergence signals with all module scores
    rows = query("""
        SELECT symbol, convergence_score, conviction_level,
               main_signal_score, smartmoney_score, worldview_score,
               variant_score, research_score, foreign_intel_score,
               news_displacement_score, alt_data_score, sector_expert_score,
               pairs_score, ma_score, energy_intel_score,
               prediction_markets_score, pattern_options_score,
               estimate_momentum_score, ai_regulatory_score,
               consensus_blindspots_score
        FROM convergence_signals
        WHERE date = ?
          AND conviction_level IN ('HIGH', 'NOTABLE')
        ORDER BY convergence_score DESC
    """, [today])

    if not rows:
        print("  No HIGH/NOTABLE signals to check for conflicts")
        print("=" * 60)
        return

    print(f"  Checking {len(rows)} positions for internal contradictions...")

    all_conflicts = []
    symbols_with_conflicts = 0

    for row in rows:
        symbol = row["symbol"]
        # Build scores dict
        scores = {
            "main_signal": row.get("main_signal_score"),
            "smartmoney": row.get("smartmoney_score"),
            "worldview": row.get("worldview_score"),
            "variant": row.get("variant_score"),
            "research": row.get("research_score"),
            "foreign_intel": row.get("foreign_intel_score"),
            "news_displacement": row.get("news_displacement_score"),
            "alt_data": row.get("alt_data_score"),
            "sector_expert": row.get("sector_expert_score"),
            "pairs": row.get("pairs_score"),
            "ma": row.get("ma_score"),
            "energy_intel": row.get("energy_intel_score"),
            "prediction_markets": row.get("prediction_markets_score"),
            "pattern_options": row.get("pattern_options_score"),
            "estimate_momentum": row.get("estimate_momentum_score"),
            "ai_regulatory": row.get("ai_regulatory_score"),
            "consensus_blindspots": row.get("consensus_blindspots_score"),
        }

        conflicts = _detect_conflicts(symbol, scores)
        if conflicts:
            symbols_with_conflicts += 1
            for c in conflicts:
                c["symbol"] = symbol
                c["date"] = today
                all_conflicts.append(c)
                sev_icon = "!!" if c["severity"] == "HIGH" else "!"
                print(f"  {sev_icon} {symbol:>6} | {c['conflict_type']}: "
                      f"{c['module_a']}={c['module_a_score']:.0f} vs "
                      f"{c['module_b']}={c['module_b_score']:.0f}")

    # Persist
    if all_conflicts:
        conflict_rows = [
            (c["symbol"], c["date"], c["conflict_type"], c["severity"],
             c["description"], c["module_a"], c["module_a_score"],
             c["module_b"], c["module_b_score"], c["score_gap"])
            for c in all_conflicts
        ]
        upsert_many(
            "signal_conflicts",
            ["symbol", "date", "conflict_type", "severity", "description",
             "module_a", "module_a_score", "module_b", "module_b_score", "score_gap"],
            conflict_rows,
        )

    print(f"\n  Conflicts detected: {len(all_conflicts)} across {symbols_with_conflicts} symbols")
    high = sum(1 for c in all_conflicts if c["severity"] == "HIGH")
    print(f"  HIGH severity: {high} | MODERATE: {len(all_conflicts) - high}")
    print("=" * 60)

    return all_conflicts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    run()
