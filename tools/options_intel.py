"""Options Intelligence — Layer 5 of the Pattern Match & Options module.

Fetches options chains and computes derivatives-based signals:
  - IV Rank / IV Percentile / IV Premium
  - Expected moves (ATM straddle)
  - Put/Call ratio analysis
  - Unusual options activity detection
  - Skew & term structure analysis
  - Dealer positioning (GEX, gamma flip, vanna, max pain, walls)

Cost-gated: only runs on symbols with pattern_scan_score >= threshold.
Primary data source: yfinance (free). FMP fallback for failures.
"""

import logging
import math
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from tools.db import query_df
from tools.config import (
    OPTIONS_YFINANCE_DELAY,
    OPTIONS_MIN_OI,
    OPTIONS_MIN_VOLUME,
    OPTIONS_UNUSUAL_VOL_OI_MULT,
    OPTIONS_UNUSUAL_MIN_NOTIONAL,
    OPTIONS_SKEW_EXTREME_ZSCORE,
    OPTIONS_TERM_STRUCTURE_STRESS,
    OPTIONS_COMPOSITE_WEIGHTS,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# OPTIONS CHAIN FETCHING
# ═══════════════════════════════════════════════════════════════════════════

def fetch_options_chain(symbol: str) -> dict | None:
    """Fetch options chain via yfinance.

    Returns dict with expirations and chain data, or None on failure.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations:
            return None

        # Get nearest 2-3 expirations (near-term focus)
        target_exps = expirations[:min(3, len(expirations))]

        chains = {}
        for exp in target_exps:
            try:
                chain = ticker.option_chain(exp)
                calls = chain.calls
                puts = chain.puts

                # Filter low-liquidity strikes
                calls = calls[(calls["openInterest"] >= OPTIONS_MIN_OI) |
                              (calls["volume"] >= OPTIONS_MIN_VOLUME)].copy()
                puts = puts[(puts["openInterest"] >= OPTIONS_MIN_OI) |
                            (puts["volume"] >= OPTIONS_MIN_VOLUME)].copy()

                if calls.empty and puts.empty:
                    continue

                chains[exp] = {"calls": calls, "puts": puts}
            except Exception:
                continue

        if not chains:
            return None

        # Get current price
        info = ticker.fast_info
        current_price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        if not current_price:
            hist = ticker.history(period="1d")
            current_price = float(hist["Close"].iloc[-1]) if not hist.empty else None

        return {
            "symbol": symbol,
            "current_price": current_price,
            "expirations": list(chains.keys()),
            "chains": chains,
        }

    except Exception as e:
        logger.warning(f"Options fetch failed for {symbol}: {e}")
        return None


def _dte(expiry_str: str) -> int:
    """Days to expiration from expiry string (YYYY-MM-DD)."""
    try:
        exp_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        return max(1, (exp_date - date.today()).days)
    except Exception:
        return 30


def _nearest_expiry(chain_data: dict, target_dte: int = 30) -> tuple[str, dict] | None:
    """Get the expiration closest to target_dte (default 30 days) for meaningful IV."""
    if not chain_data or not chain_data.get("chains"):
        return None
    expirations = chain_data.get("expirations", [])
    if not expirations:
        return None
    # Pick expiry closest to target_dte
    best_exp = min(expirations, key=lambda e: abs(_dte(e) - target_dte))
    return best_exp, chain_data["chains"][best_exp]


# ═══════════════════════════════════════════════════════════════════════════
# IV RANK & IV PERCENTILE
# ═══════════════════════════════════════════════════════════════════════════

def compute_iv_metrics(chain_data: dict) -> dict:
    """Compute IV rank, percentile, and premium vs realized vol."""
    result = {
        "atm_iv": None, "hv_20d": None, "iv_premium": None,
        "iv_rank": None, "iv_percentile": None, "iv_score": 0,
    }

    if not chain_data or not chain_data.get("current_price"):
        return result

    price = chain_data["current_price"]
    nearest = _nearest_expiry(chain_data)
    if not nearest:
        return result

    exp, data = nearest
    calls, puts = data["calls"], data["puts"]

    # Find ATM strike (closest to current price)
    if not calls.empty and "impliedVolatility" in calls.columns:
        calls_sorted = calls.copy()
        calls_sorted["dist"] = (calls_sorted["strike"] - price).abs()
        atm_call = calls_sorted.loc[calls_sorted["dist"].idxmin()]
        atm_iv_call = atm_call.get("impliedVolatility", 0)
    else:
        atm_iv_call = 0

    if not puts.empty and "impliedVolatility" in puts.columns:
        puts_sorted = puts.copy()
        puts_sorted["dist"] = (puts_sorted["strike"] - price).abs()
        atm_put = puts_sorted.loc[puts_sorted["dist"].idxmin()]
        atm_iv_put = atm_put.get("impliedVolatility", 0)
    else:
        atm_iv_put = 0

    # ATM IV = average of call and put
    atm_iv = (atm_iv_call + atm_iv_put) / 2 if atm_iv_call and atm_iv_put else max(atm_iv_call, atm_iv_put)
    if not atm_iv or atm_iv <= 0:
        return result

    result["atm_iv"] = round(atm_iv, 4)

    # Historical vol for comparison (use price_data)
    hv_df = query_df("""
        SELECT close FROM price_data WHERE symbol = ?
        AND close IS NOT NULL ORDER BY date DESC LIMIT 252
    """, [chain_data["symbol"]])

    if len(hv_df) >= 20:
        log_rets = np.log(hv_df["close"] / hv_df["close"].shift(1)).dropna()
        hv20 = float(log_rets.iloc[:20].std() * np.sqrt(252))
        result["hv_20d"] = round(hv20, 4)
        result["iv_premium"] = round(atm_iv - hv20, 4)

        # IV Rank using HV as proxy for historical IV
        hv_series = log_rets.rolling(20).std() * np.sqrt(252)
        hv_series = hv_series.dropna()
        if len(hv_series) > 20:
            hv_min = hv_series.min()
            hv_max = hv_series.max()
            if hv_max > hv_min:
                result["iv_rank"] = round((atm_iv - hv_min) / (hv_max - hv_min) * 100, 1)
            result["iv_percentile"] = round(float(np.sum(hv_series < atm_iv) / len(hv_series) * 100), 1)

    # IV Score
    iv_rank = result.get("iv_rank", 50) or 50
    iv_premium = result.get("iv_premium", 0) or 0

    if iv_rank > 80 and iv_premium > 0.05:
        # Very high IV = sell premium opportunity OR short-vol crowding danger
        result["iv_score"] = 75
    elif iv_rank < 20:
        # Very low IV = buy options (cheap protection)
        result["iv_score"] = 80
    elif 40 <= iv_rank <= 60:
        result["iv_score"] = 50
    else:
        result["iv_score"] = 50 + (iv_rank - 50) * 0.3

    result["iv_score"] = round(max(0, min(100, result["iv_score"])), 1)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# EXPECTED MOVE
# ═══════════════════════════════════════════════════════════════════════════

def compute_expected_move(chain_data: dict) -> dict:
    """Derive expected move from ATM straddle pricing."""
    result = {
        "expected_move_pct": None, "straddle_cost": None,
        "expected_move_1sd": None, "dte": None,
    }

    if not chain_data or not chain_data.get("current_price"):
        return result

    price = chain_data["current_price"]
    nearest = _nearest_expiry(chain_data, target_dte=7)  # Near-term for expected move
    if not nearest:
        return result

    exp, data = nearest
    calls, puts = data["calls"], data["puts"]
    dte = _dte(exp)

    # Find ATM straddle
    if calls.empty or puts.empty:
        return result

    # ATM call
    calls_s = calls.copy()
    calls_s["dist"] = (calls_s["strike"] - price).abs()
    atm_call = calls_s.loc[calls_s["dist"].idxmin()]

    # ATM put
    puts_s = puts.copy()
    puts_s["dist"] = (puts_s["strike"] - price).abs()
    atm_put = puts_s.loc[puts_s["dist"].idxmin()]

    # Straddle cost = mid of call + mid of put
    call_mid = (atm_call.get("bid", 0) + atm_call.get("ask", 0)) / 2
    put_mid = (atm_put.get("bid", 0) + atm_put.get("ask", 0)) / 2

    if call_mid <= 0 and put_mid <= 0:
        # Fallback to last price
        call_mid = atm_call.get("lastPrice", 0)
        put_mid = atm_put.get("lastPrice", 0)

    straddle = call_mid + put_mid
    if straddle <= 0:
        return result

    expected_move_pct = straddle / price * 100
    result["straddle_cost"] = round(straddle, 2)
    result["expected_move_pct"] = round(expected_move_pct, 2)
    result["expected_move_1sd"] = round(straddle, 2)
    result["dte"] = dte

    return result


# ═══════════════════════════════════════════════════════════════════════════
# PUT/CALL RATIO ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def compute_put_call_ratios(chain_data: dict) -> dict:
    """Volume and OI put/call ratios with contrarian scoring."""
    result = {
        "volume_pc_ratio": None, "oi_pc_ratio": None,
        "pc_signal": "neutral", "pc_score": 50,
    }

    if not chain_data:
        return result

    total_call_vol = 0
    total_put_vol = 0
    total_call_oi = 0
    total_put_oi = 0

    for exp, data in chain_data.get("chains", {}).items():
        calls, puts = data["calls"], data["puts"]
        total_call_vol += calls["volume"].sum() if "volume" in calls.columns else 0
        total_put_vol += puts["volume"].sum() if "volume" in puts.columns else 0
        total_call_oi += calls["openInterest"].sum() if "openInterest" in calls.columns else 0
        total_put_oi += puts["openInterest"].sum() if "openInterest" in puts.columns else 0

    if total_call_vol > 0:
        result["volume_pc_ratio"] = round(total_put_vol / total_call_vol, 3)
    if total_call_oi > 0:
        result["oi_pc_ratio"] = round(total_put_oi / total_call_oi, 3)

    # Contrarian scoring
    vpc = result["volume_pc_ratio"] or 0.7
    if vpc > 1.5:
        result["pc_signal"] = "extreme_bearish"
        result["pc_score"] = 80  # Contrarian bullish
    elif vpc > 1.0:
        result["pc_signal"] = "bearish"
        result["pc_score"] = 65
    elif vpc < 0.4:
        result["pc_signal"] = "extreme_bullish"
        result["pc_score"] = 20  # Contrarian bearish (complacency)
    elif vpc < 0.6:
        result["pc_signal"] = "bullish"
        result["pc_score"] = 35
    else:
        result["pc_signal"] = "neutral"
        result["pc_score"] = 50

    return result


# ═══════════════════════════════════════════════════════════════════════════
# UNUSUAL OPTIONS ACTIVITY
# ═══════════════════════════════════════════════════════════════════════════

def detect_unusual_activity(chain_data: dict) -> list[dict]:
    """Flag unusual options activity that may signal informed trading."""
    if not chain_data or not chain_data.get("current_price"):
        return []

    price = chain_data["current_price"]
    unusual = []

    for exp, data in chain_data.get("chains", {}).items():
        dte = _dte(exp)
        for opt_type, df in [("call", data["calls"]), ("put", data["puts"])]:
            if df.empty:
                continue

            for _, row in df.iterrows():
                vol = row.get("volume", 0) or 0
                oi = row.get("openInterest", 0) or 0
                strike = row.get("strike", 0)
                last_price = row.get("lastPrice", 0) or 0

                flags = []

                # Volume > 3x OI
                if oi > 0 and vol > OPTIONS_UNUSUAL_VOL_OI_MULT * oi:
                    flags.append("volume_surge")

                # Large notional
                notional = vol * last_price * 100  # 100 shares per contract
                if notional >= OPTIONS_UNUSUAL_MIN_NOTIONAL:
                    flags.append("size")

                # Short-dated OTM put surge (forced liquidation precursor)
                if opt_type == "put" and dte <= 14 and strike < price * 0.95 and vol > 500:
                    flags.append("short_dated_otm_put")

                if flags:
                    # Direction bias
                    if opt_type == "call":
                        bias = "bullish"
                    elif opt_type == "put":
                        bias = "bearish"
                    else:
                        bias = "neutral"

                    unusual.append({
                        "strike": float(strike),
                        "expiry": exp,
                        "type": opt_type,
                        "volume": int(vol),
                        "oi": int(oi),
                        "vol_oi_ratio": round(vol / max(oi, 1), 1),
                        "notional": round(notional, 0),
                        "flags": flags,
                        "direction_bias": bias,
                    })

    # Sort by notional value
    unusual.sort(key=lambda x: x["notional"], reverse=True)
    return unusual[:20]  # Top 20 most significant


def _unusual_activity_score(unusual: list[dict]) -> float:
    """Convert unusual activity list to 0-100 score."""
    if not unusual:
        return 40  # No unusual = slightly below neutral (no edge from flow)

    # Count directional bias
    bullish = sum(1 for u in unusual if u["direction_bias"] == "bullish")
    bearish = sum(1 for u in unusual if u["direction_bias"] == "bearish")

    # Intensity = total notional / $10M benchmark
    total_notional = sum(u["notional"] for u in unusual)
    intensity = min(1.0, total_notional / 10_000_000)

    # Net direction
    if bullish > bearish * 2:
        base = 75  # Strongly bullish flow
    elif bearish > bullish * 2:
        base = 25  # Strongly bearish flow
    elif bullish > bearish:
        base = 65
    elif bearish > bullish:
        base = 35
    else:
        base = 50

    # Scale by intensity
    score = 50 + (base - 50) * intensity

    # Bonus for short-dated OTM put surge (red flag)
    if any("short_dated_otm_put" in u.get("flags", []) for u in unusual):
        score = max(score - 15, 0)  # Major bearish signal

    return round(max(0, min(100, score)), 1)


# ═══════════════════════════════════════════════════════════════════════════
# SKEW & TERM STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

def compute_skew(chain_data: dict) -> dict:
    """Volatility skew and term structure analysis."""
    result = {
        "skew_25d": None, "skew_direction": "balanced",
        "term_structure_signal": "normal", "skew_score": 50,
    }

    if not chain_data or not chain_data.get("current_price"):
        return result

    price = chain_data["current_price"]
    nearest = _nearest_expiry(chain_data)
    if not nearest:
        return result

    exp, data = nearest
    calls, puts = data["calls"], data["puts"]

    # 25-delta approximation: ~5% OTM
    otm_put_strike = price * 0.95
    otm_call_strike = price * 1.05

    def _iv_near_strike(df, target_strike):
        if df.empty or "impliedVolatility" not in df.columns:
            return None
        df_s = df.copy()
        df_s["dist"] = (df_s["strike"] - target_strike).abs()
        nearest_row = df_s.loc[df_s["dist"].idxmin()]
        iv = nearest_row.get("impliedVolatility", 0)
        return iv if iv and iv > 0 else None

    put_iv = _iv_near_strike(puts, otm_put_strike)
    call_iv = _iv_near_strike(calls, otm_call_strike)

    if put_iv and call_iv:
        skew = put_iv - call_iv
        result["skew_25d"] = round(skew, 4)

        if skew > 0.05:
            result["skew_direction"] = "put_premium"
        elif skew < -0.05:
            result["skew_direction"] = "call_premium"
        else:
            result["skew_direction"] = "balanced"

    # Term structure: compare near-term vs far-term IV
    if len(chain_data.get("expirations", [])) >= 2:
        exp_near = chain_data["expirations"][0]
        exp_far = chain_data["expirations"][-1]
        near_data = chain_data["chains"].get(exp_near)
        far_data = chain_data["chains"].get(exp_far)

        if near_data and far_data:
            near_atm_iv = _iv_near_strike(near_data["calls"], price) or _iv_near_strike(near_data["puts"], price)
            far_atm_iv = _iv_near_strike(far_data["calls"], price) or _iv_near_strike(far_data["puts"], price)

            if near_atm_iv and far_atm_iv and far_atm_iv > 0:
                ratio = near_atm_iv / far_atm_iv
                if ratio > OPTIONS_TERM_STRUCTURE_STRESS:
                    result["term_structure_signal"] = "backwardation"  # Near-term stress
                elif ratio < 0.85:
                    result["term_structure_signal"] = "contango"  # Normal, calm
                else:
                    result["term_structure_signal"] = "normal"

    # Skew score
    skew_val = result.get("skew_25d", 0) or 0
    if result["skew_direction"] == "put_premium" and abs(skew_val) > 0.08:
        result["skew_score"] = 75  # Extreme put skew = contrarian bullish
    elif result["skew_direction"] == "call_premium":
        result["skew_score"] = 30  # Call premium = euphoria risk
    else:
        result["skew_score"] = 50

    # Term structure adjustment
    if result["term_structure_signal"] == "backwardation":
        result["skew_score"] = max(result["skew_score"] - 15, 0)  # Near-term stress

    return result


# ═══════════════════════════════════════════════════════════════════════════
# DEALER POSITIONING (GEX, GAMMA FLIP, VANNA, MAX PAIN, WALLS)
# ═══════════════════════════════════════════════════════════════════════════

def estimate_dealer_exposure(chain_data: dict) -> dict:
    """Estimate dealer gamma/vanna exposure and key mechanical levels.

    Core insight: dealers are net short options to retail/institutional buyers.
    When they hedge, their mechanical flows create reflexive price dynamics.
    """
    result = {
        "net_gex": None, "gamma_flip_level": None,
        "vanna_exposure": None, "max_pain": None,
        "put_wall": None, "call_wall": None,
        "dealer_regime": "neutral", "dealer_score": 50,
    }

    if not chain_data or not chain_data.get("current_price"):
        return result

    price = chain_data["current_price"]
    nearest = _nearest_expiry(chain_data)
    if not nearest:
        return result

    exp, data = nearest
    calls, puts = data["calls"], data["puts"]

    # --- Net Gamma Exposure (GEX) ---
    # Assumption: dealers are net short calls, net long puts (retail buys both)
    # GEX_per_strike = OI × gamma × 100 × spot_price
    # Calls contribute POSITIVE gamma (dealers short → need to buy dips/sell rallies → stabilizing)
    # Wait — dealers SHORT calls means they have NEGATIVE gamma on calls
    # Dealers SHORT puts means they have POSITIVE gamma on puts (they sold puts)
    # Net dealer gamma = -sum(call_OI * call_gamma) + sum(put_OI * put_gamma) * spot * 100

    total_gex = 0
    gex_by_strike = {}

    for _, row in calls.iterrows():
        strike = row.get("strike", 0)
        oi = row.get("openInterest", 0) or 0
        gamma = row.get("gamma", 0) or 0  # May not be available from yfinance
        if gamma > 0 and oi > 0:
            # Dealers short calls → negative gamma contribution
            gex = -oi * gamma * 100 * price
            total_gex += gex
            gex_by_strike[strike] = gex_by_strike.get(strike, 0) + gex

    for _, row in puts.iterrows():
        strike = row.get("strike", 0)
        oi = row.get("openInterest", 0) or 0
        gamma = row.get("gamma", 0) or 0
        if gamma > 0 and oi > 0:
            # Dealers short puts → positive gamma contribution
            gex = oi * gamma * 100 * price
            total_gex += gex
            gex_by_strike[strike] = gex_by_strike.get(strike, 0) + gex

    result["net_gex"] = round(total_gex, 0)

    # --- Gamma Flip Level ---
    # Find the strike where cumulative GEX flips sign
    if gex_by_strike:
        sorted_strikes = sorted(gex_by_strike.keys())
        cumulative = 0
        flip_level = None
        for s in sorted_strikes:
            prev_cum = cumulative
            cumulative += gex_by_strike[s]
            if prev_cum <= 0 < cumulative or prev_cum >= 0 > cumulative:
                flip_level = s
                break
        result["gamma_flip_level"] = float(flip_level) if flip_level else None

    # --- Vanna Exposure ---
    # Vanna = dDelta/dVol. When vol rises, dealer delta shifts → forced rehedging
    # Approximate: sum(OI * vega) as proxy for vol-sensitivity
    vanna_total = 0
    for _, row in calls.iterrows():
        vega = row.get("vega", 0) or 0
        oi = row.get("openInterest", 0) or 0
        vanna_total += oi * vega * 100

    for _, row in puts.iterrows():
        vega = row.get("vega", 0) or 0
        oi = row.get("openInterest", 0) or 0
        vanna_total -= oi * vega * 100  # Puts contribute opposite sign

    result["vanna_exposure"] = round(vanna_total, 0)

    # --- Max Pain ---
    # Strike where most options expire worthless
    strikes = sorted(set(
        list(calls["strike"].unique()) + list(puts["strike"].unique())
    ))
    if strikes:
        min_pain = float("inf")
        max_pain_strike = strikes[0]
        for k in strikes:
            # Total intrinsic value at expiry if spot = k
            call_pain = sum(
                max(0, k - row["strike"]) * (row.get("openInterest", 0) or 0)
                for _, row in calls.iterrows()
            )
            put_pain = sum(
                max(0, row["strike"] - k) * (row.get("openInterest", 0) or 0)
                for _, row in puts.iterrows()
            )
            total_pain = call_pain + put_pain
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = k

        result["max_pain"] = float(max_pain_strike)

    # --- Put Wall / Call Wall (highest OI strikes) ---
    if not calls.empty and "openInterest" in calls.columns:
        result["call_wall"] = float(calls.loc[calls["openInterest"].idxmax()]["strike"])
    if not puts.empty and "openInterest" in puts.columns:
        result["put_wall"] = float(puts.loc[puts["openInterest"].idxmax()]["strike"])

    # --- Dealer Regime Classification ---
    if total_gex > 0:
        result["dealer_regime"] = "pinning"   # Positive GEX → dealers stabilize price
    elif total_gex < 0:
        result["dealer_regime"] = "amplifying"  # Negative GEX → dealers amplify moves
    else:
        result["dealer_regime"] = "neutral"

    # --- Dealer Score ---
    # Negative GEX + vol compression = explosive setup (highest score)
    # Positive GEX + near max pain = pinned (low score, range-bound)
    if total_gex < 0:
        result["dealer_score"] = 75  # Amplifying = high conviction directional
    elif total_gex > 0 and result["max_pain"]:
        dist_to_max_pain = abs(price - result["max_pain"]) / price
        if dist_to_max_pain < 0.02:
            result["dealer_score"] = 30  # Pinned near max pain
        else:
            result["dealer_score"] = 50
    else:
        result["dealer_score"] = 50

    result["dealer_score"] = round(result["dealer_score"], 1)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# OPTIONS COMPOSITE SCORE
# ═══════════════════════════════════════════════════════════════════════════

def compute_options_composite(iv: dict, expected_move: dict, pc: dict,
                              unusual: list[dict], skew: dict, dealer: dict) -> float:
    """Blend all options sub-scores into a 0-100 composite."""
    w = OPTIONS_COMPOSITE_WEIGHTS

    iv_score = iv.get("iv_score", 50)
    pc_score = pc.get("pc_score", 50)
    unusual_score = _unusual_activity_score(unusual)
    skew_score = skew.get("skew_score", 50)
    dealer_score = dealer.get("dealer_score", 50)

    composite = (
        w["iv_metrics"] * iv_score
        + w["pc_ratios"] * pc_score
        + w["unusual_activity"] * unusual_score
        + w["skew"] * skew_score
        + w["dealer_exposure"] * dealer_score
    )

    return round(max(0, min(100, composite)), 1)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def analyze_symbol(symbol: str) -> dict | None:
    """Run full options analysis on a single symbol.

    Returns dict ready for DB insertion, or None on failure.
    """
    chain = fetch_options_chain(symbol)
    if not chain:
        return None

    iv = compute_iv_metrics(chain)
    em = compute_expected_move(chain)
    pc = compute_put_call_ratios(chain)
    unusual = detect_unusual_activity(chain)
    skew = compute_skew(chain)
    dealer = estimate_dealer_exposure(chain)

    options_score = compute_options_composite(iv, em, pc, unusual, skew, dealer)

    # Determine overall direction bias from unusual activity
    if unusual:
        bullish_count = sum(1 for u in unusual if u["direction_bias"] == "bullish")
        bearish_count = sum(1 for u in unusual if u["direction_bias"] == "bearish")
        if bullish_count > bearish_count * 1.5:
            direction_bias = "bullish"
        elif bearish_count > bullish_count * 1.5:
            direction_bias = "bearish"
        else:
            direction_bias = "mixed"
    else:
        direction_bias = None

    return {
        "symbol": symbol,
        "date": date.today().isoformat(),
        # IV
        "atm_iv": iv.get("atm_iv"),
        "hv_20d": iv.get("hv_20d"),
        "iv_premium": iv.get("iv_premium"),
        "iv_rank": iv.get("iv_rank"),
        "iv_percentile": iv.get("iv_percentile"),
        # Expected Move
        "expected_move_pct": em.get("expected_move_pct"),
        "straddle_cost": em.get("straddle_cost"),
        # Put/Call
        "volume_pc_ratio": pc.get("volume_pc_ratio"),
        "oi_pc_ratio": pc.get("oi_pc_ratio"),
        "pc_signal": pc.get("pc_signal"),
        # Unusual
        "unusual_activity_count": len(unusual),
        "unusual_activity": json.dumps(unusual[:10]) if unusual else None,
        "unusual_direction_bias": direction_bias,
        # Skew
        "skew_25d": skew.get("skew_25d"),
        "skew_direction": skew.get("skew_direction"),
        "term_structure_signal": skew.get("term_structure_signal"),
        # Dealer
        "net_gex": dealer.get("net_gex"),
        "gamma_flip_level": dealer.get("gamma_flip_level"),
        "vanna_exposure": dealer.get("vanna_exposure"),
        "max_pain": dealer.get("max_pain"),
        "put_wall": dealer.get("put_wall"),
        "call_wall": dealer.get("call_wall"),
        "dealer_regime": dealer.get("dealer_regime"),
        # Composite
        "options_score": options_score,
    }


# Need json import for unusual_activity serialization
import json


def analyze_batch(symbols: list[str], delay: float = OPTIONS_YFINANCE_DELAY) -> list[dict]:
    """Analyze options for a batch of symbols with rate limiting."""
    results = []
    for i, sym in enumerate(symbols):
        if (i + 1) % 10 == 0:
            print(f"    Options: {i + 1}/{len(symbols)} analyzed...")
        try:
            result = analyze_symbol(sym)
            if result:
                results.append(result)
        except Exception as e:
            logger.warning(f"Options analysis failed for {sym}: {e}")
        time.sleep(delay)

    return results
