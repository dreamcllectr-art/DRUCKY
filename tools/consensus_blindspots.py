"""Consensus Blindspots Module — Howard Marks' Second-Level Thinking, Quantified.

The 18th convergence module. Runs LAST (Phase 2.8) because it reads ALL other
module outputs and compares them against market consensus.

Core thesis (Howard Marks, The Most Important Thing):
  "Superior performance requires being RIGHT WHEN OTHERS ARE WRONG —
   not merely right. If your conclusion is the same as everyone else's,
   it is already priced in."

This module answers: WHERE does our system disagree with consensus,
and WHERE is consensus most likely to be wrong?

Five sub-signals weighted into a composite cbs_score (0-100):

  1. Sentiment Cycle Position (25%) — market-wide
     Where on Marks' greed/fear pendulum. AAII bull/bear ratio, VIX percentile,
     put/call ratio, margin debt growth, money market fund flows.
     Extreme fear = contrarian bullish. Extreme greed = contrarian bearish.

  2. Our-vs-Consensus Gap (30%) — per stock
     Compare our convergence score direction vs analyst consensus direction.
     When we're bullish but consensus is bearish = fat pitch.
     When we're bullish AND consensus is bullish = priced in (penalty).

  3. Positioning Extremes (20%) — per stock
     Short interest as % of float (squeeze vs crowded short).
     Institutional ownership extremes. Analyst rating distribution skew.
     Extreme one-sided positioning = fragile, mean-reverts.

  4. Signal Divergence (15%) — per stock
     When our own modules disagree with each other, that's information.
     Smart money vs technicals. Fundamentals vs price action.
     High divergence = either fat pitch or value trap — context resolves.

  5. Fat Pitch Detector (10%) — per stock
     Marks + Buffett: "Be fearful when others are greedy, greedy when others
     are fearful." Composite of: extreme fear (cycle) + deep undervaluation
     (variant) + smart money buying (13F) + insider buying.
     The "blood in the streets" signal.

Usage: python -m tools.consensus_blindspots
"""

import sys
import logging
import time
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import numpy as np

from tools.config import (
    FINNHUB_API_KEY, FRED_API_KEY,
    CBS_SENTIMENT_WEIGHT, CBS_CONSENSUS_GAP_WEIGHT,
    CBS_POSITIONING_WEIGHT, CBS_DIVERGENCE_WEIGHT, CBS_FAT_PITCH_WEIGHT,
    CBS_VIX_EXTREME_HIGH, CBS_VIX_EXTREME_LOW,
    CBS_AAII_BULL_EXTREME, CBS_AAII_BEAR_EXTREME,
    CBS_SHORT_INTEREST_HIGH, CBS_SHORT_INTEREST_LOW,
    CBS_INST_OWNERSHIP_HIGH, CBS_INST_OWNERSHIP_LOW,
    CBS_DIVERGENCE_THRESHOLD, CBS_FAT_PITCH_MIN_SIGNALS,
    CBS_FINNHUB_DELAY,
)
from tools.db import init_db, upsert_many, query, get_conn

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# SUB-SIGNAL 1: SENTIMENT CYCLE POSITION (Market-Wide)
# ═══════════════════════════════════════════════════════════════════════
# Howard Marks' pendulum: markets oscillate between greed and fear.
# This score is MARKET-LEVEL — same value applied to all stocks, but
# its INTERPRETATION differs per stock (bullish signal in fear,
# bearish signal in greed, adjusted by each stock's beta/cyclicality).

def _fetch_fred_series(series_id: str, lookback_days: int = 365 * 5) -> list[dict]:
    """Fetch a FRED series from local DB (already populated by macro pipeline)."""
    rows = query(
        """SELECT date, value FROM macro_indicators
           WHERE indicator_id = ? AND date >= date('now', ?)
           ORDER BY date ASC""",
        [series_id, f"-{lookback_days} days"],
    )
    return rows


def _vix_percentile() -> float | None:
    """VIX percentile rank over 5 years. Higher = more fear."""
    rows = query(
        """SELECT close FROM price_data
           WHERE symbol = '^VIX' AND date >= date('now', '-1260 days')
           ORDER BY date ASC"""
    )
    if not rows or len(rows) < 60:
        return None

    values = [r["close"] for r in rows if r["close"] is not None]
    if not values:
        return None

    current = values[-1]
    percentile = sum(1 for v in values if v <= current) / len(values) * 100
    return round(percentile, 1)


def _vix_term_structure() -> float | None:
    """VIX vs VIX3M ratio. >1.0 = backwardation (fear). <1.0 = contango (complacency)."""
    vix_rows = query(
        "SELECT close FROM price_data WHERE symbol = '^VIX' ORDER BY date DESC LIMIT 1"
    )
    vix3m_rows = query(
        "SELECT close FROM price_data WHERE symbol = '^VIX3M' ORDER BY date DESC LIMIT 1"
    )
    if not vix_rows or not vix3m_rows:
        return None
    vix = vix_rows[0]["close"]
    vix3m = vix3m_rows[0]["close"]
    if not vix or not vix3m or vix3m == 0:
        return None
    return round(vix / vix3m, 3)


