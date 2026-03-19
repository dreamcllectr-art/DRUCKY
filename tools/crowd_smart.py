"""Layer 3 — Smart Money Signals (highest IC, leading indicators).

Sources:
  - OpenInsider + SEC Form 4: insider cluster buying (reuses insider_trading.py DB output)
  - yfinance options chain: 25Δ-equivalent skew (0.85/1.15 moneyness proxy)
  - Polymarket: macro event probability shifts (reuses prediction_markets.py DB output)

Theory: Lakonishok & Lee (2001) — insider cluster buying predicts 6-month
excess returns of 4-6%. Cluster = 3+ insiders, 14-day window (matches
INSIDER_CLUSTER_WINDOW_DAYS constant in config_modules.py).

NOTE: Finnhub free tier does NOT provide delta-mapped skew.
Using yfinance options chain with moneyness proxy instead.
"""
import sys, json, logging
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)


def fetch_insider_clusters(tickers: list[str]) -> list[Signal]:
    """Detect insider cluster buying from existing insider_signals DB table.

    Reuses insider_trading.py output — does NOT rebuild cluster logic.
    Cluster buy (3+ insiders, 14-day window) gets IC boost to 0.08.
    Non-cluster insider buys score at IC=0.05.
    """
    try:
        from tools.db import query
        signals = []
        cutoff = (date.today() - timedelta(days=90)).isoformat()

        rows = query(
            """SELECT symbol, date, insider_score, cluster_buy, large_csuite
               FROM insider_signals
               WHERE date >= ? AND (cluster_buy = 1 OR insider_score > 60)
               ORDER BY date DESC""",
            [cutoff]
        )

        seen: set[str] = set()
        tickers_set = set(tickers)
        for row in (rows or []):
            ticker = row["symbol"]
            if ticker not in tickers_set or ticker in seen:
                continue
            seen.add(ticker)
            is_cluster = bool(row["cluster_buy"])
            score = float(row["insider_score"] or 0)
            norm = min(1.0, score / 100.0)
            age_days = (date.today() - date.fromisoformat(row["date"])).days
            ic = 0.08 if is_cluster else 0.05
            signals.append(Signal(
                name=f"insider_cluster_{ticker}",
                value=score,
                normalized=norm,
                ic=ic,
                half_life=90,
                age_days=age_days,
                layer="smart",
                source="openinsider_form4",
            ))
        return signals
    except Exception as e:
        logger.warning(f"fetch_insider_clusters failed: {e}")
        return []


def fetch_options_skew(tickers: list[str], max_tickers: int = 300) -> list[Signal]:
    """Compute 25Δ-equivalent skew from yfinance options chain.

    Skew = OTM put IV / OTM call IV at 0.85/1.15 moneyness.
    High skew (>1) = put demand > call demand = market fear.
    Low skew (<1) = call demand > put demand = bullish sentiment.

    Only processes tickers with liquid options (nearest expiry 20-60 DTE).
    """
    try:
        import yfinance as yf
        import numpy as np
        signals = []

        for ticker in tickers[:max_tickers]:
            try:
                tk = yf.Ticker(ticker)
                info = tk.info or {}
                price = info.get("regularMarketPrice") or info.get("currentPrice")
                if not price:
                    hist = tk.history(period="1d")
                    if hist.empty:
                        continue
                    price = float(hist["Close"].iloc[-1])
                if not price or price <= 0:
                    continue

                exps = tk.options
                if not exps:
                    continue

                # Find nearest expiry 20-60 DTE
                today = date.today()
                target_exp = None
                for exp in exps:
                    try:
                        exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                        dte = (exp_date - today).days
                        if 20 <= dte <= 60:
                            target_exp = exp
                            break
                    except Exception:
                        continue
                if not target_exp:
                    target_exp = exps[0]

                chain = tk.option_chain(target_exp)
                puts  = chain.puts
                calls = chain.calls
                if puts.empty or calls.empty:
                    continue

                # 25Δ proxy: 0.85 × price for puts, 1.15 × price for calls
                otm_put  = puts[puts["strike"].between(price * 0.80, price * 0.90)]
                otm_call = calls[calls["strike"].between(price * 1.10, price * 1.20)]
                if otm_put.empty or otm_call.empty:
                    continue

                put_iv  = float(otm_put["impliedVolatility"].mean())
                call_iv = float(otm_call["impliedVolatility"].mean())
                if call_iv < 0.001:
                    continue

                skew = put_iv / call_iv
                # Normalize: skew 0.8-2.0 → [0, 1]
                norm = float(min(1.0, max(0.0, (skew - 0.8) / 1.2)))

                signals.append(Signal(
                    name=f"options_skew_{ticker}",
                    value=skew,
                    normalized=norm,
                    ic=0.06,
                    half_life=5,
                    age_days=0,
                    layer="smart",
                    source="yfinance_options",
                ))
            except Exception:
                continue

        return signals
    except Exception as e:
        logger.warning(f"fetch_options_skew failed: {e}")
        return []


def fetch_polymarket_signals() -> list[Signal]:
    """Fetch macro crowd probability from Polymarket via existing DB output.

    Reuses prediction_markets.py Gamma API logic — reads from DB.
    Falls back gracefully if table doesn't exist.
    """
    try:
        from tools.db import query
        cutoff = (date.today() - timedelta(days=7)).isoformat()

        # Try convergence_signals table first (has prediction_markets_score)
        rows = query(
            """SELECT symbol, date, prediction_markets_score
               FROM convergence_signals
               WHERE prediction_markets_score IS NOT NULL AND date >= ?
               ORDER BY date DESC LIMIT 50""",
            [cutoff]
        )

        signals = []
        seen: set[str] = set()
        for row in (rows or []):
            ticker = row.get("symbol", "MACRO")
            if ticker in seen:
                continue
            seen.add(ticker)
            score = float(row.get("prediction_markets_score") or 0)
            if score <= 0:
                continue
            age_days = (date.today() - date.fromisoformat(row["date"])).days
            signals.append(Signal(
                name=f"polymarket_{ticker}",
                value=score,
                normalized=min(1.0, score / 100.0),
                ic=0.04,
                half_life=3,
                age_days=age_days,
                layer="smart",
                source="polymarket",
            ))
        return signals
    except Exception as e:
        logger.warning(f"fetch_polymarket_signals failed: {e}")
        return []


def fetch_all_smart(tickers: list[str]) -> list[Signal]:
    """Fetch all Layer 3 smart money signals. Gracefully handles source failures."""
    signals: list[Signal] = []
    signals.extend(fetch_insider_clusters(tickers))
    signals.extend(fetch_options_skew(tickers))
    signals.extend(fetch_polymarket_signals())
    logger.info(f"Smart money layer: {len(signals)} signals collected")
    return signals
