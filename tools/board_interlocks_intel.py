"""Board Interlocks Intelligence — corporate governance network analysis from SEC proxy filings.

Analyzes board of directors interlocks and executive network signals
from SEC DEF 14A proxy filings. Institutional-grade governance scoring.

Why This Matters (hedge fund theory):
  - Board members sitting on multiple company boards create information networks
  - Companies sharing board members often have correlated strategic decisions
  - New board appointments signal strategic direction changes
  - Director departures can indicate governance concerns
  - "Star directors" (experienced, well-connected) correlate with better governance

Data sources (all free, public):
  1. SEC EDGAR DEF 14A proxy filings — board composition, independence
  2. Serper news search — board appointment/departure signals

Produces 0-100 board_interlocks_score per symbol.
Monthly gate: skips if last run was <30 days ago.

Usage:
    python -m tools.board_interlocks_intel
"""

import json
import logging
import re
import time
from datetime import date, datetime, timedelta

import requests

from tools.db import init_db, get_conn, query, upsert_many
from tools.config import SERPER_API_KEY, EDGAR_BASE, EDGAR_HEADERS

logger = logging.getLogger(__name__)

# ── Weights ─────────────────────────────────────────────────────────
W_QUALITY = 0.35
W_NETWORK = 0.25
W_GOVERNANCE_CHANGE = 0.25
W_INDEPENDENCE = 0.15

NEUTRAL_SCORE = 50.0
EDGAR_RATE_LIMIT = 0.3   # seconds between EDGAR calls
SERPER_RATE_LIMIT = 0.5  # seconds between Serper calls
TOP_N_PROXY = 100         # full proxy analysis for top N by market cap

# EDGAR full-text search endpoint
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

_session = requests.Session()
_session.headers.update(EDGAR_HEADERS)


# ── DB Setup ────────────────────────────────────────────────────────

