"""Earnings Call NLP — sentiment analysis of 8-K filings from SEC EDGAR.
Fetches recent 8-K filings, extracts text, runs VADER + financial lexicon, produces 0-100 score."""
import json, re, ssl, time
from datetime import date, timedelta
import requests
from bs4 import BeautifulSoup
from tools.db import init_db, query, upsert_many

EDGAR_HEADERS = {"User-Agent": "DruckenmillerAlpha/1.0 research@example.com"}
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
REQUEST_DELAY, MAX_FILINGS, LOOKBACK_DAYS = 0.15, 200, 30
HEDGING_WORDS = ["uncertain", "challenging", "headwinds", "volatile", "cautious", "difficult", "risk", "weakness", "pressure", "concern", "worried", "downturn", "slowdown", "deteriorating"]
CONFIDENCE_WORDS = ["confident", "strong", "momentum", "robust", "accelerating", "visibility", "optimistic", "outperform", "record", "exceptional", "exceeded", "beat", "upside", "tailwind"]
GUIDANCE_WORDS = ["guidance", "outlook", "expect", "forecast", "anticipate", "project", "target", "reiterate", "raise", "lower", "withdraw"]

def _get_vader():
    from nltk.sentiment.vader import SentimentIntensityAnalyzer
    try: return SentimentIntensityAnalyzer()
    except LookupError: pass
    try:
        import nltk; nltk.download("vader_lexicon", quiet=True); return SentimentIntensityAnalyzer()
    except Exception: pass
    try:
        import nltk
        _ctx = ssl.create_default_context(); _ctx.check_hostname = False; _ctx.verify_mode = ssl.CERT_NONE
        old = getattr(ssl, "_create_default_https_context", None)
        ssl._create_default_https_context = lambda: _ctx
        try: nltk.download("vader_lexicon", quiet=True)
        finally:
            if old is not None: ssl._create_default_https_context = old
        return SentimentIntensityAnalyzer()
    except Exception as e: print(f"  WARNING: Could not load VADER: {e}"); return None

def _fetch_cik_to_ticker():
    try:
        resp = requests.get(EDGAR_TICKERS_URL, headers=EDGAR_HEADERS, timeout=15); resp.raise_for_status()
        return {int(e["cik_str"]): e["ticker"].upper() for e in resp.json().values()}
    except Exception as e: print(f"  WARNING: Could not fetch CIK-ticker map: {e}"); return {}

def _fetch_recent_filings(start_date, end_date):
    try:
        resp = requests.get(EDGAR_SEARCH_URL, params={"q": '"earnings"', "forms": "8-K", "dateRange": "custom", "startdt": start_date, "enddt": end_date}, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status(); return resp.json().get("hits", {}).get("hits", [])
    except Exception as e: print(f"  WARNING: EDGAR search failed: {e}"); return []

def _extract_text_from_filing(url):
    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=20); resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style"]): tag.decompose()
        return re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))
    except Exception as e: print(f"    Could not extract filing text: {e}"); return None

def _analyze_text(text, vader):
    words = text.lower().split()
    if not words: return None
    total = len(words)
    vader_compound = 0.0
    if vader is not None:
        chunks = [text[i:i+5000] for i in range(0, min(len(text), 50000), 5000)]
        compounds = [vader.polarity_scores(c)["compound"] for c in chunks]
        vader_compound = sum(compounds) / len(compounds) if compounds else 0.0
    hc = sum(1 for w in words if w in HEDGING_WORDS)
    cc = sum(1 for w in words if w in CONFIDENCE_WORDS)
    gc = sum(1 for w in words if w in GUIDANCE_WORDS)
    return {"word_count": total, "vader_compound": round(vader_compound, 4),
        "hedging_count": hc, "confidence_count": cc, "guidance_count": gc,
        "hedging_ratio": round(hc / total, 6), "confidence_ratio": round(cc / total, 6),
        "guidance_score": round(min(100, gc / total * 10000), 2)}

def _compute_score(metrics, sentiment_delta=None, hedging_delta=None):
    s = (metrics["vader_compound"] + 1) * 25  # 0-50
    s += max(0, 25 - (metrics["hedging_ratio"] * 5000))  # hedging penalty
    s += min(25, metrics["confidence_ratio"] * 5000)  # confidence boost
    if sentiment_delta is not None: s += max(-10, min(10, sentiment_delta * 20))
    return round(max(0, min(100, s)), 2)

def _get_filing_url(hit):
    src = hit.get("_source", {})
    acc = src.get("accession_no", "")
    if not acc: return None
    primary_doc = src.get("primary_doc", "")
    entity_id = src.get("entity_id", "")
    if primary_doc: return f"https://www.sec.gov/Archives/edgar/data/{entity_id}/{acc.replace('-', '')}/{primary_doc}"
    if entity_id: return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={entity_id}&type=8-K&dateb=&owner=include&count=1"
    return None

