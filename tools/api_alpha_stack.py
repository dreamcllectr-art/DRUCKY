"""Alpha Stack API — unified signal intelligence for high-conviction stocks.

Returns all signal sources stacked per symbol, filtered by gate level.
This is the institutional-grade intelligence view: every independent data
source pointing at the same name.

Routes:
  GET /api/alpha/stack?min_gate=5   — ranked stock list with full signal stack
  GET /api/alpha/stack/{symbol}     — full signal stack for one symbol
"""
from fastapi import APIRouter, Query
from tools.db import query
import json

router = APIRouter()


def _safe_json(val):
    if val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return val
    return val


def _build_signal_stack(symbol: str) -> dict:
    """Pull all signal sources for one symbol."""
    stack = {}

    # Insider
    rows = query(
        "SELECT * FROM insider_signals WHERE symbol=? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if rows:
        r = rows[0]
        stack["insider"] = {
            "score": r["insider_score"],
            "cluster_buy": r["cluster_buy"],
            "cluster_count": r["cluster_count"],
            "large_buys_count": r["large_buys_count"],
            "total_buy_value_30d": r["total_buy_value_30d"],
            "total_sell_value_30d": r["total_sell_value_30d"],
            "unusual_volume_flag": r["unusual_volume_flag"],
            "top_buyer": r["top_buyer"],
            "narrative": r["narrative"],
            "date": r["date"],
        }

    # Pattern scan
    rows = query(
        "SELECT * FROM pattern_scan WHERE symbol=? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if rows:
        r = rows[0]
        stack["patterns"] = {
            "score": r["pattern_scan_score"],
            "wyckoff_phase": r["wyckoff_phase"],
            "wyckoff_confidence": r["wyckoff_confidence"],
            "patterns_detected": _safe_json(r["patterns_detected"]),
            "momentum_score": r["momentum_score"],
            "compression_score": r["compression_score"],
            "squeeze_active": r["squeeze_active"],
            "hurst_exponent": r["hurst_exponent"],
            "vol_regime": r["vol_regime"],
            "rotation_score": r["rotation_score"],
            "date": r["date"],
        }

    # Alt data
    rows = query(
        "SELECT * FROM alt_data_scores WHERE symbol=? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if rows:
        r = rows[0]
        stack["alt_data"] = {
            "score": r["alt_data_score"],
            "signals": _safe_json(r["contributing_signals"]),
            "date": r["date"],
        }

    # Options intel
    rows = query(
        "SELECT * FROM options_intel WHERE symbol=? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if rows:
        r = rows[0]
        stack["options"] = {
            "score": r["options_score"],
            "iv_rank": r["iv_rank"],
            "iv_percentile": r["iv_percentile"],
            "pc_signal": r["pc_signal"],
            "unusual_activity_count": r["unusual_activity_count"],
            "unusual_direction_bias": r["unusual_direction_bias"],
            "dealer_regime": r["dealer_regime"],
            "skew_direction": r["skew_direction"],
            "expected_move_pct": r["expected_move_pct"],
            "unusual_activity": _safe_json(r["unusual_activity"]),
            "date": r["date"],
        }

    # Supply chain
    rows = query(
        "SELECT * FROM supply_chain_scores WHERE symbol=? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if rows:
        r = rows[0]
        stack["supply_chain"] = {
            "score": r["supply_chain_score"],
            "rail_score": r["rail_score"],
            "shipping_score": r["shipping_score"],
            "trucking_score": r["trucking_score"],
            "details": _safe_json(r["details"]),
            "date": r["date"],
        }

    # M&A
    rows = query(
        "SELECT * FROM ma_signals WHERE symbol=? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if rows:
        r = rows[0]
        stack["ma"] = {
            "score": r["ma_score"],
            "deal_stage": r["deal_stage"],
            "rumor_credibility": r["rumor_credibility"],
            "acquirer_name": r["acquirer_name"],
            "expected_premium_pct": r["expected_premium_pct"],
            "best_headline": r["best_headline"],
            "narrative": r["narrative"],
            "date": r["date"],
        }

    # Pairs (either leg)
    rows = query(
        """SELECT * FROM pair_signals
           WHERE (symbol_a=? OR symbol_b=?) AND status='active'
           ORDER BY pairs_score DESC LIMIT 3""",
        [symbol, symbol]
    )
    if rows:
        stack["pairs"] = [
            {
                "symbol_a": r["symbol_a"],
                "symbol_b": r["symbol_b"],
                "direction": r["direction"],
                "spread_zscore": r["spread_zscore"],
                "score": r["pairs_score"],
                "narrative": r["narrative"],
                "date": r["date"],
            }
            for r in rows
        ]

    # Prediction markets
    rows = query(
        "SELECT * FROM prediction_market_signals WHERE symbol=? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if rows:
        r = rows[0]
        stack["prediction_markets"] = {
            "score": r["pm_score"],
            "market_count": r["market_count"],
            "net_impact": r["net_impact"],
            "status": r["status"],
            "narrative": r["narrative"],
            "date": r["date"],
        }

    # Digital exhaust
    rows = query(
        "SELECT * FROM digital_exhaust_scores WHERE symbol=? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if rows:
        r = rows[0]
        stack["digital_exhaust"] = {
            "score": r["digital_exhaust_score"],
            "app_score": r["app_score"],
            "github_score": r["github_score"],
            "pricing_score": r["pricing_score"],
            "domain_score": r["domain_score"],
            "details": _safe_json(r["details"]),
            "date": r["date"],
        }

    # Compute signal count (how many sources have a positive signal)
    signal_count = sum(1 for k, v in stack.items()
                       if k != "pairs" and v and (v.get("score") or 0) >= 50)
    if "pairs" in stack:
        signal_count += 1
    stack["_signal_count"] = signal_count

    return stack


@router.get("/api/alpha/stack")
def get_alpha_stack(min_gate: int = Query(default=5, ge=0, le=10)):
    """All stocks that passed >= min_gate, with full signal stacks, ranked."""
    # Get qualifying stocks with context
    gate_rows = query(
        """SELECT gr.symbol, gr.last_gate_passed, gr.gate_10 as is_fat_pitch,
                  s.composite_score, c.convergence_score, s.signal,
                  su.name, su.sector, gr.asset_class
           FROM gate_results gr
           LEFT JOIN stock_universe su ON gr.symbol = su.symbol
           LEFT JOIN signals s ON gr.symbol = s.symbol AND s.date = (SELECT MAX(date) FROM signals)
           LEFT JOIN convergence_signals c ON gr.symbol = c.symbol AND c.date = (SELECT MAX(date) FROM convergence_signals)
           WHERE gr.last_gate_passed >= ? AND gr.date = (SELECT MAX(date) FROM gate_results)
           ORDER BY gr.last_gate_passed DESC, s.composite_score DESC""",
        [min_gate]
    )

    results = []
    for r in gate_rows:
        stack = _build_signal_stack(r["symbol"])
        results.append({
            "symbol": r["symbol"],
            "name": r["name"],
            "sector": r["sector"],
            "asset_class": r["asset_class"],
            "last_gate_passed": r["last_gate_passed"],
            "is_fat_pitch": bool(r["is_fat_pitch"]),
            "composite_score": r["composite_score"],
            "convergence_score": r["convergence_score"],
            "signal": r["signal"],
            "signal_count": stack.pop("_signal_count", 0),
            "signals": stack,
        })

    # Re-rank by signal breadth + gate level
    results.sort(key=lambda x: (x["last_gate_passed"], x["signal_count"], x["composite_score"] or 0), reverse=True)
    return results


@router.get("/api/alpha/stack/{symbol}")
def get_alpha_stack_symbol(symbol: str):
    """Full signal stack for one symbol."""
    symbol = symbol.upper()

    gate_rows = query(
        """SELECT gr.symbol, gr.last_gate_passed, gr.gate_10 as is_fat_pitch,
                  s.composite_score, c.convergence_score, s.signal,
                  su.name, su.sector, gr.asset_class
           FROM gate_results gr
           LEFT JOIN stock_universe su ON gr.symbol = su.symbol
           LEFT JOIN signals s ON gr.symbol = s.symbol AND s.date = (SELECT MAX(date) FROM signals)
           LEFT JOIN convergence_signals c ON gr.symbol = c.symbol AND c.date = (SELECT MAX(date) FROM convergence_signals)
           WHERE gr.symbol = ? AND gr.date = (SELECT MAX(date) FROM gate_results)""",
        [symbol]
    )

    if not gate_rows:
        return {"symbol": symbol, "last_gate_passed": 0, "signals": {}}

    r = gate_rows[0]
    stack = _build_signal_stack(symbol)
    stack.pop("_signal_count", None)

    return {
        "symbol": r["symbol"],
        "name": r["name"],
        "sector": r["sector"],
        "asset_class": r["asset_class"],
        "last_gate_passed": r["last_gate_passed"],
        "is_fat_pitch": bool(r["is_fat_pitch"]),
        "composite_score": r["composite_score"],
        "convergence_score": r["convergence_score"],
        "signal": r["signal"],
        "signals": stack,
    }
