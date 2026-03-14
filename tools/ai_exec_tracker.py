"""AI Executive Investment Tracker.

Tracks personal investments, board appointments, and funding activity of
AI company executives and key AI-focused VCs. Discovers activity via
Serper web search + Firecrawl scraping + Gemini LLM classification, plus
SEC EDGAR Form D filings for private placements.

NOT a standalone convergence module — boosts smart_money_scores conviction
when AI exec investment aligns with universe stocks, and feeds sector tilt
to sector experts.

Usage: python -m tools.ai_exec_tracker
"""

import sys
import json
import re
import time
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    SERPER_API_KEY, FIRECRAWL_API_KEY, GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    EDGAR_BASE, EDGAR_HEADERS,
    AI_EXEC_WATCHLIST, AI_EXEC_SERPER_QUERIES_PER_EXEC,
    AI_EXEC_MAX_URLS_PER_EXEC, AI_EXEC_FIRECRAWL_DELAY, AI_EXEC_GEMINI_DELAY,
    AI_EXEC_MIN_CONFIDENCE, AI_EXEC_MIN_SCORE_STORE,
    AI_EXEC_SM_BOOST_HIGH, AI_EXEC_SM_BOOST_MED,
    AI_EXEC_CONVERGENCE_BONUS, AI_EXEC_LOOKBACK_DAYS,
    AI_EXEC_SCAN_INTERVAL_DAYS,
)
from tools.db import init_db, upsert_many, query, get_conn

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"
FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
MAX_ARTICLE_CHARS = 6_000

# Activity type weights for scoring
ACTIVITY_WEIGHTS = {
    "personal_purchase": 25,
    "board_appointment": 22,
    "angel_investment": 20,
    "vc_investment": 18,
    "advisory_role": 12,
    "equity_grant": 10,
    "fund_raise": 8,
}


# ── URL Cache ─────────────────────────────────────────────────────────

def _is_url_cached(url: str) -> bool:
    rows = query("SELECT status FROM ai_exec_url_cache WHERE url = ?", [url])
    return bool(rows and rows[0]["status"] == "ok")


def _cache_url(url: str, status: str):
    upsert_many(
        "ai_exec_url_cache",
        ["url", "scraped_at", "status"],
        [(url, date.today().isoformat(), status)],
    )


# ── Serper Search ─────────────────────────────────────────────────────

def _serper_search(query_str: str, num_results: int = 5) -> list[dict]:
    """Search via Serper API, return list of {title, link, snippet, date}."""
    if not SERPER_API_KEY:
        print("  Warning: SERPER_API_KEY not configured")
        return []
    try:
        resp = requests.post(
            SERPER_URL,
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query_str, "num": num_results},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("organic", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "date": item.get("date", ""),
            })
        return results
    except Exception as e:
        print(f"  Warning: Serper search failed: {e}")
        return []


# ── Firecrawl Scraping ────────────────────────────────────────────────

def _firecrawl_scrape(url: str) -> str | None:
    """Scrape URL via Firecrawl API, return clean markdown text."""
    if not FIRECRAWL_API_KEY:
        return None
    try:
        resp = requests.post(
            FIRECRAWL_URL,
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"url": url, "formats": ["markdown"]},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("success"):
            content = data.get("data", {}).get("markdown", "") or ""
            lines = [l for l in content.split("\n") if len(l.split()) >= 3 or l.startswith("#")]
            clean = "\n".join(lines)
            return clean[:MAX_ARTICLE_CHARS]
        return None
    except Exception as e:
        logger.debug(f"Firecrawl scrape failed for {url}: {e}")
        return None


# ── Gemini Classification ─────────────────────────────────────────────

