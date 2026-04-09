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
from tools.utils.rate_limiter import rate_limited
from tools.utils.module_logger import log_module_error

logger = logging.getLogger(__name__)

STOCKTWITS_BASE = "https://api.stocktwits.com/api/2/streams/symbol"


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


@rate_limited(max_retries=4, base_delay=1.0, max_delay=60.0)
def _fetch_symbol(symbol):
    url = f"{STOCKTWITS_BASE}/{symbol}.json"
    r = requests.get(url, timeout=10)
    if r.status_code == 429:
        r.status_code = 429  # triggers rate_limited retry via _RateLimitError check
        return r
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
    raw_score = bull_pct
    # Contrarian adjustment: extreme values get pulled toward 50
    if bull_pct > 80:
        raw_score = 80 - (bull_pct - 80) * 0.5
    elif bull_pct < 20:
        raw_score = 20 + (20 - bull_pct) * 0.5

    return (symbol, date.today().isoformat(),
            round(bull_pct, 1), round(bear_pct, 1),
            total, round(max(0, min(100, raw_score)), 1))


def run():
    _ensure_tables()
    symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
    if not symbols:
        print("  No symbols — skipping Stocktwits")
        return

    print(f"  Fetching Stocktwits sentiment for {len(symbols)} symbols...")
    rows = []
    for i, sym in enumerate(symbols):
        try:
            result = _fetch_symbol(sym)
            if result and not isinstance(result, requests.Response):
                rows.append(result)
        except Exception as e:
            log_module_error(module="stocktwits", phase="fetch", exc=e, severity="WARNING")
        time.sleep(0.1)  # 10 req/sec baseline; rate_limiter handles 429 backoff
        if (i + 1) % 100 == 0:
            print(f"    Progress: {i+1}/{len(symbols)}")

    if rows:
        upsert_many("stocktwits_sentiment",
                    ["symbol", "date", "bull_pct", "bear_pct", "msg_count", "sentiment_score"],
                    rows)
    print(f"  Stocktwits: {len(rows)} symbols with sentiment data")
