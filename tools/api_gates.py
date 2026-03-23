"""Gates API — 10-gate cascade endpoints.

Routes:
  GET  /api/gates/run             — Latest gate run summary
  GET  /api/gates/cascade         — Waterfall data (per-gate counts)
  GET  /api/gates/results         — All assets with gate_results for today
  GET  /api/gates/results/{symbol}  — Gate-by-gate status for one asset
  GET  /api/gates/passing/{gate}  — Assets passing through exactly gate N
  GET  /api/gates/fat-pitches     — gate_10 = 1
  POST /api/gates/override        — Create override
  DELETE /api/gates/override/{symbol}/{gate}  — Remove override
  GET  /api/gates/overrides       — Active overrides
  GET  /api/gates/history         — gate_run_history last 30 days
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import date
from tools.db import get_conn, query
from tools.config import GATE_NAMES, GATE_THRESHOLDS

router = APIRouter()


class GateOverride(BaseModel):
    symbol: str
    gate: int
    direction: str  # 'force_pass' or 'force_fail'
    reason: str
    expires: Optional[str] = None  # ISO date string


@router.get("/api/gates/run")
def gates_run_summary():
    """Latest gate run summary — counts per gate."""
    rows = query(
        "SELECT * FROM gate_run_history ORDER BY date DESC, run_id DESC NULLS LAST LIMIT 1"
    )
    if not rows:
        return {"message": "No gate run found — run the pipeline first"}

    r = rows[0]
    total = r.get("total_assets", 0) or 1

    return {
        "run_id": r.get("run_id"),
        "date": r.get("date"),
        "total_assets": r.get("total_assets"),
        "fat_pitches": r.get("gate_10_passed"),
        "run_time_seconds": r.get("run_time_seconds"),
        "gate_counts": {
            str(i): r.get(f"gate_{i}_passed", 0)
            for i in range(1, 11)
        },
        "funnel_pct": {
            str(i): round(r.get(f"gate_{i}_passed", 0) / total * 100, 1)
            for i in range(1, 11)
        },
    }


@router.get("/api/gates/cascade")
def gates_cascade():
    """Full cascade waterfall data — per-gate counts, names, thresholds."""
    run = query("SELECT * FROM gate_run_history ORDER BY date DESC, run_id DESC NULLS LAST LIMIT 1")
    if not run:
        return {"message": "No gate run found"}

    r = run[0]
    total = r.get("total_assets", 0) or 1

    cascade = [
        {
            "gate": 0,
            "name": GATE_NAMES[0],
            "count": total,
            "pct_of_universe": 100.0,
            "pct_of_prev": 100.0,
            "threshold": "All assets in universe",
        }
    ]

    prev_count = total
    for i in range(1, 11):
        count = r.get(f"gate_{i}_passed", 0) or 0
        cascade.append({
            "gate": i,
            "name": GATE_NAMES[i],
            "count": count,
            "pct_of_universe": round(count / total * 100, 1),
            "pct_of_prev": round(count / prev_count * 100, 1) if prev_count > 0 else 0,
            "threshold": str(GATE_THRESHOLDS.get(i, {})),
        })
        prev_count = count

    result = {
        "run_date": r.get("date"),
        "run_id": r.get("run_id"),
        "cascade": cascade,
        "fat_pitches": r.get("gate_10_passed", 0),
    }
    return result


@router.get("/api/gates/results")
def gates_results(asset_class: str = None, sector: str = None, limit: int = 500):
    """All assets with gate results for today."""
    sql = """
        SELECT gr.*, u.name, u.sector
        FROM gate_results gr
        LEFT JOIN stock_universe u ON gr.symbol = u.symbol
        WHERE gr.date = (SELECT MAX(date) FROM gate_results)
    """
    params = []
    if asset_class:
        sql += " AND gr.asset_class = ?"
        params.append(asset_class)
    if sector:
        sql += " AND u.sector = ?"
        params.append(sector)
    sql += " ORDER BY gr.last_gate_passed DESC, gr.gate_10 DESC LIMIT ?"
    params.append(limit)
    return query(sql, params)


@router.get("/api/gates/results/{symbol}")
def gates_results_symbol(symbol: str):
    """Gate-by-gate status for a specific symbol."""
    rows = query(
        """SELECT * FROM gate_results WHERE symbol = ?
           ORDER BY date DESC LIMIT 1""",
        [symbol]
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No gate results for {symbol}")

    r = rows[0]

    # Build gate-by-gate detail
    gate_detail = []
    for i in range(11):
        passed = r.get(f"gate_{i}")
        gate_detail.append({
            "gate": i,
            "name": GATE_NAMES[i],
            "passed": passed,
            "is_last_failed": i == (r.get("last_gate_passed", 0) or 0) + 1 and passed == 0,
        })

    # Load overrides for this symbol
    overrides = query(
        "SELECT * FROM gate_overrides WHERE symbol = ? AND (expires IS NULL OR expires >= date('now'))",
        [symbol]
    )

    # Load catalyst info
    catalyst = query(
        "SELECT * FROM catalyst_scores WHERE symbol = ? ORDER BY date DESC LIMIT 1",
        [symbol]
    )

    return {
        "symbol": symbol,
        "date": r.get("date"),
        "last_gate_passed": r.get("last_gate_passed"),
        "fail_reason": r.get("fail_reason"),
        "asset_class": r.get("asset_class"),
        "is_fat_pitch": r.get("gate_10") == 1,
        "gates": gate_detail,
        "overrides": overrides,
        "catalyst": catalyst[0] if catalyst else None,
    }


@router.get("/api/gates/passing/{gate}")
def gates_passing(gate: int, asset_class: str = None, limit: int = 500):
    """All assets that reached (passed at least) gate N."""
    if gate < 0 or gate > 10:
        raise HTTPException(status_code=400, detail="Gate must be 0-10")

    # Gate 0 = full universe (no gate filter needed)
    # Gate N = last_gate_passed >= N (passed all gates up to N)
    if gate == 0:
        where = "gr.last_gate_passed >= 0"
    else:
        where = f"gr.last_gate_passed >= {gate}"

    sql = f"""
        SELECT gr.symbol, gr.last_gate_passed, gr.fail_reason, gr.asset_class,
               gr.entry_mode,
               u.name, u.sector,
               s.composite_score, s.signal,
               c.convergence_score
        FROM gate_results gr
        LEFT JOIN stock_universe u ON gr.symbol = u.symbol
        LEFT JOIN signals s ON gr.symbol = s.symbol
            AND s.date = (SELECT MAX(date) FROM signals)
        LEFT JOIN convergence_signals c ON gr.symbol = c.symbol
            AND c.date = (SELECT MAX(date) FROM convergence_signals)
        WHERE gr.date = (SELECT MAX(date) FROM gate_results)
        AND {where}
    """
    params = []
    if asset_class:
        sql += " AND gr.asset_class = ?"
        params.append(asset_class)
    sql += " ORDER BY gr.last_gate_passed DESC, s.composite_score DESC LIMIT ?"
    params.append(limit)

    return {
        "gate": gate,
        "gate_name": GATE_NAMES[gate],
        "assets": query(sql, params),
    }


@router.get("/api/gates/fat-pitches")
def gates_fat_pitches():
    """All fat pitches — gate_10 = 1."""
    return query(
        """SELECT gr.symbol, gr.asset_class, gr.date,
                  u.name, u.sector,
                  s.composite_score, s.signal, s.entry_price,
                  s.target_price, s.stop_loss, s.rr_ratio,
                  c.convergence_score, c.module_count, c.conviction_level, c.narrative,
                  cat.catalyst_type, cat.catalyst_strength, cat.catalyst_detail,
                  si.short_float_pct, an.consensus_grade, an.pt_upside_pct
           FROM gate_results gr
           LEFT JOIN stock_universe u ON gr.symbol = u.symbol
           LEFT JOIN signals s ON gr.symbol = s.symbol
               AND s.date = (SELECT MAX(date) FROM signals WHERE symbol = gr.symbol)
           LEFT JOIN convergence_signals c ON gr.symbol = c.symbol
               AND c.date = (SELECT MAX(date) FROM convergence_signals WHERE symbol = gr.symbol)
           LEFT JOIN catalyst_scores cat ON gr.symbol = cat.symbol
               AND cat.date = (SELECT MAX(date) FROM catalyst_scores WHERE symbol = gr.symbol)
           LEFT JOIN short_interest_scores si ON gr.symbol = si.symbol
               AND si.date = (SELECT MAX(date) FROM short_interest_scores WHERE symbol = gr.symbol)
           LEFT JOIN analyst_scores an ON gr.symbol = an.symbol
               AND an.date = (SELECT MAX(date) FROM analyst_scores WHERE symbol = gr.symbol)
           WHERE gr.date = (SELECT MAX(date) FROM gate_results)
           AND gr.gate_10 = 1
           ORDER BY s.composite_score DESC"""
    )


@router.post("/api/gates/override")
def create_override(override: GateOverride):
    """Create a gate override (force_pass or force_fail)."""
    if override.direction not in ("force_pass", "force_fail"):
        raise HTTPException(
            status_code=400,
            detail="direction must be 'force_pass' or 'force_fail'"
        )
    if override.gate < 0 or override.gate > 10:
        raise HTTPException(status_code=400, detail="gate must be 0-10")

    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO gate_overrides
               (symbol, gate, direction, reason, expires, created_at)
               VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            [override.symbol, override.gate, override.direction,
             override.reason, override.expires]
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "created",
        "symbol": override.symbol,
        "gate": override.gate,
        "direction": override.direction,
    }


@router.delete("/api/gates/override/{symbol}/{gate}")
def delete_override(symbol: str, gate: int):
    """Remove a gate override."""
    conn = get_conn()
    try:
        result = conn.execute(
            "DELETE FROM gate_overrides WHERE symbol = ? AND gate = ?",
            [symbol, gate]
        )
        conn.commit()
        deleted = result.rowcount
    finally:
        conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Override not found")

    return {"status": "deleted", "symbol": symbol, "gate": gate}


@router.get("/api/gates/overrides")
def get_overrides():
    """All active overrides (not expired)."""
    return query(
        """SELECT * FROM gate_overrides
           WHERE expires IS NULL OR expires >= date('now')
           ORDER BY created_at DESC"""
    )


@router.get("/api/gates/history")
def gates_history(days: int = 30):
    """Gate run history — shows funnel evolution over time."""
    rows = query(
        f"""SELECT * FROM gate_run_history
            WHERE date >= date('now', '-{days} days')
            ORDER BY date DESC"""
    )
    return {
        "history": rows,
        "summary": {
            "total_runs": len(rows),
            "avg_fat_pitches": (
                sum(r.get("gate_10_passed", 0) or 0 for r in rows) / len(rows)
                if rows else 0
            ),
        },
    }