def _classify_with_gemini(
    text: str, title: str, exec_name: str, exec_role: str, exec_org: str,
) -> list[dict]:
    """Use Gemini to extract personal investment/board activities from article."""
    if not GEMINI_API_KEY:
        return []

    prompt = f"""You are a financial intelligence analyst tracking AI executive personal investments.

Executive: {exec_name} ({exec_role} at {exec_org})

Article title: {title}

Article text:
{text[:4000]}

Extract PERSONAL investment or board activity as JSON:
{{
  "activities": [
    {{
      "activity_type": "angel_investment" | "vc_investment" | "board_appointment" | "advisory_role" | "equity_grant" | "personal_purchase" | "fund_raise",
      "target_company": "company name",
      "target_ticker": "ticker if public, null if private",
      "target_sector": "Technology" | "Healthcare" | "Energy" | "Financials" | "Semiconductors" | "AI/Software" | "Industrials" | "Other",
      "investment_amount": dollar amount as number or null,
      "funding_round": "seed" | "series_a" | "series_b" | "series_c" | "series_d" | "growth" | "ipo" | "secondary" | null,
      "is_public": true or false,
      "ipo_expected": true or false,
      "ipo_timeline": "description or null",
      "date_reported": "YYYY-MM-DD or null",
      "confidence": 1-10,
      "summary": "one-sentence description"
    }}
  ],
  "mentioned_public_tickers": ["TICKER1", "TICKER2"],
  "sector_signal": "bullish_compute" | "bullish_software" | "bullish_energy" | "bullish_healthcare" | "bearish_compute" | "neutral" | null
}}

Rules:
- Only extract PERSONAL investments/roles, NOT investments by their employer company
- Confidence 1-3 = speculation/rumor; 4-6 = reported but unconfirmed; 7-10 = confirmed/filed
- If the article is not about personal investment activity, return empty activities array
- "mentioned_public_tickers" = any publicly traded companies discussed in the article

Respond ONLY with valid JSON."""

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 1024,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        result = json.loads(raw)
        return result.get("activities", []), result.get("mentioned_public_tickers", []), result.get("sector_signal")
    except Exception as e:
        print(f"  Warning: Gemini classification failed: {e}")
        return [], [], None


# ── SEC EDGAR Form D Search ───────────────────────────────────────────

def _search_edgar_form_d(exec_name: str) -> list[dict]:
    """Search SEC EDGAR for Form D filings mentioning this executive."""
    try:
        resp = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": f'"{exec_name}"',
                "dateRange": "custom",
                "startdt": (date.today() - timedelta(days=90)).isoformat(),
                "enddt": date.today().isoformat(),
                "forms": "D",
            },
            headers=EDGAR_HEADERS,
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            results = []
            for hit in hits[:5]:
                src = hit.get("_source", {})
                results.append({
                    "company": src.get("display_names", [""])[0] if src.get("display_names") else src.get("entity_name", ""),
                    "filing_date": src.get("file_date", ""),
                    "form_type": src.get("form_type", ""),
                    "accession": src.get("file_num", ""),
                })
            return results
        return []
    except Exception as e:
        logger.debug(f"EDGAR Form D search failed for {exec_name}: {e}")
        return []


# ── Data Collection Pipeline ──────────────────────────────────────────

def _search_exec_activity(exec_info: dict) -> list[dict]:
    """Search for an executive's personal investment activity."""
    exec_name = exec_info["name"]
    aliases = exec_info.get("search_aliases", [exec_name])
    all_results = []

    # Serper searches
    for alias in aliases[:AI_EXEC_SERPER_QUERIES_PER_EXEC]:
        results = _serper_search(alias, num_results=AI_EXEC_MAX_URLS_PER_EXEC)
        for r in results:
            if r["link"] and not _is_url_cached(r["link"]):
                all_results.append(r)

    # Supplementary Crunchbase/PitchBook search if few results
    if len(all_results) < 2:
        extra = _serper_search(
            f'"{exec_name}" site:crunchbase.com OR site:pitchbook.com',
            num_results=2,
        )
        for r in extra:
            if r["link"] and not _is_url_cached(r["link"]):
                all_results.append(r)

    # Deduplicate by URL
    seen = set()
    deduped = []
    for r in all_results:
        if r["link"] not in seen:
            seen.add(r["link"])
            deduped.append(r)

    return deduped[:AI_EXEC_MAX_URLS_PER_EXEC]


