"""Alpha Stack API — unified signal intelligence for high-conviction stocks.

Returns all signal sources stacked per symbol, filtered by gate level.
This is the institutional-grade intelligence view: every independent data
source pointing at the same name.

Routes:
  GET /api/alpha/stack?min_gate=5   — ranked stock list with full signal stack
  GET /api/alpha/stack/{symbol}     — full signal stack for one symbol

Performance: batch-loads all signal tables in 9 queries total (not N×9).
"""
from fastapi import APIRouter, Query
from tools.db import query
import json
from typing import Optional

router = APIRouter()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_json(val):
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return val
    return val


def _batch_load_signals(symbols: list[str]) -> dict[str, dict]:
    """Load all signal sources for a list of symbols in 9 batch queries."""
    if not symbols:
        return {}

    placeholders = ",".join("?" * len(symbols))
    stacks: dict[str, dict] = {s: {} for s in symbols}

    # Helper: latest-date subquery per symbol
    def latest(table, col="date"):
        return f"SELECT {col} FROM {table} t2 WHERE t2.symbol = t1.symbol ORDER BY {col} DESC LIMIT 1"

    # 1. Insider signals
    rows = query(
        f"""SELECT * FROM insider_signals t1
            WHERE symbol IN ({placeholders})
            AND date = ({latest('insider_signals')})""",
        symbols
    )
    for r in rows:
        stacks[r["symbol"]]["insider"] = {
            "score": r["insider_score"], "cluster_buy": r["cluster_buy"],
            "cluster_count": r["cluster_count"], "large_buys_count": r["large_buys_count"],
            "total_buy_value_30d": r["total_buy_value_30d"],
            "total_sell_value_30d": r["total_sell_value_30d"],
            "unusual_volume_flag": r["unusual_volume_flag"],
            "top_buyer": r["top_buyer"], "narrative": r["narrative"], "date": r["date"],
        }

    # 2. Pattern scan
    rows = query(
        f"""SELECT * FROM pattern_scan t1
            WHERE symbol IN ({placeholders})
            AND date = ({latest('pattern_scan')})""",
        symbols
    )
    for r in rows:
        stacks[r["symbol"]]["patterns"] = {
            "score": r["pattern_scan_score"], "wyckoff_phase": r["wyckoff_phase"],
            "wyckoff_confidence": r["wyckoff_confidence"],
            "patterns_detected": _safe_json(r["patterns_detected"]),
            "momentum_score": r["momentum_score"], "compression_score": r["compression_score"],
            "squeeze_active": r["squeeze_active"], "hurst_exponent": r["hurst_exponent"],
            "vol_regime": r["vol_regime"], "rotation_score": r["rotation_score"], "date": r["date"],
        }

    # 3. Alt data
    rows = query(
        f"""SELECT * FROM alt_data_scores t1
            WHERE symbol IN ({placeholders})
            AND date = ({latest('alt_data_scores')})""",
        symbols
    )
    for r in rows:
        stacks[r["symbol"]]["alt_data"] = {
            "score": r["alt_data_score"],
            "signals": _safe_json(r["contributing_signals"]), "date": r["date"],
        }

    # 4. Options intel
    rows = query(
        f"""SELECT * FROM options_intel t1
            WHERE symbol IN ({placeholders})
            AND date = ({latest('options_intel')})""",
        symbols
    )
    for r in rows:
        stacks[r["symbol"]]["options"] = {
            "score": r["options_score"], "iv_rank": r["iv_rank"],
            "iv_percentile": r["iv_percentile"], "pc_signal": r["pc_signal"],
            "unusual_activity_count": r["unusual_activity_count"],
            "unusual_direction_bias": r["unusual_direction_bias"],
            "dealer_regime": r["dealer_regime"], "skew_direction": r["skew_direction"],
            "expected_move_pct": r["expected_move_pct"],
            "unusual_activity": _safe_json(r["unusual_activity"]), "date": r["date"],
        }

    # 5. Supply chain
    rows = query(
        f"""SELECT * FROM supply_chain_scores t1
            WHERE symbol IN ({placeholders})
            AND date = ({latest('supply_chain_scores')})""",
        symbols
    )
    for r in rows:
        stacks[r["symbol"]]["supply_chain"] = {
            "score": r["supply_chain_score"], "rail_score": r["rail_score"],
            "shipping_score": r["shipping_score"], "trucking_score": r["trucking_score"],
            "details": _safe_json(r["details"]), "date": r["date"],
        }

    # 6. M&A signals
    rows = query(
        f"""SELECT * FROM ma_signals t1
            WHERE symbol IN ({placeholders})
            AND date = ({latest('ma_signals')})""",
        symbols
    )
    for r in rows:
        stacks[r["symbol"]]["ma"] = {
            "score": r["ma_score"], "deal_stage": r["deal_stage"],
            "rumor_credibility": r["rumor_credibility"], "acquirer_name": r["acquirer_name"],
            "expected_premium_pct": r["expected_premium_pct"],
            "best_headline": r["best_headline"], "narrative": r["narrative"], "date": r["date"],
        }

    # 7. Pairs (either leg, active only)
    rows = query(
        f"""SELECT * FROM pair_signals
            WHERE (symbol_a IN ({placeholders}) OR symbol_b IN ({placeholders}))
            AND status = 'active'
            ORDER BY pairs_score DESC""",
        symbols + symbols
    )
    for r in rows:
        pair = {
            "symbol_a": r["symbol_a"], "symbol_b": r["symbol_b"],
            "direction": r["direction"], "spread_zscore": r["spread_zscore"],
            "score": r["pairs_score"], "narrative": r["narrative"], "date": r["date"],
        }
        for sym in (r["symbol_a"], r["symbol_b"]):
            if sym in stacks:
                stacks[sym].setdefault("pairs", [])
                if len(stacks[sym]["pairs"]) < 3:
                    stacks[sym]["pairs"].append(pair)

    # 8. Prediction markets
    rows = query(
        f"""SELECT * FROM prediction_market_signals t1
            WHERE symbol IN ({placeholders})
            AND date = ({latest('prediction_market_signals')})""",
        symbols
    )
    for r in rows:
        stacks[r["symbol"]]["prediction_markets"] = {
            "score": r["pm_score"], "market_count": r["market_count"],
            "net_impact": r["net_impact"], "status": r["status"],
            "narrative": r["narrative"], "date": r["date"],
        }

    # 9. Digital exhaust
    rows = query(
        f"""SELECT * FROM digital_exhaust_scores t1
            WHERE symbol IN ({placeholders})
            AND date = ({latest('digital_exhaust_scores')})""",
        symbols
    )
    for r in rows:
        stacks[r["symbol"]]["digital_exhaust"] = {
            "score": r["digital_exhaust_score"], "app_score": r["app_score"],
            "github_score": r["github_score"], "pricing_score": r["pricing_score"],
            "domain_score": r["domain_score"], "details": _safe_json(r["details"]), "date": r["date"],
        }

    return stacks


