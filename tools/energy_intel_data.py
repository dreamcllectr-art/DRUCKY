"""Energy Intelligence Data Ingestion — physical supply-demand fundamentals.

Data sources (all free):
  - EIA API (enhanced): PADD district stocks, product supplied, crack spreads
  - JODI (jodidata.org): international oil stats by country (monthly)
  - UN Comtrade: merchandise trade by commodity/country (quarterly)
  - Existing macro_indicators: crude stocks, nat gas, refinery util (from fetch_eia_data.py)

Pipeline phase: 1.5 (after alternative_data, before scoring)
"""

import sys
import math
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    EIA_API_KEY,
    SERPER_API_KEY,
    GEMINI_API_KEY,
    GEMINI_BASE,
    GEMINI_MODEL,
    ENERGY_EIA_ENHANCED_SERIES,
    ENERGY_SEASONAL_LOOKBACK_YEARS,
    ENERGY_JODI_COUNTRIES,
    ENERGY_JODI_MAX_LAG_DAYS,
    ENERGY_COMTRADE_REFRESH_DAYS,
)
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

EIA_API_BASE = "https://api.eia.gov/v2"


# ─────────────────────────────────────────────────────────
# EIA Enhanced Data Fetching
# ─────────────────────────────────────────────────────────

def _fetch_eia_series(series_id: str, length: int = 260) -> list[tuple]:
    """Fetch a single EIA series. Returns [(date, value), ...] sorted desc."""
    if not EIA_API_KEY:
        return []
    url = f"{EIA_API_BASE}/seriesid/{series_id}"
    params = {
        "api_key": EIA_API_KEY,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": length,
    }
    try:
        resp = requests.get(url, params=params, timeout=15, verify=False)
        if resp.status_code != 200:
            logger.warning(f"EIA {series_id} returned {resp.status_code}")
            return []
        data = resp.json().get("response", {}).get("data", [])
        return [
            (d["period"], float(d["value"]))
            for d in data
            if d.get("value") is not None
        ]
    except Exception as e:
        logger.warning(f"EIA fetch failed for {series_id}: {e}")
        return []


def _fetch_enhanced_eia():
    """Fetch enhanced EIA series: PADD stocks, product supplied, prices."""
    print("  Fetching enhanced EIA series...")
    rows = []

    for series_id, description, category in ENERGY_EIA_ENHANCED_SERIES:
        values = _fetch_eia_series(series_id, length=260)  # 5 years weekly
        if not values:
            logger.info(f"  No data for {description}")
            continue

        logger.info(f"  {description}: {len(values)} observations")

        for i, (dt, val) in enumerate(values):
            wow = (val - values[i + 1][1]) if i + 1 < len(values) else None
            yoy = (val - values[i + 52][1]) if i + 52 < len(values) else None
            rows.append((series_id, dt, category, description, val, wow, yoy))

        time.sleep(0.3)  # Rate limit

    if rows:
        upsert_many(
            "energy_eia_enhanced",
            ["series_id", "date", "category", "description", "value", "wow_change", "yoy_change"],
            rows,
        )

    print(f"    Saved {len(rows)} enhanced EIA data points")
    return len(rows)


# ─────────────────────────────────────────────────────────
# Seasonal Norms Computation
# ─────────────────────────────────────────────────────────