def _aaii_sentiment() -> dict:
    """AAII Investor Sentiment Survey — bull/bear ratio from FRED.
    Series: AAII Bullish% (not directly in FRED, but we use UMich as proxy
    and compute bull/bear from our economic_dashboard if available).
    """
    result = {"bull_bear_ratio": None, "umich_zscore": None}

    # UMich Consumer Sentiment as proxy (already in our DB)
    umich_rows = _fetch_fred_series("UMCSENT", lookback_days=365 * 10)
    if umich_rows and len(umich_rows) >= 24:
        values = [r["value"] for r in umich_rows if r["value"] is not None]
        if values:
            current = values[-1]
            mean = float(np.mean(values))
            std = float(np.std(values))
            if std > 0:
                result["umich_zscore"] = round((current - mean) / std, 2)

    # AAII from economic_dashboard table if available
    aaii_rows = query(
        """SELECT value FROM economic_dashboard
           WHERE indicator_id = 'AAII_BULLISH'
           ORDER BY date DESC LIMIT 1"""
    )
    if aaii_rows and aaii_rows[0]["value"] is not None:
        result["aaii_bullish"] = aaii_rows[0]["value"]

    return result


def _margin_debt_growth() -> float | None:
    """Margin debt YoY growth rate. High growth = excessive leverage = greed.
    Uses FINRA margin debt if available, otherwise FRED margin stats.
    """
    # Check macro_indicators for margin debt (if populated by economic_dashboard)
    rows = _fetch_fred_series("BOGZ1FL663067003Q", lookback_days=365 * 3)
    if not rows or len(rows) < 4:
        return None

    values = [r["value"] for r in rows if r["value"] is not None]
    if len(values) < 4:
        return None

    current = values[-1]
    year_ago = values[-4] if len(values) >= 4 else values[0]  # quarterly
    if year_ago and year_ago > 0:
        return round((current - year_ago) / year_ago * 100, 1)
    return None


def _money_market_fund_flows() -> float | None:
    """Money market fund assets growth — cash on sidelines.
    High = fear (money fleeing risk assets). Drawdown = greed (money entering market).
    """
    rows = _fetch_fred_series("WRMFNS", lookback_days=365 * 3)
    if not rows or len(rows) < 12:
        return None

    values = [r["value"] for r in rows if r["value"] is not None]
    if len(values) < 12:
        return None

    current = values[-1]
    six_mo_ago = values[-26] if len(values) >= 26 else values[0]  # weekly
    if six_mo_ago and six_mo_ago > 0:
        return round((current - six_mo_ago) / six_mo_ago * 100, 1)
    return None


def _put_call_ratio() -> float | None:
    """Equity put/call ratio from CBOE.
    >1.0 = extreme fear (contrarian bullish). <0.6 = complacency (bearish).
    Sourced from price_data if we track $PCALL, otherwise from options data.
    """
    rows = query(
        """SELECT close FROM price_data
           WHERE symbol IN ('^PCALL', 'PCALL')
           ORDER BY date DESC LIMIT 1"""
    )
    if rows and rows[0]["close"] is not None:
        return rows[0]["close"]
    return None


def compute_sentiment_cycle() -> dict:
    """Compute the market-wide sentiment cycle position.

    Returns:
        {
            "cycle_score": -100 to +100 (negative=fear, positive=greed),
            "cycle_position": "extreme_fear"|"fear"|"neutral"|"greed"|"extreme_greed",
            "vix_percentile": float,
            "vix_term_ratio": float,
            "umich_zscore": float,
            "margin_debt_growth": float,
            "mmf_flow": float,
            "put_call": float,
        }
    """
    result = {}
    score_components = []

    # VIX percentile (inverted: high VIX = fear = negative cycle score)
    vix_pctl = _vix_percentile()
    result["vix_percentile"] = vix_pctl
    if vix_pctl is not None:
        # Map 0-100 percentile to -50..+50
        # 90th+ percentile = extreme fear = -50
        # 10th- percentile = extreme complacency = +50
        vix_score = (50 - vix_pctl)  # High VIX percentile = negative (fear)
        score_components.append(("vix", vix_score, 0.30))

    # VIX term structure
    vix_term = _vix_term_structure()
    result["vix_term_ratio"] = vix_term
    if vix_term is not None:
        # >1.05 = backwardation = fear = negative
        # <0.90 = steep contango = complacency = positive
        term_score = (1.0 - vix_term) * 100  # Backwardation = negative
        term_score = max(-40, min(40, term_score))
        score_components.append(("vix_term", term_score, 0.10))

    # UMich sentiment z-score
    aaii_data = _aaii_sentiment()
    umich_z = aaii_data.get("umich_zscore")
    result["umich_zscore"] = umich_z
    if umich_z is not None:
        # Positive z-score = optimistic = greed
        umich_score = umich_z * 20  # Scale: 2 std = 40 pts
        umich_score = max(-40, min(40, umich_score))
        score_components.append(("umich", umich_score, 0.20))

    # Margin debt growth
    margin_growth = _margin_debt_growth()
    result["margin_debt_growth"] = margin_growth
    if margin_growth is not None:
        # >20% YoY growth = leverage mania = greed
        # <-10% = deleveraging = fear
        margin_score = margin_growth * 1.5
        margin_score = max(-40, min(40, margin_score))
        score_components.append(("margin_debt", margin_score, 0.15))

    # Money market fund flows
    mmf_flow = _money_market_fund_flows()
    result["mmf_flow"] = mmf_flow
    if mmf_flow is not None:
        # Positive growth = cash hoarding = fear (inverted)
        # Negative growth = cash deploying = greed
        mmf_score = -mmf_flow * 2  # Invert: cash hoarding = fear = negative
        mmf_score = max(-30, min(30, mmf_score))
        score_components.append(("mmf", mmf_score, 0.15))

    # Put/call ratio
    pc_ratio = _put_call_ratio()
    result["put_call"] = pc_ratio
    if pc_ratio is not None:
        # >1.0 = extreme puts = fear = negative
        # <0.6 = extreme calls = greed = positive
        pc_score = (0.8 - pc_ratio) * 100  # 0.8 is "neutral"
        pc_score = max(-40, min(40, pc_score))
        score_components.append(("put_call", pc_score, 0.10))

    # Weighted composite
    if score_components:
        total_weight = sum(w for _, _, w in score_components)
        cycle_score = sum(s * w for _, s, w in score_components) / total_weight
        cycle_score = max(-100, min(100, cycle_score))
    else:
        # Fallback: use macro regime as proxy
        regime_rows = query("SELECT total_score FROM macro_scores ORDER BY date DESC LIMIT 1")
        if regime_rows:
            cycle_score = regime_rows[0]["total_score"]
        else:
            cycle_score = 0

    result["cycle_score"] = round(cycle_score, 1)

    # Classify position on Marks' pendulum
    if cycle_score <= -40:
        result["cycle_position"] = "extreme_fear"
    elif cycle_score <= -15:
        result["cycle_position"] = "fear"
    elif cycle_score <= 15:
        result["cycle_position"] = "neutral"
    elif cycle_score <= 40:
        result["cycle_position"] = "greed"
    else:
        result["cycle_position"] = "extreme_greed"

    return result


