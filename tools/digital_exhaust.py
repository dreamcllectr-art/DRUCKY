"""Digital Exhaust — app rankings, GitHub velocity, pricing & domain signals.

Tracks digital footprint signals for tech-oriented equities:
  1. App Store rankings  (weight 0.30) — Apple Top Charts RSS (free, no key)
  2. GitHub commit velocity (weight 0.25) — GitHub REST API
  3. Pricing page changes  (weight 0.25) — web-search proxy via Serper
  4. Domain registration   (weight 0.20) — RDAP / web-search proxy

Produces 0-100 digital_exhaust_score per symbol.
Weekly gate: skips if last run was <7 days ago.

Usage:
    python -m tools.digital_exhaust
"""

import hashlib
import json
import logging
import os
import time
from datetime import date, datetime, timedelta

import requests

from tools.db import init_db, get_conn, query, upsert_many
from tools.config import SERPER_API_KEY

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# ── App Developer → Ticker ──────────────────────────────────────────

APP_DEVELOPER_MAP = {
    "Meta Platforms, Inc.": "META",
    "Google LLC": "GOOGL",
    "Apple": "AAPL",
    "Amazon.com, Inc.": "AMZN",
    "Microsoft Corporation": "MSFT",
    "Snap, Inc.": "SNAP",
    "Pinterest, Inc.": "PINS",
    "Uber Technologies, Inc.": "UBER",
    "Block, Inc.": "SQ",
    "PayPal, Inc.": "PYPL",
    "Spotify AB": "SPOT",
    "Netflix, Inc.": "NFLX",
    "The Walt Disney Company": "DIS",
    "Paramount Global": "PARA",
    "Warner Bros. Discovery": "WBD",
    "Roblox Corporation": "RBLX",
    "DoorDash, Inc.": "DASH",
    "Airbnb, Inc.": "ABNB",
    "Booking.com": "BKNG",
    "Match Group, LLC": "MTCH",
    "Duolingo": "DUOL",
    "Peloton Interactive": "PTON",
    "Coinbase, Inc.": "COIN",
    "Robinhood Markets": "HOOD",
    "Instacart": "CART",
}

# Reverse for quick ticker lookup
_DEVELOPER_BY_TICKER: dict[str, str] = {v: k for k, v in APP_DEVELOPER_MAP.items()}

# ── GitHub Org → Ticker ─────────────────────────────────────────────

GITHUB_ORG_MAP = {
    "META": "facebook",
    "GOOGL": "google",
    "MSFT": "microsoft",
    "AMZN": "aws",
    "AAPL": "apple",
    "NVDA": "NVIDIA",
    "CRM": "salesforce",
    "ORCL": "oracle",
    "IBM": "IBM",
    "UBER": "uber",
    "ABNB": "airbnb",
    "SNAP": "Snapchat",
    "SQ": "square",
    "SHOP": "Shopify",
    "TWLO": "twilio",
    "NET": "cloudflare",
    "DDOG": "DataDog",
    "CRWD": "CrowdStrike",
    "PLTR": "palantir",
    "SNOW": "snowflakedb",
    "NOW": "ServiceNow",
    "WDAY": "Workday",
    "ZS": "zscaler",
    "PANW": "PaloAltoNetworks",
    "COIN": "coinbase",
}

# All tickers covered by at least one digital-exhaust source
ALL_COVERED_TICKERS = sorted(
    set(APP_DEVELOPER_MAP.values()) | set(GITHUB_ORG_MAP.keys())
)


# ── DB Setup ─────────────────────────────────────────────────────────

