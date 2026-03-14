"""Foreign Intelligence Module — discover, translate, and score foreign-language
financial articles for global stocks.

Pipeline: Discover (Serper) → Filter (cache) → Scrape (Firecrawl) →
          Translate (DeepL tiered) → Analyze (Gemini) → Map tickers → Store

Supports: Japan, Korea, China/HK, Germany, France, Italy.
"""

import json
import time
import logging
import requests
from datetime import datetime, date

from tools.db import get_conn, query
from tools.config import (
    SERPER_API_KEY, FIRECRAWL_API_KEY, GEMINI_API_KEY, DEEPL_API_KEY,
    FOREIGN_INTEL_SOURCES, MARKET_LANGUAGE, MARKET_SERPER_PARAMS,
    FOREIGN_INTEL_MAX_ARTICLES_PER_SOURCE,
    FOREIGN_INTEL_MAX_CHARS_TRANSLATE,
    FOREIGN_INTEL_FULL_TEXT_THRESHOLD,
    FOREIGN_INTEL_FULL_TEXT_MAX_CHARS,
    SENTIMENT_CALIBRATION,
    REGIME_MARKET_PRIORITY,
)
from tools.ticker_mapper import get_ticker_map, resolve_ticker, init_ticker_map

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. DISCOVER — find article URLs via Serper
# ---------------------------------------------------------------------------

