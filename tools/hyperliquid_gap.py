"""Hyperliquid Weekend-to-CME Gap Arbitrage Monitor.

Tracks HIP-3 perp prices during weekends to predict Monday opening gaps.
Three capabilities:
  1. Weekend price snapshots (hourly Sat/Sun)
  2. Gap signal generation (20:00 UTC Sunday — optimal R²=0.73, slope≈1.0)
  3. Cross-deployer spread monitoring (same asset, different deployers)

Research backing: 100% directional accuracy (34/34 assets), R²=0.973,
14bps median error. Best signal at 20:00 UTC, not 23:00 when books thin.

Data source: Hyperliquid REST API (https://api.hyperliquid.xyz/info)
No API key needed — public data only.
Usage: python -m tools.hyperliquid_gap [--mode auto|snapshot|signal|backfill]
"""

import sys
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from itertools import combinations

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    HL_API_BASE, HL_INSTRUMENTS, HL_DEPLOYERS,
    HL_OPTIMAL_SIGNAL_TIME, HL_CROSS_DEPLOYER_SPREAD_THRESHOLD_BPS,
    HL_BOOK_THIN_WARNING_PCT, HL_GAP_ALERT_THRESHOLD_PCT,
    HL_DEPLOYER_ALERT_THRESHOLD_BPS, HL_TICKER_TO_HL_SYMBOLS,
    HL_CROSS_DEPLOYER_TICKERS, SMTP_USER, SMTP_PASS, EMAIL_TO,
)
from tools.db import init_db, upsert_many, query, get_conn

logger = logging.getLogger(__name__)

INFO_URL = f"{HL_API_BASE}/info"
REQUEST_TIMEOUT = 15


# ── Hyperliquid API ─────────────────────────────────────────────────

