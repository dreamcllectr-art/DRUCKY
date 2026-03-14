"""Labor Market Intelligence — hiring velocity, job postings, employee sentiment.

Aggregates 3 labor-market data sources into a single labor_intel_score (0-100)
per stock symbol:

  1. H-1B LCA filing velocity  (weight 0.40)
  2. Job posting velocity       (weight 0.35)
  3. Employee sentiment         (weight 0.25)

Runs weekly (7-day gate). Symbols without labor data get a neutral 50.

Usage:
  python -m tools.labor_intel
"""

import json
import logging
import re
import time
from datetime import date, datetime

import requests

from tools.db import init_db, get_conn, query, upsert_many
from tools.config import SERPER_API_KEY

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

WEIGHTS = {"h1b": 0.40, "hiring": 0.35, "sentiment": 0.25}
NEUTRAL = 50
RATE_LIMIT_SEC = 0.5

# ── H-1B Employer → Ticker mapping ──────────────────────────────────

H1B_EMPLOYER_MAP = {
    "GOOGLE LLC": "GOOGL", "ALPHABET INC": "GOOGL",
    "APPLE INC": "AAPL", "MICROSOFT CORPORATION": "MSFT",
    "META PLATFORMS": "META", "AMAZON.COM SERVICES LLC": "AMZN",
    "NVIDIA CORPORATION": "NVDA", "TESLA INC": "TSLA",
    "SALESFORCE INC": "CRM", "ORACLE AMERICA INC": "ORCL",
    "INTEL CORPORATION": "INTC", "QUALCOMM INC": "QCOM",
    "CISCO SYSTEMS": "CSCO", "ADOBE INC": "ADBE",
    "IBM": "IBM", "PAYPAL INC": "PYPL",
    "UBER TECHNOLOGIES": "UBER", "AIRBNB INC": "ABNB",
    "SNAP INC": "SNAP", "PINTEREST INC": "PINS",
    "BROADCOM INC": "AVGO", "ADVANCED MICRO DEVICES": "AMD",
    "SERVICENOW INC": "NOW", "WORKDAY INC": "WDAY",
    "PALANTIR TECHNOLOGIES": "PLTR", "DATADOG INC": "DDOG",
    "CROWDSTRIKE": "CRWD", "SNOWFLAKE INC": "SNOW",
    "JPMORGAN CHASE": "JPM", "GOLDMAN SACHS": "GS",
    "MORGAN STANLEY": "MS", "BANK OF AMERICA": "BAC",
    "WELLS FARGO": "WFC", "CITIGROUP": "C",
    "UNITEDHEALTH GROUP": "UNH", "JOHNSON & JOHNSON": "JNJ",
    "PFIZER INC": "PFE", "ELI LILLY": "LLY",
    "MERCK & CO": "MRK", "ABBVIE INC": "ABBV",
    "DELOITTE": None, "ACCENTURE": "ACN",
    "COGNIZANT TECHNOLOGY": "CTSH", "INFOSYS": "INFY",
    "TATA CONSULTANCY": None, "WIPRO": "WIT",
    "HCL AMERICA": None, "CAPGEMINI": None,
}

# Reverse map: ticker → list of employer names (for lookups)
TICKER_TO_EMPLOYERS: dict[str, list[str]] = {}
for _emp, _tick in H1B_EMPLOYER_MAP.items():
    if _tick:
        TICKER_TO_EMPLOYERS.setdefault(_tick, []).append(_emp)

