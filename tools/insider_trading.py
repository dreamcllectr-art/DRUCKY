"""Insider Trading Intelligence — Form 4 Monitor & Signal Detector."""
import sys, json, time, logging
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
import requests
from tools.config import (EDGAR_BASE, EDGAR_HEADERS, FMP_API_KEY, FMP_BASE,
    INSIDER_CLUSTER_WINDOW_DAYS, INSIDER_CLUSTER_MIN_COUNT, INSIDER_LARGE_BUY_THRESHOLD,
    INSIDER_UNUSUAL_VOLUME_MULT, INSIDER_BOOST_HIGH, INSIDER_BOOST_MED, INSIDER_SELL_PENALTY,
    INSIDER_FMP_BATCH_SIZE, INSIDER_LOOKBACK_DAYS)
from tools.db import init_db, upsert_many, query, get_conn

logger = logging.getLogger(__name__)
CSUITE_TITLES = {"ceo", "chief executive", "president", "cfo", "chief financial", "coo", "chief operating",
    "cto", "chief technology", "chairman", "vice chairman", "director"}

def _fetch_fmp_insider(symbol):
    if not FMP_API_KEY: return []
    try:
        resp = requests.get(f"{FMP_BASE}/v4/insider-trading", params={"symbol": symbol, "limit": 100, "apikey": FMP_API_KEY}, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, list) else []
    except Exception: pass
    return []

def _fetch_yfinance_insider(symbol):
    try:
        import yfinance as yf
        insiders = yf.Ticker(symbol).insider_transactions
        if insiders is None or insiders.empty: return []
        results = []
        for _, row in insiders.iterrows():
            tx_text = str(row.get("Transaction", "") or row.get("Text", "")).lower()
            tx_type = "BUY" if any(w in tx_text for w in ["purchase", "buy"]) else "SELL" if any(w in tx_text for w in ["sale", "sell"]) else "OPTION_EXERCISE" if "exercise" in tx_text else "UNKNOWN"
            tx_date = str(row.get("Start Date"))[:10] if "Start Date" in insiders.columns and row.get("Start Date") is not None else None
            if not tx_date: continue
            shares = abs(row.get("Shares", 0) or 0); value = abs(row.get("Value", 0) or 0)
            # Heuristic: $0 value + UNKNOWN type = tax withholding on RSU vesting (Form F), not a market sale
            if tx_type == "UNKNOWN" and value == 0 and shares > 0:
                tx_type = "TAX_WITHHOLDING"
            price = value / shares if shares > 0 else 0
            results.append({"symbol": symbol, "date": tx_date, "insider_name": str(row.get("Insider", "") or ""),
                "insider_title": str(row.get("Position", "") or ""), "transaction_type": tx_type,
                "shares": int(shares), "price": round(price, 4) if price else None, "value": round(value, 2),
                "shares_owned_after": None, "filing_url": f"yf://{symbol}/{tx_date}/{row.get('Insider','')}", "source": "yfinance"})
        return results
    except Exception: return []

def _parse_fmp_transaction(tx, symbol):
    tx_type_raw = (tx.get("transactionType") or "").upper()
    if any(w in tx_type_raw for w in ["PURCHASE", "BUY"]) or tx_type_raw == "P-PURCHASE": tx_type = "BUY"
    elif any(w in tx_type_raw for w in ["SALE", "SELL"]) or tx_type_raw == "S-SALE": tx_type = "SELL"
    elif any(w in tx_type_raw for w in ["GRANT", "AWARD"]) or tx_type_raw in ("A-AWARD", "G-GIFT"): tx_type = "GRANT"
    elif "EXERCISE" in tx_type_raw or tx_type_raw == "M-EXEMPT": tx_type = "OPTION_EXERCISE"
    else: tx_type = tx_type_raw or "UNKNOWN"
    filing_date = tx.get("filingDate") or tx.get("transactionDate")
    if not filing_date: return None
    shares = abs(tx.get("securitiesTransacted") or 0); price = tx.get("price") or 0; value = shares * price if price else 0
    link = tx.get("link") or f"fmp://{symbol}/{filing_date}/{tx.get('reportingName', 'unknown')}"
    return {"symbol": symbol, "date": filing_date, "insider_name": tx.get("reportingName") or "",
        "insider_title": tx.get("typeOfOwner") or "", "transaction_type": tx_type, "shares": int(shares),
        "price": round(price, 4) if price else None, "value": round(value, 2),
        "shares_owned_after": tx.get("securitiesOwned"), "filing_url": link, "source": "fmp"}

