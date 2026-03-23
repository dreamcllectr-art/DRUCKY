"""Fundamental scoring engine (0-100) for stocks — powered by FMP + Finnhub data.

5 sub-scores, each 0-20:
- Valuation: P/E, P/B, EV/EBITDA, FCF yield, DCF discount vs market
- Growth: Revenue, earnings growth, earnings beat rate, earnings surprises
- Profitability: ROE, ROIC, gross/operating/net margins
- Financial Health: Debt/equity, interest coverage, current ratio
- Quality/Smart Money: Insider buying, institutional flows, analyst consensus

Crypto and commodities default to 50 (neutral).
"""

import pandas as pd
import numpy as np
from datetime import datetime
from tools.db import init_db, upsert_many, query_df, query


def _get(fund_df, symbol, metric):
    row = fund_df[(fund_df["symbol"] == symbol) & (fund_df["metric"] == metric)]
    return float(row.iloc[0]["value"]) if not row.empty else None


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _pct_score(value, series, higher_is_better=True, scale=20):
    """Score value by percentile rank within sector peers."""
    if value is None or series.empty:
        return scale / 2
    clean = series.dropna()
    if len(clean) < 3:
        return scale / 2
    pctile = (clean < value).mean()
    if not higher_is_better:
        pctile = 1 - pctile
    return round(pctile * scale, 1)


def score_valuation(fund_df, symbol, sector_syms):
    """Valuation score (0-20): P/E, P/B, EV/EBITDA, FCF yield, DCF upside."""
    scores = []

    # P/E ratio (lower = better)
    pe = _get(fund_df, symbol, "pe_ratio")
    if pe and 0 < pe < 200:
        sector_pe = fund_df[(fund_df["symbol"].isin(sector_syms)) & (fund_df["metric"] == "pe_ratio")
                            & (fund_df["value"].between(0, 200))]["value"]
        scores.append(_pct_score(pe, sector_pe, higher_is_better=False, scale=7))

    # P/B ratio (lower = better)
    pb = _get(fund_df, symbol, "pb_ratio")
    if pb and 0 < pb < 50:
        sector_pb = fund_df[(fund_df["symbol"].isin(sector_syms)) & (fund_df["metric"] == "pb_ratio")
                            & (fund_df["value"].between(0, 50))]["value"]
        scores.append(_pct_score(pb, sector_pb, higher_is_better=False, scale=5))

    # FCF yield (higher = better)
    fcf_yield = _get(fund_df, symbol, "fcf_yield")
    if fcf_yield and fcf_yield > 0:
        if fcf_yield > 0.08:   scores.append(5)
        elif fcf_yield > 0.05: scores.append(4)
        elif fcf_yield > 0.02: scores.append(2)
        else:                  scores.append(1)

    # DCF discount (positive = undervalued vs intrinsic value)
    dcf_discount = _get(fund_df, symbol, "dcf_discount")
    if dcf_discount is not None:
        # Beta regime adjustment: FMP uses market beta in WACC, which inflates the
        # discount rate for high-beta momentum stocks (e.g. NVDA beta=2.3 → WACC=16.7%
        # vs normalized beta=1.4 → WACC=11.5%). Each 1.0 beta above 1.5 suppresses
        # fair value by ~15%, so we add 15pp per excess beta unit before scoring.
        beta = _get(fund_df, symbol, "beta")
        if beta is not None and beta > 2.0:
            dcf_discount += (beta - 1.5) * 15
        if dcf_discount > 30:   scores.append(3)
        elif dcf_discount > 10: scores.append(2)
        elif dcf_discount > 0:  scores.append(1)
        else:                   scores.append(-1)

    if not scores:
        return 10
    return _clamp(sum(scores), 0, 20)


