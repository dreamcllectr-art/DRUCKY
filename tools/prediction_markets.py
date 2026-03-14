"""Prediction Markets Module — Polymarket event probabilities → stock signals.

Fetches active prediction markets from Polymarket's Gamma API,
classifies financially-relevant markets, and translates event probabilities
into sector/stock-level signals for the convergence engine.

Key insight: prediction markets aggregate thousands of informed bettors into
calibrated probabilities. When Polymarket says "72% chance Fed cuts in June",
that's a better forecast than any single analyst.

Signal pipeline:
  1. Fetch active markets with volume > threshold (filter noise)
  2. Classify markets by financial relevance category (Gemini LLM)
  3. Map categories → sector/stock impacts with directional probability
  4. Score each symbol 0-100 based on probability-weighted impacts
  5. Store in prediction_market_signals table

Categories tracked:
  - monetary_policy: Fed rate decisions, QT/QE
  - inflation: CPI, PCE, inflation expectations
  - fiscal: government spending, tax policy, debt ceiling
  - trade: tariffs, trade agreements, sanctions
  - geopolitics: wars, elections, regime changes
  - sector_specific: industry regulation, antitrust, sector events
  - company_specific: IPOs, mergers, earnings surprises

Usage: python -m tools.prediction_markets
"""

import sys
import json
import time
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    PM_MIN_VOLUME, PM_MIN_LIQUIDITY, PM_CLASSIFICATION_BATCH_SIZE,
    PM_GEMINI_DELAY, PM_FETCH_LIMIT, PM_PROBABILITY_STRONG_THRESHOLD,
    PM_PROBABILITY_MODERATE_THRESHOLD, PM_LOOKBACK_DAYS,
)
from tools.db import init_db, upsert_many, query, get_conn

logger = logging.getLogger(__name__)

# ── Polymarket Gamma API ──────────────────────────────────────────────
GAMMA_API_BASE = "https://gamma-api.polymarket.com"

# ── Category → Sector/Stock Impact Mapping ────────────────────────────
# Each category defines how a YES outcome shifts sectors.
# The LLM classifies the market AND identifies direction (is YES bullish or bearish?).
# These are default sector tilts; LLM can override per-market.

