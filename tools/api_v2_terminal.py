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

# Headlines-only cache: 60s TTL to avoid hammering Finnhub rate limits
_headlines_cache: dict = {}
_HEADLINES_TTL = 60


@router.get("/api/v2/terminal")
def terminal_feed():
    """Full market terminal feed — ENTIRE market, not filtered picks.
    Fat pitches live in /v2/gates. This is the FT/Bloomberg front page.
    """
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
               ROUND(AVG(s.composite_score)::numeric, 1) as avg_score,
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
               ROUND((t.convergence_score - COALESCE(y.convergence_score, 0))::numeric, 1) as delta,
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
            WHERE ins.date >= date('now', '-30 days')
            AND ins.insider_score >= 25
            AND ins.insider_score = (
                SELECT MAX(i2.insider_score) FROM insider_signals i2
                WHERE i2.symbol = ins.symbol AND i2.date >= date('now', '-30 days')
            )
            ORDER BY ins.insider_score DESC
            LIMIT 40
        """)
    except Exception as e:
        logger.warning("insider_signals query failed, falling back to transactions: %s", e)
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
        except Exception as e2:
            logger.warning("insider_transactions fallback also failed: %s", e2)

    # 7. Key economic indicators — all categories for tabbed left panel
    key_indicators = []
    try:
        key_indicators = query("""
            SELECT indicator_id, name, category, value, prev_value,
                   mom_change, yoy_change, zscore, trend
            FROM economic_dashboard
            WHERE date = (SELECT MAX(date) FROM economic_dashboard)
            ORDER BY category, ABS(COALESCE(zscore, 0)) DESC
        """)
    except Exception as e:
        logger.warning("economic_dashboard query failed: %s", e)

    # 8. M&A intelligence — top targets + recent rumors
    ma_intel = []
    try:
        ma_intel = query("""
            SELECT m.symbol, m.ma_score, m.deal_stage, m.expected_premium_pct,
                   m.acquirer_name, m.narrative, m.best_headline, m.date,
                   u.name as company_name, u.sector
            FROM ma_signals m
            LEFT JOIN stock_universe u ON m.symbol = u.symbol
            WHERE m.date >= date('now', '-30 days')
            AND m.ma_score >= 30
            ORDER BY m.ma_score DESC
            LIMIT 20
        """)
    except Exception as e:
        logger.warning("ma_signals query failed: %s", e)

    ma_rumors = []
    try:
        ma_rumors = query("""
            SELECT symbol, rumor_headline, credibility_score, date, rumor_source
            FROM ma_rumors
            WHERE date >= date('now', '-14 days')
            ORDER BY credibility_score DESC, date DESC
            LIMIT 10
        """)
    except Exception as e:
        logger.warning("ma_rumors query failed: %s", e)

    # 9. Energy + sector anomalies — surface supply/demand dislocations
    energy_anomalies = []
    try:
        energy_anomalies = query("""
            SELECT e.symbol, e.energy_intel_score as energy_score,
                   e.inventory_signal, e.production_signal,
                   e.demand_signal, e.trade_flow_signal, e.global_balance_signal,
                   e.ticker_category, e.narrative, e.date,
                   u.name as company_name, u.sector
            FROM energy_intel_signals e
            LEFT JOIN stock_universe u ON e.symbol = u.symbol
            WHERE e.date >= date('now', '-7 days')
            AND e.energy_intel_score >= 40
            AND e.date = (SELECT MAX(e2.date) FROM energy_intel_signals e2 WHERE e2.symbol = e.symbol)
            ORDER BY e.energy_intel_score DESC
            LIMIT 15
        """)
    except Exception as e:
        logger.warning("energy_intel_signals query failed: %s", e)

    # 10. Pipeline status
    gate_summary = query(
        "SELECT * FROM gate_run_history ORDER BY date DESC LIMIT 1"
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
        "ma_intel": ma_intel,
        "ma_rumors": ma_rumors,
        "energy_anomalies": energy_anomalies,
        "pipeline": {
            "fat_pitches_count": gate_data.get("gate_10_passed", 0),
            "total_assets": gate_data.get("total_assets", 0),
            "date": gate_data.get("date"),
        },
    }
    return result


@router.get("/api/v2/headlines")
def market_headlines():
    """Live market news headlines — stock-specific news filtered to our universe.
    Short TTL (60s) so the ticker feels live.
    """
    cached = _headlines_cache.get("h")
    if cached and (time.time() - cached["ts"]) < _HEADLINES_TTL:
        return cached["data"]

    headlines = []

    # 1. Live stock-specific news from Finnhub for our top conviction names
    try:
        from tools.config import FINNHUB_API_KEY
        if FINNHUB_API_KEY:
            import finnhub, time as _time
            client = finnhub.Client(api_key=FINNHUB_API_KEY)
            # Get top 8 conviction symbols from convergence_signals
            top_symbols = query("""
                SELECT DISTINCT symbol FROM convergence_signals
                WHERE conviction_level IN ('HIGH', 'NOTABLE')
                ORDER BY signal_count DESC, composite_score DESC
                LIMIT 8
            """)
            for row in (top_symbols or []):
                sym = row["symbol"]
                try:
                    news = client.company_news(sym,
                        _from=_time.strftime("%Y-%m-%d", _time.gmtime(_time.time() - 7*86400)),
                        to=_time.strftime("%Y-%m-%d", _time.gmtime()))
                    for item in (news or [])[:3]:
                        if item.get("headline"):
                            headlines.append({
                                "headline": item["headline"],
                                "source": item.get("source", ""),
                                "url": item.get("url", ""),
                                "symbol": sym,
                                "timestamp": item.get("datetime"),
                                "category": "stock",
                                "summary": item.get("summary", "")[:200] if item.get("summary") else "",
                            })
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Finnhub company news fetch failed: {e}")

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
    _headlines_cache["h"] = {"data": result, "ts": time.time()}
    return result


@router.get("/api/v2/stock/{symbol}")
def stock_panel(symbol: str):
    """Full stock panel data — prices, signal, fundamentals, insider, catalyst."""
    symbol = symbol.upper()

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
        """SELECT last_gate_passed, gate_10, fail_reason, entry_mode FROM gate_results
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

    # M&A signals for this stock
    ma_signal = None
    ma_stock_rumors = []
    try:
        ma_rows = query(
            "SELECT * FROM ma_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol]
        )
        ma_signal = ma_rows[0] if ma_rows else None
        ma_stock_rumors = query(
            "SELECT * FROM ma_rumors WHERE symbol = ? ORDER BY date DESC LIMIT 5", [symbol]
        )
    except Exception:
        pass

    # Flag delisted/acquired stocks: no price data AND either not in universe or universe has no name.
    no_prices = len(prices) == 0
    no_signal = not signal
    no_fundamentals = len(fundamentals) == 0
    delisted = no_prices and no_signal and no_fundamentals

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
        "ma_signal": ma_signal,
        "ma_rumors": ma_stock_rumors,
        "delisted": delisted,
    }
    return result