def _discover_articles(market: str, source_name: str, site_domain: str,
                       keywords: str, max_results: int = 5) -> list[dict]:
    """Search for recent articles from a specific foreign source."""
    if not SERPER_API_KEY:
        logger.warning("SERPER_API_KEY not set, skipping discovery.")
        return []

    serper_params = MARKET_SERPER_PARAMS.get(market, {})
    query_str = f"site:{site_domain} {keywords}"

    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={
                "q": query_str,
                "num": max_results,
                "tbs": "qdr:d3",   # last 3 days
                **serper_params,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.error(f"Serper search failed for {source_name}: {e}")
        return []

    results = []
    for item in data.get("organic", [])[:max_results]:
        results.append({
            "url": item.get("link", ""),
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "source": source_name,
        })
    return results


# ---------------------------------------------------------------------------
# 2. FILTER — skip already-scraped URLs
# ---------------------------------------------------------------------------

def _filter_cached(articles: list[dict]) -> list[dict]:
    """Remove articles already in the URL cache."""
    if not articles:
        return []

    urls = [a["url"] for a in articles]
    placeholders = ",".join(["?"] * len(urls))
    cached = query(
        f"SELECT url FROM foreign_intel_url_cache WHERE url IN ({placeholders})",
        urls,
    )
    cached_urls = {r["url"] for r in cached}
    return [a for a in articles if a["url"] not in cached_urls]


def _cache_url(url: str, status: str = "cached"):
    """Mark a URL as processed."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO foreign_intel_url_cache (url, scraped_at, status) VALUES (?, ?, ?)",
            (url, datetime.utcnow().isoformat(), status),
        )


# ---------------------------------------------------------------------------
# 3. SCRAPE — extract article text via Firecrawl
# ---------------------------------------------------------------------------

def _scrape_article(url: str) -> str | None:
    """Scrape article text using Firecrawl API."""
    if not FIRECRAWL_API_KEY:
        logger.warning("FIRECRAWL_API_KEY not set, skipping scrape.")
        return None

    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={
                "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "formats": ["markdown"],
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("markdown", "")
    except Exception as e:
        logger.error(f"Firecrawl scrape failed for {url}: {e}")
        _cache_url(url, "failed")
        return None


# ---------------------------------------------------------------------------
# 4. TRANSLATE — tiered DeepL translation
# ---------------------------------------------------------------------------

def _detect_target_lang(language: str) -> str:
    """Map our language code to DeepL source language."""
    return {
        "ja": "JA",
        "ko": "KO",
        "zh": "ZH",
        "de": "DE",
        "fr": "FR",
        "it": "IT",
    }.get(language, "")


def _translate_deepl(text: str, source_lang: str) -> tuple[str, int]:
    """Translate text via DeepL API. Returns (translated_text, char_count)."""
    if not DEEPL_API_KEY or not text:
        return text, 0

    try:
        # DeepL Free API uses api-free.deepl.com, Pro uses api.deepl.com
        # Try free first, fall back to pro
        base_url = "https://api-free.deepl.com" if "free" in DEEPL_API_KEY.lower() or ":fx" in DEEPL_API_KEY else "https://api.deepl.com"

        resp = requests.post(
            f"{base_url}/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
            data={
                "text": text,
                "source_lang": source_lang,
                "target_lang": "EN",
            },
            timeout=20,
        )
        resp.raise_for_status()
        result = resp.json()
        translated = result["translations"][0]["text"]
        return translated, len(text)
    except Exception as e:
        logger.error(f"DeepL translation failed: {e}")
        return text, 0


def _translate_tiered(title: str, body: str, language: str) -> dict:
    """Tiered translation strategy for cost control.

    Tier 1: Translate headline + first 2 sentences (always).
    Tier 2: Translate first 2000 chars of body (if headline is relevant).
    Tier 3: Triggered later if Gemini flags relevance > 80.

    Returns dict with translated text and metadata.
    """
    source_lang = _detect_target_lang(language)
    total_chars = 0

    # Tier 1: Always translate title
    title_translated, chars = _translate_deepl(title, source_lang)
    total_chars += chars

    # Extract first ~500 chars for initial assessment
    snippet = body[:500] if body else ""
    snippet_translated, chars = _translate_deepl(snippet, source_lang)
    total_chars += chars

    # Tier 2: Translate more if snippet looks relevant
    body_translated = snippet_translated
    if len(body) > 500:
        more = body[500:FOREIGN_INTEL_MAX_CHARS_TRANSLATE]
        more_translated, chars = _translate_deepl(more, source_lang)
        total_chars += chars
        body_translated = snippet_translated + " " + more_translated

    return {
        "title_translated": title_translated,
        "body_translated": body_translated,
        "translation_method": "deepl",
        "char_count": total_chars,
    }


def _translate_tier3(body: str, language: str, existing_chars: int) -> tuple[str, int]:
    """Tier 3: Translate full article text (up to 10K chars) for high-relevance articles."""
    source_lang = _detect_target_lang(language)
    # Translate the remaining text beyond what Tier 2 covered
    remaining = body[FOREIGN_INTEL_MAX_CHARS_TRANSLATE:FOREIGN_INTEL_FULL_TEXT_MAX_CHARS]
    if not remaining:
        return "", existing_chars
    translated, chars = _translate_deepl(remaining, source_lang)
    return translated, existing_chars + chars


# ---------------------------------------------------------------------------
# 5. ANALYZE — extract signals via Gemini
# ---------------------------------------------------------------------------

def _calibrate_sentiment(raw_sentiment: float, language: str) -> float:
    """Apply cultural calibration to raw sentiment score."""
    cal = SENTIMENT_CALIBRATION.get(language, 1.0)

    if isinstance(cal, dict):
        # Chinese: different factors for positive vs negative
        if raw_sentiment > 0:
            return max(-1.0, min(1.0, raw_sentiment * cal.get("positive", 1.0)))
        else:
            return max(-1.0, min(1.0, raw_sentiment * cal.get("negative", 1.0)))
    else:
        return max(-1.0, min(1.0, raw_sentiment * cal))


def _analyze_with_gemini(title: str, body: str, language: str,
                         market: str, ticker_map: dict) -> dict | None:
    """Use Gemini to extract structured signals from a translated article.

    Returns dict with: sentiment, relevance_score, key_themes,
    mentioned_tickers, bullish_for, bearish_for, article_summary
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set, skipping analysis.")
        return None

    known_companies = ", ".join(
        f"{name} ({ticker})" for name, ticker in list(ticker_map.items())[:50]
        if not name.endswith((".T", ".KS", ".HK", ".DE", ".PA", ".MI", ".AS", ".SW", ".L"))
    )

    prompt = f"""You are a financial analyst extracting trading signals from a translated {language} article.

ARTICLE TITLE: {title}

ARTICLE BODY (translated to English):
{body[:3000]}

KNOWN COMPANIES IN THIS MARKET:
{known_companies}

Analyze this article and return a JSON object with these fields:
- "sentiment": float from -1.0 (very bearish) to 1.0 (very bullish), reflecting the article's tone about the companies/markets discussed
- "relevance_score": int 0-100, how relevant this is for investment decisions (0=irrelevant fluff, 100=material market-moving)
- "key_themes": list of 1-3 theme tags (e.g., "EARNINGS_BEAT", "SUPPLY_CHAIN", "REGULATORY", "AI_EXPANSION", "MARGIN_PRESSURE")
- "mentioned_tickers": list of ADR ticker symbols mentioned or discussed (use the known companies list above to map)
- "bullish_for": list of ADR tickers this article is bullish for
- "bearish_for": list of ADR tickers this article is bearish for
- "summary": 2-3 sentence summary of the key investment-relevant takeaway

IMPORTANT: Only output valid JSON, no markdown formatting or extra text.
"""

    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Clean up markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)
        # Calibrate sentiment
        raw = result.get("sentiment", 0)
        result["sentiment"] = _calibrate_sentiment(float(raw), language)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"Gemini returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Gemini analysis failed: {e}")
        return None


