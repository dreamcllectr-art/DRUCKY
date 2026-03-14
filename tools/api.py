"""FastAPI application — serves all /api/* routes for the dashboard.

This file was regenerated after iCloud corruption. It includes:
  - Core endpoints (macro, signals, convergence, prices, asset detail)
  - All 5 new module endpoints (memos, conflicts, stress test, thesis monitor, reports)
  - All existing module endpoints matching dashboard/src/lib/api.ts

Architecture: thin query layer over SQLite. No business logic here —
all intelligence lives in tools/*.py modules.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tools.db import init_db, query

init_db()

app = FastAPI(title="Druckenmiller Alpha System", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════
# CORE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/macro")
def macro():
    rows = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    return rows[0] if rows else {}


@app.get("/api/macro/history")
def macro_history():
    return query("SELECT date, total_score, regime FROM macro_scores ORDER BY date DESC LIMIT 90")


@app.get("/api/breadth")
def breadth():
    rows = query("SELECT * FROM market_breadth ORDER BY date DESC LIMIT 1")
    return rows[0] if rows else {}


@app.get("/api/signals")
def signals(sector: str = None, signal: str = None, limit: int = 100):
    sql = """
        SELECT s.* FROM signals s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM signals GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
        WHERE 1=1
    """
    params = []
    if sector:
        sql += " AND s.sector = ?"
        params.append(sector)
    if signal:
        sql += " AND s.signal = ?"
        params.append(signal)
    sql += " ORDER BY s.composite_score DESC LIMIT ?"
    params.append(limit)
    return query(sql, params)


@app.get("/api/signals/summary")
def signals_summary():
    return query("""
        SELECT signal, COUNT(*) as count FROM signals
        WHERE date = (SELECT MAX(date) FROM signals)
        GROUP BY signal ORDER BY count DESC
    """)


@app.get("/api/asset/{symbol}")
def asset_detail(symbol: str):
    tech = query("SELECT * FROM technical_scores WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    fund = query("SELECT metric, value FROM fundamentals WHERE symbol = ?", [symbol])
    universe = query("SELECT * FROM stock_universe WHERE symbol = ?", [symbol])
    conv = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    da = query("SELECT * FROM devils_advocate WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])

    return {
        "symbol": symbol,
        "info": universe[0] if universe else {},
        "technical": tech[0] if tech else {},
        "fundamentals": {r["metric"]: r["value"] for r in fund},
        "convergence": conv[0] if conv else {},
        "devils_advocate": da[0] if da else {},
    }


@app.get("/api/prices/{symbol}")
def prices(symbol: str, days: int = 365):
    return query("""
        SELECT date, open, high, low, close, volume
        FROM price_data WHERE symbol = ?
        ORDER BY date DESC LIMIT ?
    """, [symbol, days])


@app.get("/api/watchlist")
def watchlist():
    return query("SELECT * FROM watchlist")


@app.get("/api/portfolio")
def portfolio():
    return query("SELECT * FROM portfolio")


# ═══════════════════════════════════════════════════════════════════════
# CONVERGENCE
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/convergence")
def convergence():
    return query("""
        SELECT * FROM convergence_signals
        WHERE date = (SELECT MAX(date) FROM convergence_signals)
        ORDER BY convergence_score DESC
    """)


@app.get("/api/convergence/{symbol}")
def convergence_symbol(symbol: str):
    rows = query("""
        SELECT * FROM convergence_signals
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    return rows[0] if rows else {}


# ═══════════════════════════════════════════════════════════════════════
# DISPLACEMENT / ALT DATA / SECTOR EXPERTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/displacement")
def displacement(days: int = 7):
    return query("""
        SELECT * FROM news_displacement
        WHERE date >= date('now', ? || ' days') AND status = 'active'
        ORDER BY displacement_score DESC
    """, [f"-{days}"])


