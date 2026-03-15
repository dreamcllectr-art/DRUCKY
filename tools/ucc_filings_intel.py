"""UCC Filings Intelligence — asset pledging / lien data as a corporate distress leading indicator.

When companies pledge assets as collateral (UCC-1 filings), it can signal:
- Increasing leverage / financial stress (bearish)
- Secured borrowing for expansion (context-dependent)
- Pattern of UCC amendments/continuations = ongoing debt dependency

Three sub-scores blended into ucc_filings_score (0-100):
  1. SEC EDGAR secured-debt language   (weight 0.45)
  2. News sentiment on secured debt     (weight 0.30)
  3. Leverage context from fundamentals (weight 0.25)

Weekly cadence.  Batches Serper calls to top 50-100 high-leverage names.
"""
import json, logging, time, re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
import requests
from tools.db import init_db, get_conn, query, upsert_many
from tools.config import SERPER_API_KEY

logger = logging.getLogger(__name__)

WEIGHTS = {"sec_language": 0.45, "news": 0.30, "leverage": 0.25}
NEUTRAL_SCORE = 55.0
MATCH_THRESHOLD = 0.82
RATE_LIMIT_DELAY = 0.4
LOOKBACK_DAYS = 90
BATCH_SIZE = 50          # top N by D/E for active scanning
SERPER_BATCH = 10        # queries per Serper call

_session = requests.Session()
_session.headers.update({"User-Agent": "DruckenmillerAlpha/1.0 (research; ucc-filings)"})

RAW_COLS = ["symbol", "date", "source", "filing_type", "severity", "details"]
SCORE_COLS = ["symbol", "date", "ucc_filings_score", "sec_language_score",
              "news_score", "leverage_score", "details"]

# ---------------------------------------------------------------------------
# Keyword dictionaries for scoring
# ---------------------------------------------------------------------------
SEC_STRESS_PATTERNS = {
    "blanket_lien":   (re.compile(r"(?:blanket\s+lien|all\s+assets.*(?:collateral|secured))", re.I), 15),
    "ucc_all_assets": (re.compile(r"UCC.*all\s+assets", re.I), 15),
    "covenant_amend": (re.compile(r"(?:amendment|waiver).*(?:credit\s+agreement|covenant)", re.I), 35),
    "covenant_stress": (re.compile(r"(?:covenant\s+(?:violation|breach|default))", re.I), 20),
    "secured_normal":  (re.compile(r"secured\s+credit\s+facility", re.I), 55),
}

NEWS_POSITIVE_KW = ["refinanced", "extended maturity", "reduced rate", "investment grade",
                     "upgraded", "improved terms", "deleveraging"]
NEWS_NEUTRAL_KW  = ["credit facility", "revolving", "term loan", "secured lending",
                     "credit agreement"]
NEWS_NEGATIVE_KW = ["covenant violation", "default", "restructuring", "distressed",
                     "emergency loan", "going concern", "forbearance", "bankruptcy",
                     "liquidation", "downgraded", "junk"]