def _signal_count(stack: dict) -> int:
    count = sum(1 for k, v in stack.items()
                if k != "pairs" and v and (v.get("score") or 0) >= 50)
    if stack.get("pairs"):
        count += 1
    return count


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api/alpha/stack")
def get_alpha_stack(min_gate: int = Query(default=5, ge=0, le=10)):
    gate_rows = query(
        """SELECT gr.symbol, gr.last_gate_passed, gr.gate_10 as is_fat_pitch,
                  gr.entry_mode,
                  s.composite_score, c.convergence_score, s.signal,
                  su.name, su.sector, gr.asset_class
           FROM gate_results gr
           LEFT JOIN stock_universe su ON gr.symbol = su.symbol
           LEFT JOIN signals s ON gr.symbol = s.symbol
               AND s.date = (SELECT MAX(date) FROM signals)
           LEFT JOIN convergence_signals c ON gr.symbol = c.symbol
               AND c.date = (SELECT MAX(date) FROM convergence_signals)
           WHERE gr.last_gate_passed >= ?
               AND gr.date = (SELECT MAX(date) FROM gate_results)
           ORDER BY gr.last_gate_passed DESC, s.composite_score DESC""",
        [min_gate]
    )

    symbols = [r["symbol"] for r in gate_rows]
    stacks = _batch_load_signals(symbols)

    results = []
    for r in gate_rows:
        sym = r["symbol"]
        stack = stacks.get(sym, {})
        results.append({
            "symbol": sym,
            "name": r["name"],
            "sector": r["sector"],
            "asset_class": r["asset_class"],
            "last_gate_passed": r["last_gate_passed"],
            "is_fat_pitch": bool(r["is_fat_pitch"]),
            "composite_score": r["composite_score"],
            "convergence_score": r["convergence_score"],
            "signal": r["signal"],
            "entry_mode": r["entry_mode"],
            "signal_count": _signal_count(stack),
            "signals": stack,
        })

    results.sort(
        key=lambda x: (x["last_gate_passed"], x["signal_count"], x["composite_score"] or 0),
        reverse=True
    )

    return results


@router.get("/api/alpha/stack/{symbol}")
def get_alpha_stack_symbol(symbol: str):
    symbol = symbol.upper()

    gate_rows = query(
        """SELECT gr.symbol, gr.last_gate_passed, gr.gate_10 as is_fat_pitch,
                  s.composite_score, c.convergence_score, s.signal,
                  su.name, su.sector, gr.asset_class
           FROM gate_results gr
           LEFT JOIN stock_universe su ON gr.symbol = su.symbol
           LEFT JOIN signals s ON gr.symbol = s.symbol
               AND s.date = (SELECT MAX(date) FROM signals)
           LEFT JOIN convergence_signals c ON gr.symbol = c.symbol
               AND c.date = (SELECT MAX(date) FROM convergence_signals)
           WHERE gr.symbol = ?
               AND gr.date = (SELECT MAX(date) FROM gate_results)""",
        [symbol]
    )

    if not gate_rows:
        return {"symbol": symbol, "last_gate_passed": 0, "signals": {}}

    r = gate_rows[0]
    stacks = _batch_load_signals([symbol])
    stack = stacks.get(symbol, {})

    result = {
        "symbol": r["symbol"], "name": r["name"], "sector": r["sector"],
        "asset_class": r["asset_class"], "last_gate_passed": r["last_gate_passed"],
        "is_fat_pitch": bool(r["is_fat_pitch"]),
        "composite_score": r["composite_score"], "convergence_score": r["convergence_score"],
        "signal": r["signal"], "signals": stack,
    }
    return result
