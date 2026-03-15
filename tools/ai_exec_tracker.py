"""AI Executive Investment Tracker — discovers exec personal investments via web search + LLM."""
import sys, json, re, time, logging
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import (SERPER_API_KEY, FIRECRAWL_API_KEY, GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    EDGAR_HEADERS, AI_EXEC_WATCHLIST, AI_EXEC_SERPER_QUERIES_PER_EXEC,
    AI_EXEC_MAX_URLS_PER_EXEC, AI_EXEC_FIRECRAWL_DELAY, AI_EXEC_GEMINI_DELAY,
    AI_EXEC_MIN_CONFIDENCE, AI_EXEC_MIN_SCORE_STORE, AI_EXEC_SM_BOOST_HIGH, AI_EXEC_SM_BOOST_MED,
    AI_EXEC_CONVERGENCE_BONUS, AI_EXEC_LOOKBACK_DAYS, AI_EXEC_SCAN_INTERVAL_DAYS)
from tools.db import init_db, upsert_many, query, get_conn

logger = logging.getLogger(__name__)
SERPER_URL = "https://google.serper.dev/search"
FIRECRAWL_URL = "https://api.firecrawl.dev/v1/scrape"
MAX_ARTICLE_CHARS = 6_000
ACTIVITY_WEIGHTS = {"personal_purchase": 25, "board_appointment": 22, "angel_investment": 20,
    "vc_investment": 18, "advisory_role": 12, "equity_grant": 10, "fund_raise": 8}

def _is_url_cached(url):
    rows = query("SELECT status FROM ai_exec_url_cache WHERE url = ?", [url])
    return bool(rows and rows[0]["status"] == "ok")

def _cache_url(url, status):
    upsert_many("ai_exec_url_cache", ["url", "scraped_at", "status"], [(url, date.today().isoformat(), status)])

def _serper_search(query_str, num_results=5):
    if not SERPER_API_KEY: return []
    try:
        resp = requests.post(SERPER_URL, headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query_str, "num": num_results}, timeout=15)
        resp.raise_for_status()
        return [{"title": i.get("title",""), "link": i.get("link",""), "snippet": i.get("snippet",""), "date": i.get("date","")} for i in resp.json().get("organic", [])]
    except Exception as e:
        print(f"  Warning: Serper search failed: {e}"); return []