# ═══════════════════════════════════════════════════════════════════════
# SUB-SIGNAL 2: OUR-VS-CONSENSUS GAP (Per Stock)
# ═══════════════════════════════════════════════════════════════════════
# The alpha is in the GAP. When our system says BUY and Wall Street
# also says BUY, the opportunity is priced in. When we disagree with
# consensus, one of us is wrong — and if we're right, that's the edge.

def _get_analyst_consensus(symbol: str) -> dict:
    """Get analyst consensus data for a symbol from fundamentals table.

    Returns: {buy_pct, sell_pct, rating_count, target_upside, finnhub_bullish_pct}
    """
    rows = query(
        """SELECT metric, value FROM fundamentals
           WHERE symbol = ? AND metric IN (
               'analyst_buy_pct', 'analyst_sell_pct', 'analyst_rating_count',
               'analyst_target_consensus', 'finnhub_analyst_bullish_pct'
           )""",
        [symbol],
    )
    data = {r["metric"]: r["value"] for r in rows}

    # Get current price for target upside calc
    price_row = query(
        "SELECT close FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 1",
        [symbol],
    )
    price = price_row[0]["close"] if price_row and price_row[0]["close"] else None
    target = data.get("analyst_target_consensus")

    target_upside = None
    if price and target and price > 0:
        target_upside = (target - price) / price

    return {
        "buy_pct": data.get("analyst_buy_pct"),
        "sell_pct": data.get("analyst_sell_pct"),
        "rating_count": data.get("analyst_rating_count"),
        "target_upside": target_upside,
        "finnhub_bullish_pct": data.get("finnhub_analyst_bullish_pct"),
    }


def compute_consensus_gap(symbol: str, our_convergence_score: float,
                          analyst_data: dict) -> dict:
    """Compute the gap between our view and consensus.

    Our convergence_score is 0-100. We compare its direction against
    analyst consensus to detect where we disagree with the crowd.

    Scoring (calibrated to actual convergence distribution: avg ~16, P90 ~21):
      - We're bullish (score>=20), consensus bearish (buy<=30%) = STRONG contrarian (+40)
      - We're bullish, consensus also very bullish (buy>=85%) = PRICED IN (-30)
      - We're bearish (score<15), consensus very bullish (buy>=85%) = Our bear contrarian (+10)
      - Mild disagreements get smaller scores
    """
    result = {"consensus_gap_score": 0, "gap_type": "unknown"}

    buy_pct = analyst_data.get("buy_pct")
    sell_pct = analyst_data.get("sell_pct")
    fh_bullish = analyst_data.get("finnhub_bullish_pct")

    # Use best available consensus direction
    consensus_bullish = None
    if buy_pct is not None:
        consensus_bullish = buy_pct
    elif fh_bullish is not None:
        consensus_bullish = fh_bullish

    if consensus_bullish is None:
        return result

    # Our direction — calibrated to actual convergence score distribution
    # (avg ~16, P75 ~17, P90 ~21, max ~27 — NOT 0-100 theoretical range)
    # We classify relative to PEERS, not absolute thresholds
    we_are_bullish = our_convergence_score >= 20  # Top ~14% (above P90)
    we_are_neutral = 15 <= our_convergence_score < 20
    we_are_bearish = our_convergence_score < 15  # Below median

    # Consensus direction
    consensus_is_bullish = consensus_bullish >= 70
    consensus_is_very_bullish = consensus_bullish >= 85
    consensus_is_bearish = consensus_bullish <= 30
    consensus_is_neutral = 30 < consensus_bullish < 70

    gap_score = 0

    if we_are_bullish and consensus_is_bearish:
        # GOLD: We see what others don't — classic Marks second-level thinking
        gap_score = 40
        result["gap_type"] = "contrarian_bullish"
    elif we_are_bullish and consensus_is_neutral:
        # Good: we're ahead of consensus shift
        gap_score = 20
        result["gap_type"] = "ahead_of_consensus"
    elif we_are_bullish and consensus_is_very_bullish:
        # DANGER: everyone agrees including us — this is Marks' "when everyone
        # agrees, something is wrong"
        gap_score = -30
        result["gap_type"] = "crowded_agreement"
    elif we_are_bullish and consensus_is_bullish:
        # Mild penalty: partially priced in
        gap_score = -15
        result["gap_type"] = "consensus_aligned"
    elif we_are_bearish and consensus_is_very_bullish:
        # We're contrarian bearish — valuable info but doesn't boost convergence
        # since we don't generate sell signals
        gap_score = 10
        result["gap_type"] = "contrarian_bearish_warning"
    elif we_are_bearish and consensus_is_bearish:
        # Both bearish = nothing interesting
        gap_score = -10
        result["gap_type"] = "consensus_aligned_bearish"
    elif we_are_neutral:
        gap_score = 0
        result["gap_type"] = "neutral"

    # Target upside as confirming/disconfirming signal
    target_upside = analyst_data.get("target_upside")
    if target_upside is not None:
        if target_upside < 0.03 and we_are_bullish:
            # Price already at target — consensus says no upside left
            gap_score -= 10
        elif target_upside > 0.30 and we_are_bullish:
            # Deep discount to target — consensus sees upside too, but
            # price hasn't moved. Why? Investigate.
            gap_score += 5

    result["consensus_gap_score"] = max(-50, min(50, gap_score))
    return result


