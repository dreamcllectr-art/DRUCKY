"""Ship Tracking Intelligence — maritime shipping signals for trade flow and port congestion.

Combines four signal layers to produce a 0-100 ship_tracking_score per symbol:
  1. BDI proxy / shipping stock momentum vs SPY  — weight 0.30
  2. Container freight rate direction (Serper)    — weight 0.25
  3. Port congestion signals (Serper)             — weight 0.25
  4. Tanker rate signals (Serper)                 — weight 0.20

Sector mapping routes scores to the symbols most affected:
  - Shipping stocks get direct shipping exposure scores
  - Energy stocks weight tanker rates more heavily
  - Retailers/tech weight container & congestion signals
  - Ag/mining weight dry bulk (BDI) signals
  - Default: blended score for remaining universe

Weekly gate: skips if last run was <7 days ago.

Usage:
    python -m tools.ship_tracking_intel
"""

import json
import logging
import time
from datetime import date, datetime, timedelta

import requests

from tools.db import init_db, get_conn, query, upsert_many
from tools.config import SERPER_API_KEY

logger = logging.getLogger(__name__)

# ── Stock Baskets ────────────────────────────────────────────────────

SHIPPING_BASKET = ["ZIM", "SBLK", "GOGL", "MATX", "DAC", "INSW", "STNG"]
BDI_PROXY_ETFS = ["SBLK", "BDRY"]  # dry-bulk proxies

# ── Sector Mapping ───────────────────────────────────────────────────

SECTOR_MAP = {
    "shipping":      ["ZIM", "SBLK", "GOGL", "MATX", "DAC", "INSW", "STNG"],
    "energy":        ["XOM", "CVX", "COP", "EOG", "OXY"],
    "retail_import": ["WMT", "TGT", "COST", "AMZN", "HD", "LOW"],
    "tech_hardware": ["AAPL", "DELL", "HPQ"],
    "agriculture":   ["ADM", "BG", "DE", "MOS", "CF"],
    "mining":        ["FCX", "NEM", "SCCO", "CLF", "X", "AA"],
}

# Signal weight overrides per sector (bdi, freight, congestion, tanker)
SECTOR_WEIGHTS = {
    "shipping":      {"bdi": 0.35, "freight": 0.25, "congestion": 0.20, "tanker": 0.20},
    "energy":        {"bdi": 0.15, "freight": 0.15, "congestion": 0.10, "tanker": 0.60},
    "retail_import": {"bdi": 0.10, "freight": 0.40, "congestion": 0.40, "tanker": 0.10},
    "tech_hardware": {"bdi": 0.10, "freight": 0.45, "congestion": 0.35, "tanker": 0.10},
    "agriculture":   {"bdi": 0.55, "freight": 0.15, "congestion": 0.15, "tanker": 0.15},
    "mining":        {"bdi": 0.55, "freight": 0.15, "congestion": 0.15, "tanker": 0.15},
}

DEFAULT_WEIGHTS = {"bdi": 0.30, "freight": 0.25, "congestion": 0.25, "tanker": 0.20}

# ── Keyword Dictionaries ────────────────────────────────────────────

FREIGHT_BULLISH_KW = ["surge", "spike", "increase", "rising", "record",
                      "soar", "jump", "elevated", "highest", "climbing"]
FREIGHT_BEARISH_KW = ["drop", "fall", "collapse", "decline", "plunge",
                      "tumble", "slump", "lowest", "crash", "plummet"]

CONGESTION_HIGH_KW = ["delay", "backlog", "waiting", "queue", "congestion",
                      "bottleneck", "gridlock", "stuck", "logjam", "backup"]
CONGESTION_LOW_KW = ["cleared", "improved", "normalized", "flowing", "easing",
                     "resolved", "unclogged", "smooth", "decline in wait",
                     "shorter queue"]

TANKER_BULLISH_KW = ["surge", "spike", "increase", "rising", "record",
                     "soar", "jump", "elevated", "highest", "firm"]
TANKER_BEARISH_KW = ["drop", "fall", "collapse", "decline", "plunge",
                     "tumble", "slump", "weakening", "lowest", "soft"]

# ── DB Setup ─────────────────────────────────────────────────────────