def score_growth(fund_df, symbol):
    """Growth score (0-20): Revenue/earnings growth, beat rate, surprises."""
    score = 0

    rev_g = _get(fund_df, symbol, "revenue_growth")
    if rev_g is not None:
        if rev_g > 0.25:    score += 5
        elif rev_g > 0.15:  score += 4
        elif rev_g > 0.05:  score += 3
        elif rev_g > 0:     score += 1

    eps_g = _get(fund_df, symbol, "earnings_growth")
    if eps_g is not None:
        if eps_g > 0.25:    score += 5
        elif eps_g > 0.15:  score += 4
        elif eps_g > 0.05:  score += 3
        elif eps_g > 0:     score += 1

    # Earnings beat rate: consistently beating estimates = quality
    beat_rate = _get(fund_df, symbol, "earnings_beat_rate")
    if beat_rate is not None:
        if beat_rate >= 75:   score += 5
        elif beat_rate >= 50: score += 3
        elif beat_rate < 25:  score -= 2

    # Avg earnings surprise magnitude
    surprise = _get(fund_df, symbol, "earnings_surprise_avg")
    if surprise is not None:
        if surprise > 10:   score += 5
        elif surprise > 5:  score += 3
        elif surprise > 0:  score += 1
        elif surprise < -5: score -= 2

    return _clamp(score, 0, 20)


def score_profitability(fund_df, symbol):
    """Profitability score (0-20): ROE, ROIC, gross/operating margins."""
    scores = []

    roe = _get(fund_df, symbol, "roe")
    if roe is not None:
        if roe > 0.25:    scores.append(6)
        elif roe > 0.15:  scores.append(5)
        elif roe > 0.10:  scores.append(3)
        elif roe > 0:     scores.append(1)

    roic = _get(fund_df, symbol, "roic")
    if roic is not None:
        if roic > 0.20:   scores.append(5)
        elif roic > 0.12: scores.append(4)
        elif roic > 0.08: scores.append(2)
        elif roic > 0:    scores.append(1)

    gm = _get(fund_df, symbol, "gross_margin")
    if gm is not None:
        if gm > 0.60:    scores.append(5)
        elif gm > 0.40:  scores.append(4)
        elif gm > 0.20:  scores.append(2)
        else:            scores.append(1)

    om = _get(fund_df, symbol, "operating_margin")
    if om is not None:
        if om > 0.25:    scores.append(4)
        elif om > 0.15:  scores.append(3)
        elif om > 0.05:  scores.append(2)

    if not scores:
        return 10
    max_possible = sum([6, 5, 5, 4][:len(scores)])
    raw = sum(scores)
    return _clamp(round(raw / max_possible * 20, 1), 0, 20)


def score_health(fund_df, symbol):
    """Financial health score (0-20): D/E, interest coverage, liquidity."""
    score = 10  # neutral start

    de = _get(fund_df, symbol, "debt_equity")
    if de is not None:
        if de < 0.3:    score += 5
        elif de < 0.75: score += 3
        elif de < 1.5:  score += 1
        elif de > 3.0:  score -= 5
        elif de > 2.0:  score -= 3

    coverage = _get(fund_df, symbol, "interest_coverage")
    if coverage is not None:
        if coverage > 10:  score += 4
        elif coverage > 5: score += 2
        elif coverage < 2: score -= 4
        elif coverage < 1: score -= 6

    current = _get(fund_df, symbol, "current_ratio")
    if current is not None:
        if current > 2.5:   score += 1
        elif current > 1.5: score += 1
        elif current < 1.0: score -= 4

    return _clamp(round(score, 1), 0, 20)


