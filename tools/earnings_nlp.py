"""Earnings Call NLP — sentiment analysis of 8-K filings from SEC EDGAR.

Fetches recent 8-K filings, extracts transcript text, runs VADER sentiment
plus custom financial lexicon analysis, and produces a 0-100 score per symbol.
"""

import json
import re
import ssl
import time
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from tools.db import init_db, query, upsert_many

# ── EDGAR request config ──
EDGAR_HEADERS = {"User-Agent": "DruckenmillerAlpha/1.0 research@example.com"}
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
REQUEST_DELAY = 0.15  # seconds between EDGAR requests
MAX_FILINGS = 200     # cap per run to stay within time budget
LOOKBACK_DAYS = 30

# ── Financial lexicon ──
HEDGING_WORDS = [
    "uncertain", "challenging", "headwinds", "volatile", "cautious",
    "difficult", "risk", "weakness", "pressure", "concern",
    "worried", "downturn", "slowdown", "deteriorating",
]
CONFIDENCE_WORDS = [
    "confident", "strong", "momentum", "robust", "accelerating",
    "visibility", "optimistic", "outperform", "record", "exceptional",
    "exceeded", "beat", "upside", "tailwind",
]
GUIDANCE_WORDS = [
    "guidance", "outlook", "expect", "forecast", "anticipate",
    "project", "target", "reiterate", "raise", "lower", "withdraw",
]


def _get_vader():
    """Return a VADER SentimentIntensityAnalyzer, handling NLTK data download."""
    from nltk.sentiment.vader import SentimentIntensityAnalyzer

    try:
        return SentimentIntensityAnalyzer()
    except LookupError:
        pass

    # Try downloading with SSL workaround
    try:
        import nltk
        nltk.download("vader_lexicon", quiet=True)
        return SentimentIntensityAnalyzer()
    except Exception:
        pass

    # Last resort: disable SSL verification for download
    try:
        import nltk
        _ctx = ssl.create_default_context()
        _ctx.check_hostname = False
        _ctx.verify_mode = ssl.CERT_NONE
        old = getattr(ssl, "_create_default_https_context", None)
        ssl._create_default_https_context = lambda: _ctx
        try:
            nltk.download("vader_lexicon", quiet=True)
        finally:
            if old is not None:
                ssl._create_default_https_context = old
        return SentimentIntensityAnalyzer()
    except Exception as e:
        print(f"  WARNING: Could not load VADER: {e}")
        return None