# ═══════════════════════════════════════════════════════════════════════
# SUB-SIGNAL 3: POSITIONING EXTREMES (Per Stock)
# ═══════════════════════════════════════════════════════════════════════
# Marks: "Risk is invisible in good times. Apparent stability is often
# concealed fragility." Extreme positioning = fragility. When everyone
# is on the same side of the boat, the boat capsizes.

def _get_short_interest(symbol: str) -> dict:
    """Get short interest data from fundamentals table."""
    rows = query(
        """SELECT metric, value FROM fundamentals
           WHERE symbol = ? AND metric IN (
               'short_interest_pct', 'short_ratio', 'shares_short',
               'float_shares', 'institutional_pct'
           )""",
        [symbol],
    )
    return {r["metric"]: r["value"] for r in rows}


def compute_positioning_extremes(symbol: str, short_data: dict,
                                 analyst_data: dict) -> dict:
    """Score positioning extremes for a symbol.

    Extreme short interest = potential squeeze (contrarian bullish).
    Very low short interest = complacency (contrarian bearish).
    Extreme institutional ownership = crowded long (fragile).
    Very low institutional = neglected (potential opportunity).
    """
    result = {"positioning_score": 0, "positioning_flags": []}
    score = 0
    flags = []

    # Short interest as % of float
    si_pct = short_data.get("short_interest_pct")
    if si_pct is not None:
        if si_pct >= CBS_SHORT_INTEREST_HIGH:
            # Heavy short interest = potential squeeze + market thinks it's broken
            # Contrarian: if our system is bullish, this amplifies the signal
            score += 25
            flags.append("heavy_short_interest")
        elif si_pct >= 10:
            score += 10
            flags.append("elevated_short_interest")
        elif si_pct <= CBS_SHORT_INTEREST_LOW:
            # Almost no shorts = everyone is long = complacency
            score -= 10
            flags.append("minimal_short_interest")

    # Short ratio (days to cover)
    short_ratio = short_data.get("short_ratio")
    if short_ratio is not None:
        if short_ratio >= 8:
            # Very crowded short — squeeze risk
            score += 15
            flags.append("high_days_to_cover")
        elif short_ratio >= 5:
            score += 5

    # Institutional ownership
    inst_pct = short_data.get("institutional_pct")
    if inst_pct is not None:
        if inst_pct >= CBS_INST_OWNERSHIP_HIGH:
            # Over-owned by institutions — when they sell, it's violent
            score -= 15
            flags.append("crowded_institutional")
        elif inst_pct <= CBS_INST_OWNERSHIP_LOW:
            # Under-owned — room for institutional accumulation
            score += 15
            flags.append("underfollowed")

    # Analyst rating skew (from sub-signal 2 data)
    buy_pct = analyst_data.get("buy_pct")
    sell_pct = analyst_data.get("sell_pct")
    rating_count = analyst_data.get("rating_count")

    if buy_pct is not None and rating_count and rating_count >= 5:
        if buy_pct >= 90:
            # Near-unanimous buy = extreme crowding = fragile
            score -= 20
            flags.append("analyst_unanimity_buy")
        elif sell_pct is not None and sell_pct >= 60:
            # Widely hated = contrarian opportunity
            score += 20
            flags.append("analyst_widely_hated")

    result["positioning_score"] = max(-50, min(50, score))
    result["positioning_flags"] = flags
    return result


# ═══════════════════════════════════════════════════════════════════════
# SUB-SIGNAL 4: SIGNAL DIVERGENCE (Per Stock)
# ═══════════════════════════════════════════════════════════════════════
# When our own modules disagree, that IS information. A stock where
# smart money is buying but technicals are bearish could mean:
# (a) Smart money sees something the market hasn't priced (fat pitch), or
# (b) Smart money is wrong and about to take a loss (value trap).
# The divergence score measures internal disagreement magnitude.

