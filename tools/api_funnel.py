"""Funnel / Dossier / Journal / Environment API routes for V2 dashboard.

Composes existing query() calls into higher-level endpoints that power
the 5-view funnel architecture: Environment, Funnel, Conviction Board,
Risk, and Journal.
"""

from fastapi import APIRouter, Body
from tools.db import query, get_conn
import json

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# ENVIRONMENT
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/environment")
def environment():
    """Compose: macro regime + heat index + asset class signals + cross-cutting intel."""
    macro = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = macro[0] if macro else {}

    heat = query("SELECT * FROM economic_heat_index ORDER BY date DESC LIMIT 1")
    heat_index = heat[0] if heat else {}

    asset_classes = query("""
        SELECT * FROM asset_class_signals
        WHERE date = (SELECT MAX(date) FROM asset_class_signals)
        ORDER BY asset_class
    """)

    # Cross-cutting intelligence: non-ticker findings from worldview + thesis
    cross_cutting = []
    theses = query("SELECT * FROM thesis_snapshots WHERE date >= date('now', '-7 days') ORDER BY confidence DESC LIMIT 5")
    for t in theses:
        cross_cutting.append({
            "source": "worldview",
            "headline": t.get("thesis", ""),
            "detail": f"{t.get('direction', '')} | confidence: {t.get('confidence', 0):.0f} | sectors: {t.get('affected_sectors', 'N/A')}"
        })

    narratives = query("SELECT * FROM narrative_signals WHERE date >= date('now', '-7 days') ORDER BY strength_score DESC LIMIT 5")
    for n in narratives:
        cross_cutting.append({
            "source": "narrative",
            "headline": n.get("narrative_name", ""),
            "detail": f"Strength: {n.get('strength_score', 0):.0f} | Maturity: {n.get('maturity', 'N/A')} | Expression: {n.get('best_expression', 'N/A')}"
        })

    alerts = query("""
        SELECT * FROM thesis_alerts
        WHERE date >= date('now', '-3 days') AND severity IN ('HIGH', 'CRITICAL')
        ORDER BY date DESC LIMIT 10
    """)

    return {
        "regime": regime,
        "heat_index": heat_index,
        "asset_classes": asset_classes,
        "cross_cutting": cross_cutting,
        "alerts": [{"type": a.get("alert_type", ""), "message": a.get("description", ""), "severity": a.get("severity", "")} for a in alerts],
    }


@router.get("/api/environment/alerts")
def environment_alerts():
    """Regime change alerts: large score movements in recent days."""
    return query("""
        SELECT * FROM thesis_alerts
        WHERE date >= date('now', '-7 days')
        ORDER BY date DESC, severity DESC
        LIMIT 20
    """)


# ═══════════════════════════════════════════════════════════════════════
# FUNNEL
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/funnel")
def funnel():
    """Funnel stage counts from convergence + signals + technical data."""
    universe = query("SELECT COUNT(*) as cnt FROM stock_universe")
    universe_count = universe[0]["cnt"] if universe else 903

    # Sector-passed: stocks in non-flagged sectors (rotation score > 30)
    sector_passed = query("""
        SELECT COUNT(DISTINCT su.symbol) as cnt
        FROM stock_universe su
        LEFT JOIN sector_rotation sr ON su.sector = sr.sector
            AND sr.date = (SELECT MAX(date) FROM sector_rotation)
        WHERE COALESCE(sr.rotation_score, 50) >= 30
    """)
    sector_count = sector_passed[0]["cnt"] if sector_passed else 0

    # Technical gate: stocks with technical_score > 40
    tech_passed = query("""
        SELECT COUNT(*) as cnt FROM technical_scores
        WHERE date = (SELECT MAX(date) FROM technical_scores)
        AND total_score >= 40
    """)
    tech_count = tech_passed[0]["cnt"] if tech_passed else 0

    # Conviction levels: combine convergence_signals + signals table
    # HIGH: convergence_score >= 60 OR (no convergence AND composite_score >= 65)
    # NOTABLE: convergence_score >= 55 (or composite >= 55) but not HIGH
    # WATCH: everything else with a score

    # Use composite_score from signals as the conviction metric.
    # Convergence scores exist but are in 0-30 range (limited module coverage),
    # so composite_score (50-100 range) is the reliable conviction signal right now.
    conviction_high = query("""
        SELECT COUNT(*) as cnt FROM signals s
        WHERE s.date = (SELECT MAX(date) FROM signals)
        AND s.composite_score >= 65
    """)

    conviction_notable = query("""
        SELECT COUNT(*) as cnt FROM signals s
        WHERE s.date = (SELECT MAX(date) FROM signals)
        AND s.composite_score >= 55 AND s.composite_score < 65
    """)

    conviction_watch = query("""
        SELECT COUNT(*) as cnt FROM signals s
        WHERE s.date = (SELECT MAX(date) FROM signals)
        AND s.composite_score < 55
    """)

    # Actionable = HIGH + NOTABLE conviction with valid trade setup (BUY signal)
    actionable = query("""
        SELECT COUNT(*) as cnt FROM signals s
        WHERE s.date = (SELECT MAX(date) FROM signals)
        AND s.composite_score >= 55
        AND s.signal = 'BUY'
    """)

    return {
        "universe": universe_count,
        "sector_passed": sector_count,
        "sector_flagged": universe_count - sector_count,
        "technical_passed": tech_count,
        "technical_flagged": sector_count - tech_count if sector_count > tech_count else 0,
        "conviction_high": conviction_high[0]["cnt"] if conviction_high else 0,
        "conviction_notable": conviction_notable[0]["cnt"] if conviction_notable else 0,
        "conviction_watch": conviction_watch[0]["cnt"] if conviction_watch else 0,
        "actionable": actionable[0]["cnt"] if actionable else 0,
    }


