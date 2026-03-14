"""Insider Trading Intelligence — Form 4 Monitor & Signal Detector.

Tracks SEC Form 4 insider filings (officers, directors, 10%+ owners) and
FMP historical insider transactions. Detects:
  - Cluster buys (3+ insiders buying within 14 days)
  - Large C-suite purchases (>$200K)
  - Unusual volume (buy value > 3x historical avg)
  - Net selling pressure (negative signal)

Scores each symbol 0-100 and boosts/penalizes the existing smart_money_scores
conviction_score so insider intelligence flows through the 20% smartmoney
convergence weight.

Data sources: SEC EDGAR EFTS (Form 4), FMP /v4/insider-trading (free tier).
Usage: python -m tools.insider_trading
"""

import sys
import json
import time
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from collections import defaultdict

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    EDGAR_BASE, EDGAR_HEADERS, FMP_API_KEY, FMP_BASE,
    INSIDER_CLUSTER_WINDOW_DAYS, INSIDER_CLUSTER_MIN_COUNT,
    INSIDER_LARGE_BUY_THRESHOLD, INSIDER_UNUSUAL_VOLUME_MULT,
    INSIDER_BOOST_HIGH, INSIDER_BOOST_MED, INSIDER_SELL_PENALTY,
    INSIDER_FMP_BATCH_SIZE, INSIDER_LOOKBACK_DAYS,
)
from tools.db import init_db, upsert_many, query, get_conn

logger = logging.getLogger(__name__)

# SEC EDGAR full-text search for recent Form 4 filings
EDGAR_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_FULL_TEXT_URL = "https://efts.sec.gov/LATEST/search-index"

# C-suite titles that carry the most signal weight
CSUITE_TITLES = {
    "ceo", "chief executive", "president", "cfo", "chief financial",
    "coo", "chief operating", "cto", "chief technology",
    "chairman", "vice chairman", "director",
}


# ── Data Fetching ─────────────────────────────────────────────────────

