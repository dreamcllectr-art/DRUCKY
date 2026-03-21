"""V2 Terminal feed — FT/Economist-style home page data.

Combines macro regime, fat pitches, insider flow, score movers, and catalysts
into a single fast endpoint for the terminal dashboard.
"""
from fastapi import APIRouter
from tools.db import query
import time

router = APIRouter()

_cache: dict = {}
_CACHE_TTL = 120  # 2 minutes


def _cache_get(key: str):
    e = _cache.get(key)
    if e and (time.time() - e["ts"]) < _CACHE_TTL:
        return e["data"]
    return None


def _cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}


@router.get("/api/v2/terminal")
def terminal_feed():
    """Full terminal feed — macro + fat pitches + insider flow + movers + catalysts."""
    cached = _cache_get("terminal")
    if cached:
        return cached

    # 1. Macro regime
    macro = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    macro_data = macro[0] if macro else {}

    # 2. Fat pitches with full context
    fat_pitches = query("""
        SELECT gr.symbol, gr.asset_class, gr.date,
               u.name, u.sector,
               s.composite_score, s.signal, s.entry_price, s.target_price,
               s.stop_loss, s.rr_ratio, s.position_size_dollars,
               c.convergence_score, c.conviction_level, c.narrative, c.module_count,
               cat.catalyst_type, cat.catalyst_strength, cat.catalyst_detail
        FROM gate_results gr
        LEFT JOIN stock_universe u ON gr.symbol = u.symbol
        LEFT JOIN signals s ON gr.symbol = s.symbol
            AND s.date = (SELECT MAX(date) FROM signals WHERE symbol = gr.symbol)
        LEFT JOIN convergence_signals c ON gr.symbol = c.symbol
            AND c.date = (SELECT MAX(date) FROM convergence_signals WHERE symbol = gr.symbol)
        LEFT JOIN catalyst_scores cat ON gr.symbol = cat.symbol
            AND cat.date = (SELECT MAX(date) FROM catalyst_scores WHERE symbol = gr.symbol)
        WHERE gr.date = (SELECT MAX(date) FROM gate_results)
        AND gr.gate_10 = 1
        ORDER BY COALESCE(s.composite_score, 0) DESC
        LIMIT 20
    """)

    # 3. Insider flow — individual transactions sorted by dollar value
    insider_flow = []
    try:
        insider_flow = query("""
            SELECT it.symbol, it.transaction_type, it.date as transaction_date,
                   it.shares, it.price, it.value,
                   it.insider_name, it.insider_title,
                   u.name as company_name, u.sector,
                   ins.insider_score, ins.cluster_buy, ins.cluster_count
            FROM insider_transactions it
            LEFT JOIN stock_universe u ON it.symbol = u.symbol
            LEFT JOIN insider_signals ins ON it.symbol = ins.symbol
                AND ins.date = (SELECT MAX(date) FROM insider_signals WHERE symbol = it.symbol)
            WHERE it.date >= date('now', '-14 days')
            AND ABS(COALESCE(it.value, 0)) >= 100000
            ORDER BY ABS(COALESCE(it.value, 0)) DESC
            LIMIT 40
        """)
    except Exception:
        # Fallback: aggregate insider signals if transactions table is empty/missing
        try:
            insider_flow = query("""
                SELECT ins.symbol, 'BUY' as transaction_type, ins.date as transaction_date,
                       ins.large_buys_count as shares, NULL as price,
                       ins.total_buy_value_30d as value,
                       ins.top_buyer as insider_name, NULL as insider_title,
                       u.name as company_name, u.sector,
                       ins.insider_score, ins.cluster_buy, ins.cluster_count
                FROM insider_signals ins
                LEFT JOIN stock_universe u ON ins.symbol = u.symbol
                WHERE ins.date >= date('now', '-14 days')
                AND ins.total_buy_value_30d >= 100000
                ORDER BY ins.total_buy_value_30d DESC
                LIMIT 40
            """)
        except Exception:
            pass

    # 4. Score movers — biggest convergence changes today
    movers = query("""
        SELECT t.symbol, t.convergence_score, t.conviction_level,
               t.narrative, t.module_count,
               y.convergence_score as prev_score,
               ROUND(t.convergence_score - COALESCE(y.convergence_score, 0), 1) as delta,
               u.name, u.sector
        FROM convergence_signals t
        LEFT JOIN convergence_signals y ON t.symbol = y.symbol
            AND y.date = (
                SELECT MAX(date) FROM convergence_signals
                WHERE date < (SELECT MAX(date) FROM convergence_signals)
            )
        LEFT JOIN stock_universe u ON t.symbol = u.symbol
        WHERE t.date = (SELECT MAX(date) FROM convergence_signals)
        AND ABS(t.convergence_score - COALESCE(y.convergence_score, 0)) > 5
        ORDER BY t.convergence_score - COALESCE(y.convergence_score, 0) DESC
        LIMIT 12
    """)

    # 5. Strong catalyst events (recent)
    catalysts = query("""
        SELECT cat.symbol, cat.catalyst_type, cat.catalyst_strength,
               cat.catalyst_detail, cat.date,
               u.name, u.sector,
               s.composite_score, s.signal
        FROM catalyst_scores cat
        LEFT JOIN stock_universe u ON cat.symbol = u.symbol
        LEFT JOIN signals s ON cat.symbol = s.symbol
            AND s.date = (SELECT MAX(date) FROM signals WHERE symbol = cat.symbol)
        WHERE cat.date >= date('now', '-5 days')
        AND cat.catalyst_strength >= 55
        ORDER BY cat.catalyst_strength DESC
        LIMIT 15
    """)

    # 6. Key economic indicators
    key_indicators = []
    try:
        key_indicators = query("""
            SELECT indicator_id, name, category, value, prev_value,
                   yoy_pct_change, z_score
            FROM economic_dashboard
            WHERE date = (SELECT MAX(date) FROM economic_dashboard)
            AND category IN ('RATES', 'INFLATION', 'GROWTH', 'EMPLOYMENT', 'CREDIT')
            ORDER BY ABS(COALESCE(z_score, 0)) DESC
            LIMIT 10
        """)
    except Exception:
        pass

    # 7. Gate funnel summary (counts per gate)
    gate_summary = query(
        "SELECT * FROM gate_run_history ORDER BY date DESC, rowid DESC LIMIT 1"
    )
    gate_data = gate_summary[0] if gate_summary else {}

    result = {
        "macro": macro_data,
        "fat_pitches": fat_pitches,
        "insider_flow": insider_flow,
        "score_movers": movers,
        "catalysts": catalysts,
        "key_indicators": key_indicators,
        "gate_summary": {
            "total": gate_data.get("total_assets", 0),
            "fat_pitches_count": gate_data.get("gate_10_passed", 0),
            "gate_counts": {str(i): gate_data.get(f"gate_{i}_passed", 0) for i in range(1, 11)},
            "date": gate_data.get("date"),
        },
    }
    _cache_set("terminal", result)
    return result