def compute_signal_divergence(symbol: str, module_scores: dict) -> dict:
    """Compute divergence between our own modules' views on a symbol.

    High divergence = modules disagree = INFORMATION.
    We split modules into "fundamental" camp and "momentum/technical" camp
    and measure the gap.

    Scoring:
      - Fundamental bullish + momentum bearish = "accumulation divergence" (+15)
        (Smart money accumulating before market catches up — classic Marks)
      - Fundamental bearish + momentum bullish = "distribution divergence" (-15)
        (Momentum running on fumes — late-cycle danger, overvalued)
      - Both camps agree = no divergence signal (0)
    """
    result = {"divergence_score": 0, "divergence_type": "none", "divergence_magnitude": 0}

    # Fundamental camp: smart money, worldview, variant, research, estimate_momentum
    fund_modules = ["smartmoney", "worldview", "variant", "research",
                    "estimate_momentum", "ma"]
    # Momentum/Technical camp: main_signal, pattern_options, pairs, sector_expert
    mom_modules = ["main_signal", "pattern_options", "pairs", "sector_expert",
                   "news_displacement"]

    fund_scores = [module_scores.get(m, {}).get(symbol, 0) for m in fund_modules]
    mom_scores = [module_scores.get(m, {}).get(symbol, 0) for m in mom_modules]

    # Filter out zeros (module didn't fire = no opinion, not bearish)
    fund_active = [s for s in fund_scores if s > 0]
    mom_active = [s for s in mom_scores if s > 0]

    if not fund_active and not mom_active:
        return result

    fund_avg = float(np.mean(fund_active)) if fund_active else 0
    mom_avg = float(np.mean(mom_active)) if mom_active else 0

    # Divergence magnitude (0-100 scale)
    divergence = abs(fund_avg - mom_avg)
    result["divergence_magnitude"] = round(divergence, 1)

    if divergence < CBS_DIVERGENCE_THRESHOLD:
        result["divergence_type"] = "aligned"
        result["divergence_score"] = 0
        return result

    score = 0
    if fund_avg > mom_avg + CBS_DIVERGENCE_THRESHOLD:
        # Fundamentals bullish, momentum lagging
        # This is the Marks pattern: smart money sees value before price
        score = min(25, int(divergence * 0.5))
        result["divergence_type"] = "accumulation"
    elif mom_avg > fund_avg + CBS_DIVERGENCE_THRESHOLD:
        # Momentum bullish, fundamentals skeptical
        # Late-cycle danger: price running ahead of reality
        score = -min(20, int(divergence * 0.4))
        result["divergence_type"] = "distribution"

    result["divergence_score"] = score
    return result


# ═══════════════════════════════════════════════════════════════════════
# SUB-SIGNAL 5: FAT PITCH DETECTOR (Per Stock)
# ═══════════════════════════════════════════════════════════════════════
# Marks + Buffett: "Wait for the fat pitch." Don't force trades.
# A fat pitch requires MULTIPLE conditions converging simultaneously:
#   1. Market-wide fear (cycle position)
#   2. This specific stock is deeply undervalued (variant perception)
#   3. Smart money is buying (13F conviction)
#   4. Insiders are buying (skin in the game)
#   5. Our system is bullish (convergence score)
# All five = once-in-a-cycle opportunity. Any three = interesting.

def compute_fat_pitch(symbol: str, cycle_score: float,
                      module_scores: dict, our_convergence: float,
                      insider_score_override: float | None = None) -> dict:
    """Detect fat pitch conditions (Marks/Buffett extreme dislocation).

    Each condition is binary (met/not-met). The score scales with how
    many conditions converge.

    Returns:
        {
            "fat_pitch_score": 0-100,
            "fat_pitch_conditions": list[str],
            "fat_pitch_count": int,
            "anti_pitch_count": int,  # greed + overvaluation = anti-pitch
        }
    """
    conditions_met = []
    anti_conditions = []

    # 1. Market-wide fear (cycle_score < -20)
    if cycle_score <= -30:
        conditions_met.append("extreme_fear")
    elif cycle_score <= -15:
        conditions_met.append("fear")

    # Anti-condition: extreme greed
    if cycle_score >= 30:
        anti_conditions.append("extreme_greed")
    elif cycle_score >= 15:
        anti_conditions.append("greed")

    # 2. Deep undervaluation (variant_score > 65)
    variant = module_scores.get("variant", {}).get(symbol, 0)
    if variant >= 70:
        conditions_met.append("deep_undervaluation")
    elif variant >= 60:
        conditions_met.append("undervaluation")

    # Anti-condition: overvaluation
    if variant < 30 and variant > 0:
        anti_conditions.append("overvaluation")

    # 3. Smart money buying (conviction_score > 60)
    smartmoney = module_scores.get("smartmoney", {}).get(symbol, 0)
    if smartmoney >= 65:
        conditions_met.append("smart_money_buying")
    elif smartmoney >= 55:
        conditions_met.append("smart_money_interested")

    # 4. Insider buying (batch-loaded or per-query fallback)
    if insider_score_override is not None:
        insider_score = insider_score_override
    else:
        insider_rows = query(
            """SELECT MAX(insider_score) as score FROM insider_signals
               WHERE symbol = ? AND date >= date('now', '-30 days')""",
            [symbol],
        )
        insider_score = insider_rows[0]["score"] if insider_rows and insider_rows[0]["score"] else 0
    if insider_score >= 60:
        conditions_met.append("insider_buying")
    elif insider_score >= 40:
        conditions_met.append("insider_interest")

    # Anti-condition: insider selling
    if insider_score <= 15 and insider_score > 0:
        anti_conditions.append("insider_selling")

    # 5. Our convergence is bullish (calibrated to actual distribution: avg ~16, P90 ~21)
    if our_convergence >= 22:
        conditions_met.append("system_bullish")
    elif our_convergence >= 18:
        conditions_met.append("system_leaning_bullish")

    # Score: geometric scaling — each additional condition multiplicatively increases
    count = len(conditions_met)
    anti_count = len(anti_conditions)

    if count >= CBS_FAT_PITCH_MIN_SIGNALS:
        # Base score + exponential bonus for convergence of conditions
        base_scores = {3: 40, 4: 70, 5: 90}
        fat_pitch_score = base_scores.get(min(count, 5), 90)
        # Penalty for anti-conditions (temper enthusiasm when some things are wrong)
        fat_pitch_score -= anti_count * 10
    else:
        fat_pitch_score = count * 5  # 0-1 conditions = minimal

    # Anti-pitch: greed + overvaluation converging
    if anti_count >= 3:
        fat_pitch_score = max(0, fat_pitch_score - 30)

    return {
        "fat_pitch_score": max(0, min(100, fat_pitch_score)),
        "fat_pitch_conditions": conditions_met,
        "fat_pitch_count": count,
        "anti_pitch_count": anti_count,
        "anti_pitch_conditions": anti_conditions,
    }


