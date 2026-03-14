"""News Displacement Detection — finds material news the market hasn't priced in.

Core thesis: when significant news drops and the affected asset doesn't move,
that's a displacement opportunity. This module:
  1. Pulls recent company news via Finnhub
  2. Pulls high-relevance research_signals and foreign_intel_signals from DB
  3. Uses Gemini to identify affected tickers + expected impact (first/second/cross-asset)
  4. Compares expected vs actual price movement
  5. Flags gaps as displacement signals

Why this exists: The existing system tells you what IS moving.
This tells you what SHOULD be moving but ISN'T — the actual displacement.

Usage: python -m tools.news_displacement
"""

import sys
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests
import finnhub

from tools.config import FINNHUB_API_KEY, GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL
from tools.db import init_db, get_conn, query


# ── Constants ──────────────────────────────────────────────────────────

# Minimum displacement score to store (filter noise)
MIN_DISPLACEMENT_SCORE = 30
# How many days of news to look back
NEWS_LOOKBACK_DAYS = 3
# Max news items per batch to Gemini (token efficiency)
GEMINI_BATCH_SIZE = 8
# Rate limit: seconds between Finnhub calls
FINNHUB_DELAY = 0.15
# Rate limit: seconds between Gemini calls
GEMINI_DELAY = 1.5


def _get_finnhub_client():
    return finnhub.Client(api_key=FINNHUB_API_KEY)


def _fetch_company_news(client, symbols: list[str]) -> list[dict]:
    """Fetch recent company news from Finnhub for all symbols.

    Returns list of {symbol, headline, source, url, datetime, summary}.
    Deduplicates by URL.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    lookback = (datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    all_news = []
    seen_urls = set()

    for i, symbol in enumerate(symbols):
        try:
            articles = client.company_news(symbol, _from=lookback, to=today)
            if not articles:
                continue

            # Take top 3 most recent per symbol (avoid flooding)
            for article in articles[:3]:
                url = article.get("url", "")
                if url in seen_urls or not url:
                    continue
                seen_urls.add(url)

                all_news.append({
                    "symbol": symbol,
                    "headline": article.get("headline", ""),
                    "source": article.get("source", ""),
                    "url": url,
                    "datetime": article.get("datetime", 0),
                    "summary": article.get("summary", "")[:300],
                })
        except Exception:
            pass

        if (i + 1) % 30 == 0:
            print(f"    News fetch: {i + 1}/{len(symbols)}")
            time.sleep(FINNHUB_DELAY * 3)
        elif (i + 1) % 5 == 0:
            time.sleep(FINNHUB_DELAY)

    return all_news


def _pull_recent_signals() -> list[dict]:
    """Pull high-relevance research_signals and foreign_intel_signals from DB."""
    signals = []

    # Research signals (relevance >= 60, last 3 days)
    rows = query("""
        SELECT symbol, title, source, url, article_summary, sentiment, relevance_score
        FROM research_signals
        WHERE date >= date('now', '-3 days') AND relevance_score >= 60
        ORDER BY relevance_score DESC LIMIT 30
    """)
    for r in rows:
        signals.append({
            "headline": r["title"] or "",
            "source": f"research:{r['source']}",
            "url": r["url"],
            "summary": r["article_summary"] or "",
            "symbol": r["symbol"],
        })

    # Foreign intel signals (relevance >= 60, last 3 days)
    rows = query("""
        SELECT symbol, title_translated, source, url, article_summary, sentiment, relevance_score
        FROM foreign_intel_signals
        WHERE date >= date('now', '-3 days') AND relevance_score >= 60
          AND symbol != 'UNMAPPED'
        ORDER BY relevance_score DESC LIMIT 20
    """)
    for r in rows:
        signals.append({
            "headline": r["title_translated"] or "",
            "source": f"foreign:{r['source']}",
            "url": r["url"],
            "summary": r["article_summary"] or "",
            "symbol": r["symbol"],
        })

    return signals


def _get_price_changes(symbols: list[str]) -> dict[str, dict]:
    """Get recent price changes for symbols.

    Returns: {symbol: {price_1d: float, price_3d: float, current: float}}
    """
    changes = {}
    for symbol in symbols:
        rows = query("""
            SELECT date, close FROM price_data
            WHERE symbol = ? ORDER BY date DESC LIMIT 5
        """, [symbol])
        if len(rows) < 2:
            continue

        current = rows[0]["close"]
        prev_1d = rows[1]["close"] if len(rows) >= 2 else current
        prev_3d = rows[3]["close"] if len(rows) >= 4 else rows[-1]["close"]

        changes[symbol] = {
            "current": current,
            "price_1d": ((current - prev_1d) / prev_1d * 100) if prev_1d else 0,
            "price_3d": ((current - prev_3d) / prev_3d * 100) if prev_3d else 0,
        }
    return changes


def _analyze_news_batch(news_items: list[dict], universe_symbols: list[str]) -> list[dict]:
    """Send a batch of news items to Gemini for displacement analysis.

    Returns list of structured analysis dicts.
    """
    if not GEMINI_API_KEY or not news_items:
        return []

    # Build news digest for the prompt
    news_digest = ""
    for i, item in enumerate(news_items):
        news_digest += f"\n[{i+1}] ({item.get('source', 'unknown')}) {item['headline']}\n"
        if item.get("summary"):
            news_digest += f"    {item['summary'][:200]}\n"

    # Only include top tickers for context (avoid token waste)
    top_tickers = ", ".join(universe_symbols[:200])

    prompt = f"""You are a senior macro trader at a top hedge fund. Analyze these news items for DISPLACEMENT opportunities — material events that should move specific assets but may not be priced in yet.

