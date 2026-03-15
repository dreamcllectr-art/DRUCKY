"""AAR Rail Car Loadings Intelligence — weekly rail traffic as a macro leading indicator.

Tracks Association of American Railroads (AAR) carloading data via FRED
and rail stock momentum as a proxy for real economic activity.  Rail freight
is one of the oldest and most reliable coincident/leading indicators:
  - Carloading YoY changes map directly to economic expansion/contraction
  - 4-week momentum captures acceleration or deceleration
  - Rail stock relative strength (CSX, NSC, UNP vs SPY) confirms price discovery

Commodity-type carloadings are mapped to sector-specific symbols so the signal
is granular, not just a macro blanket.

Produces 0-100 aar_rail_score per symbol.  Weekly gate (7-day).

Usage:
    python -m tools.aar_rail_intel
"""

import json
import logging
import time
from datetime import date, datetime, timedelta

import requests

from tools.db import init_db, get_conn, query, upsert_many
from tools.config import FRED_API_KEY, SERPER_API_KEY

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES_RAIL = "RAILFR"          # Railroad Freight Carloadings
RATE_LIMIT_SEC = 0.3
NEUTRAL = 50

RAIL_STOCKS = ["CSX", "NSC", "UNP"]

# ── Commodity-Type → Sector → Symbols Mapping ───────────────────────

COMMODITY_SECTOR_MAP = {
    "coal_petroleum":       {"sector": "energy",       "symbols": ["XOM", "CVX", "COP", "EOG", "OXY"]},
    "grain_farm":           {"sector": "agriculture",  "symbols": ["ADM", "BG", "DE", "MOS", "CF"]},
    "chemicals":            {"sector": "chemicals",    "symbols": ["DOW", "LYB", "DD", "EMN", "PPG"]},
    "motor_vehicles":       {"sector": "autos",        "symbols": ["GM", "F", "CAT", "CMI"]},
    "metals_ores":          {"sector": "mining",       "symbols": ["FCX", "NEM", "SCCO", "CLF", "X", "AA"]},
    "intermodal":           {"sector": "retail",       "symbols": ["WMT", "TGT", "COST", "AMZN", "HD"]},
    "forest_products":      {"sector": "housing",      "symbols": ["LPX", "WY", "BCC"]},
}

# Flatten for quick lookup: symbol → commodity type(s)
_SYMBOL_TO_COMMODITY: dict[str, list[str]] = {}
for _ctype, _info in COMMODITY_SECTOR_MAP.items():
    for _sym in _info["symbols"]:
        _SYMBOL_TO_COMMODITY.setdefault(_sym, []).append(_ctype)

# All explicitly mapped symbols
_MAPPED_SYMBOLS: set[str] = set()
for _info in COMMODITY_SECTOR_MAP.values():
    _MAPPED_SYMBOLS.update(_info["symbols"])


# ── DB Setup ─────────────────────────────────────────────────────────