# ---------------------------------------------------------------------------
# 6. STORE — write signals to database
# ---------------------------------------------------------------------------

def _store_signal(symbol: str, local_ticker: str, article: dict,
                  translation: dict, analysis: dict,
                  market: str, language: str):
    """Store a processed foreign intel signal."""
    today = date.today().isoformat()

    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO foreign_intel_signals
               (symbol, local_ticker, date, market, language, source, url,
                title_original, title_translated, sentiment, relevance_score,
                key_themes, mentioned_tickers, bullish_for, bearish_for,
                article_summary, translation_method, char_count_translated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                symbol,
                local_ticker,
                today,
                market,
                language,
                article["source"],
                article["url"],
                article.get("title", ""),
                translation.get("title_translated", ""),
                analysis.get("sentiment", 0),
                analysis.get("relevance_score", 0),
                json.dumps(analysis.get("key_themes", [])),
                json.dumps(analysis.get("mentioned_tickers", [])),
                json.dumps(analysis.get("bullish_for", [])),
                json.dumps(analysis.get("bearish_for", [])),
                analysis.get("summary", ""),
                translation.get("translation_method", "deepl"),
                translation.get("char_count", 0),
            ),
        )
    _cache_url(article["url"], "cached")


# ---------------------------------------------------------------------------
# 7. ORCHESTRATOR — main entry point
# ---------------------------------------------------------------------------

def _get_current_regime() -> str:
    """Get the current macro regime from the database."""
    rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    if rows:
        return rows[0]["regime"]
    return "neutral"


def _get_market_order(regime: str) -> list[str]:
    """Get prioritized market scan order based on regime."""
    return REGIME_MARKET_PRIORITY.get(regime, list(FOREIGN_INTEL_SOURCES.keys()))