def _firecrawl_scrape(url):
    if not FIRECRAWL_API_KEY: return None
    try:
        resp = requests.post(FIRECRAWL_URL, headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"]}, timeout=30)
        resp.raise_for_status(); data = resp.json()
        if data.get("success"):
            content = data.get("data", {}).get("markdown", "") or ""
            return "\n".join(l for l in content.split("\n") if len(l.split()) >= 3 or l.startswith("#"))[:MAX_ARTICLE_CHARS]
    except Exception: pass
    return None

def _classify_with_gemini(text, title, exec_name, exec_role, exec_org):
    if not GEMINI_API_KEY: return [], [], None
    prompt = f"""Financial analyst tracking AI exec investments.\nExec: {exec_name} ({exec_role} at {exec_org})\nTitle: {title}\nText:\n{text[:4000]}\n\nExtract PERSONAL investment/board activity as JSON:\n{{"activities": [{{"activity_type": "angel_investment"|"vc_investment"|"board_appointment"|"advisory_role"|"equity_grant"|"personal_purchase"|"fund_raise", "target_company": "name", "target_ticker": "ticker or null", "target_sector": "sector", "investment_amount": null, "funding_round": null, "is_public": bool, "ipo_expected": bool, "ipo_timeline": null, "date_reported": "YYYY-MM-DD or null", "confidence": 1-10, "summary": "one sentence"}}], "mentioned_public_tickers": [], "sector_signal": null}}\nOnly PERSONAL investments. Respond ONLY with valid JSON."""
    try:
        resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"}, params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024}}, timeout=30)
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        result = json.loads(raw)
        return result.get("activities", []), result.get("mentioned_public_tickers", []), result.get("sector_signal")
    except Exception as e:
        print(f"  Warning: Gemini classification failed: {e}"); return [], [], None

def _search_edgar_form_d(exec_name):
    try:
        resp = requests.get("https://efts.sec.gov/LATEST/search-index",
            params={"q": f'"{exec_name}"', "dateRange": "custom", "startdt": (date.today()-timedelta(days=90)).isoformat(),
                "enddt": date.today().isoformat(), "forms": "D"}, headers=EDGAR_HEADERS, timeout=15)
        if resp.status_code == 200:
            return [{"company": (h.get("_source",{}).get("display_names",[""])[0] if h.get("_source",{}).get("display_names") else h.get("_source",{}).get("entity_name","")),
                "filing_date": h.get("_source",{}).get("file_date",""), "form_type": h.get("_source",{}).get("form_type","")}
                for h in resp.json().get("hits",{}).get("hits",[])[:5]]
    except Exception: pass
    return []

def _search_exec_activity(exec_info):
    results = []
    for alias in exec_info.get("search_aliases", [exec_info["name"]])[:AI_EXEC_SERPER_QUERIES_PER_EXEC]:
        for r in _serper_search(alias, num_results=AI_EXEC_MAX_URLS_PER_EXEC):
            if r["link"] and not _is_url_cached(r["link"]): results.append(r)
    if len(results) < 2:
        for r in _serper_search(f'"{exec_info["name"]}" site:crunchbase.com OR site:pitchbook.com', 2):
            if r["link"] and not _is_url_cached(r["link"]): results.append(r)
    seen = set(); deduped = []
    for r in results:
        if r["link"] not in seen: seen.add(r["link"]); deduped.append(r)
    return deduped[:AI_EXEC_MAX_URLS_PER_EXEC]

def _scrape_and_classify(search_results, exec_info):
    all_activities, all_tickers, all_sectors = [], [], []
    for result in search_results:
        url = result["link"]
        text = _firecrawl_scrape(url)
        if text: _cache_url(url, "ok"); time.sleep(AI_EXEC_FIRECRAWL_DELAY)
        else: text = f"{result['title']}\n{result['snippet']}"; _cache_url(url, "snippet_only")
        activities, tickers, sector = _classify_with_gemini(text, result["title"], exec_info["name"], exec_info["role"], exec_info["org"])
        time.sleep(AI_EXEC_GEMINI_DELAY)
        for act in activities:
            act.update({"exec_name": exec_info["name"], "exec_org": exec_info["org"],
                "exec_prominence": exec_info["prominence"], "source_url": url, "source": result.get("title","")[:200]})
        all_activities.extend(activities); all_tickers.extend(tickers); all_sectors.append(sector)
    return all_activities, all_tickers, all_sectors

def _score_investment(act):
    score = act.get("exec_prominence", 50) * 0.30 + ACTIVITY_WEIGHTS.get(act.get("activity_type",""), 5)
    score *= max(0.3, act.get("confidence", 5) / 10)
    dr = act.get("date_reported")
    if dr:
        try: score += max(0, 15 * (1 - (date.today() - date.fromisoformat(dr)).days / 90))
        except (ValueError, TypeError): score += 5
    else: score += 5
    score += 10 if act.get("is_public") else (7 if act.get("ipo_expected") else 3)
    amt = act.get("investment_amount") or 0
    if amt >= 10_000_000: score += 10
    elif amt >= 1_000_000: score += 7
    elif amt >= 100_000: score += 4
    return max(0, min(100, score))

def _aggregate_signals(today, all_activities):
    scored = []
    for act in all_activities:
        if (act.get("confidence") or 0) < AI_EXEC_MIN_CONFIDENCE: continue
        act["raw_score"] = _score_investment(act)
        if act["raw_score"] >= AI_EXEC_MIN_SCORE_STORE: scored.append(act)
    if not scored: return 0
    inv_rows = [(a.get("exec_name"), a.get("exec_org"), a.get("exec_prominence"), a.get("activity_type","unknown"),
        a.get("target_company","unknown"), a.get("target_ticker"), a.get("target_sector"), a.get("investment_amount"),
        a.get("funding_round"), 1 if a.get("is_public") else 0, 1 if a.get("ipo_expected") else 0,
        a.get("ipo_timeline"), a.get("date_reported"), a.get("confidence"), a.get("summary"),
        a.get("source_url"), a.get("source"), a.get("raw_score"), today) for a in scored]
    upsert_many("ai_exec_investments", ["exec_name","exec_org","exec_prominence","activity_type","target_company",
        "target_ticker","target_sector","investment_amount","funding_round","is_public","ipo_expected",
        "ipo_timeline","date_reported","confidence","summary","source_url","source","raw_score","scan_date"], inv_rows)
    ticker_map = defaultdict(list)
    for act in scored:
        t = act.get("target_ticker")
        if t: ticker_map[t.upper()].append(act)
    universe = {r["symbol"] for r in query("SELECT symbol FROM stock_universe")}
    signal_rows = []
    for ticker, acts in ticker_map.items():
        if ticker not in universe: continue
        best = max(acts, key=lambda a: a["raw_score"]); score = best["raw_score"]
        exec_names = list({a["exec_name"] for a in acts})
        if len(exec_names) >= 2: score = min(100, score + AI_EXEC_CONVERGENCE_BONUS)
        narr = " | ".join(f"{a['exec_name']} ({a['exec_org']}): {a.get('activity_type','?')}" for a in acts)[:500]
        signal_rows.append((ticker, today, round(score, 1), len(exec_names), exec_names[0] if exec_names else None,
            best.get("activity_type"), best.get("target_sector"), narr))
    if signal_rows:
        upsert_many("ai_exec_signals", ["symbol","date","ai_exec_score","exec_count","top_exec",
            "top_activity","sector_signal","narrative"], signal_rows)
    return len(signal_rows)

def _boost_smart_money(today):
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    exec_rows = query("SELECT symbol, MAX(ai_exec_score) as ai_exec_score FROM ai_exec_signals WHERE date >= ? GROUP BY symbol", [cutoff])
    if not exec_rows: return 0
    sm_map = {r["symbol"]: r for r in query("SELECT s.symbol, s.date, s.conviction_score FROM smart_money_scores s INNER JOIN (SELECT symbol, MAX(date) as mx FROM smart_money_scores GROUP BY symbol) m ON s.symbol = m.symbol AND s.date = m.mx")}
    updates = 0
    with get_conn() as conn:
        for row in exec_rows:
            sym, escore = row["symbol"], row["ai_exec_score"]
            boost = AI_EXEC_SM_BOOST_HIGH if escore >= 70 else AI_EXEC_SM_BOOST_MED if escore >= 50 else None
            if boost is None: continue
            if sym not in sm_map:
                conn.execute("INSERT OR REPLACE INTO smart_money_scores (symbol, date, manager_count, conviction_score, top_holders) VALUES (?, ?, 0, ?, '[]')", [sym, today, min(100, escore * 0.5)])
                updates += 1; continue
            sm = sm_map[sym]; new_score = max(0, min(100, (sm["conviction_score"] or 0) + boost))
            if new_score != (sm["conviction_score"] or 0):
                conn.execute("UPDATE smart_money_scores SET conviction_score = ? WHERE symbol = ? AND date = ?", [new_score, sym, sm["date"]])
                updates += 1
    return updates

def run():
    init_db(); today = date.today().isoformat()
    print("AI Exec Tracker: Scanning executive investment activity...")
    last_scan = query("SELECT MAX(scan_date) as last_scan FROM ai_exec_investments")
    needs_full = True
    if last_scan and last_scan[0]["last_scan"]:
        days_since = (date.today() - date.fromisoformat(last_scan[0]["last_scan"])).days
        if days_since < AI_EXEC_SCAN_INTERVAL_DAYS:
            print(f"  Last scan {days_since}d ago, skipping full scan"); needs_full = False
    if needs_full:
        all_activities, total_urls = [], 0
        for ei in AI_EXEC_WATCHLIST:
            print(f"\n  [{ei['name']}] ({ei['role']} @ {ei['org']})")
            sr = _search_exec_activity(ei)
            if not sr: print(f"    No new URLs"); continue
            print(f"    Found {len(sr)} new URLs"); total_urls += len(sr)
            activities, _, _ = _scrape_and_classify(sr, ei)
            if activities: print(f"    Extracted {len(activities)} activities")
            all_activities.extend(activities)
            for hit in _search_edgar_form_d(ei["name"]):
                all_activities.append({"activity_type": "fund_raise", "target_company": hit["company"], "target_ticker": None,
                    "target_sector": None, "investment_amount": None, "funding_round": None, "is_public": False,
                    "ipo_expected": False, "ipo_timeline": None, "date_reported": hit["filing_date"], "confidence": 6,
                    "summary": f"SEC Form D: {hit['company']}", "exec_name": ei["name"], "exec_org": ei["org"],
                    "exec_prominence": ei["prominence"], "source_url": "", "source": f"EDGAR Form D: {hit['company']}"})
            time.sleep(0.15)
        print(f"\n  Total: {total_urls} URLs, {len(all_activities)} activities")
        print(f"  Stored {_aggregate_signals(today, all_activities)} universe-mapped signals")
    boost_count = _boost_smart_money(today)
    print(f"  Smart money boosts: {boost_count}")
    cutoff = (date.today() - timedelta(days=AI_EXEC_LOOKBACK_DAYS)).isoformat()
    rows = query("SELECT exec_name, target_sector FROM ai_exec_investments WHERE scan_date >= ? AND confidence >= ? AND target_sector IS NOT NULL", [cutoff, AI_EXEC_MIN_CONFIDENCE])
    sector_execs = defaultdict(set)
    for r in rows: sector_execs[r["target_sector"]].add(r["exec_name"])
    for sector, execs in sector_execs.items():
        if len(execs) >= 3: print(f"  Sector tilt: {sector} — {len(execs)} execs investing")
    print("AI Exec Tracker: Done.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
