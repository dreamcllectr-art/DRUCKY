"""Variant Perception Engine — find the fattest mispricings in the market.

For each stock, this tool:
1. Reverse-engineers what growth rate the market is currently pricing
2. Compares implied growth to historical base rates (5yr/10yr CAGRs)
3. Detects systematic analyst estimate bias (do they chronically under/over-estimate?)
4. Tracks estimate revision momentum (are consensus numbers moving up or down?)
5. Builds 3-scenario probabilistic fair value (bull/base/bear)
6. Computes a variant score (0-100) ranking the biggest mispricings

Druckenmiller principle: "I'm looking for the fat pitch where I see it differently
than the consensus."
"""

import sys
import time
import argparse
import numpy as np
from datetime import datetime

_project_root = str(__import__("pathlib").Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import (
    FMP_API_KEY, DISCOUNT_RATE_BULL, DISCOUNT_RATE_BASE, DISCOUNT_RATE_BEAR,
    SCENARIO_WEIGHTS, TERMINAL_GROWTH_CAP,
    CONSENSUS_CROWDING_NARROW_PCT, CONSENSUS_CROWDING_WIDE_PCT,
    CONSENSUS_HERDING_BUY_THRESH, CONSENSUS_HERDING_SELL_THRESH,
    CONSENSUS_SURPRISE_PERSIST_MIN, CONSENSUS_SURPRISE_PERSIST_BIAS,
    CONSENSUS_TARGET_UPSIDE_CROWDED, CONSENSUS_TARGET_UPSIDE_DEEP,
)
from tools.db import init_db, upsert_many, query, query_df
from tools.fetch_fmp_fundamentals import fmp_get


def _safe(val, default=None):
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _cagr(start, end, years):
    """Compound annual growth rate."""
    if start is None or end is None or start <= 0 or years <= 0:
        return None
    if end <= 0:
        return None
    return (end / start) ** (1 / years) - 1


def get_current_regime():
    """Get current macro regime for scenario weight adjustment."""
    df = query_df("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    if df.empty:
        return "neutral"
    return df.iloc[0]["regime"]


def fetch_historical_financials(symbol):
    """Fetch 10 years of income statements and key metrics."""
    income = fmp_get(f"/income-statement/{symbol}", {"period": "annual", "limit": 10})
    metrics = fmp_get(f"/key-metrics/{symbol}", {"period": "annual", "limit": 10})
    ev = fmp_get(f"/enterprise-values/{symbol}", {"period": "annual", "limit": 1})
    return income, metrics, ev


def fetch_analyst_estimates(symbol):
    """Fetch forward consensus estimates."""
    return fmp_get(f"/analyst-estimates/{symbol}", {"period": "annual", "limit": 3})


def fetch_earnings_surprises(symbol):
    """Fetch historical earnings surprises for bias detection."""
    return fmp_get(f"/earnings-surprises/{symbol}")


def compute_growth_metrics(income):
    """Compute historical growth rates and volatility."""
    if not income or not isinstance(income, list) or len(income) < 3:
        return {}

    # Revenue CAGRs (income is newest-first)
    revenues = [_safe(y.get("revenue")) for y in income]
    earnings = [_safe(y.get("netIncome")) for y in income]
    fcfs = [_safe(y.get("operatingIncome")) for y in income]  # Proxy

    metrics = {}
    n = len(revenues)

    # 5-year CAGR
    if n >= 5 and revenues[-5] and revenues[0]:
        cagr_5 = _cagr(revenues[-1], revenues[0], min(n - 1, 5))
        if cagr_5 is not None:
            metrics["variant_revenue_cagr_5y"] = round(cagr_5, 4)

    # 10-year CAGR (or max available)
    if n >= 3 and revenues[-1] and revenues[0]:
        cagr_full = _cagr(revenues[-1], revenues[0], n - 1)
        if cagr_full is not None:
            metrics["variant_revenue_cagr_10y"] = round(cagr_full, 4)

    # Growth volatility (std of YoY growth rates)
    yoy_growth = []
    for i in range(len(revenues) - 1):
        curr, prev = revenues[i], revenues[i + 1]
        if curr and prev and prev > 0:
            yoy_growth.append((curr - prev) / prev)
    if len(yoy_growth) >= 3:
        metrics["variant_growth_volatility"] = round(float(np.std(yoy_growth)), 4)

    # Growth percentiles for scenario modeling
    if len(yoy_growth) >= 4:
        metrics["_growth_p75"] = float(np.percentile(yoy_growth, 75))
        metrics["_growth_p50"] = float(np.percentile(yoy_growth, 50))
        metrics["_growth_p25"] = float(np.percentile(yoy_growth, 25))

    # Latest FCF and revenue for modeling
    if revenues[0]:
        metrics["_latest_revenue"] = revenues[0]
    if earnings[0]:
        metrics["_latest_earnings"] = earnings[0]

    return metrics


def compute_implied_growth(income, key_metrics, ev_data):
    """Reverse-engineer implied growth from current EV/FCF."""
    if not ev_data or not isinstance(ev_data, list) or not ev_data:
        return {}
    if not key_metrics or not isinstance(key_metrics, list) or not key_metrics:
        return {}

    # Current enterprise value
    current_ev = _safe(ev_data[0].get("enterpriseValue"))
    if not current_ev or current_ev <= 0:
        return {}

    # Current FCF
    fcf = _safe(key_metrics[0].get("freeCashFlowPerShare"))
    shares = _safe(key_metrics[0].get("marketCap"))
    price = _safe(key_metrics[0].get("peRatio"))  # Just checking if data exists

    # Try to get FCF from key metrics
    fcf_yield = _safe(key_metrics[0].get("freeCashFlowYield"))
    market_cap = _safe(key_metrics[0].get("marketCap"))

    if fcf_yield and market_cap and market_cap > 0:
        total_fcf = fcf_yield * market_cap
    elif income and income[0]:
        # Fallback: use operating income as proxy
        total_fcf = _safe(income[0].get("operatingIncome"))
    else:
        return {}

    if not total_fcf or total_fcf <= 0:
        return {}

    ev_fcf = current_ev / total_fcf
    if ev_fcf <= 0:
        return {}

    # Implied growth from simplified perpetuity: EV = FCF / (r - g)
    # => g = r - FCF/EV
    # Using base discount rate
    implied_growth = DISCOUNT_RATE_BASE - (total_fcf / current_ev)
    implied_growth = min(implied_growth, TERMINAL_GROWTH_CAP * 3)  # Cap at 12%
    implied_growth = max(implied_growth, -0.10)  # Floor at -10%

    return {
        "variant_implied_growth": round(implied_growth, 4),
        "_current_ev": current_ev,
        "_current_fcf": total_fcf,
    }


def compute_estimate_bias(symbol):
    """Detect systematic analyst estimate bias from historical surprises."""
    data = fetch_earnings_surprises(symbol)
    if not data or not isinstance(data, list):
        return {}

    recent = data[:8]  # Last 8 quarters
    biases = []
    for q in recent:
        actual = _safe(q.get("actualEarningResult"))
        estimated = _safe(q.get("estimatedEarning"))
        if actual is not None and estimated is not None and abs(estimated) > 0.01:
            bias = (actual - estimated) / abs(estimated)
            biases.append(bias)

    if len(biases) < 4:
        return {}

    avg_bias = float(np.mean(biases))
    return {"variant_estimate_bias": round(avg_bias, 4)}


def compute_revision_momentum(symbol):
    """Check if analyst estimates are being revised up or down."""
    estimates = fetch_analyst_estimates(symbol)
    if not estimates or not isinstance(estimates, list) or len(estimates) < 2:
        return {}

    # Compare current year estimate to what it was (we only have latest snapshot)
    # Use the difference between next year and this year growth expectations
    est_curr = estimates[0] if estimates else None
    est_next = estimates[1] if len(estimates) > 1 else None

    if not est_curr or not est_next:
        return {}

    rev_est_curr = _safe(est_curr.get("estimatedRevenueAvg"))
    rev_est_next = _safe(est_next.get("estimatedRevenueAvg"))
    eps_est_curr = _safe(est_curr.get("estimatedEpsAvg"))
    eps_est_next = _safe(est_next.get("estimatedEpsAvg"))

    # Revision momentum: positive if next year expectations are growing
    momentum = 0
    if rev_est_curr and rev_est_next and rev_est_curr > 0:
        rev_growth = (rev_est_next - rev_est_curr) / rev_est_curr
        if rev_growth > 0.10:
            momentum += 30
        elif rev_growth > 0.05:
            momentum += 15
        elif rev_growth < -0.05:
            momentum -= 20

    if eps_est_curr and eps_est_next and abs(eps_est_curr) > 0.01:
        eps_growth = (eps_est_next - eps_est_curr) / abs(eps_est_curr)
        if eps_growth > 0.15:
            momentum += 30
        elif eps_growth > 0.05:
            momentum += 15
        elif eps_growth < -0.10:
            momentum -= 20

    return {
        "variant_revision_momentum": max(-100, min(100, momentum)),
        "_fwd_revenue": rev_est_curr,
        "_fwd_eps": eps_est_curr,
    }


# =========================================================================
# CONTRARIAN CONSENSUS SIGNALS
# Analysts are often wrong AND priced in. The edge is in detecting:
# 1. When they all agree (crowding) — fragile, likely wrong
# 2. When they all say "Buy" (herding) — contrarian red flag
# 3. When the company keeps beating them (persistence) — they never learn
# 4. When the price already matches their target (priced in) — no upside left
# =========================================================================


def compute_estimate_crowding(symbol):
    """Detect narrow estimate spreads — when everyone agrees, they're wrong.

    Narrow spread = low dispersion = analysts copying each other.
    Wide spread = high uncertainty = market hasn't figured it out (opportunity).
    """
    estimates = fetch_analyst_estimates(symbol)
    if not estimates or not isinstance(estimates, list) or not estimates[0]:
        return {}

    est = estimates[0]
    eps_high = _safe(est.get("estimatedEpsHigh"))
    eps_low = _safe(est.get("estimatedEpsLow"))
    eps_avg = _safe(est.get("estimatedEpsAvg"))
    rev_high = _safe(est.get("estimatedRevenueHigh"))
    rev_low = _safe(est.get("estimatedRevenueLow"))
    rev_avg = _safe(est.get("estimatedRevenueAvg"))

    metrics = {}

    # EPS estimate spread
    if eps_high is not None and eps_low is not None and eps_avg and abs(eps_avg) > 0.01:
        eps_spread = (eps_high - eps_low) / abs(eps_avg)
        metrics["variant_eps_spread"] = round(eps_spread, 4)

    # Revenue estimate spread
    if rev_high is not None and rev_low is not None and rev_avg and rev_avg > 0:
        rev_spread = (rev_high - rev_low) / rev_avg
        metrics["variant_rev_spread"] = round(rev_spread, 4)

    # Crowding score: negative = crowded (bad), positive = dispersed (good)
    spreads = [v for k, v in metrics.items() if "spread" in k]
    if spreads:
        avg_spread = float(np.mean(spreads))
        if avg_spread < CONSENSUS_CROWDING_NARROW_PCT:
            # Everyone agrees — contrarian penalty
            metrics["variant_crowding_score"] = -30
        elif avg_spread < 0.15:
            metrics["variant_crowding_score"] = -10
        elif avg_spread > CONSENSUS_CROWDING_WIDE_PCT:
            # High dispersion — market hasn't figured it out, potential alpha
            metrics["variant_crowding_score"] = 15
        else:
            metrics["variant_crowding_score"] = 0

    return metrics


def compute_herding_score(symbol):
    """Detect analyst rating herds — when 80%+ say Buy, run the other way.

    Academic research: stocks with >80% buy ratings underperform over 12 months.
    Stocks with >80% sell ratings outperform — Wall Street overshoots in both directions.
    We pull from fundamentals table (populated by fetch_fmp_fundamentals via yfinance).
    """
    rows = query(
        "SELECT metric, value FROM fundamentals "
        "WHERE symbol = ? AND metric IN ('analyst_buy_pct', 'analyst_sell_pct', 'analyst_rating_count')",
        [symbol]
    )
    if not rows:
        return {}

    data = {r["metric"]: r["value"] for r in rows}
    buy_pct = data.get("analyst_buy_pct")
    sell_pct = data.get("analyst_sell_pct")
    count = data.get("analyst_rating_count")

    # Need at least 5 analysts for herding to be meaningful
    if count is not None and count < 5:
        return {}

    metrics = {}
    herding = 0

    if buy_pct is not None:
        metrics["variant_buy_pct"] = buy_pct
        if buy_pct >= CONSENSUS_HERDING_BUY_THRESH:
            herding = -25  # Contrarian penalty — too much love
        elif buy_pct >= 70:
            herding = -10

    if sell_pct is not None:
        metrics["variant_sell_pct"] = sell_pct
        if sell_pct >= CONSENSUS_HERDING_SELL_THRESH:
            herding = 25  # Contrarian bonus — hated stocks rebound
        elif sell_pct >= 50:
            herding = 10

    if herding != 0:
        metrics["variant_herding_score"] = herding

    return metrics


def compute_surprise_persistence(symbol):
    """Detect companies that consistently beat estimates — analysts never learn.

    If a company beats 5+ of 8 quarters with avg surprise > 5%, the sell side
    is systematically wrong. That's not luck — it's a modeling failure we can exploit.
    This is stronger than the basic estimate_bias metric which just averages.
    """
    data = fetch_earnings_surprises(symbol)
    if not data or not isinstance(data, list):
        return {}

    recent = data[:8]  # Last 8 quarters
    beats = 0
    misses = 0
    surprises = []

    for q in recent:
        actual = _safe(q.get("actualEarningResult"))
        estimated = _safe(q.get("estimatedEarning"))
        if actual is not None and estimated is not None and abs(estimated) > 0.01:
            surprise_pct = (actual - estimated) / abs(estimated)
            surprises.append(surprise_pct)
            if surprise_pct > 0:
                beats += 1
            elif surprise_pct < 0:
                misses += 1

    if len(surprises) < 4:
        return {}

    metrics = {
        "variant_beat_rate": round(beats / len(surprises), 2),
        "variant_miss_rate": round(misses / len(surprises), 2),
    }

    avg_surprise = float(np.mean(surprises))

    # Persistent beater: analysts chronically underestimate
    if beats >= CONSENSUS_SURPRISE_PERSIST_MIN and avg_surprise > CONSENSUS_SURPRISE_PERSIST_BIAS:
        metrics["variant_surprise_persistence"] = 20  # Strong alpha signal
    elif beats >= 4 and avg_surprise > 0.03:
        metrics["variant_surprise_persistence"] = 10
    # Persistent misser: the market is in denial
    elif misses >= CONSENSUS_SURPRISE_PERSIST_MIN and avg_surprise < -CONSENSUS_SURPRISE_PERSIST_BIAS:
        metrics["variant_surprise_persistence"] = -20
    elif misses >= 4 and avg_surprise < -0.03:
        metrics["variant_surprise_persistence"] = -10
    else:
        metrics["variant_surprise_persistence"] = 0

    return metrics


def compute_target_exhaustion(symbol):
    """Detect when price has already reached analyst targets — upside is priced in.

    If the stock is within 5% of the consensus target, there's nothing left.
    Analysts will just ratchet the target up (lagging, not leading).
    If the stock is >30% below target, either it's broken or the analysts
    haven't downgraded yet — cross-check with other signals.
    """
    rows = query(
        "SELECT metric, value FROM fundamentals "
        "WHERE symbol = ? AND metric IN ('analyst_target_consensus', 'analyst_target_high', 'analyst_target_low')",
        [symbol]
    )
    if not rows:
        return {}

    data = {r["metric"]: r["value"] for r in rows}
    target = data.get("analyst_target_consensus")
    target_high = data.get("analyst_target_high")
    target_low = data.get("analyst_target_low")

    if not target or target <= 0:
        return {}

    # Get current price
    price_row = query(
        "SELECT close FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 1",
        [symbol]
    )
    if not price_row:
        return {}

    price = price_row[0]["close"]
    if not price or price <= 0:
        return {}

    upside_to_target = (target - price) / price
    metrics = {
        "variant_target_upside": round(upside_to_target, 4),
    }

    # Target spread (analyst disagreement on price target)
    if target_high and target_low and target > 0:
        target_spread = (target_high - target_low) / target
        metrics["variant_target_spread"] = round(target_spread, 4)

    # Exhaustion scoring
    if abs(upside_to_target) < CONSENSUS_TARGET_UPSIDE_CROWDED:
        # Price already at target — upside is priced in, analysts will just lag
        metrics["variant_target_exhaustion"] = -15
    elif upside_to_target < -0.15:
        # Price ABOVE target — analysts already behind, momentum may continue
        metrics["variant_target_exhaustion"] = -20
    elif upside_to_target > CONSENSUS_TARGET_UPSIDE_DEEP:
        # Deep below target — either broken or contrarian opportunity
        metrics["variant_target_exhaustion"] = 10
    else:
        metrics["variant_target_exhaustion"] = 0

    return metrics


def compute_scenario_fair_value(growth_metrics, implied_metrics, regime):
    """3-scenario probability-weighted fair value."""
    fcf = implied_metrics.get("_current_fcf")
    if not fcf or fcf <= 0:
        return {}

    growth_p75 = growth_metrics.get("_growth_p75")
    growth_p50 = growth_metrics.get("_growth_p50")
    growth_p25 = growth_metrics.get("_growth_p25")

    if growth_p50 is None:
        return {}

    # Default fallbacks
    if growth_p75 is None:
        growth_p75 = growth_p50 * 1.5
    if growth_p25 is None:
        growth_p25 = growth_p50 * 0.5

    # Cap terminal growth
    tg_bull = min(growth_p75 * 0.4, TERMINAL_GROWTH_CAP)
    tg_base = min(growth_p50 * 0.4, TERMINAL_GROWTH_CAP * 0.75)
    tg_bear = min(max(growth_p25 * 0.3, 0), TERMINAL_GROWTH_CAP * 0.5)

    # 5-year DCF + terminal value
    def scenario_fv(growth_rate, margin_adj, discount_rate, terminal_growth):
        """Simple 5-year DCF with terminal value."""
        fcf_proj = fcf
        pv_sum = 0
        for yr in range(1, 6):
            fcf_proj *= (1 + growth_rate) * margin_adj
            pv_sum += fcf_proj / (1 + discount_rate) ** yr

        # Terminal value (Gordon growth model)
        terminal = fcf_proj * (1 + terminal_growth) / (discount_rate - terminal_growth)
        if discount_rate <= terminal_growth:
            terminal = fcf_proj * 20  # Cap at 20x FCF if math breaks
        pv_terminal = terminal / (1 + discount_rate) ** 5

        return max(pv_sum + pv_terminal, 0)

    fv_bull = scenario_fv(growth_p75, 1.05, DISCOUNT_RATE_BULL, tg_bull)
    fv_base = scenario_fv(growth_p50, 1.00, DISCOUNT_RATE_BASE, tg_base)
    fv_bear = scenario_fv(growth_p25, 0.92, DISCOUNT_RATE_BEAR, tg_bear)

    # Probability-weighted
    weights = SCENARIO_WEIGHTS.get(regime, SCENARIO_WEIGHTS["neutral"])
    prob_fv = fv_bull * weights[0] + fv_base * weights[1] + fv_bear * weights[2]

    # Upside vs current EV
    current_ev = implied_metrics.get("_current_ev", 0)
    upside = ((prob_fv - current_ev) / current_ev * 100) if current_ev > 0 else 0

    return {
        "variant_fair_value_bull": round(fv_bull, 0),
        "variant_fair_value_base": round(fv_base, 0),
        "variant_fair_value_bear": round(fv_bear, 0),
        "variant_prob_weighted_fv": round(prob_fv, 0),
        "variant_upside_pct": round(upside, 2),
    }


def compute_variant_score(all_metrics):
    """Composite variant score (0-100). Higher = bigger mispricing opportunity.

    Scoring philosophy (Citadel/Jane Street mindset):
    - Scenario DCF upside is the base signal (25 pts max)
    - Growth gap vs base rate is structural edge (12 pts max)
    - Contrarian signals ADD to conviction when consensus is wrong (35 pts total):
      * Crowding penalty: narrow estimates = fragile consensus (-30 to +15)
      * Herding penalty: 80%+ buy ratings = contrarian flag (-25 to +25)
      * Surprise persistence: chronic beater = analysts never learn (+20 max)
      * Target exhaustion: price at target = upside priced in (-20 to +10)
    - Revision momentum is useful but ONLY when consensus isn't herding (8 pts max)
    """
    score = 50

    # --- SCENARIO MODEL (25 pts max) ---
    upside = all_metrics.get("variant_upside_pct")
    if upside is not None:
        if upside > 50:
            score += 25
        elif upside > 30:
            score += 18
        elif upside > 15:
            score += 10
        elif upside > 0:
            score += 3
        elif upside < -30:
            score -= 20
        elif upside < -15:
            score -= 10
        elif upside < 0:
            score -= 3

    # --- GROWTH GAP (12 pts max) ---
    growth_gap = all_metrics.get("variant_growth_gap")
    if growth_gap is not None:
        if growth_gap < -0.05:
            score += 12  # Market pricing deceleration vs history = opportunity
        elif growth_gap < -0.02:
            score += 6
        elif growth_gap > 0.10:
            score -= 10  # Market pricing acceleration = risky
        elif growth_gap > 0.05:
            score -= 5

    # --- CONTRARIAN: ESTIMATE CROWDING (±30 pts) ---
    crowding = all_metrics.get("variant_crowding_score")
    if crowding is not None:
        score += crowding  # Negative when narrow (bad), positive when dispersed

    # --- CONTRARIAN: ANALYST HERDING (±25 pts) ---
    herding = all_metrics.get("variant_herding_score")
    if herding is not None:
        score += herding  # Negative when everyone says Buy, positive when hated

    # --- CONTRARIAN: SURPRISE PERSISTENCE (±20 pts) ---
    persistence = all_metrics.get("variant_surprise_persistence")
    if persistence is not None:
        score += persistence  # Positive when company keeps beating

    # --- CONTRARIAN: TARGET EXHAUSTION (±20 pts) ---
    exhaustion = all_metrics.get("variant_target_exhaustion")
    if exhaustion is not None:
        score += exhaustion  # Negative when price already at target

    # --- ESTIMATE BIAS (basic, 8 pts — reduced weight, persistence is better) ---
    bias = all_metrics.get("variant_estimate_bias")
    if bias is not None:
        if bias > 0.10:
            score += 6
        elif bias > 0.05:
            score += 3
        elif bias < -0.10:
            score -= 6
        elif bias < -0.05:
            score -= 3

    # --- REVISION MOMENTUM (8 pts — but discounted if herding) ---
    rev_mom = all_metrics.get("variant_revision_momentum")
    if rev_mom is not None:
        # If analysts are already herding, revisions are just more of the same noise
        herding_discount = 0.5 if (herding is not None and abs(herding) >= 20) else 1.0
        rev_pts = 0
        if rev_mom > 30:
            rev_pts = 8
        elif rev_mom > 0:
            rev_pts = 3
        elif rev_mom < -30:
            rev_pts = -8
        elif rev_mom < 0:
            rev_pts = -3
        score += int(rev_pts * herding_discount)

    return max(0, min(100, score))


def run(symbols=None):
    """Run variant perception analysis."""
    init_db()

    if not FMP_API_KEY:
        print("  ERROR: FMP_API_KEY not set in .env")
        return

    # Default: analyze BUY/STRONG BUY signals, or full universe
    if symbols is None:
        buy_signals = query(
            "SELECT DISTINCT symbol FROM signals WHERE signal IN ('BUY', 'STRONG BUY') "
            "AND date = (SELECT MAX(date) FROM signals)"
        )
        if buy_signals:
            symbols = [r["symbol"] for r in buy_signals]
            print(f"Analyzing {len(symbols)} BUY/STRONG BUY signals for variant perception...")
        else:
            symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
            print(f"No active signals. Analyzing full universe ({len(symbols)} stocks)...")

    regime = get_current_regime()
    print(f"  Macro regime: {regime}")

    today = datetime.now().strftime("%Y-%m-%d")
    all_fund_rows = []
    variant_rows = []
    top_variants = []

    for i, symbol in enumerate(symbols):
        income, key_metrics, ev_data = fetch_historical_financials(symbol)
        if not income:
            continue

        # Compute all metrics
        growth_m = compute_growth_metrics(income)
        implied_m = compute_implied_growth(income, key_metrics, ev_data)
        bias_m = compute_estimate_bias(symbol)
        revision_m = compute_revision_momentum(symbol)

        # Contrarian consensus signals
        crowding_m = compute_estimate_crowding(symbol)
        herding_m = compute_herding_score(symbol)
        persistence_m = compute_surprise_persistence(symbol)
        exhaustion_m = compute_target_exhaustion(symbol)

        # Merge all metrics
        all_m = {}
        all_m.update(growth_m)
        all_m.update(implied_m)
        all_m.update(bias_m)
        all_m.update(revision_m)
        all_m.update(crowding_m)
        all_m.update(herding_m)
        all_m.update(persistence_m)
        all_m.update(exhaustion_m)

        # Growth gap
        implied_g = all_m.get("variant_implied_growth")
        base_g = all_m.get("variant_revenue_cagr_5y") or all_m.get("variant_revenue_cagr_10y")
        if implied_g is not None and base_g is not None:
            all_m["variant_growth_gap"] = round(implied_g - base_g, 4)

        # Scenario fair value
        scenario_m = compute_scenario_fair_value(growth_m, implied_m, regime)
        all_m.update(scenario_m)

        # Variant score (now includes contrarian signals)
        vscore = compute_variant_score(all_m)
        all_m["variant_score"] = vscore

        # Store public metrics in fundamentals table (skip internal _ prefixed)
        for metric_name, value in all_m.items():
            if not metric_name.startswith("_") and value is not None:
                all_fund_rows.append((symbol, metric_name, float(value)))

        # Store in variant_analysis table
        variant_rows.append((
            symbol, today,
            all_m.get("variant_implied_growth"),
            base_g,
            all_m.get("variant_growth_gap"),
            all_m.get("variant_estimate_bias"),
            all_m.get("variant_revision_momentum"),
            all_m.get("variant_fair_value_bull"),
            all_m.get("variant_fair_value_base"),
            all_m.get("variant_fair_value_bear"),
            all_m.get("variant_prob_weighted_fv"),
            all_m.get("variant_upside_pct"),
            vscore,
            all_m.get("variant_crowding_score"),
            all_m.get("variant_herding_score"),
            all_m.get("variant_surprise_persistence"),
            all_m.get("variant_target_exhaustion"),
            all_m.get("variant_beat_rate"),
            all_m.get("variant_target_upside"),
        ))

        if vscore >= 65:
            top_variants.append((symbol, vscore, all_m.get("variant_upside_pct", 0),
                                 all_m.get("variant_crowding_score"),
                                 all_m.get("variant_herding_score"),
                                 all_m.get("variant_surprise_persistence"),
                                 all_m.get("variant_target_exhaustion")))

        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(symbols)} stocks...")
            time.sleep(0.5)

    # Save
    upsert_many("fundamentals", ["symbol", "metric", "value"], all_fund_rows)
    upsert_many("variant_analysis",
                ["symbol", "date", "implied_growth", "base_rate_growth", "growth_gap",
                 "estimate_bias", "revision_momentum", "fair_value_bull", "fair_value_base",
                 "fair_value_bear", "prob_weighted_fv", "upside_pct", "variant_score",
                 "crowding_score", "herding_score", "surprise_persistence",
                 "target_exhaustion", "beat_rate", "target_upside"],
                variant_rows)

    # Summary
    print(f"\n  Variant perception complete: {len(variant_rows)} stocks analyzed")

    if top_variants:
        top_variants.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  TOP VARIANT OPPORTUNITIES (score >= 65):")
        print(f"    {'Symbol':10s} | {'VScore':>6s} | {'Upside%':>8s} | {'Crowd':>6s} | {'Herd':>5s} | {'Persist':>7s} | {'Target':>6s}")
        print(f"    {'-'*10}-+-{'-'*6}-+-{'-'*8}-+-{'-'*6}-+-{'-'*5}-+-{'-'*7}-+-{'-'*6}")
        for sym, vs, up, crowd, herd, persist, exhaust in top_variants[:25]:
            crowd_s = f"{crowd:+.0f}" if crowd is not None else "—"
            herd_s = f"{herd:+.0f}" if herd is not None else "—"
            pers_s = f"{persist:+.0f}" if persist is not None else "—"
            exh_s = f"{exhaust:+.0f}" if exhaust is not None else "—"
            print(f"    {sym:10s} | {vs:6.0f} | {up:+7.1f}% | {crowd_s:>6s} | {herd_s:>5s} | {pers_s:>7s} | {exh_s:>6s}")
    else:
        print("\n  No stocks scored >= 65 on variant perception.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Variant Perception Engine")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (default: BUY signals)")
    parser.add_argument("--all", action="store_true", help="Analyze full universe")
    args = parser.parse_args()

    if args.symbols:
        sym_list = args.symbols.split(",")
    elif args.all:
        sym_list = None  # Will query full universe
    else:
        sym_list = None  # Will default to BUY signals

    run(sym_list)
