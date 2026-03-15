"""Intelligence module routes — memos, signal-conflicts, stress-test,
thesis-monitor, pairs, reports, trading-ideas."""

from fastapi import APIRouter
from tools.db import query

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# PAIRS TRADING
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/pairs")
def pairs(signal_type: str = None, sector: str = None, limit: int = 100):
    sql = "SELECT * FROM pair_signals WHERE date >= date('now', '-7 days')"
    params = []
    if signal_type:
        sql += " AND signal_type = ?"
        params.append(signal_type)
    if sector:
        sql += " AND sector = ?"
        params.append(sector)
    sql += " ORDER BY pairs_score DESC LIMIT ?"
    params.append(limit)
    return query(sql, params)


@router.get("/api/pairs/relationships")
def pair_relationships(sector: str = None, limit: int = 200):
    sql = "SELECT * FROM pair_relationships WHERE 1=1"
    params = []
    if sector:
        sql += " AND sector = ?"
        params.append(sector)
    sql += " ORDER BY coint_pvalue ASC LIMIT ?"
    params.append(limit)
    return query(sql, params)


@router.get("/api/pairs/spread/{symbol_a}/{symbol_b}")
def pair_spread(symbol_a: str, symbol_b: str, days: int = 120):
    return query("""
        SELECT * FROM pair_spreads
        WHERE symbol_a = ? AND symbol_b = ?
        ORDER BY date DESC LIMIT ?
    """, [symbol_a, symbol_b, days])


@router.get("/api/pairs/{symbol}")
def pairs_for_symbol(symbol: str):
    rels = query("""
        SELECT * FROM pair_relationships
        WHERE symbol_a = ? OR symbol_b = ?
    """, [symbol, symbol])
    sigs = query("""
        SELECT * FROM pair_signals
        WHERE (symbol_a = ? OR symbol_b = ? OR runner_symbol = ?)
          AND date >= date('now', '-7 days')
    """, [symbol, symbol, symbol])
    return {"relationships": rels, "signals": sigs}


# ═══════════════════════════════════════════════════════════════════════
# TRADING IDEAS (Thematic Scanner)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/trading-ideas")
def trading_ideas(theme: str = None, min_score: int = 0):
    sql = "SELECT * FROM thematic_ideas WHERE score >= ?"
    params = [min_score]
    if theme:
        sql += " AND theme = ?"
        params.append(theme)
    sql += " ORDER BY score DESC LIMIT 50"
    return query(sql, params)


@router.get("/api/trading-ideas/themes")
def trading_ideas_themes():
    return query("""
        SELECT theme, COUNT(*) as count, AVG(score) as avg_score
        FROM thematic_ideas GROUP BY theme ORDER BY avg_score DESC
    """)


@router.get("/api/trading-ideas/top")
def trading_ideas_top(limit: int = 10):
    return query("SELECT * FROM thematic_ideas ORDER BY score DESC LIMIT ?", [limit])


@router.get("/api/trading-ideas/theme/{theme}")
def trading_ideas_theme(theme: str):
    return query("SELECT * FROM thematic_ideas WHERE theme = ? ORDER BY score DESC", [theme])


@router.get("/api/trading-ideas/sub-theme/{sub_theme}")
def trading_ideas_subtheme(sub_theme: str):
    return query("SELECT * FROM thematic_ideas WHERE details LIKE ? ORDER BY score DESC", [f"%{sub_theme}%"])


@router.get("/api/trading-ideas/history/{symbol}")
def trading_ideas_history(symbol: str, days: int = 30):
    return query("""
        SELECT * FROM thematic_ideas
        WHERE symbols LIKE ? AND date >= date('now', ? || ' days')
        ORDER BY date DESC
    """, [f"%{symbol}%", f"-{days}"])


@router.get("/api/trading-ideas/{symbol}")
def trading_ideas_detail(symbol: str):
    return query("SELECT * FROM thematic_ideas WHERE symbols LIKE ? ORDER BY date DESC", [f"%{symbol}%"])


# ═══════════════════════════════════════════════════════════════════════
# INVESTMENT MEMOS & INTELLIGENCE REPORTS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/report/list")
def report_list():
    return query("""
        SELECT id, topic, topic_type, expert_type, generated_at, regime, symbols_covered
        FROM intelligence_reports ORDER BY generated_at DESC LIMIT 50
    """)


@router.get("/api/report/latest")
def report_latest(topic: str):
    rows = query("""
        SELECT * FROM intelligence_reports
        WHERE topic = ? ORDER BY generated_at DESC LIMIT 1
    """, [topic])
    return rows[0] if rows else {}


@router.post("/api/report/generate")
def report_generate(topic: str):
    from tools.intelligence_report import generate_memo
    result = generate_memo(topic)
    if result:
        return {"status": "ok", "symbol": topic, "memo": result["memo"]}
    return {"status": "error", "message": f"Could not generate memo for {topic}"}