def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS digital_exhaust_raw (
            symbol TEXT,
            date TEXT,
            source TEXT,
            metric TEXT,
            value REAL,
            prior_value REAL,
            details TEXT,
            PRIMARY KEY (symbol, date, source, metric)
        );
        CREATE TABLE IF NOT EXISTS digital_exhaust_scores (
            symbol TEXT,
            date TEXT,
            digital_exhaust_score REAL,
            app_score REAL,
            github_score REAL,
            pricing_score REAL,
            domain_score REAL,
            details TEXT,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.commit()
    conn.close()


# ── Weekly Gate ──────────────────────────────────────────────────────

def _should_run() -> bool:
    rows = query("SELECT MAX(date) as last_date FROM digital_exhaust_scores")
    if not rows or rows[0]["last_date"] is None:
        return True
    last = datetime.strptime(rows[0]["last_date"], "%Y-%m-%d").date()
    return (date.today() - last).days >= 7


# ── 1. App Store Rankings ───────────────────────────────────────────

def _fetch_app_rankings() -> dict[str, float]:
    """Fetch Apple top-free and top-grossing charts, return ticker→score."""
    print("  [1/4] App Store rankings …")
    scores: dict[str, float] = {}
    charts = [
        ("top-free", "https://rss.applemarketingtools.com/api/v2/us/apps/top-free/200/apps.json"),
        ("top-grossing", "https://rss.applemarketingtools.com/api/v2/us/apps/top-grossing/200/apps.json"),
    ]

    ticker_best_rank: dict[str, int] = {}  # best (lowest) rank across charts

    for chart_name, url in charts:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("feed", {}).get("results", [])
        except Exception as e:
            print(f"    Warning: failed to fetch {chart_name}: {e}")
            continue

        time.sleep(0.5)

        for rank_idx, app in enumerate(results, start=1):
            artist = app.get("artistName", "")
            ticker = APP_DEVELOPER_MAP.get(artist)
            if ticker is None:
                continue
            # Keep best rank across charts
            if ticker not in ticker_best_rank or rank_idx < ticker_best_rank[ticker]:
                ticker_best_rank[ticker] = rank_idx

    # Convert ranks to scores
    for ticker, rank in ticker_best_rank.items():
        if rank <= 10:
            scores[ticker] = 95.0
        elif rank <= 25:
            scores[ticker] = 85.0
        elif rank <= 50:
            scores[ticker] = 75.0
        elif rank <= 100:
            scores[ticker] = 65.0
        elif rank <= 200:
            scores[ticker] = 55.0
        else:
            scores[ticker] = 45.0

    found = len(scores)
    print(f"    Found {found} tickers in charts")
    return scores


# ── 2. GitHub Commit Velocity ───────────────────────────────────────

def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    return headers


def _fetch_github_velocity() -> dict[str, float]:
    """Query GitHub commit activity for mapped orgs, return ticker→score."""
    print("  [2/4] GitHub commit velocity …")
    scores: dict[str, float] = {}
    headers = _github_headers()

    for ticker, org in GITHUB_ORG_MAP.items():
        try:
            # Get most-recently-pushed repos
            repos_url = (
                f"https://api.github.com/orgs/{org}/repos"
                f"?sort=pushed&per_page=5"
            )
            resp = requests.get(repos_url, headers=headers, timeout=15)
            if resp.status_code == 403:
                print("    GitHub rate-limited — stopping GitHub scan")
                break
            if resp.status_code != 200:
                continue
            repos = resp.json()
            if not repos:
                continue

            time.sleep(0.5)

            # Sample commit activity from the top repo
            top_repo = repos[0].get("name", "")
            activity_url = (
                f"https://api.github.com/repos/{org}/{top_repo}"
                f"/stats/commit_activity"
            )
            resp2 = requests.get(activity_url, headers=headers, timeout=15)
            if resp2.status_code != 200:
                scores[ticker] = 50.0
                continue

            weeks = resp2.json()
            if not isinstance(weeks, list) or len(weeks) < 4:
                scores[ticker] = 50.0
                time.sleep(0.5)
                continue

            # Compare last 4 weeks vs prior 4 weeks
            recent_4 = sum(w.get("total", 0) for w in weeks[-4:])
            prior_4 = sum(w.get("total", 0) for w in weeks[-8:-4])

            if prior_4 == 0:
                velocity = 1.0 if recent_4 > 0 else 0.0
            else:
                velocity = recent_4 / prior_4

            # Map velocity ratio to score
            if velocity >= 1.3:
                score = min(85.0, 65.0 + (velocity - 1.3) * 40)
            elif velocity >= 1.0:
                score = 55.0 + (velocity - 1.0) / 0.3 * 10
            elif velocity >= 0.7:
                score = 35.0 + (velocity - 0.7) / 0.3 * 20
            else:
                score = max(15.0, 35.0 - (0.7 - velocity) * 40)

            scores[ticker] = round(score, 1)
            time.sleep(0.5)

        except Exception as e:
            logger.debug("GitHub error for %s/%s: %s", ticker, org, e)
            scores[ticker] = 50.0

    print(f"    Scored {len(scores)} orgs")
    return scores


# ── 3. Pricing Page Changes (web-search proxy) ─────────────────────

# SaaS companies whose pricing signals matter
SAAS_PRICING_TICKERS = [
    "CRM", "NOW", "SNOW", "DDOG", "NET", "CRWD", "ZS", "PANW",
    "WDAY", "SHOP", "TWLO", "MSFT", "GOOGL", "AMZN",
]


def _fetch_pricing_signals() -> dict[str, float]:
    """Use Serper web search to detect recent pricing changes for SaaS cos."""
    print("  [3/4] Pricing page signals …")
    scores: dict[str, float] = {}

    if not SERPER_API_KEY:
        print("    No SERPER_API_KEY — using neutral scores")
        return {t: 50.0 for t in SAAS_PRICING_TICKERS}

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }

    for ticker in SAAS_PRICING_TICKERS:
        try:
            # Look for recent pricing news
            payload = {
                "q": f"{ticker} stock pricing increase OR price hike OR raises prices",
                "num": 5,
                "tbs": "qdr:m",  # last month
            }
            resp = requests.post(
                "https://google.serper.dev/search",
                headers=headers,
                json=payload,
                timeout=10,
            )
            if resp.status_code != 200:
                scores[ticker] = 50.0
                continue

            data = resp.json()
            organic = data.get("organic", [])

            # Simple heuristic: count results mentioning price increase
            increase_hits = 0
            decrease_hits = 0
            for result in organic:
                snippet = (result.get("snippet", "") + result.get("title", "")).lower()
                if any(kw in snippet for kw in ["price increase", "raises price",
                                                  "price hike", "higher pricing"]):
                    increase_hits += 1
                if any(kw in snippet for kw in ["price cut", "lowers price",
                                                  "price decrease", "cheaper"]):
                    decrease_hits += 1

            if increase_hits >= 2:
                scores[ticker] = 80.0
            elif increase_hits == 1:
                scores[ticker] = 65.0
            elif decrease_hits >= 2:
                scores[ticker] = 25.0
            elif decrease_hits == 1:
                scores[ticker] = 40.0
            else:
                scores[ticker] = 50.0

            time.sleep(0.5)

        except Exception as e:
            logger.debug("Pricing search error for %s: %s", ticker, e)
            scores[ticker] = 50.0

    print(f"    Scored {len(scores)} SaaS tickers")
    return scores