def fetch_all_transactions(universe_symbols):
    all_txs, seen_urls = [], set()
    cutoff = (date.today() - timedelta(days=INSIDER_LOOKBACK_DAYS)).isoformat()
    existing_urls = set()
    try: existing_urls = {r["filing_url"] for r in query("SELECT filing_url FROM insider_transactions WHERE date >= ?", [cutoff])}
    except Exception: pass
    symbols_list = sorted(universe_symbols)
    def _add(parsed):
        if parsed and parsed["filing_url"] not in seen_urls and parsed["filing_url"] not in existing_urls and parsed["date"] >= cutoff:
            seen_urls.add(parsed["filing_url"]); all_txs.append(parsed); return True
        return False
    fmp_available = False
    if FMP_API_KEY:
        probe = _fetch_fmp_insider(symbols_list[0] if symbols_list else "AAPL")
        fmp_available = len(probe) > 0
        if fmp_available:
            for raw_tx in probe: _add(_parse_fmp_transaction(raw_tx, symbols_list[0]))
    if fmp_available:
        print(f"  FMP online — fetching insider data for {len(symbols_list)} symbols...")
        fetched = 0
        for i, symbol in enumerate(symbols_list[1:], 1):
            if i > 0 and i % INSIDER_FMP_BATCH_SIZE == 0: time.sleep(1.0)
            for raw_tx in _fetch_fmp_insider(symbol):
                if _add(_parse_fmp_transaction(raw_tx, symbol)): fetched += 1
            time.sleep(0.12)
        print(f"  FMP: {fetched} new transactions")
    else:
        print(f"  FMP unavailable — falling back to yfinance for {len(symbols_list)} symbols...")
        fetched = 0
        for i, symbol in enumerate(symbols_list):
            for parsed in _fetch_yfinance_insider(symbol):
                if _add(parsed): fetched += 1
            if i > 0 and i % 50 == 0: print(f"    ... {i}/{len(symbols_list)} ({fetched} txs)"); time.sleep(0.5)
        print(f"  yfinance: {fetched} new transactions")
    return all_txs

def _is_csuite(title): return any(t in (title or "").lower() for t in CSUITE_TITLES)

def _detect_signals(symbol, txs, today):
    if not txs: return None
    cutoff_30d = (date.today() - timedelta(days=30)).isoformat()
    cutoff_cluster = (date.today() - timedelta(days=INSIDER_CLUSTER_WINDOW_DAYS)).isoformat()
    buys_30d = [t for t in txs if t["transaction_type"] == "BUY" and t["date"] >= cutoff_30d]
    sells_30d = [t for t in txs if t["transaction_type"] == "SELL" and t["date"] >= cutoff_30d]
    total_buy = sum(t["value"] for t in buys_30d); total_sell = sum(t["value"] for t in sells_30d)
    if total_buy == 0 and total_sell == 0: return None
    # Use full cluster window (independent of 30d activity window) for director accumulation detection
    buys_cluster = [t for t in txs if t["transaction_type"] == "BUY" and t["date"] >= cutoff_cluster]
    distinct_buyers = len(set(t["insider_name"] for t in buys_cluster if t["insider_name"]))
    cluster_buy = distinct_buyers >= INSIDER_CLUSTER_MIN_COUNT
    large_buys = [t for t in buys_30d if t["value"] >= INSIDER_LARGE_BUY_THRESHOLD and _is_csuite(t["insider_title"])]
    hist_rows = query("SELECT AVG(value) as avg_val FROM insider_transactions WHERE symbol = ? AND transaction_type = 'BUY' AND value > 0 AND date < ?", [symbol, cutoff_30d])
    hist_avg = (hist_rows[0]["avg_val"] or 0) if hist_rows else 0
    avg_recent = (total_buy / len(buys_30d)) if buys_30d else 0
    unusual_volume = hist_avg > 0 and avg_recent > hist_avg * INSIDER_UNUSUAL_VOLUME_MULT
    score = 0.0
    if cluster_buy: score += 35.0
    if large_buys: score += min(25.0, len(large_buys) * 12.5)
    if distinct_buyers >= 2 and not cluster_buy: score += 10.0
    if unusual_volume: score += 15.0
    if buys_30d and not cluster_buy: score += min(10.0, len(buys_30d) * 3.0)
    if buys_30d:
        days_ago = (date.today() - date.fromisoformat(max(t["date"] for t in buys_30d))).days
        if days_ago > 14: score *= 0.6
        elif days_ago > 7: score *= 0.8
    if total_sell > total_buy * 3: score -= 30.0
    elif total_sell > total_buy * 2: score -= 20.0
    elif total_sell > total_buy: score -= 10.0
    score = max(0.0, min(100.0, score))
    if score == 0 and total_sell == 0: return None
    top_buyer = None
    if buys_30d:
        b = max(buys_30d, key=lambda t: t["value"])
        top_buyer = json.dumps({"name": b["insider_name"], "title": b["insider_title"], "value": b["value"], "date": b["date"]})
    parts = []
    if cluster_buy: parts.append(f"CLUSTER BUY: {distinct_buyers} insiders in {INSIDER_CLUSTER_WINDOW_DAYS}d")
    if large_buys: parts.append(f"Large C-suite: {', '.join(t['insider_name'] for t in large_buys[:3])}")
    if unusual_volume: parts.append(f"Unusual volume ({avg_recent/hist_avg:.1f}x avg)" if hist_avg else "Unusual volume")
    if total_sell > total_buy: parts.append(f"Net selling: ${total_sell:,.0f} vs ${total_buy:,.0f}")
    if not parts: parts.append(f"Net insider buying: ${total_buy:,.0f} (30d)")
    return {"symbol": symbol, "date": today, "insider_score": round(score, 1), "cluster_buy": 1 if cluster_buy else 0,
        "cluster_count": distinct_buyers if cluster_buy else None, "large_buys_count": len(large_buys),
        "total_buy_value_30d": round(total_buy, 2), "total_sell_value_30d": round(total_sell, 2),
        "unusual_volume_flag": 1 if unusual_volume else 0, "top_buyer": top_buyer, "narrative": " | ".join(parts)}