def _infer_quarter(filing_date_str):
    try:
        parts = filing_date_str.split("-"); return f"{parts[0]}Q{(int(parts[1]) - 1) // 3 + 1}"
    except Exception: return f"{date.today().year}Q{(date.today().month - 1) // 3 + 1}"

def run(gated_symbols=None):
    init_db()
    print("=" * 60 + "\nEARNINGS NLP — Sentiment Analysis of 8-K Filings\n" + "=" * 60)
    universe = {r["symbol"] for r in query("SELECT symbol FROM stock_universe")}
    if gated_symbols: universe = universe & set(gated_symbols)
    if not universe: print("  No symbols. Skipping."); return
    print(f"  Universe: {len(universe)} symbols\n  Fetching CIK-to-ticker mapping...")
    cik_to_ticker = _fetch_cik_to_ticker()
    if not cik_to_ticker: print("  Could not load ticker mapping. Aborting."); return
    print(f"  Loaded {len(cik_to_ticker)} CIK mappings"); time.sleep(REQUEST_DELAY)
    vader = _get_vader()
    if vader is None: print("  WARNING: VADER unavailable; sentiment scores will be 0.")
    end_dt = date.today().isoformat()
    start_dt = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    print(f"  Searching EDGAR for 8-K filings ({start_dt} to {end_dt})...")
    hits = _fetch_recent_filings(start_dt, end_dt)
    print(f"  Found {len(hits)} filing hits")
    if not hits: print("  No filings found."); return
    filings, seen = [], set()
    for hit in hits:
        src = hit.get("_source", {})
        eid = src.get("entity_id")
        if eid is None: continue
        try: cik = int(eid)
        except (ValueError, TypeError): continue
        ticker = cik_to_ticker.get(cik)
        if ticker is None or ticker not in universe or ticker in seen: continue
        seen.add(ticker)
        url = _get_filing_url(hit)
        if url: filings.append({"symbol": ticker, "filing_url": url, "filing_date": src.get("file_date", date.today().isoformat())})
        if len(filings) >= MAX_FILINGS: break
    print(f"  Matched {len(filings)} filings to universe")
    if not filings: print("  No matching filings."); return
    prior_data = {}
    try:
        for r in query("SELECT symbol, sentiment, hedging_ratio FROM earnings_transcripts"):
            if r["symbol"] not in prior_data: prior_data[r["symbol"]] = r
    except Exception: pass
    transcript_rows, score_rows, processed, errors = [], [], 0, 0
    for f in filings:
        sym, url, fdate = f["symbol"], f["filing_url"], f["filing_date"]
        quarter = _infer_quarter(fdate)
        print(f"  [{processed + 1}/{len(filings)}] {sym} ({quarter})...", end="")
        text = _extract_text_from_filing(url)
        if not text or len(text) < 200: print(" skipped (too short)"); errors += 1; continue
        metrics = _analyze_text(text, vader)
        if metrics is None: print(" skipped (analysis failed)"); errors += 1; continue
        sd, hd = None, None
        prior = prior_data.get(sym)
        if prior and prior.get("sentiment") is not None:
            sd = metrics["vader_compound"] - prior["sentiment"]
            if prior.get("hedging_ratio") is not None: hd = metrics["hedging_ratio"] - prior["hedging_ratio"]
        score = _compute_score(metrics, sd, hd)
        print(f" score={score:.1f}, sentiment={metrics['vader_compound']:+.3f}")
        today_str = date.today().isoformat()
        kp = json.dumps({"hedging_count": metrics["hedging_count"], "confidence_count": metrics["confidence_count"], "guidance_count": metrics["guidance_count"]})
        transcript_rows.append((sym, today_str, quarter, url, metrics["word_count"], metrics["vader_compound"], metrics["hedging_ratio"], metrics["confidence_ratio"], kp))
        details = json.dumps({"vader_compound": metrics["vader_compound"], "hedging_ratio": metrics["hedging_ratio"], "confidence_ratio": metrics["confidence_ratio"], "word_count": metrics["word_count"], "guidance_score": metrics["guidance_score"]})
        score_rows.append((sym, today_str, score, round(sd, 4) if sd is not None else None, round(hd, 6) if hd is not None else None, metrics["guidance_score"], details))
        processed += 1
    if transcript_rows:
        upsert_many("earnings_transcripts", ["symbol", "date", "quarter", "filing_url", "word_count", "sentiment", "hedging_ratio", "confidence_ratio", "key_phrases"], transcript_rows)
    if score_rows:
        upsert_many("earnings_nlp_scores", ["symbol", "date", "earnings_nlp_score", "sentiment_delta", "hedging_delta", "guidance_score", "details"], score_rows)
    print(f"\n  Processed: {processed} | Errors: {errors} | Stored: {len(score_rows)} scores\n  Earnings NLP complete.")
    return {"processed": processed, "scored": len(score_rows), "errors": errors}

if __name__ == "__main__":
    run()
