"""FastAPI application — serves all /api/* routes for the dashboard.

This file was regenerated after iCloud corruption. It includes:
  - Core endpoints (macro, signals, convergence, prices, asset detail)
  - All 5 new module endpoints (memos, conflicts, stress test, thesis monitor, reports)
  - All existing module endpoints matching dashboard/src/lib/api.ts

Architecture: thin query layer over SQLite. No business logic here —
all intelligence lives in tools/*.py modules.

Route organization:
  - api.py              — Core endpoints (macro, signals, convergence, prices, portfolio, displacement, alt-data, sector-experts)
  - api_intelligence.py — Pairs, trading-ideas, reports/memos, signal-conflicts, stress-test, thesis-monitor
  - api_data_modules.py — Economic-indicators, insider, ai-exec, hyperliquid, estimate-momentum,
                           consensus-blindspots, MA, prediction-markets, regulatory
  - api_market_modules.py — Worldview, energy, patterns/options, Alt Alpha II modules
  - api_analytics.py    — Thesis-lab, discover, performance, health
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tools.db import init_db, query
from tools.api_intelligence import router as intelligence_router
from tools.api_data_modules import router as data_modules_router
from tools.api_market_modules import router as market_modules_router
from tools.api_analytics import router as analytics_router
from tools.api_funnel import router as funnel_router
from tools.api_gates import router as gates_router
from tools.api_alpha_stack import router as alpha_stack_router

init_db()

app = FastAPI(title="Druckenmiller Alpha System", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception):
    import logging
    logging.getLogger(__name__).error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": "Pipeline may be processing — try again shortly"},
    )

# Include sub-routers
app.include_router(intelligence_router)
app.include_router(data_modules_router)
app.include_router(market_modules_router)
app.include_router(analytics_router)
app.include_router(funnel_router)
app.include_router(gates_router)
app.include_router(alpha_stack_router)


# ═══════════════════════════════════════════════════════════════════════
# CORE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════

@app.get("/api/macro")
def macro():
    rows = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    return rows[0] if rows else {}


@app.get("/api/macro/history")
def macro_history():
    return query("SELECT date, COALESCE(total_score, regime_score) as total_score, regime FROM macro_scores ORDER BY date DESC LIMIT 90")


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
    sig = query("SELECT * FROM signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])

    return {
        "symbol": symbol,
        "info": universe[0] if universe else {},
        "technical": tech[0] if tech else {},
        "fundamentals": {r["metric"]: r["value"] for r in fund},
        "convergence": conv[0] if conv else {},
        "devils_advocate": da[0] if da else {},
        "signal": sig[0] if sig else None,
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
    """Get open positions with live P&L calculations."""
    positions = query("SELECT * FROM portfolio WHERE status = 'open'")
    if not positions:
        return []
    # Get latest prices for P&L calc
    symbols = [p["symbol"] for p in positions]
    placeholders = ",".join("?" for _ in symbols)
    prices = query(f"""
        SELECT symbol, close as current_price, date
        FROM price_data
        WHERE (symbol, date) IN (
            SELECT symbol, MAX(date) FROM price_data
            WHERE symbol IN ({placeholders})
            GROUP BY symbol
        )
    """, symbols)
    price_map = {p["symbol"]: p["current_price"] for p in prices}
    for p in positions:
        cp = price_map.get(p["symbol"], p["entry_price"])
        p["current_price"] = cp
        p["current_value"] = cp * (p["shares"] or 0)
        cost = (p["entry_price"] or 0) * (p["shares"] or 0)
        p["pnl"] = p["current_value"] - cost
        p["pnl_pct"] = ((cp / p["entry_price"]) - 1) * 100 if p["entry_price"] else 0
    return positions


@app.get("/api/portfolio/closed")
def portfolio_closed(limit: int = 50):
    """Get closed/historical trades."""
    return query("""
        SELECT *, ROUND((exit_price / entry_price - 1) * 100, 2) as pnl_pct,
               ROUND((exit_price - entry_price) * shares, 2) as pnl
        FROM portfolio WHERE status = 'closed'
        ORDER BY exit_date DESC LIMIT ?
    """, [limit])


@app.get("/api/portfolio/stats")
def portfolio_stats():
    """Aggregate paper trading performance stats."""
    open_pos = query("SELECT * FROM portfolio WHERE status = 'open'")
    closed = query("SELECT * FROM portfolio WHERE status = 'closed'")
    # Closed trade stats
    wins = [t for t in closed if t.get("exit_price", 0) > t.get("entry_price", 0)]
    losses = [t for t in closed if t.get("exit_price", 0) <= t.get("entry_price", 0)]
    win_rate = len(wins) / len(closed) * 100 if closed else 0
    avg_win = sum((t["exit_price"] / t["entry_price"] - 1) * 100 for t in wins) / len(wins) if wins else 0
    avg_loss = sum((t["exit_price"] / t["entry_price"] - 1) * 100 for t in losses) / len(losses) if losses else 0
    profit_factor = abs(avg_win * len(wins) / (avg_loss * len(losses))) if losses and avg_loss != 0 else 0
    return {
        "open_count": len(open_pos),
        "closed_count": len(closed),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
    }


@app.post("/api/portfolio/sync")
def portfolio_sync():
    """Auto-generate paper positions from HIGH conviction signals.
    Only creates entries for symbols not already in open positions."""
    from tools.db import get_conn
    # Get current open symbols
    open_syms = {r["symbol"] for r in query("SELECT symbol FROM portfolio WHERE status = 'open'")}
    # Get HIGH conviction signals with entry prices
    signals = query("""
        SELECT s.symbol, s.entry_price, s.stop_loss, s.target_price, s.position_size_shares
        FROM signals s
        JOIN convergence_signals c ON s.symbol = c.symbol AND s.date = c.date
        WHERE c.date = (SELECT MAX(date) FROM convergence_signals)
        AND c.conviction_level = 'HIGH'
        AND s.entry_price IS NOT NULL
        AND s.entry_price > 0
    """)
    new_entries = []
    conn = get_conn()
    try:
        for sig in signals:
            if sig["symbol"] in open_syms:
                continue
            shares = sig["position_size_shares"] or 100
            conn.execute("""
                INSERT INTO portfolio (symbol, asset_class, entry_date, entry_price, shares, stop_loss, target_price, status)
                VALUES (?, 'equity', date('now'), ?, ?, ?, ?, 'open')
            """, [sig["symbol"], sig["entry_price"], shares, sig["stop_loss"], sig["target_price"]])
            new_entries.append(sig["symbol"])
        conn.commit()
    finally:
        conn.close()
    return {"synced": len(new_entries), "symbols": new_entries}


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


@app.get("/api/convergence/delta")
def convergence_delta():
    """Symbols with significant convergence score changes vs previous day."""
    return query("""
        SELECT
            t.symbol,
            t.convergence_score,
            t.conviction_level,
            t.narrative,
            t.module_count,
            y.convergence_score as prev_score,
            y.conviction_level as prev_conviction,
            ROUND(t.convergence_score - COALESCE(y.convergence_score, 0), 2) as score_delta
        FROM convergence_signals t
        LEFT JOIN convergence_signals y
            ON t.symbol = y.symbol
            AND y.date = (
                SELECT MAX(date) FROM convergence_signals
                WHERE date < (SELECT MAX(date) FROM convergence_signals)
            )
        WHERE t.date = (SELECT MAX(date) FROM convergence_signals)
            AND ABS(t.convergence_score - COALESCE(y.convergence_score, 0)) > 5
        ORDER BY (t.convergence_score - COALESCE(y.convergence_score, 0)) DESC
        LIMIT 30
    """)


@app.get("/api/convergence/{symbol}")
def convergence_symbol(symbol: str):
    rows = query("""
        SELECT * FROM convergence_signals
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    return rows[0] if rows else {}