def _compute_seasonal_norms():
    """Compute 5-year seasonal averages for all EIA series (original + enhanced)."""
    print("  Computing seasonal norms...")
    cutoff_years = ENERGY_SEASONAL_LOOKBACK_YEARS

    # Combine original macro_indicators EIA data + enhanced
    all_series = set()
    for series_id, _, _ in ENERGY_EIA_ENHANCED_SERIES:
        all_series.add(series_id)

    # Also include the core EIA series from fetch_eia_data.py
    core_eia = [
        "PET.WCESTUS1.W",   # US crude stocks
        "PET.WGTSTUS1.W",   # Gasoline stocks
        "PET.WDISTUS1.W",   # Distillate stocks
        "PET.WCRFPUS2.W",   # US crude production
        "PET.WPULEUS3.W",   # Refinery utilization
    ]
    for sid in core_eia:
        all_series.add(sid)

    today = date.today()
    norm_rows = []

    for series_id in all_series:
        # Try enhanced table first, fall back to macro_indicators
        values = query("""
            SELECT date, value FROM energy_eia_enhanced
            WHERE series_id = ? AND date >= ?
            ORDER BY date
        """, [series_id, (today - timedelta(days=cutoff_years * 365 + 30)).isoformat()])

        if not values:
            values = query("""
                SELECT date, value FROM macro_indicators
                WHERE indicator_id = ? AND date >= ?
                ORDER BY date
            """, [series_id, (today - timedelta(days=cutoff_years * 365 + 30)).isoformat()])

        if len(values) < 20:
            continue

        # Group by week-of-year
        by_week: dict[int, list[float]] = {}
        for row in values:
            try:
                dt = datetime.strptime(row["date"][:10], "%Y-%m-%d")
                woy = dt.isocalendar()[1]
                by_week.setdefault(woy, []).append(row["value"])
            except (ValueError, TypeError):
                continue

        for woy, vals in by_week.items():
            if len(vals) < 2:
                continue
            avg_v = sum(vals) / len(vals)
            std_v = (sum((v - avg_v) ** 2 for v in vals) / len(vals)) ** 0.5
            norm_rows.append((
                series_id, woy, avg_v, std_v,
                min(vals), max(vals), len(vals),
                today.isoformat(),
            ))

    if norm_rows:
        upsert_many(
            "energy_seasonal_norms",
            ["series_id", "week_of_year", "avg_value", "std_value",
             "min_value", "max_value", "sample_count", "last_updated"],
            norm_rows,
        )

    print(f"    Computed norms for {len(all_series)} series, {len(norm_rows)} week-buckets")


# ─────────────────────────────────────────────────────────
# JODI International Oil Statistics
# ─────────────────────────────────────────────────────────

def _jodi_is_fresh() -> bool:
    """Check if JODI data was fetched recently enough."""
    rows = query("""
        SELECT MAX(last_updated) as lu FROM energy_jodi_data
    """)
    if not rows or not rows[0]["lu"]:
        return False
    last = datetime.fromisoformat(rows[0]["lu"])
    return (datetime.now() - last).days < 30  # JODI is monthly, refresh monthly


def _fetch_jodi_data():
    """Fetch JODI oil data via Serper web search + Gemini extraction.

    JODI doesn't have a clean REST API, so we search for the latest
    data release and use Gemini to extract structured numbers.
    """
    if _jodi_is_fresh():
        print("  JODI data is fresh, skipping...")
        return

    if not SERPER_API_KEY or not GEMINI_API_KEY:
        print("  WARNING: SERPER_API_KEY or GEMINI_API_KEY not set, skipping JODI")
        return

    print("  Fetching JODI international oil data...")

    # Search for latest JODI data
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            json={
                "q": "JODI oil world database latest monthly production demand stocks 2024 2025 2026",
                "num": 5,
            },
            headers={"X-API-KEY": SERPER_API_KEY},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"    Serper search failed: {resp.status_code}")
            return
        results = resp.json().get("organic", [])
    except Exception as e:
        print(f"    Serper search error: {e}")
        return

    # Collect snippets for context
    snippets = []
    for r in results[:5]:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        snippets.append(f"Title: {title}\nSnippet: {snippet}")

    context = "\n---\n".join(snippets)

    # Use Gemini to extract structured data
    prompt = f"""From the following search results about JODI (Joint Organisations Data Initiative) oil statistics,
extract the latest available monthly data for these countries: {', '.join(ENERGY_JODI_COUNTRIES)}

For each country, extract (if available):
- production (thousand barrels per day)
- demand/consumption (thousand barrels per day)
- closing stocks (million barrels)
- imports (thousand barrels per day)
- exports (thousand barrels per day)

Return ONLY valid JSON array, no markdown. Format:
[{{"country": "...", "indicator": "production|demand|stocks|imports|exports", "date": "YYYY-MM", "value": 12345.6, "unit": "kbd|mb"}}]

If data is not clearly available for a country/indicator, omit it. Be conservative — only include numbers you're confident about.

Search results:
{context}"""

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"    Gemini JODI extraction failed: {resp.status_code}")
            return

        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        import json
        records = json.loads(text)
    except Exception as e:
        print(f"    Gemini JODI extraction error: {e}")
        return

    # Compute changes and store
    today_str = date.today().isoformat()
    rows = []
    for rec in records:
        country = rec.get("country", "")
        indicator = rec.get("indicator", "")
        dt = rec.get("date", "")
        value = rec.get("value")
        unit = rec.get("unit", "")

        if not all([country, indicator, dt, value]):
            continue

        # Look up prior month for MoM change
        prior_rows = query("""
            SELECT value FROM energy_jodi_data
            WHERE country = ? AND indicator = ? AND date < ?
            ORDER BY date DESC LIMIT 1
        """, [country, indicator, dt])

        mom = (value - prior_rows[0]["value"]) if prior_rows else None

        # YoY
        yoy_date = dt[:4]
        yoy_target = str(int(yoy_date) - 1) + dt[4:]
        yoy_rows = query("""
            SELECT value FROM energy_jodi_data
            WHERE country = ? AND indicator = ? AND date = ?
        """, [country, indicator, yoy_target])
        yoy = (value - yoy_rows[0]["value"]) if yoy_rows else None

        rows.append((country, indicator, dt, value, unit, mom, yoy, today_str))

    if rows:
        upsert_many(
            "energy_jodi_data",
            ["country", "indicator", "date", "value", "unit",
             "mom_change", "yoy_change", "last_updated"],
            rows,
        )

    print(f"    Extracted {len(rows)} JODI data points from web search")


