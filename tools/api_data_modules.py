"""Data module routes — economic-indicators, insider, ai-exec, hyperliquid,
estimate-momentum, consensus-blindspots, MA, prediction-markets, regulatory."""
from fastapi import APIRouter
from tools.db import query
router = APIRouter()

# ── ECONOMIC INDICATORS ──
@router.get("/api/economic-indicators")
def economic_indicators(category: str = None):
    sql = "SELECT e.*, eh.heat_index FROM economic_dashboard e LEFT JOIN economic_heat_index eh ON e.date = eh.date WHERE e.date = (SELECT MAX(date) FROM economic_dashboard)"
    params = []
    if category:
        sql += " AND e.category = ?"; params.append(category)
    return query(sql, params)

@router.get("/api/economic-indicators/history/{indicator_id}")
def indicator_history(indicator_id: str, days: int = 365):
    return query("SELECT date, value FROM economic_dashboard WHERE indicator_id = ? ORDER BY date DESC LIMIT ?", [indicator_id, days])

@router.get("/api/economic-indicators/heat-index")
def heat_index():
    rows = query("SELECT * FROM economic_heat_index ORDER BY date DESC LIMIT 30")
    return {"current": rows[0] if rows else None, "history": rows}

# ── INSIDER TRADING ──
@router.get("/api/insider-trading")
def insider_signals(min_score: int = 0, days: int = 30):
    return query("SELECT * FROM insider_signals WHERE date >= date('now', ? || ' days') AND insider_score >= ? ORDER BY insider_score DESC", [f"-{days}", min_score])

@router.get("/api/insider-trading/cluster-buys")
def insider_cluster_buys(days: int = 30):
    return query("SELECT * FROM insider_signals WHERE date >= date('now', ? || ' days') AND cluster_buy = 1 ORDER BY insider_score DESC", [f"-{days}"])

