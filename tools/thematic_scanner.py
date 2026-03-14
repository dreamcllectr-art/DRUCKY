"""Thematic Alpha Scanner — small/mid-cap trading ideas across policy-driven themes.

Standalone module (NOT a convergence module). Identifies asymmetric opportunities
in small/mid-cap stocks ($300M-$10B) driven by secular policy tailwinds.

Themes:
  1. AI Infrastructure — data centers, cooling, chips, AI software, GPU/compute
  2. Energy Buildout — solar, nuclear, grid modernization, battery, EV charging
  3. Fintech & Stablecoins — payments, crypto infra, digital banking, blockchain
  4. Defense Tech — drones, cybersecurity, space, autonomous systems
  5. Reshoring & CHIPS — semiconductor fabs, industrial automation, supply chain

Scoring per stock (0-100):
  - Policy Exposure (25%): How directly does legislation/regulation benefit this name?
  - Growth Quality (25%): Revenue growth, earnings trajectory, margin expansion
  - Technical Setup (20%): Price momentum, RS vs theme ETF, breakout proximity
  - Valuation Opportunity (15%): P/S, P/E vs growth, not priced in yet
  - Institutional Signal (15%): Smart money, insider buying, analyst upgrades

Pipeline phase: standalone (runs after convergence engine, or independently)
Dashboard: /trading-ideas
"""

import sys
import json
import math
import time
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import (
    TS_THEMES,
    TS_MCAP_MIN,
    TS_MCAP_MAX,
    TS_SCORE_WEIGHTS,
    TS_TOP_N_PER_THEME,
    TS_YFINANCE_DELAY,
    TS_POLICY_SCORES,
)
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


# ─────────────────────────────────────────────────────────
# Universe Management
# ─────────────────────────────────────────────────────────

def get_theme_universe() -> dict[str, list[dict]]:
    """Return the full curated universe organized by theme.

    Each entry: {symbol, name, sub_theme, policy_exposure}
    """
    return TS_THEMES


