"""Foreign Intelligence — discover, translate, score foreign-language financial articles."""
import json, time, logging, requests
from datetime import datetime, date
from tools.db import get_conn, query
from tools.config import (
    SERPER_API_KEY, FIRECRAWL_API_KEY, GEMINI_API_KEY, DEEPL_API_KEY,
    FOREIGN_INTEL_SOURCES, MARKET_LANGUAGE, MARKET_SERPER_PARAMS,
    FOREIGN_INTEL_MAX_ARTICLES_PER_SOURCE, FOREIGN_INTEL_MAX_CHARS_TRANSLATE,
    FOREIGN_INTEL_FULL_TEXT_THRESHOLD, FOREIGN_INTEL_FULL_TEXT_MAX_CHARS,
    SENTIMENT_CALIBRATION, REGIME_MARKET_PRIORITY,
)
from tools.ticker_mapper import get_ticker_map, resolve_ticker, init_ticker_map

logger = logging.getLogger(__name__)

LANG_MAP = {"ja": "JA", "ko": "KO", "zh": "ZH", "de": "DE", "fr": "FR", "it": "IT"}

def _discover_articles(market, source_name, site_domain, keywords, max_results=5):
    if not SERPER_API_KEY: return []
    try:
        resp = requests.post("https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": f"site:{site_domain} {keywords}", "num": max_results, "tbs": "qdr:d3",
                  **MARKET_SERPER_PARAMS.get(market, {})}, timeout=15)
        resp.raise_for_status()
        return [{"url": i.get("link",""), "title": i.get("title",""),
                 "snippet": i.get("snippet",""), "source": source_name}
                for i in resp.json().get("organic", [])[:max_results]]
    except Exception as e:
        logger.error(f"Serper search failed for {source_name}: {e}"); return []

def _filter_cached(articles):
    if not articles: return []
    urls = [a["url"] for a in articles]
    cached = {r["url"] for r in query(
        f"SELECT url FROM foreign_intel_url_cache WHERE url IN ({','.join(['?']*len(urls))})", urls)}
    return [a for a in articles if a["url"] not in cached]

def _cache_url(url, status="cached"):
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO foreign_intel_url_cache (url, scraped_at, status) VALUES (?,?,?)",
                     (url, datetime.utcnow().isoformat(), status))

def _scrape_article(url):
    if not FIRECRAWL_API_KEY: return None
    try:
        resp = requests.post("https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"]}, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", {}).get("markdown", "")
    except Exception as e:
        logger.error(f"Firecrawl scrape failed for {url}: {e}"); _cache_url(url, "failed"); return None

def _translate_deepl(text, source_lang):
    if not DEEPL_API_KEY or not text: return text, 0
    try:
        base = "https://api-free.deepl.com" if "free" in DEEPL_API_KEY.lower() or ":fx" in DEEPL_API_KEY else "https://api.deepl.com"
        resp = requests.post(f"{base}/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"},
            data={"text": text, "source_lang": source_lang, "target_lang": "EN"}, timeout=20)
        resp.raise_for_status()
        return resp.json()["translations"][0]["text"], len(text)
    except Exception as e:
        logger.error(f"DeepL translation failed: {e}"); return text, 0

def _translate_tiered(title, body, language):
    sl = LANG_MAP.get(language, "")
    total = 0
    title_t, c = _translate_deepl(title, sl); total += c
    snippet_t, c = _translate_deepl(body[:500] if body else "", sl); total += c
    body_t = snippet_t
    if len(body) > 500:
        more_t, c = _translate_deepl(body[500:FOREIGN_INTEL_MAX_CHARS_TRANSLATE], sl); total += c
        body_t = snippet_t + " " + more_t
    return {"title_translated": title_t, "body_translated": body_t, "translation_method": "deepl", "char_count": total}

def _translate_tier3(body, language, existing_chars):
    remaining = body[FOREIGN_INTEL_MAX_CHARS_TRANSLATE:FOREIGN_INTEL_FULL_TEXT_MAX_CHARS]
    if not remaining: return "", existing_chars
    t, c = _translate_deepl(remaining, LANG_MAP.get(language, ""))
    return t, existing_chars + c

def _calibrate_sentiment(raw, language):
    cal = SENTIMENT_CALIBRATION.get(language, 1.0)
    if isinstance(cal, dict):
        factor = cal.get("positive", 1.0) if raw > 0 else cal.get("negative", 1.0)
        return max(-1.0, min(1.0, raw * factor))
    return max(-1.0, min(1.0, raw * cal))