@router.get("/api/funnel/stage/3")
def funnel_stage_3():
    """Stage 3: Sector/Theme filter — sector cards with rotation data."""
    return query("""
        SELECT sr.sector, sr.rotation_score, sr.quadrant, sr.rs_ratio, sr.rs_momentum,
               COUNT(su.symbol) as stock_count,
               ws.thesis, ws.direction, ws.confidence as thesis_confidence
        FROM sector_rotation sr
        LEFT JOIN stock_universe su ON su.sector = sr.sector
        LEFT JOIN worldview_signals ws ON ws.symbol IS NULL
            AND ws.date = (SELECT MAX(date) FROM worldview_signals WHERE symbol IS NULL)
            AND ws.affected_sectors LIKE '%' || sr.sector || '%'
        WHERE sr.date = (SELECT MAX(date) FROM sector_rotation)
        GROUP BY sr.sector
        ORDER BY sr.rotation_score DESC
    """)


@router.get("/api/funnel/stage/4")
def funnel_stage_4():
    """Stage 4: Technical Gate — pass/fail with scores."""
    return query("""
        SELECT ts.symbol, su.sector, ts.total_score,
               ts.trend_score, ts.momentum_score,
               CASE WHEN ts.total_score >= 40 THEN 'passed' ELSE 'flagged' END as status,
               COALESCE(cs.convergence_score, s.composite_score) as best_score,
               cs.convergence_score, cs.conviction_level,
               s.composite_score, s.signal
        FROM technical_scores ts
        JOIN stock_universe su ON su.symbol = ts.symbol
        LEFT JOIN convergence_signals cs ON cs.symbol = ts.symbol
            AND cs.date = (SELECT MAX(date) FROM convergence_signals)
        LEFT JOIN signals s ON s.symbol = ts.symbol
            AND s.date = (SELECT MAX(date) FROM signals)
        WHERE ts.date = (SELECT MAX(date) FROM technical_scores)
        ORDER BY ts.total_score DESC
        LIMIT 500
    """)


@router.get("/api/funnel/stage/5")
def funnel_stage_5():
    """Stage 5: Conviction Filter — all scored stocks, ranked by best available score.

    Combines convergence_signals (when available) with signals table as fallback,
    so stocks without convergence data still appear.
    """
    return query("""
        SELECT
            COALESCE(cs.symbol, s.symbol) as symbol,
            su.name as company_name, su.sector, su.industry,
            cs.convergence_score,
            cs.conviction_level,
            cs.module_count,
            cs.forensic_blocked,
            cs.narrative,
            s.composite_score,
            s.signal,
            s.entry_price, s.stop_loss, s.target_price, s.rr_ratio,
            s.position_size_shares, s.position_size_dollars,
            s.composite_score as best_score,
            CASE
                WHEN s.composite_score >= 65 THEN 'HIGH'
                WHEN s.composite_score >= 55 THEN 'NOTABLE'
                ELSE 'WATCH'
            END as effective_conviction
        FROM signals s
        LEFT JOIN convergence_signals cs ON cs.symbol = s.symbol
            AND cs.date = (SELECT MAX(date) FROM convergence_signals)
        JOIN stock_universe su ON su.symbol = s.symbol
        WHERE s.date = (SELECT MAX(date) FROM signals)
        ORDER BY s.composite_score DESC
        LIMIT 200
    """)