def _boost_smart_money_scores(today):
    insider_rows = query("SELECT symbol, insider_score FROM insider_signals WHERE date = ?", [today])
    if not insider_rows: return 0
    sm_map = {r["symbol"]: r for r in query("SELECT s.symbol, s.date, s.conviction_score FROM smart_money_scores s INNER JOIN (SELECT symbol, MAX(date) as mx FROM smart_money_scores GROUP BY symbol) m ON s.symbol = m.symbol AND s.date = m.mx")}
    updates = 0
    with get_conn() as conn:
        for row in insider_rows:
            sym, iscore = row["symbol"], row["insider_score"]
            if sym not in sm_map:
                if iscore >= 50:
                    conn.execute("INSERT OR REPLACE INTO smart_money_scores (symbol, date, manager_count, conviction_score, top_holders) VALUES (?, ?, 0, ?, '[]')", [sym, today, min(100, iscore * 0.6)])
                    updates += 1
                continue
            sm = sm_map[sym]; current = sm["conviction_score"] or 0
            boost = INSIDER_BOOST_HIGH if iscore >= 70 else INSIDER_BOOST_MED if iscore >= 50 else INSIDER_SELL_PENALTY if 0 < iscore <= 20 else None
            if boost is None: continue
            new_score = max(0, min(100, current + boost))
            if new_score != current:
                conn.execute("UPDATE smart_money_scores SET conviction_score = ? WHERE symbol = ? AND date = ?", [new_score, sym, sm["date"]])
                updates += 1
    return updates

def run():
    init_db(); today = date.today().isoformat()
    print("Insider Trading: Scanning Form 4 filings & FMP data...")
    universe_symbols = {r["symbol"] for r in query("SELECT symbol FROM stock_universe")}
    if not universe_symbols: print("  No symbols in universe."); return
    new_txs = fetch_all_transactions(universe_symbols)
    if new_txs:
        # Backfill missing prices from price_data using closing price on transaction date
        for tx in new_txs:
            if tx["price"] is None and tx["shares"] > 0:
                rows = query("SELECT close FROM price_data WHERE symbol=? AND date=? LIMIT 1", [tx["symbol"], tx["date"]])
                if rows:
                    tx["price"] = round(rows[0]["close"], 4)
                    tx["value"] = round(tx["shares"] * rows[0]["close"], 2)
        tx_rows = [(tx["symbol"], tx["date"], tx["insider_name"], tx["insider_title"], tx["transaction_type"],
            tx["shares"], tx["price"], tx["value"], tx["shares_owned_after"], tx["filing_url"], tx["source"]) for tx in new_txs]
        upsert_many("insider_transactions", ["symbol", "date", "insider_name", "insider_title", "transaction_type",
            "shares", "price", "value", "shares_owned_after", "filing_url", "source"], tx_rows)
        print(f"  Stored {len(tx_rows)} new insider transactions")
    print("  Detecting insider signals...")
    cutoff = (date.today() - timedelta(days=INSIDER_LOOKBACK_DAYS)).isoformat()
    sym_placeholders = ",".join(["?"] * len(universe_symbols))
    all_tx_rows = query(f"SELECT symbol, date, insider_name, insider_title, transaction_type, shares, price, value FROM insider_transactions WHERE date >= ? AND symbol IN ({sym_placeholders})", [cutoff] + list(universe_symbols))
    by_symbol = defaultdict(list)
    for row in all_tx_rows: by_symbol[row["symbol"]].append(row)
    signal_rows = []
    for symbol, txs in by_symbol.items():
        sig = _detect_signals(symbol, txs, today)
        if sig: signal_rows.append((sig["symbol"], sig["date"], sig["insider_score"], sig["cluster_buy"],
            sig["cluster_count"], sig["large_buys_count"], sig["total_buy_value_30d"],
            sig["total_sell_value_30d"], sig["unusual_volume_flag"], sig["top_buyer"], sig["narrative"]))
    if signal_rows:
        upsert_many("insider_signals", ["symbol", "date", "insider_score", "cluster_buy", "cluster_count",
            "large_buys_count", "total_buy_value_30d", "total_sell_value_30d", "unusual_volume_flag", "top_buyer", "narrative"], signal_rows)
    boosts = _boost_smart_money_scores(today)
    print(f"  {boosts} smart money boosts | {len(signal_rows)} signals | {sum(1 for r in signal_rows if r[3]==1)} clusters")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
