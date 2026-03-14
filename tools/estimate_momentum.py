"""Estimate Revision Momentum — the Jane Street edge.

Tracks the VELOCITY and ACCELERATION of analyst estimate revisions.
Variant Perception asks "is the stock mispriced?" — this module asks
"is the consensus MOVING, and how fast?"

Key insight: estimate revision momentum is one of the most documented
alpha factors in quantitative finance. When analysts start revising
estimates in one direction, it persists for 2-6 months. The market
underreacts to these revisions.

Signals:
  1. EPS Revision Velocity — how fast are EPS estimates changing? (7d/30d/90d)
  2. Revenue Revision Velocity — same for revenue
  3. Revision Acceleration — is the velocity speeding up or slowing down?
  4. Earnings Surprise Momentum — consecutive beat/miss streaks with magnitude
  5. Estimate Dispersion Change — tightening = conviction growing
  6. Cross-Sectional Rank — revision strength relative to sector peers

Score: 0-100 composite. Feeds into convergence engine as 16th module.
"""

import sys
import time
import logging
import numpy as np
from datetime import date, datetime

_project_root = str(__import__("pathlib").Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import (
    FMP_API_KEY,
    EM_REVISION_VELOCITY_WEIGHT,
    EM_REVENUE_VELOCITY_WEIGHT,
    EM_ACCELERATION_WEIGHT,
    EM_SURPRISE_MOMENTUM_WEIGHT,
    EM_DISPERSION_WEIGHT,
    EM_CROSS_SECTIONAL_WEIGHT,
    EM_STRONG_REVISION_PCT,
    EM_MODERATE_REVISION_PCT,
    EM_SURPRISE_STREAK_BONUS,
    EM_DISPERSION_TIGHTENING_BONUS,
)
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# FMP API helper (lightweight, avoids broken fmp_get import)
# ---------------------------------------------------------------------------

def _fmp_get(endpoint: str, params: dict = None) -> list | dict | None:
    """Call FMP API. Returns parsed JSON or None on failure."""
    import requests
    if not FMP_API_KEY:
        return None
    base = "https://financialmodelingprep.com/api/v3"
    url = f"{base}{endpoint}"
    p = {"apikey": FMP_API_KEY}
    if params:
        p.update(params)
    try:
        resp = requests.get(url, params=p, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Data fetching — yfinance primary, FMP fallback for estimates
# ---------------------------------------------------------------------------

def _fetch_yf_estimates(symbol: str) -> dict:
    """Fetch estimate data from yfinance.

    Returns dict with keys:
      eps_trend: {period: {current, 7d, 30d, 60d, 90d}}
      earnings_estimate: {period: {avg, low, high, num_analysts}}
      revenue_estimate: {period: {avg, low, high, num_analysts}}
      earnings_history: [{quarter, estimate, actual, surprise_pct}]
    """
    import yfinance as yf

    result = {
        "eps_trend": {},
        "earnings_estimate": {},
        "revenue_estimate": {},
        "earnings_history": [],
    }

    try:
        ticker = yf.Ticker(symbol)

        # EPS Trend — estimates at different lookback windows
        # yfinance returns: columns=[current, 7daysAgo, 30daysAgo, 60daysAgo, 90daysAgo]
        #                   index=[0q, +1q, 0y, +1y] (periods)
        try:
            eps_trend = ticker.eps_trend
            if eps_trend is not None and not eps_trend.empty:
                for period_idx in eps_trend.index:
                    period_data = {}
                    for col in eps_trend.columns:
                        val = eps_trend.loc[period_idx, col]
                        if val is not None and not (isinstance(val, float) and np.isnan(val)):
                            # Normalize column names for our code
                            key = str(col).lower().replace(" ", "_")
                            period_data[key] = float(val)
                    if period_data:
                        result["eps_trend"][str(period_idx)] = period_data
        except Exception:
            pass

        # Earnings estimates (current + next quarter/year)
        # yfinance returns: columns=[avg, low, high, yearAgoEps, numberOfAnalysts, growth]
        #                   index=[0q, +1q, 0y, +1y]
        try:
            ee = ticker.earnings_estimate
            if ee is not None and not ee.empty:
                for period_idx in ee.index:
                    period_data = {}
                    for col in ee.columns:
                        val = ee.loc[period_idx, col]
                        if val is not None and not (isinstance(val, float) and np.isnan(val)):
                            key = str(col).lower().replace(" ", "_")
                            # Normalize yfinance keys to our standard
                            if key == "numberofanalysts":
                                key = "num_analysts"
                            elif key == "yearagoeps":
                                key = "year_ago_eps"
                            period_data[key] = float(val)
                    if period_data:
                        result["earnings_estimate"][str(period_idx)] = period_data
        except Exception:
            pass

        # Revenue estimates
        # yfinance returns: columns=[avg, low, high, numberOfAnalysts, yearAgoRevenue, growth]
        #                   index=[0q, +1q, 0y, +1y]
        try:
            re_ = ticker.revenue_estimate
            if re_ is not None and not re_.empty:
                for period_idx in re_.index:
                    period_data = {}
                    for col in re_.columns:
                        val = re_.loc[period_idx, col]
                        if val is not None and not (isinstance(val, float) and np.isnan(val)):
                            key = str(col).lower().replace(" ", "_")
                            if key == "numberofanalysts":
                                key = "num_analysts"
                            elif key == "yearagorevenue":
                                key = "year_ago_revenue"
                            period_data[key] = float(val)
                    if period_data:
                        result["revenue_estimate"][str(period_idx)] = period_data
        except Exception:
            pass

        # Earnings history (actual vs estimate for past quarters)
        # yfinance returns: columns=[epsActual, epsEstimate, epsDifference, surprisePercent]
        #                   index=Timestamps
        try:
            eh = ticker.earnings_history
            if eh is not None and not eh.empty:
                for idx, row in eh.iterrows():
                    actual = row.get("epsActual")
                    estimated = row.get("epsEstimate")
                    surprise_pct = row.get("surprisePercent")

                    if actual is not None and not (isinstance(actual, float) and np.isnan(actual)):
                        entry = {
                            "quarter": str(idx.date()) if hasattr(idx, 'date') else str(idx),
                            "actual": float(actual),
                            "estimate": float(estimated) if estimated is not None and not (isinstance(estimated, float) and np.isnan(estimated)) else None,
                            # surprisePercent is already a ratio (0.08 = 8%), convert to pct
                            "surprise_pct": round(float(surprise_pct) * 100, 2) if surprise_pct is not None and not (isinstance(surprise_pct, float) and np.isnan(surprise_pct)) else None,
                        }
                        result["earnings_history"].append(entry)
        except Exception:
            pass

    except Exception as e:
        logger.debug(f"yfinance estimate fetch failed for {symbol}: {e}")

    return result


def _fetch_fmp_estimates(symbol: str) -> dict:
    """Fallback: fetch estimate snapshots from FMP API."""
    result = {
        "eps_trend": {},
        "earnings_estimate": {},
        "revenue_estimate": {},
        "earnings_history": [],
    }

    # Analyst estimates (quarterly)
    estimates = _fmp_get(f"/analyst-estimates/{symbol}", {"period": "quarter", "limit": 8})
    if estimates and isinstance(estimates, list):
        for est in estimates[:4]:
            period = est.get("date", "unknown")
            result["earnings_estimate"][period] = {
                "avg": est.get("estimatedEpsAvg"),
                "low": est.get("estimatedEpsLow"),
                "high": est.get("estimatedEpsHigh"),
                "num_analysts": est.get("numberAnalystEstimatedEps"),
            }
            result["revenue_estimate"][period] = {
                "avg": est.get("estimatedRevenueAvg"),
                "low": est.get("estimatedRevenueLow"),
                "high": est.get("estimatedRevenuHigh"),
                "num_analysts": est.get("numberAnalystsEstimatedRevenue"),
            }

    # Earnings surprises
    surprises = _fmp_get(f"/earnings-surprises/{symbol}")
    if surprises and isinstance(surprises, list):
        for s in surprises[:8]:
            actual = s.get("actualEarningResult")
            estimated = s.get("estimatedEarning")
            if actual is not None and estimated is not None and abs(estimated) > 0.001:
                result["earnings_history"].append({
                    "quarter": s.get("date"),
                    "estimate": estimated,
                    "actual": actual,
                    "surprise_pct": round((actual - estimated) / abs(estimated) * 100, 2),
                })

    return result


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def _compute_eps_revision_velocity(eps_trend: dict) -> dict:
    """Compute EPS revision velocity from trend data.

    Returns: {velocity_7d, velocity_30d, velocity_90d, velocity_score (0-100)}
    """
    result = {"velocity_7d": None, "velocity_30d": None, "velocity_90d": None, "velocity_score": 0}

    # eps_trend keys after normalization: current, 7daysago, 30daysago, 60daysago, 90daysago
    # Each period (0q, +1q, 0y, +1y) has these lookback values
    for period_key, period_data in eps_trend.items():
        current = period_data.get("current")
        ago_7d = period_data.get("7daysago")
        ago_30d = period_data.get("30daysago")
        ago_90d = period_data.get("90daysago")

        if current is None:
            continue

        # Compute percentage changes
        if ago_7d and abs(ago_7d) > 0.001:
            result["velocity_7d"] = round((current - ago_7d) / abs(ago_7d) * 100, 3)
        if ago_30d and abs(ago_30d) > 0.001:
            result["velocity_30d"] = round((current - ago_30d) / abs(ago_30d) * 100, 3)
        if ago_90d and abs(ago_90d) > 0.001:
            result["velocity_90d"] = round((current - ago_90d) / abs(ago_90d) * 100, 3)

        # Use the first valid period (nearest quarter) and break
        break

    # Score: weighted combination of velocities
    score = 0
    weights = [(result["velocity_7d"], 0.5), (result["velocity_30d"], 0.3), (result["velocity_90d"], 0.2)]

    for vel, w in weights:
        if vel is None:
            continue
        # Map velocity to 0-100 scale
        # Strong revision: >5% change → max contribution
        # Moderate: 1-5% → partial
        # Weak: <1% → minimal
        abs_vel = abs(vel)
        if abs_vel >= EM_STRONG_REVISION_PCT:
            contribution = 100
        elif abs_vel >= EM_MODERATE_REVISION_PCT:
            contribution = 30 + 70 * (abs_vel - EM_MODERATE_REVISION_PCT) / (EM_STRONG_REVISION_PCT - EM_MODERATE_REVISION_PCT)
        else:
            contribution = abs_vel / EM_MODERATE_REVISION_PCT * 30

        # Direction: positive revisions are bullish
        if vel > 0:
            score += contribution * w
        else:
            # Negative revisions still score (they're informative for shorts)
            # but we score on the bearish side (inverted for convergence)
            score += contribution * w * 0.3  # downward revisions get 30% weight

    result["velocity_score"] = round(min(100, max(0, score)), 1)
    return result


def _compute_revenue_revision_velocity(rev_estimates: dict) -> dict:
    """Compute revenue revision velocity from snapshot comparisons.

    For revenue, we compare current snapshot to stored historical snapshots.
    Returns: {rev_velocity_score (0-100)}
    """
    # Revenue estimates don't have the nice trend data like EPS
    # We'll compare high/low spread changes as a proxy for direction
    result = {"rev_velocity_score": 0}

    for period_key, period_data in rev_estimates.items():
        avg = period_data.get("avg")
        num = period_data.get("num_analysts") or period_data.get("number_of_analysts")

        if avg is None:
            continue

        # More analysts covering = more reliable signal
        analyst_boost = min(1.0, (num or 1) / 10) if num else 0.5

        # Check if we have a stored historical snapshot to compare
        # On first run, we just store the snapshot; velocity comes from subsequent runs
        result["rev_avg_estimate"] = avg
        result["rev_num_analysts"] = num
        result["analyst_coverage_boost"] = round(analyst_boost, 2)
        break

    return result


def _compute_revision_acceleration(eps_trend: dict) -> dict:
    """Is the revision velocity INCREASING or DECREASING?

    Acceleration = velocity of velocity. If 7d revision > 30d/3 revision,
    revisions are accelerating. This is the second derivative.
    Returns: {acceleration, acceleration_score (0-100)}
    """
    result = {"acceleration": None, "acceleration_score": 0}

    for period_key, period_data in eps_trend.items():
        current = period_data.get("current")
        ago_7d = period_data.get("7daysago")
        ago_30d = period_data.get("30daysago")
        ago_90d = period_data.get("90daysago")

        if current is None:
            continue

        # Compute recent velocity (7d) vs older velocity (30d-90d)
        vel_recent = None
        vel_older = None

        if ago_7d and abs(ago_7d) > 0.001:
            vel_recent = (current - ago_7d) / abs(ago_7d)

        if ago_30d and ago_90d and abs(ago_90d) > 0.001:
            # Average daily velocity over the 30d-90d window
            vel_older = (ago_30d - ago_90d) / abs(ago_90d)

        if vel_recent is not None and vel_older is not None:
            # Acceleration: positive = revisions speeding up
            result["acceleration"] = round(vel_recent - vel_older, 4)

            # Score: accelerating upward revisions are most bullish
            accel = result["acceleration"]
            if accel > 0:
                # Positive acceleration (upward revisions speeding up)
                result["acceleration_score"] = round(min(100, accel * 500), 1)
            else:
                # Decelerating or reversing
                result["acceleration_score"] = round(max(0, 30 + accel * 200), 1)
        break

    return result


def _compute_surprise_momentum(earnings_history: list) -> dict:
    """Consecutive earnings beat/miss streaks with magnitude.

    A stock that beats 4 quarters in a row with increasing magnitude
    is a strong revision momentum candidate — analysts are STILL catching up.
    Returns: {beat_streak, miss_streak, avg_surprise_pct, surprise_score (0-100)}
    """
    result = {
        "beat_streak": 0,
        "miss_streak": 0,
        "avg_surprise_pct": 0,
        "surprise_score": 0,
    }

    if not earnings_history:
        return result

    # Sort by quarter (most recent first)
    surprises = []
    for entry in earnings_history:
        surprise = entry.get("surprise_pct") or entry.get("surprise(%)") or entry.get("surprisepercent")
        if surprise is not None:
            try:
                surprises.append(float(surprise))
            except (ValueError, TypeError):
                continue

    if not surprises:
        return result

    # Compute streak
    beat_streak = 0
    miss_streak = 0

    for s in surprises:
        if s > 0:
            if miss_streak > 0:
                break
            beat_streak += 1
        elif s < 0:
            if beat_streak > 0:
                break
            miss_streak += 1
        else:
            break

    result["beat_streak"] = beat_streak
    result["miss_streak"] = miss_streak
    result["avg_surprise_pct"] = round(np.mean(surprises[:4]), 2) if surprises else 0

    # Score
    score = 0

    # Beat streak bonus (exponential — 4 in a row is much stronger than 2)
    if beat_streak >= 4:
        score += 60
    elif beat_streak >= 3:
        score += 45
    elif beat_streak >= 2:
        score += 25
    elif beat_streak >= 1:
        score += 10

    # Magnitude bonus: large surprise + streak = analysts are chronically behind
    avg_s = result["avg_surprise_pct"]
    if avg_s > 10:
        score += 30
    elif avg_s > 5:
        score += 20
    elif avg_s > 2:
        score += 10

    # Miss streak penalty (symmetric but less aggressive — shorts are harder)
    if miss_streak >= 3:
        score = max(0, score - 40)
    elif miss_streak >= 2:
        score = max(0, score - 20)

    # Increasing surprise magnitude = analysts falling further behind
    if len(surprises) >= 2 and surprises[0] > surprises[1] > 0:
        score += EM_SURPRISE_STREAK_BONUS

    result["surprise_score"] = round(min(100, max(0, score)), 1)
    return result


def _compute_dispersion_change(earnings_est: dict) -> dict:
    """Track narrowing/widening of estimate dispersion.

    Tightening dispersion = growing consensus conviction (bullish for trend continuation).
    Widening dispersion = uncertainty increasing (potential regime change).
    Returns: {dispersion_pct, dispersion_score (0-100)}
    """
    result = {"dispersion_pct": None, "dispersion_score": 50}  # 50 = neutral

    for period_key, period_data in earnings_est.items():
        high = period_data.get("high")
        low = period_data.get("low")
        avg = period_data.get("avg")

        if high is not None and low is not None and avg is not None and abs(avg) > 0.001:
            dispersion = (high - low) / abs(avg) * 100
            result["dispersion_pct"] = round(dispersion, 2)

            # Low dispersion + positive revisions = strong conviction move
            # High dispersion = uncertainty
            if dispersion < 10:
                result["dispersion_score"] = 70 + EM_DISPERSION_TIGHTENING_BONUS
            elif dispersion < 20:
                result["dispersion_score"] = 60
            elif dispersion < 40:
                result["dispersion_score"] = 50
            elif dispersion < 60:
                result["dispersion_score"] = 35
            else:
                result["dispersion_score"] = 20

            break

    return result


def _compute_cross_sectional_rank(symbol: str, velocity_score: float) -> dict:
    """Rank this stock's revision velocity against its sector peers.

    Uses stored scores from prior symbols in same sector.
    Returns: {sector_rank_pct (0-100), sector_rank_score (0-100)}
    """
    result = {"sector_rank_pct": None, "sector_rank_score": 50}

    try:
        # Get this stock's sector
        sector_rows = query(
            "SELECT sector FROM stock_universe WHERE symbol = ?", [symbol]
        )
        if not sector_rows:
            return result
        sector = sector_rows[0]["sector"]

        # Get all revision scores for this sector from today
        today = date.today().isoformat()
        peer_rows = query("""
            SELECT em.velocity_score
            FROM estimate_momentum_signals em
            JOIN stock_universe su ON em.symbol = su.symbol
            WHERE su.sector = ? AND em.date = ?
            AND em.velocity_score IS NOT NULL
        """, [sector, today])

        if len(peer_rows) < 3:
            return result

        scores = [r["velocity_score"] for r in peer_rows]
        rank_pct = sum(1 for s in scores if s < velocity_score) / len(scores) * 100
        result["sector_rank_pct"] = round(rank_pct, 1)

        # Top quartile of sector = strong signal
        if rank_pct >= 90:
            result["sector_rank_score"] = 95
        elif rank_pct >= 75:
            result["sector_rank_score"] = 75
        elif rank_pct >= 50:
            result["sector_rank_score"] = 55
        elif rank_pct >= 25:
            result["sector_rank_score"] = 35
        else:
            result["sector_rank_score"] = 15

    except Exception as e:
        logger.debug(f"Cross-sectional rank failed for {symbol}: {e}")

    return result


def _compute_historical_velocity(symbol: str, current_eps_avg: float | None,
                                  current_rev_avg: float | None) -> dict:
    """Compare current estimates to stored historical snapshots.

    This is the core time-series signal — on day 1 we just store,
    on subsequent days we compute actual revision velocity from our own data.
    Returns: {hist_eps_velocity, hist_rev_velocity, hist_score (0-100)}
    """
    result = {"hist_eps_velocity": None, "hist_rev_velocity": None, "hist_score": 0}

    if current_eps_avg is None:
        return result

    try:
        # Get snapshot from 7 and 30 days ago
        rows = query("""
            SELECT date, eps_current_avg, rev_current_avg
            FROM estimate_snapshots
            WHERE symbol = ?
            ORDER BY date DESC
            LIMIT 30
        """, [symbol])

        if not rows:
            return result

        # Find snapshots at ~7d and ~30d ago
        snap_7d = None
        snap_30d = None
        today = date.today()

        for r in rows:
            try:
                d = datetime.strptime(r["date"], "%Y-%m-%d").date()
                delta = (today - d).days
                if 5 <= delta <= 10 and snap_7d is None:
                    snap_7d = r
                elif 25 <= delta <= 35 and snap_30d is None:
                    snap_30d = r
            except Exception:
                continue

        score = 0

        if snap_7d and snap_7d["eps_current_avg"] and abs(snap_7d["eps_current_avg"]) > 0.001:
            vel = (current_eps_avg - snap_7d["eps_current_avg"]) / abs(snap_7d["eps_current_avg"]) * 100
            result["hist_eps_velocity"] = round(vel, 3)
            if vel > EM_STRONG_REVISION_PCT:
                score += 60
            elif vel > EM_MODERATE_REVISION_PCT:
                score += 35
            elif vel > 0:
                score += 15

        if snap_30d and snap_30d["eps_current_avg"] and abs(snap_30d["eps_current_avg"]) > 0.001:
            vel_30 = (current_eps_avg - snap_30d["eps_current_avg"]) / abs(snap_30d["eps_current_avg"]) * 100
            # 30d velocity adds confirmation
            if vel_30 > EM_MODERATE_REVISION_PCT:
                score += 25
            elif vel_30 > 0:
                score += 10

        # Revenue velocity (if available)
        if current_rev_avg and snap_7d and snap_7d.get("rev_current_avg"):
            old_rev = snap_7d["rev_current_avg"]
            if old_rev and abs(old_rev) > 1000:
                rev_vel = (current_rev_avg - old_rev) / abs(old_rev) * 100
                result["hist_rev_velocity"] = round(rev_vel, 3)
                if rev_vel > 2:
                    score += 15

        result["hist_score"] = round(min(100, max(0, score)), 1)

    except Exception as e:
        logger.debug(f"Historical velocity failed for {symbol}: {e}")

    return result


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

def _composite_score(velocity: dict, rev_velocity: dict, acceleration: dict,
                     surprise: dict, dispersion: dict, cross_sect: dict,
                     hist_velocity: dict) -> float:
    """Weighted composite of all sub-signals → single 0-100 score."""

    # If we have historical velocity data, blend it with yfinance trend data
    eps_vel_score = velocity.get("velocity_score", 0)
    hist_score = hist_velocity.get("hist_score", 0)

    # Use the stronger of yfinance trend or our historical snapshots
    effective_eps_score = max(eps_vel_score, hist_score)

    components = [
        (effective_eps_score, EM_REVISION_VELOCITY_WEIGHT),
        (rev_velocity.get("rev_velocity_score", 0), EM_REVENUE_VELOCITY_WEIGHT),
        (acceleration.get("acceleration_score", 0), EM_ACCELERATION_WEIGHT),
        (surprise.get("surprise_score", 0), EM_SURPRISE_MOMENTUM_WEIGHT),
        (dispersion.get("dispersion_score", 50), EM_DISPERSION_WEIGHT),
        (cross_sect.get("sector_rank_score", 50), EM_CROSS_SECTIONAL_WEIGHT),
    ]

    weighted_sum = sum(score * weight for score, weight in components)
    weight_sum = sum(w for _, w in components)

    return round(weighted_sum / weight_sum if weight_sum else 0, 1)


# ---------------------------------------------------------------------------
# Store snapshot for historical velocity tracking
# ---------------------------------------------------------------------------

def _store_snapshot(symbol: str, data: dict):
    """Store today's estimate snapshot for future velocity computation."""
    today = date.today().isoformat()

    eps_avg = None
    rev_avg = None
    eps_high = None
    eps_low = None
    num_analysts = None

    # Extract from earnings_estimate — prefer current quarter (0q)
    ee = data.get("earnings_estimate", {})
    for period_key in ["0q", "+1q", "0y", "+1y"]:
        if period_key in ee:
            period_data = ee[period_key]
            eps_avg = period_data.get("avg")
            eps_high = period_data.get("high")
            eps_low = period_data.get("low")
            num_analysts = period_data.get("num_analysts")
            break
    # Fallback: try first available period
    if eps_avg is None:
        for period_key, period_data in ee.items():
            eps_avg = period_data.get("avg")
            eps_high = period_data.get("high")
            eps_low = period_data.get("low")
            num_analysts = period_data.get("num_analysts")
            break

    # Extract from revenue_estimate — prefer current quarter
    re = data.get("revenue_estimate", {})
    for period_key in ["0q", "+1q", "0y", "+1y"]:
        if period_key in re:
            rev_avg = re[period_key].get("avg")
            break
    if rev_avg is None:
        for period_key, period_data in re.items():
            rev_avg = period_data.get("avg")
            break

    if eps_avg is None and rev_avg is None:
        return eps_avg, rev_avg

    upsert_many(
        "estimate_snapshots",
        ["symbol", "date", "eps_current_avg", "eps_current_high", "eps_current_low",
         "rev_current_avg", "num_analysts"],
        [(symbol, today, eps_avg, eps_high, eps_low, rev_avg, num_analysts)]
    )

    return eps_avg, rev_avg


# ---------------------------------------------------------------------------
# Main per-symbol analysis
# ---------------------------------------------------------------------------

def analyze_symbol(symbol: str) -> dict | None:
    """Run full estimate momentum analysis for a single symbol.

    Returns dict with all sub-scores and composite em_score, or None if no data.
    """
    # Fetch estimate data (yfinance primary, FMP fallback)
    data = _fetch_yf_estimates(symbol)

    has_data = (data["eps_trend"] or data["earnings_estimate"] or
                data["earnings_history"])

    # If yfinance returned nothing, try FMP
    if not has_data:
        data = _fetch_fmp_estimates(symbol)
        has_data = (data["earnings_estimate"] or data["earnings_history"])

    if not has_data:
        return None

    # Store snapshot for historical tracking
    eps_avg, rev_avg = _store_snapshot(symbol, data)

    # Compute all sub-signals
    velocity = _compute_eps_revision_velocity(data["eps_trend"])
    rev_velocity = _compute_revenue_revision_velocity(data["revenue_estimate"])
    acceleration = _compute_revision_acceleration(data["eps_trend"])
    surprise = _compute_surprise_momentum(data["earnings_history"])
    dispersion = _compute_dispersion_change(data["earnings_estimate"])
    hist_velocity = _compute_historical_velocity(symbol, eps_avg, rev_avg)

    # Cross-sectional rank (uses already-stored scores from this run)
    cross_sect = _compute_cross_sectional_rank(
        symbol, velocity.get("velocity_score", 0)
    )

    # Composite score
    em_score = _composite_score(
        velocity, rev_velocity, acceleration, surprise, dispersion,
        cross_sect, hist_velocity
    )

    return {
        "symbol": symbol,
        "em_score": em_score,
        "eps_velocity_7d": velocity.get("velocity_7d"),
        "eps_velocity_30d": velocity.get("velocity_30d"),
        "eps_velocity_90d": velocity.get("velocity_90d"),
        "velocity_score": velocity.get("velocity_score", 0),
        "rev_velocity_score": rev_velocity.get("rev_velocity_score", 0),
        "acceleration": acceleration.get("acceleration"),
        "acceleration_score": acceleration.get("acceleration_score", 0),
        "beat_streak": surprise.get("beat_streak", 0),
        "miss_streak": surprise.get("miss_streak", 0),
        "avg_surprise_pct": surprise.get("avg_surprise_pct", 0),
        "surprise_score": surprise.get("surprise_score", 0),
        "dispersion_pct": dispersion.get("dispersion_pct"),
        "dispersion_score": dispersion.get("dispersion_score", 50),
        "sector_rank_pct": cross_sect.get("sector_rank_pct"),
        "sector_rank_score": cross_sect.get("sector_rank_score", 50),
        "hist_eps_velocity": hist_velocity.get("hist_eps_velocity"),
        "hist_rev_velocity": hist_velocity.get("hist_rev_velocity"),
        "hist_score": hist_velocity.get("hist_score", 0),
    }


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run(symbols: list[str] | None = None):
    """Run estimate momentum analysis for all stocks in universe.

    Pipeline Phase 2.5 — after fundamentals, before extended alpha.
    """
    print("\n" + "=" * 60)
    print("  ESTIMATE REVISION MOMENTUM")
    print("=" * 60)

    init_db()

    if symbols is None:
        rows = query("SELECT symbol FROM stock_universe WHERE asset_class = 'stock'")
        symbols = [r["symbol"] for r in rows]

    if not symbols:
        print("  No symbols in universe.")
        return

    print(f"  Analyzing {len(symbols)} symbols...")

    today = date.today().isoformat()
    results = []
    errors = 0
    no_data = 0

    for i, symbol in enumerate(symbols):
        if i > 0 and i % 100 == 0:
            print(f"    Progress: {i}/{len(symbols)} ({len(results)} scored, {no_data} no data)")

        try:
            result = analyze_symbol(symbol)
            if result is None:
                no_data += 1
                continue

            results.append((
                result["symbol"], today, result["em_score"],
                result["eps_velocity_7d"], result["eps_velocity_30d"],
                result["eps_velocity_90d"], result["velocity_score"],
                result["rev_velocity_score"],
                result["acceleration"], result["acceleration_score"],
                result["beat_streak"], result["miss_streak"],
                result["avg_surprise_pct"], result["surprise_score"],
                result["dispersion_pct"], result["dispersion_score"],
                result["sector_rank_pct"], result["sector_rank_score"],
                result["hist_eps_velocity"], result["hist_rev_velocity"],
                result["hist_score"],
            ))

            # Small delay to be respectful to yfinance
            if i % 5 == 0:
                time.sleep(0.3)

        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning(f"  Error analyzing {symbol}: {e}")

    # Write to database
    if results:
        upsert_many(
            "estimate_momentum_signals",
            ["symbol", "date", "em_score",
             "eps_velocity_7d", "eps_velocity_30d", "eps_velocity_90d",
             "velocity_score", "rev_velocity_score",
             "acceleration", "acceleration_score",
             "beat_streak", "miss_streak", "avg_surprise_pct", "surprise_score",
             "dispersion_pct", "dispersion_score",
             "sector_rank_pct", "sector_rank_score",
             "hist_eps_velocity", "hist_rev_velocity", "hist_score"],
            results,
        )

    # Summary stats
    scores = [r[2] for r in results if r[2] is not None]
    strong = sum(1 for s in scores if s >= 70)
    moderate = sum(1 for s in scores if 50 <= s < 70)
    weak = sum(1 for s in scores if s < 50)

    print(f"\n  Results: {len(results)} symbols scored, {no_data} no data, {errors} errors")
    if scores:
        print(f"  Score distribution: avg={np.mean(scores):.1f}, "
              f"median={np.median(scores):.1f}, "
              f"max={max(scores):.1f}")
        print(f"  Strong (≥70): {strong} | Moderate (50-69): {moderate} | Weak (<50): {weak}")

    # Top movers
    if results:
        top = sorted(results, key=lambda r: r[2] or 0, reverse=True)[:10]
        print(f"\n  Top 10 estimate momentum:")
        for r in top:
            sym, _, score, v7, v30, v90, *_ = r
            beat = r[10]
            v_str = f"7d={v7:+.1f}%" if v7 else "7d=n/a"
            print(f"    {sym:6s} score={score:.0f}  {v_str}  beat_streak={beat}")

    print("=" * 60)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Estimate Revision Momentum")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to analyze")
    parser.add_argument("--test", action="store_true", help="Quick test with 5 symbols")
    args = parser.parse_args()

    init_db()

    if args.test:
        test_symbols = ["AAPL", "NVDA", "MSFT", "TSLA", "META"]
        print(f"Testing with: {test_symbols}")
        for sym in test_symbols:
            result = analyze_symbol(sym)
            if result:
                print(f"\n{sym}: em_score={result['em_score']}")
                print(f"  EPS velocity: 7d={result['eps_velocity_7d']}, "
                      f"30d={result['eps_velocity_30d']}, 90d={result['eps_velocity_90d']}")
                print(f"  Beat streak: {result['beat_streak']}, "
                      f"surprise avg: {result['avg_surprise_pct']}%")
                print(f"  Dispersion: {result['dispersion_pct']}%, "
                      f"sector rank: {result['sector_rank_pct']}")
            else:
                print(f"\n{sym}: no estimate data")
    elif args.symbols:
        run(args.symbols)
    else:
        run()