def _ensure_tables():
    """Create AAR rail-specific tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS aar_rail_raw (
            date TEXT,
            commodity_type TEXT,
            carloadings INTEGER,
            yoy_change REAL,
            details TEXT,
            PRIMARY KEY (date, commodity_type)
        );
        CREATE TABLE IF NOT EXISTS aar_rail_scores (
            symbol TEXT,
            date TEXT,
            aar_rail_score REAL,
            macro_score REAL,
            sector_score REAL,
            momentum_score REAL,
            details TEXT,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.commit()
    conn.close()


# ── Weekly Gate ──────────────────────────────────────────────────────

def _should_run() -> bool:
    """Return True if last run was >= 7 days ago (or never)."""
    rows = query("SELECT MAX(date) as last_date FROM aar_rail_scores")
    if not rows or rows[0]["last_date"] is None:
        return True
    last = datetime.strptime(rows[0]["last_date"], "%Y-%m-%d").date()
    return (date.today() - last).days >= 7


# ── FRED Rail Freight Carloadings ────────────────────────────────────

def _fetch_fred_rail() -> dict:
    """Fetch RAILFR from FRED and compute YoY change + 4-week momentum.

    Returns dict with keys:
        current, prior_year, yoy_pct, recent_4wk_avg, prior_4wk_avg,
        momentum_pct, observations (list of recent values)
    """
    result = {
        "current": None, "prior_year": None, "yoy_pct": None,
        "recent_4wk_avg": None, "prior_4wk_avg": None, "momentum_pct": None,
        "observations": [],
    }

    if not FRED_API_KEY:
        logger.warning("FRED_API_KEY not set — rail freight fetch skipped")
        return result

    try:
        # Fetch last 2 years of data for YoY comparison
        start = (date.today() - timedelta(days=800)).isoformat()
        resp = requests.get(FRED_BASE, params={
            "series_id": FRED_SERIES_RAIL,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "observation_start": start,
            "sort_order": "desc",
            "limit": 200,
        }, timeout=15)
        resp.raise_for_status()
        obs = resp.json().get("observations", [])

        # Filter valid numeric observations
        valid = []
        for o in obs:
            try:
                val = float(o["value"])
                valid.append({"date": o["date"], "value": val})
            except (ValueError, KeyError):
                continue

        if not valid:
            logger.warning("No valid RAILFR observations from FRED")
            return result

        result["observations"] = valid[:60]  # keep recent 60 for analysis

        # Current value (most recent)
        current = valid[0]["value"]
        current_date = datetime.strptime(valid[0]["date"], "%Y-%m-%d").date()
        result["current"] = current

        # Find same-week-prior-year observation (closest to 52 weeks ago)
        target_prior = current_date - timedelta(days=364)
        best_prior = None
        best_gap = 999
        for o in valid:
            d = datetime.strptime(o["date"], "%Y-%m-%d").date()
            gap = abs((d - target_prior).days)
            if gap < best_gap:
                best_gap = gap
                best_prior = o["value"]
            if gap > 30 and best_prior is not None:
                break  # past the window

        if best_prior and best_prior > 0:
            result["prior_year"] = best_prior
            result["yoy_pct"] = (current - best_prior) / best_prior * 100

        # 4-week momentum: avg of latest 4 vs avg of prior 4
        if len(valid) >= 8:
            recent_4 = [v["value"] for v in valid[:4]]
            prior_4 = [v["value"] for v in valid[4:8]]
            r4avg = sum(recent_4) / len(recent_4)
            p4avg = sum(prior_4) / len(prior_4)
            result["recent_4wk_avg"] = r4avg
            result["prior_4wk_avg"] = p4avg
            if p4avg > 0:
                result["momentum_pct"] = (r4avg - p4avg) / p4avg * 100

        print(f"    FRED RAILFR: current={current:,.0f}, "
              f"YoY={result['yoy_pct']:+.1f}%" if result["yoy_pct"] is not None
              else f"    FRED RAILFR: current={current:,.0f}, YoY=N/A")

    except Exception as e:
        logger.warning("FRED rail freight fetch failed: %s", e)

    return result


def _fetch_serper_aar_fallback() -> dict:
    """Search for latest AAR weekly rail traffic report via Serper as a
    supplementary signal.  Returns extracted YoY if found, else empty dict."""
    result = {}
    if not SERPER_API_KEY:
        return result

    try:
        resp = requests.post("https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": "AAR weekly rail traffic carloadings report latest",
                  "num": 5}, timeout=15)
        resp.raise_for_status()
        organic = resp.json().get("organic", [])
        time.sleep(RATE_LIMIT_SEC)

        # Try to extract YoY numbers from snippets
        import re
        for r in organic:
            snippet = r.get("snippet", "") + " " + r.get("title", "")
            # Look for patterns like "up 3.2%" or "down 1.5%" or "+4.1%"
            m = re.search(r'(?:up|increase[d]?|rose|gain)\s*(?:of\s*)?([\d.]+)\s*%', snippet, re.I)
            if m:
                result["serper_yoy"] = float(m.group(1))
                result["serper_direction"] = "up"
                result["serper_source"] = r.get("link", "")
                break
            m = re.search(r'(?:down|decrease[d]?|fell|decline[d]?|drop)\s*(?:of\s*)?([\d.]+)\s*%', snippet, re.I)
            if m:
                result["serper_yoy"] = -float(m.group(1))
                result["serper_direction"] = "down"
                result["serper_source"] = r.get("link", "")
                break
            m = re.search(r'([+-][\d.]+)\s*%', snippet)
            if m:
                val = float(m.group(1))
                result["serper_yoy"] = val
                result["serper_direction"] = "up" if val > 0 else "down"
                result["serper_source"] = r.get("link", "")
                break

        if result:
            print(f"    Serper AAR: {result.get('serper_direction','?')} "
                  f"{abs(result.get('serper_yoy', 0)):.1f}%")
        else:
            print("    Serper AAR: no YoY extracted from search results")

    except Exception as e:
        logger.warning("Serper AAR fallback failed: %s", e)

    return result


# ── Rail Stock Relative Strength ─────────────────────────────────────

def _get_returns(symbol: str, days: int = 20):
    """Return percentage change over *days* trading days for a symbol."""
    rows = query(
        "SELECT close FROM price_data WHERE symbol = ? AND close IS NOT NULL "
        "ORDER BY date DESC LIMIT ?",
        [symbol, days + 1],
    )
    if len(rows) < days + 1:
        return None
    latest = rows[0]["close"]
    prior = rows[days]["close"]
    if prior is None or prior == 0:
        return None
    return (latest - prior) / prior * 100


def _compute_rail_stock_strength() -> dict:
    """Compute CSX+NSC+UNP average 20-day return vs SPY.

    Returns dict with rail_avg_return, spy_return, spread_pp, bonus.
    """
    result = {"rail_avg_return": None, "spy_return": None,
              "spread_pp": 0.0, "bonus": 0}

    rets = []
    for sym in RAIL_STOCKS:
        r = _get_returns(sym, 20)
        if r is not None:
            rets.append(r)

    spy_ret = _get_returns("SPY", 20)
    result["spy_return"] = spy_ret

    if rets:
        rail_avg = sum(rets) / len(rets)
        result["rail_avg_return"] = rail_avg

        if spy_ret is not None:
            spread = rail_avg - spy_ret
            result["spread_pp"] = spread
            if spread > 2:
                result["bonus"] = 5
            elif spread < -2:
                result["bonus"] = -5

        print(f"    Rail stocks 20d: {rail_avg:+.2f}%  SPY: "
              f"{spy_ret:+.2f}%  spread: {result['spread_pp']:+.2f}pp  "
              f"bonus: {result['bonus']:+d}" if spy_ret is not None
              else f"    Rail stocks 20d: {rail_avg:+.2f}%  SPY: N/A")
    else:
        print("    Rail stock data unavailable — using neutral")

    return result


# ── Scoring Logic ────────────────────────────────────────────────────

def _yoy_to_macro_score(yoy_pct: float | None) -> float:
    """Convert carloading YoY% to a 0-100 macro score.

    YoY > +5%:        80-100 (economy expanding)
    YoY +2% to +5%:   65-80  (moderate growth)
    YoY -2% to +2%:   45-65  (neutral)
    YoY -5% to -2%:   25-45  (slowdown)
    YoY < -5%:        0-25   (recessionary)
    """
    if yoy_pct is None:
        return NEUTRAL

    if yoy_pct > 5:
        # Map 5-15% → 80-100
        return min(100.0, 80.0 + (yoy_pct - 5.0) * 2.0)
    elif yoy_pct > 2:
        # Map 2-5% → 65-80
        return 65.0 + (yoy_pct - 2.0) / 3.0 * 15.0
    elif yoy_pct > -2:
        # Map -2 to +2% → 45-65
        return 45.0 + (yoy_pct + 2.0) / 4.0 * 20.0
    elif yoy_pct > -5:
        # Map -5 to -2% → 25-45
        return 25.0 + (yoy_pct + 5.0) / 3.0 * 20.0
    else:
        # Map -15 to -5% → 0-25
        return max(0.0, 25.0 + (yoy_pct + 5.0) * 2.5)


def _momentum_bonus(momentum_pct: float | None) -> int:
    """4-week momentum bonus: accelerating +10, decelerating -10."""
    if momentum_pct is None:
        return 0
    if momentum_pct > 1.0:
        return 10
    elif momentum_pct < -1.0:
        return -10
    return 0


def _compute_sector_score(commodity_type: str, macro_score: float,
                          fred_data: dict) -> float:
    """Compute a sector-specific score adjustment.

    For now, all commodity types share the same macro score (we don't have
    per-commodity carloading breakdowns from FRED's aggregate series).
    Future enhancement: scrape AAR per-commodity breakdowns.
    """
    # Slight differentiation based on commodity sensitivity
    sensitivity = {
        "coal_petroleum": 1.10,   # more cyclical
        "grain_farm": 0.90,       # less cyclical, weather-driven
        "chemicals": 1.05,
        "motor_vehicles": 1.15,   # very cyclical
        "metals_ores": 1.10,
        "intermodal": 1.00,       # tracks consumer spending
        "forest_products": 1.05,  # housing cycle
    }
    mult = sensitivity.get(commodity_type, 1.0)

    # Adjust around neutral: amplify deviation from 50
    deviation = (macro_score - 50.0) * mult
    adjusted = 50.0 + deviation
    return round(max(0.0, min(100.0, adjusted)), 1)


def _build_all_scores(fred_data: dict, serper_data: dict,
                      rail_strength: dict) -> list[tuple]:
    """Build per-symbol aar_rail_score rows for the entire universe."""
    today_str = date.today().isoformat()

    # Determine best YoY estimate
    yoy = fred_data.get("yoy_pct")
    if yoy is None and serper_data.get("serper_yoy") is not None:
        yoy = serper_data["serper_yoy"]

    # Core macro score from carloading YoY
    macro_score = round(_yoy_to_macro_score(yoy), 1)

    # 4-week momentum bonus
    mom_bonus = _momentum_bonus(fred_data.get("momentum_pct"))

    # Rail stock relative strength bonus
    rail_bonus = rail_strength.get("bonus", 0)

    # Store raw data
    raw_rows = []
    raw_rows.append((today_str, "total_carloadings",
                     int(fred_data["current"]) if fred_data["current"] else None,
                     yoy,
                     json.dumps({
                         "source": "FRED_RAILFR",
                         "prior_year": fred_data.get("prior_year"),
                         "recent_4wk_avg": fred_data.get("recent_4wk_avg"),
                         "prior_4wk_avg": fred_data.get("prior_4wk_avg"),
                         "momentum_pct": fred_data.get("momentum_pct"),
                         "serper_yoy": serper_data.get("serper_yoy"),
                         "rail_stock_spread": rail_strength.get("spread_pp"),
                     })))
    upsert_many("aar_rail_raw",
                ["date", "commodity_type", "carloadings", "yoy_change", "details"],
                raw_rows)

    # Build per-symbol scores
    universe = query("SELECT symbol FROM stock_universe")
    rows_out = []

    for row in universe:
        sym = row["symbol"]
        commodity_types = _SYMBOL_TO_COMMODITY.get(sym)

        if commodity_types:
            # Symbol is in a mapped sector — use best commodity score
            sector_scores = []
            for ct in commodity_types:
                s = _compute_sector_score(ct, macro_score, fred_data)
                sector_scores.append(s)
            sector_score = max(sector_scores)  # use best sector match
        else:
            # Default: blended macro score
            sector_score = macro_score

        # Composite: sector_score + momentum bonus + rail strength bonus
        composite = round(max(0.0, min(100.0,
                          sector_score + mom_bonus + rail_bonus)), 1)

        momentum_score = round(max(0.0, min(100.0, 50.0 + mom_bonus * 5)), 1)

        details = json.dumps({
            "yoy_pct": yoy,
            "macro_score": macro_score,
            "sector_score": sector_score,
            "momentum_bonus": mom_bonus,
            "rail_stock_bonus": rail_bonus,
            "rail_stock_spread_pp": rail_strength.get("spread_pp"),
            "commodity_types": commodity_types or ["default"],
            "fred_current": fred_data.get("current"),
        })

        rows_out.append((sym, today_str, composite, macro_score,
                         sector_score, momentum_score, details))

    return rows_out


# ── Entry Point ──────────────────────────────────────────────────────

def run():
    """Weekly AAR Rail Carloadings Intelligence run."""
    init_db()
    _ensure_tables()

    print("\n" + "=" * 60)
    print("  AAR RAIL CARLOADINGS INTELLIGENCE")
    print("=" * 60)

    if not _should_run():
        print("  Skipping — last run < 7 days ago")
        print("=" * 60)
        return

    # [1/3] FRED rail freight carloadings
    print("  [1/3] FRED rail freight carloadings ...")
    fred_data = _fetch_fred_rail()

    # Supplementary: Serper AAR search (only if FRED data is missing YoY)
    serper_data = {}
    if fred_data.get("yoy_pct") is None and SERPER_API_KEY:
        print("    Trying Serper AAR fallback ...")
        serper_data = _fetch_serper_aar_fallback()

    # [2/3] Rail stock relative strength
    print("  [2/3] Rail stock relative strength ...")
    rail_strength = _compute_rail_stock_strength()

    # [3/3] Composite scores
    print("  [3/3] Computing composite scores ...")
    symbol_rows = _build_all_scores(fred_data, serper_data, rail_strength)

    upsert_many("aar_rail_scores",
                ["symbol", "date", "aar_rail_score", "macro_score",
                 "sector_score", "momentum_score", "details"],
                symbol_rows)

    if symbol_rows:
        avg = sum(r[2] for r in symbol_rows) / len(symbol_rows)
        top = sorted(symbol_rows, key=lambda r: r[2], reverse=True)[:5]
        bot = sorted(symbol_rows, key=lambda r: r[2])[:5]
        print(f"\n  Scored {len(symbol_rows)} symbols (avg: {avg:.1f})")
        for label, items in [("Top 5", top), ("Bottom 5", bot)]:
            print(f"\n  {label}:")
            for r in items:
                print(f"    {r[0]:<8} {r[2]:>5.1f}  "
                      f"(macro={r[3]:.0f} sector={r[4]:.0f} momentum={r[5]:.0f})")
    else:
        print("\n  Scored 0 symbols")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