CATEGORY_SECTOR_IMPACTS = {
    "fed_rate_cut": {
        "bullish": ["Technology", "Consumer Discretionary", "Real Estate",
                     "Communication Services"],
        "bearish": ["Financials"],
        "symbols_bullish": [],
        "symbols_bearish": [],
    },
    "fed_rate_hike": {
        "bullish": ["Financials", "Energy"],
        "bearish": ["Technology", "Consumer Discretionary", "Real Estate"],
        "symbols_bullish": [],
        "symbols_bearish": [],
    },
    "inflation_higher": {
        "bullish": ["Energy", "Materials", "Real Estate"],
        "bearish": ["Technology", "Consumer Discretionary", "Utilities"],
        "symbols_bullish": ["GLD", "XOM", "CVX"],
        "symbols_bearish": [],
    },
    "inflation_lower": {
        "bullish": ["Technology", "Consumer Discretionary"],
        "bearish": ["Energy", "Materials"],
        "symbols_bullish": [],
        "symbols_bearish": [],
    },
    "tariff_increase": {
        "bullish": ["Utilities", "Consumer Staples"],
        "bearish": ["Technology", "Industrials", "Materials",
                     "Consumer Discretionary"],
        "symbols_bullish": [],
        "symbols_bearish": ["AAPL", "TSLA", "NKE", "CAT"],
    },
    "tariff_decrease": {
        "bullish": ["Technology", "Industrials", "Materials"],
        "bearish": ["Utilities"],
        "symbols_bullish": ["AAPL", "TSLA", "NKE", "CAT"],
        "symbols_bearish": [],
    },
    "recession_risk": {
        "bullish": ["Utilities", "Consumer Staples", "Health Care"],
        "bearish": ["Consumer Discretionary", "Financials", "Industrials",
                     "Materials", "Energy"],
        "symbols_bullish": ["GLD"],
        "symbols_bearish": [],
    },
    "government_spending_increase": {
        "bullish": ["Industrials", "Materials", "Health Care"],
        "bearish": [],
        "symbols_bullish": ["LMT", "RTX", "NOC", "GD"],
        "symbols_bearish": [],
    },
    "tech_regulation": {
        "bullish": [],
        "bearish": ["Technology", "Communication Services"],
        "symbols_bullish": [],
        "symbols_bearish": ["GOOGL", "META", "AMZN", "AAPL", "MSFT"],
    },
    "energy_policy_green": {
        "bullish": ["Utilities"],
        "bearish": ["Energy"],
        "symbols_bullish": ["ENPH", "FSLR", "NEE"],
        "symbols_bearish": ["XOM", "CVX", "COP"],
    },
    "energy_policy_fossil": {
        "bullish": ["Energy"],
        "bearish": [],
        "symbols_bullish": ["XOM", "CVX", "COP", "OXY"],
        "symbols_bearish": ["ENPH", "FSLR"],
    },
    "geopolitical_escalation": {
        "bullish": ["Energy", "Utilities", "Consumer Staples"],
        "bearish": ["Technology", "Consumer Discretionary", "Financials"],
        "symbols_bullish": ["LMT", "RTX", "NOC", "GLD"],
        "symbols_bearish": [],
    },
    "china_slowdown": {
        "bullish": ["Utilities", "Consumer Staples"],
        "bearish": ["Materials", "Industrials", "Energy"],
        "symbols_bullish": [],
        "symbols_bearish": ["CAT", "DE", "FCX", "NEM"],
    },
    "crypto_regulation_positive": {
        "bullish": ["Financials"],
        "bearish": [],
        "symbols_bullish": ["COIN", "MSTR", "SQ"],
        "symbols_bearish": [],
    },
}


def _fetch_active_markets() -> list[dict]:
    """Fetch active prediction markets from Polymarket Gamma API.

    Filters by volume and liquidity to eliminate noise markets.
    Returns list of market dicts with question, probability, volume, etc.
    """
    markets = []
    offset = 0
    limit = 100  # Gamma API page size

    while len(markets) < PM_FETCH_LIMIT:
        try:
            resp = requests.get(
                f"{GAMMA_API_BASE}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                    "offset": offset,
                },
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json()

            if not batch:
                break

            for m in batch:
                vol = float(m.get("volumeNum", 0) or 0)
                liq = float(m.get("liquidityNum", 0) or 0)

                if vol < PM_MIN_VOLUME or liq < PM_MIN_LIQUIDITY:
                    continue

                # Parse outcome prices
                outcome_prices = []
                try:
                    outcome_prices = json.loads(m.get("outcomePrices", "[]"))
                except (json.JSONDecodeError, TypeError):
                    pass

                yes_prob = float(outcome_prices[0]) if outcome_prices else None

                if yes_prob is None:
                    continue

                markets.append({
                    "id": m.get("conditionId", m.get("id", "")),
                    "question": m.get("question", ""),
                    "category": m.get("category", ""),
                    "yes_probability": yes_prob,
                    "no_probability": 1.0 - yes_prob,
                    "volume": vol,
                    "liquidity": liq,
                    "end_date": m.get("endDate", ""),
                    "description": (m.get("description", "") or "")[:500],
                    "volume_24h": float(m.get("volume24hr", 0) or 0),
                    "open_interest": float(m.get("openInterest", 0) or 0),
                })

            offset += limit
            time.sleep(0.3)  # rate limit

        except requests.RequestException as e:
            logger.warning(f"Polymarket API error at offset {offset}: {e}")
            break

    logger.info(f"Fetched {len(markets)} active markets (vol >= ${PM_MIN_VOLUME:,.0f}, liq >= ${PM_MIN_LIQUIDITY:,.0f})")
    return markets


