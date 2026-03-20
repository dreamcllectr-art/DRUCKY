"""Stocktwits retail sentiment fetcher.

Public API: https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json
No API key required.
Table: stocktwits_sentiment
"""
import logging
import time
import requests
from datetime import date
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)

STOCKTWITS_BASE = "https://api.stocktwits.com/api/2/streams/symbol"
REQUEST_DELAY = 0.5  # 2 req/sec to be safe


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS stocktwits_sentiment (
    symbol TEXT, date TEXT,
    bull_pct REAL, bear_pct REAL, msg_count INTEGER, sentiment_score REAL,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _fetch_symbol(symbol):
    url = f"{STOCKTWITS_BASE}/{symbol}.json"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 429:
            time.sleep(60)
            return None
        if r.status_code != 200:
            return None
        data = r.json()
        messages = data.get("messages", [])
        if not messages:
            return None

        bull_count = sum(1 for m in messages
                         if m.get("entities", {}).get("sentiment", {}) and
                         m["entities"]["sentiment"].get("basic") == "Bullish")
        bear_count = sum(1 for m in messages
                         if m.get("entities", {}).get("sentiment", {}) and
                         m["entities"]["sentiment"].get("basic") == "Bearish")
        total = len(messages)
        bull_pct = (bull_count / total * 100) if total > 0 else 50.0
        bear_pct = (bear_count / total * 100) if total > 0 else 50.0

        # Score: 0=extreme fear, 50=neutral, 100=extreme greed
        # Moderate bullishness (55-70%) with volume = momentum confirmation
        raw_score = bull_pct
        # Contrarian adjustment: extreme values get pulled toward 50
        if bull_pct > 80:
            raw_score = 80 - (bull_pct - 80) * 0.5  # pullback
        elif bull_pct < 20:
            raw_score = 20 + (20 - bull_pct) * 0.5  # contrarian buy

        return (symbol, date.today().isoformat(),
                round(bull_pct, 1), round(bear_pct, 1),
                total, round(max(0, min(100, raw_score)), 1))
    except Exception as e:
        logger.debug(f"Stocktwits {symbol}: {e}")
        return None


def run():
    _ensure_tables()
    symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
    if not symbols:
        print("  No symbols — skipping Stocktwits")
        return

    print(f"  Fetching Stocktwits sentiment for {len(symbols)} symbols (~{len(symbols)/2/60:.0f} min)...")
    rows = []
    for i, sym in enumerate(symbols):
        result = _fetch_symbol(sym)
        if result:
            rows.append(result)
        time.sleep(REQUEST_DELAY)
        if (i + 1) % 100 == 0:
            print(f"    Progress: {i+1}/{len(symbols)}")

    if rows:
        upsert_many("stocktwits_sentiment",
                    ["symbol", "date", "bull_pct", "bear_pct", "msg_count", "sentiment_score"],
                    rows)
    print(f"  Stocktwits: {len(rows)} symbols with sentiment data")
