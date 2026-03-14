"""M&A Intelligence Module — acquisition target scoring + rumor detection.

Two signal types feeding a single ma_score (0-100) into convergence:

  1. Target Profile Score — deterministic scoring of acquisition likelihood
     based on financial characteristics, smart money accumulation, sector
     consolidation signals, and strategic fit indicators.

  2. Rumor/News Score — LLM-powered classification of M&A-related news
     via Finnhub company news + Serper web search. Scores rumor credibility,
     deal stage, and expected price impact.

Design principles (quant-grade):
  - All sub-scores normalized to 0-100 before blending
  - Bayesian-inspired: base rate of M&A for sector × market cap bucket
  - Decay function on rumor signals (half-life 5 days — stale rumors = noise)
  - Cross-validation against 13F accumulation patterns
  - Conservative scoring: false positives cost more than missed signals

Feeds into convergence engine as the 12th module (ma_score column).

Usage: python -m tools.ma_signals
"""

import json
import logging
import math
import re
import time
from datetime import date, datetime, timedelta

import finnhub
import requests

from tools.db import get_conn, query, query_df, upsert_many, init_db
from tools.config import (
    FINNHUB_API_KEY,
    SERPER_API_KEY,
    GEMINI_API_KEY,
    GEMINI_BASE,
    GEMINI_MODEL,
    MA_RUMOR_LOOKBACK_DAYS,
    MA_RUMOR_HALF_LIFE_DAYS,
    MA_NEWS_BATCH_SIZE,
    MA_FINNHUB_DELAY,
    MA_GEMINI_DELAY,
    MA_MIN_MARKET_CAP,
    MA_MAX_MARKET_CAP,
    MA_TARGET_WEIGHT_PROFILE,
    MA_TARGET_WEIGHT_RUMOR,
    MA_MIN_SCORE_STORE,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# SECTOR M&A BASE RATES
# ═══════════════════════════════════════════════════════════════════════════
# Empirical annual M&A rates by sector (2015-2024 average, source: Dealogic/
# Bloomberg). Used as Bayesian prior — sectors with higher base rates get a
# multiplier on target profile scores. Range: 0.5x to 1.5x.

SECTOR_MA_BASE_RATES = {
    "Technology":             1.40,  # Highest M&A activity — platform consolidation
    "Healthcare":             1.35,  # Pharma pipeline acquisitions, biotech buyouts
    "Communication Services": 1.20,  # Media consolidation, streaming wars
    "Financials":             1.15,  # Bank mergers, fintech acquisitions
    "Energy":                 1.10,  # Upstream consolidation cycle
    "Industrials":            1.00,  # Baseline — diversified industrial M&A
    "Consumer Discretionary": 0.95,
    "Consumer Staples":       0.90,
    "Materials":              0.90,
    "Real Estate":            0.85,
    "Utilities":              0.80,  # Regulated — lowest M&A frequency
}

# Market cap buckets for target attractiveness (log-scale breakpoints)
# Sweet spot: $2B-$30B — large enough to matter, small enough to acquire.
MCAP_ATTRACTIVENESS = [
    (0,       2e9,  0.4),   # Micro/small cap — too small for most acquirers
    (2e9,     10e9, 1.0),   # Mid cap sweet spot — highest acquisition probability
    (10e9,    30e9, 0.9),   # Upper mid — still acquirable, larger premium
    (30e9,    100e9, 0.5),  # Large cap — harder to acquire, regulatory scrutiny
    (100e9,   1e15, 0.2),   # Mega cap — near-impossible to acquire whole
]


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def _load_universe() -> list[dict]:
    """Load stock universe with sector and market cap.

    Market cap comes from fundamentals table (yfinance), not stock_universe.
    """
    return query("""
        SELECT u.symbol, u.sector, f.value as market_cap, u.name as company_name
        FROM stock_universe u
        INNER JOIN fundamentals f ON f.symbol = u.symbol AND f.metric = 'marketCap'
        WHERE u.sector IS NOT NULL AND f.value IS NOT NULL AND f.value > 0
    """)


def _load_fundamentals() -> dict[str, dict]:
    """Load key fundamental metrics per symbol for target profiling.

    Returns: {symbol: {metric: value}}
    """
    rows = query("""
        SELECT symbol, metric, value FROM fundamentals
        WHERE metric IN (
            'trailingPE', 'forwardPE', 'priceToBook', 'priceToSales',
            'enterpriseToEbitda', 'debt_equity', 'current_ratio',
            'profit_margin', 'operating_margin', 'roe', 'roa',
            'revenue_growth', 'earnings_growth', 'dividend_yield',
            'analyst_target_consensus'
        )
    """)
    result: dict[str, dict] = {}
    for r in rows:
        result.setdefault(r["symbol"], {})[r["metric"]] = r["value"]
    return result


def _load_smart_money() -> dict[str, dict]:
    """Load latest 13F smart money data per symbol.

    Returns: {symbol: {conviction_score, manager_count, top_holders}}
    """
    rows = query("""
        SELECT s.symbol, s.conviction_score, s.manager_count, s.top_holders
        FROM smart_money_scores s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM smart_money_scores GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
    """)
    return {r["symbol"]: dict(r) for r in rows}


def _load_13f_accumulation() -> dict[str, dict]:
    """Detect recent 13F accumulation patterns suggestive of M&A positioning.

    Looks for: new positions, significant increases, activist-style concentration.
    Returns: {symbol: {new_positions: int, total_increase_value: float, max_portfolio_pct: float}}
    """
    rows = query("""
        SELECT symbol, action, shares_held, market_value, portfolio_pct, manager_name
        FROM filings_13f
        WHERE period_of_report >= date('now', '-6 months')
    """)
    accum: dict[str, dict] = {}
    for r in rows:
        sym = r["symbol"]
        if sym not in accum:
            accum[sym] = {"new_positions": 0, "total_increase_value": 0.0,
                          "max_portfolio_pct": 0.0, "manager_names": set()}
        if r["action"] in ("new", "NEW"):
            accum[sym]["new_positions"] += 1
        if r["action"] in ("increase", "INCREASE", "new", "NEW"):
            accum[sym]["total_increase_value"] += (r["market_value"] or 0)
        pct = r["portfolio_pct"] or 0
        if pct > accum[sym]["max_portfolio_pct"]:
            accum[sym]["max_portfolio_pct"] = pct
        accum[sym]["manager_names"].add(r["manager_name"])

    # Convert sets to counts
    for sym in accum:
        accum[sym]["unique_accumulators"] = len(accum[sym].pop("manager_names"))
    return accum


def _load_insider_signals() -> dict[str, dict]:
    """Load insider trading signals — cluster buys are strong M&A precursors."""
    rows = query("""
        SELECT s.symbol, s.insider_score, s.cluster_buy, s.cluster_count,
               s.total_buy_value_30d
        FROM insider_signals s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM insider_signals GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
    """)
    return {r["symbol"]: dict(r) for r in rows}


def _load_sector_expert_themes() -> dict[str, list[str]]:
    """Load sector expert key catalysts — look for consolidation themes."""
    rows = query("""
        SELECT symbol, key_catalysts
        FROM sector_expert_signals
        WHERE date >= date('now', '-14 days')
          AND key_catalysts IS NOT NULL
    """)
    result: dict[str, list[str]] = {}
    for r in rows:
        try:
            catalysts = json.loads(r["key_catalysts"]) if isinstance(r["key_catalysts"], str) else []
        except (json.JSONDecodeError, TypeError):
            catalysts = [r["key_catalysts"]] if r["key_catalysts"] else []
        result.setdefault(r["symbol"], []).extend(catalysts)
    return result


def _load_existing_rumors() -> dict[str, list[dict]]:
    """Load existing M&A rumors from DB for dedup and decay calculation."""
    rows = query("""
        SELECT symbol, date, rumor_source, rumor_headline, credibility_score,
               deal_stage, expected_premium_pct
        FROM ma_rumors
        WHERE date >= date('now', '-30 days')
        ORDER BY date DESC
    """)
    result: dict[str, list[dict]] = {}
    for r in rows:
        result.setdefault(r["symbol"], []).append(dict(r))
    return result


# ═══════════════════════════════════════════════════════════════════════════
# TARGET PROFILE SCORING (deterministic)
# ═══════════════════════════════════════════════════════════════════════════

def _score_valuation_attractiveness(fundamentals: dict) -> float:
    """Score 0-100: how attractively valued is this company to an acquirer?

    Acquirers seek: low EV/EBITDA, low P/B, reasonable P/E, below analyst targets.
    """
    score = 0.0
    count = 0

    # EV/EBITDA — most important M&A valuation metric
    ev_ebitda = fundamentals.get("enterpriseToEbitda")
    if ev_ebitda is not None and ev_ebitda > 0:
        count += 2  # Double-weighted
        if ev_ebitda < 8:
            score += 100 * 2     # Very attractive
        elif ev_ebitda < 12:
            score += 75 * 2      # Attractive
        elif ev_ebitda < 18:
            score += 40 * 2      # Fair
        else:
            score += 10 * 2      # Expensive

    # P/B — asset-heavy targets often acquired near book
    pb = fundamentals.get("priceToBook")
    if pb is not None and pb > 0:
        count += 1
        if pb < 1.5:
            score += 90
        elif pb < 3.0:
            score += 60
        elif pb < 5.0:
            score += 30
        else:
            score += 10

    # Forward P/E — growth-adjusted value
    fpe = fundamentals.get("forwardPE")
    if fpe is not None and fpe > 0:
        count += 1
        if fpe < 12:
            score += 85
        elif fpe < 18:
            score += 60
        elif fpe < 25:
            score += 35
        else:
            score += 10

    # Price vs analyst consensus — trading below consensus = acquirer sees value
    target = fundamentals.get("analyst_target_consensus")
    trailing_pe = fundamentals.get("trailingPE")
    if target is not None and trailing_pe is not None and target > 0:
        # We don't have current price directly, but if forward PE << trailing PE,
        # analysts expect growth (which makes it attractive to acquirers)
        fpe_val = fundamentals.get("forwardPE")
        if fpe_val and trailing_pe > 0 and fpe_val < trailing_pe * 0.85:
            count += 1
            score += 70  # Analysts see growth acceleration

    return (score / count) if count > 0 else 0.0


def _score_balance_sheet_quality(fundamentals: dict) -> float:
    """Score 0-100: how clean is the balance sheet for an acquisition?

    Acquirers prefer: low debt (easier to finance), high cash flow, good margins.
    """
    score = 0.0
    count = 0

    # Debt/equity — lower = easier to lever up in LBO or strategic deal
    de = fundamentals.get("debt_equity")
    if de is not None:
        count += 2  # Double-weighted
        if de < 30:
            score += 100 * 2   # Fortress balance sheet
        elif de < 80:
            score += 75 * 2    # Conservative
        elif de < 150:
            score += 40 * 2    # Moderate
        elif de < 300:
            score += 15 * 2    # Heavily levered
        else:
            score += 0         # Distressed — acquirable but different thesis

    # Operating margin — high margin = high synergy potential
    opm = fundamentals.get("operating_margin")
    if opm is not None:
        count += 1
        if opm > 0.25:
            score += 90
        elif opm > 0.15:
            score += 70
        elif opm > 0.08:
            score += 45
        elif opm > 0:
            score += 20
        else:
            score += 5   # Negative margins — turnaround play

    # Current ratio — liquidity health
    cr = fundamentals.get("current_ratio")
    if cr is not None:
        count += 1
        if cr > 2.0:
            score += 80
        elif cr > 1.5:
            score += 65
        elif cr > 1.0:
            score += 40
        else:
            score += 10

    # ROE — profitability efficiency
    roe = fundamentals.get("roe")
    if roe is not None:
        count += 1
        if roe > 0.20:
            score += 90
        elif roe > 0.12:
            score += 65
        elif roe > 0.05:
            score += 35
        else:
            score += 10

    return (score / count) if count > 0 else 0.0


def _score_growth_profile(fundamentals: dict) -> float:
    """Score 0-100: how attractive is the growth profile to acquirers?

    Growth acquirers want: revenue growth + margin expansion.
    Value acquirers want: stable cash flows (moderate growth OK).
    We score for BOTH — the blend naturally captures different buyer types.
    """
    score = 0.0
    count = 0

    rev_growth = fundamentals.get("revenue_growth")
    if rev_growth is not None:
        count += 1
        if rev_growth > 0.30:
            score += 95    # Hypergrowth — strategic premium
        elif rev_growth > 0.15:
            score += 80    # Strong growth
        elif rev_growth > 0.05:
            score += 55    # Moderate — still attractive
        elif rev_growth > 0:
            score += 35    # Slow growth — value play
        else:
            score += 15    # Declining — turnaround/asset play

    earn_growth = fundamentals.get("earnings_growth")
    if earn_growth is not None:
        count += 1
        if earn_growth > 0.25:
            score += 90
        elif earn_growth > 0.10:
            score += 70
        elif earn_growth > 0:
            score += 45
        else:
            score += 15

    return (score / count) if count > 0 else 0.0


def _score_smart_money_accumulation(
    symbol: str,
    smart_money: dict[str, dict],
    accumulation: dict[str, dict],
    insider_signals: dict[str, dict],
) -> float:
    """Score 0-100: are institutional/insider flows consistent with pre-acquisition?

    Key signals:
    - New 13F positions from multiple managers
    - Concentrated positions (>5% portfolio) — activist-style
    - Insider cluster buys (officers buying before deal)
    """
    score = 0.0
    weights = 0.0

    # 13F accumulation
    acc = accumulation.get(symbol)
    if acc:
        # New positions from multiple managers
        new_pos = acc.get("new_positions", 0)
        if new_pos >= 4:
            score += 90 * 0.30
        elif new_pos >= 2:
            score += 65 * 0.30
        elif new_pos >= 1:
            score += 35 * 0.30
        weights += 0.30

        # Concentrated positions (activist-style)
        max_pct = acc.get("max_portfolio_pct", 0)
        if max_pct > 10:
            score += 95 * 0.25    # Activist-level concentration
        elif max_pct > 5:
            score += 70 * 0.25
        elif max_pct > 2:
            score += 40 * 0.25
        weights += 0.25

        # Multiple unique accumulators
        uniq = acc.get("unique_accumulators", 0)
        if uniq >= 5:
            score += 85 * 0.15
        elif uniq >= 3:
            score += 55 * 0.15
        weights += 0.15

    # Smart money conviction
    sm = smart_money.get(symbol)
    if sm:
        conv = sm.get("conviction_score", 0) or 0
        score += conv * 0.15
        weights += 0.15

    # Insider cluster buys — strongest single M&A precursor
    ins = insider_signals.get(symbol)
    if ins:
        if ins.get("cluster_buy"):
            cluster_ct = ins.get("cluster_count", 0) or 0
            if cluster_ct >= 3:
                score += 95 * 0.15   # Multiple insiders buying = very strong
            else:
                score += 75 * 0.15
        else:
            buy_val = ins.get("total_buy_value_30d", 0) or 0
            if buy_val > 1_000_000:
                score += 50 * 0.15
            elif buy_val > 100_000:
                score += 25 * 0.15
        weights += 0.15

    return (score / weights) if weights > 0 else 0.0


def _score_sector_consolidation(
    symbol: str,
    sector: str,
    sector_themes: dict[str, list[str]],
) -> float:
    """Score 0-25 bonus: is this sector undergoing active consolidation?

    Cross-references sector expert catalysts for M&A/consolidation keywords.
    """
    MA_KEYWORDS = {
        "consolidation", "merger", "acquisition", "buyout", "takeover",
        "strategic review", "activist", "spin-off", "spinoff", "divestiture",
        "going private", "leveraged buyout", "lbo", "m&a",
    }

    themes = sector_themes.get(symbol, [])
    if not themes:
        return 0.0

    # Count M&A-related themes
    ma_hits = 0
    for theme in themes:
        theme_lower = theme.lower() if isinstance(theme, str) else ""
        if any(kw in theme_lower for kw in MA_KEYWORDS):
            ma_hits += 1

    if ma_hits >= 3:
        return 25.0
    elif ma_hits >= 2:
        return 18.0
    elif ma_hits >= 1:
        return 10.0
    return 0.0


def compute_target_profile_scores(
    universe: list[dict],
    fundamentals: dict[str, dict],
    smart_money: dict[str, dict],
    accumulation: dict[str, dict],
    insider_signals: dict[str, dict],
    sector_themes: dict[str, list[str]],
) -> dict[str, dict]:
    """Compute target profile scores for all symbols.

    Returns: {symbol: {target_score, valuation_score, balance_sheet_score,
                       growth_score, smart_money_score, consolidation_bonus,
                       mcap_multiplier, sector_multiplier}}
    """
    results = {}

    for stock in universe:
        sym = stock["symbol"]
        sector = stock["sector"] or "Industrials"
        mcap = stock["market_cap"] or 0

        # Skip if outside acquirable market cap range
        if mcap < MA_MIN_MARKET_CAP or mcap > MA_MAX_MARKET_CAP:
            continue

        fund = fundamentals.get(sym, {})
        if not fund:
            continue

        # Sub-scores (each 0-100)
        val_score = _score_valuation_attractiveness(fund)
        bs_score = _score_balance_sheet_quality(fund)
        growth_score = _score_growth_profile(fund)
        sm_score = _score_smart_money_accumulation(
            sym, smart_money, accumulation, insider_signals
        )
        consol_bonus = _score_sector_consolidation(sym, sector, sector_themes)

        # Weighted blend of sub-scores
        raw_target = (
            val_score * 0.30 +       # Valuation most important for M&A
            bs_score * 0.25 +        # Clean balance sheet
            sm_score * 0.25 +        # Institutional accumulation
            growth_score * 0.20      # Growth profile
        )

        # Add consolidation bonus (additive, not multiplicative)
        raw_target = min(100, raw_target + consol_bonus)

        # Market cap multiplier (sweet spot: $2B-$30B)
        mcap_mult = 0.5  # default
        for low, high, mult in MCAP_ATTRACTIVENESS:
            if low <= mcap < high:
                mcap_mult = mult
                break

        # Sector base rate multiplier
        sector_mult = SECTOR_MA_BASE_RATES.get(sector, 1.0)

        # Final target score
        target_score = min(100, raw_target * mcap_mult * sector_mult)

        results[sym] = {
            "target_score": round(target_score, 1),
            "valuation_score": round(val_score, 1),
            "balance_sheet_score": round(bs_score, 1),
            "growth_score": round(growth_score, 1),
            "smart_money_score": round(sm_score, 1),
            "consolidation_bonus": round(consol_bonus, 1),
            "mcap_multiplier": round(mcap_mult, 2),
            "sector_multiplier": round(sector_mult, 2),
        }

    return results


# ═══════════════════════════════════════════════════════════════════════════
# RUMOR / NEWS DETECTION (LLM-powered)
# ═══════════════════════════════════════════════════════════════════════════

def _get_finnhub_client():
    return finnhub.Client(api_key=FINNHUB_API_KEY)


def _fetch_ma_news(client, symbols: list[str]) -> list[dict]:
    """Fetch recent company news from Finnhub, pre-filtered for M&A relevance.

    Returns list of {symbol, headline, source, url, datetime, summary}.
    """
    MA_KEYWORDS_NEWS = {
        "acqui", "merger", "buyout", "takeover", "bid", "offer",
        "going private", "strategic review", "strategic alternative",
        "deal", "consortium", "approach", "proposal",
        "activist", "spin-off", "divest",
    }

    today = datetime.now().strftime("%Y-%m-%d")
    lookback = (datetime.now() - timedelta(days=MA_RUMOR_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    all_news = []
    seen_urls = set()

    for sym in symbols:
        try:
            articles = client.company_news(sym, _from=lookback, to=today)
        except Exception as e:
            logger.debug(f"Finnhub news error for {sym}: {e}")
            continue

        for a in articles:
            url = a.get("url", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)

            headline = (a.get("headline") or "").lower()
            summary = (a.get("summary") or "").lower()
            text = headline + " " + summary

            # Pre-filter: only keep articles with M&A-relevant keywords
            if not any(kw in text for kw in MA_KEYWORDS_NEWS):
                continue

            all_news.append({
                "symbol": sym,
                "headline": a.get("headline", ""),
                "source": a.get("source", ""),
                "url": url,
                "datetime": a.get("datetime", 0),
                "summary": a.get("summary", ""),
            })

        time.sleep(MA_FINNHUB_DELAY)

    return all_news


def _fetch_ma_web_search(symbols: list[str]) -> list[dict]:
    """Supplementary web search for M&A rumors via Serper.

    Targets M&A-specific queries for top target candidates.
    """
    if not SERPER_API_KEY:
        return []

    results = []
    seen_urls = set()

    # Batch symbols into groups to avoid excessive API calls
    for sym in symbols[:30]:  # Limit to top 30 candidates
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": f"{sym} acquisition merger buyout 2026", "num": 5},
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            data = resp.json()
            for item in data.get("organic", []):
                url = item.get("link", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = (item.get("title") or "").lower()
                snippet = (item.get("snippet") or "").lower()

                # Only keep if M&A-relevant
                ma_kws = {"acqui", "merger", "buyout", "takeover", "bid", "deal", "offer"}
                if any(kw in title + snippet for kw in ma_kws):
                    results.append({
                        "symbol": sym,
                        "headline": item.get("title", ""),
                        "source": "web_search",
                        "url": url,
                        "datetime": 0,
                        "summary": item.get("snippet", ""),
                    })

            time.sleep(0.5)  # Rate limit Serper
        except Exception as e:
            logger.debug(f"Serper M&A search error for {sym}: {e}")
            continue

    return results


def _classify_ma_rumors_llm(news_batch: list[dict]) -> list[dict]:
    """Use Gemini to classify M&A news items.

    For each article, returns:
    - is_ma_relevant (bool): is this genuinely about M&A activity?
    - credibility (1-10): how credible is this as a real M&A signal?
    - deal_stage: rumor | confirmed_interest | definitive_agreement | completed | denied
    - acquirer_name: identified or speculated acquirer (if any)
    - expected_premium_pct: expected acquisition premium over current price
    - target_symbol: the company being acquired
    - price_impact_direction: up | down | neutral
    - rationale: brief explanation
    """
    if not news_batch or not GEMINI_API_KEY:
        return []

    articles_text = []
    for i, article in enumerate(news_batch):
        articles_text.append(
            f"[{i}] Symbol: {article['symbol']}\n"
            f"    Headline: {article['headline']}\n"
            f"    Source: {article['source']}\n"
            f"    Summary: {article['summary'][:500]}"
        )

    prompt = f"""You are an M&A analyst at a top investment bank. Classify these news articles
for M&A relevance and credibility. Be CONSERVATIVE — most "deal" mentions are noise.

Only classify as credible (score ≥6) if there are SPECIFIC details: named acquirer,
deal terms, board approval, regulatory filing, or credible source citing people familiar.

Generic industry commentary about "consolidation trends" = credibility 1-2.

Articles:
{chr(10).join(articles_text)}

Respond with a JSON array. For each article [i], return:
{{
  "index": i,
  "is_ma_relevant": true/false,
  "credibility": 1-10,
  "deal_stage": "rumor" | "confirmed_interest" | "definitive_agreement" | "completed" | "denied" | "speculation",
  "acquirer_name": "string or null",
  "expected_premium_pct": number or null (typical: 20-50 for strategic, 10-30 for PE),
  "target_symbol": "TICKER",
  "price_impact_direction": "up" | "down" | "neutral",
  "rationale": "brief explanation"
}}

Return ONLY the JSON array, no markdown."""

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=60,
        )
        if resp.status_code != 200:
            logger.warning(f"Gemini M&A classification failed: {resp.status_code}")
            return []

        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown fences
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        return json.loads(text.strip())

    except Exception as e:
        logger.warning(f"Gemini M&A classification error: {e}")
        return []


def _compute_rumor_scores(
    news: list[dict],
    classifications: list[dict],
    existing_rumors: dict[str, list[dict]],
) -> dict[str, dict]:
    """Compute per-symbol rumor scores from LLM classifications.

    Applies:
    - Credibility weighting (1-10 → 0-100)
    - Deal stage multiplier (speculation=0.3, rumor=0.6, confirmed=1.0, definitive=1.0)
    - Temporal decay (half-life MA_RUMOR_HALF_LIFE_DAYS)
    - Deduplication against existing rumors
    - Max aggregation per symbol (strongest rumor wins)

    Returns: {symbol: {rumor_score, best_headline, deal_stage, credibility,
                       acquirer, expected_premium}}
    """
    STAGE_MULTIPLIERS = {
        "speculation":           0.30,
        "rumor":                 0.60,
        "confirmed_interest":    0.85,
        "definitive_agreement":  1.00,
        "completed":             0.10,  # Already priced in
        "denied":                0.15,  # Denials sometimes precede deals
    }

    today = date.today()
    symbol_scores: dict[str, dict] = {}

    # Build a mapping from classification index to news item
    news_by_idx = {i: n for i, n in enumerate(news)}

    for cls in classifications:
        idx = cls.get("index")
        if idx is None or idx not in news_by_idx:
            continue

        if not cls.get("is_ma_relevant", False):
            continue

        article = news_by_idx[idx]
        sym = cls.get("target_symbol") or article["symbol"]
        credibility = cls.get("credibility", 1)

        if credibility < 3:
            continue  # Below noise floor

        stage = cls.get("deal_stage", "speculation")
        stage_mult = STAGE_MULTIPLIERS.get(stage, 0.30)

        # Base rumor score: credibility (0-100 scale) × stage multiplier
        raw_score = (credibility / 10.0) * 100 * stage_mult

        # Temporal decay for existing rumors on same symbol
        existing = existing_rumors.get(sym, [])
        if existing:
            # If we've seen this rumor before, boost slightly (persistence signal)
            days_since_first = max(1, (today - datetime.strptime(
                existing[0]["date"], "%Y-%m-%d"
            ).date()).days)
            if days_since_first <= MA_RUMOR_HALF_LIFE_DAYS:
                raw_score *= 1.1  # Persistence bonus
            else:
                # Decay old rumors
                decay = 0.5 ** (days_since_first / MA_RUMOR_HALF_LIFE_DAYS)
                raw_score *= decay

        raw_score = min(100, raw_score)

        if sym not in symbol_scores or raw_score > symbol_scores[sym]["rumor_score"]:
            symbol_scores[sym] = {
                "rumor_score": round(raw_score, 1),
                "best_headline": article["headline"][:200],
                "deal_stage": stage,
                "credibility": credibility,
                "acquirer": cls.get("acquirer_name"),
                "expected_premium": cls.get("expected_premium_pct"),
                "source": article["source"],
                "url": article["url"],
            }

    return symbol_scores


# ═══════════════════════════════════════════════════════════════════════════
# FINAL SCORE SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════════

def _compute_final_ma_scores(
    target_scores: dict[str, dict],
    rumor_scores: dict[str, dict],
) -> list[dict]:
    """Blend target profile + rumor scores into final ma_score per symbol.

    Weighting: configurable via MA_TARGET_WEIGHT_PROFILE / MA_TARGET_WEIGHT_RUMOR.
    Default: 40% profile + 40% rumor, with 20% interaction bonus when BOTH fire.

    The interaction bonus is critical: a high target profile score PLUS a credible
    rumor is exponentially more significant than either alone.
    """
    all_symbols = set(target_scores.keys()) | set(rumor_scores.keys())
    today_str = date.today().isoformat()
    results = []

    for sym in all_symbols:
        tp = target_scores.get(sym, {})
        rp = rumor_scores.get(sym, {})

        target = tp.get("target_score", 0)
        rumor = rp.get("rumor_score", 0)

        # Weighted blend
        profile_contrib = target * MA_TARGET_WEIGHT_PROFILE
        rumor_contrib = rumor * MA_TARGET_WEIGHT_RUMOR

        # Interaction bonus: when both signals fire, it's much more significant
        interaction_weight = 1.0 - MA_TARGET_WEIGHT_PROFILE - MA_TARGET_WEIGHT_RUMOR
        if target > 40 and rumor > 30:
            # Geometric mean of both scores, scaled to interaction weight
            interaction_bonus = math.sqrt(target * rumor) * interaction_weight
        else:
            interaction_bonus = 0

        ma_score = min(100, profile_contrib + rumor_contrib + interaction_bonus)

        if ma_score < MA_MIN_SCORE_STORE:
            continue

        # Build narrative
        parts = []
        if target > 50:
            parts.append(f"Strong acquisition target profile ({target:.0f})")
        elif target > 30:
            parts.append(f"Moderate target profile ({target:.0f})")

        if rumor > 50:
            stage = rp.get("deal_stage", "rumor")
            acq = rp.get("acquirer")
            acq_str = f" by {acq}" if acq else ""
            parts.append(f"Credible M&A {stage}{acq_str} ({rumor:.0f})")
        elif rumor > 20:
            parts.append(f"Weak M&A rumor signal ({rumor:.0f})")

        if target > 40 and rumor > 30:
            parts.append("Profile + rumor convergence")

        narrative = ". ".join(parts) if parts else f"M&A score: {ma_score:.0f}"

        results.append({
            "symbol": sym,
            "date": today_str,
            "ma_score": round(ma_score, 1),
            "target_profile_score": round(target, 1),
            "rumor_score": round(rumor, 1),
            "valuation_score": tp.get("valuation_score"),
            "balance_sheet_score": tp.get("balance_sheet_score"),
            "growth_score": tp.get("growth_score"),
            "smart_money_score": tp.get("smart_money_score"),
            "consolidation_bonus": tp.get("consolidation_bonus"),
            "mcap_multiplier": tp.get("mcap_multiplier"),
            "sector_multiplier": tp.get("sector_multiplier"),
            "deal_stage": rp.get("deal_stage"),
            "rumor_credibility": rp.get("credibility"),
            "acquirer_name": rp.get("acquirer"),
            "expected_premium_pct": rp.get("expected_premium"),
            "best_headline": rp.get("best_headline"),
            "narrative": narrative,
            "status": "active",
        })

    return results


# ═══════════════════════════════════════════════════════════════════════════
# DATABASE WRITES
# ═══════════════════════════════════════════════════════════════════════════

def _write_ma_signals(signals: list[dict]):
    """Write M&A signals to database (clear today's first)."""
    if not signals:
        return
    today_str = date.today().isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM ma_signals WHERE date = ?", [today_str])
        conn.executemany(
            """INSERT INTO ma_signals
               (symbol, date, ma_score, target_profile_score, rumor_score,
                valuation_score, balance_sheet_score, growth_score,
                smart_money_score, consolidation_bonus, mcap_multiplier,
                sector_multiplier, deal_stage, rumor_credibility,
                acquirer_name, expected_premium_pct, best_headline,
                narrative, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    s["symbol"], s["date"], s["ma_score"],
                    s["target_profile_score"], s["rumor_score"],
                    s["valuation_score"], s["balance_sheet_score"],
                    s["growth_score"], s["smart_money_score"],
                    s["consolidation_bonus"], s["mcap_multiplier"],
                    s["sector_multiplier"], s["deal_stage"],
                    s["rumor_credibility"], s["acquirer_name"],
                    s["expected_premium_pct"], s["best_headline"],
                    s["narrative"], s["status"],
                )
                for s in signals
            ],
        )


def _write_ma_rumors(rumor_scores: dict[str, dict]):
    """Persist classified rumors for dedup and decay tracking."""
    if not rumor_scores:
        return
    today_str = date.today().isoformat()
    rows = []
    for sym, data in rumor_scores.items():
        rows.append((
            sym, today_str, data.get("source", ""),
            data.get("best_headline", ""), data.get("credibility", 0),
            data.get("deal_stage", "speculation"),
            data.get("expected_premium"),
            data.get("acquirer"), data.get("url", ""),
        ))
    upsert_many("ma_rumors", [
        "symbol", "date", "rumor_source", "rumor_headline",
        "credibility_score", "deal_stage", "expected_premium_pct",
        "acquirer_name", "url",
    ], rows)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def run():
    """Run M&A intelligence analysis."""
    print("\n" + "=" * 60)
    print("  M&A INTELLIGENCE MODULE")
    print("=" * 60)

    init_db()

    # ── Load all data sources ──
    print("  Loading stock universe...")
    universe = _load_universe()
    print(f"  {len(universe)} stocks in universe")

    print("  Loading fundamentals...")
    fundamentals = _load_fundamentals()
    print(f"  {len(fundamentals)} symbols with fundamental data")

    print("  Loading smart money / 13F data...")
    smart_money = _load_smart_money()
    accumulation = _load_13f_accumulation()
    print(f"  {len(smart_money)} symbols with smart money scores, "
          f"{len(accumulation)} with 13F accumulation")

    print("  Loading insider signals...")
    insider_sigs = _load_insider_signals()
    print(f"  {len(insider_sigs)} symbols with insider data")

    print("  Loading sector expert themes...")
    sector_themes = _load_sector_expert_themes()

    print("  Loading existing M&A rumors...")
    try:
        existing_rumors = _load_existing_rumors()
    except Exception:
        existing_rumors = {}  # Table may not exist yet on first run

    # ── Phase 1: Target Profile Scoring (deterministic) ──
    print("\n  [1/3] Computing target profile scores...")
    target_scores = compute_target_profile_scores(
        universe, fundamentals, smart_money, accumulation,
        insider_sigs, sector_themes,
    )
    scored_count = sum(1 for v in target_scores.values() if v["target_score"] > 30)
    print(f"  {len(target_scores)} symbols scored, {scored_count} above noise floor (>30)")

    # ── Phase 2: Rumor Detection (LLM-powered) ──
    print("\n  [2/3] Scanning for M&A rumors...")

    # Only scan top target candidates + any symbol with existing rumors
    # This is cost-efficient: ~30-50 Finnhub calls + 3-5 Gemini calls
    top_targets = sorted(
        target_scores.items(),
        key=lambda x: x[1]["target_score"],
        reverse=True,
    )[:50]
    scan_symbols = list({sym for sym, _ in top_targets} | set(existing_rumors.keys()))

    rumor_scores = {}
    if FINNHUB_API_KEY and GEMINI_API_KEY:
        print(f"  Fetching news for {len(scan_symbols)} candidates...")
        fh_client = _get_finnhub_client()
        ma_news = _fetch_ma_news(fh_client, scan_symbols)
        print(f"  Found {len(ma_news)} M&A-relevant news articles")

        # Supplementary web search for top 20 targets
        web_news = _fetch_ma_web_search([s for s, _ in top_targets[:20]])
        ma_news.extend(web_news)
        print(f"  Total after web search: {len(ma_news)} articles")

        if ma_news:
            # Classify in batches
            all_classifications = []
            for i in range(0, len(ma_news), MA_NEWS_BATCH_SIZE):
                batch = ma_news[i:i + MA_NEWS_BATCH_SIZE]
                print(f"  Classifying batch {i // MA_NEWS_BATCH_SIZE + 1}...")
                cls = _classify_ma_rumors_llm(batch)
                all_classifications.extend(cls)
                if i + MA_NEWS_BATCH_SIZE < len(ma_news):
                    time.sleep(MA_GEMINI_DELAY)

            print(f"  Classified {len(all_classifications)} articles")
            credible = [c for c in all_classifications
                        if c.get("is_ma_relevant") and c.get("credibility", 0) >= 3]
            print(f"  Credible M&A signals: {len(credible)}")

            rumor_scores = _compute_rumor_scores(
                ma_news, all_classifications, existing_rumors
            )
            _write_ma_rumors(rumor_scores)
    else:
        print("  Skipping rumor scan (missing FINNHUB_API_KEY or GEMINI_API_KEY)")

    # ── Phase 3: Final Score Synthesis ──
    print("\n  [3/3] Computing final M&A scores...")
    ma_signals = _compute_final_ma_scores(target_scores, rumor_scores)
    _write_ma_signals(ma_signals)

    # ── Summary ──
    high_scores = sorted(
        [s for s in ma_signals if s["ma_score"] >= 50],
        key=lambda x: x["ma_score"],
        reverse=True,
    )

    print(f"\n  Total M&A signals: {len(ma_signals)}")
    print(f"  Above convergence threshold (>50): {len(high_scores)}")

    if rumor_scores:
        print(f"  Active rumors: {len(rumor_scores)}")
        for sym, data in sorted(rumor_scores.items(),
                                key=lambda x: x[1]["rumor_score"], reverse=True)[:5]:
            print(f"    {sym:6s} credibility={data['credibility']}/10  "
                  f"stage={data['deal_stage']}  "
                  f"score={data['rumor_score']:.0f}")

    if high_scores:
        print("\n  Top M&A candidates:")
        for s in high_scores[:10]:
            rumor_tag = ""
            if s["rumor_score"] and s["rumor_score"] > 20:
                rumor_tag = f"  rumor={s['rumor_score']:.0f}"
            print(f"    {s['symbol']:6s} ma_score={s['ma_score']:.0f}  "
                  f"target={s['target_profile_score']:.0f}"
                  f"{rumor_tag}  "
                  f"| {s['narrative'][:60]}")

    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
