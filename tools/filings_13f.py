"""Institutional 13F Filing Tracker — Smart Money Intelligence.

Tracks quarterly 13F-HR filings from elite capital allocators:
  Druckenmiller, Burry, Tepper, Ackman, Tiger Global, Coatue, Viking

Data source: SEC EDGAR (free, no API key required).
Filing cadence: quarterly, 45-day delay after quarter-end.
The staleness is a feature — we trade the NEXT quarter with their disclosed thesis.

Outputs:
  - filings_13f: raw positions per manager per quarter
  - smart_money_scores: aggregated per-symbol conviction score (0-100)

Usage: python -m tools.filings_13f
"""

import sys
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    EDGAR_BASE, EDGAR_HEADERS, TRACKED_13F_MANAGERS,
    CUSIP_MAP_PATH, FMP_API_KEY, FMP_BASE,
)
from tools.db import init_db, upsert_many, query, get_conn


# ── Constants ──────────────────────────────────────────────────────────

EDGAR_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
EDGAR_SUBMISSIONS_URL = f"{EDGAR_BASE}/submissions/CIK{{cik}}.json"

# Manager reputation weights for conviction scoring (higher = more trusted)
MANAGER_WEIGHTS = {
    "0001536411": 1.0,   # Druckenmiller — top weight
    "0001649339": 0.90,  # Burry
    "0000813672": 0.85,  # Tepper
    "0001336920": 0.85,  # Ackman
    "0001167483": 0.75,  # Tiger Global
    "0001336528": 0.75,  # Coatue
    "0001103804": 0.75,  # Viking
}

# Staleness discounts based on days since period_of_report
STALENESS_THRESHOLDS = [
    (90,  1.00),
    (135, 0.70),
    (180, 0.40),
    (999, 0.15),
]

# Common false-positive CUSIPs / tickers to skip
SKIP_TICKERS = {"", "N/A", "CASH", "MONY"}


def _load_cusip_map() -> dict:
    """Load or build CUSIP -> ticker mapping from cache file."""
    if CUSIP_MAP_PATH.exists():
        try:
            with open(CUSIP_MAP_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cusip_map(cusip_map: dict):
    CUSIP_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CUSIP_MAP_PATH, "w") as f:
        json.dump(cusip_map, f)