@app.get("/api/displacement/{symbol}")
def displacement_symbol(symbol: str):
    return query("SELECT * FROM news_displacement WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])


@app.get("/api/alt-data")
def alt_data(days: int = 7):
    return query("""
        SELECT * FROM alt_data_scores
        WHERE date >= date('now', ? || ' days')
        ORDER BY score DESC
    """, [f"-{days}"])


@app.get("/api/sector-experts")
def sector_experts():
    return query("""
        SELECT * FROM sector_expert_signals
        WHERE date >= date('now', '-7 days')
        ORDER BY score DESC
    """)


@app.get("/api/sector-experts/{symbol}")
def sector_experts_symbol(symbol: str):
    return query("SELECT * FROM sector_expert_signals WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])


# ═══════════════════════════════════════════════════════════════════════
# PAIRS TRADING
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/pairs")
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


@app.get("/api/pairs/relationships")
def pair_relationships(sector: str = None, limit: int = 200):
    sql = "SELECT * FROM pair_relationships WHERE 1=1"
    params = []
    if sector:
        sql += " AND sector = ?"
        params.append(sector)
    sql += " ORDER BY coint_pvalue ASC LIMIT ?"
    params.append(limit)
    return query(sql, params)


@app.get("/api/pairs/spread/{symbol_a}/{symbol_b}")
def pair_spread(symbol_a: str, symbol_b: str, days: int = 120):
    return query("""
        SELECT * FROM pair_spreads
        WHERE symbol_a = ? AND symbol_b = ?
        ORDER BY date DESC LIMIT ?
    """, [symbol_a, symbol_b, days])


@app.get("/api/pairs/{symbol}")
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
# ECONOMIC INDICATORS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/economic-indicators")
def economic_indicators(category: str = None):
    sql = """
        SELECT e.*, eh.heat_index, eh.regime as heat_regime
        FROM economic_dashboard e
        LEFT JOIN economic_heat_index eh ON e.date = eh.date
        WHERE e.date = (SELECT MAX(date) FROM economic_dashboard)
    """
    params = []
    if category:
        sql += " AND e.category = ?"
        params.append(category)
    return query(sql, params)


@app.get("/api/economic-indicators/history/{indicator_id}")
def indicator_history(indicator_id: str, days: int = 365):
    return query("""
        SELECT date, value FROM economic_dashboard
        WHERE indicator_id = ? ORDER BY date DESC LIMIT ?
    """, [indicator_id, days])


@app.get("/api/economic-indicators/heat-index")
def heat_index():
    rows = query("SELECT * FROM economic_heat_index ORDER BY date DESC LIMIT 30")
    return {"current": rows[0] if rows else None, "history": rows}


# ═══════════════════════════════════════════════════════════════════════
# INSIDER TRADING
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/insider-trading")
def insider_signals(min_score: int = 0, days: int = 30):
    return query("""
        SELECT * FROM insider_signals
        WHERE date >= date('now', ? || ' days') AND insider_score >= ?
        ORDER BY insider_score DESC
    """, [f"-{days}", min_score])


@app.get("/api/insider-trading/cluster-buys")
def insider_cluster_buys(days: int = 30):
    return query("""
        SELECT * FROM insider_signals
        WHERE date >= date('now', ? || ' days') AND cluster_buy = 1
        ORDER BY insider_score DESC
    """, [f"-{days}"])


@app.get("/api/insider-trading/{symbol}")
def insider_detail(symbol: str, days: int = 90):
    signals = query("SELECT * FROM insider_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])
    txns = query("""
        SELECT * FROM insider_transactions
        WHERE symbol = ? AND date >= date('now', ? || ' days')
        ORDER BY date DESC
    """, [symbol, f"-{days}"])
    return {"signals": signals, "transactions": txns}


# ═══════════════════════════════════════════════════════════════════════
# AI EXECUTIVE TRACKER
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/ai-exec")
def ai_exec_signals(min_score: int = 0, days: int = 90):
    return query("""
        SELECT * FROM ai_exec_signals
        WHERE date >= date('now', ? || ' days') AND score >= ?
        ORDER BY score DESC
    """, [f"-{days}", min_score])


@app.get("/api/ai-exec/investments")
def ai_exec_investments(days: int = 180, exec_name: str = None):
    sql = "SELECT * FROM ai_exec_investments WHERE date >= date('now', ? || ' days')"
    params = [f"-{days}"]
    if exec_name:
        sql += " AND company = ?"
        params.append(exec_name)
    sql += " ORDER BY date DESC"
    return query(sql, params)


@app.get("/api/ai-exec/convergence")
def ai_exec_convergence():
    return query("""
        SELECT symbol, COUNT(*) as exec_count, AVG(score) as avg_score
        FROM ai_exec_signals WHERE date >= date('now', '-90 days')
        GROUP BY symbol HAVING exec_count >= 2
        ORDER BY avg_score DESC
    """)


@app.get("/api/ai-exec/{symbol}")
def ai_exec_detail(symbol: str):
    signals = query("SELECT * FROM ai_exec_signals WHERE symbol = ? ORDER BY date DESC", [symbol])
    investments = query("SELECT * FROM ai_exec_investments WHERE symbol = ? ORDER BY date DESC", [symbol])
    return {"signals": signals, "investments": investments}


# ═══════════════════════════════════════════════════════════════════════
# HYPERLIQUID
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/hyperliquid/gaps")
def hl_gaps(weeks: int = 8):
    return query("""
        SELECT * FROM hl_gap_signals
        ORDER BY date DESC LIMIT ?
    """, [weeks * 7])


@app.get("/api/hyperliquid/snapshots/{ticker}")
def hl_snapshots(ticker: str, hours: int = 72):
    return query("""
        SELECT * FROM hl_price_snapshots
        WHERE ticker = ? ORDER BY timestamp DESC LIMIT ?
    """, [ticker, hours])


@app.get("/api/hyperliquid/deployer-spreads")
def hl_deployer_spreads(min_spread_bps: int = 0, hours: int = 72):
    return query("""
        SELECT * FROM hl_deployer_spreads
        WHERE ABS(spread) >= ? ORDER BY date DESC
    """, [min_spread_bps / 10000.0])


@app.get("/api/hyperliquid/book-depth")
def hl_book_depth():
    return query("SELECT * FROM hl_price_snapshots WHERE timestamp = (SELECT MAX(timestamp) FROM hl_price_snapshots)")


@app.get("/api/hyperliquid/accuracy")
def hl_accuracy():
    rows = query("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN actual_gap IS NOT NULL THEN 1 ELSE 0 END) as backfilled,
               AVG(ABS(predicted_gap - actual_gap)) as avg_error
        FROM hl_gap_signals WHERE actual_gap IS NOT NULL
    """)
    return rows[0] if rows else {}


# ═══════════════════════════════════════════════════════════════════════
# ESTIMATE MOMENTUM
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/estimate-momentum")
def estimate_momentum(min_score: int = 0, limit: int = 50, sector: str = None):
    sql = """
        SELECT em.*, su.sector, su.name FROM estimate_momentum_signals em
        JOIN stock_universe su ON em.symbol = su.symbol
        WHERE em.date >= date('now', '-7 days') AND em.em_score >= ?
    """
    params = [min_score]
    if sector:
        sql += " AND su.sector = ?"
        params.append(sector)
    sql += " ORDER BY em.em_score DESC LIMIT ?"
    params.append(limit)
    return query(sql, params)


@app.get("/api/estimate-momentum/{symbol}")
def estimate_momentum_detail(symbol: str):
    signals = query("SELECT * FROM estimate_momentum_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])
    snapshots = query("SELECT * FROM estimate_snapshots WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])
    return {"symbol": symbol, "signals": signals, "snapshots": snapshots}


@app.get("/api/estimate-momentum/top-movers")
def estimate_momentum_top_movers():
    up = query("""
        SELECT em.*, su.sector, su.name FROM estimate_momentum_signals em
        JOIN stock_universe su ON em.symbol = su.symbol
        WHERE em.date >= date('now', '-7 days')
        ORDER BY em.revision_velocity DESC LIMIT 20
    """)
    down = query("""
        SELECT em.*, su.sector, su.name FROM estimate_momentum_signals em
        JOIN stock_universe su ON em.symbol = su.symbol
        WHERE em.date >= date('now', '-7 days')
        ORDER BY em.revision_velocity ASC LIMIT 20
    """)
    return {"upward": up, "downward": down}


@app.get("/api/estimate-momentum/sector-summary")
def estimate_momentum_sectors():
    return query("""
        SELECT su.sector, COUNT(*) as count,
               AVG(em.em_score) as avg_score,
               AVG(em.revision_velocity) as avg_velocity
        FROM estimate_momentum_signals em
        JOIN stock_universe su ON em.symbol = su.symbol
        WHERE em.date >= date('now', '-7 days')
        GROUP BY su.sector ORDER BY avg_score DESC
    """)


# ═══════════════════════════════════════════════════════════════════════
# CONSENSUS BLINDSPOTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/consensus-blindspots")
def consensus_blindspots(min_score: int = 0, limit: int = 50):
    return query("""
        SELECT * FROM consensus_blindspot_signals
        WHERE date >= date('now', '-7 days') AND symbol != '_MARKET'
          AND cbs_score >= ?
        ORDER BY cbs_score DESC LIMIT ?
    """, [min_score, limit])


@app.get("/api/consensus-blindspots/cycle")
def sentiment_cycle():
    rows = query("""
        SELECT * FROM consensus_blindspot_signals
        WHERE symbol = '_MARKET' ORDER BY date DESC LIMIT 30
    """)
    return {"current": rows[0] if rows else None, "history": rows}


@app.get("/api/consensus-blindspots/fat-pitches")
def fat_pitches():
    return query("""
        SELECT * FROM consensus_blindspot_signals
        WHERE date >= date('now', '-7 days')
          AND symbol != '_MARKET'
          AND gap_type = 'fat_pitch'
        ORDER BY cbs_score DESC
    """)


@app.get("/api/consensus-blindspots/crowded")
def crowded_trades():
    return query("""
        SELECT * FROM consensus_blindspot_signals
        WHERE date >= date('now', '-7 days')
          AND symbol != '_MARKET'
          AND gap_type = 'crowded_agreement'
        ORDER BY cbs_score ASC LIMIT 30
    """)


@app.get("/api/consensus-blindspots/divergences")
def signal_divergences():
    return query("""
        SELECT * FROM consensus_blindspot_signals
        WHERE date >= date('now', '-7 days')
          AND symbol != '_MARKET'
          AND gap_type IN ('contrarian_bullish', 'contrarian_bearish_warning')
        ORDER BY cbs_score DESC
    """)


@app.get("/api/consensus-blindspots/{symbol}")
def consensus_blindspots_symbol(symbol: str):
    current = query("SELECT * FROM consensus_blindspot_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    history = query("SELECT * FROM consensus_blindspot_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])
    return {"current": current[0] if current else None, "history": history}


# ═══════════════════════════════════════════════════════════════════════
# M&A INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/ma-signals")
def ma_signals(min_score: int = 0, days: int = 30):
    return query("""
        SELECT * FROM ma_signals
        WHERE date >= date('now', ? || ' days') AND ma_score >= ?
        ORDER BY ma_score DESC
    """, [f"-{days}", min_score])


@app.get("/api/ma-signals/top-targets")
def ma_top_targets():
    return query("""
        SELECT * FROM ma_signals
        WHERE date >= date('now', '-7 days') AND ma_score >= 50
        ORDER BY ma_score DESC LIMIT 20
    """)


@app.get("/api/ma-signals/rumors")
def ma_rumors(days: int = 30):
    return query("""
        SELECT * FROM ma_rumors
        WHERE date >= date('now', ? || ' days')
        ORDER BY date DESC
    """, [f"-{days}"])


@app.get("/api/ma-signals/{symbol}")
def ma_detail(symbol: str):
    signals = query("SELECT * FROM ma_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])
    rumors = query("SELECT * FROM ma_rumors WHERE symbol = ? ORDER BY date DESC", [symbol])
    return {"signals": signals, "rumors": rumors}


# ═══════════════════════════════════════════════════════════════════════
# PREDICTION MARKETS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/prediction-markets")
def prediction_markets(min_score: int = 0, days: int = 7):
    return query("""
        SELECT * FROM prediction_market_signals
        WHERE date >= date('now', ? || ' days') AND pm_score >= ?
        ORDER BY pm_score DESC
    """, [f"-{days}", min_score])


@app.get("/api/prediction-markets/raw")
def prediction_markets_raw(category: str = None, days: int = 3):
    sql = "SELECT * FROM prediction_market_raw WHERE date >= date('now', ? || ' days')"
    params = [f"-{days}"]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY volume DESC"
    return query(sql, params)


@app.get("/api/prediction-markets/categories")
def prediction_market_categories():
    return query("""
        SELECT category, COUNT(*) as count, AVG(probability) as avg_prob
        FROM prediction_market_raw
        WHERE date = (SELECT MAX(date) FROM prediction_market_raw)
        GROUP BY category ORDER BY count DESC
    """)


# ═══════════════════════════════════════════════════════════════════════
# AI REGULATORY
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/regulatory")
def regulatory_signals(min_score: int = 0, days: int = 7):
    return query("""
        SELECT * FROM regulatory_signals
        WHERE date >= date('now', ? || ' days') AND reg_score >= ?
        ORDER BY reg_score DESC
    """, [f"-{days}", min_score])


@app.get("/api/regulatory/events")
def regulatory_events(source: str = None, category: str = None,
                      jurisdiction: str = None, min_severity: int = 1, days: int = 14):
    sql = "SELECT * FROM regulatory_events WHERE date >= date('now', ? || ' days') AND severity >= ?"
    params = [f"-{days}", min_severity]
    if source:
        sql += " AND source = ?"
        params.append(source)
    if category:
        sql += " AND category = ?"
        params.append(category)
    if jurisdiction:
        sql += " AND jurisdiction = ?"
        params.append(jurisdiction)
    sql += " ORDER BY severity DESC, date DESC"
    return query(sql, params)


@app.get("/api/regulatory/categories")
def regulatory_categories():
    return query("""
        SELECT category, COUNT(*) as count, AVG(severity) as avg_severity
        FROM regulatory_events
        WHERE date >= date('now', '-30 days')
        GROUP BY category ORDER BY avg_severity DESC
    """)


@app.get("/api/regulatory/sources")
def regulatory_sources():
    return query("""
        SELECT source, COUNT(*) as count
        FROM regulatory_events
        WHERE date >= date('now', '-30 days')
        GROUP BY source ORDER BY count DESC
    """)


@app.get("/api/regulatory/jurisdictions")
def regulatory_jurisdictions():
    return query("""
        SELECT jurisdiction, COUNT(*) as count, AVG(severity) as avg_severity
        FROM regulatory_events
        WHERE date >= date('now', '-30 days')
        GROUP BY jurisdiction ORDER BY avg_severity DESC
    """)


@app.get("/api/regulatory/{symbol}")
def regulatory_symbol(symbol: str, days: int = 14):
    signals = query("SELECT * FROM regulatory_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])
    events = query("""
        SELECT * FROM regulatory_events
        WHERE date >= date('now', ? || ' days')
          AND affected_symbols LIKE ?
        ORDER BY severity DESC
    """, [f"-{days}", f"%{symbol}%"])
    return {"signals": signals, "events": events}


# ═══════════════════════════════════════════════════════════════════════
# WORLDVIEW / GLOBAL MACRO
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/worldview")
def worldview():
    return query("""
        SELECT * FROM worldview_signals
        WHERE date = (SELECT MAX(date) FROM worldview_signals)
        ORDER BY thesis_alignment_score DESC LIMIT 50
    """)


@app.get("/api/worldview/theses")
def worldview_theses():
    rows = query("""
        SELECT active_theses, COUNT(*) as symbol_count,
               AVG(thesis_alignment_score) as avg_score, regime
        FROM worldview_signals
        WHERE date = (SELECT MAX(date) FROM worldview_signals)
        GROUP BY active_theses
        ORDER BY avg_score DESC
    """)
    return rows


@app.get("/api/worldview/world-macro")
def world_macro():
    return query("SELECT * FROM world_macro_indicators ORDER BY date DESC LIMIT 100")


@app.get("/api/worldview/{symbol}")
def worldview_symbol(symbol: str):
    return query("SELECT * FROM worldview_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])


# ═══════════════════════════════════════════════════════════════════════
# ENERGY INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/energy-intel")
def energy_intel(min_score: int = 0):
    signals = query("""
        SELECT * FROM energy_intel_signals
        WHERE date >= date('now', '-7 days') AND score >= ?
        ORDER BY score DESC
    """, [min_score])
    anomalies = query("SELECT * FROM energy_supply_anomalies ORDER BY date DESC LIMIT 20")
    return {"signals": signals, "summary": {}, "anomalies": anomalies}


@app.get("/api/energy-intel/supply-balance")
def energy_supply():
    return query("SELECT * FROM energy_eia_enhanced ORDER BY date DESC LIMIT 100")


@app.get("/api/energy-intel/production")
def energy_production():
    return query("SELECT * FROM energy_eia_enhanced WHERE category = 'production' ORDER BY date DESC LIMIT 100")


@app.get("/api/energy-intel/trade-flows")
def energy_trade_flows():
    return {"imports": [], "exports": [], "padd_stocks": [], "import_by_country": [], "comtrade": []}


@app.get("/api/energy-intel/global-balance")
def energy_global_balance():
    jodi = query("SELECT * FROM energy_jodi_data ORDER BY date DESC LIMIT 100")
    return {"jodi_data": jodi, "balance": None, "global_stocks": []}


# ═══════════════════════════════════════════════════════════════════════
# PATTERNS & OPTIONS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/patterns")
def patterns(min_score: int = 0, sector: str = None, phase: str = None, squeeze_only: bool = False):
    sql = """
        SELECT po.*, su.sector, su.name FROM pattern_options_signals po
        JOIN stock_universe su ON po.symbol = su.symbol
        WHERE po.date >= date('now', '-7 days') AND po.score >= ?
    """
    params = [min_score]
    if sector:
        sql += " AND su.sector = ?"
        params.append(sector)
    sql += " ORDER BY po.score DESC LIMIT 100"
    return query(sql, params)


@app.get("/api/patterns/layers/{symbol}")
def pattern_layers(symbol: str):
    patterns = query("SELECT * FROM pattern_scan WHERE symbol = ? ORDER BY date DESC LIMIT 20", [symbol])
    options = query("SELECT * FROM options_intel WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])
    return {"patterns": patterns, "options": options}


@app.get("/api/patterns/rotation")
def sector_rotation(days: int = 30):
    return query("SELECT * FROM sector_rotation ORDER BY date DESC LIMIT ?", [days])


@app.get("/api/patterns/options")
def options_intel(min_score: int = 0):
    return query("""
        SELECT * FROM options_intel
        WHERE date >= date('now', '-7 days') AND score >= ?
        ORDER BY score DESC
    """, [min_score])


@app.get("/api/patterns/options/{symbol}")
def options_detail(symbol: str):
    return query("SELECT * FROM options_intel WHERE symbol = ? ORDER BY date DESC LIMIT 20", [symbol])


@app.get("/api/patterns/unusual-activity")
def unusual_activity(min_count: int = 1):
    return query("""
        SELECT * FROM options_intel
        WHERE date >= date('now', '-7 days') AND unusual_volume >= ?
        ORDER BY unusual_volume DESC
    """, [min_count])


@app.get("/api/patterns/expected-moves")
def expected_moves():
    return query("""
        SELECT * FROM options_intel
        WHERE date >= date('now', '-7 days') AND iv_rank IS NOT NULL
        ORDER BY iv_rank DESC LIMIT 50
    """)


@app.get("/api/patterns/compression")
def compression_setups():
    return query("""
        SELECT * FROM pattern_scan
        WHERE date >= date('now', '-7 days') AND pattern LIKE '%squeeze%'
        ORDER BY score DESC
    """)


@app.get("/api/patterns/dealer-exposure")
def dealer_exposure():
    return query("""
        SELECT * FROM options_intel
        WHERE date >= date('now', '-7 days')
        ORDER BY put_call_ratio DESC LIMIT 50
    """)


# ═══════════════════════════════════════════════════════════════════════
# THESIS LAB
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/thesis/funnel")
def thesis_funnel():
    total = query("SELECT COUNT(DISTINCT symbol) as n FROM stock_universe")
    gated = query("SELECT COUNT(DISTINCT symbol) as n FROM technical_scores WHERE date = (SELECT MAX(date) FROM technical_scores) AND total_score >= 35")
    scored = query("SELECT COUNT(DISTINCT symbol) as n FROM convergence_signals WHERE date = (SELECT MAX(date) FROM convergence_signals)")
    high = query("SELECT COUNT(DISTINCT symbol) as n FROM convergence_signals WHERE date = (SELECT MAX(date) FROM convergence_signals) AND conviction_level = 'HIGH'")
    return {
        "universe": total[0]["n"] if total else 0,
        "gated": gated[0]["n"] if gated else 0,
        "scored": scored[0]["n"] if scored else 0,
        "high_conviction": high[0]["n"] if high else 0,
    }


@app.get("/api/thesis/models")
def thesis_models():
    regime = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    return {"models": [], "regime": regime[0]["regime"] if regime else "neutral"}


@app.get("/api/thesis/checklist/{symbol}")
def thesis_checklist(symbol: str):
    conv = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    da = query("SELECT * FROM devils_advocate WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    forensic = query("SELECT * FROM forensic_alerts WHERE symbol = ? ORDER BY date DESC LIMIT 3", [symbol])
    conflicts = query("SELECT * FROM signal_conflicts WHERE symbol = ? ORDER BY date DESC LIMIT 5", [symbol])
    return {
        "symbol": symbol,
        "convergence": conv[0] if conv else {},
        "devils_advocate": da[0] if da else {},
        "forensic_alerts": forensic,
        "signal_conflicts": conflicts,
    }


# ═══════════════════════════════════════════════════════════════════════
# TRADING IDEAS (Thematic Scanner)
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/trading-ideas")
def trading_ideas(theme: str = None, min_score: int = 0):
    sql = "SELECT * FROM thematic_ideas WHERE score >= ?"
    params = [min_score]
    if theme:
        sql += " AND theme = ?"
        params.append(theme)
    sql += " ORDER BY score DESC LIMIT 50"
    return query(sql, params)


@app.get("/api/trading-ideas/themes")
def trading_ideas_themes():
    return query("""
        SELECT theme, COUNT(*) as count, AVG(score) as avg_score
        FROM thematic_ideas GROUP BY theme ORDER BY avg_score DESC
    """)


@app.get("/api/trading-ideas/top")
def trading_ideas_top(limit: int = 10):
    return query("SELECT * FROM thematic_ideas ORDER BY score DESC LIMIT ?", [limit])


@app.get("/api/trading-ideas/{symbol}")
def trading_ideas_detail(symbol: str):
    return query("SELECT * FROM thematic_ideas WHERE symbols LIKE ? ORDER BY date DESC", [f"%{symbol}%"])


@app.get("/api/trading-ideas/theme/{theme}")
def trading_ideas_theme(theme: str):
    return query("SELECT * FROM thematic_ideas WHERE theme = ? ORDER BY score DESC", [theme])


@app.get("/api/trading-ideas/sub-theme/{sub_theme}")
def trading_ideas_subtheme(sub_theme: str):
    return query("SELECT * FROM thematic_ideas WHERE details LIKE ? ORDER BY score DESC", [f"%{sub_theme}%"])


@app.get("/api/trading-ideas/history/{symbol}")
def trading_ideas_history(symbol: str, days: int = 30):
    return query("""
        SELECT * FROM thematic_ideas
        WHERE symbols LIKE ? AND date >= date('now', ? || ' days')
        ORDER BY date DESC
    """, [f"%{symbol}%", f"-{days}"])


# ═══════════════════════════════════════════════════════════════════════
# ★ NEW: INVESTMENT MEMOS & INTELLIGENCE REPORTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/report/list")
def report_list():
    return query("""
        SELECT id, topic, topic_type, expert_type, generated_at, regime, symbols_covered
        FROM intelligence_reports ORDER BY generated_at DESC LIMIT 50
    """)


@app.get("/api/report/latest")
def report_latest(topic: str):
    rows = query("""
        SELECT * FROM intelligence_reports
        WHERE topic = ? ORDER BY generated_at DESC LIMIT 1
    """, [topic])
    return rows[0] if rows else {}


@app.post("/api/report/generate")
def report_generate(topic: str):
    from tools.intelligence_report import generate_memo
    result = generate_memo(topic)
    if result:
        return {"status": "ok", "symbol": topic, "memo": result["memo"]}
    return {"status": "error", "message": f"Could not generate memo for {topic}"}


@app.get("/api/memos")
def memos(limit: int = 20):
    """Get all investment memos."""
    return query("""
        SELECT id, topic as symbol, generated_at, regime,
               report_html, metadata
        FROM intelligence_reports
        WHERE topic_type = 'investment_memo'
        ORDER BY generated_at DESC LIMIT ?
    """, [limit])


@app.get("/api/memos/{symbol}")
def memo_detail(symbol: str):
    """Get the latest memo for a specific symbol."""
    rows = query("""
        SELECT * FROM intelligence_reports
        WHERE topic = ? AND topic_type = 'investment_memo'
        ORDER BY generated_at DESC LIMIT 1
    """, [symbol])
    return rows[0] if rows else {}


# ═══════════════════════════════════════════════════════════════════════
# ★ NEW: SIGNAL CONFLICTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/signal-conflicts")
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


@app.get("/api/signal-conflicts/summary")
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


@app.get("/api/signal-conflicts/{symbol}")
def signal_conflicts_symbol(symbol: str):
    """Get conflicts for a specific symbol."""
    return query("""
        SELECT * FROM signal_conflicts
        WHERE symbol = ? ORDER BY date DESC LIMIT 20
    """, [symbol])


# ═══════════════════════════════════════════════════════════════════════
# ★ NEW: STRESS TESTING
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/stress-test")
def stress_test_results():
    """Get latest stress test results across all scenarios."""
    return query("""
        SELECT * FROM stress_test_results
        WHERE date = (SELECT MAX(date) FROM stress_test_results)
        ORDER BY portfolio_impact_pct ASC
    """)


@app.get("/api/stress-test/concentration")
def concentration_risk():
    """Get current portfolio concentration risk."""
    rows = query("SELECT * FROM concentration_risk ORDER BY date DESC LIMIT 1")
    return rows[0] if rows else {}


@app.get("/api/stress-test/backtest")
def stress_backtest():
    """Get historical backtest calibration results."""
    return query("SELECT * FROM stress_backtest_results ORDER BY crisis, sector_etf")


@app.get("/api/stress-test/calibration")
def stress_calibration():
    """Get calibrated vs assumed impact comparison."""
    return query("SELECT * FROM stress_calibration ORDER BY scenario, sector")


@app.get("/api/stress-test/{scenario}")
def stress_test_scenario_detail(scenario: str):
    """Get detailed position-level impacts for a scenario."""
    rows = query("""
        SELECT * FROM stress_test_results
        WHERE scenario = ? ORDER BY date DESC LIMIT 1
    """, [scenario])
    return rows[0] if rows else {}


# ═══════════════════════════════════════════════════════════════════════
# ★ NEW: THESIS MONITOR
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/thesis-monitor")
def thesis_monitor_alerts(severity: str = None, days: int = 7):
    """Get thesis break/change alerts."""
    sql = "SELECT * FROM thesis_alerts WHERE date >= date('now', ? || ' days')"
    params = [f"-{days}"]
    if severity:
        sql += " AND severity = ?"
        params.append(severity)
    sql += " ORDER BY date DESC"
    return query(sql, params)


@app.get("/api/thesis-monitor/snapshots")
def thesis_snapshots(days: int = 30):
    """Get thesis evolution over time."""
    return query("""
        SELECT * FROM thesis_snapshots
        WHERE date >= date('now', ? || ' days')
        ORDER BY date DESC, thesis
    """, [f"-{days}"])


@app.get("/api/thesis-monitor/{thesis}")
def thesis_detail(thesis: str):
    """Get history for a specific thesis."""
    snapshots = query("SELECT * FROM thesis_snapshots WHERE thesis = ? ORDER BY date DESC LIMIT 30", [thesis])
    alerts = query("SELECT * FROM thesis_alerts WHERE thesis = ? ORDER BY date DESC LIMIT 20", [thesis])
    return {"snapshots": snapshots, "alerts": alerts}


# ═══════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    """System health check."""
    tables = query("SELECT name FROM sqlite_master WHERE type='table'")
    latest = query("SELECT MAX(date) as d FROM convergence_signals")
    return {
        "status": "ok",
        "tables": len(tables),
        "latest_data": latest[0]["d"] if latest else None,
    }