def _fetch_cik_to_ticker():
    """Fetch SEC company_tickers.json and return {cik_int: ticker} mapping."""
    try:
        resp = requests.get(EDGAR_TICKERS_URL, headers=EDGAR_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        mapping = {}
        for entry in data.values():
            cik = int(entry["cik_str"])
            ticker = entry["ticker"].upper()
            mapping[cik] = ticker
        return mapping
    except Exception as e:
        print(f"  WARNING: Could not fetch CIK-ticker map: {e}")
        return {}


def _fetch_recent_filings(start_date, end_date):
    """Search EDGAR EFTS for recent 8-K filings mentioning earnings."""
    params = {
        "q": '"earnings"',
        "forms": "8-K",
        "dateRange": "custom",
        "startdt": start_date,
        "enddt": end_date,
    }
    try:
        resp = requests.get(
            EDGAR_SEARCH_URL, params=params,
            headers=EDGAR_HEADERS, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        return hits
    except Exception as e:
        print(f"  WARNING: EDGAR search failed: {e}")
        return []


def _extract_text_from_filing(filing_url):
    """Fetch an EDGAR filing HTML page and extract plain text."""
    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(filing_url, headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove script/style elements
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text
    except Exception as e:
        print(f"    Could not extract filing text: {e}")
        return None


def _analyze_text(text, vader):
    """Run VADER + financial lexicon analysis on text. Returns dict of metrics."""
    words = text.lower().split()
    total_words = len(words)
    if total_words == 0:
        return None

    # VADER sentiment
    vader_compound = 0.0
    if vader is not None:
        # VADER on full text can be slow; sample chunks
        chunks = [text[i:i+5000] for i in range(0, min(len(text), 50000), 5000)]
        compounds = [vader.polarity_scores(c)["compound"] for c in chunks]
        vader_compound = sum(compounds) / len(compounds) if compounds else 0.0

    # Lexicon counts
    hedging_count = sum(1 for w in words if w in HEDGING_WORDS)
    confidence_count = sum(1 for w in words if w in CONFIDENCE_WORDS)
    guidance_count = sum(1 for w in words if w in GUIDANCE_WORDS)

    hedging_ratio = hedging_count / total_words
    confidence_ratio = confidence_count / total_words

    # Guidance score: simple ratio scaled 0-100
    guidance_ratio = guidance_count / total_words
    guidance_score = min(100, guidance_ratio * 10000)

    return {
        "word_count": total_words,
        "vader_compound": round(vader_compound, 4),
        "hedging_count": hedging_count,
        "confidence_count": confidence_count,
        "guidance_count": guidance_count,
        "hedging_ratio": round(hedging_ratio, 6),
        "confidence_ratio": round(confidence_ratio, 6),
        "guidance_score": round(guidance_score, 2),
    }


def _compute_score(metrics, sentiment_delta=None, hedging_delta=None):
    """Compute earnings_nlp_score (0-100) from analysis metrics."""
    vader_compound = metrics["vader_compound"]
    hedging_ratio = metrics["hedging_ratio"]
    confidence_ratio = metrics["confidence_ratio"]

    # Base score from sentiment (VADER compound -1 to +1, map to 0-50)
    sentiment_component = (vader_compound + 1) * 25  # 0-50

    # Hedging penalty (0-25, higher hedging = lower score)
    hedging_component = max(0, 25 - (hedging_ratio * 5000))

    # Confidence boost (0-25)
    confidence_component = min(25, confidence_ratio * 5000)

    # Delta bonus if we have prior quarter data (-10 to +10)
    delta_bonus = 0.0
    if sentiment_delta is not None:
        delta_bonus = max(-10, min(10, sentiment_delta * 20))

    score = sentiment_component + hedging_component + confidence_component + delta_bonus
    return round(max(0, min(100, score)), 2)


def _get_filing_url(hit):
    """Extract the primary filing document URL from an EFTS search hit."""
    source = hit.get("_source", {})
    # Build URL from accession number and primary document
    file_num = source.get("file_num", "")
    accession = source.get("accession_no", "")
    if not accession:
        return None
    # Normalize accession number (remove dashes for URL path)
    acc_nodash = accession.replace("-", "")
    # The primary document filename
    primary_doc = source.get("primary_doc", "")
    if primary_doc:
        url = f"https://www.sec.gov/Archives/edgar/data/{source.get('entity_id', '')}/{acc_nodash}/{primary_doc}"
        return url
    # Fallback: filing index page
    entity_id = source.get("entity_id", "")
    if entity_id:
        return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={entity_id}&type=8-K&dateb=&owner=include&count=1"
    return None


def _infer_quarter(filing_date_str):
    """Infer fiscal quarter from filing date string (YYYY-MM-DD)."""
    try:
        parts = filing_date_str.split("-")
        year = parts[0]
        month = int(parts[1])
        q = (month - 1) // 3 + 1
        return f"{year}Q{q}"
    except Exception:
        return f"{date.today().year}Q{(date.today().month - 1) // 3 + 1}"


def run(gated_symbols=None):
    """Main entry point: fetch 8-K filings, analyze text, store scores."""
    init_db()
    print("=" * 60)
    print("EARNINGS NLP — Sentiment Analysis of 8-K Filings")
    print("=" * 60)

    # Load stock universe
    universe_rows = query("SELECT symbol FROM stock_universe")
    universe = {r["symbol"] for r in universe_rows}
    if gated_symbols:
        universe = universe & set(gated_symbols)
    if not universe:
        print("  No symbols in stock_universe. Skipping.")
        return

    print(f"  Universe: {len(universe)} symbols")

    # Fetch CIK -> ticker mapping
    print("  Fetching CIK-to-ticker mapping...")
    cik_to_ticker = _fetch_cik_to_ticker()
    if not cik_to_ticker:
        print("  Could not load ticker mapping. Aborting.")
        return
    print(f"  Loaded {len(cik_to_ticker)} CIK mappings")
    time.sleep(REQUEST_DELAY)

    # Initialize VADER
    vader = _get_vader()
    if vader is None:
        print("  WARNING: VADER unavailable; sentiment scores will be 0.")

    # Fetch recent 8-K filings
    end_dt = date.today().isoformat()
    start_dt = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    print(f"  Searching EDGAR for 8-K filings ({start_dt} to {end_dt})...")
    hits = _fetch_recent_filings(start_dt, end_dt)
    print(f"  Found {len(hits)} filing hits")

    if not hits:
        print("  No filings found. Done.")
        return

    # Filter to our universe and deduplicate by symbol
    filings_to_process = []
    seen_symbols = set()
    for hit in hits:
        source = hit.get("_source", {})
        entity_id = source.get("entity_id")
        if entity_id is None:
            continue
        try:
            cik = int(entity_id)
        except (ValueError, TypeError):
            continue
        ticker = cik_to_ticker.get(cik)
        if ticker is None or ticker not in universe:
            continue
        if ticker in seen_symbols:
            continue  # one filing per symbol per run
        seen_symbols.add(ticker)
        filing_url = _get_filing_url(hit)
        filing_date = source.get("file_date", date.today().isoformat())
        if filing_url:
            filings_to_process.append({
                "symbol": ticker,
                "filing_url": filing_url,
                "filing_date": filing_date,
            })
        if len(filings_to_process) >= MAX_FILINGS:
            break

    print(f"  Matched {len(filings_to_process)} filings to universe symbols")

    if not filings_to_process:
        print("  No matching filings. Done.")
        return

    # Fetch prior quarter data for delta computation
    prior_data = {}
    try:
        prior_rows = query(
            "SELECT symbol, sentiment, hedging_ratio FROM earnings_transcripts"
        )
        for r in prior_rows:
            sym = r["symbol"]
            if sym not in prior_data:
                prior_data[sym] = r
    except Exception:
        pass  # table may not exist yet

    # Process each filing
    transcript_rows = []
    score_rows = []
    processed = 0
    errors = 0

    for filing in filings_to_process:
        symbol = filing["symbol"]
        filing_url = filing["filing_url"]
        filing_date = filing["filing_date"]
        quarter = _infer_quarter(filing_date)

        print(f"  [{processed + 1}/{len(filings_to_process)}] {symbol} ({quarter})...", end="")

        text = _extract_text_from_filing(filing_url)
        if not text or len(text) < 200:
            print(" skipped (too short)")
            errors += 1
            continue

        metrics = _analyze_text(text, vader)
        if metrics is None:
            print(" skipped (analysis failed)")
            errors += 1
            continue

        # Compute deltas from prior quarter
        sentiment_delta = None
        hedging_delta = None
        prior = prior_data.get(symbol)
        if prior and prior.get("sentiment") is not None:
            sentiment_delta = metrics["vader_compound"] - prior["sentiment"]
            if prior.get("hedging_ratio") is not None:
                hedging_delta = metrics["hedging_ratio"] - prior["hedging_ratio"]

        # Compute final score
        score = _compute_score(metrics, sentiment_delta, hedging_delta)
        print(f" score={score:.1f}, sentiment={metrics['vader_compound']:+.3f}")

        today_str = date.today().isoformat()

        # Build key phrases summary
        key_phrases = json.dumps({
            "hedging_count": metrics["hedging_count"],
            "confidence_count": metrics["confidence_count"],
            "guidance_count": metrics["guidance_count"],
        })

        # Transcript row
        transcript_rows.append((
            symbol,
            today_str,
            quarter,
            filing_url,
            metrics["word_count"],
            metrics["vader_compound"],
            metrics["hedging_ratio"],
            metrics["confidence_ratio"],
            key_phrases,
        ))

        # Score row
        details = json.dumps({
            "vader_compound": metrics["vader_compound"],
            "hedging_ratio": metrics["hedging_ratio"],
            "confidence_ratio": metrics["confidence_ratio"],
            "word_count": metrics["word_count"],
            "guidance_score": metrics["guidance_score"],
        })
        score_rows.append((
            symbol,
            today_str,
            score,
            round(sentiment_delta, 4) if sentiment_delta is not None else None,
            round(hedging_delta, 6) if hedging_delta is not None else None,
            metrics["guidance_score"],
            details,
        ))

        processed += 1

    # Store results
    if transcript_rows:
        upsert_many(
            "earnings_transcripts",
            ["symbol", "date", "quarter", "filing_url", "word_count",
             "sentiment", "hedging_ratio", "confidence_ratio", "key_phrases"],
            transcript_rows,
        )
    if score_rows:
        upsert_many(
            "earnings_nlp_scores",
            ["symbol", "date", "earnings_nlp_score", "sentiment_delta",
             "hedging_delta", "guidance_score", "details"],
            score_rows,
        )

    print(f"\n  Processed: {processed} | Errors: {errors} | Stored: {len(score_rows)} scores")
    print("  Earnings NLP complete.")
    return {"processed": processed, "scored": len(score_rows), "errors": errors}


if __name__ == "__main__":
    run()
