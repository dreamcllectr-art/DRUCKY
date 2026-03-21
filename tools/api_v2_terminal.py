"""V2 Terminal feed — FT/Economist-style home page data.

Combines macro regime, sector rotation, insider flow, score movers, catalysts,
and live news headlines for the terminal dashboard.
"""
from fastapi import APIRouter
from tools.db import query
import time
import logging

logger = logging.getLogger(__name__)

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
    """Full market terminal feed — ENTIRE market, not filtered picks.
    Fat pitches live in /v2/gates. This is the FT/Bloomberg front page.
    """
    cached = _cache_get("terminal")
    if cached:
        return cached

    # 1. Macro regime
    macro = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    macro_data = macro[0] if macro else {}

    # 2. Market breadth
    breadth = query("SELECT * FROM market_breadth ORDER BY date DESC LIMIT 1")
    breadth_data = breadth[0] if breadth else {}

    # 3. Sector rotation — ALL 11 sectors ranked by avg signal score + bull/bear sentiment
    sectors = query("""
        SELECT u.sector,
               COUNT(*) as stock_count,
               ROUND(AVG(s.composite_score), 1) as avg_score,
               SUM(CASE WHEN s.signal LIKE '%BUY%' THEN 1 ELSE 0 END) as bull_count,
               SUM(CASE WHEN s.signal LIKE '%SELL%' THEN 1 ELSE 0 END) as bear_count,
               SUM(CASE WHEN s.signal = 'NEUTRAL' THEN 1 ELSE 0 END) as neutral_count,
               MAX(s.composite_score) as top_score
        FROM signals s
        JOIN stock_universe u ON s.symbol = u.symbol
        WHERE s.date = (SELECT MAX(date) FROM signals)
        AND u.sector IS NOT NULL
        GROUP BY u.sector
        ORDER BY avg_score DESC
    """)

    # 4. Biggest score movers across the ENTIRE universe
    movers = query("""
        SELECT t.symbol, t.convergence_score, t.conviction_level,
               t.module_count,
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
        LIMIT 20
    """)

    # 5. Strongest catalysts across the ENTIRE universe (not filtered to our picks)
    catalysts = query("""
        SELECT cat.symbol, cat.catalyst_type, cat.catalyst_strength,
               cat.catalyst_detail, cat.date,
               u.name, u.sector
        FROM catalyst_scores cat
        LEFT JOIN stock_universe u ON cat.symbol = u.symbol
        WHERE cat.date >= date('now', '-5 days')
        AND cat.catalyst_strength >= 55
        ORDER BY cat.catalyst_strength DESC
        LIMIT 20
    """)

    # 6. Insider intelligence — aggregated signals across the ENTIRE universe
    insider_flow = []
    try:
        insider_flow = query("""
            SELECT ins.symbol, ins.insider_score, ins.cluster_buy, ins.cluster_count,
                   ins.unusual_volume_flag, ins.total_buy_value_30d, ins.total_sell_value_30d,
                   ins.narrative, ins.top_buyer, ins.large_buys_count,
                   u.name as company_name, u.sector
            FROM insider_signals ins
            LEFT JOIN stock_universe u ON ins.symbol = u.symbol
            WHERE ins.date = (SELECT MAX(date) FROM insider_signals)
            AND ins.insider_score >= 25
            ORDER BY ins.insider_score DESC
            LIMIT 40
        """)
    except Exception:
        # Fallback: aggregate from individual transactions if insider_signals missing
        try:
            insider_flow = query("""
                SELECT it.symbol,
                       COUNT(*) as cluster_count,
                       SUM(CASE WHEN it.transaction_type IN ('P','BUY') THEN 1 ELSE 0 END) as cluster_buy,
                       0 as unusual_volume_flag,
                       SUM(CASE WHEN it.transaction_type IN ('P','BUY') THEN COALESCE(it.value,0) ELSE 0 END) as total_buy_value_30d,
                       SUM(CASE WHEN it.transaction_type NOT IN ('P','BUY') THEN ABS(COALESCE(it.value,0)) ELSE 0 END) as total_sell_value_30d,
                       NULL as narrative,
                       MAX(it.insider_name) as top_buyer,
                       0 as large_buys_count,
                       u.name as company_name, u.sector,
                       COUNT(*) * 10 as insider_score
                FROM insider_transactions it
                LEFT JOIN stock_universe u ON it.symbol = u.symbol
                WHERE it.date >= date('now', '-30 days')
                GROUP BY it.symbol
                HAVING SUM(CASE WHEN it.transaction_type IN ('P','BUY') THEN COALESCE(it.value,0) ELSE 0 END) >= 100000
                ORDER BY total_buy_value_30d DESC
                LIMIT 40
            """)
        except Exception:
            pass

    # 7. Key economic indicators
    key_indicators = []
    try:
        key_indicators = query("""
            SELECT indicator_id, name, category, value, prev_value,
                   yoy_pct_change, z_score
            FROM economic_dashboard
            WHERE date = (SELECT MAX(date) FROM economic_dashboard)
            AND category IN ('RATES', 'INFLATION', 'GROWTH', 'EMPLOYMENT', 'CREDIT')
            ORDER BY ABS(COALESCE(z_score, 0)) DESC
            LIMIT 12
        """)
    except Exception:
        pass

    # 8. Pipeline status (just the count for the header CTA)
    gate_summary = query(
        "SELECT * FROM gate_run_history ORDER BY date DESC, rowid DESC LIMIT 1"
    )
    gate_data = gate_summary[0] if gate_summary else {}

    result = {
        "macro": macro_data,
        "breadth": breadth_data,
        "sectors": sectors,
        "insider_flow": insider_flow,
        "score_movers": movers,
        "catalysts": catalysts,
        "key_indicators": key_indicators,
        "pipeline": {
            "fat_pitches_count": gate_data.get("gate_10_passed", 0),
            "total_assets": gate_data.get("total_assets", 0),
            "date": gate_data.get("date"),
        },
    }
    _cache_set("terminal", result)
    return result


