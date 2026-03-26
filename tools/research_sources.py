"""Curated Research Source Ingestion.

Scrapes and analyzes high-signal research publications:
  - Epoch AI (epochai.org) — AI compute trends, training run scaling
  - SemiAnalysis — semiconductor industry deep dives
  - Federal Reserve Research — monetary policy papers
  - BLS Reports — CPI/PPI/employment data

Pipeline per source:
  1. Serper API -> find 5 most recent relevant URLs
  2. Firecrawl -> extract clean markdown text from each URL
  3. Gemini Flash -> extract: mentioned tickers, sentiment, themes, summary
  4. Store to research_signals (skip cached URLs)

Outputs:
  - research_signals: per-article signals with ticker extraction
  - research_url_cache: prevents re-scraping the same URL

Usage: python -m tools.research_sources
"""

import sys
import json
import re
import time
from datetime import date
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    SERPER_API_KEY, FIRECRAWL_API_KEY, GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    RESEARCH_SOURCES, RESEARCH_MIN_SCRAPE_CHARS, RESEARCH_SNIPPET_FALLBACK,
)
from tools.db import init_db, upsert_many, query, get_conn


# ── Constants ──────────────────────────────────────────────────────────

SERPER_URL = "https://google.serper.dev/search"
FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
MAX_ARTICLE_CHARS = 8_000
SCRAPE_DELAY = 2.0   # seconds between Firecrawl calls (rate limit)
MAX_URLS_PER_SOURCE = 5

# All known investment-relevant themes
ALL_THEMES = [
    "ai_capex", "compute_scaling", "training_runs", "inference_demand",
    "semiconductors", "supply_chain", "fab_capacity", "chip_shortage",
    "monetary_policy", "inflation", "cpi", "ppi", "labor_market", "employment",
    "rate_hike", "rate_cut", "quantitative_tightening", "liquidity",
    "energy", "oil", "natural_gas", "renewables", "power_demand",
    "cloud_computing", "data_centers", "hyperscalers",
    "geopolitics", "trade_war", "tariffs", "china",
    "regulation", "fiscal_policy", "trade_policy", "m_and_a",
    "central_banks", "credit_markets", "commodities_physical",
]


# ── Serper + Firecrawl (same pattern as founder_letter_analyzer.py) ────

def _serper_search(query_str: str, num_results: int = MAX_URLS_PER_SOURCE) -> list[dict]:
    """Search using Serper API, return list of {title, link, snippet, date}."""
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


def _firecrawl_scrape(url: str) -> str | None:
    """Scrape URL via Firecrawl API, return clean markdown text."""
    if not FIRECRAWL_API_KEY:
        print("  Warning: FIRECRAWL_API_KEY not configured")
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
            # Strip boilerplate navigation/footer (heuristic: < 3 words per line)
            lines = [l for l in content.split("\n") if len(l.split()) >= 3 or l.startswith("#")]
            clean = "\n".join(lines)
            return clean[:MAX_ARTICLE_CHARS]
        return None
    except Exception as e:
        print(f"  Warning: Firecrawl scrape failed for {url}: {e}")
        return None


def _is_url_cached(url: str) -> bool:
    """Check if URL was already successfully scraped."""
    try:
        rows = query(
            "SELECT content FROM research_url_cache WHERE url = ?",
            [url],
        )
        return bool(rows and rows[0]["content"] == "ok")
    except Exception:
        return False


def _cache_url(url: str, status: str):
    try:
        upsert_many(
            "research_url_cache",
            ["url", "fetched_date", "content"],
            [(url, date.today().isoformat(), status)],
        )
    except Exception as e:
        print(f"  Warning: cache write failed for {url}: {e}")


def _analyze_with_gemini(
    text: str,
    title: str,
    source: str,
    relevance_tickers: list[str],
    is_snippet_only: bool = False,
) -> dict:
    """
    Use Gemini Flash to extract investment signals from article text.
    Returns dict with tickers (symbol + sentiment), themes, summary.
    """
    if not GEMINI_API_KEY:
        return {"tickers": [], "themes": [], "summary": title[:200]}

    ticker_list = ", ".join(relevance_tickers) if relevance_tickers else "none specified"
    themes_list = ", ".join(ALL_THEMES)

    snippet_note = ""
    if is_snippet_only:
        snippet_note = """
NOTE: Only the article title and snippet are available (full text behind paywall).
Base your analysis on whatever signal you can extract from these fragments.
Lower your relevance_score by 20 points to reflect reduced confidence.
If there is not enough information for meaningful analysis, set relevance_score to 0."""

    prompt = f"""You are an institutional investment analyst. Analyze this article and extract investment signals.
{snippet_note}

Source: {source}
Title: {title}

Article text:
{text[:4000]}

Extract the following as JSON:
1. "tickers": array of objects with "symbol" (from this list: {ticker_list}) and "sentiment" (+1 = bullish, -1 = bearish, 0 = neutral). Only include tickers explicitly discussed.
2. "themes": array of applicable themes from: {themes_list}. Maximum 4 themes.
3. "bullish_for": array of ticker symbols with clearly positive investment implications
4. "bearish_for": array of ticker symbols with clearly negative investment implications
5. "summary": 2-sentence investor summary. Be specific about magnitude and mechanism.
6. "relevance_score": 0-100 score for investment relevance (100 = critical market-moving insight, 50 = useful context, 0 = not actionable)

Respond ONLY with valid JSON. No markdown, no explanation."""

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

        # Clean up potential markdown code fences
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

        result = json.loads(raw)
        return result
    except Exception as e:
        print(f"  Warning: Gemini analysis failed: {e}")
        return {
            "tickers": [],
            "themes": [],
            "bullish_for": [],
            "bearish_for": [],
            "summary": title[:200],
            "relevance_score": 30,
        }