def _scrape_and_classify(
    search_results: list[dict], exec_info: dict,
) -> tuple[list[dict], list[str], list[str | None]]:
    """Scrape URLs and classify via Gemini. Returns (activities, tickers, sector_signals)."""
    all_activities = []
    all_tickers = []
    all_sector_signals = []

    for result in search_results:
        url = result["link"]

        # Try full scrape, fall back to snippet
        text = _firecrawl_scrape(url)
        if text:
            _cache_url(url, "ok")
            time.sleep(AI_EXEC_FIRECRAWL_DELAY)
        else:
            text = f"{result['title']}\n{result['snippet']}"
            _cache_url(url, "snippet_only")

        # Classify with Gemini
        activities, tickers, sector_signal = _classify_with_gemini(
            text=text,
            title=result["title"],
            exec_name=exec_info["name"],
            exec_role=exec_info["role"],
            exec_org=exec_info["org"],
        )
        time.sleep(AI_EXEC_GEMINI_DELAY)

        # Attach metadata to each activity
        for act in activities:
            act["exec_name"] = exec_info["name"]
            act["exec_org"] = exec_info["org"]
            act["exec_prominence"] = exec_info["prominence"]
            act["source_url"] = url
            act["source"] = result.get("title", "")[:200]

        all_activities.extend(activities)
        all_tickers.extend(tickers)
        all_sector_signals.append(sector_signal)

    return all_activities, all_tickers, all_sector_signals


# ── Scoring ───────────────────────────────────────────────────────────

def _score_investment(activity: dict) -> float:
    """Score a single investment activity 0-100."""
    score = 0.0

    # Component 1: Executive prominence (0-30 pts)
    prominence = activity.get("exec_prominence", 50)
    score += prominence * 0.30

    # Component 2: Activity type (0-25 pts)
    score += ACTIVITY_WEIGHTS.get(activity.get("activity_type", ""), 5)

    # Component 3: Confidence multiplier (0.3-1.0)
    confidence = activity.get("confidence", 5)
    score *= max(0.3, confidence / 10)

    # Component 4: Recency (0-15 pts, decays over 90 days)
    date_reported = activity.get("date_reported")
    if date_reported:
        try:
            days_old = (date.today() - date.fromisoformat(date_reported)).days
            recency = max(0, 15 * (1 - days_old / 90))
            score += recency
        except (ValueError, TypeError):
            score += 5  # default if date parse fails
    else:
        score += 5

    # Component 5: Public vs pre-IPO (3-10 pts)
    if activity.get("is_public"):
        score += 10
    elif activity.get("ipo_expected"):
        score += 7
    else:
        score += 3

    # Component 6: Investment size bonus (0-10 pts)
    amount = activity.get("investment_amount") or 0
    if amount >= 10_000_000:
        score += 10
    elif amount >= 1_000_000:
        score += 7
    elif amount >= 100_000:
        score += 4

    return max(0, min(100, score))


# ── Signal Aggregation ────────────────────────────────────────────────

