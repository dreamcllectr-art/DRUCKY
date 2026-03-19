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
    """Funnel stage counts from convergence + technical data."""
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

    # Conviction levels from convergence
    conviction = query("""
        SELECT conviction_level, COUNT(*) as cnt
        FROM convergence_signals
        WHERE date = (SELECT MAX(date) FROM convergence_signals)
        AND forensic_blocked = 0
        GROUP BY conviction_level
    """)
    conv_map = {r["conviction_level"]: r["cnt"] for r in conviction}

    # Actionable = HIGH conviction + not blocked
    actionable = query("""
        SELECT COUNT(*) as cnt FROM convergence_signals
        WHERE date = (SELECT MAX(date) FROM convergence_signals)
        AND conviction_level = 'HIGH' AND forensic_blocked = 0
    """)

    return {
        "universe": universe_count,
        "sector_passed": sector_count,
        "sector_flagged": universe_count - sector_count,
        "technical_passed": tech_count,
        "technical_flagged": sector_count - tech_count if sector_count > tech_count else 0,
        "conviction_high": conv_map.get("HIGH", 0),
        "conviction_notable": conv_map.get("NOTABLE", 0),
        "conviction_watch": conv_map.get("WATCH", 0),
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
               cs.convergence_score, cs.conviction_level
        FROM technical_scores ts
        JOIN stock_universe su ON su.symbol = ts.symbol
        LEFT JOIN convergence_signals cs ON cs.symbol = ts.symbol
            AND cs.date = (SELECT MAX(date) FROM convergence_signals)
        WHERE ts.date = (SELECT MAX(date) FROM technical_scores)
        ORDER BY ts.total_score DESC
        LIMIT 500
    """)


@router.get("/api/funnel/stage/5")
def funnel_stage_5():
    """Stage 5: Conviction Filter — ranked by convergence score."""
    return query("""
        SELECT cs.*, su.name as company_name, su.sector, su.industry,
               s.signal, s.entry_price, s.stop_loss, s.target_price, s.rr_ratio,
               s.position_size_shares, s.position_size_dollars
        FROM convergence_signals cs
        JOIN stock_universe su ON su.symbol = cs.symbol
        LEFT JOIN signals s ON s.symbol = cs.symbol
            AND s.date = (SELECT MAX(date) FROM signals WHERE symbol = cs.symbol)
        WHERE cs.date = (SELECT MAX(date) FROM convergence_signals)
        ORDER BY cs.convergence_score DESC
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
    """Full stock dossier: signals + convergence + price data."""
    sig = query("SELECT * FROM signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    conv = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    prices = query("SELECT date, open, high, low, close, volume FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 120", [symbol])
    meta = query("SELECT * FROM stock_universe WHERE symbol = ?", [symbol])

    # Auto-generate thesis from convergence narrative + worldview + variant
    thesis_parts = []
    if conv:
        c = conv[0]
        if c.get("narrative"):
            thesis_parts.append(c["narrative"])
    variant = query("SELECT thesis FROM variant_analysis WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    if variant and variant[0].get("thesis"):
        thesis_parts.append(f"Variant: {variant[0]['thesis']}")

    return {
        "symbol": symbol,
        "meta": meta[0] if meta else {},
        "signal": sig[0] if sig else None,
        "convergence": conv[0] if conv else None,
        "prices": list(reversed(prices)),
        "thesis": " | ".join(thesis_parts) if thesis_parts else "No thesis generated yet.",
    }


@router.get("/api/dossier/{symbol}/evidence")
def dossier_evidence(symbol: str):
    """All 29 module scores + top contributing details."""
    conv = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    if not conv:
        return {"modules": {}, "top_contributors": []}

    c = conv[0]
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
    for k in module_keys:
        val = c.get(k)
        if val is not None:
            modules[k] = val
            if val > 0:
                top.append({"module": k.replace("_score", ""), "score": val, "detail": ""})

    # Enrich top contributors with details from source tables
    for item in top:
        mod = item["module"]
        detail_row = None
        if mod == "variant":
            detail_row = query("SELECT thesis as detail FROM variant_analysis WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
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
    """HIGH conviction stocks with signal data for sizing."""
    return query("""
        SELECT cs.*, su.name as company_name, su.sector,
               s.signal, s.entry_price, s.stop_loss, s.target_price,
               s.rr_ratio, s.position_size_shares, s.position_size_dollars
        FROM convergence_signals cs
        JOIN stock_universe su ON su.symbol = cs.symbol
        LEFT JOIN signals s ON s.symbol = cs.symbol
            AND s.date = (SELECT MAX(date) FROM signals WHERE symbol = cs.symbol)
        WHERE cs.date = (SELECT MAX(date) FROM convergence_signals)
        AND cs.conviction_level = 'HIGH' AND cs.forensic_blocked = 0
        ORDER BY cs.convergence_score DESC
    """)


@router.get("/api/conviction-board/blocked")
def conviction_blocked():
    """Forensic-blocked stocks that would otherwise be HIGH conviction."""
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
    """Portfolio exposure + concentration metrics."""
    portfolio = query("SELECT * FROM portfolio WHERE status = 'open'")
    concentration = query("SELECT * FROM concentration_risk ORDER BY date DESC LIMIT 1")

    total_exposure = sum(
        (p.get("shares", 0) or 0) * (p.get("entry_price", 0) or 0) for p in portfolio
    )

    sectors = {}
    for p in portfolio:
        s = p.get("asset_class", "equity")
        sectors[s] = sectors.get(s, 0) + 1

    # Edge health: count of modules with positive IC
    edge_health = query("""
        SELECT COUNT(*) as cnt FROM module_ic_summary
        WHERE regime = 'all' AND horizon_days = 20 AND mean_ic > 0
    """)

    return {
        "total_exposure": total_exposure,
        "position_count": len(portfolio),
        "concentration": concentration[0] if concentration else {},
        "sector_breakdown": sectors,
        "edge_health": edge_health[0]["cnt"] if edge_health else 0,
        "positions": portfolio,
    }


@router.get("/api/risk/edge-decay")
def risk_edge_decay():
    """Module IC trends — are modules losing predictive power?"""
    return query("""
        SELECT module, regime, horizon_days, mean_ic, std_ic,
               information_ratio, ic_positive_pct, n_dates, is_significant
        FROM module_ic_summary
        WHERE regime = 'all' AND horizon_days IN (20, 30)
        ORDER BY mean_ic DESC
    """)


@router.get("/api/risk/track-record")
def risk_track_record():
    """Monthly signal outcomes aggregated."""
    return query("""
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