# Company display names for search queries
TICKER_TO_COMPANY: dict[str, str] = {
    "GOOGL": "Google", "AAPL": "Apple", "MSFT": "Microsoft",
    "META": "Meta", "AMZN": "Amazon", "NVDA": "Nvidia",
    "TSLA": "Tesla", "CRM": "Salesforce", "ORCL": "Oracle",
    "INTC": "Intel", "QCOM": "Qualcomm", "CSCO": "Cisco",
    "ADBE": "Adobe", "IBM": "IBM", "PYPL": "PayPal",
    "UBER": "Uber", "ABNB": "Airbnb", "SNAP": "Snap",
    "PINS": "Pinterest", "AVGO": "Broadcom", "AMD": "AMD",
    "NOW": "ServiceNow", "WDAY": "Workday", "PLTR": "Palantir",
    "DDOG": "Datadog", "CRWD": "CrowdStrike", "SNOW": "Snowflake",
    "JPM": "JPMorgan Chase", "GS": "Goldman Sachs",
    "MS": "Morgan Stanley", "BAC": "Bank of America",
    "WFC": "Wells Fargo", "C": "Citigroup",
    "UNH": "UnitedHealth Group", "JNJ": "Johnson & Johnson",
    "PFE": "Pfizer", "LLY": "Eli Lilly", "MRK": "Merck",
    "ABBV": "AbbVie", "ACN": "Accenture",
    "CTSH": "Cognizant", "INFY": "Infosys", "WIT": "Wipro",
}


# ── DB Schema ────────────────────────────────────────────────────────