# ═══════════════════════════════════════════════════════════════════════
# COMPOSITE SCORE
# ═══════════════════════════════════════════════════════════════════════

def compute_cbs_score(sentiment_sub: float, consensus_gap_sub: float,
                      positioning_sub: float, divergence_sub: float,
                      fat_pitch_sub: float) -> float:
    """Compute composite Consensus Blindspots Score (0-100).

    Each sub-signal is on different scales. We normalize and apply point
    contributions anchored at 50 (neutral). Config weights (CBS_*_WEIGHT)
    control the relative contribution of each sub-signal.

    Key insight: this score is ADDITIVE to convergence, not redundant.
    A high CBS score means "our view has a contrarian edge" — it AMPLIFIES
    the convergence signal rather than replacing it.
    """
    score = 50.0

    # Sub-signal 1: Sentiment Cycle — market-level modifier
    # cycle_score is -100 to +100. Invert: fear = opportunity for longs
    # Scale factor: CBS_SENTIMENT_WEIGHT (0.25) × 60 = max ±15 pts
    sentiment_pts = -sentiment_sub * CBS_SENTIMENT_WEIGHT * 0.60
    sentiment_pts = max(-15, min(15, sentiment_pts))
    score += sentiment_pts

    # Sub-signal 2: Our-vs-Consensus Gap — THE core Marks signal
    # Already scored -50 to +50. Scale: CBS_CONSENSUS_GAP_WEIGHT (0.30) × 2.0
    # Contrarian bullish (+40) → +24 pts, Crowded agreement (-30) → -18 pts
    score += consensus_gap_sub * CBS_CONSENSUS_GAP_WEIGHT * 2.0

    # Sub-signal 3: Positioning Extremes
    # Already scored -50 to +50. Scale: CBS_POSITIONING_WEIGHT (0.20) × 2.0
    score += positioning_sub * CBS_POSITIONING_WEIGHT * 2.0

    # Sub-signal 4: Signal Divergence
    # Already scored -25 to +25. Scale: CBS_DIVERGENCE_WEIGHT (0.15) × 2.0
    score += divergence_sub * CBS_DIVERGENCE_WEIGHT * 2.0

    # Sub-signal 5: Fat Pitch — bonus for extreme convergence of conditions
    # 0-100 scale. Scale: CBS_FAT_PITCH_WEIGHT (0.10) × 1.0
    fat_pitch_pts = max(0, (fat_pitch_sub - 20) * CBS_FAT_PITCH_WEIGHT)
    score += fat_pitch_pts

    return max(0, min(100, round(score, 1)))


# ═══════════════════════════════════════════════════════════════════════
# MAIN RUN
# ═══════════════════════════════════════════════════════════════════════

