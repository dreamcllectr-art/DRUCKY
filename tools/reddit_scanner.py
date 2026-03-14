"""Reddit Social Sentiment & Trend Scanner.

Scans 10 investment subreddits for ticker mentions and emerging trends.
Weights institutional-quality communities (SecurityAnalysis, ValueInvesting)
3x higher than retail (WallStreetBets) to filter signal from noise.

Subreddits:
  Quality (3x): SecurityAnalysis, ValueInvesting, investing
  Momentum (1x): wallstreetbets, options, stocks
  Thematic (1.5x): artificial, MachineLearning, energy, technology

Requires Reddit API credentials (free):
  1. Go to reddit.com/prefs/apps
  2. Create a "script" app (not web app)
  3. Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to .env

Output: reddit_signals table with Social Velocity Score (0-100) per symbol.

Usage: python -m tools.reddit_scanner
"""

import sys
import re
import json
import math
import time
from datetime import datetime, date, timezone
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import (
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT,
    REDDIT_SUBREDDITS_QUALITY, REDDIT_SUBREDDITS_MOMENTUM, REDDIT_SUBREDDITS_THEMATIC,
)
from tools.db import init_db, upsert_many, query


# ── Constants ──────────────────────────────────────────────────────────

# Posts from last N seconds (48 hours)
POST_WINDOW_SECONDS = 172_800

# Subreddit weights
SUBREDDIT_WEIGHTS = {
    **{s: 3.0 for s in REDDIT_SUBREDDITS_QUALITY},
    **{s: 1.5 for s in REDDIT_SUBREDDITS_THEMATIC},
    **{s: 1.0 for s in REDDIT_SUBREDDITS_MOMENTUM},
}

# Quality subreddits set for tracking
QUALITY_SUBS = set(REDDIT_SUBREDDITS_QUALITY)
WSB_SUBS = {"wallstreetbets"}

# Minimum mentions to store a signal
MIN_MENTIONS = 3

# Common false positives to filter out
FALSE_POSITIVE_TICKERS = {
    "I", "A", "AI", "DD", "OP", "AM", "PM", "ETF", "IPO", "CEO", "CFO",
    "COO", "CTO", "CIO", "US", "UK", "EU", "FED", "SEC", "IRS", "FBI",
    "CIA", "GDP", "CPI", "PPI", "EPS", "P/E", "PE", "ATH", "ATL", "YTD",
    "IMO", "TBH", "FOMO", "YOLO", "WSB", "OTC", "NYSE", "NASDAQ", "SP",
    "ETH", "BTC", "THE", "FOR", "AND", "NOT", "BUT", "ALL", "ANY", "ARE",
    "WAS", "HAS", "HAD", "ITS", "OWN", "TOO", "OUT", "NEW", "NOW", "OR",
    "SO", "UP", "DO", "GO", "IF", "IN", "IS", "NO", "ON", "TV", "WE",
    "IT", "AT", "BE", "BY", "HE", "ME", "OF", "TO", "AS", "AN", "OK",
    "EV", "VC", "PE", "RE", "MA", "BB", "DD", "FF", "GG", "HH",
    "HOLD", "SELL", "BUY", "LONG", "SHORT", "CALL", "PUT", "PUTS", "CALLS",
}

# Sentiment word lists
BULLISH_WORDS = {
    "bull", "bullish", "buy", "long", "calls", "moon", "rocket", "squeeze",
    "breakout", "breakeven", "upside", "outperform", "upgrade", "overweight",
    "undervalued", "cheap", "growth", "revenue", "beat", "positive", "strong",
    "momentum", "oversold", "accumulate", "catalyst", "rally", "rip",
    "to the moon", "going up", "rate cut", "cutting rates", "earnings beat",
}
BEARISH_WORDS = {
    "bear", "bearish", "sell", "short", "puts", "crash", "dump", "fraud",
    "overvalued", "expensive", "decline", "miss", "negative", "weak",
    "downside", "underperform", "downgrade", "underweight", "expensive",
    "debt", "bankrupt", "recession", "risk", "caution", "concern",
    "overbought", "resistance", "distribution", "rotate out", "going down",
    "rate hike", "earnings miss", "guidance cut",
}

# Ticker extraction patterns
TICKER_PATTERN = re.compile(r'\$([A-Z]{1,5})\b')
BARE_TICKER_PATTERN = re.compile(r'\b([A-Z]{2,5})\b')


# ── Core Functions ─────────────────────────────────────────────────────

def _extract_tickers(text: str, universe: set[str]) -> list[str]:
    """Extract valid stock tickers from text, cross-referenced with universe."""
    found = set()

    # $TICKER pattern (high confidence)
    for match in TICKER_PATTERN.finditer(text):
        ticker = match.group(1)
        if ticker in universe and ticker not in FALSE_POSITIVE_TICKERS:
            found.add(ticker)

    # Bare uppercase words in context of investment language
    if any(word in text.lower() for word in ["stock", "share", "ticker", "buy", "sell",
                                               "call", "put", "option", "earnings", "position"]):
        for match in BARE_TICKER_PATTERN.finditer(text):
            ticker = match.group(1)
            if (ticker in universe and ticker not in FALSE_POSITIVE_TICKERS
                    and len(ticker) >= 2):
                found.add(ticker)

    return list(found)