@router.get("/api/funnel/overrides")
def funnel_overrides():
    """Active funnel overrides (not expired)."""
    return query("""
        SELECT * FROM funnel_overrides
        WHERE expires_at IS NULL OR expires_at > datetime('now')
        ORDER BY updated_at DESC
    """)


@router.post("/api/funnel/override")
def funnel_override_create(body: dict = Body(...)):
    """Create/replace a funnel override with 14-day default expiry."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO funnel_overrides (symbol, stage, action, reason, updated_at, expires_at)
            VALUES (?, ?, ?, ?, datetime('now'), COALESCE(?, datetime('now', '+14 days')))
        """, [body.get("symbol"), body.get("stage"), body.get("action"),
              body.get("reason"), body.get("expires_at")])
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@router.delete("/api/funnel/override/{symbol}/{stage}")
def funnel_override_delete(symbol: str, stage: str):
    """Delete a funnel override."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM funnel_overrides WHERE symbol = ? AND stage = ?", [symbol, stage])
        conn.commit()
        return {"status": "deleted"}
    finally:
        conn.close()


@router.get("/api/funnel/filter")
def funnel_filter(
    sectors: str = None, conviction: str = None,
    min_convergence: float = 0, min_module_count: int = 0,
    module: str = None, min_module_score: float = 0,
    limit: int = 100
):
    """Ad-hoc multi-factor screener on convergence data."""
    sql = """
        SELECT cs.*, su.name as company_name, su.sector, su.industry
        FROM convergence_signals cs
        JOIN stock_universe su ON su.symbol = cs.symbol
        WHERE cs.date = (SELECT MAX(date) FROM convergence_signals)
        AND cs.convergence_score >= ?
        AND cs.module_count >= ?
    """
    params: list = [min_convergence, min_module_count]

    if sectors:
        sector_list = [s.strip() for s in sectors.split(",")]
        placeholders = ",".join(["?"] * len(sector_list))
        sql += f" AND su.sector IN ({placeholders})"
        params.extend(sector_list)

    if conviction:
        conv_list = [c.strip() for c in conviction.split(",")]
        placeholders = ",".join(["?"] * len(conv_list))
        sql += f" AND cs.conviction_level IN ({placeholders})"
        params.extend(conv_list)

    if module and min_module_score > 0:
        safe_col = module.replace("-", "_")
        if safe_col.endswith("_score") and safe_col.replace("_score", "").replace("_", "").isalpha():
            sql += f" AND cs.{safe_col} >= ?"
            params.append(min_module_score)

    sql += " ORDER BY cs.convergence_score DESC LIMIT ?"
    params.append(limit)
    return query(sql, params)


# ═══════════════════════════════════════════════════════════════════════
# DOSSIER
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/dossier/{symbol}")
def dossier(symbol: str):
    """Full stock dossier: signals + convergence + price data.

    Works even when convergence data doesn't exist for the symbol —
    falls back to signals table as primary data source.
    """
    sig = query("SELECT * FROM signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    conv = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    prices = query("SELECT date, open, high, low, close, volume FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 120", [symbol])
    meta = query("SELECT * FROM stock_universe WHERE symbol = ?", [symbol])

    # Auto-generate thesis from multiple sources
    thesis_parts = []

    # 1. Convergence narrative (if available)
    if conv:
        c = conv[0]
        if c.get("narrative"):
            thesis_parts.append(c["narrative"])

    # 2. Signal direction from signals table
    if sig:
        s = sig[0]
        signal_type = s.get("signal", "NEUTRAL")
        composite = s.get("composite_score", 0) or 0
        rr = s.get("rr_ratio", 0) or 0
        thesis_parts.append(
            f"Signal: {signal_type} (composite {composite:.0f}, R:R {rr:.1f}x)"
        )

    # 3. Variant analysis
    variant = query("SELECT variant_score, thesis, details FROM variant_analysis WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    if variant:
        v = variant[0]
        vs = v.get("variant_score", 0) or 0
        vt = v.get("thesis") or ""
        if vt:
            thesis_parts.append(f"Variant: {vt} (score {vs:.0f})")
        else:
            thesis_parts.append(f"Variant: score {vs:.0f}")

    # 4. Worldview context
    worldview = query("SELECT narrative FROM worldview_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    if worldview and worldview[0].get("narrative"):
        thesis_parts.append(f"Worldview: {worldview[0]['narrative']}")

    # Build effective conviction from best available data
    effective_conviction = None
    best_score = None
    if conv:
        best_score = conv[0].get("convergence_score")
        effective_conviction = conv[0].get("conviction_level")
    elif sig:
        best_score = sig[0].get("composite_score")
        cs = best_score or 0
        if cs >= 65:
            effective_conviction = "HIGH"
        elif cs >= 55:
            effective_conviction = "NOTABLE"
        else:
            effective_conviction = "WATCH"

    return {
        "symbol": symbol,
        "meta": meta[0] if meta else {},
        "signal": sig[0] if sig else None,
        "convergence": conv[0] if conv else None,
        "prices": list(reversed(prices)),
        "thesis": " | ".join(thesis_parts) if thesis_parts else "No thesis generated yet.",
        "effective_conviction": effective_conviction,
        "best_score": best_score,
    }


@router.get("/api/dossier/{symbol}/evidence")
def dossier_evidence(symbol: str):
    """All module scores + top contributing details.

    Works when convergence doesn't exist — falls back to signals table
    and individual module tables for evidence.
    """
    conv = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])

    module_keys = [
        "main_signal_score", "smartmoney_score", "worldview_score", "variant_score",
        "research_score", "reddit_score", "news_displacement_score", "alt_data_score",
        "sector_expert_score", "foreign_intel_score", "pairs_score", "ma_score",
        "energy_intel_score", "prediction_markets_score", "pattern_options_score",
        "estimate_momentum_score", "ai_regulatory_score", "consensus_blindspots_score",
        "earnings_nlp_score", "gov_intel_score", "labor_intel_score",
        "supply_chain_score", "digital_exhaust_score", "pharma_intel_score",
    ]

    modules = {}
    top = []

    if conv:
        # Use convergence data as primary source
        c = conv[0]
        for k in module_keys:
            val = c.get(k)
            if val is not None:
                modules[k] = val
                if val > 0:
                    top.append({"module": k.replace("_score", ""), "score": val, "detail": ""})
    else:
        # Fallback: build evidence from signals + individual module tables
        sig = query("SELECT * FROM signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
        if sig:
            s = sig[0]
            # Map signals table columns to module-like scores
            score_map = {
                "macro_score": s.get("macro_score"),
                "technical_score": s.get("technical_score"),
                "fundamental_score": s.get("fundamental_score"),
                "composite_score": s.get("composite_score"),
            }
            for k, val in score_map.items():
                if val is not None:
                    modules[k] = val
                    if val > 0:
                        top.append({"module": k.replace("_score", ""), "score": val, "detail": ""})

        # Query individual module tables for additional evidence
        module_queries = [
            ("worldview", "SELECT thesis_alignment_score as val, narrative as detail FROM worldview_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("smartmoney", "SELECT conviction_score as val, top_holders as detail FROM smart_money_scores WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("estimate_momentum", "SELECT em_score as val, details as detail FROM estimate_momentum_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("consensus_blindspots", "SELECT cbs_score as val, narrative as detail FROM consensus_blindspot_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("pattern_options", "SELECT pattern_options_score as val, narrative as detail FROM pattern_options_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("energy_intel", "SELECT energy_intel_score as val, narrative as detail FROM energy_intel_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("ma", "SELECT ma_score as val, details as detail FROM ma_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("news_displacement", "SELECT displacement_score as val, details as detail FROM news_displacement WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("reddit", "SELECT score as val, NULL as detail FROM reddit_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("research", "SELECT score as val, details as detail FROM research_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("insider", "SELECT insider_score as val, narrative as detail FROM insider_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
            ("variant", "SELECT variant_score as val, upside_pct as detail FROM variant_analysis WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
        ]
        for mod_name, sql in module_queries:
            try:
                rows = query(sql, [symbol])
                if rows and rows[0].get("val") is not None:
                    val = rows[0]["val"]
                    modules[f"{mod_name}_score"] = val
                    if val > 0:
                        detail = str(rows[0].get("detail", "") or "")[:300]
                        top.append({"module": mod_name, "score": val, "detail": detail})
            except Exception:
                pass  # Table may not exist or have different schema

    # Enrich top contributors with details from source tables (for convergence path)
    if conv:
        for item in top:
            if item["detail"]:
                continue
            mod = item["module"]
            detail_row = None
            try:
                if mod == "variant":
                    detail_row = query("SELECT 'Score ' || CAST(variant_score AS TEXT) || ', upside ' || CAST(COALESCE(upside_pct,0) AS TEXT) || '%' as detail FROM variant_analysis WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                elif mod == "smartmoney":
                    detail_row = query("SELECT top_holders as detail FROM smart_money_scores WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                elif mod == "insider":
                    detail_row = query("SELECT narrative as detail FROM insider_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                elif mod == "worldview":
                    detail_row = query("SELECT narrative as detail FROM worldview_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                elif mod == "estimate_momentum":
                    detail_row = query("SELECT details as detail FROM estimate_momentum_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                elif mod == "consensus_blindspots":
                    detail_row = query("SELECT narrative as detail FROM consensus_blindspot_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                elif mod == "pattern_options":
                    detail_row = query("SELECT narrative as detail FROM pattern_options_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                elif mod == "energy_intel":
                    detail_row = query("SELECT narrative as detail FROM energy_intel_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                elif mod == "ma":
                    detail_row = query("SELECT details as detail FROM ma_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
                if detail_row and detail_row[0].get("detail"):
                    item["detail"] = str(detail_row[0]["detail"])[:300]
            except Exception:
                pass

    top.sort(key=lambda x: x["score"], reverse=True)
    return {"modules": modules, "top_contributors": top[:10]}


@router.get("/api/dossier/{symbol}/risks")
def dossier_risks(symbol: str):
    """Devil's advocate + signal conflicts + forensic alerts."""
    da = query("SELECT * FROM devils_advocate WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    conflicts = query("SELECT * FROM signal_conflicts WHERE symbol = ? ORDER BY date DESC LIMIT 5", [symbol])
    forensic = query("SELECT * FROM forensic_alerts WHERE symbol = ? ORDER BY date DESC LIMIT 5", [symbol])
    stress = query("""
        SELECT * FROM stress_test_results
        WHERE position_details LIKE ? OR worst_hit LIKE ?
        ORDER BY date DESC LIMIT 3
    """, [f"%{symbol}%", f"%{symbol}%"])

    return {
        "devils_advocate": da[0] if da else None,
        "conflicts": conflicts,
        "forensic": forensic,
        "stress": stress,
    }


@router.get("/api/dossier/{symbol}/fundamentals")
def dossier_fundamentals(symbol: str):
    """Fundamentals table pivoted to key-value."""
    rows = query("SELECT metric, value FROM fundamentals WHERE symbol = ?", [symbol])
    return {r["metric"]: r["value"] for r in rows}


@router.get("/api/dossier/{symbol}/catalysts")
def dossier_catalysts(symbol: str):
    """Earnings + M&A rumors + insider signals + regulatory."""
    earnings = query("SELECT * FROM earnings_calendar WHERE symbol = ? ORDER BY date DESC LIMIT 3", [symbol])
    rumors = query("SELECT * FROM ma_rumors WHERE symbol = ? ORDER BY date DESC LIMIT 3", [symbol])
    insider = query("SELECT * FROM insider_signals WHERE symbol = ? ORDER BY date DESC LIMIT 3", [symbol])
    regulatory = query("SELECT * FROM regulatory_signals WHERE symbol = ? ORDER BY date DESC LIMIT 3", [symbol])
    return {
        "earnings": earnings,
        "rumors": rumors,
        "insider": insider,
        "regulatory": regulatory,
    }


# ═══════════════════════════════════════════════════════════════════════
# CONVICTION BOARD
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/conviction-board")
def conviction_board():
    """Top 20 stocks by best available score, with signal data for sizing.

    Combines convergence_signals (preferred) with signals table fallback.
    No longer requires HIGH conviction — shows best stocks regardless.
    """
    # First: convergence stocks ranked by score (with signal enrichment)
    conv_stocks = query("""
        SELECT cs.symbol, cs.convergence_score as best_score, cs.conviction_level,
               cs.convergence_score, cs.module_count, cs.forensic_blocked, cs.narrative,
               su.name as company_name, su.sector, su.industry,
               s.signal, s.entry_price, s.stop_loss, s.target_price,
               s.rr_ratio, s.position_size_shares, s.position_size_dollars,
               s.composite_score,
               'convergence' as score_source
        FROM convergence_signals cs
        JOIN stock_universe su ON su.symbol = cs.symbol
        LEFT JOIN signals s ON s.symbol = cs.symbol
            AND s.date = (SELECT MAX(date) FROM signals WHERE symbol = cs.symbol)
        WHERE cs.date = (SELECT MAX(date) FROM convergence_signals)
        AND cs.forensic_blocked = 0
        ORDER BY cs.convergence_score DESC
        LIMIT 20
    """)

    # Second: signals-only stocks (no convergence) ranked by composite_score
    sig_stocks = query("""
        SELECT s.symbol, s.composite_score as best_score,
               CASE
                   WHEN s.composite_score >= 65 THEN 'HIGH'
                   WHEN s.composite_score >= 55 THEN 'NOTABLE'
                   ELSE 'WATCH'
               END as conviction_level,
               NULL as convergence_score, NULL as module_count,
               0 as forensic_blocked, NULL as narrative,
               su.name as company_name, su.sector, su.industry,
               s.signal, s.entry_price, s.stop_loss, s.target_price,
               s.rr_ratio, s.position_size_shares, s.position_size_dollars,
               s.composite_score,
               'signals' as score_source
        FROM signals s
        JOIN stock_universe su ON su.symbol = s.symbol
        LEFT JOIN convergence_signals cs ON cs.symbol = s.symbol
            AND cs.date = (SELECT MAX(date) FROM convergence_signals)
        WHERE s.date = (SELECT MAX(date) FROM signals)
        AND cs.symbol IS NULL
        ORDER BY s.composite_score DESC
        LIMIT 20
    """)

    # Merge and take top 20 by best_score
    combined = conv_stocks + sig_stocks
    combined.sort(key=lambda x: x.get("best_score", 0) or 0, reverse=True)
    return combined[:20]


@router.get("/api/conviction-board/blocked")
def conviction_blocked():
    """Forensic-blocked stocks that would otherwise be high conviction."""
    return query("""
        SELECT cs.*, su.name as company_name, su.sector,
               fa.alert_type, fa.severity as forensic_severity, fa.details as forensic_detail
        FROM convergence_signals cs
        JOIN stock_universe su ON su.symbol = cs.symbol
        LEFT JOIN forensic_alerts fa ON fa.symbol = cs.symbol
            AND fa.date = (SELECT MAX(date) FROM forensic_alerts WHERE symbol = cs.symbol)
        WHERE cs.date = (SELECT MAX(date) FROM convergence_signals)
        AND cs.forensic_blocked = 1
        ORDER BY cs.convergence_score DESC
    """)


# ═══════════════════════════════════════════════════════════════════════
# RISK
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/risk/overview")
def risk_overview():
    """Portfolio exposure + stress tests + signal conflicts + edge health.

    Returns useful data even with 0 portfolio positions by pulling from
    stress_test_results, signal_conflicts, and module_performance.
    """
    portfolio = query("SELECT * FROM portfolio WHERE status = 'open'")
    concentration = query("SELECT * FROM concentration_risk ORDER BY date DESC LIMIT 1")

    total_exposure = sum(
        (p.get("shares", 0) or 0) * (p.get("entry_price", 0) or 0) for p in portfolio
    )

    sectors = {}
    for p in portfolio:
        s = p.get("asset_class", "equity")
        sectors[s] = sectors.get(s, 0) + 1

    # Edge health: try module_ic_summary first, fallback to module_performance
    edge_health = query("""
        SELECT COUNT(*) as cnt FROM module_ic_summary
        WHERE regime = 'all' AND horizon_days = 20 AND mean_ic > 0
    """)
    edge_count = edge_health[0]["cnt"] if edge_health else 0

    if edge_count == 0:
        # Fallback: count modules with positive win rate from module_performance
        edge_perf = query("""
            SELECT COUNT(*) as cnt FROM module_performance
            WHERE regime = 'all' AND win_rate > 50
        """)
        edge_count = edge_perf[0]["cnt"] if edge_perf else 0

    # Stress test results (available even without portfolio)
    stress_tests = query("""
        SELECT * FROM stress_test_results
        ORDER BY date DESC LIMIT 5
    """)

    # Signal conflicts summary
    conflict_count = query("""
        SELECT COUNT(*) as cnt FROM signal_conflicts
        WHERE date = (SELECT MAX(date) FROM signal_conflicts)
    """)

    # Signal health: distribution of current signals
    signal_dist = query("""
        SELECT signal, COUNT(*) as cnt
        FROM signals
        WHERE date = (SELECT MAX(date) FROM signals)
        GROUP BY signal
        ORDER BY cnt DESC
    """)

    return {
        "total_exposure": total_exposure,
        "position_count": len(portfolio),
        "concentration": concentration[0] if concentration else {},
        "sector_breakdown": sectors,
        "edge_health": edge_count,
        "positions": portfolio,
        "stress_tests": stress_tests,
        "signal_conflicts_count": conflict_count[0]["cnt"] if conflict_count else 0,
        "signal_distribution": {r["signal"]: r["cnt"] for r in signal_dist},
    }


@router.get("/api/risk/edge-decay")
def risk_edge_decay():
    """Module IC trends — are modules losing predictive power?

    Falls back to module_performance if module_ic_summary is empty.
    """
    ic_data = query("""
        SELECT module, regime, horizon_days, mean_ic, std_ic,
               information_ratio, ic_positive_pct, n_dates, is_significant
        FROM module_ic_summary
        WHERE regime = 'all' AND horizon_days IN (20, 30)
        ORDER BY mean_ic DESC
    """)

    if ic_data:
        return {"source": "module_ic_summary", "data": ic_data}

    # Fallback: use module_performance data
    perf_data = query("""
        SELECT module_name as module, regime,
               win_rate, avg_return_5d, avg_return_20d, avg_return_30d,
               sharpe_ratio, max_drawdown, total_signals, observation_count,
               confidence_interval_low, confidence_interval_high
        FROM module_performance
        WHERE regime = 'all' AND sector = 'all'
        ORDER BY sharpe_ratio DESC
    """)

    if perf_data:
        return {"source": "module_performance", "data": perf_data}

    return {
        "source": "none",
        "data": [],
        "message": "No module performance data available yet. Run the daily pipeline to generate IC and performance metrics."
    }


@router.get("/api/risk/track-record")
def risk_track_record():
    """Monthly signal outcomes aggregated.

    Falls back to basic signal statistics if signal_outcomes is empty.
    """
    outcomes = query("""
        SELECT
            strftime('%Y-%m', signal_date) as month,
            COUNT(*) as total_signals,
            SUM(CASE WHEN return_5d > 0 THEN 1 ELSE 0 END) as wins_5d,
            SUM(CASE WHEN return_20d > 0 THEN 1 ELSE 0 END) as wins_20d,
            AVG(return_5d) as avg_return_5d,
            AVG(return_20d) as avg_return_20d,
            AVG(return_30d) as avg_return_30d
        FROM signal_outcomes
        WHERE signal_date IS NOT NULL
        GROUP BY month
        ORDER BY month DESC
        LIMIT 24
    """)

    if outcomes:
        return {"source": "signal_outcomes", "data": outcomes}

    # Fallback: show signal generation stats from signals table
    signal_stats = query("""
        SELECT
            strftime('%Y-%m', date) as month,
            COUNT(*) as total_signals,
            SUM(CASE WHEN signal IN ('BUY', 'STRONG BUY') THEN 1 ELSE 0 END) as buy_signals,
            SUM(CASE WHEN signal IN ('SELL', 'STRONG SELL') THEN 1 ELSE 0 END) as sell_signals,
            SUM(CASE WHEN signal = 'NEUTRAL' THEN 1 ELSE 0 END) as neutral_signals,
            AVG(composite_score) as avg_composite,
            AVG(rr_ratio) as avg_rr_ratio
        FROM signals
        WHERE date IS NOT NULL
        GROUP BY month
        ORDER BY month DESC
        LIMIT 24
    """)

    return {
        "source": "signals_summary",
        "data": signal_stats,
        "message": "Track record requires signal_outcomes data (generated after signals age 5-30 days). Showing signal generation stats instead."
    }


# ═══════════════════════════════════════════════════════════════════════
# JOURNAL
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/journal/open")
def journal_open():
    """Open positions with convergence delta since entry."""
    positions = query("SELECT * FROM portfolio WHERE status = 'open' ORDER BY entry_date DESC")
    for p in positions:
        sym = p.get("symbol")
        if not sym:
            continue
        # Current convergence
        curr = query("SELECT convergence_score FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [sym])
        p["current_convergence"] = curr[0]["convergence_score"] if curr else None

        # Entry convergence (closest to entry date)
        entry_date = p.get("entry_date")
        if entry_date:
            entry_conv = query("""
                SELECT convergence_score FROM convergence_signals
                WHERE symbol = ? AND date <= ? ORDER BY date DESC LIMIT 1
            """, [sym, entry_date])
            p["entry_convergence"] = entry_conv[0]["convergence_score"] if entry_conv else None
            if p.get("current_convergence") and p.get("entry_convergence"):
                p["score_delta"] = p["current_convergence"] - p["entry_convergence"]
            else:
                p["score_delta"] = None
        else:
            p["entry_convergence"] = None
            p["score_delta"] = None

        # Days held
        if entry_date:
            days_q = query("SELECT julianday('now') - julianday(?) as days", [entry_date])
            p["days_held"] = int(days_q[0]["days"]) if days_q else 0
        else:
            p["days_held"] = 0

        # Current price for P&L
        price = query("SELECT close FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 1", [sym])
        if price:
            p["current_price"] = price[0]["close"]
            entry_px = p.get("entry_price", 0) or 0
            if entry_px > 0:
                p["pnl_pct"] = ((price[0]["close"] - entry_px) / entry_px) * 100
            else:
                p["pnl_pct"] = 0
        else:
            p["current_price"] = None
            p["pnl_pct"] = 0

    return positions


@router.get("/api/journal/closed")
def journal_closed():
    """Closed positions with outcome attribution."""
    positions = query("SELECT * FROM portfolio WHERE status = 'closed' ORDER BY exit_date DESC LIMIT 50")
    for p in positions:
        entry_px = p.get("entry_price", 0) or 0
        exit_px = p.get("exit_price", 0) or 0
        if entry_px > 0 and exit_px > 0:
            p["return_pct"] = ((exit_px - entry_px) / entry_px) * 100
        else:
            p["return_pct"] = 0

        # Signal outcome if available
        sym = p.get("symbol")
        entry_date = p.get("entry_date")
        if sym and entry_date:
            outcome = query("""
                SELECT * FROM signal_outcomes
                WHERE symbol = ? AND signal_date = ?
                LIMIT 1
            """, [sym, entry_date])
            p["outcome"] = outcome[0] if outcome else None
        else:
            p["outcome"] = None

    return positions


@router.post("/api/journal/note")
def journal_note(body: dict = Body(...)):
    """Add a journal entry/note for a position."""
    conn = get_conn()
    try:
        # Get current convergence snapshot
        sym = body.get("symbol", "")
        snapshot = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [sym])
        snapshot_json = json.dumps(snapshot[0]) if snapshot else None

        conn.execute("""
            INSERT INTO journal_entries (portfolio_id, symbol, entry_type, content, convergence_snapshot)
            VALUES (?, ?, ?, ?, ?)
        """, [body.get("portfolio_id"), sym, body.get("entry_type", "note"),
              body.get("content", ""), snapshot_json])
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# PORTFOLIO CRUD
# ═══════════════════════════════════════════════════════════════════════

@router.post("/api/portfolio")
def portfolio_create(body: dict = Body(...)):
    """Create a new portfolio position."""
    conn = get_conn()
    try:
        # Capture entry convergence snapshot
        sym = body.get("symbol", "")
        conv = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [sym])
        entry_thesis = body.get("entry_thesis", "")
        if not entry_thesis and conv:
            entry_thesis = conv[0].get("narrative", "")
        snapshot_json = json.dumps(conv[0]) if conv else None

        cur = conn.execute("""
            INSERT INTO portfolio (symbol, shares, entry_price, entry_date, stop_loss, target_price, notes, asset_class, entry_thesis, entry_convergence_snapshot)
            VALUES (?, ?, ?, COALESCE(?, date('now')), ?, ?, ?, COALESCE(?, 'equity'), ?, ?)
        """, [sym, body.get("shares"), body.get("entry_price"),
              body.get("entry_date"), body.get("stop_loss"), body.get("target_price"),
              body.get("notes"), body.get("asset_class"), entry_thesis, snapshot_json])
        conn.commit()
        return {"status": "ok", "id": cur.lastrowid}
    finally:
        conn.close()