# ─────────────────────────────────────────────────────────
# UN Comtrade Trade Flows
# ─────────────────────────────────────────────────────────

def _comtrade_is_fresh() -> bool:
    """Check if Comtrade data was fetched recently enough."""
    rows = query("SELECT MAX(last_updated) as lu FROM energy_trade_flows")
    if not rows or not rows[0]["lu"]:
        return False
    last = datetime.fromisoformat(rows[0]["lu"])
    return (datetime.now() - last).days < ENERGY_COMTRADE_REFRESH_DAYS


def _fetch_comtrade_data():
    """Fetch UN Comtrade crude oil trade data (HS 2709, 2710, 2711)."""
    if _comtrade_is_fresh():
        print("  Comtrade data is fresh, skipping...")
        return

    print("  Fetching UN Comtrade trade flows...")

    # HS codes: 2709 = crude petroleum, 2710 = refined, 2711 = LNG/LPG
    commodity_codes = ["2709", "2710", "2711"]
    # Key reporters (top oil importers/exporters)
    reporters = ["USA", "CHN", "IND", "JPN", "KOR", "DEU"]
    today_str = date.today().isoformat()
    rows = []

    for reporter in reporters:
        for hs_code in commodity_codes:
            try:
                resp = requests.get(
                    "https://comtradeapi.un.org/data/v1/get/C/M",
                    params={
                        "reporterCode": reporter,
                        "cmdCode": hs_code,
                        "flowCode": "M,X",  # imports and exports
                        "period": "recent",
                        "maxRecords": 100,
                    },
                    timeout=20,
                )
                if resp.status_code != 200:
                    continue

                data = resp.json().get("data", [])
                for rec in data:
                    rows.append((
                        rec.get("reporterDesc", reporter),
                        rec.get("partnerDesc", "World"),
                        hs_code,
                        str(rec.get("period", "")),
                        rec.get("flowDesc", ""),
                        rec.get("primaryValue"),
                        rec.get("netWgt"),
                        today_str,
                    ))

                time.sleep(1.0)  # Comtrade rate limit
            except Exception as e:
                logger.warning(f"Comtrade fetch failed for {reporter}/{hs_code}: {e}")
                continue

    if rows:
        upsert_many(
            "energy_trade_flows",
            ["reporter", "partner", "commodity_code", "period",
             "trade_flow", "value_usd", "quantity_kg", "last_updated"],
            rows,
        )

    print(f"    Fetched {len(rows)} Comtrade records")


# ─────────────────────────────────────────────────────────
# Supply Anomaly Detection
# ─────────────────────────────────────────────────────────