def _ensure_tables():
    """Create board-interlocks-specific tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS board_interlocks_raw (
            symbol TEXT,
            date TEXT,
            director_name TEXT,
            other_boards TEXT,
            committees TEXT,
            is_independent INTEGER,
            details TEXT,
            PRIMARY KEY (symbol, date, director_name)
        );
        CREATE TABLE IF NOT EXISTS board_interlocks_scores (
            symbol TEXT,
            date TEXT,
            board_interlocks_score REAL,
            quality_score REAL,
            network_score REAL,
            governance_change_score REAL,
            independence_score REAL,
            details TEXT,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.commit()
    conn.close()


# ── Monthly Gate ────────────────────────────────────────────────────

def _should_run() -> bool:
    """Return True if last run was >= 30 days ago (or never)."""
    rows = query("SELECT MAX(date) as last_date FROM board_interlocks_scores")
    if not rows or rows[0]["last_date"] is None:
        return True
    last = datetime.strptime(rows[0]["last_date"], "%Y-%m-%d").date()
    return (date.today() - last).days >= 30


# ── Universe Helpers ────────────────────────────────────────────────

def _get_universe():
    """Return {symbol: name} for the full stock universe."""
    return {r["symbol"]: r["name"] for r in query(
        "SELECT symbol, name FROM stock_universe WHERE name IS NOT NULL"
    )}


def _get_top_symbols(n: int) -> list[dict]:
    """Return top N symbols by market cap with names."""
    rows = query("""
        SELECT u.symbol, u.name, f.value as market_cap
        FROM stock_universe u
        LEFT JOIN fundamentals f ON u.symbol = f.symbol AND f.metric = 'marketCap'
        WHERE u.name IS NOT NULL AND f.value > 0
        ORDER BY f.value DESC
        LIMIT ?
    """, [n])
    return rows


# ── SEC EDGAR Proxy Filing Fetch ────────────────────────────────────

def _search_edgar_proxy(company_name: str) -> dict | None:
    """Search EDGAR for the most recent DEF 14A filing for a company.

    Returns the filing metadata dict or None.
    """
    time.sleep(EDGAR_RATE_LIMIT)
    # Clean company name for search — remove Inc, Corp, etc.
    clean = re.sub(r'\b(Inc\.?|Corp\.?|Ltd\.?|LLC|Co\.?|Group|Holdings?|Enterprises?|International)\b',
                   '', company_name, flags=re.IGNORECASE).strip()
    clean = re.sub(r'\s+', ' ', clean).strip()
    if not clean:
        clean = company_name

    today_str = date.today().isoformat()
    year_ago = (date.today() - timedelta(days=365)).isoformat()

    try:
        resp = _session.get(
            EDGAR_SEARCH_URL,
            params={
                "q": f'"{clean}"',
                "forms": "DEF 14A",
                "dateRange": "custom",
                "startdt": year_ago,
                "enddt": today_str,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", data.get("results", []))
        if isinstance(hits, dict):
            hits = hits.get("hits", [])
        if hits and isinstance(hits, list):
            return hits[0]
    except Exception as exc:
        logger.debug("EDGAR search failed for %s: %s", company_name, exc)
    return None


def _fetch_filing_text(filing_url: str, max_chars: int = 50000) -> str:
    """Fetch the first max_chars of a filing document from EDGAR."""
    time.sleep(EDGAR_RATE_LIMIT)
    try:
        resp = _session.get(filing_url, timeout=20, stream=True)
        resp.raise_for_status()
        # Read only first chunk to avoid downloading huge filings
        text = ""
        for chunk in resp.iter_content(chunk_size=8192, decode_unicode=True):
            if chunk:
                text += chunk
                if len(text) >= max_chars:
                    break
        return text[:max_chars]
    except Exception as exc:
        logger.debug("Failed to fetch filing text from %s: %s", filing_url, exc)
        return ""


def _extract_filing_url(hit: dict) -> str | None:
    """Extract the filing document URL from an EDGAR search hit."""
    # The search result structure varies; try common fields
    source = hit.get("_source", hit)
    # Try file_url, document_url, or construct from accession
    for key in ("file_url", "document_url", "url"):
        if source.get(key):
            url = source[key]
            if not url.startswith("http"):
                url = f"https://www.sec.gov{url}"
            return url
    # Try to build from accession number
    accession = source.get("accession_no") or source.get("accession_number", "")
    if accession:
        acc_clean = accession.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{acc_clean[:10]}/{accession}/{accession}.txt"
    return None


# ── DEF 14A Text Parsing ────────────────────────────────────────────

def _parse_directors_from_text(text: str) -> list[dict]:
    """Extract director information from DEF 14A filing text.

    Uses regex patterns to find director names, independence status,
    committee assignments, and other board memberships.
    Returns list of dicts with keys: name, is_independent, committees, other_boards.
    """
    directors = []
    if not text:
        return directors

    text_lower = text.lower()

    # Pattern 1: "Name, age XX, has served as [independent] director"
    # Pattern 2: "Name — Independent Director"
    # Pattern 3: Lines near "director" or "nominee" sections
    director_patterns = [
        # "John Smith, age 62, independent director"
        re.compile(
            r'([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
            r',?\s*(?:age\s+\d+,?\s*)?'
            r'(?:has\s+(?:been|served)\s+as\s+)?'
            r'(?:an?\s+)?(independent\s+)?director',
            re.IGNORECASE,
        ),
        # "Ms. Jane Doe — Director since 2018"
        re.compile(
            r'(?:Mr\.|Ms\.|Mrs\.|Dr\.)\s+'
            r'([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
            r'[^.]*?director',
            re.IGNORECASE,
        ),
        # "DIRECTOR NOMINEES" section followed by names
        re.compile(
            r'(?:nominee|director|board\s+member)[:\s]*'
            r'([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)',
            re.IGNORECASE,
        ),
    ]

    seen_names = set()
    for pattern in director_patterns:
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            # Skip too-short or too-long names, or common false positives
            if len(name) < 5 or len(name) > 50:
                continue
            # Skip common non-name matches
            skip_words = {"the board", "our board", "each director", "the company",
                          "this proxy", "annual meeting", "common stock",
                          "united states", "new york", "board directors"}
            if name.lower() in skip_words:
                continue
            if name in seen_names:
                continue
            seen_names.add(name)

            # Check independence
            context_start = max(0, match.start() - 200)
            context_end = min(len(text), match.end() + 500)
            context = text[context_start:context_end].lower()
            is_independent = 1 if "independent" in context else 0

            # Extract committees from nearby context
            committees = []
            for comm in ["audit", "compensation", "nominating", "governance",
                         "risk", "finance", "technology", "strategy"]:
                if comm in context:
                    committees.append(comm)

            # Extract other board memberships
            other_boards = []
            # Look for "serves on the board of X" or "director of X"
            board_pattern = re.compile(
                r'(?:serves?\s+on\s+the\s+board\s+of|director\s+of|board\s+member\s+of|'
                r'board\s+of\s+directors\s+of)\s+'
                r'([A-Z][A-Za-z\s&,]+?)(?:\.|,|\s+since|\s+from|\s+and\b)',
                re.IGNORECASE,
            )
            for bm in board_pattern.finditer(text[context_start:context_end]):
                board_name = bm.group(1).strip()
                if len(board_name) > 3 and len(board_name) < 80:
                    other_boards.append(board_name)

            directors.append({
                "name": name,
                "is_independent": is_independent,
                "committees": committees,
                "other_boards": other_boards,
            })

    return directors


# ── Serper News Search ──────────────────────────────────────────────

def _search_board_news(company_name: str, symbol: str) -> list[dict]:
    """Search for recent board appointment/departure news via Serper."""
    if not SERPER_API_KEY:
        return []
    time.sleep(SERPER_RATE_LIMIT)
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={
                "q": f'"{company_name}" board of directors appointment OR resignation OR departure',
                "num": 5,
                "tbs": "qdr:m3",  # last 3 months
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("organic", [])
        return results[:5]
    except Exception as exc:
        logger.debug("Serper board news failed for %s: %s", symbol, exc)
        return []


def _score_governance_changes(news_results: list[dict]) -> tuple[float, str]:
    """Score governance changes from news results.

    Returns (score, narrative).
    Appointment keywords → bullish (65-80)
    Departure keywords → bearish (30-45)
    No news → neutral (50)
    """
    if not news_results:
        return NEUTRAL_SCORE, "no recent board changes"

    appointment_keywords = [
        "appointed", "joined board", "elected director", "new independent director",
        "named to board", "board appointment", "adds director", "new board member",
        "joins board",
    ]
    departure_keywords = [
        "resigned", "departed", "stepped down", "removed", "leaves board",
        "board departure", "director exit", "steps down",
    ]
    ceo_keywords = [
        "new ceo", "ceo transition", "ceo change", "ceo appointed",
        "chair change", "new chairman",
    ]

    appointment_count = 0
    departure_count = 0
    ceo_change = False
    narratives = []

    for result in news_results:
        title = (result.get("title", "") + " " + result.get("snippet", "")).lower()
        if any(kw in title for kw in appointment_keywords):
            appointment_count += 1
            narratives.append("new appointment")
        if any(kw in title for kw in departure_keywords):
            departure_count += 1
            narratives.append("departure")
        if any(kw in title for kw in ceo_keywords):
            ceo_change = True
            narratives.append("CEO/chair change")

    # Score logic
    if ceo_change:
        # CEO changes are high-impact — slightly bearish uncertainty unless paired with appointment
        if appointment_count > departure_count:
            score = 70.0  # new CEO appointed, positive transition
        else:
            score = 40.0  # uncertainty from leadership change
    elif appointment_count > 0 and departure_count == 0:
        score = min(80.0, 65.0 + appointment_count * 5)
    elif departure_count > 0 and appointment_count == 0:
        score = max(30.0, 45.0 - departure_count * 5)
    elif appointment_count > departure_count:
        score = 60.0 + (appointment_count - departure_count) * 3
    elif departure_count > appointment_count:
        score = 40.0 - (departure_count - appointment_count) * 3
    else:
        score = NEUTRAL_SCORE

    score = max(10.0, min(90.0, score))
    narrative = "; ".join(set(narratives)) if narratives else "no clear signal"
    return round(score, 1), narrative


# ── Scoring Functions ───────────────────────────────────────────────

def _compute_quality_score(directors: list[dict]) -> float:
    """Board Quality Score based on interlocks and committee presence.

    Average interlocks per director:
      3+ → 80, 2-3 → 65, 1-2 → 50, <1 → 40
    Committee bonus: +5 for each key committee covered (audit, compensation, nominating)
    """
    if not directors:
        return NEUTRAL_SCORE

    total_interlocks = sum(len(d.get("other_boards", [])) for d in directors)
    avg_interlocks = total_interlocks / len(directors)

    if avg_interlocks >= 3:
        score = 80.0
    elif avg_interlocks >= 2:
        score = 65.0 + (avg_interlocks - 2) * 15
    elif avg_interlocks >= 1:
        score = 50.0 + (avg_interlocks - 1) * 15
    else:
        score = 40.0 + avg_interlocks * 10

    # Committee coverage bonus
    all_committees = set()
    for d in directors:
        all_committees.update(d.get("committees", []))
    key_committees = {"audit", "compensation", "nominating", "governance"}
    covered = len(all_committees & key_committees)
    score += covered * 3

    return round(max(10.0, min(95.0, score)), 1)


def _compute_network_score(symbol: str, directors: list[dict]) -> float:
    """Network Effect Score — cross-reference board connections with convergence signals.

    Connected to HIGH conviction stocks: +15 bonus
    Connected to BLOCKED stocks: -10 penalty
    Base: 50 (neutral)
    """
    if not directors:
        return NEUTRAL_SCORE

    # Get all other board names mentioned by directors
    connected_companies = set()
    for d in directors:
        for board in d.get("other_boards", []):
            connected_companies.add(board.lower().strip())

    if not connected_companies:
        return NEUTRAL_SCORE

    # Check convergence signals for connected companies
    try:
        high_conviction = query("""
            SELECT DISTINCT symbol FROM convergence_signals
            WHERE conviction_level = 'HIGH'
            AND date = (SELECT MAX(date) FROM convergence_signals)
        """)
        high_symbols = {r["symbol"] for r in high_conviction}

        blocked = query("""
            SELECT DISTINCT symbol FROM convergence_signals
            WHERE forensic_blocked = 1
            AND date = (SELECT MAX(date) FROM convergence_signals)
        """)
        blocked_symbols = {r["symbol"] for r in blocked}
    except Exception:
        return NEUTRAL_SCORE

    # Try to match connected company names to symbols
    universe = _get_universe()
    name_to_symbol = {v.lower(): k for k, v in universe.items() if v}

    score = NEUTRAL_SCORE
    for company in connected_companies:
        # Fuzzy match: check if any universe company name is contained in the board name
        for name_lower, sym in name_to_symbol.items():
            if sym == symbol:
                continue
            if company in name_lower or name_lower in company:
                if sym in high_symbols:
                    score += 15
                if sym in blocked_symbols:
                    score -= 10
                break

    return round(max(10.0, min(95.0, score)), 1)


def _compute_independence_score(directors: list[dict]) -> float:
    """Board Independence Score.

    >75% independent → 80
    50-75% → 60
    <50% → 35
    """
    if not directors:
        return NEUTRAL_SCORE

    independent_count = sum(1 for d in directors if d.get("is_independent"))
    total = len(directors)
    if total == 0:
        return NEUTRAL_SCORE

    ratio = independent_count / total

    if ratio > 0.75:
        score = 80.0
    elif ratio >= 0.50:
        score = 60.0 + (ratio - 0.50) / 0.25 * 20
    else:
        score = 35.0 + ratio / 0.50 * 25

    return round(max(10.0, min(95.0, score)), 1)


# ── Core Pipeline ───────────────────────────────────────────────────

def _fetch_proxy_filings(top_symbols: list[dict]) -> dict[str, list[dict]]:
    """Fetch and parse DEF 14A filings for top symbols.

    Returns {symbol: [director_dicts]}.
    """
    directors_by_symbol = {}
    parsed_filings = 0
    total_directors = 0

    for sym_info in top_symbols:
        symbol = sym_info["symbol"]
        name = sym_info["name"]
        if not name:
            continue

        hit = _search_edgar_proxy(name)
        if not hit:
            continue

        filing_url = _extract_filing_url(hit)
        if not filing_url:
            continue

        text = _fetch_filing_text(filing_url)
        if not text:
            continue

        directors = _parse_directors_from_text(text)
        if directors:
            directors_by_symbol[symbol] = directors
            parsed_filings += 1
            total_directors += len(directors)

    return directors_by_symbol, parsed_filings, total_directors


def _fetch_board_news(universe: dict, top_symbols_set: set) -> dict[str, tuple[float, str]]:
    """Fetch board change news for the universe via Serper.

    For top symbols, does individual searches.
    For others, assigns neutral.
    Returns {symbol: (governance_change_score, narrative)}.
    """
    news_scores = {}

    # Only search top symbols + any symbol not covered by proxy
    search_symbols = []
    for sym, name in universe.items():
        if sym in top_symbols_set and name:
            search_symbols.append((sym, name))
    # Limit Serper calls: only search symbols where we have proxy data or top 100
    for sym, name in search_symbols:
        if not SERPER_API_KEY:
            news_scores[sym] = (NEUTRAL_SCORE, "no API key")
            continue
        results = _search_board_news(name, sym)
        score, narrative = _score_governance_changes(results)
        news_scores[sym] = (score, narrative)

    return news_scores


def _store_raw_directors(directors_by_symbol: dict[str, list[dict]], today_str: str):
    """Store raw director data for audit trail."""
    raw_rows = []
    for symbol, directors in directors_by_symbol.items():
        for d in directors:
            raw_rows.append((
                symbol,
                today_str,
                d["name"],
                json.dumps(d.get("other_boards", [])),
                json.dumps(d.get("committees", [])),
                d.get("is_independent", 0),
                json.dumps(d),
            ))
    if raw_rows:
        upsert_many(
            "board_interlocks_raw",
            ["symbol", "date", "director_name", "other_boards",
             "committees", "is_independent", "details"],
            raw_rows,
        )


def _compute_all_scores(
    universe: dict,
    directors_by_symbol: dict[str, list[dict]],
    news_scores: dict[str, tuple[float, str]],
) -> list[tuple]:
    """Compute composite board_interlocks_score for all symbols."""
    today_str = date.today().isoformat()
    score_rows = []

    for symbol in universe:
        directors = directors_by_symbol.get(symbol, [])
        has_proxy = len(directors) > 0

        # Sub-scores
        quality = _compute_quality_score(directors) if has_proxy else NEUTRAL_SCORE
        network = _compute_network_score(symbol, directors) if has_proxy else NEUTRAL_SCORE
        gov_change, narrative = news_scores.get(symbol, (NEUTRAL_SCORE, "no data"))
        independence = _compute_independence_score(directors) if has_proxy else NEUTRAL_SCORE

        # Composite
        composite = round(
            quality * W_QUALITY
            + network * W_NETWORK
            + gov_change * W_GOVERNANCE_CHANGE
            + independence * W_INDEPENDENCE,
            1,
        )

        details = json.dumps({
            "quality_score": quality,
            "network_score": network,
            "governance_change_score": gov_change,
            "independence_score": independence,
            "director_count": len(directors),
            "has_proxy_data": has_proxy,
            "governance_narrative": narrative,
        })

        score_rows.append((
            symbol, today_str, composite,
            quality, network, gov_change, independence,
            details,
        ))

    return score_rows


# ── Entry Point ─────────────────────────────────────────────────────

def run():
    """Monthly board interlocks intelligence run."""
    init_db()
    _ensure_tables()

    print("\n" + "=" * 60)
    print("  BOARD INTERLOCKS INTELLIGENCE")
    print("=" * 60)

    if not _should_run():
        print("  Skipping -- last run was < 30 days ago")
        print("=" * 60)
        return

    universe = _get_universe()
    if not universe:
        print("  No stock universe found")
        print("=" * 60)
        return

    top_symbols = _get_top_symbols(TOP_N_PROXY)
    top_set = {s["symbol"] for s in top_symbols}

    print(f"  Universe: {len(top_symbols)} top symbols by market cap")

    # [1/3] SEC EDGAR proxy filings
    print("  [1/3] SEC EDGAR proxy filings (DEF 14A) ...")
    directors_by_symbol, parsed_count, director_count = _fetch_proxy_filings(top_symbols)
    print(f"    Parsed {parsed_count} proxy filings, extracted {director_count} directors")

    # Store raw director data
    today_str = date.today().isoformat()
    _store_raw_directors(directors_by_symbol, today_str)

    # [2/3] Board change news signals
    print("  [2/3] Board change news signals ...")
    news_scores = _fetch_board_news(universe, top_set)
    news_count = sum(1 for _, (s, _) in news_scores.items() if s != NEUTRAL_SCORE)
    print(f"    Found {news_count} symbols with board change signals")

    # [3/3] Compute governance + network scores
    print("  [3/3] Computing governance + network scores ...")
    score_rows = _compute_all_scores(universe, directors_by_symbol, news_scores)

    upsert_many(
        "board_interlocks_scores",
        ["symbol", "date", "board_interlocks_score",
         "quality_score", "network_score", "governance_change_score",
         "independence_score", "details"],
        score_rows,
    )

    print(f"  Scored {len(score_rows)} symbols")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