def _classify_markets_batch(markets: list[dict]) -> list[dict]:
    """Use Gemini to classify markets by financial relevance.

    For each market, determines:
      - is_relevant: bool (does this market have stock market implications?)
      - impact_category: str (key from CATEGORY_SECTOR_IMPACTS)
      - direction: "yes_bullish" or "yes_bearish" (is YES outcome good for stocks?)
      - confidence: 0-100
      - specific_symbols: list of directly impacted tickers
      - rationale: one-line explanation

    Returns markets with classification fields added.
    """
    if not GEMINI_API_KEY:
        logger.warning("No Gemini API key — skipping classification")
        return []

    categories_list = list(CATEGORY_SECTOR_IMPACTS.keys())
    classified = []

    for i in range(0, len(markets), PM_CLASSIFICATION_BATCH_SIZE):
        batch = markets[i:i + PM_CLASSIFICATION_BATCH_SIZE]

        market_texts = []
        for idx, m in enumerate(batch):
            market_texts.append(
                f"{idx+1}. Q: \"{m['question']}\" | "
                f"YES={m['yes_probability']:.0%} | "
                f"Vol=${m['volume']:,.0f} | "
                f"Category: {m['category']} | "
                f"Ends: {m['end_date'][:10] if m['end_date'] else 'N/A'}"
            )

        prompt = f"""You are a macro strategist classifying prediction markets for stock market impact.

For each market below, determine if it has DIRECT implications for US stock sectors or specific stocks.
Skip sports, entertainment, celebrity, and other non-financial markets.

Available impact categories: {json.dumps(categories_list)}

For each market, respond with a JSON array of objects:
{{
  "index": <1-based index>,
  "is_relevant": true/false,
  "impact_category": "<category from list above or null>",
  "direction": "yes_bullish" or "yes_bearish",
  "confidence": <0-100>,
  "specific_symbols": ["TICKER1", "TICKER2"],
  "rationale": "<one sentence>"
}}

Markets:
{chr(10).join(market_texts)}

Respond ONLY with the JSON array, no other text."""

        try:
            resp = requests.post(
                f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
                headers={"Content-Type": "application/json"},
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.2,
                        "maxOutputTokens": 2048,
                    },
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

            # Parse JSON from response (handle markdown code blocks)
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            classifications = json.loads(text)

            for cls in classifications:
                idx = cls.get("index", 0) - 1
                if 0 <= idx < len(batch) and cls.get("is_relevant"):
                    market = batch[idx].copy()
                    market["impact_category"] = cls.get("impact_category")
                    market["direction"] = cls.get("direction", "yes_bullish")
                    market["confidence"] = cls.get("confidence", 50)
                    market["specific_symbols"] = cls.get("specific_symbols", [])
                    market["rationale"] = cls.get("rationale", "")
                    classified.append(market)

        except Exception as e:
            logger.warning(f"Gemini classification batch error: {e}")

        time.sleep(PM_GEMINI_DELAY)

    logger.info(f"Classified {len(classified)} financially-relevant markets from {len(markets)} total")
    return classified