def _analyze_with_gemini(title, body, language, market, ticker_map):
    if not GEMINI_API_KEY: return None
    known = ", ".join(f"{n} ({t})" for n, t in list(ticker_map.items())[:50]
                      if not n.endswith((".T",".KS",".HK",".DE",".PA",".MI",".AS",".SW",".L")))
    prompt = f"""Financial analyst extracting trading signals from translated {language} article.
TITLE: {title}
BODY: {body[:3000]}
KNOWN COMPANIES: {known}
Return JSON: {{"sentiment": float -1..1, "relevance_score": int 0-100, "key_themes": [1-3 tags],
"mentioned_tickers": [ADR tickers], "bullish_for": [tickers], "bearish_for": [tickers], "summary": "2-3 sentences"}}
Only output valid JSON."""
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1000}}, timeout=30)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```"): text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"): text = text[:-3]
        result = json.loads(text.strip())
        result["sentiment"] = _calibrate_sentiment(float(result.get("sentiment", 0)), language)
        return result
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Gemini analysis failed: {e}"); return None

def _store_signal(symbol, local_ticker, article, translation, analysis, market, language):
    today = date.today().isoformat()
    with get_conn() as conn:
        conn.execute("""INSERT OR REPLACE INTO foreign_intel_signals
            (symbol, local_ticker, date, market, language, source, url, title_original,
             title_translated, sentiment, relevance_score, key_themes, mentioned_tickers,
             bullish_for, bearish_for, article_summary, translation_method, char_count_translated)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (symbol, local_ticker, today, market, language, article["source"], article["url"],
             article.get("title",""), translation.get("title_translated",""),
             analysis.get("sentiment",0), analysis.get("relevance_score",0),
             json.dumps(analysis.get("key_themes",[])), json.dumps(analysis.get("mentioned_tickers",[])),
             json.dumps(analysis.get("bullish_for",[])), json.dumps(analysis.get("bearish_for",[])),
             analysis.get("summary",""), translation.get("translation_method","deepl"),
             translation.get("char_count",0)))
    _cache_url(article["url"], "cached")

def run(markets=None):
    print("\n" + "="*60 + "\n  FOREIGN INTELLIGENCE MODULE\n" + "="*60)
    init_ticker_map()
    regime_rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = regime_rows[0]["regime"] if regime_rows else "neutral"
    market_order = markets or REGIME_MARKET_PRIORITY.get(regime, list(FOREIGN_INTEL_SOURCES.keys()))
    print(f"  Regime: {regime} | Markets: {', '.join(market_order)}")
    total_articles = total_signals = total_chars = 0
    for market in market_order:
        sources = FOREIGN_INTEL_SOURCES.get(market, [])
        language = MARKET_LANGUAGE.get(market, "en")
        ticker_map = get_ticker_map(market)
        print(f"\n  [{market.upper()}] Scanning {len(sources)} sources ({language})...")
        for source_name, site_domain, keywords in sources:
            articles = _discover_articles(market, source_name, site_domain, keywords,
                                          max_results=FOREIGN_INTEL_MAX_ARTICLES_PER_SOURCE)
            articles = _filter_cached(articles) if articles else []
            if not articles: continue
            print(f"    {source_name}: {len(articles)} new articles"); total_articles += len(articles)
            for article in articles:
                try:
                    body = _scrape_article(article["url"])
                    if not body or len(body) < 100: _cache_url(article["url"], "empty"); continue
                    translation = _translate_tiered(article.get("title",""), body, language)
                    total_chars += translation.get("char_count", 0)
                    analysis = _analyze_with_gemini(translation["title_translated"],
                        translation["body_translated"], language, market, ticker_map)
                    if not analysis: _cache_url(article["url"], "analysis_failed"); continue
                    rel = analysis.get("relevance_score", 0)
                    if rel >= FOREIGN_INTEL_FULL_TEXT_THRESHOLD and len(body) > FOREIGN_INTEL_MAX_CHARS_TRANSLATE:
                        extra, total_chars = _translate_tier3(body, language, total_chars)
                        if extra:
                            full = translation["body_translated"] + " " + extra
                            analysis = _analyze_with_gemini(translation["title_translated"],
                                full, language, market, ticker_map) or analysis
                            translation["body_translated"] = full
                            translation["translation_method"] = "deepl_full"
                    mentioned = analysis.get("mentioned_tickers", [])
                    if not mentioned:
                        resolved = resolve_ticker(article.get("title",""), market)
                        mentioned = [resolved] if resolved else ["UNMAPPED"]
                        analysis["mentioned_tickers"] = mentioned
                    for ticker in mentioned:
                        _store_signal(ticker, None, article, translation, analysis, market, language)
                        total_signals += 1
                    time.sleep(1.5)
                except Exception as e:
                    logger.error(f"Error processing {article['url']}: {e}")
                    _cache_url(article["url"], "error")
    print(f"\n  -- Summary --\n  Articles: {total_articles} | Signals: {total_signals} | "
          f"Chars: {total_chars:,} | Est cost: ${total_chars/1e6*25:.2f}\n" + "="*60)

def compute_foreign_intel_scores():
    from tools.config import FOREIGN_INTEL_LOOKBACK_DAYS
    rows = query("""SELECT symbol, AVG(sentiment) as avg_sentiment, AVG(relevance_score) as avg_relevance,
        COUNT(*) as article_count FROM foreign_intel_signals
        WHERE symbol != 'UNMAPPED' AND date >= date('now', ?)
        GROUP BY symbol""", [f"-{FOREIGN_INTEL_LOOKBACK_DAYS} days"])
    scores = {}
    for r in rows:
        base = ((r["avg_sentiment"] + 1) / 2) * r["avg_relevance"]
        scores[r["symbol"]] = max(0, min(100, base * min(1.5, 1.0 + r["article_count"] * 0.05)))
    return scores

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from tools.db import init_db; init_db(); run()