def _fetch_yfinance_data(symbols: list[str]) -> dict[str, dict]:
    """Fetch price + fundamental data for a list of symbols via yfinance.

    Returns dict keyed by symbol with keys:
      price, market_cap, pe, ps, revenue_growth, earnings_growth,
      profit_margin, rsi_14, price_vs_52w_high, avg_volume,
      sma_50, sma_200, beta, sector, industry
    """
    import yfinance as yf

    results = {}
    batch_size = 20

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        tickers_str = " ".join(batch)

        try:
            tickers = yf.Tickers(tickers_str)
            for sym in batch:
                try:
                    t = tickers.tickers.get(sym)
                    if t is None:
                        continue

                    info = t.info or {}
                    price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
                    mcap = info.get("marketCap", 0)

                    # Flag market cap range — skip if way outside range
                    mcap_in_range = bool(mcap and TS_MCAP_MIN <= mcap <= TS_MCAP_MAX)
                    if mcap and mcap > TS_MCAP_MAX * 3:
                        logger.debug(f"{sym}: mcap ${mcap/1e9:.1f}B far above range, skipping")
                        continue
                    if mcap and mcap < TS_MCAP_MIN * 0.5:
                        logger.debug(f"{sym}: mcap ${mcap/1e6:.0f}M far below range, skipping")
                        continue

                    # Technicals from history
                    hist = t.history(period="1y")
                    if hist.empty or len(hist) < 20:
                        continue

                    close = hist["Close"]
                    sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else close.mean()
                    sma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.mean()
                    high_52w = close.max()
                    low_52w = close.min()
                    current_price = close.iloc[-1]

                    # RSI (guard against NaN from no losses or no gains)
                    delta = close.diff()
                    gain = delta.where(delta > 0, 0).rolling(14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    g_val = gain.iloc[-1] if not gain.empty else 0
                    l_val = loss.iloc[-1] if not loss.empty else 0
                    if l_val is None or (isinstance(l_val, float) and math.isnan(l_val)) or l_val == 0:
                        rsi = 100.0 if (g_val and not math.isnan(g_val) and g_val > 0) else 50.0
                    else:
                        rs = g_val / l_val
                        rsi = 100 - (100 / (1 + rs)) if not math.isnan(rs) else 50.0

                    # 3-month momentum
                    mom_3m = ((current_price / close.iloc[-63]) - 1) * 100 if len(close) >= 63 else 0

                    # Volume trend
                    vol = hist["Volume"]
                    avg_vol_20 = vol.rolling(20).mean().iloc[-1] if len(vol) >= 20 else vol.mean()

                    results[sym] = {
                        "price": float(current_price),
                        "market_cap": mcap or 0,
                        "mcap_in_range": mcap_in_range,
                        "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
                        "ps_ratio": info.get("priceToSalesTrailing12Months"),
                        "peg_ratio": info.get("pegRatio"),
                        "revenue_growth": info.get("revenueGrowth"),  # quarterly YoY
                        "earnings_growth": info.get("earningsGrowth"),
                        "profit_margin": info.get("profitMargins"),
                        "gross_margin": info.get("grossMargins"),
                        "rsi_14": float(rsi),
                        "momentum_3m": float(mom_3m),
                        "price_vs_52w_high": float(current_price / high_52w) if high_52w else 0,
                        "price_vs_52w_low": float(current_price / low_52w) if low_52w else 0,
                        "sma_50": float(sma_50),
                        "sma_200": float(sma_200),
                        "above_sma50": current_price > sma_50,
                        "above_sma200": current_price > sma_200,
                        "avg_volume": float(avg_vol_20),
                        "beta": info.get("beta"),
                        "sector": info.get("sector", ""),
                        "industry": info.get("industry", ""),
                        "short_pct": info.get("shortPercentOfFloat"),
                        "target_mean_price": info.get("targetMeanPrice"),
                        "recommendation": info.get("recommendationKey"),
                        "num_analysts": info.get("numberOfAnalystOpinions", 0),
                    }
                except Exception as e:
                    logger.warning(f"yfinance error for {sym}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"yfinance batch error: {e}")

        if i + batch_size < len(symbols):
            time.sleep(TS_YFINANCE_DELAY)

    return results


# ─────────────────────────────────────────────────────────
# Sub-Score 1: Policy Exposure (25%)
# ─────────────────────────────────────────────────────────

def _score_policy_exposure(sym: str, theme_entry: dict) -> float:
    """Score 0-100 based on how directly this stock benefits from policy tailwinds.

    Uses curated policy_exposure tier from TS_THEMES config.
    Tier 1 (direct beneficiary) = 85-100
    Tier 2 (strong indirect) = 60-84
    Tier 3 (moderate exposure) = 35-59
    """
    tier = theme_entry.get("policy_tier", 2)
    base = TS_POLICY_SCORES.get(tier, 50)

    # Bonus for multiple policy catalysts
    catalysts = theme_entry.get("catalysts", [])
    catalyst_bonus = min(len(catalysts) * 5, 15)

    return _clamp(base + catalyst_bonus)


# ─────────────────────────────────────────────────────────
# Sub-Score 2: Growth Quality (25%)
# ─────────────────────────────────────────────────────────

def _score_growth(data: dict) -> float:
    """Score 0-100 based on revenue/earnings growth + margins."""
    score = 50.0  # baseline

    # Revenue growth (biggest weight for small caps)
    rev_g = data.get("revenue_growth")
    if rev_g is not None:
        if rev_g > 0.50:
            score += 25
        elif rev_g > 0.25:
            score += 18
        elif rev_g > 0.10:
            score += 10
        elif rev_g > 0:
            score += 3
        elif rev_g > -0.10:
            score -= 5
        else:
            score -= 15

    # Earnings growth
    earn_g = data.get("earnings_growth")
    if earn_g is not None:
        if earn_g > 0.50:
            score += 15
        elif earn_g > 0.20:
            score += 10
        elif earn_g > 0:
            score += 5
        elif earn_g < -0.20:
            score -= 10

    # Profitability trajectory
    margin = data.get("profit_margin")
    if margin is not None:
        if margin > 0.20:
            score += 10  # Profitable + high margin
        elif margin > 0.05:
            score += 5
        elif margin > 0:
            score += 2
        elif margin > -0.10:
            score -= 3  # Slightly negative, could turn
        else:
            score -= 8  # Deep negative margin

    return _clamp(score)


# ─────────────────────────────────────────────────────────
# Sub-Score 3: Technical Setup (20%)
# ─────────────────────────────────────────────────────────

def _score_technical(data: dict) -> float:
    """Score 0-100 based on price momentum, trend, and breakout proximity."""
    score = 50.0

    # Trend structure
    if data.get("above_sma200"):
        score += 10
    else:
        score -= 10

    if data.get("above_sma50"):
        score += 8
    else:
        score -= 5

    # Golden cross / death cross
    sma50 = data.get("sma_50", 0)
    sma200 = data.get("sma_200", 0)
    if sma50 and sma200:
        if sma50 > sma200:
            score += 5  # Golden cross territory
        else:
            score -= 5

    # RSI — want momentum but not overbought
    rsi = data.get("rsi_14", 50)
    if 55 <= rsi <= 70:
        score += 10  # Momentum without exhaustion
    elif 40 <= rsi < 55:
        score += 3   # Neutral
    elif 30 <= rsi < 40:
        score += 5   # Oversold bounce potential
    elif rsi < 30:
        score -= 5   # Broken
    elif rsi > 75:
        score -= 8   # Overbought

    # 3-month momentum
    mom = data.get("momentum_3m", 0)
    if mom > 20:
        score += 12
    elif mom > 10:
        score += 8
    elif mom > 0:
        score += 3
    elif mom > -10:
        score -= 3
    else:
        score -= 10

    # Proximity to 52-week high (breakout potential)
    pct_of_high = data.get("price_vs_52w_high", 0)
    if pct_of_high > 0.95:
        score += 8  # Near highs, breakout zone
    elif pct_of_high > 0.85:
        score += 4
    elif pct_of_high < 0.60:
        score -= 8  # Far from highs, broken chart

    return _clamp(score)


# ─────────────────────────────────────────────────────────
# Sub-Score 4: Valuation Opportunity (15%)
# ─────────────────────────────────────────────────────────

def _score_valuation(data: dict) -> float:
    """Score 0-100 — higher = more attractive valuation relative to growth."""
    score = 50.0

    # PEG ratio is the single best growth-adjusted value metric
    peg = data.get("peg_ratio")
    if peg is not None and peg > 0:
        if peg < 0.8:
            score += 20  # Significantly undervalued for growth
        elif peg < 1.2:
            score += 12  # Fair value
        elif peg < 2.0:
            score += 3
        elif peg < 3.0:
            score -= 5
        else:
            score -= 15  # Very expensive

    # P/S ratio (critical for pre-profit companies)
    ps = data.get("ps_ratio")
    rev_g = data.get("revenue_growth") or 0
    if ps is not None:
        if ps < 3 and rev_g > 0.20:
            score += 15  # Cheap for a fast grower
        elif ps < 5:
            score += 8
        elif ps < 10:
            score += 2
        elif ps < 20:
            score -= 5
        else:
            score -= 12  # Very expensive P/S

    # Analyst upside
    target = data.get("target_mean_price")
    price = data.get("price", 0)
    if target and price and price > 0:
        upside = (target - price) / price
        if upside > 0.40:
            score += 12
        elif upside > 0.20:
            score += 7
        elif upside > 0:
            score += 3
        elif upside < -0.10:
            score -= 8  # Analysts think it's overvalued

    return _clamp(score)


# ─────────────────────────────────────────────────────────
# Sub-Score 5: Institutional Signal (15%)
# ─────────────────────────────────────────────────────────

def _score_institutional(sym: str, data: dict) -> float:
    """Score 0-100 based on smart money, insider, and convergence signals."""
    score = 50.0

    # Check if this stock is in our existing DB (Russell 1000 overlap)
    try:
        # Smart money
        sm = query("""
            SELECT conviction_score FROM smart_money_scores
            WHERE symbol = ? ORDER BY date DESC LIMIT 1
        """, [sym])
        if sm and sm[0]["conviction_score"]:
            conv = sm[0]["conviction_score"]
            if conv > 70:
                score += 20
            elif conv > 50:
                score += 12
            elif conv > 30:
                score += 5

        # Insider signals
        ins = query("""
            SELECT insider_score, cluster_buy FROM insider_signals
            WHERE symbol = ? ORDER BY date DESC LIMIT 1
        """, [sym])
        if ins:
            iscore = ins[0]["insider_score"] or 0
            if ins[0].get("cluster_buy"):
                score += 15  # Cluster buys = very bullish
            elif iscore > 60:
                score += 10
            elif iscore > 40:
                score += 5

        # Convergence signal
        conv_sig = query("""
            SELECT convergence_score, conviction_level FROM convergence_signals
            WHERE symbol = ? ORDER BY date DESC LIMIT 1
        """, [sym])
        if conv_sig:
            cs = conv_sig[0]["convergence_score"] or 0
            if cs > 70:
                score += 10
            elif cs > 50:
                score += 5

    except Exception:
        pass  # DB not initialized or symbol not in universe

    # Analyst coverage (from yfinance)
    n_analysts = data.get("num_analysts", 0)
    rec = data.get("recommendation", "")
    if rec in ("strongBuy", "buy"):
        score += 5
    elif rec in ("sell", "strongSell"):
        score -= 10

    # Short interest — high short + our signal = squeeze potential
    short_pct = data.get("short_pct")
    if short_pct is not None:
        if short_pct > 0.15:
            score += 8  # High short interest = squeeze candidate
        elif short_pct > 0.08:
            score += 3

    return _clamp(score)


# ─────────────────────────────────────────────────────────
# Composite Scoring
# ─────────────────────────────────────────────────────────

def score_stock(sym: str, theme_entry: dict, data: dict) -> dict:
    """Compute composite thematic score for a single stock.

    Returns dict with all sub-scores and composite.
    """
    policy = _score_policy_exposure(sym, theme_entry)
    growth = _score_growth(data)
    technical = _score_technical(data)
    valuation = _score_valuation(data)
    institutional = _score_institutional(sym, data)

    composite = (
        policy * TS_SCORE_WEIGHTS["policy"]
        + growth * TS_SCORE_WEIGHTS["growth"]
        + technical * TS_SCORE_WEIGHTS["technical"]
        + valuation * TS_SCORE_WEIGHTS["valuation"]
        + institutional * TS_SCORE_WEIGHTS["institutional"]
    )

    # Build narrative
    strengths = []
    if policy >= 75:
        strengths.append("direct policy beneficiary")
    if growth >= 70:
        strengths.append("strong growth")
    if technical >= 70:
        strengths.append("bullish technicals")
    if valuation >= 65:
        strengths.append("attractive valuation")
    if institutional >= 70:
        strengths.append("institutional backing")

    risks = []
    mcap = data.get("market_cap", 0)
    if mcap and mcap < 500_000_000:
        risks.append("micro-cap liquidity risk")
    if data.get("profit_margin") is not None and data["profit_margin"] < 0:
        risks.append("unprofitable")
    if data.get("rsi_14", 50) > 75:
        risks.append("overbought")
    if data.get("price_vs_52w_high", 1) < 0.60:
        risks.append("broken chart")

    narrative = ""
    if strengths:
        narrative += "Strengths: " + ", ".join(strengths) + ". "
    if risks:
        narrative += "Risks: " + ", ".join(risks) + "."

    return {
        "symbol": sym,
        "name": theme_entry.get("name", sym),
        "theme": theme_entry.get("theme", ""),
        "sub_theme": theme_entry.get("sub_theme", ""),
        "policy_score": round(policy, 1),
        "growth_score": round(growth, 1),
        "technical_score": round(technical, 1),
        "valuation_score": round(valuation, 1),
        "institutional_score": round(institutional, 1),
        "composite_score": round(composite, 1),
        "market_cap": data.get("market_cap", 0),
        "price": data.get("price", 0),
        "revenue_growth": data.get("revenue_growth"),
        "earnings_growth": data.get("earnings_growth"),
        "pe_ratio": data.get("pe_ratio"),
        "ps_ratio": data.get("ps_ratio"),
        "rsi_14": data.get("rsi_14"),
        "momentum_3m": data.get("momentum_3m"),
        "short_pct": data.get("short_pct"),
        "catalysts": json.dumps(theme_entry.get("catalysts", [])),
        "narrative": narrative,
    }


# ─────────────────────────────────────────────────────────
# Main Scanner
# ─────────────────────────────────────────────────────────

def scan_theme(theme_name: str) -> list[dict]:
    """Scan all stocks in a single theme and return scored results."""
    themes = get_theme_universe()
    if theme_name not in themes:
        logger.error(f"Unknown theme: {theme_name}")
        return []

    entries = themes[theme_name]
    symbols = [e["symbol"] for e in entries]
    logger.info(f"[{theme_name}] Scanning {len(symbols)} stocks...")

    # Fetch data
    data = _fetch_yfinance_data(symbols)
    logger.info(f"[{theme_name}] Got data for {len(data)}/{len(symbols)} stocks")

    # Score each
    results = []
    for entry in entries:
        sym = entry["symbol"]
        if sym not in data:
            continue
        scored = score_stock(sym, entry, data[sym])
        results.append(scored)

    # Sort by composite score
    results.sort(key=lambda x: x["composite_score"], reverse=True)
    return results


def scan_all_themes() -> dict[str, list[dict]]:
    """Scan all themes and return results organized by theme."""
    themes = get_theme_universe()
    all_results = {}

    for theme_name in themes:
        results = scan_theme(theme_name)
        all_results[theme_name] = results
        logger.info(
            f"[{theme_name}] Top 3: "
            + ", ".join(f"{r['symbol']}={r['composite_score']}" for r in results[:3])
        )

    return all_results


def run_scanner(persist: bool = True) -> dict[str, list[dict]]:
    """Run the full thematic scanner and optionally persist to DB.

    Returns dict of theme -> sorted results.
    """
    init_db()
    today = date.today().isoformat()

    logger.info("=" * 60)
    logger.info("THEMATIC ALPHA SCANNER — Starting scan")
    logger.info("=" * 60)

    all_results = scan_all_themes()

    if persist:
        _persist_results(all_results, today)

    # Summary
    total = sum(len(v) for v in all_results.values())
    top_ideas = []
    for theme, results in all_results.items():
        for r in results[:TS_TOP_N_PER_THEME]:
            top_ideas.append(r)
    top_ideas.sort(key=lambda x: x["composite_score"], reverse=True)

    logger.info("=" * 60)
    logger.info(f"SCAN COMPLETE — {total} stocks scored across {len(all_results)} themes")
    logger.info(f"Top 10 ideas:")
    for i, idea in enumerate(top_ideas[:10], 1):
        mcap_str = f"${idea['market_cap']/1e9:.1f}B" if idea['market_cap'] else "N/A"
        logger.info(
            f"  {i}. {idea['symbol']} ({idea['theme']}/{idea['sub_theme']}) "
            f"score={idea['composite_score']} mcap={mcap_str}"
        )
    logger.info("=" * 60)

    return all_results


def _persist_results(all_results: dict[str, list[dict]], scan_date: str):
    """Save scan results to DB."""
    rows = []
    for theme, results in all_results.items():
        for r in results:
            rows.append((
                r["symbol"], scan_date, r["theme"], r["sub_theme"], r["name"],
                r["policy_score"], r["growth_score"], r["technical_score"],
                r["valuation_score"], r["institutional_score"], r["composite_score"],
                r["market_cap"], r["price"],
                r.get("revenue_growth"), r.get("earnings_growth"),
                r.get("pe_ratio"), r.get("ps_ratio"),
                r.get("rsi_14"), r.get("momentum_3m"), r.get("short_pct"),
                r["catalysts"], r["narrative"],
            ))

    cols = [
        "symbol", "date", "theme", "sub_theme", "name",
        "policy_score", "growth_score", "technical_score",
        "valuation_score", "institutional_score", "composite_score",
        "market_cap", "price",
        "revenue_growth", "earnings_growth",
        "pe_ratio", "ps_ratio",
        "rsi_14", "momentum_3m", "short_pct",
        "catalysts", "narrative",
    ]
    upsert_many("thematic_ideas", cols, rows)
    logger.info(f"Persisted {len(rows)} thematic ideas to DB")



# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    import argparse
    parser = argparse.ArgumentParser(description="Thematic Alpha Scanner")
    parser.add_argument("--theme", type=str, help="Scan single theme")
    parser.add_argument("--no-persist", action="store_true", help="Don't save to DB")
    args = parser.parse_args()

    if args.theme:
        results = scan_theme(args.theme)
        print(f"\n{'='*70}")
        print(f"  THEMATIC ALPHA SCANNER — {args.theme.upper()}")
        print(f"{'='*70}")
        for i, r in enumerate(results[:15], 1):
            mcap = f"${r['market_cap']/1e9:.1f}B" if r['market_cap'] else "N/A"
            print(
                f"  {i:2d}. {r['symbol']:8s} {r['name']:30s} "
                f"Score={r['composite_score']:5.1f}  MCap={mcap:>8s}  "
                f"P={r['policy_score']:4.0f} G={r['growth_score']:4.0f} "
                f"T={r['technical_score']:4.0f} V={r['valuation_score']:4.0f} "
                f"I={r['institutional_score']:4.0f}"
            )
        print(f"{'='*70}\n")
    else:
        results = run_scanner(persist=not args.no_persist)