def score_quality_smart_money(fund_df, symbol):
    """Quality/Smart Money score (0-20).

    Druckenmiller's key qualitative signals:
    - Insiders BUYING = management conviction in own stock (major bullish signal)
    - Institutions ACCUMULATING = smart money inflow
    - Analyst UPGRADES = improving narrative
    - Consistent EARNINGS BEATS = management under-promises and over-delivers
    """
    score = 10  # neutral start

    # NET INSIDER BUYING (90 days) — Druckenmiller watches this closely
    insider_val = _get(fund_df, symbol, "insider_net_value_90d")
    if insider_val is not None:
        if insider_val > 5_000_000:    score += 5   # >$5M net buying: strong signal
        elif insider_val > 1_000_000:  score += 4
        elif insider_val > 250_000:    score += 2
        elif insider_val < -5_000_000: score -= 5
        elif insider_val < -1_000_000: score -= 3

    # INSTITUTIONAL NET CHANGE (smart money flows)
    inst_change_pct = _get(fund_df, symbol, "inst_change_pct")
    if inst_change_pct is not None:
        if inst_change_pct > 5:    score += 3
        elif inst_change_pct > 1:  score += 1
        elif inst_change_pct < -5: score -= 3
        elif inst_change_pct < -1: score -= 1

    # ANALYST CONSENSUS (FMP grades — last 90 days)
    buy_pct = _get(fund_df, symbol, "analyst_buy_pct")
    sell_pct = _get(fund_df, symbol, "analyst_sell_pct")
    if buy_pct is not None and sell_pct is not None:
        if buy_pct > 70 and sell_pct < 10:    score += 2
        elif buy_pct > 50:                    score += 1
        elif sell_pct > 50:                   score -= 2

    # FINNHUB ANALYST RECOMMENDATIONS
    fh_bullish = _get(fund_df, symbol, "finnhub_analyst_bullish_pct")
    if fh_bullish is not None:
        if fh_bullish > 75:   score += 1
        elif fh_bullish < 25: score -= 1

    # FORENSIC ACCOUNTING PENALTIES (from accounting_forensics.py)
    forensic_score = _get(fund_df, symbol, "forensic_score")
    if forensic_score is not None:
        if forensic_score < 30:
            score -= 3   # Red alert: accounting red flags
        elif forensic_score >= 80:
            score += 2   # Pristine books bonus

    forensic_mscore = _get(fund_df, symbol, "forensic_mscore")
    if forensic_mscore is not None and forensic_mscore > -1.78:
        score -= 5   # Beneish M-Score suggests likely manipulation

    # FOUNDER LETTER QUALITY (from founder_letter_analyzer.py)
    letter_tier = _get(fund_df, symbol, "letter_tier")
    if letter_tier is not None:
        if letter_tier >= 5:    score += 3   # Bezos-tier CEO
        elif letter_tier >= 4:  score += 2   # Buffett-tier CEO
        elif letter_tier == 0:  score -= 3   # Red flags in letter
        elif letter_tier == 1:  score -= 1   # Bureaucratic

    letter_traj = _get(fund_df, symbol, "letter_yoy_trajectory")
    if letter_traj is not None:
        if letter_traj >= 1:     score += 2   # Improving letters
        elif letter_traj <= -2:  score -= 3   # Concerning shift

    return _clamp(round(score, 1), 0, 20)


def run():
    """Compute fundamental scores for all stocks."""
    init_db()
    print("Computing fundamental scores (FMP + Finnhub enhanced)...")

    fund_df = query_df("SELECT * FROM fundamentals")
    if fund_df.empty:
        print("  No fundamental data. Run fetch_fmp_fundamentals.py first.")
        return

    symbols = fund_df["symbol"].unique().tolist()

    # Group by sector via sector_name hash
    sector_map = {}
    for sym in symbols:
        sec = _get(fund_df, sym, "sector_name")
        sector_key = int(sec) if sec is not None else 0
        sector_map.setdefault(sector_key, []).append(sym)

    today = datetime.now().strftime("%Y-%m-%d")
    results = []

    for symbol in symbols:
        sec = _get(fund_df, symbol, "sector_name")
        sector_key = int(sec) if sec is not None else 0
        sector_syms = sector_map.get(sector_key, [])

        v = score_valuation(fund_df, symbol, sector_syms)
        g = score_growth(fund_df, symbol)
        p = score_profitability(fund_df, symbol)
        h = score_health(fund_df, symbol)
        q = score_quality_smart_money(fund_df, symbol)
        total = v + g + p + h + q

        results.append((symbol, today, v, g, p, h, q, round(total, 1)))

    upsert_many(
        "fundamental_scores",
        ["symbol", "date", "valuation_score", "growth_score", "profitability_score",
         "health_score", "quality_score", "total_score"],
        results
    )
    print(f"  Computed enhanced fundamental scores for {len(results)} stocks")

    if results:
        sorted_results = sorted(results, key=lambda x: x[-1], reverse=True)
        print("\n  Top 15 Fundamental Scores (FMP Enhanced):")
        for r in sorted_results[:15]:
            print(f"    {r[0]:12s} | {r[-1]:5.1f} | "
                  f"V:{r[2]:4.0f} G:{r[3]:4.0f} P:{r[4]:4.0f} H:{r[5]:4.0f} Q:{r[6]:4.0f}")


if __name__ == "__main__":
    run()