def _detect_supply_anomalies():
    """Detect unusual draws/builds/flow shifts using z-scores vs seasonal norms."""
    print("  Detecting supply anomalies...")
    today = date.today()
    current_week = today.isocalendar()[1]
    alerts = []

    # Check each key inventory series against seasonal norm
    inventory_series = [
        ("PET.WCESTUS1.W",  "US Crude Stocks",     "macro_indicators"),
        ("PET.WGTSTUS1.W",  "US Gasoline Stocks",   "macro_indicators"),
        ("PET.WDISTUS1.W",  "US Distillate Stocks", "macro_indicators"),
        ("PET.WCESTP21.W",  "Cushing Crude Stocks", "energy_eia_enhanced"),
    ]

    for series_id, desc, table in inventory_series:
        # Get latest value
        col = "value"
        id_col = "indicator_id" if table == "macro_indicators" else "series_id"
        latest = query(f"""
            SELECT date, {col} as value FROM {table}
            WHERE {id_col} = ?
            ORDER BY date DESC LIMIT 2
        """, [series_id])

        if len(latest) < 2:
            continue

        current_val = latest[0]["value"]
        wow_change = current_val - latest[1]["value"]

        # Get seasonal norm for current week
        norms = query("""
            SELECT avg_value, std_value FROM energy_seasonal_norms
            WHERE series_id = ? AND week_of_year = ?
        """, [series_id, current_week])

        if not norms or not norms[0]["std_value"] or norms[0]["std_value"] == 0:
            continue

        avg = norms[0]["avg_value"]
        std = norms[0]["std_value"]
        zscore = (current_val - avg) / std

        # Also z-score the WoW change
        wow_norms = query("""
            SELECT avg_value, std_value FROM energy_seasonal_norms
            WHERE series_id = ? AND week_of_year = ?
        """, [f"{series_id}_WOW_CHANGE", current_week])

        # Alert if current level is > 2 std from seasonal
        severity = None
        if abs(zscore) >= 3.0:
            severity = "critical"
        elif abs(zscore) >= 2.0:
            severity = "high"
        elif abs(zscore) >= 1.5:
            severity = "medium"

        if severity:
            direction = "above" if zscore > 0 else "below"
            anomaly_type = "inventory_surplus" if zscore > 0 else "inventory_deficit"

            # Map affected tickers based on series
            if "Crude" in desc:
                affected = "OXY,COP,XOM,CVX,DVN,FANG,EOG,PXD"
            elif "Gasoline" in desc:
                affected = "MPC,VLO,PSX"
            elif "Distillate" in desc:
                affected = "MPC,VLO,PSX"
            else:
                affected = "OXY,COP,XOM,CVX"

            alerts.append((
                today.isoformat(),
                anomaly_type,
                series_id,
                f"{desc} is {abs(zscore):.1f} std {direction} seasonal norm "
                f"(current: {current_val:,.1f}, seasonal avg: {avg:,.1f}, "
                f"WoW change: {wow_change:+,.1f})",
                zscore,
                severity,
                affected,
            ))

    if alerts:
        with get_conn() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO energy_supply_anomalies
                (date, anomaly_type, series_id, description, zscore, severity, affected_tickers)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, alerts)

    print(f"    Detected {len(alerts)} supply anomalies")


# ─────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────

def run():
    """Main entry point — called by daily_pipeline.py Phase 1.5."""
    init_db()

    if not EIA_API_KEY:
        print("  ERROR: EIA_API_KEY not set in .env")
        return

    print("\n  === ENERGY INTELLIGENCE DATA INGESTION ===")

    # 1. Enhanced EIA (PADD stocks, product supplied, prices)
    eia_count = _fetch_enhanced_eia()

    # 2. Seasonal norms (requires EIA data in DB)
    _compute_seasonal_norms()

    # 3. JODI international data (monthly, skip if fresh)
    _fetch_jodi_data()

    # 4. UN Comtrade (quarterly, skip if fresh)
    _fetch_comtrade_data()

    # 5. Anomaly detection (requires norms + current data)
    _detect_supply_anomalies()

    print("  === ENERGY DATA INGESTION COMPLETE ===\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
