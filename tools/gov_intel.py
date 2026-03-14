"""Government Intelligence Module — regulatory & labor signal aggregation.

Aggregates 5 government/regulatory data sources into a single gov_intel_score
(0-100) per stock symbol:

  1. WARN Act Layoff Filings      (weight 0.30)
  2. OSHA Inspection Logs         (weight 0.15)
  3. EPA ECHO Permits/Violations  (weight 0.20)
  4. FCC Filings                  (weight 0.15)
  5. Lobbying Disclosures         (weight 0.20)

Runs weekly (skips if last run < 7 days ago).

Usage:
    python -m tools.gov_intel
"""

import json
import logging
import time
import traceback
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher

import requests

from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

# ── Weights ──────────────────────────────────────────────────────────────
WARN_WEIGHT = 0.30
OSHA_WEIGHT = 0.15
EPA_WEIGHT = 0.20
FCC_WEIGHT = 0.15
LOBBY_WEIGHT = 0.20

NEUTRAL_SCORE = 50
MATCH_THRESHOLD = 0.85
MAX_RECORDS_PER_SOURCE = 500
RATE_LIMIT_DELAY = 0.5  # seconds between API calls
LOOKBACK_DAYS = 90

# ── HTTP Session ─────────────────────────────────────────────────────────
_session = requests.Session()
_session.headers.update({
    "User-Agent": "DruckenmillerAlpha/1.0 (research; gov-intel)"
})


# ── Helpers ──────────────────────────────────────────────────────────────

def _should_run() -> bool:
    """Return True if module hasn't run in the last 7 days."""
    rows = query("SELECT MAX(date) as last_run FROM gov_intel_scores")
    if not rows or not rows[0]["last_run"]:
        return True
    last = datetime.strptime(rows[0]["last_run"], "%Y-%m-%d").date()
    return (date.today() - last).days >= 7


def _get_universe() -> dict[str, str]:
    """Return {symbol: company_name} from stock_universe."""
    rows = query("SELECT symbol, name FROM stock_universe WHERE name IS NOT NULL")
    return {r["symbol"]: r["name"] for r in rows}


def _get_market_caps() -> dict[str, float]:
    """Return {symbol: market_cap} from fundamentals."""
    rows = query(
        "SELECT symbol, value FROM fundamentals WHERE metric = 'marketCap' AND value > 0"
    )
    return {r["symbol"]: r["value"] for r in rows}


def _match_company_to_ticker(company_name: str, universe: dict[str, str]) -> str | None:
    """Fuzzy match a company name to a ticker in the universe.

    universe: {symbol: name} from stock_universe table.
    Returns ticker or None if no match above 0.85 threshold.
    """
    if not company_name:
        return None

    company_lower = company_name.lower().strip()
    best_ticker = None
    best_ratio = 0.0

    for symbol, name in universe.items():
        if not name:
            continue
        name_lower = name.lower().strip()

        # Exact substring match (fast path)
        if company_lower in name_lower or name_lower in company_lower:
            return symbol

        ratio = SequenceMatcher(None, company_lower, name_lower).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_ticker = symbol

    if best_ratio >= MATCH_THRESHOLD:
        return best_ticker
    return None


def _safe_get(url: str, params: dict | None = None,
              timeout: int = 15) -> dict | list | None:
    """GET with rate limiting and error handling. Returns parsed JSON or None."""
    time.sleep(RATE_LIMIT_DELAY)
    try:
        resp = _session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("GET %s failed: %s", url, exc)
        return None


