"""Layer 1 — Retail Crowding Signals.

Sources:
  - Reddit PRAW: ticker mention velocity + sentiment (WSB, r/investing, r/stocks)
  - Alternative.me Fear & Greed: documented free API, stable
  - AAII Sentiment Survey: weekly HTML scrape of aaii.com
  - Google Trends (pytrends): retail FOMO proxy, top-50 tickers only

All signals are CONTRARIAN. High retail = crowding risk.
crowd_engine.score_layer() handles the inversion via layer_type="retail".
"""
import sys, json, time, logging, re
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)


def fetch_fear_greed() -> list[Signal]:
    """Fetch Fear & Greed via Alternative.me documented API (free, stable).

    NOT CNN's internal endpoint — Alternative.me is documented and versioned.
    """
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=2&format=json",
            timeout=10,
            headers={"User-Agent": "DruckenmillerAlpha/1.0"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return []
        current = data[0]
        value = float(current["value"])
        age_days = max(0, (datetime.now() - datetime.fromtimestamp(int(current["timestamp"]))).days)
        return [Signal(
            name="fear_greed",
            value=value,
            normalized=value / 100.0,
            ic=-0.04,
            half_life=1,
            age_days=age_days,
            layer="retail",
            source="alternative_me",
        )]
    except Exception as e:
        logger.warning(f"fetch_fear_greed failed: {e}")
        return []


def fetch_aaii_sentiment() -> list[Signal]:
    """Scrape AAII weekly sentiment survey — bulls% as crowding indicator."""
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(
            "https://www.aaii.com/sentimentsurvey/sent_results",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DruckenmillerAlpha/1.0)"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        bulls = None
        for td in soup.find_all("td"):
            txt = td.get_text(strip=True)
            if "%" in txt:
                try:
                    pct = float(txt.replace("%", ""))
                    if 0 < pct < 100:
                        bulls = pct
                        break
                except ValueError:
                    continue
        if bulls is None:
            return []
        normalized = min(1.0, max(0.0, bulls / 100.0))
        return [Signal(
            name="aaii_bulls",
            value=bulls,
            normalized=normalized,
            ic=-0.03,
            half_life=7,
            age_days=0,
            layer="retail",
            source="aaii",
        )]
    except Exception as e:
        logger.warning(f"fetch_aaii_sentiment failed: {e}")
        return []


def fetch_reddit_sentiment(tickers: list[str], max_tickers: int = 200) -> list[Signal]:
    """Fetch ticker mention velocity from Reddit WSB + r/investing + r/stocks.

    Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in environment (.env).
    Already configured in this project's config.py.
    """
    try:
        import praw
        from tools.config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
        if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
            logger.info("Reddit credentials not configured — skipping")
            return []
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            check_for_async=False,
        )
        scan_tickers = set(tickers[:max_tickers])
        mention_counts: dict[str, int] = {t: 0 for t in scan_tickers}
        subreddits = ["wallstreetbets", "investing", "stocks"]
        for sub_name in subreddits:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.new(limit=200):
                    text = f"{post.title} {post.selftext}".upper()
                    for ticker in scan_tickers:
                        if f" {ticker} " in text or f"${ticker}" in text:
                            mention_counts[ticker] += 1
            except Exception as e:
                logger.warning(f"Reddit r/{sub_name} failed: {e}")
        signals = []
        max_mentions = max(mention_counts.values()) if mention_counts else 1
        for ticker in scan_tickers:
            count = mention_counts.get(ticker, 0)
            if count == 0:
                continue
            norm = count / max(max_mentions, 1)
            signals.append(Signal(
                name=f"reddit_mentions_{ticker}",
                value=float(count),
                normalized=float(norm),
                ic=-0.02,
                half_life=2,
                age_days=0,
                layer="retail",
                source="reddit",
            ))
        return signals
    except Exception as e:
        logger.warning(f"fetch_reddit_sentiment failed: {e}")
        return []


def fetch_google_trends(tickers: list[str], max_tickers: int = 50) -> list[Signal]:
    """Fetch Google Trends interest. Top-50 tickers only — aggressive rate limiting.

    Exponential backoff on 429. Falls back gracefully to empty list if blocked.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.info("pytrends not installed — skipping Google Trends")
        return []
    signals = []
    batch = tickers[:max_tickers]
    for i in range(0, len(batch), 5):
        chunk = batch[i:i + 5]
        for attempt in range(3):
            try:
                pt = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
                pt.build_payload(chunk, timeframe="now 7-d")
                df = pt.interest_over_time()
                if df.empty:
                    break
                for ticker in chunk:
                    if ticker not in df.columns:
                        continue
                    series = df[ticker].values.tolist()
                    if not series:
                        continue
                    current = float(series[-1])
                    signals.append(Signal(
                        name=f"gtrends_{ticker}",
                        value=current,
                        normalized=current / 100.0,
                        ic=-0.02,
                        half_life=3,
                        age_days=0,
                        layer="retail",
                        source="google_trends",
                    ))
                break
            except Exception as e:
                if "429" in str(e) or "Too Many" in str(e):
                    wait = 2 ** attempt * 30
                    logger.warning(f"Google Trends rate limited — waiting {wait}s")
                    time.sleep(wait)
                else:
                    logger.warning(f"Google Trends chunk {chunk} failed: {e}")
                    break
        time.sleep(5)
    return signals


def fetch_all_retail(tickers: list[str]) -> list[Signal]:
    """Fetch all Layer 1 retail signals. Gracefully handles any source failure."""
    signals: list[Signal] = []
    signals.extend(fetch_fear_greed())
    signals.extend(fetch_aaii_sentiment())
    signals.extend(fetch_reddit_sentiment(tickers))
    signals.extend(fetch_google_trends(tickers))
    logger.info(f"Retail layer: {len(signals)} signals collected")
    return signals