def _classify_sentiment(text: str) -> float:
    """
    Lightweight regex-based sentiment. Returns -1.0 to +1.0.
    No external NLP dependency.
    """
    text_lower = text.lower()
    bullish_hits = sum(1 for w in BULLISH_WORDS if w in text_lower)
    bearish_hits = sum(1 for w in BEARISH_WORDS if w in text_lower)
    total = bullish_hits + bearish_hits
    if total == 0:
        return 0.0
    return (bullish_hits - bearish_hits) / total


def _compute_social_velocity_score(
    mention_count: int,
    post_score_sum: int,
    comment_count_sum: int,
    sentiment: float,
    quality_mentions: int,
    wsb_mentions: int,
) -> float:
    """
    Composite social velocity score (0-100).
    Quality mentions weighted 3x over WSB.
    """
    # Mention reach: log scale, cap at 40 pts
    mention_score = min(40.0, math.log(mention_count + 1) / math.log(100) * 40)

    # Engagement quality: post upvotes + comment volume
    engagement = math.log(post_score_sum + 1) / math.log(10000) * 15
    comment_signal = math.log(comment_count_sum + 1) / math.log(5000) * 10

    # Quality premium: SecurityAnalysis/ValueInvesting mentions get extra weight
    quality_boost = min(20.0, quality_mentions * 5.0)

    # Sentiment contribution: +10 / -10
    sentiment_score = sentiment * 10.0

    # WSB penalty: heavy WSB with no quality coverage = lower signal
    if wsb_mentions > 5 and quality_mentions == 0:
        wsb_penalty = -5.0
    else:
        wsb_penalty = 0.0

    total = mention_score + engagement + comment_signal + quality_boost + sentiment_score + wsb_penalty
    return min(100.0, max(0.0, total))


def _fetch_subreddit_posts_via_api(subreddit: str, limit: int = 75) -> list[dict]:
    """Fetch recent posts using PRAW."""
    import praw
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )
    cutoff = time.time() - POST_WINDOW_SECONDS
    posts = []
    try:
        sub = reddit.subreddit(subreddit)
        for post in sub.hot(limit=limit):
            if post.created_utc >= cutoff:
                posts.append({
                    "id": post.id,
                    "title": post.title,
                    "text": post.selftext or "",
                    "score": post.score,
                    "comments": post.num_comments,
                    "url": f"https://reddit.com{post.permalink}",
                    "subreddit": subreddit,
                    "created_utc": post.created_utc,
                })
        # Also check new posts
        for post in sub.new(limit=25):
            if post.created_utc >= cutoff:
                posts.append({
                    "id": post.id,
                    "title": post.title,
                    "text": post.selftext or "",
                    "score": post.score,
                    "comments": post.num_comments,
                    "url": f"https://reddit.com{post.permalink}",
                    "subreddit": subreddit,
                    "created_utc": post.created_utc,
                })
    except Exception as e:
        print(f"  Warning: Could not fetch r/{subreddit}: {e}")
    return posts


def _fetch_subreddit_posts_pushshift(subreddit: str) -> list[dict]:
    """
    Fallback scraper using Reddit's JSON API (no auth required).
    Limited to public hot/new feeds.
    """
    import requests as req
    posts = []
    cutoff = time.time() - POST_WINDOW_SECONDS
    for feed in ("hot", "new"):
        url = f"https://www.reddit.com/r/{subreddit}/{feed}.json"
        headers = {"User-Agent": REDDIT_USER_AGENT}
        try:
            resp = req.get(url, headers=headers, timeout=15, params={"limit": 50})
            if resp.status_code == 200:
                data = resp.json()
                for child in data.get("data", {}).get("children", []):
                    p = child.get("data", {})
                    if p.get("created_utc", 0) >= cutoff:
                        posts.append({
                            "id": p.get("id", ""),
                            "title": p.get("title", ""),
                            "text": p.get("selftext", ""),
                            "score": p.get("score", 0),
                            "comments": p.get("num_comments", 0),
                            "url": f"https://reddit.com{p.get('permalink', '')}",
                            "subreddit": subreddit,
                            "created_utc": p.get("created_utc", 0),
                        })
            time.sleep(1.0)  # Reddit rate limit for unauthenticated requests
        except Exception as e:
            print(f"  Warning: Could not fetch r/{subreddit}/{feed}: {e}")
    return posts