@router.get("/api/insider-trading/{symbol}")
def insider_detail(symbol: str, days: int = 90):
    return {"signals": query("SELECT * FROM insider_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol]),
            "transactions": query("SELECT * FROM insider_transactions WHERE symbol = ? AND date >= date('now', ? || ' days') ORDER BY date DESC", [symbol, f"-{days}"])}

# ── AI EXECUTIVE TRACKER ──
@router.get("/api/ai-exec")
def ai_exec_signals(min_score: int = 0, days: int = 90):
    return query("SELECT * FROM ai_exec_signals WHERE date >= date('now', ? || ' days') AND score >= ? ORDER BY score DESC", [f"-{days}", min_score])

@router.get("/api/ai-exec/investments")
def ai_exec_investments(days: int = 180, exec_name: str = None):
    sql = "SELECT * FROM ai_exec_investments WHERE date >= date('now', ? || ' days')"
    params = [f"-{days}"]
    if exec_name:
        sql += " AND company = ?"; params.append(exec_name)
    return query(sql + " ORDER BY date DESC", params)

@router.get("/api/ai-exec/convergence")
def ai_exec_convergence():
    return query("SELECT symbol, COUNT(*) as exec_count, AVG(score) as avg_score FROM ai_exec_signals WHERE date >= date('now', '-90 days') GROUP BY symbol HAVING exec_count >= 2 ORDER BY avg_score DESC")

@router.get("/api/ai-exec/{symbol}")
def ai_exec_detail(symbol: str):
    return {"signals": query("SELECT * FROM ai_exec_signals WHERE symbol = ? ORDER BY date DESC", [symbol]),
            "investments": query("SELECT * FROM ai_exec_investments WHERE symbol = ? ORDER BY date DESC", [symbol])}

# ── HYPERLIQUID ──
@router.get("/api/hyperliquid/gaps")
def hl_gaps(weeks: int = 8):
    return query("SELECT * FROM hl_gap_signals ORDER BY date DESC LIMIT ?", [weeks * 7])

@router.get("/api/hyperliquid/snapshots/{ticker}")
def hl_snapshots(ticker: str, hours: int = 72):
    return query("SELECT * FROM hl_price_snapshots WHERE ticker = ? ORDER BY timestamp DESC LIMIT ?", [ticker, hours])

@router.get("/api/hyperliquid/deployer-spreads")
def hl_deployer_spreads(min_spread_bps: int = 0, hours: int = 72):
    return query("SELECT * FROM hl_deployer_spreads WHERE ABS(spread) >= ? ORDER BY date DESC", [min_spread_bps / 10000.0])

@router.get("/api/hyperliquid/book-depth")
def hl_book_depth():
    return query("SELECT * FROM hl_price_snapshots WHERE timestamp = (SELECT MAX(timestamp) FROM hl_price_snapshots)")

@router.get("/api/hyperliquid/accuracy")
def hl_accuracy():
    rows = query("SELECT COUNT(*) as total, SUM(CASE WHEN actual_gap IS NOT NULL THEN 1 ELSE 0 END) as backfilled, AVG(ABS(predicted_gap - actual_gap)) as avg_error FROM hl_gap_signals WHERE actual_gap IS NOT NULL")
    return rows[0] if rows else {}

# ── ESTIMATE MOMENTUM ──
@router.get("/api/estimate-momentum")
def estimate_momentum(min_score: int = 0, limit: int = 50, sector: str = None):
    sql = "SELECT em.*, su.sector, su.name FROM estimate_momentum_signals em JOIN stock_universe su ON em.symbol = su.symbol WHERE em.date >= date('now', '-7 days') AND em.em_score >= ?"
    params = [min_score]
    if sector:
        sql += " AND su.sector = ?"; params.append(sector)
    return query(sql + " ORDER BY em.em_score DESC LIMIT ?", params + [limit])

@router.get("/api/estimate-momentum/top-movers")
def estimate_momentum_top_movers():
    base = "SELECT em.*, su.sector, su.name FROM estimate_momentum_signals em JOIN stock_universe su ON em.symbol = su.symbol WHERE em.date >= date('now', '-7 days')"
    return {"upward": query(base + " ORDER BY em.revision_velocity DESC LIMIT 20"),
            "downward": query(base + " ORDER BY em.revision_velocity ASC LIMIT 20")}

@router.get("/api/estimate-momentum/sector-summary")
def estimate_momentum_sectors():
    return query("SELECT su.sector, COUNT(*) as count, AVG(em.em_score) as avg_score, AVG(em.revision_velocity) as avg_velocity FROM estimate_momentum_signals em JOIN stock_universe su ON em.symbol = su.symbol WHERE em.date >= date('now', '-7 days') GROUP BY su.sector ORDER BY avg_score DESC")

@router.get("/api/estimate-momentum/{symbol}")
def estimate_momentum_detail(symbol: str):
    return {"symbol": symbol,
            "signals": query("SELECT * FROM estimate_momentum_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol]),
            "snapshots": query("SELECT * FROM estimate_snapshots WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])}

# ── CONSENSUS BLINDSPOTS ──
@router.get("/api/consensus-blindspots")
def consensus_blindspots(min_score: int = 0, limit: int = 50):
    return query("SELECT * FROM consensus_blindspot_signals WHERE date >= date('now', '-7 days') AND symbol != '_MARKET' AND cbs_score >= ? ORDER BY cbs_score DESC LIMIT ?", [min_score, limit])

@router.get("/api/consensus-blindspots/cycle")
def sentiment_cycle():
    rows = query("SELECT * FROM consensus_blindspot_signals WHERE symbol = '_MARKET' ORDER BY date DESC LIMIT 30")
    return {"current": rows[0] if rows else None, "history": rows}

@router.get("/api/consensus-blindspots/fat-pitches")
def fat_pitches():
    return query("SELECT * FROM consensus_blindspot_signals WHERE date >= date('now', '-7 days') AND symbol != '_MARKET' AND gap_type = 'fat_pitch' ORDER BY cbs_score DESC")

@router.get("/api/consensus-blindspots/crowded")
def crowded_trades():
    return query("SELECT * FROM consensus_blindspot_signals WHERE date >= date('now', '-7 days') AND symbol != '_MARKET' AND gap_type = 'crowded_agreement' ORDER BY cbs_score ASC LIMIT 30")

@router.get("/api/consensus-blindspots/divergences")
def signal_divergences():
    return query("SELECT * FROM consensus_blindspot_signals WHERE date >= date('now', '-7 days') AND symbol != '_MARKET' AND gap_type IN ('contrarian_bullish', 'contrarian_bearish_warning') ORDER BY cbs_score DESC")

@router.get("/api/consensus-blindspots/{symbol}")
def consensus_blindspots_symbol(symbol: str):
    return {"current": (query("SELECT * FROM consensus_blindspot_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol]) or [None])[0],
            "history": query("SELECT * FROM consensus_blindspot_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])}

# ── M&A INTELLIGENCE ──
@router.get("/api/ma-signals")
def ma_signals(min_score: int = 0, days: int = 30):
    return query("SELECT * FROM ma_signals WHERE date >= date('now', ? || ' days') AND ma_score >= ? ORDER BY ma_score DESC", [f"-{days}", min_score])

@router.get("/api/ma-signals/top-targets")
def ma_top_targets():
    return query("SELECT * FROM ma_signals WHERE date >= date('now', '-7 days') AND ma_score >= 50 ORDER BY ma_score DESC LIMIT 20")

@router.get("/api/ma-signals/rumors")
def ma_rumors(days: int = 30):
    return query("SELECT * FROM ma_rumors WHERE date >= date('now', ? || ' days') ORDER BY date DESC", [f"-{days}"])

@router.get("/api/ma-signals/{symbol}")
def ma_detail(symbol: str):
    return {"signals": query("SELECT * FROM ma_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol]),
            "rumors": query("SELECT * FROM ma_rumors WHERE symbol = ? ORDER BY date DESC", [symbol])}

# ── PREDICTION MARKETS ──
@router.get("/api/prediction-markets")
def prediction_markets(min_score: int = 0, days: int = 7):
    return query("SELECT * FROM prediction_market_signals WHERE date >= date('now', ? || ' days') AND pm_score >= ? ORDER BY pm_score DESC", [f"-{days}", min_score])

@router.get("/api/prediction-markets/raw")
def prediction_markets_raw(category: str = None, days: int = 3):
    sql = "SELECT * FROM prediction_market_raw WHERE date >= date('now', ? || ' days')"
    params = [f"-{days}"]
    if category:
        sql += " AND category = ?"; params.append(category)
    return query(sql + " ORDER BY volume DESC", params)

@router.get("/api/prediction-markets/categories")
def prediction_market_categories():
    return query("SELECT category, COUNT(*) as count, AVG(probability) as avg_prob FROM prediction_market_raw WHERE date = (SELECT MAX(date) FROM prediction_market_raw) GROUP BY category ORDER BY count DESC")

# ── AI REGULATORY ──
@router.get("/api/regulatory")
def regulatory_signals(min_score: int = 0, days: int = 7):
    return query("SELECT * FROM regulatory_signals WHERE date >= date('now', ? || ' days') AND reg_score >= ? ORDER BY reg_score DESC", [f"-{days}", min_score])

@router.get("/api/regulatory/events")
def regulatory_events(source: str = None, category: str = None, jurisdiction: str = None, min_severity: int = 1, days: int = 14):
    sql = "SELECT * FROM regulatory_events WHERE date >= date('now', ? || ' days') AND severity >= ?"
    params = [f"-{days}", min_severity]
    if source:
        sql += " AND source = ?"; params.append(source)
    if category:
        sql += " AND category = ?"; params.append(category)
    if jurisdiction:
        sql += " AND jurisdiction = ?"; params.append(jurisdiction)
    return query(sql + " ORDER BY severity DESC, date DESC", params)

@router.get("/api/regulatory/categories")
def regulatory_categories():
    return query("SELECT category, COUNT(*) as count, AVG(severity) as avg_severity FROM regulatory_events WHERE date >= date('now', '-30 days') GROUP BY category ORDER BY avg_severity DESC")

@router.get("/api/regulatory/sources")
def regulatory_sources():
    return query("SELECT source, COUNT(*) as count FROM regulatory_events WHERE date >= date('now', '-30 days') GROUP BY source ORDER BY count DESC")

@router.get("/api/regulatory/jurisdictions")
def regulatory_jurisdictions():
    return query("SELECT jurisdiction, COUNT(*) as count, AVG(severity) as avg_severity FROM regulatory_events WHERE date >= date('now', '-30 days') GROUP BY jurisdiction ORDER BY avg_severity DESC")

@router.get("/api/regulatory/{symbol}")
def regulatory_symbol(symbol: str, days: int = 14):
    return {"signals": query("SELECT * FROM regulatory_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol]),
            "events": query("SELECT * FROM regulatory_events WHERE date >= date('now', ? || ' days') AND affected_symbols LIKE ? ORDER BY severity DESC", [f"-{days}", f"%{symbol}%"])}