def _build_cusip_map_from_sec() -> dict:
    """Download SEC company_tickers_exchange.json and build CUSIP -> ticker map."""
    print("  Building CUSIP map from SEC EDGAR...")
    try:
        resp = requests.get(EDGAR_TICKERS_EXCHANGE_URL, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        cusip_map = {}
        # Format: {"fields": [...], "data": [[cik, name, ticker, exchange, ...], ...]}
        fields = data.get("fields", [])
        ticker_idx = fields.index("ticker") if "ticker" in fields else 2
        cusip_idx = fields.index("cusip") if "cusip" in fields else -1
        if cusip_idx == -1:
            return {}
        for row in data.get("data", []):
            if len(row) > cusip_idx and row[cusip_idx]:
                cusip = str(row[cusip_idx]).strip()
                ticker = str(row[ticker_idx]).strip()
                if cusip and ticker:
                    cusip_map[cusip] = ticker
        print(f"  Built CUSIP map: {len(cusip_map):,} entries")
        return cusip_map
    except Exception as e:
        print(f"  Warning: Could not build CUSIP map from SEC: {e}")
        return {}


def _cusip_to_ticker_fmp(cusip: str) -> str | None:
    """Fallback: look up CUSIP via FMP search."""
    if not FMP_API_KEY:
        return None
    try:
        resp = requests.get(
            f"{FMP_BASE}/search",
            params={"query": cusip, "limit": 1, "apikey": FMP_API_KEY},
            timeout=10,
        )
        data = resp.json()
        if data and isinstance(data, list):
            return data[0].get("symbol")
    except Exception:
        pass
    return None


def _get_latest_13f_accession(cik: str) -> tuple[str, str, str] | None:
    """
    Fetch the most recent 13F-HR filing info from SEC EDGAR submissions API.
    Returns (accession_number, filing_date, period_of_report) or None.
    """
    url = EDGAR_SUBMISSIONS_URL.format(cik=cik)
    try:
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  Warning: Could not fetch submissions for CIK {cik}: {e}")
        return None

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    filing_dates = filings.get("filingDate", [])
    periods = filings.get("reportDate", [])

    for i, form in enumerate(forms):
        if form in ("13F-HR", "13F-HR/A"):
            return accessions[i], filing_dates[i], periods[i]
    return None


def _is_already_processed(cik: str, accession_number: str) -> bool:
    """Check if we've already stored this exact filing."""
    rows = query(
        "SELECT 1 FROM filings_13f WHERE cik = ? AND accession_number = ? LIMIT 1",
        [cik, accession_number],
    )
    return len(rows) > 0


def _fetch_prior_positions(cik: str, period_of_report: str) -> dict[str, int]:
    """Get previous quarter's share counts for a manager."""
    rows = query(
        """
        SELECT symbol, shares_held FROM filings_13f
        WHERE cik = ? AND period_of_report < ?
        ORDER BY period_of_report DESC
        """,
        [cik, period_of_report],
    )
    # Deduplicate: keep most recent prior period
    prior = {}
    for row in rows:
        sym = row["symbol"]
        if sym not in prior:
            prior[sym] = row["shares_held"] or 0
    return prior


def _compute_action(prior: int | None, current: int) -> str:
    if prior is None and current > 0:
        return "NEW"
    if prior is not None and prior > 0 and current == 0:
        return "EXIT"
    if prior is None or prior == 0:
        return "NEW" if current > 0 else "UNCHANGED"
    ratio = current / prior
    if ratio >= 1.10:
        return "ADD"
    if ratio <= 0.50:
        return "CUT"
    if ratio < 0.90:
        return "TRIM"
    return "UNCHANGED"


def _parse_13f_xml(cik: str, accession_number: str) -> list[dict]:
    """
    Download and parse 13F-HR information table XML from EDGAR.
    Returns list of position dicts.
    """
    acc_no_dashes = accession_number.replace("-", "")
    # Try primary XML document
    index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_dashes}/{accession_number}-index.json"
    try:
        resp = requests.get(index_url, headers=EDGAR_HEADERS, timeout=20)
        resp.raise_for_status()
        index = resp.json()
    except Exception as e:
        print(f"  Warning: Could not fetch filing index for {accession_number}: {e}")
        return []

    # Find the information table document
    xml_url = None
    for doc in index.get("documents", []):
        doc_type = doc.get("type", "").lower()
        filename = doc.get("filename", "").lower()
        if "information table" in doc_type or filename.endswith(".xml"):
            xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_dashes}/{doc.get('filename')}"
            break

    if not xml_url:
        # Try common filename pattern
        xml_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_dashes}/infotable.xml"

    try:
        resp = requests.get(xml_url, headers=EDGAR_HEADERS, timeout=30)
        resp.raise_for_status()
        content = resp.text
    except Exception as e:
        print(f"  Warning: Could not fetch XML for {accession_number}: {e}")
        return []

    return _parse_information_table(content)


def _parse_information_table(xml_content: str) -> list[dict]:
    """Parse SEC 13F XML information table into list of position dicts."""
    positions = []
    try:
        # Strip namespace for simpler parsing
        content = re.sub(r'\s+xmlns[^"]*"[^"]*"', '', xml_content)
        content = re.sub(r'<ns\d+:', '<', content)
        content = re.sub(r'</ns\d+:', '</', content)

        root = ET.fromstring(content)
        ns = {'': ''}

        def find_text(node, *tags) -> str:
            for tag in tags:
                el = node.find(f".//{tag}")
                if el is not None and el.text:
                    return el.text.strip()
            return ""

        for entry in root.iter("infoTable"):
            issuer = find_text(entry, "nameOfIssuer")
            cusip = find_text(entry, "cusip")
            value_str = find_text(entry, "value")
            inv_type = find_text(entry, "investmentDiscretion") or "COM"

            # Shares/principal
            shares_el = entry.find(".//shrsOrPrnAmt")
            shares = 0
            if shares_el is not None:
                amt = find_text(shares_el, "sshPrnamt", "sshOrPrnAmt")
                try:
                    shares = int(amt.replace(",", ""))
                except (ValueError, AttributeError):
                    shares = 0

            # Put/call
            put_call = find_text(entry, "putCall")
            if put_call:
                inv_type = put_call.upper()

            try:
                value = int(str(value_str).replace(",", ""))
            except (ValueError, AttributeError):
                value = 0

            if shares > 0 and cusip:
                positions.append({
                    "cusip": cusip.strip(),
                    "issuer": issuer,
                    "shares_held": shares,
                    "market_value": value,
                    "investment_type": inv_type or "COM",
                })
    except ET.ParseError as e:
        print(f"  Warning: XML parse error: {e}")

    return positions