def _aggregate_signals(today: str, all_activities: list[dict]) -> int:
    """Group activities by ticker, compute ai_exec_score, store signals."""
    # Filter by confidence and score
    scored = []
    for act in all_activities:
        if (act.get("confidence") or 0) < AI_EXEC_MIN_CONFIDENCE:
            continue
        raw_score = _score_investment(act)
        act["raw_score"] = raw_score
        if raw_score >= AI_EXEC_MIN_SCORE_STORE:
            scored.append(act)

    if not scored:
        return 0

    # Store raw investments
    inv_rows = []
    for act in scored:
        inv_rows.append((
            act.get("exec_name"), act.get("exec_org"), act.get("exec_prominence"),
            act.get("activity_type", "unknown"), act.get("target_company", "unknown"),
            act.get("target_ticker"), act.get("target_sector"),
            act.get("investment_amount"), act.get("funding_round"),
            1 if act.get("is_public") else 0,
            1 if act.get("ipo_expected") else 0,
            act.get("ipo_timeline"), act.get("date_reported"),
            act.get("confidence"), act.get("summary"),
            act.get("source_url"), act.get("source"),
            act.get("raw_score"), today,
        ))
    upsert_many(
        "ai_exec_investments",
        ["exec_name", "exec_org", "exec_prominence", "activity_type",
         "target_company", "target_ticker", "target_sector",
         "investment_amount", "funding_round", "is_public", "ipo_expected",
         "ipo_timeline", "date_reported", "confidence", "summary",
         "source_url", "source", "raw_score", "scan_date"],
        inv_rows,
    )

    # Group by ticker for universe-mapped signals
    ticker_map = defaultdict(list)
    for act in scored:
        ticker = act.get("target_ticker")
        if ticker:
            ticker_map[ticker.upper()].append(act)

    # Get stock universe for validation
    universe_rows = query("SELECT symbol FROM stock_universe")
    universe_symbols = {r["symbol"] for r in universe_rows}

    signal_rows = []
    for ticker, acts in ticker_map.items():
        if ticker not in universe_symbols:
            continue

        # Best score for this ticker
        best = max(acts, key=lambda a: a["raw_score"])
        ai_exec_score = best["raw_score"]
        exec_names = list({a["exec_name"] for a in acts})

        # Multi-exec convergence bonus
        if len(exec_names) >= 2:
            ai_exec_score = min(100, ai_exec_score + AI_EXEC_CONVERGENCE_BONUS)

        narrative_parts = []
        for a in acts:
            narrative_parts.append(
                f"{a['exec_name']} ({a['exec_org']}): {a.get('activity_type', '?')} — {a.get('summary', '')}"
            )

        signal_rows.append((
            ticker, today, round(ai_exec_score, 1), len(exec_names),
            exec_names[0] if exec_names else None,
            best.get("activity_type"),
            best.get("target_sector"),
            " | ".join(narrative_parts)[:500],
        ))

    if signal_rows:
        upsert_many(
            "ai_exec_signals",
            ["symbol", "date", "ai_exec_score", "exec_count", "top_exec",
             "top_activity", "sector_signal", "narrative"],
            signal_rows,
        )

    return len(signal_rows)


# ── Smart Money Boost ─────────────────────────────────────────────────

def _boost_smart_money(today: str) -> int:
    """Apply AI exec signal boosts to smart_money_scores conviction."""
    # Get recent ai_exec_signals (within lookback window)
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    exec_rows = query(
        "SELECT symbol, MAX(ai_exec_score) as ai_exec_score "
        "FROM ai_exec_signals WHERE date >= ? GROUP BY symbol",
        [cutoff],
    )
    if not exec_rows:
        return 0

    # Get latest smart money scores
    sm_rows = query("""
        SELECT s.symbol, s.date, s.conviction_score
        FROM smart_money_scores s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM smart_money_scores GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
    """)
    sm_by_symbol = {r["symbol"]: r for r in sm_rows}

    updates = 0
    with get_conn() as conn:
        for row in exec_rows:
            sym = row["symbol"]
            exec_score = row["ai_exec_score"]

            if exec_score >= 70:
                boost = AI_EXEC_SM_BOOST_HIGH
            elif exec_score >= 50:
                boost = AI_EXEC_SM_BOOST_MED
            else:
                continue

            if sym not in sm_by_symbol:
                # Create new smart money score from exec data
                conn.execute(
                    """INSERT OR REPLACE INTO smart_money_scores
                       (symbol, date, manager_count, conviction_score, top_holders)
                       VALUES (?, ?, 0, ?, '[]')""",
                    [sym, today, min(100, exec_score * 0.5)],
                )
                updates += 1
                continue

            sm = sm_by_symbol[sym]
            current = sm["conviction_score"] or 0
            new_score = max(0, min(100, current + boost))
            if new_score != current:
                conn.execute(
                    """UPDATE smart_money_scores
                       SET conviction_score = ?
                       WHERE symbol = ? AND date = ?""",
                    [new_score, sym, sm["date"]],
                )
                updates += 1

    return updates


# ── Sector Signal Feed ────────────────────────────────────────────────