NEWS ITEMS:{news_digest}

STOCK UNIVERSE (subset): {top_tickers}

For each news item that is INVESTMENT-MATERIAL (skip fluff), output:
{{
  "news_index": <1-based index>,
  "affected_tickers": [
    {{
      "symbol": "<ticker>",
      "expected_direction": "bullish" or "bearish",
      "expected_magnitude": <expected % move, e.g. 2.5>,
      "order_type": "first_order" or "second_order" or "cross_asset",
      "reasoning": "<1 sentence>"
    }}
  ],
  "materiality_score": <0-100>,
  "time_horizon": "immediate" or "days" or "weeks",
  "confidence": <0.0-1.0>
}}

CRITICAL RULES:
- Only flag genuinely material news (earnings surprises, regulatory changes, supply disruptions, macro shifts, M&A, guidance changes)
- second_order = supply chain/competitor effects. cross_asset = commodity→producer, macro→sector
- Expected magnitude: be specific and realistic (1-3% for moderate, 5%+ for major events)
- Skip routine coverage, analyst notes, and noise
- Return a JSON array of analyses. Skip non-material news entirely.

Respond ONLY with a valid JSON array. No markdown, no explanation."""

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 2048,
                },
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Clean markdown fences
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

        analyses = json.loads(raw)
        if not isinstance(analyses, list):
            analyses = [analyses]
        return analyses

    except Exception as e:
        print(f"  Warning: Gemini analysis failed: {e}")
        return []


def _compute_displacement_score(
    materiality: float,
    expected_mag: float,
    actual_change: float,
    confidence: float,
) -> float:
    """Compute displacement score: high materiality + low price response = high score.

    Score 0-100. Higher = bigger displacement opportunity.
    """
    if expected_mag <= 0:
        return 0.0

    # How much of the expected move actually happened?
    # If actual moved in OPPOSITE direction, that's even more displacement
    actual_abs = abs(actual_change)
    if actual_change * (1 if expected_mag > 0 else -1) < 0:
        # Price moved opposite to expected — extra displacement
        response_gap = 1.0 + (actual_abs / abs(expected_mag))
    else:
        # Price moved in right direction but maybe not enough
        response_gap = max(0, 1.0 - (actual_abs / abs(expected_mag)))

    score = materiality * response_gap * confidence
    return max(0, min(100, score))


def run(symbols=None):
    """Main entry: detect news displacement signals.

    Args:
        symbols: Optional list of symbols to analyze. If None, uses full
                 stock universe (backward compatible).
    """
    init_db()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  NEWS DISPLACEMENT DETECTION")
    print("=" * 60)

    if not FINNHUB_API_KEY:
        print("  ERROR: FINNHUB_API_KEY not set")
        return
    if not GEMINI_API_KEY:
        print("  ERROR: GEMINI_API_KEY not set")
        return

    # Get stock universe (use provided symbols or full universe)
    if symbols is None:
        universe = query("SELECT symbol FROM stock_universe ORDER BY market_cap DESC LIMIT 500")
        symbols = [r["symbol"] for r in universe]
    if not symbols:
        print("  No stocks in universe. Run fetch_stock_universe first.")
        return

    # Step 1: Fetch news
    print(f"  Fetching news for {len(symbols)} symbols...")
    client = _get_finnhub_client()
    news_items = _fetch_company_news(client, symbols)
    print(f"  Collected {len(news_items)} news items")

    # Step 2: Pull existing intelligence signals from DB
    db_signals = _pull_recent_signals()
    print(f"  Pulled {len(db_signals)} existing intelligence signals")

    # Combine all news items
    all_items = news_items + db_signals
    if not all_items:
        print("  No news items to analyze.")
        return

    # Step 3: Analyze in batches with Gemini
    print(f"  Analyzing {len(all_items)} items in batches of {GEMINI_BATCH_SIZE}...")
    all_analyses = []

    for batch_start in range(0, len(all_items), GEMINI_BATCH_SIZE):
        batch = all_items[batch_start:batch_start + GEMINI_BATCH_SIZE]
        batch_num = batch_start // GEMINI_BATCH_SIZE + 1
        total_batches = (len(all_items) + GEMINI_BATCH_SIZE - 1) // GEMINI_BATCH_SIZE
        print(f"    Batch {batch_num}/{total_batches}...")

        analyses = _analyze_news_batch(batch, symbols)

        # Map analyses back to news items
        for analysis in analyses:
            idx = analysis.get("news_index", 0) - 1
            if 0 <= idx < len(batch):
                analysis["_source_item"] = batch[idx]
            all_analyses.append(analysis)

        if batch_start + GEMINI_BATCH_SIZE < len(all_items):
            time.sleep(GEMINI_DELAY)

    print(f"  Got {len(all_analyses)} material analyses from Gemini")

    # Step 4: Get price data for all affected tickers
    affected_symbols = set()
    for analysis in all_analyses:
        for ticker in analysis.get("affected_tickers", []):
            sym = ticker.get("symbol", "")
            if sym:
                affected_symbols.add(sym)

    price_changes = _get_price_changes(list(affected_symbols))
    print(f"  Price data for {len(price_changes)} affected symbols")

    # Step 5: Compute displacement scores and store
    rows_to_store = []
    displacement_count = 0

    for analysis in all_analyses:
        source_item = analysis.get("_source_item", {})
        materiality = analysis.get("materiality_score", 0)
        confidence = analysis.get("confidence", 0.5)
        time_horizon = analysis.get("time_horizon", "days")

        for ticker_info in analysis.get("affected_tickers", []):
            symbol = ticker_info.get("symbol", "")
            if not symbol or symbol not in price_changes:
                continue

            expected_dir = ticker_info.get("expected_direction", "bullish")
            expected_mag = ticker_info.get("expected_magnitude", 1.0)
            order_type = ticker_info.get("order_type", "first_order")
            reasoning = ticker_info.get("reasoning", "")

            # Sign the expected magnitude
            signed_mag = expected_mag if expected_dir == "bullish" else -expected_mag

            prices = price_changes[symbol]
            actual_1d = prices["price_1d"]
            actual_3d = prices["price_3d"]

            # Use appropriate window based on time horizon
            actual_for_score = actual_1d if time_horizon == "immediate" else actual_3d

            d_score = _compute_displacement_score(
                materiality, signed_mag, actual_for_score, confidence
            )

            if d_score < MIN_DISPLACEMENT_SCORE:
                continue

            # Build narrative
            direction_word = "up" if expected_dir == "bullish" else "down"
            narrative = (
                f"{order_type.replace('_', ' ').title()}: Expected {symbol} {direction_word} "
                f"{abs(expected_mag):.1f}% but moved {actual_1d:+.1f}% (1d) / {actual_3d:+.1f}% (3d). "
                f"{reasoning}"
            )

            affected_json = json.dumps(
                [t.get("symbol") for t in analysis.get("affected_tickers", []) if t.get("symbol")]
            )

            rows_to_store.append((
                symbol, today,
                source_item.get("headline", "")[:500],
                source_item.get("source", ""),
                source_item.get("url", ""),
                materiality,
                expected_dir,
                expected_mag,
                actual_1d,
                actual_3d,
                d_score,
                time_horizon,
                order_type,
                affected_json,
                confidence,
                narrative,
            ))
            displacement_count += 1

    # Store results
    if rows_to_store:
        with get_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO news_displacement
                   (symbol, date, news_headline, news_source, news_url,
                    materiality_score, expected_direction, expected_magnitude,
                    actual_price_change_1d, actual_price_change_3d,
                    displacement_score, time_horizon, order_type,
                    affected_tickers, confidence, narrative)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows_to_store,
            )

    # Mark old signals as expired
    with get_conn() as conn:
        conn.execute("""
            UPDATE news_displacement SET status = 'expired'
            WHERE date < date('now', '-7 days') AND status = 'active'
        """)

    # Summary
    top = query("""
        SELECT symbol, displacement_score, order_type, narrative
        FROM news_displacement
        WHERE date = ? AND displacement_score >= ?
        ORDER BY displacement_score DESC LIMIT 10
    """, [today, MIN_DISPLACEMENT_SCORE])

    if top:
        print(f"\n  TOP DISPLACEMENT SIGNALS:")
        print(f"  {'Symbol':<8} {'Score':>6} {'Type':<14} Narrative")
        print(f"  {'-' * 70}")
        for r in top:
            narrative_short = (r["narrative"] or "")[:50]
            print(f"  {r['symbol']:<8} {r['displacement_score']:>6.0f} {r['order_type']:<14} {narrative_short}...")

    print(f"\n  Displacement detection complete: {displacement_count} signals stored")
    print("=" * 60)


if __name__ == "__main__":
    run()