def run(symbols: list[str] | None = None):
    """Run the Consensus Blindspots module.

    Phase 2.8: runs AFTER all other modules since it reads their outputs.
    """
    init_db()

    print("\n" + "=" * 60)
    print("  CONSENSUS BLINDSPOTS — Second-Level Thinking")
    print("  Howard Marks: 'To outperform, your thinking must be")
    print("  different AND more accurate than consensus.'")
    print("=" * 60)

    # ── Step 1: Market-wide sentiment cycle ──
    print("\n  [1/5] Computing sentiment cycle position...")
    cycle_data = compute_sentiment_cycle()
    cycle_score = cycle_data["cycle_score"]
    cycle_pos = cycle_data["cycle_position"]
    print(f"        Cycle score: {cycle_score:+.1f} ({cycle_pos})")
    if cycle_data["vix_percentile"] is not None:
        print(f"        VIX percentile: {cycle_data['vix_percentile']:.0f}th")
    if cycle_data["umich_zscore"] is not None:
        print(f"        UMich z-score: {cycle_data['umich_zscore']:+.2f}")

    # ── Step 2: Load all module scores (from convergence engine's source tables) ──
    print("\n  [2/5] Loading module scores for divergence analysis...")

    # Import the loader from convergence_engine
    from tools.convergence_engine import _load_module_scores
    module_scores = _load_module_scores()

    # Also load convergence scores
    conv_rows = query(
        """SELECT symbol, convergence_score, module_count, conviction_level
           FROM convergence_signals
           WHERE date = (SELECT MAX(date) FROM convergence_signals)"""
    )
    convergence_map = {r["symbol"]: r for r in conv_rows}
    print(f"        {len(convergence_map)} symbols with convergence scores")

    # ── Step 3: Determine symbols to analyze ──
    if symbols is None:
        symbols = list(convergence_map.keys())
    print(f"        Analyzing {len(symbols)} symbols")

    # Batch-load per-stock data (avoid N+1 queries — ~2000 individual queries → 5)
    analyst_rows = query(
        """SELECT symbol, metric, value FROM fundamentals
           WHERE metric IN (
               'analyst_buy_pct', 'analyst_sell_pct', 'analyst_rating_count',
               'analyst_target_consensus', 'finnhub_analyst_bullish_pct'
           )"""
    )
    _analyst_bulk = {}
    for r in analyst_rows:
        _analyst_bulk.setdefault(r["symbol"], {})[r["metric"]] = r["value"]

    price_rows = query(
        """SELECT symbol, close FROM price_data
           WHERE (symbol, date) IN (
               SELECT symbol, MAX(date) FROM price_data GROUP BY symbol
           )"""
    )
    _price_bulk = {r["symbol"]: r["close"] for r in price_rows if r["close"]}

    short_rows = query(
        """SELECT symbol, metric, value FROM fundamentals
           WHERE metric IN (
               'short_interest_pct', 'short_ratio', 'shares_short',
               'float_shares', 'institutional_pct'
           )"""
    )
    _short_bulk = {}
    for r in short_rows:
        _short_bulk.setdefault(r["symbol"], {})[r["metric"]] = r["value"]

    insider_rows = query(
        """SELECT symbol, MAX(insider_score) as score FROM insider_signals
           WHERE date >= date('now', '-30 days')
           GROUP BY symbol"""
    )
    _insider_bulk = {r["symbol"]: r["score"] for r in insider_rows if r["score"]}

    # ── Step 4: Per-stock analysis ──
    print("\n  [3/5] Computing per-stock consensus gaps & positioning...")
    today = date.today().isoformat()
    results = []
    fat_pitches = []
    contrarian_opportunities = []
    crowded_agreements = []

    errors = 0
    for i, symbol in enumerate(symbols):
      try:
        conv_data = convergence_map.get(symbol, {})
        our_score = conv_data.get("convergence_score", 0) if isinstance(conv_data, dict) else 0

        # Sub-signal 2: Our-vs-Consensus Gap (batch lookup)
        raw_analyst = _analyst_bulk.get(symbol, {})
        price = _price_bulk.get(symbol)
        target = raw_analyst.get("analyst_target_consensus")
        target_upside = ((target - price) / price) if (price and target and price > 0) else None
        analyst_data = {
            "buy_pct": raw_analyst.get("analyst_buy_pct"),
            "sell_pct": raw_analyst.get("analyst_sell_pct"),
            "rating_count": raw_analyst.get("analyst_rating_count"),
            "target_upside": target_upside,
            "finnhub_bullish_pct": raw_analyst.get("finnhub_analyst_bullish_pct"),
        }
        gap_result = compute_consensus_gap(symbol, our_score, analyst_data)

        # Sub-signal 3: Positioning Extremes (batch lookup)
        short_data = _short_bulk.get(symbol, {})
        positioning_result = compute_positioning_extremes(symbol, short_data, analyst_data)

        # Sub-signal 4: Signal Divergence
        divergence_result = compute_signal_divergence(symbol, module_scores)

        # Sub-signal 5: Fat Pitch Detector (batch insider lookup)
        fat_pitch_result = compute_fat_pitch(
            symbol, cycle_score, module_scores, our_score,
            insider_score_override=_insider_bulk.get(symbol, 0),
        )

        # Composite score
        cbs_score = compute_cbs_score(
            sentiment_sub=cycle_score,
            consensus_gap_sub=gap_result["consensus_gap_score"],
            positioning_sub=positioning_result["positioning_score"],
            divergence_sub=divergence_result["divergence_score"],
            fat_pitch_sub=fat_pitch_result["fat_pitch_score"],
        )

        # Build narrative
        parts = []
        if gap_result["gap_type"] not in ("unknown", "neutral"):
            parts.append(gap_result["gap_type"])
        if positioning_result["positioning_flags"]:
            parts.append("|".join(positioning_result["positioning_flags"][:2]))
        if divergence_result["divergence_type"] != "none":
            parts.append(f"div:{divergence_result['divergence_type']}")
        if fat_pitch_result["fat_pitch_count"] >= CBS_FAT_PITCH_MIN_SIGNALS:
            parts.append(f"FAT_PITCH({fat_pitch_result['fat_pitch_count']})")
        narrative = f"[{cycle_pos}] {' | '.join(parts)}" if parts else f"[{cycle_pos}] no_signal"

        results.append((
            symbol, today, cbs_score,
            cycle_score, cycle_pos,
            gap_result["consensus_gap_score"], gap_result["gap_type"],
            positioning_result["positioning_score"],
            json.dumps(positioning_result["positioning_flags"]),
            divergence_result["divergence_score"],
            divergence_result["divergence_type"],
            divergence_result["divergence_magnitude"],
            fat_pitch_result["fat_pitch_score"],
            fat_pitch_result["fat_pitch_count"],
            json.dumps(fat_pitch_result["fat_pitch_conditions"]),
            fat_pitch_result["anti_pitch_count"],
            json.dumps(fat_pitch_result.get("anti_pitch_conditions", [])),
            analyst_data.get("buy_pct"),
            analyst_data.get("sell_pct"),
            analyst_data.get("target_upside"),
            short_data.get("short_interest_pct"),
            short_data.get("institutional_pct"),
            our_score,
            narrative,
        ))

        # Track notable results
        if cbs_score >= 65:
            contrarian_opportunities.append((symbol, cbs_score, gap_result["gap_type"],
                                             fat_pitch_result["fat_pitch_count"]))
        if fat_pitch_result["fat_pitch_count"] >= 3:
            fat_pitches.append((symbol, cbs_score, fat_pitch_result["fat_pitch_count"],
                                fat_pitch_result["fat_pitch_conditions"]))
        if gap_result["gap_type"] == "crowded_agreement":
            crowded_agreements.append((symbol, our_score, analyst_data.get("buy_pct")))

      except Exception as e:
        errors += 1
        if errors <= 5:
            logger.warning(f"CBS error for {symbol}: {e}")

        if (i + 1) % 100 == 0:
            print(f"        Processed {i + 1}/{len(symbols)} symbols...")
    if errors:
        print(f"        {errors} symbols had errors (logged first 5)")

    # ── Step 5: Store results ──
    print("\n  [5/6] Storing results...")
    if results:
        upsert_many(
            "consensus_blindspot_signals",
            ["symbol", "date", "cbs_score",
             "cycle_score", "cycle_position",
             "consensus_gap_score", "gap_type",
             "positioning_score", "positioning_flags",
             "divergence_score", "divergence_type", "divergence_magnitude",
             "fat_pitch_score", "fat_pitch_count", "fat_pitch_conditions",
             "anti_pitch_count", "anti_pitch_conditions",
             "analyst_buy_pct", "analyst_sell_pct", "analyst_target_upside",
             "short_interest_pct", "institutional_pct",
             "our_convergence_score", "narrative"],
            results,
        )

    # Store cycle data as a market-wide record
    upsert_many(
        "consensus_blindspot_signals",
        ["symbol", "date", "cbs_score", "cycle_score", "cycle_position",
         "consensus_gap_score", "gap_type", "positioning_score", "positioning_flags",
         "divergence_score", "divergence_type", "divergence_magnitude",
         "fat_pitch_score", "fat_pitch_count", "fat_pitch_conditions",
         "anti_pitch_count", "anti_pitch_conditions",
         "analyst_buy_pct", "analyst_sell_pct", "analyst_target_upside",
         "short_interest_pct", "institutional_pct",
         "our_convergence_score", "narrative"],
        [("_MARKET", today, 50,
          cycle_score, cycle_pos,
          0, "market_wide",
          0, "[]",
          0, "none", 0,
          0, 0, "[]",
          0, "[]",
          None, None, None,
          None, None,
          0, f"Market sentiment: {cycle_pos} ({cycle_score:+.1f})")],
    )

    # ── Summary ──
    print(f"\n  [6/6] Summary")
    print(f"  {'='*58}")
    print(f"  Market Cycle: {cycle_pos.upper()} (score: {cycle_score:+.1f})")
    print(f"  Symbols analyzed: {len(results)}")

    above_65 = sum(1 for r in results if r[2] >= 65)
    below_35 = sum(1 for r in results if r[2] <= 35)
    print(f"  Contrarian opportunities (CBS >= 65): {above_65}")
    print(f"  Crowded/consensus-aligned (CBS <= 35): {below_35}")

    if fat_pitches:
        fat_pitches.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  FAT PITCHES ({len(fat_pitches)}):")
        print(f"    {'Symbol':>8} | {'CBS':>5} | {'#Cond':>5} | Conditions")
        print(f"    {'-'*8}-+-{'-'*5}-+-{'-'*5}-+-{'-'*30}")
        for sym, cbs, count, conds in fat_pitches[:10]:
            print(f"    {sym:>8} | {cbs:5.0f} | {count:>5} | {', '.join(conds[:3])}")

    if contrarian_opportunities:
        contrarian_opportunities.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  TOP CONTRARIAN OPPORTUNITIES ({len(contrarian_opportunities)}):")
        print(f"    {'Symbol':>8} | {'CBS':>5} | {'Gap Type':>22} | {'FP#':>3}")
        print(f"    {'-'*8}-+-{'-'*5}-+-{'-'*22}-+-{'-'*3}")
        for sym, cbs, gap_type, fp_count in contrarian_opportunities[:15]:
            print(f"    {sym:>8} | {cbs:5.0f} | {gap_type:>22} | {fp_count:>3}")

    if crowded_agreements:
        print(f"\n  CROWDED AGREEMENTS — CAUTION ({len(crowded_agreements)}):")
        print(f"    {'Symbol':>8} | {'Our Score':>9} | {'Buy%':>5}")
        print(f"    {'-'*8}-+-{'-'*9}-+-{'-'*5}")
        for sym, our, buy in crowded_agreements[:10]:
            buy_s = f"{buy:.0f}" if buy is not None else "?"
            print(f"    {sym:>8} | {our:9.0f} | {buy_s:>5}")

    print(f"\n  {'='*58}")
    print(f"  Howard Marks: 'We may never know where we're going,")
    print(f"  but we'd better have a good sense of where we are.'")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import argparse

    parser = argparse.ArgumentParser(description="Consensus Blindspots — Second-Level Thinking")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (default: all convergence)")
    args = parser.parse_args()

    sym_list = args.symbols.split(",") if args.symbols else None
    run(sym_list)