def _compute_smart_money_scores(universe_symbols: set[str], today: str):
    """Aggregate all managers' latest positions into per-symbol conviction scores."""
    # Get latest period per manager
    rows = query(
        """
        SELECT cik, manager_name, symbol, shares_held, market_value,
               action, period_of_report, rank_in_portfolio, portfolio_pct
        FROM filings_13f
        WHERE symbol != ''
        GROUP BY cik, symbol
        HAVING period_of_report = MAX(period_of_report)
        """
    )

    # Group by symbol
    by_symbol: dict[str, list[dict]] = {}
    for row in rows:
        sym = row["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(row)

    score_rows = []
    for sym, positions in by_symbol.items():
        if sym not in universe_symbols:
            continue

        manager_count = len(positions)
        total_mv = sum(p["market_value"] or 0 for p in positions)
        net_change = sum(p.get("shares_held", 0) or 0 for p in positions
                        if p.get("action") in ("NEW", "ADD"))
        net_change -= sum(p.get("shares_held", 0) or 0 for p in positions
                         if p.get("action") in ("EXIT", "CUT"))
        new_pos = sum(1 for p in positions if p.get("action") == "NEW")
        exits = sum(1 for p in positions if p.get("action") == "EXIT")

        # Conviction score: weighted by manager reputation
        base_score = 0.0
        for p in positions:
            cik = p["cik"]
            weight = MANAGER_WEIGHTS.get(cik, 0.70)
            # Base: holding = 15 pts * weight
            base_score += 15.0 * weight
            # Bonus: NEW position = +10, ADD = +5
            if p.get("action") == "NEW":
                base_score += 10.0 * weight
            elif p.get("action") == "ADD":
                base_score += 5.0 * weight
            elif p.get("action") in ("EXIT", "CUT"):
                base_score -= 8.0 * weight
            # Concentration bonus: top 10 in portfolio
            rank = p.get("rank_in_portfolio") or 999
            if rank <= 5:
                base_score += 8.0 * weight
            elif rank <= 10:
                base_score += 4.0 * weight

        conviction_score = min(100.0, max(0.0, base_score))

        top_holders = json.dumps([
            {"manager": p["manager_name"], "portfolio_pct": p.get("portfolio_pct")}
            for p in sorted(positions, key=lambda x: x.get("portfolio_pct") or 0, reverse=True)[:5]
        ])

        score_rows.append((
            sym, today, manager_count, total_mv, net_change,
            new_pos, exits, conviction_score, top_holders,
        ))

    if score_rows:
        upsert_many(
            "smart_money_scores",
            ["symbol", "date", "manager_count", "total_market_value",
             "net_change_shares", "new_positions", "exits",
             "conviction_score", "top_holders"],
            score_rows,
        )
        print(f"  Stored smart money scores for {len(score_rows)} symbols")


def run():
    """Main entry: fetch latest 13F filings for all tracked managers."""
    init_db()
    today = date.today().isoformat()
    print("13F Filings: Loading smart money positions...")

    # Load/build CUSIP map
    cusip_map = _load_cusip_map()
    if len(cusip_map) < 100:
        cusip_map = _build_cusip_map_from_sec()
        if cusip_map:
            _save_cusip_map(cusip_map)
    cusip_fmp_cache: dict[str, str | None] = {}

    # Get stock universe for filtering
    universe_rows = query("SELECT symbol FROM stock_universe")
    universe_symbols = {r["symbol"] for r in universe_rows}

    new_filings = 0

    for cik, manager_name in TRACKED_13F_MANAGERS.items():
        print(f"\n  [{manager_name}]")
        time.sleep(0.15)  # SEC EDGAR rate limit: 10 req/sec

        filing_info = _get_latest_13f_accession(cik)
        if not filing_info:
            print(f"  No 13F filing found for {manager_name}")
            continue

        accession_number, filing_date, period_of_report = filing_info
        print(f"  Latest: {accession_number} (period: {period_of_report}, filed: {filing_date})")

        if _is_already_processed(cik, accession_number):
            print(f"  Already processed — skipping")
            continue

        time.sleep(0.15)
        positions = _parse_13f_xml(cik, accession_number)
        if not positions:
            print(f"  No positions parsed — skipping")
            continue

        print(f"  Parsed {len(positions)} positions")

        # Resolve CUSIPs to tickers
        ticker_positions = []
        for pos in positions:
            cusip = pos["cusip"]
            ticker = cusip_map.get(cusip)
            if not ticker:
                if cusip not in cusip_fmp_cache:
                    cusip_fmp_cache[cusip] = _cusip_to_ticker_fmp(cusip)
                    time.sleep(0.1)
                ticker = cusip_fmp_cache.get(cusip)
            if ticker and ticker not in SKIP_TICKERS:
                pos["symbol"] = ticker
                ticker_positions.append(pos)

        # Compute portfolio ranks and pcts
        total_value = sum(p["market_value"] for p in ticker_positions if p["market_value"]) or 1
        ticker_positions_sorted = sorted(ticker_positions, key=lambda x: x.get("market_value") or 0, reverse=True)

        # Get prior quarter positions for change detection
        prior_positions = _fetch_prior_positions(cik, period_of_report)

        rows = []
        for rank, pos in enumerate(ticker_positions_sorted, 1):
            symbol = pos["symbol"]
            prior_shares = prior_positions.get(symbol)
            current_shares = pos["shares_held"]
            action = _compute_action(prior_shares, current_shares)
            change_shares = current_shares - (prior_shares or 0)
            change_pct = (change_shares / prior_shares * 100) if prior_shares and prior_shares > 0 else None
            portfolio_pct = (pos["market_value"] / total_value * 100) if pos["market_value"] else None

            rows.append((
                cik, manager_name, symbol, period_of_report, filing_date,
                accession_number, cusip, current_shares, pos["market_value"],
                pos["investment_type"], prior_shares, change_shares, change_pct,
                action, rank, portfolio_pct,
            ))

        if rows:
            upsert_many(
                "filings_13f",
                ["cik", "manager_name", "symbol", "period_of_report", "filing_date",
                 "accession_number", "cusip", "shares_held", "market_value",
                 "investment_type", "prior_shares", "change_shares", "change_pct",
                 "action", "rank_in_portfolio", "portfolio_pct"],
                rows,
            )
            new_positions = sum(1 for r in rows if r[13] == "NEW")
            exits = sum(1 for r in rows if r[13] == "EXIT")
            print(f"  Stored {len(rows)} positions | NEW: {new_positions} | EXIT: {exits}")
            new_filings += 1

        # Update CUSIP map with new resolutions
        for cusip, ticker in cusip_fmp_cache.items():
            if ticker:
                cusip_map[cusip] = ticker
        _save_cusip_map(cusip_map)

    # Recompute smart money scores
    print(f"\n  Recomputing smart money scores...")
    _compute_smart_money_scores(universe_symbols, today)

    # Print summary of top smart money holdings
    top_rows = query(
        """
        SELECT s.symbol, s.conviction_score, s.manager_count, s.top_holders
        FROM smart_money_scores s
        WHERE s.date = (SELECT MAX(date) FROM smart_money_scores WHERE symbol = s.symbol)
        ORDER BY s.conviction_score DESC
        LIMIT 15
        """
    )
    if top_rows:
        print("\n  TOP SMART MONEY HOLDINGS:")
        print(f"  {'Symbol':<8} {'Score':>6} {'Managers':>8}")
        print(f"  {'-'*30}")
        for r in top_rows:
            print(f"  {r['symbol']:<8} {r['conviction_score']:>6.1f} {r['manager_count']:>8}")

    print(f"\n13F complete: {new_filings} new filings processed")


if __name__ == "__main__":
    run()