def _ensure_tables():
    """Create ship-tracking-specific tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ship_tracking_raw (
            date TEXT,
            source TEXT,
            metric TEXT,
            value REAL,
            details TEXT,
            PRIMARY KEY (date, source, metric)
        );
        CREATE TABLE IF NOT EXISTS ship_tracking_scores (
            symbol TEXT,
            date TEXT,
            ship_tracking_score REAL,
            bdi_score REAL,
            freight_score REAL,
            congestion_score REAL,
            tanker_score REAL,
            details TEXT,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.commit()
    conn.close()


# ── Weekly Gate ──────────────────────────────────────────────────────

def _should_run() -> bool:
    """Return True if last run was >= 7 days ago (or never)."""
    rows = query(
        "SELECT MAX(date) as last_date FROM ship_tracking_scores"
    )
    if not rows or rows[0]["last_date"] is None:
        return True
    last = datetime.strptime(rows[0]["last_date"], "%Y-%m-%d").date()
    return (date.today() - last).days >= 7


# ── Momentum Helpers ─────────────────────────────────────────────────

def _get_returns(symbol: str, days: int = 20):
    """Return percentage change over *days* trading days for a symbol.

    Uses the two most recent closes separated by *days* rows.
    Returns None if insufficient data.
    """
    rows = query(
        """
        SELECT close FROM price_data
        WHERE symbol = ? AND close IS NOT NULL
        ORDER BY date DESC
        LIMIT ?
        """,
        [symbol, days + 1],
    )
    if len(rows) < days + 1:
        return None
    latest = rows[0]["close"]
    prior = rows[days]["close"]
    if prior is None or prior == 0:
        return None
    return (latest - prior) / prior * 100


def _compute_basket_momentum(symbols: list, days: int = 20):
    """Average return of a basket over *days* trading days."""
    returns = []
    for sym in symbols:
        r = _get_returns(sym, days)
        if r is not None:
            returns.append(r)
    return sum(returns) / len(returns) if returns else None


def _momentum_to_score(basket_return, spy_return):
    """Convert relative momentum (basket vs SPY) to a 0-100 score.

    Outperformance bands:
      > +5 pp  → 85-100
      +2 to +5 → 65-85
      -2 to +2 → 45-65  (neutral)
      -5 to -2 → 25-45
      < -5 pp  → 0-25
    """
    if basket_return is None or spy_return is None:
        return 50.0  # neutral fallback

    spread = basket_return - spy_return  # percentage-point spread

    if spread >= 5:
        return min(100.0, 85.0 + (spread - 5) * 3)
    elif spread >= 2:
        return 65.0 + (spread - 2) / 3 * 20
    elif spread >= -2:
        return 45.0 + (spread + 2) / 4 * 20
    elif spread >= -5:
        return 25.0 + (spread + 5) / 3 * 20
    else:
        return max(0.0, 25.0 + (spread + 5) * 5)


# ── Serper Search Helper ────────────────────────────────────────────

def _serper_search(query_str: str, num: int = 10, tbs: str = "qdr:w"):
    """Run a Serper Google search and return organic results.

    Returns list of dicts with 'title' and 'snippet' keys.
    Returns empty list on failure or missing API key.
    """
    if not SERPER_API_KEY:
        logger.warning("SERPER_API_KEY not set — returning empty results")
        return []
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers=headers,
            json={"q": query_str, "num": num, "tbs": tbs},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("Serper returned %d for query: %s", resp.status_code, query_str)
            return []
        return resp.json().get("organic", [])
    except Exception as e:
        logger.warning("Serper error for '%s': %s", query_str, e)
        return []


def _score_keywords(results: list, bullish_kw: list, bearish_kw: list) -> float:
    """Score search results based on keyword prevalence.

    Returns 0-100 score:
      Strong bullish signal → 75-90
      Mild bullish → 60-75
      Neutral → 45-55
      Mild bearish → 25-40
      Strong bearish → 15-30
    """
    if not results:
        return 50.0  # neutral when no data

    bull_hits = 0
    bear_hits = 0

    for r in results:
        text = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        for kw in bullish_kw:
            if kw in text:
                bull_hits += 1
        for kw in bearish_kw:
            if kw in text:
                bear_hits += 1

    total = bull_hits + bear_hits
    if total == 0:
        return 50.0

    bull_ratio = bull_hits / total

    if bull_ratio >= 0.75:
        return min(90.0, 75.0 + bull_ratio * 20)
    elif bull_ratio >= 0.55:
        return 60.0 + (bull_ratio - 0.55) / 0.20 * 15
    elif bull_ratio >= 0.45:
        return 45.0 + (bull_ratio - 0.45) / 0.10 * 10
    elif bull_ratio >= 0.25:
        return 25.0 + (bull_ratio - 0.25) / 0.20 * 20
    else:
        return max(15.0, 30.0 - (0.25 - bull_ratio) * 60)


# ── Data Fetch Functions ─────────────────────────────────────────────

def _fetch_shipping_momentum() -> float:
    """[1/4] Compute shipping basket 20-day momentum vs SPY → 0-100 score."""
    print("  [1/4] Shipping stock momentum (BDI proxy) ...")

    spy_return = _get_returns("SPY", 20)
    basket_return = _compute_basket_momentum(SHIPPING_BASKET, 20)

    if spy_return is not None:
        print(f"    SPY 20-day return: {spy_return:+.2f}%")
    else:
        print("    SPY return: N/A (using neutral)")

    if basket_return is not None:
        print(f"    Shipping basket 20-day return: {basket_return:+.2f}%")
    else:
        print("    Shipping basket return: N/A (using neutral)")

    score = _momentum_to_score(basket_return, spy_return)
    print(f"    BDI momentum score: {score:.0f}")
    return round(score, 1)


def _fetch_freight_signals() -> tuple:
    """[2/4] Search for container freight rate direction → 0-100 score."""
    print("  [2/4] Container freight rate signals ...")

    queries = [
        "Freightos Baltic Index latest container freight rates",
        "SCFI Shanghai containerized freight index weekly",
        "global container shipping rates trend",
    ]

    all_results = []
    for q in queries:
        results = _serper_search(q, num=5)
        all_results.extend(results)
        time.sleep(0.5)

    score = _score_keywords(all_results, FREIGHT_BULLISH_KW, FREIGHT_BEARISH_KW)
    print(f"    Freight results: {len(all_results)} articles, score: {score:.0f}")
    return round(score, 1), all_results


def _fetch_congestion_signals() -> tuple:
    """[3/4] Search for port congestion at major ports → 0-100 score."""
    print("  [3/4] Port congestion signals ...")

    ports = [
        "Los Angeles Long Beach port congestion",
        "Shanghai port congestion delays",
        "Rotterdam port congestion",
        "Singapore port congestion shipping",
    ]

    all_results = []
    for q in ports:
        results = _serper_search(q, num=5)
        all_results.extend(results)
        time.sleep(0.5)

    # For congestion, high congestion = bullish for shipping, bearish for importers.
    # We store a "raw congestion level" (high = high score) and let sector mapping invert.
    congestion_level = _score_keywords(all_results, CONGESTION_HIGH_KW, CONGESTION_LOW_KW)
    print(f"    Congestion results: {len(all_results)} articles, raw level: {congestion_level:.0f}")
    return round(congestion_level, 1), all_results


def _fetch_tanker_signals() -> tuple:
    """[4/4] Search for tanker rate signals → 0-100 score."""
    print("  [4/4] Tanker rate signals ...")

    queries = [
        "VLCC tanker rates latest",
        "clean product tanker rates weekly",
        "crude oil tanker freight rates trend",
    ]

    all_results = []
    for q in queries:
        results = _serper_search(q, num=5)
        all_results.extend(results)
        time.sleep(0.5)

    score = _score_keywords(all_results, TANKER_BULLISH_KW, TANKER_BEARISH_KW)
    print(f"    Tanker results: {len(all_results)} articles, score: {score:.0f}")
    return round(score, 1), all_results


# ── Scoring ──────────────────────────────────────────────────────────

def _sector_adjusted_congestion(raw_congestion: float, sector: str) -> float:
    """Adjust congestion score based on sector.

    High congestion is BULLISH for shipping stocks (capacity constrained)
    but BEARISH for importers (supply disruption).
    """
    if sector in ("shipping",):
        # High congestion → high score (bullish for shippers)
        return raw_congestion
    elif sector in ("retail_import", "tech_hardware"):
        # High congestion → low score (bearish for importers)
        return max(0.0, min(100.0, 100.0 - raw_congestion))
    else:
        # Neutral — slight negative bias for congestion
        return max(0.0, min(100.0, 100.0 - (raw_congestion - 50.0) * 0.5))


def _build_symbol_scores(bdi_score: float, freight_score: float,
                          raw_congestion: float, tanker_score: float) -> list:
    """Map signal scores to individual symbols via sector weights."""
    today = date.today().isoformat()
    rows_out = []
    assigned = set()

    for sector, symbols in SECTOR_MAP.items():
        w = SECTOR_WEIGHTS.get(sector, DEFAULT_WEIGHTS)
        adj_congestion = _sector_adjusted_congestion(raw_congestion, sector)

        composite = round(
            bdi_score * w["bdi"]
            + freight_score * w["freight"]
            + adj_congestion * w["congestion"]
            + tanker_score * w["tanker"],
            1,
        )
        details = json.dumps({
            "sector": sector,
            "weights": w,
            "bdi_score": bdi_score,
            "freight_score": freight_score,
            "congestion_raw": raw_congestion,
            "congestion_adjusted": adj_congestion,
            "tanker_score": tanker_score,
        })
        for sym in symbols:
            rows_out.append((
                sym, today, composite,
                bdi_score, freight_score, adj_congestion, tanker_score,
                details,
            ))
            assigned.add(sym)

    # Default blend for all other universe symbols
    default_congestion = _sector_adjusted_congestion(raw_congestion, "default")
    blended = round(
        bdi_score * DEFAULT_WEIGHTS["bdi"]
        + freight_score * DEFAULT_WEIGHTS["freight"]
        + default_congestion * DEFAULT_WEIGHTS["congestion"]
        + tanker_score * DEFAULT_WEIGHTS["tanker"],
        1,
    )
    details_default = json.dumps({
        "sector": "default",
        "weights": DEFAULT_WEIGHTS,
        "bdi_score": bdi_score,
        "freight_score": freight_score,
        "congestion_raw": raw_congestion,
        "congestion_adjusted": default_congestion,
        "tanker_score": tanker_score,
    })

    universe = query("SELECT symbol FROM stock_universe")
    for row in universe:
        sym = row["symbol"]
        if sym not in assigned:
            rows_out.append((
                sym, today, blended,
                bdi_score, freight_score, default_congestion, tanker_score,
                details_default,
            ))

    return rows_out


def _store_raw(bdi_score: float, freight_score: float,
               raw_congestion: float, tanker_score: float,
               freight_results: list, congestion_results: list,
               tanker_results: list):
    """Persist raw signal metrics for audit trail."""
    today = date.today().isoformat()
    raw_rows = []

    # BDI momentum
    raw_rows.append((
        today, "bdi_proxy", "momentum_vs_spy", bdi_score,
        json.dumps({"basket": SHIPPING_BASKET, "lookback_days": 20}),
    ))

    # Freight rate direction
    freight_headlines = [r.get("title", "")[:120] for r in freight_results[:5]]
    raw_rows.append((
        today, "container_freight", "keyword_score", freight_score,
        json.dumps({"article_count": len(freight_results),
                     "top_headlines": freight_headlines}),
    ))

    # Port congestion
    congestion_headlines = [r.get("title", "")[:120] for r in congestion_results[:5]]
    raw_rows.append((
        today, "port_congestion", "congestion_level", raw_congestion,
        json.dumps({"article_count": len(congestion_results),
                     "top_headlines": congestion_headlines}),
    ))

    # Tanker rates
    tanker_headlines = [r.get("title", "")[:120] for r in tanker_results[:5]]
    raw_rows.append((
        today, "tanker_rates", "keyword_score", tanker_score,
        json.dumps({"article_count": len(tanker_results),
                     "top_headlines": tanker_headlines}),
    ))

    upsert_many(
        "ship_tracking_raw",
        ["date", "source", "metric", "value", "details"],
        raw_rows,
    )


# ── Entry Point ──────────────────────────────────────────────────────

def run():
    """Weekly ship tracking intelligence run."""
    init_db()
    _ensure_tables()

    print("\n" + "=" * 60)
    print("  SHIP TRACKING INTELLIGENCE")
    print("=" * 60)

    if not _should_run():
        print("  Skipping — last run was < 7 days ago")
        print("=" * 60)
        return

    # 1. Shipping stock momentum (BDI proxy)
    bdi_score = _fetch_shipping_momentum()

    # 2. Container freight rate signals
    freight_score, freight_results = _fetch_freight_signals()

    # 3. Port congestion signals
    raw_congestion, congestion_results = _fetch_congestion_signals()

    # 4. Tanker rate signals
    tanker_score, tanker_results = _fetch_tanker_signals()

    # Store raw metrics
    _store_raw(bdi_score, freight_score, raw_congestion, tanker_score,
               freight_results, congestion_results, tanker_results)

    # Build per-symbol scores
    symbol_rows = _build_symbol_scores(bdi_score, freight_score,
                                        raw_congestion, tanker_score)
    print(f"\n  Scored {len(symbol_rows)} symbols")

    upsert_many(
        "ship_tracking_scores",
        ["symbol", "date", "ship_tracking_score",
         "bdi_score", "freight_score", "congestion_score", "tanker_score",
         "details"],
        symbol_rows,
    )

    print(f"  Stored {len(symbol_rows)} ship tracking scores")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