def _ensure_tables():
    """Create labor_intel tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS labor_intel_raw (
            symbol TEXT,
            date TEXT,
            source TEXT,
            metric TEXT,
            value REAL,
            details TEXT,
            PRIMARY KEY (symbol, date, source, metric)
        );
        CREATE TABLE IF NOT EXISTS labor_intel_scores (
            symbol TEXT,
            date TEXT,
            labor_intel_score REAL,
            h1b_score REAL,
            hiring_score REAL,
            morale_score REAL,
            details TEXT,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.commit()
    conn.close()


# ── Weekly Gate ──────────────────────────────────────────────────────

def _should_run() -> bool:
    """Only run once per week."""
    rows = query("SELECT MAX(date) as last_run FROM labor_intel_scores")
    if not rows or not rows[0]["last_run"]:
        return True
    last = datetime.strptime(rows[0]["last_run"], "%Y-%m-%d").date()
    return (date.today() - last).days >= 7


# ── Serper search helper ─────────────────────────────────────────────

def _serper_search(q: str, num: int = 10) -> list[dict]:
    """Search via Serper API. Returns list of result dicts.

    Falls back to empty list if key is missing or request fails.
    """
    if not SERPER_API_KEY:
        logger.warning("SERPER_API_KEY not set — search skipped for: %s", q)
        return []
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": q, "num": num},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("organic", [])
    except Exception as exc:
        logger.warning("Serper search failed for '%s': %s", q, exc)
        return []


# ── Data Source 1: H-1B LCA Filing Velocity ──────────────────────────

def _fetch_h1b_scores() -> dict[str, float]:
    """Query DOL OFLC LCA data for each mapped employer.

    Returns {symbol: score} where score is 0-100 based on filing
    velocity change (recent quarter vs prior quarter).
    """
    scores: dict[str, float] = {}
    today_str = date.today().isoformat()

    DOL_BASE = "https://api.dol.gov/V1/Statistics/LCA"
    session = requests.Session()

    # Group employers by ticker to avoid duplicate work
    for ticker, employers in TICKER_TO_EMPLOYERS.items():
        total_recent = 0
        total_prior = 0

        for employer in employers:
            try:
                # Recent quarter filings
                params_recent = {
                    "$filter": f"EMPLOYER_NAME eq '{employer}'",
                    "$select": "EMPLOYER_NAME,CASE_NUMBER,CASE_STATUS,RECEIVED_DATE",
                    "$top": "100",
                    "$orderby": "RECEIVED_DATE desc",
                }
                resp = session.get(DOL_BASE, params=params_recent, timeout=15)
                time.sleep(RATE_LIMIT_SEC)

                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("d", data.get("results", []))
                    if isinstance(results, dict):
                        results = results.get("results", [])

                    # Split into recent vs prior quarter based on dates
                    now = date.today()
                    recent_count = 0
                    prior_count = 0
                    for r in results:
                        rd = r.get("RECEIVED_DATE", "")
                        try:
                            # Handle /Date(...)/ format from OData
                            if "/Date(" in str(rd):
                                ts = int(re.search(r"/Date\((\d+)\)", str(rd)).group(1))
                                filing_date = date.fromtimestamp(ts / 1000)
                            else:
                                filing_date = datetime.strptime(str(rd)[:10], "%Y-%m-%d").date()
                            days_ago = (now - filing_date).days
                            if days_ago <= 90:
                                recent_count += 1
                            elif days_ago <= 180:
                                prior_count += 1
                        except (ValueError, TypeError, AttributeError):
                            recent_count += 1  # count toward recent if unparseable

                    total_recent += recent_count
                    total_prior += prior_count
                else:
                    logger.debug("DOL API returned %d for %s", resp.status_code, employer)

            except Exception as exc:
                logger.warning("H-1B fetch failed for %s: %s", employer, exc)
                continue

        # Compute velocity score
        if total_recent == 0 and total_prior == 0:
            # No data — try Serper fallback
            score = _h1b_serper_fallback(ticker)
        else:
            if total_prior == 0:
                velocity = 1.0 if total_recent > 0 else 0.0
            else:
                velocity = (total_recent - total_prior) / total_prior

            # Map velocity to 0-100
            # velocity > 0.5 → strong growth → 80-100
            # velocity 0-0.5 → moderate growth → 60-80
            # velocity -0.2 to 0 → slight decline → 40-60
            # velocity < -0.2 → significant decline → 0-40
            if velocity > 0.5:
                score = min(100, 80 + velocity * 40)
            elif velocity > 0:
                score = 60 + velocity * 40
            elif velocity > -0.2:
                score = 40 + (velocity + 0.2) * 100
            else:
                score = max(0, 40 + velocity * 100)

            score = round(max(0, min(100, score)), 1)

        scores[ticker] = score

        # Store raw data
        upsert_many(
            "labor_intel_raw",
            ["symbol", "date", "source", "metric", "value", "details"],
            [
                (ticker, today_str, "h1b", "recent_filings", total_recent,
                 json.dumps({"employers": employers, "prior_filings": total_prior})),
            ],
        )

    print(f"    H-1B scores: {len(scores)} tickers processed")
    return scores


def _h1b_serper_fallback(ticker: str) -> float:
    """Use Serper search to estimate H-1B filing activity when DOL API fails."""
    company = TICKER_TO_COMPANY.get(ticker, ticker)
    results = _serper_search(f'"{company}" H-1B visa hiring 2024 2025', num=5)
    time.sleep(RATE_LIMIT_SEC)

    if not results:
        return NEUTRAL

    # Look for positive/negative sentiment in snippets
    positive_kw = ["hiring", "expansion", "increase", "growth", "ramp", "adding"]
    negative_kw = ["layoff", "freeze", "cutting", "reduction", "decline", "halt"]

    pos = 0
    neg = 0
    for r in results:
        snippet = (r.get("snippet", "") + " " + r.get("title", "")).lower()
        pos += sum(1 for kw in positive_kw if kw in snippet)
        neg += sum(1 for kw in negative_kw if kw in snippet)

    if pos > neg:
        return min(80, 55 + (pos - neg) * 5)
    elif neg > pos:
        return max(20, 45 - (neg - pos) * 5)
    return NEUTRAL


# ── Data Source 2: Job Posting Velocity ──────────────────────────────

def _fetch_job_posting_scores() -> dict[str, float]:
    """Estimate job posting velocity via Serper search.

    Searches LinkedIn job listings for each company and uses result
    count as a proxy for hiring activity.
    """
    scores: dict[str, float] = {}
    today_str = date.today().isoformat()

    for ticker, company in TICKER_TO_COMPANY.items():
        try:
            # Search for recent job postings
            results = _serper_search(
                f'"{company}" hiring OR careers site:linkedin.com/jobs',
                num=10,
            )
            time.sleep(RATE_LIMIT_SEC)

            if not results:
                scores[ticker] = NEUTRAL
                continue

            result_count = len(results)

            # Check snippets for expansion vs contraction signals
            expansion_kw = ["hiring", "open positions", "we're growing",
                            "join our team", "multiple openings", "urgently hiring"]
            contraction_kw = ["layoff", "restructuring", "freeze",
                              "workforce reduction", "downsizing"]

            exp_hits = 0
            con_hits = 0
            for r in results:
                text = (r.get("snippet", "") + " " + r.get("title", "")).lower()
                exp_hits += sum(1 for kw in expansion_kw if kw in text)
                con_hits += sum(1 for kw in contraction_kw if kw in text)

            # Score based on result count + sentiment
            base = 50
            if result_count >= 8:
                base = 65
            elif result_count >= 5:
                base = 55
            elif result_count <= 2:
                base = 40

            sentiment_adj = (exp_hits - con_hits) * 3
            score = round(max(0, min(100, base + sentiment_adj)), 1)

            scores[ticker] = score

            # Store raw
            upsert_many(
                "labor_intel_raw",
                ["symbol", "date", "source", "metric", "value", "details"],
                [
                    (ticker, today_str, "job_postings", "search_results",
                     result_count,
                     json.dumps({"expansion_hits": exp_hits,
                                 "contraction_hits": con_hits})),
                ],
            )

        except Exception as exc:
            logger.warning("Job posting fetch failed for %s: %s", ticker, exc)
            scores[ticker] = NEUTRAL

    print(f"    Job posting scores: {len(scores)} tickers processed")
    return scores


# ── Data Source 3: Employee Sentiment ────────────────────────────────

def _fetch_sentiment_scores() -> dict[str, float]:
    """Estimate employee sentiment via Serper search for Glassdoor ratings.

    Extracts star ratings from search snippets and maps to 0-100 score.
    """
    scores: dict[str, float] = {}
    today_str = date.today().isoformat()

    for ticker, company in TICKER_TO_COMPANY.items():
        try:
            results = _serper_search(
                f'"{company}" glassdoor rating reviews',
                num=5,
            )
            time.sleep(RATE_LIMIT_SEC)

            rating = _extract_rating(results)

            if rating is None:
                # Fallback: search Indeed reviews
                results2 = _serper_search(
                    f'"{company}" indeed company reviews rating',
                    num=5,
                )
                time.sleep(RATE_LIMIT_SEC)
                rating = _extract_rating(results2)

            if rating is not None:
                # Map rating to score
                # 4.5+ → 90, 4.0 → 75, 3.5 → 60, 3.0 → 45, 2.5 → 30, 2.0 → 15
                if rating >= 4.5:
                    score = 90
                elif rating >= 4.0:
                    score = 70 + (rating - 4.0) * 40
                elif rating >= 3.0:
                    score = 40 + (rating - 3.0) * 30
                elif rating >= 2.0:
                    score = 10 + (rating - 2.0) * 30
                else:
                    score = 10
                score = round(max(0, min(100, score)), 1)
            else:
                score = NEUTRAL

            scores[ticker] = score

            # Store raw
            upsert_many(
                "labor_intel_raw",
                ["symbol", "date", "source", "metric", "value", "details"],
                [
                    (ticker, today_str, "sentiment", "glassdoor_rating",
                     rating if rating else -1,
                     json.dumps({"source": "serper_glassdoor",
                                 "rating_found": rating is not None})),
                ],
            )

        except Exception as exc:
            logger.warning("Sentiment fetch failed for %s: %s", ticker, exc)
            scores[ticker] = NEUTRAL

    print(f"    Sentiment scores: {len(scores)} tickers processed")
    return scores


def _extract_rating(results: list[dict]) -> float | None:
    """Extract a numeric star rating (1.0-5.0) from search result snippets."""
    if not results:
        return None

    # Common patterns: "3.8 out of 5", "Rating: 4.2", "★ 3.9", "3.7/5"
    patterns = [
        r"(\d\.\d)\s*(?:out of|\/)\s*5",
        r"(?:rating|rated|stars?)[:\s]*(\d\.\d)",
        r"(\d\.\d)\s*stars?",
        r"★\s*(\d\.\d)",
        r"(\d\.\d)\s*overall",
    ]

    for r in results:
        text = (r.get("snippet", "") + " " + r.get("title", "")).lower()
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                val = float(match.group(1))
                if 1.0 <= val <= 5.0:
                    return val
    return None


# ── Composite Scoring ────────────────────────────────────────────────

def _compute_scores(
    h1b_scores: dict[str, float],
    job_scores: dict[str, float],
    sentiment_scores: dict[str, float],
) -> list[tuple]:
    """Combine sub-scores into final labor_intel_score per symbol.

    Returns rows ready for upsert into labor_intel_scores.
    """
    today_str = date.today().isoformat()
    all_tickers = set(h1b_scores) | set(job_scores) | set(sentiment_scores)

    rows = []
    for ticker in sorted(all_tickers):
        h1b = h1b_scores.get(ticker, NEUTRAL)
        hiring = job_scores.get(ticker, NEUTRAL)
        morale = sentiment_scores.get(ticker, NEUTRAL)

        labor_intel_score = round(
            h1b * WEIGHTS["h1b"]
            + hiring * WEIGHTS["hiring"]
            + morale * WEIGHTS["sentiment"],
            1,
        )

        details = json.dumps({
            "h1b_score": h1b,
            "hiring_score": hiring,
            "morale_score": morale,
            "weights": WEIGHTS,
        })

        rows.append((
            ticker, today_str, labor_intel_score,
            h1b, hiring, morale, details,
        ))

    return rows


# ── Entry Point ──────────────────────────────────────────────────────

def run():
    """Weekly labor market intelligence run."""
    init_db()
    _ensure_tables()

    print("\n" + "=" * 60)
    print("  LABOR MARKET INTELLIGENCE")
    print("=" * 60)

    if not _should_run():
        print("  Skipping — last run was less than 7 days ago")
        print("=" * 60)
        return

    # Fetch all three data sources
    print("  [1/3] H-1B LCA filing velocity ...")
    h1b_scores = _fetch_h1b_scores()

    print("  [2/3] Job posting velocity ...")
    job_scores = _fetch_job_posting_scores()

    print("  [3/3] Employee sentiment ...")
    sentiment_scores = _fetch_sentiment_scores()

    # Combine into composite scores
    print("  Computing composite scores ...")
    score_rows = _compute_scores(h1b_scores, job_scores, sentiment_scores)

    upsert_many(
        "labor_intel_scores",
        ["symbol", "date", "labor_intel_score",
         "h1b_score", "hiring_score", "morale_score", "details"],
        score_rows,
    )

    # Summary
    if score_rows:
        avg_score = sum(r[2] for r in score_rows) / len(score_rows)
        top = sorted(score_rows, key=lambda r: r[2], reverse=True)[:5]
        bottom = sorted(score_rows, key=lambda r: r[2])[:5]

        print(f"\n  Scored {len(score_rows)} symbols (avg: {avg_score:.1f})")
        print("\n  Top 5 (strongest labor signal):")
        for r in top:
            print(f"    {r[0]:<8} {r[2]:>5.1f}  (H1B={r[3]:.0f} Hiring={r[4]:.0f} Morale={r[5]:.0f})")
        print("\n  Bottom 5 (weakest labor signal):")
        for r in bottom:
            print(f"    {r[0]:<8} {r[2]:>5.1f}  (H1B={r[3]:.0f} Hiring={r[4]:.0f} Morale={r[5]:.0f})")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