def _fetch_fmp_insider(symbol: str) -> list[dict]:
    """Fetch insider transactions from FMP for a single symbol."""
    if not FMP_API_KEY:
        return []
    try:
        resp = requests.get(
            f"{FMP_BASE}/v4/insider-trading",
            params={"symbol": symbol, "limit": 100, "apikey": FMP_API_KEY},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
    except Exception as e:
        logger.debug(f"FMP insider fetch failed for {symbol}: {e}")
    return []


def _fetch_yfinance_insider(symbol: str) -> list[dict]:
    """Fetch insider transactions via yfinance (backup source)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        insiders = ticker.insider_transactions
        if insiders is None or insiders.empty:
            return []

        results = []
        for _, row in insiders.iterrows():
            tx_text = str(row.get("Transaction", "") or row.get("Text", "")).lower()
            if "purchase" in tx_text or "buy" in tx_text:
                tx_type = "BUY"
            elif "sale" in tx_text or "sell" in tx_text:
                tx_type = "SELL"
            elif "exercise" in tx_text:
                tx_type = "OPTION_EXERCISE"
            else:
                tx_type = "UNKNOWN"

            # Get date — yfinance uses "Start Date" or index
            tx_date = None
            if "Start Date" in insiders.columns:
                d = row.get("Start Date")
                if d is not None:
                    tx_date = str(d)[:10]
            if not tx_date:
                continue

            shares = abs(row.get("Shares", 0) or 0)
            value = abs(row.get("Value", 0) or 0)
            price = value / shares if shares > 0 else 0

            insider_name = str(row.get("Insider", "") or row.get("Insider Trading", ""))
            insider_title = str(row.get("Position", "") or row.get("Ownership", ""))

            url = f"yf://{symbol}/{tx_date}/{insider_name}"

            results.append({
                "symbol": symbol,
                "date": tx_date,
                "insider_name": insider_name,
                "insider_title": insider_title,
                "transaction_type": tx_type,
                "shares": int(shares),
                "price": round(price, 4) if price else None,
                "value": round(value, 2),
                "shares_owned_after": None,
                "filing_url": url,
                "source": "yfinance",
            })
        return results
    except Exception as e:
        logger.debug(f"yfinance insider fetch failed for {symbol}: {e}")
        return []


def _parse_fmp_transaction(tx: dict, symbol: str) -> dict | None:
    """Convert an FMP insider transaction to our standard format."""
    tx_type_raw = (tx.get("transactionType") or "").upper()
    if "PURCHASE" in tx_type_raw or "BUY" in tx_type_raw or tx_type_raw == "P-PURCHASE":
        tx_type = "BUY"
    elif "SALE" in tx_type_raw or "SELL" in tx_type_raw or tx_type_raw == "S-SALE":
        tx_type = "SELL"
    elif "GRANT" in tx_type_raw or "AWARD" in tx_type_raw or tx_type_raw in ("A-AWARD", "G-GIFT"):
        tx_type = "GRANT"
    elif "EXERCISE" in tx_type_raw or tx_type_raw == "M-EXEMPT":
        tx_type = "OPTION_EXERCISE"
    else:
        tx_type = tx_type_raw or "UNKNOWN"

    filing_date = tx.get("filingDate") or tx.get("transactionDate")
    if not filing_date:
        return None

    shares = abs(tx.get("securitiesTransacted") or 0)
    price = tx.get("price") or 0
    value = shares * price if price else 0

    # Build a unique filing URL from available data
    link = tx.get("link") or ""
    if not link:
        link = f"fmp://{symbol}/{filing_date}/{tx.get('reportingName', 'unknown')}"

    return {
        "symbol": symbol,
        "date": filing_date,
        "insider_name": tx.get("reportingName") or tx.get("reportingCik") or "",
        "insider_title": tx.get("typeOfOwner") or "",
        "transaction_type": tx_type,
        "shares": int(shares),
        "price": round(price, 4) if price else None,
        "value": round(value, 2),
        "shares_owned_after": tx.get("securitiesOwned"),
        "filing_url": link,
        "source": "fmp",
    }


def _fetch_edgar_form4_recent(symbols: set[str]) -> list[dict]:
    """Fetch recent Form 4 filings from SEC EDGAR full-text search.

    Uses the EFTS search API to find recent Form 4 filings, then matches
    them to our universe symbols.
    """
    results = []
    cutoff = (date.today() - timedelta(days=30)).isoformat()

    # Search for recent Form 4 filings
    try:
        resp = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": '"form 4"',
                "dateRange": "custom",
                "startdt": cutoff,
                "enddt": date.today().isoformat(),
                "forms": "4",
            },
            headers=EDGAR_HEADERS,
            timeout=30,
        )
        if resp.status_code != 200:
            # EFTS may not be available; fall back to FMP only
            logger.info(f"EDGAR EFTS returned {resp.status_code}, skipping")
            return []
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
    except Exception as e:
        logger.info(f"EDGAR EFTS search failed: {e}")
        return []

    for hit in hits[:500]:  # Cap at 500 to avoid overload
        source = hit.get("_source", {})
        # Extract ticker from filing
        tickers = source.get("tickers", [])
        for ticker in tickers:
            ticker_clean = ticker.upper().strip()
            if ticker_clean in symbols:
                filing_date = source.get("file_date") or source.get("period_of_report")
                if not filing_date:
                    continue
                results.append({
                    "symbol": ticker_clean,
                    "date": filing_date,
                    "insider_name": source.get("display_names", [""])[0] if source.get("display_names") else "",
                    "insider_title": "",  # Not always in EFTS results
                    "transaction_type": "UNKNOWN",  # Would need to parse XML
                    "shares": 0,
                    "price": None,
                    "value": 0,
                    "shares_owned_after": None,
                    "filing_url": f"https://www.sec.gov/Archives/edgar/data/{source.get('entity_id', '')}/{source.get('accession_no', '')}",
                    "source": "edgar",
                })

    return results


def fetch_all_transactions(universe_symbols: set[str]) -> list[dict]:
    """Fetch insider transactions from all sources for universe symbols.

    Primary: FMP (richer data, per-symbol).
    Secondary: EDGAR EFTS (broader coverage, less detail).
    Deduplicates by filing_url.
    """
    all_txs = []
    seen_urls = set()

    # Check what we already have in DB to avoid re-fetching
    cutoff = (date.today() - timedelta(days=INSIDER_LOOKBACK_DAYS)).isoformat()
    existing_urls = set()
    try:
        rows = query(
            "SELECT filing_url FROM insider_transactions WHERE date >= ?",
            [cutoff],
        )
        existing_urls = {r["filing_url"] for r in rows}
    except Exception:
        pass

    symbols_list = sorted(universe_symbols)

    # Probe FMP with a single symbol to check if it's responsive
    fmp_available = False
    if FMP_API_KEY:
        print("  Probing FMP API availability...")
        probe = _fetch_fmp_insider(symbols_list[0] if symbols_list else "AAPL")
        fmp_available = len(probe) > 0
        if fmp_available:
            # Process probe result
            for raw_tx in probe:
                parsed = _parse_fmp_transaction(raw_tx, symbols_list[0])
                if parsed and parsed["filing_url"] not in seen_urls and parsed["filing_url"] not in existing_urls and parsed["date"] >= cutoff:
                    seen_urls.add(parsed["filing_url"])
                    all_txs.append(parsed)

    if fmp_available:
        # FMP: fetch per symbol (most detailed data)
        print(f"  FMP online — fetching insider data for {len(symbols_list)} symbols...")
        fetched = 0
        for i, symbol in enumerate(symbols_list[1:], 1):  # Skip first (already probed)
            if i > 0 and i % INSIDER_FMP_BATCH_SIZE == 0:
                time.sleep(1.0)  # FMP rate limit

            txs = _fetch_fmp_insider(symbol)
            for raw_tx in txs:
                parsed = _parse_fmp_transaction(raw_tx, symbol)
                if not parsed:
                    continue
                if parsed["filing_url"] in seen_urls or parsed["filing_url"] in existing_urls:
                    continue
                if parsed["date"] < cutoff:
                    continue
                seen_urls.add(parsed["filing_url"])
                all_txs.append(parsed)
                fetched += 1

            time.sleep(0.12)  # ~8 req/sec

        print(f"  FMP: {fetched} new transactions")
    else:
        # Fallback: yfinance insider_transactions (always works, no API key needed)
        print(f"  FMP unavailable — falling back to yfinance for {len(symbols_list)} symbols...")
        fetched = 0
        for i, symbol in enumerate(symbols_list):
            txs = _fetch_yfinance_insider(symbol)
            for parsed in txs:
                if parsed["filing_url"] in seen_urls or parsed["filing_url"] in existing_urls:
                    continue
                if parsed["date"] < cutoff:
                    continue
                seen_urls.add(parsed["filing_url"])
                all_txs.append(parsed)
                fetched += 1

            # yfinance is local-ish but still rate-limit gently
            if i > 0 and i % 50 == 0:
                print(f"    ... {i}/{len(symbols_list)} symbols processed ({fetched} txs)")
                time.sleep(0.5)

        print(f"  yfinance: {fetched} new transactions from {len(symbols_list)} symbols")

    # EDGAR EFTS: broader scan (supplements FMP/yfinance)
    print("  Scanning EDGAR EFTS for recent Form 4 filings...")
    edgar_txs = _fetch_edgar_form4_recent(universe_symbols)
    edgar_new = 0
    for tx in edgar_txs:
        if tx["filing_url"] in seen_urls or tx["filing_url"] in existing_urls:
            continue
        seen_urls.add(tx["filing_url"])
        all_txs.append(tx)
        edgar_new += 1
    print(f"  EDGAR: {edgar_new} additional filings")

    return all_txs


# ── Signal Detection ──────────────────────────────────────────────────

def _is_csuite(title: str) -> bool:
    """Check if an insider title indicates C-suite or director level."""
    title_lower = (title or "").lower()
    return any(t in title_lower for t in CSUITE_TITLES)


def _detect_signals(symbol: str, txs: list[dict], today: str) -> dict | None:
    """Detect insider trading signals for a single symbol.

    Returns a signal dict or None if no meaningful activity.
    """
    if not txs:
        return None

    cutoff_30d = (date.today() - timedelta(days=30)).isoformat()
    cutoff_cluster = (date.today() - timedelta(days=INSIDER_CLUSTER_WINDOW_DAYS)).isoformat()

    # Separate buys and sells in last 30 days
    buys_30d = [t for t in txs if t["transaction_type"] == "BUY" and t["date"] >= cutoff_30d]
    sells_30d = [t for t in txs if t["transaction_type"] == "SELL" and t["date"] >= cutoff_30d]

    total_buy_value = sum(t["value"] for t in buys_30d)
    total_sell_value = sum(t["value"] for t in sells_30d)

    if total_buy_value == 0 and total_sell_value == 0:
        return None  # No meaningful activity

    # --- Cluster Buy Detection ---
    recent_buys = [t for t in buys_30d if t["date"] >= cutoff_cluster]
    distinct_buyers = len(set(t["insider_name"] for t in recent_buys if t["insider_name"]))
    cluster_buy = distinct_buyers >= INSIDER_CLUSTER_MIN_COUNT

    # --- Large C-suite Purchases ---
    large_buys = [
        t for t in buys_30d
        if t["value"] >= INSIDER_LARGE_BUY_THRESHOLD and _is_csuite(t["insider_title"])
    ]

    # --- Unusual Volume ---
    # Compare 30d buy value to historical average (from all stored transactions)
    hist_rows = query(
        """SELECT AVG(value) as avg_val FROM insider_transactions
           WHERE symbol = ? AND transaction_type = 'BUY' AND value > 0
           AND date < ?""",
        [symbol, cutoff_30d],
    )
    hist_avg = (hist_rows[0]["avg_val"] or 0) if hist_rows else 0
    avg_recent_buy = (total_buy_value / len(buys_30d)) if buys_30d else 0
    unusual_volume = (
        hist_avg > 0
        and avg_recent_buy > hist_avg * INSIDER_UNUSUAL_VOLUME_MULT
    )

    # --- Scoring ---
    score = 0.0

    # Cluster buy: strongest signal
    if cluster_buy:
        score += 35.0

    # Large C-suite purchases
    if large_buys:
        score += min(25.0, len(large_buys) * 12.5)

    # Multiple buyers (but below cluster threshold)
    if distinct_buyers >= 2 and not cluster_buy:
        score += 10.0

    # Unusual volume
    if unusual_volume:
        score += 15.0

    # Base buying activity (any buys = positive signal)
    if buys_30d and not cluster_buy:
        score += min(10.0, len(buys_30d) * 3.0)

    # Recency bonus: weight more recent activity higher
    most_recent_buy = max((t["date"] for t in buys_30d), default=None) if buys_30d else None
    if most_recent_buy:
        days_ago = (date.today() - date.fromisoformat(most_recent_buy)).days
        if days_ago <= 7:
            score *= 1.0  # Full weight
        elif days_ago <= 14:
            score *= 0.8
        else:
            score *= 0.6

    # Net selling penalty
    if total_sell_value > total_buy_value * 3:
        score -= 30.0
    elif total_sell_value > total_buy_value * 2:
        score -= 20.0
    elif total_sell_value > total_buy_value:
        score -= 10.0

    score = max(0.0, min(100.0, score))

    if score == 0 and total_sell_value == 0:
        return None

    # Find top buyer for narrative
    top_buyer = None
    if buys_30d:
        biggest = max(buys_30d, key=lambda t: t["value"])
        top_buyer = json.dumps({
            "name": biggest["insider_name"],
            "title": biggest["insider_title"],
            "value": biggest["value"],
            "date": biggest["date"],
        })

    # Build narrative
    parts = []
    if cluster_buy:
        parts.append(f"CLUSTER BUY: {distinct_buyers} insiders buying in {INSIDER_CLUSTER_WINDOW_DAYS}d")
    if large_buys:
        names = [t["insider_name"] for t in large_buys[:3]]
        parts.append(f"Large C-suite: {', '.join(names)}")
    if unusual_volume:
        parts.append(f"Unusual volume ({avg_recent_buy/hist_avg:.1f}x avg)" if hist_avg else "Unusual volume")
    if total_sell_value > total_buy_value:
        parts.append(f"Net selling: ${total_sell_value:,.0f} sold vs ${total_buy_value:,.0f} bought")
    if not parts:
        parts.append(f"Net insider buying: ${total_buy_value:,.0f} (30d)")

    return {
        "symbol": symbol,
        "date": today,
        "insider_score": round(score, 1),
        "cluster_buy": 1 if cluster_buy else 0,
        "cluster_count": distinct_buyers if cluster_buy else None,
        "large_buys_count": len(large_buys),
        "total_buy_value_30d": round(total_buy_value, 2),
        "total_sell_value_30d": round(total_sell_value, 2),
        "unusual_volume_flag": 1 if unusual_volume else 0,
        "top_buyer": top_buyer,
        "narrative": " | ".join(parts),
    }


# ── Smart Money Boost ─────────────────────────────────────────────────

def _boost_smart_money_scores(today: str):
    """Apply insider signal boosts/penalties to smart_money_scores.

    Reads today's insider_signals, finds matching smart_money_scores,
    and updates conviction_score in place.
    """
    insider_rows = query(
        "SELECT symbol, insider_score FROM insider_signals WHERE date = ?",
        [today],
    )
    if not insider_rows:
        return 0

    # Get latest smart money scores
    sm_rows = query("""
        SELECT s.symbol, s.date, s.conviction_score
        FROM smart_money_scores s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM smart_money_scores GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
    """)
    sm_by_symbol = {r["symbol"]: r for r in sm_rows}

    updates = 0
    with get_conn() as conn:
        for row in insider_rows:
            sym = row["symbol"]
            insider_score = row["insider_score"]

            if sym not in sm_by_symbol:
                # No smart money score exists — create one from insider data alone
                if insider_score >= 50:
                    conn.execute(
                        """INSERT OR REPLACE INTO smart_money_scores
                           (symbol, date, manager_count, conviction_score, top_holders)
                           VALUES (?, ?, 0, ?, '[]')""",
                        [sym, today, min(100, insider_score * 0.6)],
                    )
                    updates += 1
                continue

            sm = sm_by_symbol[sym]
            current = sm["conviction_score"] or 0

            if insider_score >= 70:
                boost = INSIDER_BOOST_HIGH
            elif insider_score >= 50:
                boost = INSIDER_BOOST_MED
            elif insider_score <= 20 and insider_score > 0:
                boost = INSIDER_SELL_PENALTY
            else:
                continue

            new_score = max(0, min(100, current + boost))
            if new_score != current:
                conn.execute(
                    """UPDATE smart_money_scores
                       SET conviction_score = ?
                       WHERE symbol = ? AND date = ?""",
                    [new_score, sym, sm["date"]],
                )
                updates += 1

    return updates


# ── Main Entry ────────────────────────────────────────────────────────

def run():
    """Main entry: fetch insider transactions, detect signals, boost smart money."""
    init_db()
    today = date.today().isoformat()
    print("Insider Trading: Scanning Form 4 filings & FMP data...")

    # Get stock universe
    universe_rows = query("SELECT symbol FROM stock_universe")
    universe_symbols = {r["symbol"] for r in universe_rows}
    if not universe_symbols:
        print("  No symbols in universe. Run fetch_stock_universe first.")
        return

    # Fetch transactions
    new_txs = fetch_all_transactions(universe_symbols)

    # Store transactions
    if new_txs:
        tx_rows = []
        for tx in new_txs:
            tx_rows.append((
                tx["symbol"], tx["date"], tx["insider_name"], tx["insider_title"],
                tx["transaction_type"], tx["shares"], tx["price"], tx["value"],
                tx["shares_owned_after"], tx["filing_url"], tx["source"],
            ))
        upsert_many(
            "insider_transactions",
            ["symbol", "date", "insider_name", "insider_title",
             "transaction_type", "shares", "price", "value",
             "shares_owned_after", "filing_url", "source"],
            tx_rows,
        )
        print(f"  Stored {len(tx_rows)} new insider transactions")

    # Detect signals per symbol
    print("  Detecting insider signals...")
    cutoff = (date.today() - timedelta(days=INSIDER_LOOKBACK_DAYS)).isoformat()

    # Load all recent transactions from DB (includes historical)
    all_tx_rows = query(
        """SELECT symbol, date, insider_name, insider_title,
                  transaction_type, shares, price, value
           FROM insider_transactions
           WHERE date >= ? AND symbol IN ({})""".format(
            ",".join(f"'{s}'" for s in universe_symbols)
        ),
        [cutoff],
    )

    # Group by symbol
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for row in all_tx_rows:
        by_symbol[row["symbol"]].append(row)

    signal_rows = []
    for symbol, txs in by_symbol.items():
        signal = _detect_signals(symbol, txs, today)
        if signal:
            signal_rows.append((
                signal["symbol"], signal["date"], signal["insider_score"],
                signal["cluster_buy"], signal["cluster_count"],
                signal["large_buys_count"], signal["total_buy_value_30d"],
                signal["total_sell_value_30d"], signal["unusual_volume_flag"],
                signal["top_buyer"], signal["narrative"],
            ))

    if signal_rows:
        upsert_many(
            "insider_signals",
            ["symbol", "date", "insider_score", "cluster_buy", "cluster_count",
             "large_buys_count", "total_buy_value_30d", "total_sell_value_30d",
             "unusual_volume_flag", "top_buyer", "narrative"],
            signal_rows,
        )

    # Boost smart money scores
    print("  Applying insider boosts to smart money scores...")
    boosts = _boost_smart_money_scores(today)
    print(f"  Applied {boosts} smart money score adjustments")

    # Summary
    cluster_buys = sum(1 for r in signal_rows if r[3] == 1)
    unusual = sum(1 for r in signal_rows if r[8] == 1)
    high_score = sum(1 for r in signal_rows if r[2] >= 70)

    print(f"\n  INSIDER TRADING SUMMARY:")
    print(f"  Transactions stored:  {len(new_txs)}")
    print(f"  Signals generated:    {len(signal_rows)}")
    print(f"  Cluster buys:         {cluster_buys}")
    print(f"  Unusual volume:       {unusual}")
    print(f"  High conviction (≥70): {high_score}")

    # Top signals
    top = sorted(signal_rows, key=lambda r: r[2], reverse=True)[:10]
    if top:
        print(f"\n  TOP INSIDER SIGNALS:")
        print(f"  {'Symbol':<8} {'Score':>6} {'Cluster':>8} {'Buy$30d':>12} {'Sell$30d':>12}")
        print(f"  {'-'*50}")
        for r in top:
            cl = "YES" if r[3] else ""
            print(f"  {r[0]:<8} {r[2]:>6.1f} {cl:>8} {r[6]:>12,.0f} {r[7]:>12,.0f}")

    print(f"\nInsider trading complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