@router.get("/api/memos")
def memos(limit: int = 20):
    """Get all investment memos."""
    return query("""
        SELECT id, topic as symbol, generated_at, regime,
               report_html, metadata
        FROM intelligence_reports
        WHERE topic_type = 'investment_memo'
        ORDER BY generated_at DESC LIMIT ?
    """, [limit])


@router.get("/api/memos/{symbol}")
def memo_detail(symbol: str):
    """Get the latest memo for a specific symbol."""
    rows = query("""
        SELECT * FROM intelligence_reports
        WHERE topic = ? AND topic_type = 'investment_memo'
        ORDER BY generated_at DESC LIMIT 1
    """, [symbol])
    return rows[0] if rows else {}


# ═══════════════════════════════════════════════════════════════════════
# SIGNAL CONFLICTS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/signal-conflicts")
def signal_conflicts_list(severity: str = None, limit: int = 100):
    """Get all cross-signal conflicts."""
    sql = """
        SELECT * FROM signal_conflicts
        WHERE date = (SELECT MAX(date) FROM signal_conflicts)
    """
    params = []
    if severity:
        sql += " AND severity = ?"
        params.append(severity)
    sql += " ORDER BY score_gap DESC LIMIT ?"
    params.append(limit)
    return query(sql, params)


@router.get("/api/signal-conflicts/summary")
def signal_conflicts_summary():
    """Conflict type breakdown."""
    return query("""
        SELECT conflict_type, severity, COUNT(*) as count,
               AVG(score_gap) as avg_gap
        FROM signal_conflicts
        WHERE date = (SELECT MAX(date) FROM signal_conflicts)
        GROUP BY conflict_type, severity
        ORDER BY count DESC
    """)


@router.get("/api/signal-conflicts/{symbol}")
def signal_conflicts_symbol(symbol: str):
    """Get conflicts for a specific symbol."""
    return query("""
        SELECT * FROM signal_conflicts
        WHERE symbol = ? ORDER BY date DESC LIMIT 20
    """, [symbol])


# ═══════════════════════════════════════════════════════════════════════
# STRESS TESTING
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/stress-test")
def stress_test_results():
    """Get latest stress test results across all scenarios."""
    return query("""
        SELECT * FROM stress_test_results
        WHERE date = (SELECT MAX(date) FROM stress_test_results)
        ORDER BY portfolio_impact_pct ASC
    """)


@router.get("/api/stress-test/concentration")
def concentration_risk():
    """Get current portfolio concentration risk."""
    rows = query("SELECT * FROM concentration_risk ORDER BY date DESC LIMIT 1")
    return rows[0] if rows else {}


@router.get("/api/stress-test/backtest")
def stress_backtest():
    """Get historical backtest calibration results."""
    return query("SELECT * FROM stress_backtest_results ORDER BY crisis, sector_etf")


@router.get("/api/stress-test/calibration")
def stress_calibration():
    """Get calibrated vs assumed impact comparison."""
    return query("SELECT * FROM stress_calibration ORDER BY scenario, sector")


@router.get("/api/stress-test/{scenario}")
def stress_test_scenario_detail(scenario: str):
    """Get detailed position-level impacts for a scenario."""
    rows = query("""
        SELECT * FROM stress_test_results
        WHERE scenario = ? ORDER BY date DESC LIMIT 1
    """, [scenario])
    return rows[0] if rows else {}


# ═══════════════════════════════════════════════════════════════════════
# THESIS MONITOR
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/thesis-monitor")
def thesis_monitor_alerts(severity: str = None, days: int = 7):
    """Get thesis break/change alerts."""
    sql = "SELECT * FROM thesis_alerts WHERE date >= date('now', ? || ' days')"
    params = [f"-{days}"]
    if severity:
        sql += " AND severity = ?"
        params.append(severity)
    sql += " ORDER BY date DESC"
    return query(sql, params)


@router.get("/api/thesis-monitor/snapshots")
def thesis_snapshots(days: int = 30):
    """Get thesis evolution over time."""
    return query("""
        SELECT * FROM thesis_snapshots
        WHERE date >= date('now', ? || ' days')
        ORDER BY date DESC, thesis
    """, [f"-{days}"])


@router.get("/api/thesis-monitor/{thesis}")
def thesis_detail(thesis: str):
    """Get history for a specific thesis."""
    snapshots = query("SELECT * FROM thesis_snapshots WHERE thesis = ? ORDER BY date DESC LIMIT 30", [thesis])
    alerts = query("SELECT * FROM thesis_alerts WHERE thesis = ? ORDER BY date DESC LIMIT 20", [thesis])
    return {"snapshots": snapshots, "alerts": alerts}