# ---------------------------------------------------------------------------
# Table setup & gate
# ---------------------------------------------------------------------------
def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ucc_filings_raw (
            symbol TEXT, date TEXT, source TEXT, filing_type TEXT,
            severity TEXT, details TEXT,
            PRIMARY KEY (symbol, date, source, filing_type));
        CREATE TABLE IF NOT EXISTS ucc_filings_scores (
            symbol TEXT, date TEXT, ucc_filings_score REAL, sec_language_score REAL,
            news_score REAL, leverage_score REAL, details TEXT,
            PRIMARY KEY (symbol, date));
    """)
    conn.commit()
    conn.close()


def _should_run() -> bool:
    rows = query("SELECT MAX(date) as last_run FROM ucc_filings_scores")
    if not rows or not rows[0]["last_run"]:
        return True
    return (date.today() - datetime.strptime(rows[0]["last_run"], "%Y-%m-%d").date()).days >= 7


# ---------------------------------------------------------------------------
# Universe helpers
# ---------------------------------------------------------------------------
def _get_universe():
    return {r["symbol"]: r["name"] for r in
            query("SELECT symbol, name FROM stock_universe WHERE name IS NOT NULL")}


def _get_debt_metrics():
    """Return {symbol: {totalDebt, totalEquity, debtToEquity}} from fundamentals."""
    rows = query("""
        SELECT symbol, metric, value FROM fundamentals
        WHERE metric IN ('totalDebt', 'totalStockholdersEquity', 'debtToEquity')
          AND value IS NOT NULL
    """)
    metrics = {}
    for r in rows:
        metrics.setdefault(r["symbol"], {})[r["metric"]] = r["value"]
    # Compute D/E if not stored directly
    for sym, m in metrics.items():
        if "debtToEquity" not in m:
            debt = m.get("totalDebt", 0)
            equity = m.get("totalStockholdersEquity", 1)
            if equity and equity > 0:
                m["debtToEquity"] = debt / equity
            else:
                m["debtToEquity"] = 999.0  # effectively infinite
    return metrics


def _top_leveraged(universe, debt_metrics, n=BATCH_SIZE):
    """Return top-n symbols sorted by D/E ratio (highest first)."""
    scored = []
    for sym in universe:
        de = debt_metrics.get(sym, {}).get("debtToEquity", 0)
        if de and de > 0:
            scored.append((sym, de))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in scored[:n]]


def _match(text, universe):
    """Fuzzy-match a company name from search text to stock universe."""
    if not text:
        return None
    cl = text.lower().strip()
    best_ticker, best_ratio = None, 0.0
    for symbol, name in universe.items():
        if not name:
            continue
        nl = name.lower().strip()
        if cl in nl or nl in cl:
            return symbol
        r = SequenceMatcher(None, cl, nl).ratio()
        if r > best_ratio:
            best_ratio, best_ticker = r, symbol
    return best_ticker if best_ratio >= MATCH_THRESHOLD else None


def _safe_get(url, params=None, headers=None, timeout=20):
    time.sleep(RATE_LIMIT_DELAY)
    try:
        resp = _session.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("GET %s failed: %s", url, exc)
        return None


def _safe_post(url, json_body=None, headers=None, timeout=20):
    time.sleep(RATE_LIMIT_DELAY)
    try:
        resp = _session.post(url, json=json_body, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("POST %s failed: %s", url, exc)
        return None


def _cutoff():
    return (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()


# ---------------------------------------------------------------------------
# [1/3] SEC EDGAR secured-debt language analysis
# ---------------------------------------------------------------------------
def _fetch_sec_language_scores(universe, top_symbols):
    """Search EDGAR full-text for secured-debt / UCC language in recent 10-K/10-Q."""
    print("  [1/3] SEC EDGAR secured debt language ...")
    today_str = date.today().isoformat()
    start_dt = _cutoff()
    scores = {}
    raw_rows = []
    mention_count = 0

    for sym in top_symbols:
        company_name = universe.get(sym, sym)
        # EDGAR EFTS full-text search
        params = {
            "q": f'"{company_name}" "secured" "credit"',
            "dateRange": "custom",
            "startdt": start_dt,
            "enddt": today_str,
            "forms": "10-K,10-Q",
        }
        data = _safe_get("https://efts.sec.gov/LATEST/search-index", params=params)

        # EDGAR returns hits in various formats; try common structures
        hits = []
        if data and isinstance(data, dict):
            hits = data.get("hits", data.get("results", data.get("filings", [])))
            if isinstance(hits, dict):
                hits = hits.get("hits", hits.get("results", []))
        if not isinstance(hits, list):
            hits = []

        # Also try the standard EDGAR full-text search endpoint
        if not hits:
            alt_data = _safe_get("https://efts.sec.gov/LATEST/search-index",
                                 params={"q": f'"{company_name}" UCC lien collateral',
                                         "forms": "10-K,10-Q",
                                         "dateRange": "custom",
                                         "startdt": start_dt,
                                         "enddt": today_str})
            if alt_data and isinstance(alt_data, dict):
                hits = alt_data.get("hits", alt_data.get("results", []))
                if isinstance(hits, dict):
                    hits = hits.get("hits", [])
                if not isinstance(hits, list):
                    hits = []

        if not hits:
            # No SEC filings mentioning secured debt — clean balance sheet signal
            scores[sym] = 75.0
            continue

        mention_count += len(hits)
        # Analyze the text snippets for severity
        worst_score = 75.0
        for hit in hits[:10]:  # cap analysis per symbol
            snippet = ""
            if isinstance(hit, dict):
                snippet = (hit.get("_source", {}).get("file_description", "") +
                           " " + hit.get("_source", {}).get("display_description", "") +
                           " " + json.dumps(hit.get("highlight", {})))
            elif isinstance(hit, str):
                snippet = hit

            for pattern_name, (regex, score_val) in SEC_STRESS_PATTERNS.items():
                if regex.search(snippet):
                    if score_val < worst_score:
                        worst_score = score_val
                    severity = "high" if score_val <= 20 else "medium" if score_val <= 40 else "low"
                    raw_rows.append((sym, today_str, "sec_edgar", pattern_name,
                                     severity, json.dumps({"snippet": snippet[:300]})))
                    break

        scores[sym] = worst_score

    print(f"    Parsed {mention_count} filing mentions")
    if raw_rows:
        upsert_many("ucc_filings_raw", RAW_COLS, raw_rows)
    return scores


# ---------------------------------------------------------------------------
# [2/3] Secured-debt news signals via Serper
# ---------------------------------------------------------------------------
def _score_news_text(text):
    """Score a news snippet based on keyword presence. Returns 0-100."""
    tl = text.lower()
    neg_hits = sum(1 for kw in NEWS_NEGATIVE_KW if kw in tl)
    pos_hits = sum(1 for kw in NEWS_POSITIVE_KW if kw in tl)
    neu_hits = sum(1 for kw in NEWS_NEUTRAL_KW if kw in tl)

    if neg_hits >= 2:
        return 10.0
    if neg_hits == 1 and pos_hits == 0:
        return 25.0
    if neg_hits == 1 and pos_hits >= 1:
        return 40.0
    if pos_hits >= 2:
        return 85.0
    if pos_hits == 1:
        return 70.0
    if neu_hits >= 1:
        return 55.0
    return NEUTRAL_SCORE


def _fetch_news_scores(universe, top_symbols):
    """Search Serper for secured-debt news on top leveraged names."""
    print("  [2/3] Secured debt news signals ...")
    today_str = date.today().isoformat()
    scores = {}
    raw_rows = []

    if not SERPER_API_KEY:
        logger.warning("SERPER_API_KEY not set — skipping news fetch")
        return {sym: NEUTRAL_SCORE for sym in universe}

    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}

    # Batch Serper queries for top leveraged symbols
    batch_results = {}
    for i in range(0, len(top_symbols), SERPER_BATCH):
        batch = top_symbols[i:i + SERPER_BATCH]
        for sym in batch:
            company_name = universe.get(sym, sym)
            # Clean company name for search
            clean_name = re.sub(r'\s+(Inc\.?|Corp\.?|Ltd\.?|LLC|Co\.?|PLC|S\.A\.)$', '',
                                company_name, flags=re.I).strip()

            body = {
                "q": f'"{clean_name}" secured debt OR pledged collateral OR covenant OR lien',
                "num": 5,
                "tbs": "qdr:m3",  # last 3 months
            }
            data = _safe_post("https://google.serper.dev/search", json_body=body, headers=headers)

            snippets = []
            if data and isinstance(data, dict):
                for item in data.get("organic", [])[:5]:
                    title = item.get("title", "")
                    snippet = item.get("snippet", "")
                    snippets.append(f"{title} {snippet}")

            if snippets:
                combined = " ".join(snippets)
                score = _score_news_text(combined)
                batch_results[sym] = score
                severity = "high" if score <= 30 else "medium" if score <= 50 else "low"
                raw_rows.append((sym, today_str, "serper_news", "secured_debt_news",
                                 severity, json.dumps({"snippets": snippets[:3],
                                                        "score": score})))
            else:
                batch_results[sym] = NEUTRAL_SCORE

    # Assign scores: active scan for top symbols, neutral for rest
    for sym in universe:
        scores[sym] = batch_results.get(sym, NEUTRAL_SCORE)

    if raw_rows:
        upsert_many("ucc_filings_raw", RAW_COLS, raw_rows)
    return scores


# ---------------------------------------------------------------------------
# [3/3] Leverage context from fundamentals
# ---------------------------------------------------------------------------
def _compute_leverage_scores(universe, debt_metrics):
    """Score based on debt-to-equity ratio from existing fundamentals."""
    print("  [3/3] Leverage context from fundamentals ...")
    scores = {}
    for sym in universe:
        de = debt_metrics.get(sym, {}).get("debtToEquity")
        if de is None or de <= 0:
            scores[sym] = 80.0   # no/minimal debt
        elif de < 0.5:
            scores[sym] = 80.0
        elif de < 1.0:
            scores[sym] = 60.0
        elif de < 2.0:
            scores[sym] = 40.0
        else:
            scores[sym] = 20.0
    return scores


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------
def _compute_composite(universe, sec_scores, news_scores, leverage_scores):
    """Blend sub-scores into ucc_filings_score (0-100)."""
    today_str = date.today().isoformat()
    score_rows = []
    scored = 0
    for sym in universe:
        s = {
            "sec_language": sec_scores.get(sym, NEUTRAL_SCORE),
            "news": news_scores.get(sym, NEUTRAL_SCORE),
            "leverage": leverage_scores.get(sym, NEUTRAL_SCORE),
        }
        composite = round(sum(s[k] * WEIGHTS[k] for k in WEIGHTS), 1)
        details = json.dumps({k: round(v, 1) for k, v in s.items()})
        score_rows.append((sym, today_str, composite, round(s["sec_language"], 1),
                           round(s["news"], 1), round(s["leverage"], 1), details))
        scored += 1
    return score_rows, scored


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run():
    init_db()
    _ensure_tables()
    print("\n" + "=" * 60)
    print("  UCC FILINGS INTELLIGENCE")
    print("=" * 60)

    if not _should_run():
        print("  Skipping — last run was within 7 days")
        print("=" * 60)
        return

    universe = _get_universe()
    if not universe:
        print("  No stock universe found")
        print("=" * 60)
        return

    debt_metrics = _get_debt_metrics()

    # Filter to companies with meaningful debt exposure
    debt_universe = {sym: name for sym, name in universe.items()
                     if debt_metrics.get(sym, {}).get("totalDebt", 0) > 0
                     or debt_metrics.get(sym, {}).get("debtToEquity", 0) > 0}
    if not debt_universe:
        # Fall back to full universe if no debt data yet
        debt_universe = universe

    print(f"  Universe: {len(debt_universe)} symbols with debt exposure")

    # Top leveraged names get active scanning (SEC + news)
    top_symbols = _top_leveraged(debt_universe, debt_metrics, n=BATCH_SIZE)

    # Fetch sub-scores
    sec_scores, news_scores, leverage_scores = {}, {}, {}
    try:
        sec_scores = _fetch_sec_language_scores(debt_universe, top_symbols)
    except Exception as exc:
        logger.error("SEC language fetch failed: %s", exc)
        print(f"    SEC language source failed: {exc}")

    try:
        news_scores = _fetch_news_scores(debt_universe, top_symbols)
    except Exception as exc:
        logger.error("News fetch failed: %s", exc)
        print(f"    News source failed: {exc}")

    try:
        leverage_scores = _compute_leverage_scores(debt_universe, debt_metrics)
    except Exception as exc:
        logger.error("Leverage scoring failed: %s", exc)
        print(f"    Leverage scoring failed: {exc}")

    # Composite
    score_rows, scored = _compute_composite(debt_universe, sec_scores, news_scores, leverage_scores)
    upsert_many("ucc_filings_scores", SCORE_COLS, score_rows)
    print(f"  Scored {scored} symbols")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