# ── 4. Domain / Expansion Signals (RDAP + search proxy) ────────────

COMPANY_DOMAINS = {
    "META": "meta.com",
    "GOOGL": "google.com",
    "MSFT": "microsoft.com",
    "AMZN": "amazon.com",
    "AAPL": "apple.com",
    "NFLX": "netflix.com",
    "UBER": "uber.com",
    "ABNB": "airbnb.com",
    "CRM": "salesforce.com",
    "SHOP": "shopify.com",
    "SNAP": "snapchat.com",
    "SQ": "squareup.com",
    "COIN": "coinbase.com",
    "SPOT": "spotify.com",
    "DASH": "doordash.com",
}


def _fetch_domain_signals() -> dict[str, float]:
    """Check RDAP for domain freshness / expansion signals."""
    print("  [4/4] Domain / expansion signals …")
    scores: dict[str, float] = {}

    for ticker, domain in COMPANY_DOMAINS.items():
        try:
            rdap_url = f"https://rdap.verisign.com/com/v1/domain/{domain}"
            resp = requests.get(rdap_url, timeout=10)
            if resp.status_code != 200:
                scores[ticker] = 50.0
                continue

            data = resp.json()
            # Look for recent events (domain update = activity signal)
            events = data.get("events", [])
            last_changed = None
            for ev in events:
                if ev.get("eventAction") == "last changed":
                    last_changed = ev.get("eventDate", "")
                    break

            if last_changed:
                try:
                    changed_date = datetime.fromisoformat(
                        last_changed.replace("Z", "+00:00")
                    ).date()
                    days_ago = (date.today() - changed_date).days
                    if days_ago <= 30:
                        scores[ticker] = 75.0
                    elif days_ago <= 90:
                        scores[ticker] = 60.0
                    else:
                        scores[ticker] = 50.0
                except (ValueError, TypeError):
                    scores[ticker] = 50.0
            else:
                scores[ticker] = 50.0

            time.sleep(0.5)

        except Exception as e:
            logger.debug("RDAP error for %s: %s", ticker, e)
            scores[ticker] = 50.0

    print(f"    Scored {len(scores)} domains")
    return scores