def _compute_symbol_scores(classified_markets: list[dict]) -> dict[str, dict]:
    """Translate classified markets into per-symbol scores.

    For each market:
      1. Look up sector impacts from CATEGORY_SECTOR_IMPACTS
      2. Weight by probability * confidence * volume_factor
      3. Aggregate across all markets for each symbol

    Returns: {symbol: {"score": 0-100, "signals": [...], "market_count": N}}
    """
    # Load stock universe with sectors
    stocks = query("""
        SELECT symbol, sector FROM stock_universe
        WHERE symbol IS NOT NULL AND sector IS NOT NULL
    """)
    sector_map = {r["symbol"]: r["sector"] for r in stocks}

    # Accumulate impact signals per symbol
    symbol_signals: dict[str, list[dict]] = {}

    for market in classified_markets:
        cat = market.get("impact_category")
        if not cat or cat not in CATEGORY_SECTOR_IMPACTS:
            continue

        impacts = CATEGORY_SECTOR_IMPACTS[cat]
        prob = market["yes_probability"]
        direction = market.get("direction", "yes_bullish")
        conf = market.get("confidence", 50) / 100.0

        # If YES is bearish, flip: high prob of bearish event = negative signal
        # We use the probability as-is for the dominant outcome
        effective_prob = prob if direction == "yes_bullish" else (1.0 - prob)

        # Volume factor: log scale, normalized. $1M = 1.0, $10M = 1.3, $100M = 1.7
        import math
        vol_factor = min(2.0, max(0.5, math.log10(max(market["volume"], 1000)) - 3.0))

        signal_strength = effective_prob * conf * vol_factor

        signal_info = {
            "question": market["question"][:100],
            "category": cat,
            "probability": prob,
            "direction": direction,
            "strength": signal_strength,
        }

        # Apply to sectors
        for symbol, sector in sector_map.items():
            impact = 0.0
            if sector in impacts.get("bullish", []):
                impact = signal_strength * 0.6  # Sector-level impact
            elif sector in impacts.get("bearish", []):
                impact = -signal_strength * 0.6
            # Direct symbol impact (stronger)
            if symbol in impacts.get("symbols_bullish", []):
                impact += signal_strength * 0.9
            elif symbol in impacts.get("symbols_bearish", []):
                impact -= signal_strength * 0.9
            # LLM-identified specific symbols
            if symbol in market.get("specific_symbols", []):
                impact += signal_strength * 0.8 if direction == "yes_bullish" else -signal_strength * 0.8

            if abs(impact) > 0.01:
                symbol_signals.setdefault(symbol, []).append({
                    **signal_info,
                    "impact": impact,
                })

    # Aggregate into 0-100 scores
    results = {}
    for symbol, signals in symbol_signals.items():
        # Net impact: sum of all signal impacts
        net_impact = sum(s["impact"] for s in signals)
        # Count of contributing markets
        market_count = len(signals)
        # Confidence boost for multiple agreeing signals
        agreement_mult = min(1.5, 1.0 + (market_count - 1) * 0.1)

        # Convert net impact to 0-100 score
        # net_impact typically ranges from -3 to +3 for well-covered symbols
        # Map: -2 → 0, 0 → 50, +2 → 100
        raw_score = (net_impact / 2.0 + 1.0) / 2.0 * 100.0
        raw_score *= agreement_mult
        score = max(0.0, min(100.0, raw_score))

        # Only store if meaningfully different from neutral (50)
        if abs(score - 50.0) > 5.0:
            results[symbol] = {
                "score": round(score, 2),
                "signals": signals[:5],  # Keep top 5 for narrative
                "market_count": market_count,
                "net_impact": round(net_impact, 4),
            }

    return results


def compute_prediction_market_scores() -> dict[str, float]:
    """Compute prediction market scores for convergence engine.

    Reads from prediction_market_signals table (last N days).
    Returns: {symbol: score_0_to_100}
    """
    rows = query(f"""
        SELECT symbol, MAX(pm_score) as score
        FROM prediction_market_signals
        WHERE date >= date('now', '-{PM_LOOKBACK_DAYS} days')
          AND status = 'active'
        GROUP BY symbol
    """)
    return {r["symbol"]: r["score"] for r in rows if r["score"]}