@router.put("/api/portfolio/{portfolio_id}")
def portfolio_update(portfolio_id: int, body: dict = Body(...)):
    """Update a portfolio position (stop_loss, target_price, notes)."""
    conn = get_conn()
    try:
        updates = []
        params = []
        for field in ["stop_loss", "target_price", "notes", "shares"]:
            if field in body:
                updates.append(f"{field} = ?")
                params.append(body[field])
        if not updates:
            return {"status": "no changes"}
        params.append(portfolio_id)
        conn.execute(f"UPDATE portfolio SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()


@router.post("/api/portfolio/{portfolio_id}/close")
def portfolio_close(portfolio_id: int, body: dict = Body(...)):
    """Close a portfolio position."""
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE portfolio SET status = 'closed', exit_price = ?, exit_date = COALESCE(?, date('now'))
            WHERE id = ?
        """, [body.get("exit_price"), body.get("exit_date"), portfolio_id])
        conn.commit()
        return {"status": "closed"}
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════
# CONVERGENCE HISTORY
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/convergence/{symbol}/history")
def convergence_history(symbol: str, from_date: str = None):
    """Convergence signal history for a symbol."""
    sql = "SELECT * FROM convergence_signals WHERE symbol = ?"
    params: list = [symbol]
    if from_date:
        sql += " AND date >= ?"
        params.append(from_date)
    sql += " ORDER BY date DESC LIMIT 90"
    return query(sql, params)