def _post_info(payload: dict) -> dict | list | None:
    """POST to /info endpoint with retry."""
    for attempt in range(3):
        try:
            r = requests.post(INFO_URL, json=payload, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if data is None:
                return None
            return data
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.warning(f"HL API attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                time.sleep(1 * (attempt + 1))
    return None


def fetch_all_mids() -> dict[str, float]:
    """Fetch mid prices for all tracked instruments across all deployers.

    Returns: dict of hl_symbol -> mid_price
    """
    all_mids = {}
    for dex in HL_DEPLOYERS:
        data = _post_info({"type": "allMids", "dex": dex})
        if not data or not isinstance(data, dict):
            logger.warning(f"No mids returned for deployer {dex}")
            continue
        for symbol, price_str in data.items():
            if symbol in HL_INSTRUMENTS:
                try:
                    all_mids[symbol] = float(price_str)
                except (ValueError, TypeError):
                    pass
    logger.info(f"Fetched mids for {len(all_mids)}/{len(HL_INSTRUMENTS)} tracked instruments")
    return all_mids


def fetch_l2_book(hl_symbol: str) -> dict | None:
    """Fetch L2 order book for a specific instrument.

    Returns: {"bid": float, "ask": float, "spread_bps": float,
              "depth_bid_usd": float, "depth_ask_usd": float}
    """
    data = _post_info({"type": "l2Book", "coin": hl_symbol})
    if not data or "levels" not in data:
        return None

    levels = data["levels"]
    if len(levels) < 2 or not levels[0] or not levels[1]:
        return None

    # levels[0] = bids (descending), levels[1] = asks (ascending)
    bids = levels[0]
    asks = levels[1]

    best_bid = float(bids[0]["px"])
    best_ask = float(asks[0]["px"])
    mid = (best_bid + best_ask) / 2

    spread_bps = ((best_ask - best_bid) / mid) * 10_000 if mid > 0 else 0

    # Compute book depth in USD (top 10 levels)
    depth_bid_usd = sum(float(b["px"]) * float(b["sz"]) for b in bids[:10])
    depth_ask_usd = sum(float(a["px"]) * float(a["sz"]) for a in asks[:10])

    return {
        "bid": best_bid,
        "ask": best_ask,
        "spread_bps": round(spread_bps, 2),
        "depth_bid_usd": round(depth_bid_usd, 2),
        "depth_ask_usd": round(depth_ask_usd, 2),
    }


def _get_friday_close(ticker: str) -> float | None:
    """Get most recent Friday close from price_data table or yfinance fallback."""
    # Try DB first (works for stocks in universe + commodities)
    rows = query(
        """SELECT close FROM price_data
           WHERE symbol = ? AND close IS NOT NULL
           ORDER BY date DESC LIMIT 1""",
        [ticker],
    )
    if rows and rows[0]["close"]:
        return rows[0]["close"]

    # Fallback: yfinance for futures/ETFs not in DB
    try:
        import yfinance as yf
        data = yf.download(ticker, period="5d", progress=False, auto_adjust=True)
        if not data.empty:
            close_val = data["Close"].iloc[-1]
            # Handle MultiIndex columns from yfinance
            if hasattr(close_val, "values"):
                return float(close_val.values[0])
            return float(close_val)
    except Exception as e:
        logger.warning(f"yfinance fallback failed for {ticker}: {e}")
    return None


# ── Snapshot Collection ─────────────────────────────────────────────

def collect_snapshots() -> int:
    """Fetch current prices + book depth for all HL instruments.

    Designed to run every hour during weekends.
    Returns: number of snapshots stored
    """
    now_utc = datetime.now(timezone.utc)
    ts = now_utc.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Fetch all mids in bulk (one call per deployer)
    mids = fetch_all_mids()
    if not mids:
        logger.error("No mids fetched — aborting snapshot")
        return 0

    # 2. For each instrument, fetch L2 book (with rate limiting)
    snapshot_rows = []
    for hl_sym, mid_price in mids.items():
        meta = HL_INSTRUMENTS[hl_sym]
        book = fetch_l2_book(hl_sym)
        time.sleep(0.1)  # Rate limit: ~10 req/s

        row = (
            hl_sym,
            meta["deployer"],
            meta["ticker"],
            ts,
            mid_price,
            book["bid"] if book else None,
            book["ask"] if book else None,
            book["spread_bps"] if book else None,
            book["depth_bid_usd"] if book else None,
            book["depth_ask_usd"] if book else None,
            None,  # funding_rate (future enhancement)
            None,  # open_interest (future enhancement)
        )
        snapshot_rows.append(row)

    # 3. Store snapshots
    upsert_many(
        "hl_price_snapshots",
        ["hl_symbol", "deployer", "traditional_ticker", "timestamp",
         "mid_price", "bid", "ask", "spread_bps",
         "book_depth_bid_usd", "book_depth_ask_usd",
         "funding_rate", "open_interest"],
        snapshot_rows,
    )

    # 4. Check cross-deployer spreads
    deployer_alerts = _check_cross_deployer_spreads(mids, ts)
    if deployer_alerts:
        logger.info(f"Found {len(deployer_alerts)} cross-deployer divergences > threshold")

    logger.info(f"Stored {len(snapshot_rows)} snapshots at {ts}")
    return len(snapshot_rows)


def _check_cross_deployer_spreads(
    mids: dict[str, float], ts: str
) -> list[dict]:
    """For tickers with 2+ deployers, compute pairwise spreads."""
    alerts = []
    spread_rows = []

    for ticker, hl_symbols in HL_CROSS_DEPLOYER_TICKERS.items():
        # Get prices for this ticker across deployers
        prices = {}
        for sym in hl_symbols:
            if sym in mids:
                prices[sym] = mids[sym]

        if len(prices) < 2:
            continue

        # Compute pairwise spreads
        for (sym_a, px_a), (sym_b, px_b) in combinations(prices.items(), 2):
            dep_a = HL_INSTRUMENTS[sym_a]["deployer"]
            dep_b = HL_INSTRUMENTS[sym_b]["deployer"]
            mid = (px_a + px_b) / 2
            if mid == 0:
                continue

            spread_bps = abs(px_a - px_b) / mid * 10_000
            direction = f"{dep_a} > {dep_b}" if px_a > px_b else f"{dep_b} > {dep_a}"

            spread_rows.append((
                ticker, dep_a, dep_b, ts,
                px_a, px_b, round(spread_bps, 2), direction,
            ))

            if spread_bps >= HL_CROSS_DEPLOYER_SPREAD_THRESHOLD_BPS:
                alerts.append({
                    "ticker": ticker,
                    "deployer_a": dep_a, "deployer_b": dep_b,
                    "spread_bps": spread_bps, "direction": direction,
                })

    if spread_rows:
        upsert_many(
            "hl_deployer_spreads",
            ["traditional_ticker", "deployer_a", "deployer_b", "timestamp",
             "price_a", "price_b", "spread_bps", "spread_direction"],
            spread_rows,
        )

    return alerts


# ── Gap Signal Generation ──────────────────────────────────────────

def generate_gap_signals() -> list[dict]:
    """Generate predicted Monday gap signals.

    For each instrument:
      1. Get current HL mid price
      2. Get Friday close from price_data (or yfinance)
      3. Compute HL weekend return as predicted gap (slope≈1.0)
      4. Assign confidence based on book depth + spread
      5. Store in hl_gap_signals
    """
    now_utc = datetime.now(timezone.utc)
    weekend_date = now_utc.strftime("%Y-%m-%d")

    mids = fetch_all_mids()
    if not mids:
        logger.error("No mids for gap signal generation")
        return []

    # Group by traditional ticker — use best deployer (lowest spread)
    # Only include gap_eligible instruments (1:1 price mapping with traditional ticker)
    ticker_best: dict[str, dict] = {}
    for hl_sym, mid_price in mids.items():
        meta = HL_INSTRUMENTS[hl_sym]
        if not meta.get("gap_eligible", True):
            continue  # Skip non-1:1 priced instruments

        ticker = meta["ticker"]

        book = fetch_l2_book(hl_sym)
        time.sleep(0.1)

        spread = book["spread_bps"] if book else 9999
        if ticker not in ticker_best or spread < ticker_best[ticker].get("spread", 9999):
            ticker_best[ticker] = {
                "hl_symbol": hl_sym,
                "deployer": meta["deployer"],
                "mid_price": mid_price,
                "spread_bps": spread,
                "book": book,
            }

    signals = []
    signal_rows = []

    for ticker, best in ticker_best.items():
        friday_close = _get_friday_close(ticker)
        if not friday_close or friday_close <= 0:
            logger.debug(f"No Friday close for {ticker}, skipping")
            continue

        hl_price = best["mid_price"]
        weekend_return = (hl_price - friday_close) / friday_close * 100
        predicted_gap = weekend_return  # slope≈1.0 per research

        direction = "UP" if predicted_gap > 0 else "DOWN" if predicted_gap < 0 else "FLAT"

        # Confidence scoring
        confidence = _compute_confidence(
            best["hl_symbol"],
            best["book"],
            best["spread_bps"],
        )

        # Book depth vs Saturday avg
        depth_change = _compute_book_depth_change(best["hl_symbol"])

        signal = {
            "traditional_ticker": ticker,
            "weekend_date": weekend_date,
            "friday_close": friday_close,
            "hl_price_20utc": hl_price,
            "hl_weekend_return_pct": round(weekend_return, 4),
            "predicted_gap_pct": round(predicted_gap, 4),
            "predicted_direction": direction,
            "confidence": confidence,
            "deployer": best["deployer"],
            "hl_symbol": best["hl_symbol"],
            "book_depth_vs_saturday_pct": depth_change,
        }
        signals.append(signal)

        signal_rows.append((
            ticker, weekend_date, friday_close, hl_price,
            round(weekend_return, 4), round(predicted_gap, 4),
            direction, confidence,
            None, None, None, None,  # actual_open/gap/correct/error — filled by backfill
            depth_change,
            best["deployer"], best["hl_symbol"],
        ))

    if signal_rows:
        upsert_many(
            "hl_gap_signals",
            ["traditional_ticker", "weekend_date", "friday_close",
             "hl_price_20utc", "hl_weekend_return_pct", "predicted_gap_pct",
             "predicted_direction", "confidence",
             "actual_open", "actual_gap_pct", "direction_correct", "error_bps",
             "book_depth_vs_saturday_pct", "deployer", "hl_symbol"],
            signal_rows,
        )

    logger.info(f"Generated {len(signals)} gap signals for {weekend_date}")

    # Alert on large predicted gaps
    large_gaps = [s for s in signals if abs(s["predicted_gap_pct"]) >= HL_GAP_ALERT_THRESHOLD_PCT]
    if large_gaps:
        _send_gap_alerts(large_gaps)

    return signals


def _compute_confidence(
    hl_symbol: str,
    book: dict | None,
    spread_bps: float,
) -> float:
    """Confidence score 0-100 for a gap prediction.

    Higher when: tight spread, deep book.
    Lower when: wide spread, thin book.
    """
    score = 50.0  # baseline

    if book:
        # Spread component (tight = good): <10bps → +25, >200bps → -25
        if spread_bps < 10:
            score += 25
        elif spread_bps < 30:
            score += 15
        elif spread_bps < 50:
            score += 5
        elif spread_bps < 100:
            score -= 5
        elif spread_bps < 200:
            score -= 15
        else:
            score -= 25

        # Book depth component (deeper = better)
        total_depth = (book.get("depth_bid_usd", 0) or 0) + (book.get("depth_ask_usd", 0) or 0)
        if total_depth > 500_000:
            score += 20
        elif total_depth > 100_000:
            score += 10
        elif total_depth > 20_000:
            score += 0
        elif total_depth > 5_000:
            score -= 10
        else:
            score -= 20
    else:
        score -= 30  # No book data = low confidence

    return max(0, min(100, round(score, 1)))


def _compute_book_depth_change(hl_symbol: str) -> float | None:
    """Compare current book depth vs Saturday average.

    Returns: percentage change (negative = thinning)
    """
    now_utc = datetime.now(timezone.utc)
    saturday = now_utc - timedelta(days=now_utc.weekday() - 5) if now_utc.weekday() == 6 else now_utc

    rows = query(
        """SELECT AVG(book_depth_bid_usd + book_depth_ask_usd) as avg_depth
           FROM hl_price_snapshots
           WHERE hl_symbol = ?
             AND timestamp >= ?
             AND timestamp < ?
             AND book_depth_bid_usd IS NOT NULL""",
        [
            hl_symbol,
            saturday.strftime("%Y-%m-%d 00:00:00"),
            saturday.strftime("%Y-%m-%d 23:59:59"),
        ],
    )

    if not rows or not rows[0]["avg_depth"]:
        return None

    saturday_avg = rows[0]["avg_depth"]

    # Get latest snapshot depth
    latest = query(
        """SELECT (book_depth_bid_usd + book_depth_ask_usd) as current_depth
           FROM hl_price_snapshots
           WHERE hl_symbol = ? AND book_depth_bid_usd IS NOT NULL
           ORDER BY timestamp DESC LIMIT 1""",
        [hl_symbol],
    )

    if not latest or not latest[0]["current_depth"]:
        return None

    current = latest[0]["current_depth"]
    if saturday_avg == 0:
        return None

    return round((current - saturday_avg) / saturday_avg * 100, 1)


# ── Backfill / Accuracy Tracking ───────────────────────────────────

def backfill_actuals() -> int:
    """On Monday after market open, fetch actual open prices and compute accuracy.

    Updates hl_gap_signals with actual_open, actual_gap_pct,
    direction_correct, error_bps.
    """
    # Get signals missing actuals from the last 7 days
    pending = query(
        """SELECT traditional_ticker, weekend_date, friday_close,
                  predicted_gap_pct, predicted_direction
           FROM hl_gap_signals
           WHERE actual_open IS NULL
             AND weekend_date >= date('now', '-7 days')""",
    )

    if not pending:
        logger.info("No pending signals to backfill")
        return 0

    updated = 0
    for row in pending:
        ticker = row["traditional_ticker"]
        friday_close = row["friday_close"]

        # Get Monday open price
        actual_open = _get_monday_open(ticker)
        if actual_open is None:
            continue

        actual_gap_pct = (actual_open - friday_close) / friday_close * 100
        predicted_gap = row["predicted_gap_pct"]

        # Direction correct if both positive or both negative
        direction_correct = 1 if (predicted_gap * actual_gap_pct > 0) else 0
        # If both are essentially 0 (<5bps), count as correct
        if abs(predicted_gap) < 0.05 and abs(actual_gap_pct) < 0.05:
            direction_correct = 1

        error_bps = abs(predicted_gap - actual_gap_pct) * 100  # in basis points

        with get_conn() as conn:
            conn.execute(
                """UPDATE hl_gap_signals
                   SET actual_open = ?, actual_gap_pct = ?,
                       direction_correct = ?, error_bps = ?
                   WHERE traditional_ticker = ? AND weekend_date = ?""",
                [
                    round(actual_open, 4), round(actual_gap_pct, 4),
                    direction_correct, round(error_bps, 2),
                    ticker, row["weekend_date"],
                ],
            )
        updated += 1

    logger.info(f"Backfilled {updated}/{len(pending)} gap signals with actuals")
    return updated


def _get_monday_open(ticker: str) -> float | None:
    """Get Monday open price from price_data or yfinance."""
    # Try DB
    rows = query(
        """SELECT open FROM price_data
           WHERE symbol = ? AND open IS NOT NULL
           ORDER BY date DESC LIMIT 1""",
        [ticker],
    )
    if rows and rows[0]["open"]:
        return rows[0]["open"]

    # Fallback: yfinance
    try:
        import yfinance as yf
        data = yf.download(ticker, period="1d", progress=False, auto_adjust=True)
        if not data.empty:
            open_val = data["Open"].iloc[0]
            if hasattr(open_val, "values"):
                return float(open_val.values[0])
            return float(open_val)
    except Exception as e:
        logger.warning(f"yfinance fallback for Monday open failed for {ticker}: {e}")
    return None


# ── Alerting ────────────────────────────────────────────────────────

def _send_gap_alerts(signals: list[dict]):
    """Send email alerts for large predicted gaps."""
    if not SMTP_USER or not EMAIL_TO:
        logger.info("SMTP not configured — skipping email alert")
        return

    try:
        import smtplib
        from email.mime.text import MIMEText

        lines = ["HYPERLIQUID GAP ALERTS", "=" * 40, ""]
        for s in sorted(signals, key=lambda x: abs(x["predicted_gap_pct"]), reverse=True):
            emoji = "↑" if s["predicted_direction"] == "UP" else "↓"
            lines.append(
                f"{emoji} {s['traditional_ticker']}: "
                f"{s['predicted_gap_pct']:+.2f}% gap predicted "
                f"(HL: {s['hl_price_20utc']:.2f} vs Fri: {s['friday_close']:.2f}) "
                f"[confidence: {s['confidence']:.0f}]"
            )
        lines.append("")
        lines.append(f"Generated at 20:00 UTC — optimal signal window")
        lines.append(f"Source: {signals[0]['hl_symbol'].split(':')[0]} deployer on Hyperliquid")

        msg = MIMEText("\n".join(lines))
        msg["Subject"] = f"HL Gap Alert: {len(signals)} large moves predicted"
        msg["From"] = SMTP_USER
        msg["To"] = EMAIL_TO

        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.send_message(msg)

        logger.info(f"Sent gap alert email with {len(signals)} signals")
    except Exception as e:
        logger.error(f"Failed to send gap alert email: {e}")


# ── Entrypoints ─────────────────────────────────────────────────────

def run(mode: str = "auto"):
    """Main entrypoint.

    Modes:
      - auto: detect current time → snapshot on weekends, signal at Sunday 20:00+,
              backfill on Monday
      - snapshot: force snapshot collection
      - signal: force gap signal generation
      - backfill: force actual price backfill
    """
    init_db()
    now = datetime.now(timezone.utc)

    if mode == "auto":
        weekday = now.weekday()  # 0=Mon, 5=Sat, 6=Sun
        hour = now.hour

        if weekday in (5, 6):  # Weekend
            n = collect_snapshots()
            logger.info(f"[auto] Weekend snapshot: {n} instruments")

            # Generate gap signals if Sunday and past optimal time
            if weekday == 6 and f"{hour:02d}:00" >= HL_OPTIMAL_SIGNAL_TIME:
                signals = generate_gap_signals()
                logger.info(f"[auto] Sunday signal generation: {len(signals)} signals")

        elif weekday == 0 and hour >= 15:  # Monday after 15:00 UTC (after US open)
            updated = backfill_actuals()
            logger.info(f"[auto] Monday backfill: {updated} signals updated")

        else:
            logger.info(f"[auto] Not a weekend or Monday afternoon — nothing to do")

    elif mode == "snapshot":
        collect_snapshots()
    elif mode == "signal":
        generate_gap_signals()
    elif mode == "backfill":
        backfill_actuals()
    else:
        logger.error(f"Unknown mode: {mode}")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Hyperliquid Weekend Gap Monitor")
    parser.add_argument(
        "--mode", default="auto",
        choices=["auto", "snapshot", "signal", "backfill"],
        help="Run mode (default: auto)",
    )
    args = parser.parse_args()
    run(mode=args.mode)
