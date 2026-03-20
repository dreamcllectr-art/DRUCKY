"""Alpha Vantage technical indicators — second opinion layer.

Key: KFN3O6SD8JBMWJV0
Rate limit: 25 req/day → rotates through 903 stocks over ~36 days
Table: av_technical_indicators
"""
import logging
import time
import requests
from datetime import date, timedelta
from tools.db import get_conn, query, upsert_many
from tools.config import ALPHA_VANTAGE_API_KEY

logger = logging.getLogger(__name__)

AV_BASE = "https://www.alphavantage.co/query"
DAILY_LIMIT = 24  # Leave 1 request for overhead
REQUEST_DELAY = 12.5  # 5 per minute = 12s between requests


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS av_technical_indicators (
    symbol TEXT, date TEXT,
    rsi REAL, macd REAL, macd_signal REAL, macd_hist REAL,
    stoch_k REAL, stoch_d REAL, adx REAL, bb_upper REAL,
    bb_middle REAL, bb_lower REAL, bb_width REAL, obv REAL,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _get_indicator(symbol, function, **kwargs):
    params = {
        "function": function,
        "symbol": symbol,
        "apikey": ALPHA_VANTAGE_API_KEY,
        "datatype": "json",
    }
    params.update(kwargs)
    try:
        r = requests.get(AV_BASE, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.debug(f"AV {function} {symbol}: {e}")
        return {}


def _get_symbols_due():
    """Get symbols not updated in the last 36 days, batched to DAILY_LIMIT."""
    all_syms = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
    recent = {r["symbol"] for r in query(
        "SELECT DISTINCT symbol FROM av_technical_indicators WHERE date >= date('now', '-36 days')"
    )}
    due = [s for s in all_syms if s not in recent]
    return due[:DAILY_LIMIT]


def run():
    if not ALPHA_VANTAGE_API_KEY:
        print("  Alpha Vantage API key not set — skipping")
        return

    _ensure_tables()
    symbols = _get_symbols_due()
    if not symbols:
        print("  Alpha Vantage: all symbols up to date")
        return

    print(f"  Fetching Alpha Vantage technicals for {len(symbols)} symbols (daily batch)...")
    today = date.today().isoformat()
    rows = []

    for sym in symbols:
        try:
            # RSI
            rsi_data = _get_indicator(sym, "RSI", interval="daily", time_period=14, series_type="close")
            time.sleep(REQUEST_DELAY)

            rsi_key = list(rsi_data.get("Technical Analysis: RSI", {}).keys())
            rsi = float(rsi_data["Technical Analysis: RSI"][rsi_key[0]]["RSI"]) if rsi_key else None

            # MACD
            macd_data = _get_indicator(sym, "MACD", interval="daily", series_type="close")
            time.sleep(REQUEST_DELAY)

            macd_key = list(macd_data.get("Technical Analysis: MACD", {}).keys())
            macd = macd_sig = macd_hist = None
            if macd_key:
                md = macd_data["Technical Analysis: MACD"][macd_key[0]]
                macd = float(md.get("MACD", 0))
                macd_sig = float(md.get("MACD_Signal", 0))
                macd_hist = float(md.get("MACD_Hist", 0))

            rows.append((sym, today, rsi, macd, macd_sig, macd_hist,
                         None, None, None, None, None, None, None, None))
        except Exception as e:
            logger.debug(f"AV {sym}: {e}")

    if rows:
        upsert_many("av_technical_indicators",
                    ["symbol", "date", "rsi", "macd", "macd_signal", "macd_hist",
                     "stoch_k", "stoch_d", "adx", "bb_upper", "bb_middle",
                     "bb_lower", "bb_width", "obv"],
                    rows)
    print(f"  Alpha Vantage: {len(rows)} symbols updated")