@router.get("/api/v2/headlines")
def market_headlines():
    """Live market news headlines — Finnhub general news + DB headlines.
    Short TTL (60s) so the ticker feels live.
    """
    cached = _cache_get("headlines")
    if cached:
        return cached

    headlines = []

    # 1. Live general market news from Finnhub
    try:
        from tools.config import FINNHUB_API_KEY
        if FINNHUB_API_KEY:
            import finnhub
            client = finnhub.Client(api_key=FINNHUB_API_KEY)
            # General market news categories: general, forex, crypto, merger
            news = client.general_news("general", min_id=0)
            for item in (news or [])[:30]:
                headlines.append({
                    "headline": item.get("headline", ""),
                    "source": item.get("source", ""),
                    "url": item.get("url", ""),
                    "symbol": None,
                    "timestamp": item.get("datetime"),
                    "category": "market",
                    "summary": item.get("summary", "")[:200] if item.get("summary") else "",
                })
    except Exception as e:
        logger.warning(f"Finnhub news fetch failed: {e}")

    # 2. Stock-specific news from news_displacement table
    try:
        db_news = query("""
            SELECT nd.symbol, nd.news_headline, nd.news_source, nd.date,
                   nd.materiality_score, nd.expected_direction,
                   u.name as company_name
            FROM news_displacement nd
            LEFT JOIN stock_universe u ON nd.symbol = u.symbol
            WHERE nd.date >= date('now', '-7 days')
            AND nd.news_headline IS NOT NULL
            ORDER BY nd.materiality_score DESC, nd.date DESC
            LIMIT 20
        """)
        for item in db_news:
            headlines.append({
                "headline": item["news_headline"],
                "source": item["news_source"] or "Market",
                "url": None,
                "symbol": item["symbol"],
                "timestamp": None,
                "category": "stock",
                "summary": "",
                "company_name": item.get("company_name"),
                "materiality": item.get("materiality_score"),
                "direction": item.get("expected_direction"),
            })
    except Exception:
        pass

    # 3. M&A headlines from ma_signals
    try:
        ma_news = query("""
            SELECT m.symbol, m.best_headline, m.date, m.ma_score,
                   m.deal_stage, u.name as company_name
            FROM ma_signals m
            LEFT JOIN stock_universe u ON m.symbol = u.symbol
            WHERE m.date >= date('now', '-14 days')
            AND m.best_headline IS NOT NULL
            AND m.ma_score >= 40
            ORDER BY m.ma_score DESC, m.date DESC
            LIMIT 10
        """)
        for item in ma_news:
            headlines.append({
                "headline": item["best_headline"],
                "source": "M&A Intel",
                "url": None,
                "symbol": item["symbol"],
                "timestamp": None,
                "category": "ma",
                "summary": "",
                "company_name": item.get("company_name"),
                "deal_stage": item.get("deal_stage"),
            })
    except Exception:
        pass

    # Deduplicate by headline text
    seen = set()
    unique = []
    for h in headlines:
        key = (h["headline"] or "")[:80]
        if key and key not in seen:
            seen.add(key)
            unique.append(h)

    result = {"headlines": unique, "count": len(unique)}
    # Shorter TTL for news — 60 seconds
    _cache["headlines"] = {"data": result, "ts": time.time() - (_CACHE_TTL - 60)}
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