def run():
    """Main entry: fetch Polymarket data, classify, score, persist."""
    init_db()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  PREDICTION MARKETS MODULE (Polymarket)")
    print("=" * 60)

    # Step 1: Fetch active markets
    print("\n  Step 1: Fetching active Polymarket markets...")
    markets = _fetch_active_markets()
    if not markets:
        print("  No markets found above volume/liquidity thresholds")
        return
    print(f"  Fetched {len(markets)} markets above thresholds")

    # Step 2: Classify financial relevance
    print("\n  Step 2: Classifying markets for financial relevance...")
    classified = _classify_markets_batch(markets)
    if not classified:
        print("  No financially-relevant markets found")
        return

    # Print classified markets
    print(f"\n  RELEVANT MARKETS ({len(classified)}):")
    print(f"  {'Question':<55} {'YES%':>5} {'Category':<24} {'Vol':>10}")
    print(f"  {'-'*98}")
    for m in sorted(classified, key=lambda x: x["volume"], reverse=True)[:15]:
        q = m["question"][:54]
        print(f"  {q:<55} {m['yes_probability']:>4.0%} {m.get('impact_category',''):<24} ${m['volume']:>9,.0f}")

    # Step 3: Compute per-symbol scores
    print("\n  Step 3: Computing symbol-level scores...")
    symbol_scores = _compute_symbol_scores(classified)
    if not symbol_scores:
        print("  No symbol scores generated")
        return

    # Step 4: Persist signals
    rows = []
    for symbol, data in symbol_scores.items():
        # Build narrative from top signals
        top_signals = sorted(data["signals"], key=lambda s: abs(s["impact"]), reverse=True)[:3]
        narrative_parts = []
        for sig in top_signals:
            direction_word = "supports" if sig["impact"] > 0 else "pressures"
            narrative_parts.append(
                f"{sig['question'][:60]} ({sig['probability']:.0%} → {direction_word})"
            )
        narrative = "; ".join(narrative_parts)

        rows.append((
            symbol, today, round(data["score"], 2),
            data["market_count"], round(data["net_impact"], 4),
            "active", narrative[:500],
        ))

    if rows:
        upsert_many(
            "prediction_market_signals",
            ["symbol", "date", "pm_score", "market_count",
             "net_impact", "status", "narrative"],
            rows,
        )

    # Also persist the classified markets themselves for audit
    market_rows = []
    for m in classified:
        market_rows.append((
            m["id"][:64], today, m["question"][:300],
            m.get("impact_category", ""),
            round(m["yes_probability"], 4),
            round(m["volume"], 2),
            round(m["liquidity"], 2),
            m.get("direction", "yes_bullish"),
            m.get("confidence", 50),
            json.dumps(m.get("specific_symbols", [])),
            m.get("rationale", "")[:300],
            m.get("end_date", "")[:10],
        ))

    if market_rows:
        upsert_many(
            "prediction_market_raw",
            ["market_id", "date", "question", "impact_category",
             "yes_probability", "volume", "liquidity", "direction",
             "confidence", "specific_symbols", "rationale", "end_date"],
            market_rows,
        )

    # Summary
    bullish = sum(1 for d in symbol_scores.values() if d["score"] > 55)
    bearish = sum(1 for d in symbol_scores.values() if d["score"] < 45)
    neutral = len(symbol_scores) - bullish - bearish

    print(f"\n  Results: {len(symbol_scores)} symbols scored from {len(classified)} markets")
    print(f"  Bullish: {bullish} | Neutral: {neutral} | Bearish: {bearish}")

    # Top signals
    top_bullish = sorted(
        [(s, d) for s, d in symbol_scores.items() if d["score"] > 55],
        key=lambda x: x[1]["score"], reverse=True
    )[:10]
    top_bearish = sorted(
        [(s, d) for s, d in symbol_scores.items() if d["score"] < 45],
        key=lambda x: x[1]["score"]
    )[:10]

    if top_bullish:
        print(f"\n  TOP BULLISH (prediction market tailwinds):")
        print(f"  {'Symbol':<8} {'Score':>6} {'Markets':>8} {'Net Impact':>11}")
        for sym, data in top_bullish:
            print(f"  {sym:<8} {data['score']:>6.1f} {data['market_count']:>8} {data['net_impact']:>+11.3f}")

    if top_bearish:
        print(f"\n  TOP BEARISH (prediction market headwinds):")
        print(f"  {'Symbol':<8} {'Score':>6} {'Markets':>8} {'Net Impact':>11}")
        for sym, data in top_bearish:
            print(f"  {sym:<8} {data['score']:>6.1f} {data['market_count']:>8} {data['net_impact']:>+11.3f}")

    print(f"\nPrediction Markets complete: {len(rows)} signals persisted")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