def _cutoff_date() -> str:
    """ISO date string for LOOKBACK_DAYS ago."""
    return (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()


# ── Source 1: WARN Act Layoff Filings ────────────────────────────────────

def _fetch_warn_scores(universe: dict[str, str],
                       market_caps: dict[str, float]) -> dict[str, float]:
    """Fetch WARN Act layoff data from DOL and score each matched ticker.

    Score logic:
      - 0 layoffs in 90 days → 75 (neutral-positive)
      - Significant layoffs relative to market cap → 10-30
    """
    print("  [1/5] WARN Act layoff filings ...")
    scores: dict[str, float] = {}
    raw_rows = []
    today_str = date.today().isoformat()
    cutoff = _cutoff_date()

    # DOL WARN search — attempt structured API
    url = "https://www.doleta.gov/layoff/warn_filing_search.cfm"
    try:
        # The DOL page is primarily HTML-based; try the API-style endpoint
        # If it fails, we degrade gracefully
        data = _safe_get(
            "https://enforcedata.dol.gov/api/warn",
            params={"page": "0", "per_page": str(MAX_RECORDS_PER_SOURCE)},
        )
    except Exception:
        data = None

    layoffs_by_ticker: dict[str, int] = {}

    if data and isinstance(data, list):
        for record in data[:MAX_RECORDS_PER_SOURCE]:
            company = record.get("company_name") or record.get("establishment_name", "")
            employees = record.get("number_affected") or record.get("employees_affected", 0)
            layoff_date = record.get("effective_date") or record.get("notice_date", "")

            try:
                employees = int(employees)
            except (ValueError, TypeError):
                employees = 0

            # Filter by date
            if layoff_date and layoff_date < cutoff:
                continue

            ticker = _match_company_to_ticker(company, universe)
            if ticker:
                layoffs_by_ticker[ticker] = layoffs_by_ticker.get(ticker, 0) + employees
                raw_rows.append((
                    ticker, today_str, "warn", "layoff",
                    "high" if employees > 500 else "medium",
                    json.dumps({"company": company, "employees": employees,
                                "date": layoff_date}),
                ))
        print(f"    Parsed {len(data)} WARN records, matched {len(layoffs_by_ticker)} tickers")
    elif isinstance(data, dict) and "results" in data:
        # Handle paginated JSON response
        results = data["results"][:MAX_RECORDS_PER_SOURCE]
        for record in results:
            company = record.get("company_name") or record.get("establishment_name", "")
            employees = record.get("number_affected") or record.get("employees_affected", 0)
            layoff_date = record.get("effective_date") or record.get("notice_date", "")

            try:
                employees = int(employees)
            except (ValueError, TypeError):
                employees = 0

            if layoff_date and layoff_date < cutoff:
                continue

            ticker = _match_company_to_ticker(company, universe)
            if ticker:
                layoffs_by_ticker[ticker] = layoffs_by_ticker.get(ticker, 0) + employees
                raw_rows.append((
                    ticker, today_str, "warn", "layoff",
                    "high" if employees > 500 else "medium",
                    json.dumps({"company": company, "employees": employees,
                                "date": layoff_date}),
                ))
        print(f"    Parsed {len(results)} WARN records, matched {len(layoffs_by_ticker)} tickers")
    else:
        print("    WARN data unavailable — using neutral scores")

    # Score: higher layoffs relative to market cap = lower score
    for symbol in universe:
        layoffs = layoffs_by_ticker.get(symbol, 0)
        if layoffs == 0:
            scores[symbol] = 75.0  # neutral-positive
        else:
            mcap = market_caps.get(symbol, 1e10)  # default 10B if unknown
            # layoffs per billion of market cap
            intensity = (layoffs / (mcap / 1e9)) if mcap > 0 else layoffs
            if intensity > 100:
                scores[symbol] = 10.0
            elif intensity > 50:
                scores[symbol] = 20.0
            elif intensity > 10:
                scores[symbol] = 30.0
            elif intensity > 1:
                scores[symbol] = 50.0
            else:
                scores[symbol] = 65.0

    # Store raw data
    if raw_rows:
        upsert_many(
            "gov_intel_raw",
            ["symbol", "date", "source", "event_type", "severity", "details"],
            raw_rows,
        )

    print(f"    Scored {len(scores)} symbols")
    return scores


# ── Source 2: OSHA Inspection Logs ───────────────────────────────────────

def _fetch_osha_scores(universe: dict[str, str]) -> dict[str, float]:
    """Fetch recent OSHA inspections and score matched tickers.

    Score:
      - No violations → 70
      - Serious violations → 30
      - Willful/repeat → 10
    """
    print("  [2/5] OSHA inspection logs ...")
    scores: dict[str, float] = {}
    raw_rows = []
    today_str = date.today().isoformat()

    data = _safe_get(
        "https://enforcedata.dol.gov/api/enforcement/osha_inspection",
        params={"page": "0", "per_page": str(MAX_RECORDS_PER_SOURCE)},
    )

    violations_by_ticker: dict[str, list[str]] = {}

    if data and isinstance(data, dict):
        results = data.get("results", data.get("data", []))
        if isinstance(results, list):
            cutoff = _cutoff_date()
            for record in results[:MAX_RECORDS_PER_SOURCE]:
                company = record.get("establishment_name", "")
                open_date = record.get("open_date", "")
                case_type = record.get("case_type", "")
                viol_type = record.get("violation_type", "")

                if open_date and open_date[:10] < cutoff:
                    continue

                ticker = _match_company_to_ticker(company, universe)
                if ticker:
                    if ticker not in violations_by_ticker:
                        violations_by_ticker[ticker] = []
                    violations_by_ticker[ticker].append(viol_type or case_type)
                    raw_rows.append((
                        ticker, today_str, "osha", case_type or "inspection",
                        "high" if "willful" in (viol_type or "").lower() else "medium",
                        json.dumps({"company": company, "date": open_date,
                                    "case_type": case_type,
                                    "violation_type": viol_type}),
                    ))
            print(f"    Parsed {len(results)} OSHA records, matched {len(violations_by_ticker)} tickers")
        else:
            print("    OSHA response format unexpected — using neutral scores")
    elif data and isinstance(data, list):
        cutoff = _cutoff_date()
        for record in data[:MAX_RECORDS_PER_SOURCE]:
            company = record.get("establishment_name", "")
            open_date = record.get("open_date", "")
            case_type = record.get("case_type", "")
            viol_type = record.get("violation_type", "")

            if open_date and open_date[:10] < cutoff:
                continue

            ticker = _match_company_to_ticker(company, universe)
            if ticker:
                if ticker not in violations_by_ticker:
                    violations_by_ticker[ticker] = []
                violations_by_ticker[ticker].append(viol_type or case_type)
                raw_rows.append((
                    ticker, today_str, "osha", case_type or "inspection",
                    "high" if "willful" in (viol_type or "").lower() else "medium",
                    json.dumps({"company": company, "date": open_date,
                                "case_type": case_type,
                                "violation_type": viol_type}),
                ))
        print(f"    Parsed {len(data)} OSHA records, matched {len(violations_by_ticker)} tickers")
    else:
        print("    OSHA data unavailable — using neutral scores")

    # Score each symbol
    for symbol in universe:
        viols = violations_by_ticker.get(symbol, [])
        if not viols:
            scores[symbol] = 70.0
        else:
            viols_lower = [v.lower() for v in viols]
            if any("willful" in v or "repeat" in v for v in viols_lower):
                scores[symbol] = 10.0
            elif any("serious" in v for v in viols_lower):
                scores[symbol] = 30.0
            else:
                scores[symbol] = 50.0

    if raw_rows:
        upsert_many(
            "gov_intel_raw",
            ["symbol", "date", "source", "event_type", "severity", "details"],
            raw_rows,
        )

    print(f"    Scored {len(scores)} symbols")
    return scores


# ── Source 3: EPA ECHO Permits/Violations ────────────────────────────────

def _fetch_epa_scores(universe: dict[str, str]) -> dict[str, float]:
    """Fetch EPA ECHO facility data and score matched tickers.

    New permits → bullish boost. Violations → penalty.
    """
    print("  [3/5] EPA ECHO permits & violations ...")
    scores: dict[str, float] = {}
    raw_rows = []
    today_str = date.today().isoformat()

    # Use ECHO facility search REST API
    data = _safe_get(
        "https://echodata.epa.gov/echo/facility_rest_services.get_facilities",
        params={
            "output": "JSON",
            "p_act": "Y",
            "p_ptype": "NPD",  # NPDES permits
            "responseset": str(MAX_RECORDS_PER_SOURCE),
        },
        timeout=30,
    )

    permits_by_ticker: dict[str, dict] = {}  # {ticker: {"permits": N, "violations": N}}

    if data and isinstance(data, dict):
        # ECHO returns nested structure
        results = data.get("Results", data.get("results", {}))
        if isinstance(results, dict):
            facilities = results.get("Facilities", results.get("facilities", []))
        elif isinstance(results, list):
            facilities = results
        else:
            facilities = []

        for fac in facilities[:MAX_RECORDS_PER_SOURCE]:
            name = fac.get("FacName") or fac.get("facility_name", "")
            violations = int(fac.get("CurrVioFlag", 0) or 0) if fac.get("CurrVioFlag") else 0
            permits = int(fac.get("TotalPenalties", 0) or 0) if fac.get("TotalPenalties") else 0

            ticker = _match_company_to_ticker(name, universe)
            if ticker:
                if ticker not in permits_by_ticker:
                    permits_by_ticker[ticker] = {"permits": 0, "violations": 0}
                permits_by_ticker[ticker]["permits"] += 1
                if violations or (fac.get("CurrVioFlag") in ("Y", "1", True)):
                    permits_by_ticker[ticker]["violations"] += 1

                severity = "high" if violations else "low"
                raw_rows.append((
                    ticker, today_str, "epa", "facility_record", severity,
                    json.dumps({"name": name, "violations": violations}),
                ))

        print(f"    Parsed {len(facilities)} EPA facilities, matched {len(permits_by_ticker)} tickers")
    else:
        print("    EPA data unavailable — using neutral scores")

    # Score
    for symbol in universe:
        info = permits_by_ticker.get(symbol)
        if not info:
            scores[symbol] = NEUTRAL_SCORE
        else:
            base = 60.0
            # New permits = bullish boost
            base += min(info["permits"] * 2, 20)
            # Violations = penalty
            base -= min(info["violations"] * 15, 40)
            scores[symbol] = max(10.0, min(90.0, base))

    if raw_rows:
        upsert_many(
            "gov_intel_raw",
            ["symbol", "date", "source", "event_type", "severity", "details"],
            raw_rows,
        )

    print(f"    Scored {len(scores)} symbols")
    return scores


# ── Source 4: FCC Filings ────────────────────────────────────────────────

def _fetch_fcc_scores(universe: dict[str, str]) -> dict[str, float]:
    """Fetch FCC ECFS filings and score matched tickers.

    Recent filings indicate capex investment (bullish). Normalize by sector.
    """
    print("  [4/5] FCC filings ...")
    scores: dict[str, float] = {}
    raw_rows = []
    today_str = date.today().isoformat()
    cutoff = _cutoff_date()

    # FCC ECFS API — search recent filings
    data = _safe_get(
        "https://publicapi.fcc.gov/ecfs/filings",
        params={
            "sort": "date_disseminated,DESC",
            "limit": str(MAX_RECORDS_PER_SOURCE),
            "date_disseminated": f"[gte]{cutoff}",
        },
        timeout=30,
    )

    filings_by_ticker: dict[str, int] = {}

    if data and isinstance(data, dict):
        filings = data.get("filings", data.get("results", []))
        if isinstance(filings, list):
            for filing in filings[:MAX_RECORDS_PER_SOURCE]:
                # FCC filings have filers with name fields
                filers = filing.get("filers", [])
                filed_date = filing.get("date_disseminated", "")
                for filer in filers if isinstance(filers, list) else []:
                    name = filer.get("name", "")
                    ticker = _match_company_to_ticker(name, universe)
                    if ticker:
                        filings_by_ticker[ticker] = filings_by_ticker.get(ticker, 0) + 1
                        raw_rows.append((
                            ticker, today_str, "fcc", "filing", "low",
                            json.dumps({"filer": name, "date": filed_date}),
                        ))
            print(f"    Parsed {len(filings)} FCC filings, matched {len(filings_by_ticker)} tickers")
        else:
            print("    FCC response format unexpected — using neutral scores")
    else:
        print("    FCC data unavailable — using neutral scores")

    # Score: filings = capex signal (bullish)
    for symbol in universe:
        count = filings_by_ticker.get(symbol, 0)
        if count == 0:
            scores[symbol] = NEUTRAL_SCORE
        elif count >= 5:
            scores[symbol] = 80.0  # heavy capex investment
        elif count >= 2:
            scores[symbol] = 70.0
        else:
            scores[symbol] = 60.0

    if raw_rows:
        upsert_many(
            "gov_intel_raw",
            ["symbol", "date", "source", "event_type", "severity", "details"],
            raw_rows,
        )

    print(f"    Scored {len(scores)} symbols")
    return scores


# ── Source 5: Lobbying Disclosures ───────────────────────────────────────

def _fetch_lobbying_scores(universe: dict[str, str]) -> dict[str, float]:
    """Fetch Senate lobbying disclosures and score matched tickers.

    Increasing lobbying spend = strategic intent shift (bullish).
    """
    print("  [5/5] Lobbying disclosures ...")
    scores: dict[str, float] = {}
    raw_rows = []
    today_str = date.today().isoformat()

    # Senate LDA API — quarterly filings
    data = _safe_get(
        "https://lda.senate.gov/api/v1/filings/",
        params={
            "filing_type": "Q",
            "page_size": str(MAX_RECORDS_PER_SOURCE),
            "ordering": "-dt_posted",
        },
        timeout=30,
    )

    spend_by_ticker: dict[str, float] = {}

    if data and isinstance(data, dict):
        results = data.get("results", [])
        if isinstance(results, list):
            for filing in results[:MAX_RECORDS_PER_SOURCE]:
                registrant = filing.get("registrant", {})
                name = registrant.get("name", "") if isinstance(registrant, dict) else ""
                amount = filing.get("income") or filing.get("expenses") or 0

                try:
                    amount = float(amount)
                except (ValueError, TypeError):
                    amount = 0.0

                ticker = _match_company_to_ticker(name, universe)
                if ticker:
                    spend_by_ticker[ticker] = spend_by_ticker.get(ticker, 0) + amount
                    raw_rows.append((
                        ticker, today_str, "lobbying", "quarterly_filing", "low",
                        json.dumps({"registrant": name, "amount": amount}),
                    ))
            print(f"    Parsed {len(results)} lobbying filings, matched {len(spend_by_ticker)} tickers")
        else:
            print("    Lobbying response format unexpected — using neutral scores")
    else:
        print("    Lobbying data unavailable — using neutral scores")

    # Score: higher spend = bullish (company investing in regulatory advantage)
    if spend_by_ticker:
        max_spend = max(spend_by_ticker.values()) if spend_by_ticker else 1.0
        for symbol in universe:
            spend = spend_by_ticker.get(symbol, 0)
            if spend == 0:
                scores[symbol] = NEUTRAL_SCORE
            else:
                # Normalize: highest spender gets ~80, lowest matched gets ~55
                normalized = (spend / max_spend) if max_spend > 0 else 0
                scores[symbol] = round(55 + normalized * 25, 1)
    else:
        for symbol in universe:
            scores[symbol] = NEUTRAL_SCORE

    if raw_rows:
        upsert_many(
            "gov_intel_raw",
            ["symbol", "date", "source", "event_type", "severity", "details"],
            raw_rows,
        )

    print(f"    Scored {len(scores)} symbols")
    return scores


# ── Table Creation ───────────────────────────────────────────────────────

def _ensure_tables():
    """Create gov_intel tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS gov_intel_raw (
            symbol TEXT,
            date TEXT,
            source TEXT,
            event_type TEXT,
            severity TEXT,
            details TEXT,
            PRIMARY KEY (symbol, date, source, event_type)
        );
        CREATE TABLE IF NOT EXISTS gov_intel_scores (
            symbol TEXT,
            date TEXT,
            gov_intel_score REAL,
            warn_score REAL,
            osha_score REAL,
            epa_score REAL,
            fcc_score REAL,
            lobbying_score REAL,
            details TEXT,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.commit()
    conn.close()


# ── Main Entry Point ────────────────────────────────────────────────────

def run():
    """Run the government intelligence module.

    Aggregates 5 data sources into a 0-100 gov_intel_score per symbol.
    Skips if last run was < 7 days ago.
    """
    init_db()
    _ensure_tables()

    print("\n" + "=" * 60)
    print("  GOVERNMENT INTELLIGENCE MODULE")
    print("=" * 60)

    if not _should_run():
        print("  Skipping — last run was within 7 days")
        print("=" * 60)
        return

    universe = _get_universe()
    if not universe:
        print("  No stock universe found — run daily_pipeline first")
        print("=" * 60)
        return

    print(f"  Universe: {len(universe)} symbols")
    market_caps = _get_market_caps()

    # Fetch scores from each source (graceful degradation)
    warn_scores: dict[str, float] = {}
    osha_scores: dict[str, float] = {}
    epa_scores: dict[str, float] = {}
    fcc_scores: dict[str, float] = {}
    lobby_scores: dict[str, float] = {}

    try:
        warn_scores = _fetch_warn_scores(universe, market_caps)
    except Exception as exc:
        print(f"    WARN source failed: {exc}")
        traceback.print_exc()

    try:
        osha_scores = _fetch_osha_scores(universe)
    except Exception as exc:
        print(f"    OSHA source failed: {exc}")
        traceback.print_exc()

    try:
        epa_scores = _fetch_epa_scores(universe)
    except Exception as exc:
        print(f"    EPA source failed: {exc}")
        traceback.print_exc()

    try:
        fcc_scores = _fetch_fcc_scores(universe)
    except Exception as exc:
        print(f"    FCC source failed: {exc}")
        traceback.print_exc()

    try:
        lobby_scores = _fetch_lobbying_scores(universe)
    except Exception as exc:
        print(f"    Lobbying source failed: {exc}")
        traceback.print_exc()

    # ── Composite scoring ────────────────────────────────────────────────
    print("\n  Computing composite gov_intel_score ...")
    today_str = date.today().isoformat()
    score_rows = []
    scored = 0
    non_neutral = 0

    for symbol in universe:
        w = warn_scores.get(symbol, NEUTRAL_SCORE)
        o = osha_scores.get(symbol, NEUTRAL_SCORE)
        e = epa_scores.get(symbol, NEUTRAL_SCORE)
        f = fcc_scores.get(symbol, NEUTRAL_SCORE)
        l = lobby_scores.get(symbol, NEUTRAL_SCORE)

        composite = round(
            w * WARN_WEIGHT
            + o * OSHA_WEIGHT
            + e * EPA_WEIGHT
            + f * FCC_WEIGHT
            + l * LOBBY_WEIGHT,
            1,
        )

        # Track how many have non-neutral data
        if any(s != NEUTRAL_SCORE for s in [w, o, e, f, l]):
            non_neutral += 1

        details = json.dumps({
            "warn": round(w, 1),
            "osha": round(o, 1),
            "epa": round(e, 1),
            "fcc": round(f, 1),
            "lobbying": round(l, 1),
        })

        score_rows.append((
            symbol, today_str, composite,
            round(w, 1), round(o, 1), round(e, 1),
            round(f, 1), round(l, 1), details,
        ))
        scored += 1

    upsert_many(
        "gov_intel_scores",
        ["symbol", "date", "gov_intel_score", "warn_score", "osha_score",
         "epa_score", "fcc_score", "lobbying_score", "details"],
        score_rows,
    )

    print(f"  Stored {scored} scores ({non_neutral} with non-neutral data)")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
