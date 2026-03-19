"""Market module routes — worldview, energy, patterns/options, and Alt Alpha II modules
(earnings-nlp, gov-intel, labor-intel, supply-chain, digital-exhaust, pharma-intel)."""

from fastapi import APIRouter
from tools.db import query

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
# WORLDVIEW / GLOBAL MACRO
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/worldview")
def worldview():
    return query("""
        SELECT * FROM worldview_signals
        WHERE date = (SELECT MAX(date) FROM worldview_signals)
        ORDER BY confidence DESC LIMIT 50
    """)


@router.get("/api/worldview/theses")
def worldview_theses():
    rows = query("""
        SELECT thesis, COUNT(*) as symbol_count,
               AVG(confidence) as avg_score, direction
        FROM worldview_signals
        WHERE date = (SELECT MAX(date) FROM worldview_signals)
        GROUP BY thesis
        ORDER BY avg_score DESC
    """)
    return rows


@router.get("/api/worldview/world-macro")
def world_macro():
    return query("SELECT * FROM world_macro_indicators ORDER BY date DESC LIMIT 100")


@router.get("/api/worldview/{symbol}")
def worldview_symbol(symbol: str):
    return query("SELECT * FROM worldview_signals WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])


# ═══════════════════════════════════════════════════════════════════════
# ENERGY INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/energy-intel")
def energy_intel(min_score: int = 0):
    signals = query("""
        SELECT * FROM energy_intel_signals
        WHERE date >= date('now', '-7 days') AND energy_intel_score >= ?
        ORDER BY energy_intel_score DESC
    """, [min_score])
    anomalies = query("SELECT * FROM energy_supply_anomalies ORDER BY date DESC LIMIT 20")
    return {"signals": signals, "summary": {}, "anomalies": anomalies}


@router.get("/api/energy-intel/supply-balance")
def energy_supply():
    return query("SELECT * FROM energy_eia_enhanced ORDER BY date DESC LIMIT 100")


@router.get("/api/energy-intel/production")
def energy_production():
    # US Crude Production (weekly field production)
    production = query(
        "SELECT date, value FROM energy_eia_enhanced WHERE series_id = 'PET.WCRFPUS2.W' ORDER BY date DESC LIMIT 52")
    # Refinery utilization
    refinery_util = query(
        "SELECT date, value FROM energy_eia_enhanced WHERE series_id = 'PET.WPULEUS3.W' ORDER BY date DESC LIMIT 52")
    # Total Product Supplied (demand proxy)
    product_supplied = query(
        "SELECT date, value FROM energy_eia_enhanced WHERE series_id = 'PET.WRPUPUS2.W' ORDER BY date DESC LIMIT 52")
    # Crack spread: gasoline spot minus WTI
    gasoline = {r["date"]: r["value"] for r in query(
        "SELECT date, value FROM energy_eia_enhanced WHERE series_id = 'PET.EER_EPMRU_PF4_RGC_DPG.W' ORDER BY date DESC LIMIT 52")}
    wti = {r["date"]: r["value"] for r in query(
        "SELECT date, value FROM energy_eia_enhanced WHERE series_id = 'PET.RWTC.W' ORDER BY date DESC LIMIT 52")}
    crack_spread = sorted(
        [{"date": d, "value": round((gasoline[d] * 42) - wti[d], 2)}
         for d in gasoline if d in wti and gasoline[d] and wti[d]],
        key=lambda x: x["date"], reverse=True)
    return {
        "production": production,
        "refinery_util": refinery_util,
        "product_supplied": product_supplied,
        "crack_spread": crack_spread,
    }


@router.get("/api/energy-intel/trade-flows")
def energy_trade_flows():
    flows = query("""SELECT reporter, partner, commodity_code, period, trade_flow, value_usd, quantity_kg,
        date, country, product, flow_type, value FROM energy_trade_flows ORDER BY date DESC LIMIT 200""")
    imports = [f for f in flows if (f.get("trade_flow") or f.get("flow_type") or "").lower() in ("import", "imports")]
    exports = [f for f in flows if (f.get("trade_flow") or f.get("flow_type") or "").lower() in ("export", "exports")]
    by_country: dict = {}
    for f in imports:
        c = f.get("partner") or f.get("country") or "Unknown"
        by_country[c] = by_country.get(c, 0) + (f.get("value_usd") or f.get("value") or 0)
    import_by_country = [{"country": k, "value": v} for k, v in sorted(by_country.items(), key=lambda x: -x[1])[:20]]
    return {"imports": imports[:50], "exports": exports[:50], "padd_stocks": [], "import_by_country": import_by_country, "comtrade": flows[:50]}


@router.get("/api/energy-intel/global-balance")
def energy_global_balance():
    jodi = query("SELECT * FROM energy_jodi_data ORDER BY date DESC LIMIT 100")
    stocks = query("""SELECT country, value, mom_change FROM energy_jodi_data
        WHERE indicator = 'closing_stocks' AND date = (SELECT MAX(date) FROM energy_jodi_data WHERE indicator = 'closing_stocks')
        ORDER BY value DESC LIMIT 20""")
    prod = query("""SELECT SUM(CASE WHEN indicator='production' THEN value ELSE 0 END) as total_production,
        SUM(CASE WHEN indicator='demand' THEN value ELSE 0 END) as total_demand
        FROM energy_jodi_data WHERE date = (SELECT MAX(date) FROM energy_jodi_data)""")
    balance = None
    if prod and prod[0].get("total_production"):
        balance = {"production": prod[0]["total_production"], "demand": prod[0]["total_demand"],
                   "surplus": (prod[0]["total_production"] or 0) - (prod[0]["total_demand"] or 0)}
    return {"jodi_data": jodi, "balance": balance, "global_stocks": stocks}


# ═══════════════════════════════════════════════════════════════════════
# PATTERNS & OPTIONS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/patterns")
def patterns(min_score: int = 0, sector: str = None, phase: str = None, squeeze_only: bool = False):
    sql = """
        SELECT po.*, su.sector, su.name FROM pattern_options_signals po
        JOIN stock_universe su ON po.symbol = su.symbol
        WHERE (po.symbol, po.date) IN (SELECT symbol, MAX(date) FROM pattern_options_signals WHERE date >= date('now', '-7 days') GROUP BY symbol)
          AND COALESCE(po.pattern_options_score, po.score, 0) >= ?
    """
    params = [min_score]
    if sector:
        sql += " AND su.sector = ?"
        params.append(sector)
    sql += " ORDER BY COALESCE(po.pattern_options_score, po.score, 0) DESC LIMIT 100"
    return query(sql, params)


@router.get("/api/patterns/layers/{symbol}")
def pattern_layers(symbol: str):
    patterns = query("SELECT * FROM pattern_scan WHERE symbol = ? ORDER BY date DESC LIMIT 20", [symbol])
    options = query("SELECT * FROM options_intel WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])
    return {"patterns": patterns, "options": options}


@router.get("/api/patterns/rotation")
def sector_rotation(days: int = 30):
    return query("SELECT * FROM sector_rotation ORDER BY date DESC LIMIT ?", [days])


@router.get("/api/patterns/options")
def options_intel(min_score: int = 0):
    return query("""
        SELECT * FROM options_intel
        WHERE date >= date('now', '-7 days') AND score >= ?
        ORDER BY score DESC
    """, [min_score])


@router.get("/api/patterns/options/{symbol}")
def options_detail(symbol: str):
    return query("SELECT * FROM options_intel WHERE symbol = ? ORDER BY date DESC LIMIT 20", [symbol])


@router.get("/api/patterns/unusual-activity")
def unusual_activity(min_count: int = 1):
    return query("""
        SELECT * FROM options_intel
        WHERE date >= date('now', '-7 days') AND unusual_volume >= ?
        ORDER BY unusual_volume DESC
    """, [min_count])


@router.get("/api/patterns/expected-moves")
def expected_moves():
    return query("""
        SELECT * FROM options_intel
        WHERE date >= date('now', '-7 days') AND iv_rank IS NOT NULL
        ORDER BY iv_rank DESC LIMIT 50
    """)


@router.get("/api/patterns/compression")
def compression_setups():
    return query("""
        SELECT * FROM pattern_scan
        WHERE date >= date('now', '-7 days') AND (patterns_detected LIKE '%squeeze%' OR squeeze_active = 1)
        ORDER BY pattern_scan_score DESC
    """)


@router.get("/api/patterns/dealer-exposure")
def dealer_exposure():
    return query("""
        SELECT * FROM options_intel
        WHERE date >= date('now', '-7 days')
        ORDER BY put_call_ratio DESC LIMIT 50
    """)


# ═══════════════════════════════════════════════════════════════════════
# ALT ALPHA II ENDPOINTS (6 new modules)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/earnings-nlp")
def earnings_nlp(limit: int = 100):
    return query(
        """SELECT s.*, t.sentiment, t.hedging_ratio, t.confidence_ratio, t.word_count
           FROM earnings_nlp_scores s
           LEFT JOIN earnings_transcripts t ON s.symbol = t.symbol
           WHERE s.date = (SELECT MAX(date) FROM earnings_nlp_scores)
           ORDER BY s.earnings_nlp_score DESC LIMIT ?""", [limit])

@router.get("/api/earnings-nlp/{symbol}")
def earnings_nlp_detail(symbol: str):
    scores = query(
        "SELECT * FROM earnings_nlp_scores WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])
    transcripts = query(
        "SELECT * FROM earnings_transcripts WHERE symbol = ? ORDER BY date DESC LIMIT 8", [symbol])
    return {"scores": scores, "transcripts": transcripts}

@router.get("/api/gov-intel")
def gov_intel(limit: int = 100):
    return query(
        """SELECT * FROM gov_intel_scores
           WHERE date = (SELECT MAX(date) FROM gov_intel_scores)
           ORDER BY gov_intel_score DESC LIMIT ?""", [limit])

@router.get("/api/gov-intel/{symbol}")
def gov_intel_detail(symbol: str):
    scores = query(
        "SELECT * FROM gov_intel_scores WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])
    events = query(
        "SELECT * FROM gov_intel_raw WHERE symbol = ? ORDER BY date DESC LIMIT 50", [symbol])
    return {"scores": scores, "events": events}

@router.get("/api/labor-intel")
def labor_intel(limit: int = 100):
    return query(
        """SELECT * FROM labor_intel_scores
           WHERE date = (SELECT MAX(date) FROM labor_intel_scores)
           ORDER BY labor_intel_score DESC LIMIT ?""", [limit])

@router.get("/api/labor-intel/{symbol}")
def labor_intel_detail(symbol: str):
    scores = query(
        "SELECT * FROM labor_intel_scores WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])
    raw = query(
        "SELECT * FROM labor_intel_raw WHERE symbol = ? ORDER BY date DESC LIMIT 50", [symbol])
    return {"scores": scores, "raw": raw}

@router.get("/api/supply-chain")
def supply_chain(limit: int = 100):
    return query(
        """SELECT * FROM supply_chain_scores
           WHERE date = (SELECT MAX(date) FROM supply_chain_scores)
           ORDER BY supply_chain_score DESC LIMIT ?""", [limit])

@router.get("/api/supply-chain/{symbol}")
def supply_chain_detail(symbol: str):
    scores = query(
        "SELECT * FROM supply_chain_scores WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])
    raw = query(
        "SELECT * FROM supply_chain_raw ORDER BY date DESC LIMIT 50")
    return {"scores": scores, "raw": raw}

@router.get("/api/digital-exhaust")
def digital_exhaust(limit: int = 100):
    return query(
        """SELECT * FROM digital_exhaust_scores
           WHERE date = (SELECT MAX(date) FROM digital_exhaust_scores)
           ORDER BY digital_exhaust_score DESC LIMIT ?""", [limit])

@router.get("/api/digital-exhaust/{symbol}")
def digital_exhaust_detail(symbol: str):
    scores = query(
        "SELECT * FROM digital_exhaust_scores WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])
    raw = query(
        "SELECT * FROM digital_exhaust_raw WHERE symbol = ? ORDER BY date DESC LIMIT 50", [symbol])
    return {"scores": scores, "raw": raw}

@router.get("/api/pharma-intel")
def pharma_intel(limit: int = 100):
    return query(
        """SELECT * FROM pharma_intel_scores
           WHERE date = (SELECT MAX(date) FROM pharma_intel_scores)
           ORDER BY pharma_intel_score DESC LIMIT ?""", [limit])

@router.get("/api/pharma-intel/{symbol}")
def pharma_intel_detail(symbol: str):
    scores = query(
        "SELECT * FROM pharma_intel_scores WHERE symbol = ? ORDER BY date DESC LIMIT 10", [symbol])
    raw = query(
        "SELECT * FROM pharma_intel_raw WHERE symbol = ? ORDER BY date DESC LIMIT 50", [symbol])
    return {"scores": scores, "raw": raw}