@router.get("/api/v2/stock/{symbol}")
def stock_panel(symbol: str):
    """Full stock panel data — prices, signal, fundamentals, insider, catalyst."""
    symbol = symbol.upper()
    cached = _cache_get(f"stock_{symbol}")
    if cached:
        return cached

    prices = query("""
        SELECT date, open, high, low, close, volume
        FROM price_data WHERE symbol = ?
        ORDER BY date DESC LIMIT 180
    """, [symbol])

    signal = query(
        "SELECT * FROM signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol]
    )
    convergence = query(
        "SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol]
    )
    fundamentals = query(
        "SELECT metric, value FROM fundamentals WHERE symbol = ?", [symbol]
    )
    universe = query(
        "SELECT * FROM stock_universe WHERE symbol = ?", [symbol]
    )
    catalyst = query(
        "SELECT * FROM catalyst_scores WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol]
    )
    insider = query(
        "SELECT * FROM insider_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol]
    )
    gate = query(
        """SELECT last_gate_passed, gate_10, fail_reason FROM gate_results
           WHERE symbol = ? ORDER BY date DESC LIMIT 1""", [symbol]
    )

    # Recent insider transactions
    transactions = []
    try:
        transactions = query("""
            SELECT transaction_type, date, shares, price, value, insider_name, insider_title
            FROM insider_transactions WHERE symbol = ?
            ORDER BY date DESC LIMIT 10
        """, [symbol])
    except Exception:
        pass

    result = {
        "symbol": symbol,
        "prices": prices,
        "signal": signal[0] if signal else None,
        "convergence": convergence[0] if convergence else None,
        "fundamentals": {r["metric"]: r["value"] for r in fundamentals},
        "info": universe[0] if universe else {},
        "catalyst": catalyst[0] if catalyst else None,
        "insider": insider[0] if insider else None,
        "insider_transactions": transactions,
        "gate": gate[0] if gate else None,
    }
    _cache_set(f"stock_{symbol}", result)
    return result