# ── Scoring Aggregation ─────────────────────────────────────────────

def _aggregate_scores(
    app_scores: dict[str, float],
    github_scores: dict[str, float],
    pricing_scores: dict[str, float],
    domain_scores: dict[str, float],
) -> list[tuple]:
    """Blend sub-scores into per-symbol digital_exhaust_score."""
    today = date.today().isoformat()
    rows: list[tuple] = []

    # Collect all tickers with at least one data point
    all_tickers = (
        set(app_scores) | set(github_scores)
        | set(pricing_scores) | set(domain_scores)
    )

    for ticker in sorted(all_tickers):
        app = app_scores.get(ticker, 50.0)
        gh = github_scores.get(ticker, 50.0)
        price = pricing_scores.get(ticker, 50.0)
        dom = domain_scores.get(ticker, 50.0)

        composite = round(
            app * 0.30 + gh * 0.25 + price * 0.25 + dom * 0.20,
            1,
        )

        details = json.dumps({
            "app_score": app,
            "github_score": gh,
            "pricing_score": price,
            "domain_score": dom,
        })

        rows.append((
            ticker, today, composite,
            app, gh, price, dom, details,
        ))

    # Also give neutral (50) to every universe symbol not already covered
    universe = query("SELECT symbol FROM stock_universe")
    covered = {r[0] for r in rows}
    for row in universe:
        sym = row["symbol"]
        if sym not in covered:
            rows.append((
                sym, today, 50.0,
                50.0, 50.0, 50.0, 50.0,
                json.dumps({"note": "no digital exhaust data — neutral"}),
            ))

    return rows


def _store_raw(
    app_scores: dict[str, float],
    github_scores: dict[str, float],
    pricing_scores: dict[str, float],
    domain_scores: dict[str, float],
):
    """Persist raw sub-scores for audit trail."""
    today = date.today().isoformat()
    raw_rows = []
    for source_label, source_dict in [
        ("app_store", app_scores),
        ("github", github_scores),
        ("pricing", pricing_scores),
        ("domain", domain_scores),
    ]:
        for ticker, value in source_dict.items():
            # Fetch prior value for comparison
            prior_rows = query(
                """SELECT value FROM digital_exhaust_raw
                   WHERE symbol = ? AND source = ? AND metric = 'score'
                   ORDER BY date DESC LIMIT 1""",
                [ticker, source_label],
            )
            prior = prior_rows[0]["value"] if prior_rows else None
            raw_rows.append((
                ticker, today, source_label, "score",
                value, prior, None,
            ))

    upsert_many(
        "digital_exhaust_raw",
        ["symbol", "date", "source", "metric", "value", "prior_value", "details"],
        raw_rows,
    )


# ── Entry Point ──────────────────────────────────────────────────────

def run():
    """Weekly digital exhaust intelligence run."""
    init_db()
    _ensure_tables()

    print("\n" + "=" * 60)
    print("  DIGITAL EXHAUST INTELLIGENCE")
    print("=" * 60)

    if not _should_run():
        print("  Skipping — last run was < 7 days ago")
        print("=" * 60)
        return

    # 1. Gather all four sub-signals
    app_scores = _fetch_app_rankings()
    github_scores = _fetch_github_velocity()
    pricing_scores = _fetch_pricing_signals()
    domain_scores = _fetch_domain_signals()

    # 2. Store raw sub-scores
    _store_raw(app_scores, github_scores, pricing_scores, domain_scores)

    # 3. Aggregate and store final scores
    score_rows = _aggregate_scores(
        app_scores, github_scores, pricing_scores, domain_scores,
    )
    print(f"\n  Scoring {len(score_rows)} symbols …")

    upsert_many(
        "digital_exhaust_scores",
        ["symbol", "date", "digital_exhaust_score",
         "app_score", "github_score", "pricing_score", "domain_score",
         "details"],
        score_rows,
    )

    print(f"  Stored {len(score_rows)} digital exhaust scores")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