def run(markets: list[str] = None):
    """Run the foreign intelligence pipeline.

    Args:
        markets: Optional list of specific markets to scan.
                 If None, scans all markets in regime-prioritized order.
    """
    print("\n" + "=" * 60)
    print("  FOREIGN INTELLIGENCE MODULE")
    print("=" * 60)

    # Ensure ticker map is populated
    init_ticker_map()

    # Determine market scan order
    regime = _get_current_regime()
    if markets:
        market_order = markets
    else:
        market_order = _get_market_order(regime)

    print(f"  Regime: {regime} | Markets: {', '.join(market_order)}")

    total_articles = 0
    total_signals = 0
    total_chars = 0

    for market in market_order:
        sources = FOREIGN_INTEL_SOURCES.get(market, [])
        language = MARKET_LANGUAGE.get(market, "en")
        ticker_map = get_ticker_map(market)

        print(f"\n  [{market.upper()}] Scanning {len(sources)} sources ({language})...")

        for source_name, site_domain, keywords in sources:
            # 1. Discover
            articles = _discover_articles(
                market, source_name, site_domain, keywords,
                max_results=FOREIGN_INTEL_MAX_ARTICLES_PER_SOURCE,
            )
            if not articles:
                continue

            # 2. Filter cached
            articles = _filter_cached(articles)
            if not articles:
                continue

            print(f"    {source_name}: {len(articles)} new articles")
            total_articles += len(articles)

            for article in articles:
                try:
                    # 3. Scrape
                    body = _scrape_article(article["url"])
                    if not body or len(body) < 100:
                        _cache_url(article["url"], "empty")
                        continue

                    # 4. Translate (tiered)
                    translation = _translate_tiered(
                        article.get("title", ""), body, language,
                    )
                    total_chars += translation.get("char_count", 0)

                    # 5. Analyze with Gemini
                    analysis = _analyze_with_gemini(
                        translation["title_translated"],
                        translation["body_translated"],
                        language, market, ticker_map,
                    )
                    if not analysis:
                        _cache_url(article["url"], "analysis_failed")
                        continue

                    # Tier 3: If high relevance, translate full text and re-analyze
                    relevance = analysis.get("relevance_score", 0)
                    if relevance >= FOREIGN_INTEL_FULL_TEXT_THRESHOLD and len(body) > FOREIGN_INTEL_MAX_CHARS_TRANSLATE:
                        extra_text, total_chars_updated = _translate_tier3(
                            body, language, total_chars,
                        )
                        total_chars = total_chars_updated
                        if extra_text:
                            full_body = translation["body_translated"] + " " + extra_text
                            # Re-analyze with full context
                            analysis = _analyze_with_gemini(
                                translation["title_translated"],
                                full_body, language, market, ticker_map,
                            ) or analysis
                            translation["body_translated"] = full_body
                            translation["translation_method"] = "deepl_full"

                    # 6. Map tickers and store
                    mentioned = analysis.get("mentioned_tickers", [])
                    if mentioned:
                        for ticker in mentioned:
                            _store_signal(
                                symbol=ticker,
                                local_ticker=None,
                                article=article,
                                translation=translation,
                                analysis=analysis,
                                market=market,
                                language=language,
                            )
                            total_signals += 1
                    else:
                        # Try to resolve from article title/content
                        resolved = resolve_ticker(article.get("title", ""), market)
                        if resolved:
                            analysis["mentioned_tickers"] = [resolved]
                            _store_signal(
                                symbol=resolved,
                                local_ticker=None,
                                article=article,
                                translation=translation,
                                analysis=analysis,
                                market=market,
                                language=language,
                            )
                            total_signals += 1
                        else:
                            # Store without symbol for manual review
                            _store_signal(
                                symbol="UNMAPPED",
                                local_ticker=None,
                                article=article,
                                translation=translation,
                                analysis=analysis,
                                market=market,
                                language=language,
                            )

                    # Respectful delay between scrapes
                    time.sleep(1.5)

                except Exception as e:
                    logger.error(f"Error processing {article['url']}: {e}")
                    _cache_url(article["url"], "error")
                    continue

    print(f"\n  ── Summary ──")
    print(f"  Articles processed: {total_articles}")
    print(f"  Signals stored:     {total_signals}")
    print(f"  Characters translated: {total_chars:,}")
    print(f"  Estimated cost:     ${total_chars / 1_000_000 * 25:.2f}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Scoring — used by convergence engine
# ---------------------------------------------------------------------------

def compute_foreign_intel_scores() -> dict[str, float]:
    """Compute foreign intel scores per symbol for convergence.

    Returns dict: {symbol: score (0-100)}
    """
    from tools.config import FOREIGN_INTEL_LOOKBACK_DAYS

    rows = query("""
        SELECT symbol,
               AVG(sentiment) as avg_sentiment,
               AVG(relevance_score) as avg_relevance,
               COUNT(*) as article_count
        FROM foreign_intel_signals
        WHERE symbol != 'UNMAPPED'
          AND date >= date('now', ?)
        GROUP BY symbol
    """, [f"-{FOREIGN_INTEL_LOOKBACK_DAYS} days"])

    scores = {}
    for r in rows:
        # Normalize: sentiment (-1 to 1) → (0 to 1), multiply by relevance (0-100)
        base = ((r["avg_sentiment"] + 1) / 2) * r["avg_relevance"]
        # Volume boost: more articles = stronger signal (capped at 1.5x)
        volume_mult = min(1.5, 1.0 + r["article_count"] * 0.05)
        scores[r["symbol"]] = max(0, min(100, base * volume_mult))

    return scores


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from tools.db import init_db
    init_db()
    run()
