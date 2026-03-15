"""News Displacement Detection — finds material news the market hasn't priced in.
When significant news drops and the affected asset doesn't move, that's a displacement opportunity."""
import sys, json, re, time
from datetime import date, datetime, timedelta
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests, finnhub
from tools.config import FINNHUB_API_KEY, GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL
from tools.db import init_db, get_conn, query

MIN_DISPLACEMENT_SCORE = 30
NEWS_LOOKBACK_DAYS, GEMINI_BATCH_SIZE = 3, 8
FINNHUB_DELAY, GEMINI_DELAY = 0.15, 1.5

def _fetch_company_news(client, symbols: list[str]) -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    lookback = (datetime.now() - timedelta(days=NEWS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    all_news, seen_urls = [], set()
    for i, symbol in enumerate(symbols):
        try:
            articles = client.company_news(symbol, _from=lookback, to=today)
            if not articles: continue
            for article in articles[:3]:
                url = article.get("url", "")
                if url in seen_urls or not url: continue
                seen_urls.add(url)
                all_news.append({"symbol": symbol, "headline": article.get("headline", ""),
                    "source": article.get("source", ""), "url": url,
                    "datetime": article.get("datetime", 0), "summary": article.get("summary", "")[:300]})
        except Exception: pass
        if (i + 1) % 30 == 0: print(f"    News fetch: {i + 1}/{len(symbols)}"); time.sleep(FINNHUB_DELAY * 3)
        elif (i + 1) % 5 == 0: time.sleep(FINNHUB_DELAY)
    return all_news

def _pull_recent_signals() -> list[dict]:
    signals = []
    for r in query("SELECT symbol, title, source, url, article_summary FROM research_signals WHERE date >= date('now', '-3 days') AND relevance_score >= 60 ORDER BY relevance_score DESC LIMIT 30"):
        signals.append({"headline": r["title"] or "", "source": f"research:{r['source']}", "url": r["url"], "summary": r["article_summary"] or "", "symbol": r["symbol"]})
    for r in query("SELECT symbol, title_translated, source, url, article_summary FROM foreign_intel_signals WHERE date >= date('now', '-3 days') AND relevance_score >= 60 AND symbol != 'UNMAPPED' ORDER BY relevance_score DESC LIMIT 20"):
        signals.append({"headline": r["title_translated"] or "", "source": f"foreign:{r['source']}", "url": r["url"], "summary": r["article_summary"] or "", "symbol": r["symbol"]})
    return signals

def _get_price_changes(symbols: list[str]) -> dict[str, dict]:
    changes = {}
    for symbol in symbols:
        rows = query("SELECT date, close FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 5", [symbol])
        if len(rows) < 2: continue
        curr = rows[0]["close"]
        p1 = rows[1]["close"] if len(rows) >= 2 else curr
        p3 = rows[3]["close"] if len(rows) >= 4 else rows[-1]["close"]
        changes[symbol] = {"current": curr, "price_1d": ((curr - p1) / p1 * 100) if p1 else 0, "price_3d": ((curr - p3) / p3 * 100) if p3 else 0}
    return changes

def _analyze_news_batch(news_items: list[dict], universe_symbols: list[str]) -> list[dict]:
    if not GEMINI_API_KEY or not news_items: return []
    news_digest = ""
    for i, item in enumerate(news_items):
        news_digest += f"\n[{i+1}] ({item.get('source', 'unknown')}) {item['headline']}\n"
        if item.get("summary"): news_digest += f"    {item['summary'][:200]}\n"
    prompt = f"""You are a senior macro trader. Analyze these news items for DISPLACEMENT opportunities — material events that should move specific assets but may not be priced in.
NEWS ITEMS:{news_digest}
STOCK UNIVERSE (subset): {', '.join(universe_symbols[:200])}
For each INVESTMENT-MATERIAL item, output:
{{"news_index": <1-based>, "affected_tickers": [{{"symbol": "<ticker>", "expected_direction": "bullish"/"bearish", "expected_magnitude": <% move>, "order_type": "first_order"/"second_order"/"cross_asset", "reasoning": "<1 sentence>"}}], "materiality_score": <0-100>, "time_horizon": "immediate"/"days"/"weeks", "confidence": <0.0-1.0>}}
RULES: Only genuinely material news. Be specific on magnitude. Skip noise. Return JSON array only."""
    try:
        resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"}, params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048}}, timeout=45)
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        analyses = json.loads(raw)
        return analyses if isinstance(analyses, list) else [analyses]
    except Exception as e:
        print(f"  Warning: Gemini analysis failed: {e}"); return []

def _compute_displacement_score(materiality, expected_mag, actual_change, confidence):
    if expected_mag <= 0: return 0.0
    actual_abs = abs(actual_change)
    if actual_change * (1 if expected_mag > 0 else -1) < 0:
        response_gap = 1.0 + (actual_abs / abs(expected_mag))
    else:
        response_gap = max(0, 1.0 - (actual_abs / abs(expected_mag)))
    return max(0, min(100, materiality * response_gap * confidence))

def run(symbols=None):
    init_db(); today = date.today().isoformat()
    print("\n" + "=" * 60 + "\n  NEWS DISPLACEMENT DETECTION\n" + "=" * 60)
    if not FINNHUB_API_KEY: print("  ERROR: FINNHUB_API_KEY not set"); return
    if not GEMINI_API_KEY: print("  ERROR: GEMINI_API_KEY not set"); return
    if symbols is None:
        symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe ORDER BY market_cap DESC LIMIT 500")]
    if not symbols: print("  No stocks in universe."); return
    print(f"  Fetching news for {len(symbols)} symbols...")
    client = finnhub.Client(api_key=FINNHUB_API_KEY)
    news_items = _fetch_company_news(client, symbols)
    print(f"  Collected {len(news_items)} news items")
    db_signals = _pull_recent_signals()
    print(f"  Pulled {len(db_signals)} existing intelligence signals")
    all_items = news_items + db_signals
    if not all_items: print("  No news items to analyze."); return
    print(f"  Analyzing {len(all_items)} items in batches of {GEMINI_BATCH_SIZE}...")
    all_analyses = []
    for bs in range(0, len(all_items), GEMINI_BATCH_SIZE):
        batch = all_items[bs:bs + GEMINI_BATCH_SIZE]
        bn = bs // GEMINI_BATCH_SIZE + 1
        tb = (len(all_items) + GEMINI_BATCH_SIZE - 1) // GEMINI_BATCH_SIZE
        print(f"    Batch {bn}/{tb}...")
        analyses = _analyze_news_batch(batch, symbols)
        for a in analyses:
            idx = a.get("news_index", 0) - 1
            if 0 <= idx < len(batch): a["_source_item"] = batch[idx]
            all_analyses.append(a)
        if bs + GEMINI_BATCH_SIZE < len(all_items): time.sleep(GEMINI_DELAY)
    print(f"  Got {len(all_analyses)} material analyses from Gemini")
    affected_symbols = set()
    for a in all_analyses:
        for t in a.get("affected_tickers", []):
            if t.get("symbol"): affected_symbols.add(t["symbol"])
    price_changes = _get_price_changes(list(affected_symbols))
    print(f"  Price data for {len(price_changes)} affected symbols")
    rows_to_store, displacement_count = [], 0
    for analysis in all_analyses:
        src = analysis.get("_source_item", {})
        materiality, confidence = analysis.get("materiality_score", 0), analysis.get("confidence", 0.5)
        time_horizon = analysis.get("time_horizon", "days")
        for ti in analysis.get("affected_tickers", []):
            sym = ti.get("symbol", "")
            if not sym or sym not in price_changes: continue
            exp_dir, exp_mag = ti.get("expected_direction", "bullish"), ti.get("expected_magnitude", 1.0)
            order_type, reasoning = ti.get("order_type", "first_order"), ti.get("reasoning", "")
            signed_mag = exp_mag if exp_dir == "bullish" else -exp_mag
            prices = price_changes[sym]
            a1d, a3d = prices["price_1d"], prices["price_3d"]
            actual = a1d if time_horizon == "immediate" else a3d
            d_score = _compute_displacement_score(materiality, signed_mag, actual, confidence)
            if d_score < MIN_DISPLACEMENT_SCORE: continue
            dw = "up" if exp_dir == "bullish" else "down"
            narrative = f"{order_type.replace('_', ' ').title()}: Expected {sym} {dw} {abs(exp_mag):.1f}% but moved {a1d:+.1f}% (1d) / {a3d:+.1f}% (3d). {reasoning}"
            affected_json = json.dumps([t.get("symbol") for t in analysis.get("affected_tickers", []) if t.get("symbol")])
            rows_to_store.append((sym, today, src.get("headline", "")[:500], src.get("source", ""), src.get("url", ""),
                materiality, exp_dir, exp_mag, a1d, a3d, d_score, time_horizon, order_type, affected_json, confidence, narrative))
            displacement_count += 1
    if rows_to_store:
        with get_conn() as conn:
            conn.executemany("INSERT OR REPLACE INTO news_displacement (symbol, date, news_headline, news_source, news_url, materiality_score, expected_direction, expected_magnitude, actual_price_change_1d, actual_price_change_3d, displacement_score, time_horizon, order_type, affected_tickers, confidence, narrative) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows_to_store)
    with get_conn() as conn:
        conn.execute("UPDATE news_displacement SET status = 'expired' WHERE date < date('now', '-7 days') AND status = 'active'")
    top = query("SELECT symbol, displacement_score, order_type, narrative FROM news_displacement WHERE date = ? AND displacement_score >= ? ORDER BY displacement_score DESC LIMIT 10", [today, MIN_DISPLACEMENT_SCORE])
    if top:
        print(f"\n  TOP DISPLACEMENT SIGNALS:")
        print(f"  {'Symbol':<8} {'Score':>6} {'Type':<14} Narrative\n  {'-' * 70}")
        for r in top: print(f"  {r['symbol']:<8} {r['displacement_score']:>6.0f} {r['order_type']:<14} {(r['narrative'] or '')[:50]}...")
    print(f"\n  Displacement detection complete: {displacement_count} signals stored\n" + "=" * 60)

if __name__ == "__main__":
    run()