def run():
    """Main entry: scan subreddits and store social velocity scores."""
    init_db()
    today = date.today().isoformat()
    print("Reddit Scanner: Scanning investment subreddits...")

    # Check if PRAW is available and credentials are configured
    use_praw = bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)
    if use_praw:
        try:
            import praw
            print(f"  Using PRAW (authenticated API)")
        except ImportError:
            use_praw = False
            print(f"  PRAW not installed — using public JSON API (limited)")
    else:
        print(f"  No Reddit credentials — using public JSON API (limited)")
        print(f"  To improve: add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to .env")

    # Get stock universe
    universe_rows = query("SELECT symbol FROM stock_universe")
    universe_symbols = {r["symbol"] for r in universe_rows}
    if not universe_symbols:
        print("  Warning: No stock universe loaded — run fetch_stock_universe first")
        return

    # Aggregate posts from all subreddits
    all_subreddits = (
        REDDIT_SUBREDDITS_QUALITY +
        REDDIT_SUBREDDITS_MOMENTUM +
        REDDIT_SUBREDDITS_THEMATIC
    )
    all_posts = []
    seen_ids = set()

    for subreddit in all_subreddits:
        print(f"  Scanning r/{subreddit}...")
        if use_praw:
            posts = _fetch_subreddit_posts_via_api(subreddit)
        else:
            posts = _fetch_subreddit_posts_pushshift(subreddit)

        for post in posts:
            if post["id"] not in seen_ids:
                seen_ids.add(post["id"])
                all_posts.append(post)

        time.sleep(0.5)

    print(f"  Collected {len(all_posts)} unique posts across {len(all_subreddits)} subreddits")

    # Aggregate by ticker
    ticker_data: dict[str, dict] = {}

    for post in all_posts:
        full_text = f"{post['title']} {post['text']}"
        tickers = _extract_tickers(full_text, universe_symbols)
        sentiment = _classify_sentiment(full_text)
        sub_weight = SUBREDDIT_WEIGHTS.get(post["subreddit"], 1.0)
        is_quality = post["subreddit"] in QUALITY_SUBS
        is_wsb = post["subreddit"] in WSB_SUBS

        for ticker in tickers:
            if ticker not in ticker_data:
                ticker_data[ticker] = {
                    "mention_count": 0,
                    "post_score_sum": 0,
                    "comment_count_sum": 0,
                    "sentiment_sum": 0.0,
                    "sentiment_count": 0,
                    "bullish_mentions": 0,
                    "bearish_mentions": 0,
                    "wsb_mentions": 0,
                    "quality_mentions": 0,
                    "top_post_score": -1,
                    "top_post_title": "",
                    "top_post_url": "",
                }

            d = ticker_data[ticker]
            d["mention_count"] += sub_weight
            d["post_score_sum"] += post["score"]
            d["comment_count_sum"] += post["comments"]
            d["sentiment_sum"] += sentiment
            d["sentiment_count"] += 1
            if sentiment > 0.1:
                d["bullish_mentions"] += 1
            elif sentiment < -0.1:
                d["bearish_mentions"] += 1
            if is_wsb:
                d["wsb_mentions"] += 1
            if is_quality:
                d["quality_mentions"] += 1

            if post["score"] > d["top_post_score"]:
                d["top_post_score"] = post["score"]
                d["top_post_title"] = post["title"][:200]
                d["top_post_url"] = post["url"]

    # Filter and score
    rows = []
    for ticker, d in ticker_data.items():
        raw_mentions = d["mention_count"]
        if raw_mentions < MIN_MENTIONS:
            continue

        avg_sentiment = d["sentiment_sum"] / d["sentiment_count"] if d["sentiment_count"] else 0.0
        score = _compute_social_velocity_score(
            mention_count=int(raw_mentions),
            post_score_sum=d["post_score_sum"],
            comment_count_sum=d["comment_count_sum"],
            sentiment=avg_sentiment,
            quality_mentions=d["quality_mentions"],
            wsb_mentions=d["wsb_mentions"],
        )

        rows.append((
            ticker, today,
            int(raw_mentions), d["post_score_sum"], d["comment_count_sum"],
            d["bullish_mentions"], d["bearish_mentions"],
            round(avg_sentiment, 4),
            d["wsb_mentions"], d["quality_mentions"],
            round(score, 2),
            d["top_post_title"], d["top_post_url"],
        ))

    if rows:
        upsert_many(
            "reddit_signals",
            ["symbol", "date", "mention_count", "post_score_sum", "comment_count_sum",
             "bullish_mentions", "bearish_mentions", "sentiment_score",
             "wsb_mentions", "quality_mentions", "social_velocity_score",
             "top_post_title", "top_post_url"],
            rows,
        )

    # Print top signals
    rows_sorted = sorted(rows, key=lambda x: x[10], reverse=True)[:15]
    print(f"\n  TOP SOCIAL VELOCITY SIGNALS ({len(rows)} total tracked):")
    print(f"  {'Symbol':<8} {'Score':>6} {'Mentions':>8} {'Quality':>7} {'Sentiment':>9}")
    print(f"  {'-'*45}")
    for r in rows_sorted:
        sym, dt, mentions, _, _, bull, bear, sentiment, wsb, quality, score, title, url = r
        print(f"  {sym:<8} {score:>6.1f} {mentions:>8} {quality:>7} {sentiment:>+9.2f}")

    print(f"\nReddit complete: {len(rows)} tickers tracked")


if __name__ == "__main__":
    run()