@app.get("/api/asset/{symbol}/signal-history")
def asset_signal_history(symbol: str, days: int = 90):
    """Full signal + convergence history for traceability."""
    signal_hist = query("""
        SELECT s.date, s.signal, s.composite_score, s.entry_price, s.target_price, s.stop_loss,
               s.rr_ratio
        FROM signals s
        WHERE s.symbol = ?
        ORDER BY s.date DESC LIMIT ?
    """, [symbol, days])
    conv_hist = query("""
        SELECT *
        FROM convergence_signals
        WHERE symbol = ?
        ORDER BY date DESC LIMIT ?
    """, [symbol, days])
    return {"signal_history": signal_hist, "convergence_history": conv_hist}


@app.get("/api/signals/changes")
def signal_changes():
    """Signal upgrades/downgrades vs previous day."""
    return query("""
        SELECT t.symbol, t.signal as new_signal, y.signal as old_signal,
               t.composite_score, t.entry_price, t.target_price, t.stop_loss
        FROM signals t
        JOIN signals y
            ON t.symbol = y.symbol
            AND y.date = (
                SELECT MAX(date) FROM signals
                WHERE date < (SELECT MAX(date) FROM signals)
            )
        WHERE t.date = (SELECT MAX(date) FROM signals)
            AND t.signal != y.signal
        ORDER BY t.composite_score DESC
        LIMIT 20
    """)


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