def run():
    """Main entry: fetch and analyze research articles from curated sources."""
    init_db()
    today = date.today().isoformat()
    print("Research Sources: Ingesting curated intelligence...")

    total_articles = 0
    total_signals = 0

    for source_config in RESEARCH_SOURCES:
        source_name = source_config["name"]
        serper_query = source_config["serper_query"]
        relevance_tickers = source_config["relevance_tickers"]
        themes = source_config["themes"]

        print(f"\n  [{source_name.upper().replace('_', ' ')}]")
        print(f"  Query: {serper_query}")

        # Step 1: Discover URLs
        search_results = _serper_search(serper_query)
        if not search_results:
            print(f"  No results found")
            continue

        print(f"  Found {len(search_results)} URLs")

        for result in search_results:
            url = result["link"]
            title = result["title"]

            if _is_url_cached(url):
                print(f"  [cached] {title[:60]}...")
                continue

            print(f"  Scraping: {title[:60]}...")
            time.sleep(SCRAPE_DELAY)

            # Step 2: Scrape content (with paywall snippet fallback)
            text = _firecrawl_scrape(url)
            is_snippet_only = False

            if not text or len(text) < RESEARCH_MIN_SCRAPE_CHARS:
                if RESEARCH_SNIPPET_FALLBACK and result.get("snippet"):
                    text = f"TITLE: {title}\n\nSNIPPET: {result['snippet']}"
                    is_snippet_only = True
                    print(f"  [snippet fallback] {title[:60]}...")
                else:
                    _cache_url(url, "empty")
                    continue

            # Step 3: Analyze with Gemini
            analysis = _analyze_with_gemini(text, title, source_name, relevance_tickers, is_snippet_only)

            # Step 4: Store
            tickers_data = analysis.get("tickers", [])
            bullish_for = json.dumps(analysis.get("bullish_for", []))
            bearish_for = json.dumps(analysis.get("bearish_for", []))
            key_themes = json.dumps(analysis.get("themes", themes))
            mentioned_tickers = json.dumps([t.get("symbol") for t in tickers_data if t.get("symbol")])
            article_summary = analysis.get("summary", title[:200])
            relevance_score = analysis.get("relevance_score", 30)

            # Store one row per article (with symbol=None for macro articles)
            # Plus additional rows per mentioned ticker for easier querying
            article_rows = []

            # Primary row (aggregate) — use "_MACRO" placeholder since symbol is NOT NULL in Postgres
            article_rows.append((
                "_MACRO", today, source_name, url, title,
                0.0, relevance_score, key_themes,
                mentioned_tickers, bullish_for, bearish_for, article_summary,
            ))

            # Per-ticker rows for easy lookup
            for ticker_entry in tickers_data:
                sym = ticker_entry.get("symbol")
                sentiment = ticker_entry.get("sentiment", 0)
                if sym:
                    article_rows.append((
                        sym, today, source_name, f"{url}#{sym}", title,
                        float(sentiment), relevance_score, key_themes,
                        json.dumps([sym]), bullish_for, bearish_for, article_summary,
                    ))

            try:
                upsert_many(
                    "research_signals",
                    ["symbol", "date", "source", "url", "title", "sentiment",
                     "relevance_score", "key_themes", "mentioned_tickers",
                     "bullish_for", "bearish_for", "article_summary"],
                    article_rows,
                )
                _cache_url(url, "ok")
                total_articles += 1
                total_signals += len(tickers_data)
            except Exception as e:
                print(f"  Warning: failed to store article {url}: {e}")
                continue

            bullish = analysis.get("bullish_for", [])
            bearish = analysis.get("bearish_for", [])
            print(f"  Relevance: {relevance_score}/100 | "
                  f"Themes: {len(analysis.get('themes', []))} | "
                  f"Bullish: {bullish[:3]} | Bearish: {bearish[:3]}")

    # Summary: top recent research signals
    top_signals = query(
        """
        SELECT symbol, source, relevance_score, article_summary, date
        FROM research_signals
        WHERE symbol IS NOT NULL AND date >= date('now', '-7 days')
        ORDER BY relevance_score DESC
        LIMIT 10
        """
    )
    if top_signals:
        print(f"\n  TOP RESEARCH SIGNALS (last 7 days):")
        print(f"  {'Symbol':<8} {'Source':<16} {'Score':>6}  Summary")
        print(f"  {'-'*70}")
        for r in top_signals:
            summary_short = (r["article_summary"] or "")[:50]
            print(f"  {r['symbol']:<8} {r['source']:<16} {r['relevance_score']:>6.0f}  {summary_short}...")

    print(f"\nResearch complete: {total_articles} articles ingested, {total_signals} ticker signals extracted")


if __name__ == "__main__":
    run()