def _feed_sector_signal(today: str) -> int:
    """When 3+ AI execs invest in same sector direction, add sector tilt."""
    cutoff = (date.today() - timedelta(days=AI_EXEC_LOOKBACK_DAYS)).isoformat()
    rows = query(
        """SELECT exec_name, target_sector, activity_type, raw_score
           FROM ai_exec_investments
           WHERE scan_date >= ? AND confidence >= ? AND target_sector IS NOT NULL""",
        [cutoff, AI_EXEC_MIN_CONFIDENCE],
    )

    # Group by sector
    sector_execs = defaultdict(set)
    sector_scores = defaultdict(list)
    for r in rows:
        sector_execs[r["target_sector"]].add(r["exec_name"])
        sector_scores[r["target_sector"]].append(r["raw_score"])

    fed = 0
    for sector, execs in sector_execs.items():
        if len(execs) >= 3:
            avg_score = sum(sector_scores[sector]) / len(sector_scores[sector])
            print(f"  Sector tilt: {sector} — {len(execs)} execs investing (avg score {avg_score:.0f})")
            fed += 1

    return fed


# ── Main Entry ────────────────────────────────────────────────────────

def run():
    """Main entry: search, classify, score, boost."""
    init_db()
    today = date.today().isoformat()
    print("AI Exec Tracker: Scanning executive investment activity...")

    # Check if full scan needed (weekly cadence)
    last_scan = query("SELECT MAX(scan_date) as last_scan FROM ai_exec_investments")
    needs_full_scan = True
    if last_scan and last_scan[0]["last_scan"]:
        days_since = (date.today() - date.fromisoformat(last_scan[0]["last_scan"])).days
        if days_since < AI_EXEC_SCAN_INTERVAL_DAYS:
            print(f"  Last scan {days_since}d ago (interval={AI_EXEC_SCAN_INTERVAL_DAYS}d), skipping full scan")
            needs_full_scan = False

    if needs_full_scan:
        all_activities = []
        total_urls = 0

        for exec_info in AI_EXEC_WATCHLIST:
            name = exec_info["name"]
            print(f"\n  [{name}] ({exec_info['role']} @ {exec_info['org']})")

            # Step 1: Discover URLs
            search_results = _search_exec_activity(exec_info)
            if not search_results:
                print(f"    No new URLs found")
                continue
            print(f"    Found {len(search_results)} new URLs")
            total_urls += len(search_results)

            # Step 2: Scrape and classify
            activities, tickers, sector_signals = _scrape_and_classify(search_results, exec_info)
            if activities:
                print(f"    Extracted {len(activities)} activities")
                for act in activities:
                    conf = act.get("confidence", 0)
                    print(f"      → {act.get('activity_type', '?')}: {act.get('target_company', '?')} "
                          f"(confidence={conf})")
            all_activities.extend(activities)

            # Step 3: EDGAR Form D (supplementary)
            form_d_hits = _search_edgar_form_d(name)
            if form_d_hits:
                print(f"    EDGAR Form D: {len(form_d_hits)} filings found")
                for hit in form_d_hits:
                    # Add as low-confidence activity for tracking
                    all_activities.append({
                        "activity_type": "fund_raise",
                        "target_company": hit["company"],
                        "target_ticker": None,
                        "target_sector": None,
                        "investment_amount": None,
                        "funding_round": None,
                        "is_public": False,
                        "ipo_expected": False,
                        "ipo_timeline": None,
                        "date_reported": hit["filing_date"],
                        "confidence": 6,
                        "summary": f"SEC Form D filing by {hit['company']} mentioning {name}",
                        "exec_name": name,
                        "exec_org": exec_info["org"],
                        "exec_prominence": exec_info["prominence"],
                        "source_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={hit['company']}&type=D&dateb=&owner=include&count=10",
                        "source": f"SEC EDGAR Form D: {hit['company']}",
                    })

            time.sleep(0.15)  # EDGAR rate limit

        # Step 4: Aggregate signals
        print(f"\n  Total: {total_urls} URLs scraped, {len(all_activities)} activities extracted")
        signal_count = _aggregate_signals(today, all_activities)
        print(f"  Stored {signal_count} universe-mapped signals")
    else:
        print("  Using existing signals from last scan")

    # Step 5: Boost smart money (runs every time, even on non-scan days)
    boost_count = _boost_smart_money(today)
    print(f"  Smart money boosts applied: {boost_count}")

    # Step 6: Sector signal analysis
    sector_count = _feed_sector_signal(today)
    if sector_count:
        print(f"  Sector tilts detected: {sector_count}")

    print("AI Exec Tracker: Done.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
