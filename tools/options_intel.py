"""Options Intelligence — IV, expected moves, put/call, unusual activity, skew, dealer positioning."""

import json, logging, math, time
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd
from tools.db import query_df
from tools.config import (
    OPTIONS_YFINANCE_DELAY, OPTIONS_MIN_OI, OPTIONS_MIN_VOLUME,
    OPTIONS_UNUSUAL_VOL_OI_MULT, OPTIONS_UNUSUAL_MIN_NOTIONAL,
    OPTIONS_SKEW_EXTREME_ZSCORE, OPTIONS_TERM_STRUCTURE_STRESS,
    OPTIONS_COMPOSITE_WEIGHTS,
)

logger = logging.getLogger(__name__)


def fetch_options_chain(symbol: str) -> dict | None:
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        expirations = ticker.options
        if not expirations: return None
        target_exps = expirations[:min(3, len(expirations))]
        chains = {}
        for exp in target_exps:
            try:
                chain = ticker.option_chain(exp)
                calls = chain.calls[(chain.calls["openInterest"] >= OPTIONS_MIN_OI) | (chain.calls["volume"] >= OPTIONS_MIN_VOLUME)].copy()
                puts = chain.puts[(chain.puts["openInterest"] >= OPTIONS_MIN_OI) | (chain.puts["volume"] >= OPTIONS_MIN_VOLUME)].copy()
                if not calls.empty or not puts.empty: chains[exp] = {"calls": calls, "puts": puts}
            except Exception: continue
        if not chains: return None
        info = ticker.fast_info
        current_price = getattr(info, "last_price", None) or getattr(info, "previous_close", None)
        if not current_price:
            hist = ticker.history(period="1d")
            current_price = float(hist["Close"].iloc[-1]) if not hist.empty else None
        return {"symbol": symbol, "current_price": current_price, "expirations": list(chains.keys()), "chains": chains}
    except Exception as e:
        logger.warning(f"Options fetch failed for {symbol}: {e}"); return None


def _dte(expiry_str: str) -> int:
    try: return max(1, (datetime.strptime(expiry_str, "%Y-%m-%d").date() - date.today()).days)
    except Exception: return 30


def _nearest_expiry(chain_data: dict, target_dte: int = 30) -> tuple[str, dict] | None:
    if not chain_data or not chain_data.get("chains"): return None
    exps = chain_data.get("expirations", [])
    if not exps: return None
    best = min(exps, key=lambda e: abs(_dte(e) - target_dte))
    return best, chain_data["chains"][best]


def _atm_strike(df, price):
    if df.empty or "impliedVolatility" not in df.columns: return 0
    s = df.copy(); s["dist"] = (s["strike"] - price).abs()
    return s.loc[s["dist"].idxmin()].get("impliedVolatility", 0)


def compute_iv_metrics(chain_data: dict) -> dict:
    result = {"atm_iv": None, "hv_20d": None, "iv_premium": None, "iv_rank": None, "iv_percentile": None, "iv_score": 0}
    if not chain_data or not chain_data.get("current_price"): return result
    price = chain_data["current_price"]
    nearest = _nearest_expiry(chain_data)
    if not nearest: return result
    exp, data = nearest
    atm_iv_call = _atm_strike(data["calls"], price)
    atm_iv_put = _atm_strike(data["puts"], price)
    atm_iv = (atm_iv_call + atm_iv_put) / 2 if atm_iv_call and atm_iv_put else max(atm_iv_call, atm_iv_put)
    if not atm_iv or atm_iv <= 0: return result
    result["atm_iv"] = round(atm_iv, 4)
    hv_df = query_df("SELECT close FROM price_data WHERE symbol = ? AND close IS NOT NULL ORDER BY date DESC LIMIT 252", [chain_data["symbol"]])
    if len(hv_df) >= 20:
        log_rets = np.log(hv_df["close"] / hv_df["close"].shift(1)).dropna()
        hv20 = float(log_rets.iloc[:20].std() * np.sqrt(252))
        result["hv_20d"] = round(hv20, 4)
        result["iv_premium"] = round(atm_iv - hv20, 4)
        hv_series = log_rets.rolling(20).std() * np.sqrt(252)
        hv_series = hv_series.dropna()
        if len(hv_series) > 20:
            hv_min, hv_max = hv_series.min(), hv_series.max()
            if hv_max > hv_min: result["iv_rank"] = round((atm_iv - hv_min) / (hv_max - hv_min) * 100, 1)
            result["iv_percentile"] = round(float(np.sum(hv_series < atm_iv) / len(hv_series) * 100), 1)
    iv_rank = result.get("iv_rank", 50) or 50
    iv_prem = result.get("iv_premium", 0) or 0
    if iv_rank > 80 and iv_prem > 0.05: result["iv_score"] = 75
    elif iv_rank < 20: result["iv_score"] = 80
    elif 40 <= iv_rank <= 60: result["iv_score"] = 50
    else: result["iv_score"] = 50 + (iv_rank - 50) * 0.3
    result["iv_score"] = round(max(0, min(100, result["iv_score"])), 1)
    return result


def compute_expected_move(chain_data: dict) -> dict:
    result = {"expected_move_pct": None, "straddle_cost": None, "expected_move_1sd": None, "dte": None}
    if not chain_data or not chain_data.get("current_price"): return result
    price = chain_data["current_price"]
    nearest = _nearest_expiry(chain_data, target_dte=7)
    if not nearest: return result
    exp, data = nearest
    calls, puts = data["calls"], data["puts"]
    if calls.empty or puts.empty: return result
    calls_s = calls.copy(); calls_s["dist"] = (calls_s["strike"] - price).abs()
    atm_call = calls_s.loc[calls_s["dist"].idxmin()]
    puts_s = puts.copy(); puts_s["dist"] = (puts_s["strike"] - price).abs()
    atm_put = puts_s.loc[puts_s["dist"].idxmin()]
    call_mid = (atm_call.get("bid", 0) + atm_call.get("ask", 0)) / 2
    put_mid = (atm_put.get("bid", 0) + atm_put.get("ask", 0)) / 2
    if call_mid <= 0 and put_mid <= 0:
        call_mid, put_mid = atm_call.get("lastPrice", 0), atm_put.get("lastPrice", 0)
    straddle = call_mid + put_mid
    if straddle <= 0: return result
    result["straddle_cost"] = round(straddle, 2)
    result["expected_move_pct"] = round(straddle / price * 100, 2)
    result["expected_move_1sd"] = round(straddle, 2)
    result["dte"] = _dte(exp)
    return result


def compute_put_call_ratios(chain_data: dict) -> dict:
    result = {"volume_pc_ratio": None, "oi_pc_ratio": None, "pc_signal": "neutral", "pc_score": 50}
    if not chain_data: return result
    tcv = tpv = tco = tpo = 0
    for exp, data in chain_data.get("chains", {}).items():
        c, p = data["calls"], data["puts"]
        tcv += c["volume"].sum() if "volume" in c.columns else 0
        tpv += p["volume"].sum() if "volume" in p.columns else 0
        tco += c["openInterest"].sum() if "openInterest" in c.columns else 0
        tpo += p["openInterest"].sum() if "openInterest" in p.columns else 0
    if tcv > 0: result["volume_pc_ratio"] = round(tpv / tcv, 3)
    if tco > 0: result["oi_pc_ratio"] = round(tpo / tco, 3)
    vpc = result["volume_pc_ratio"] or 0.7
    if vpc > 1.5: result["pc_signal"], result["pc_score"] = "extreme_bearish", 80
    elif vpc > 1.0: result["pc_signal"], result["pc_score"] = "bearish", 65
    elif vpc < 0.4: result["pc_signal"], result["pc_score"] = "extreme_bullish", 20
    elif vpc < 0.6: result["pc_signal"], result["pc_score"] = "bullish", 35
    return result


def detect_unusual_activity(chain_data: dict) -> list[dict]:
    if not chain_data or not chain_data.get("current_price"): return []
    price = chain_data["current_price"]
    unusual = []
    for exp, data in chain_data.get("chains", {}).items():
        dte = _dte(exp)
        for opt_type, df in [("call", data["calls"]), ("put", data["puts"])]:
            if df.empty: continue
            for _, row in df.iterrows():
                vol = row.get("volume", 0) or 0
                oi = row.get("openInterest", 0) or 0
                strike = row.get("strike", 0)
                last_price = row.get("lastPrice", 0) or 0
                flags = []
                if oi > 0 and vol > OPTIONS_UNUSUAL_VOL_OI_MULT * oi: flags.append("volume_surge")
                notional = vol * last_price * 100
                if notional >= OPTIONS_UNUSUAL_MIN_NOTIONAL: flags.append("size")
                if opt_type == "put" and dte <= 14 and strike < price * 0.95 and vol > 500: flags.append("short_dated_otm_put")
                if flags:
                    unusual.append({"strike": float(strike), "expiry": exp, "type": opt_type,
                        "volume": int(vol), "oi": int(oi), "vol_oi_ratio": round(vol / max(oi, 1), 1),
                        "notional": round(notional, 0), "flags": flags,
                        "direction_bias": "bullish" if opt_type == "call" else "bearish"})
    unusual.sort(key=lambda x: x["notional"], reverse=True)
    return unusual[:20]


def _unusual_activity_score(unusual: list[dict]) -> float:
    if not unusual: return 40
    bullish = sum(1 for u in unusual if u["direction_bias"] == "bullish")
    bearish = sum(1 for u in unusual if u["direction_bias"] == "bearish")
    intensity = min(1.0, sum(u["notional"] for u in unusual) / 10_000_000)
    if bullish > bearish * 2: base = 75
    elif bearish > bullish * 2: base = 25
    elif bullish > bearish: base = 65
    elif bearish > bullish: base = 35
    else: base = 50
    score = 50 + (base - 50) * intensity
    if any("short_dated_otm_put" in u.get("flags", []) for u in unusual): score -= 15
    return round(max(0, min(100, score)), 1)


def _iv_near_strike(df, target_strike):
    if df.empty or "impliedVolatility" not in df.columns: return None
    s = df.copy(); s["dist"] = (s["strike"] - target_strike).abs()
    iv = s.loc[s["dist"].idxmin()].get("impliedVolatility", 0)
    return iv if iv and iv > 0 else None


def compute_skew(chain_data: dict) -> dict:
    result = {"skew_25d": None, "skew_direction": "balanced", "term_structure_signal": "normal", "skew_score": 50}
    if not chain_data or not chain_data.get("current_price"): return result
    price = chain_data["current_price"]
    nearest = _nearest_expiry(chain_data)
    if not nearest: return result
    exp, data = nearest
    put_iv = _iv_near_strike(data["puts"], price * 0.95)
    call_iv = _iv_near_strike(data["calls"], price * 1.05)
    if put_iv and call_iv:
        skew = put_iv - call_iv
        result["skew_25d"] = round(skew, 4)
        result["skew_direction"] = "put_premium" if skew > 0.05 else ("call_premium" if skew < -0.05 else "balanced")
    if len(chain_data.get("expirations", [])) >= 2:
        near_data = chain_data["chains"].get(chain_data["expirations"][0])
        far_data = chain_data["chains"].get(chain_data["expirations"][-1])
        if near_data and far_data:
            near_iv = _iv_near_strike(near_data["calls"], price) or _iv_near_strike(near_data["puts"], price)
            far_iv = _iv_near_strike(far_data["calls"], price) or _iv_near_strike(far_data["puts"], price)
            if near_iv and far_iv and far_iv > 0:
                ratio = near_iv / far_iv
                result["term_structure_signal"] = "backwardation" if ratio > OPTIONS_TERM_STRUCTURE_STRESS else ("contango" if ratio < 0.85 else "normal")
    skew_val = result.get("skew_25d", 0) or 0
    if result["skew_direction"] == "put_premium" and abs(skew_val) > 0.08: result["skew_score"] = 75
    elif result["skew_direction"] == "call_premium": result["skew_score"] = 30
    if result["term_structure_signal"] == "backwardation": result["skew_score"] = max(result["skew_score"] - 15, 0)
    return result


def estimate_dealer_exposure(chain_data: dict) -> dict:
    result = {"net_gex": None, "gamma_flip_level": None, "vanna_exposure": None, "max_pain": None,
              "put_wall": None, "call_wall": None, "dealer_regime": "neutral", "dealer_score": 50}
    if not chain_data or not chain_data.get("current_price"): return result
    price = chain_data["current_price"]
    nearest = _nearest_expiry(chain_data)
    if not nearest: return result
    exp, data = nearest
    calls, puts = data["calls"], data["puts"]
    total_gex = 0; gex_by_strike = {}
    for _, row in calls.iterrows():
        gamma, oi = row.get("gamma", 0) or 0, row.get("openInterest", 0) or 0
        if gamma > 0 and oi > 0:
            gex = -oi * gamma * 100 * price
            total_gex += gex; gex_by_strike[row.get("strike", 0)] = gex_by_strike.get(row.get("strike", 0), 0) + gex
    for _, row in puts.iterrows():
        gamma, oi = row.get("gamma", 0) or 0, row.get("openInterest", 0) or 0
        if gamma > 0 and oi > 0:
            gex = oi * gamma * 100 * price
            total_gex += gex; gex_by_strike[row.get("strike", 0)] = gex_by_strike.get(row.get("strike", 0), 0) + gex
    result["net_gex"] = round(total_gex, 0)
    if gex_by_strike:
        cumulative = 0
        for s in sorted(gex_by_strike.keys()):
            prev = cumulative; cumulative += gex_by_strike[s]
            if (prev <= 0 < cumulative) or (prev >= 0 > cumulative):
                result["gamma_flip_level"] = float(s); break
    vanna = 0
    for _, row in calls.iterrows(): vanna += (row.get("openInterest", 0) or 0) * (row.get("vega", 0) or 0) * 100
    for _, row in puts.iterrows(): vanna -= (row.get("openInterest", 0) or 0) * (row.get("vega", 0) or 0) * 100
    result["vanna_exposure"] = round(vanna, 0)
    strikes = sorted(set(list(calls["strike"].unique()) + list(puts["strike"].unique())))
    if strikes:
        min_pain, mp_strike = float("inf"), strikes[0]
        for k in strikes:
            pain = (sum(max(0, k - r["strike"]) * (r.get("openInterest", 0) or 0) for _, r in calls.iterrows()) +
                    sum(max(0, r["strike"] - k) * (r.get("openInterest", 0) or 0) for _, r in puts.iterrows()))
            if pain < min_pain: min_pain, mp_strike = pain, k
        result["max_pain"] = float(mp_strike)
    if not calls.empty and "openInterest" in calls.columns: result["call_wall"] = float(calls.loc[calls["openInterest"].idxmax()]["strike"])
    if not puts.empty and "openInterest" in puts.columns: result["put_wall"] = float(puts.loc[puts["openInterest"].idxmax()]["strike"])
    if total_gex > 0: result["dealer_regime"] = "pinning"
    elif total_gex < 0: result["dealer_regime"] = "amplifying"
    if total_gex < 0: result["dealer_score"] = 75
    elif total_gex > 0 and result["max_pain"]:
        result["dealer_score"] = 30 if abs(price - result["max_pain"]) / price < 0.02 else 50
    result["dealer_score"] = round(result["dealer_score"], 1)
    return result


def compute_options_composite(iv, expected_move, pc, unusual, skew, dealer) -> float:
    w = OPTIONS_COMPOSITE_WEIGHTS
    composite = (w["iv_metrics"] * iv.get("iv_score", 50) + w["pc_ratios"] * pc.get("pc_score", 50) +
                 w["unusual_activity"] * _unusual_activity_score(unusual) + w["skew"] * skew.get("skew_score", 50) +
                 w["dealer_exposure"] * dealer.get("dealer_score", 50))
    return round(max(0, min(100, composite)), 1)


def analyze_symbol(symbol: str) -> dict | None:
    chain = fetch_options_chain(symbol)
    if not chain: return None
    iv = compute_iv_metrics(chain)
    em = compute_expected_move(chain)
    pc = compute_put_call_ratios(chain)
    unusual = detect_unusual_activity(chain)
    skew = compute_skew(chain)
    dealer = estimate_dealer_exposure(chain)
    options_score = compute_options_composite(iv, em, pc, unusual, skew, dealer)
    if unusual:
        bc = sum(1 for u in unusual if u["direction_bias"] == "bullish")
        brc = sum(1 for u in unusual if u["direction_bias"] == "bearish")
        direction_bias = "bullish" if bc > brc * 1.5 else ("bearish" if brc > bc * 1.5 else "mixed")
    else: direction_bias = None
    return {"symbol": symbol, "date": date.today().isoformat(),
        "atm_iv": iv.get("atm_iv"), "hv_20d": iv.get("hv_20d"), "iv_premium": iv.get("iv_premium"),
        "iv_rank": iv.get("iv_rank"), "iv_percentile": iv.get("iv_percentile"),
        "expected_move_pct": em.get("expected_move_pct"), "straddle_cost": em.get("straddle_cost"),
        "volume_pc_ratio": pc.get("volume_pc_ratio"), "oi_pc_ratio": pc.get("oi_pc_ratio"), "pc_signal": pc.get("pc_signal"),
        "unusual_activity_count": len(unusual), "unusual_activity": json.dumps(unusual[:10]) if unusual else None,
        "unusual_direction_bias": direction_bias,
        "skew_25d": skew.get("skew_25d"), "skew_direction": skew.get("skew_direction"),
        "term_structure_signal": skew.get("term_structure_signal"),
        "net_gex": dealer.get("net_gex"), "gamma_flip_level": dealer.get("gamma_flip_level"),
        "vanna_exposure": dealer.get("vanna_exposure"), "max_pain": dealer.get("max_pain"),
        "put_wall": dealer.get("put_wall"), "call_wall": dealer.get("call_wall"),
        "dealer_regime": dealer.get("dealer_regime"), "options_score": options_score}


def analyze_batch(symbols: list[str], delay: float = OPTIONS_YFINANCE_DELAY) -> list[dict]:
    results = []
    for i, sym in enumerate(symbols):
        if (i + 1) % 10 == 0: print(f"    Options: {i + 1}/{len(symbols)} analyzed...")
        try:
            result = analyze_symbol(sym)
            if result: results.append(result)
        except Exception as e: logger.warning(f"Options analysis failed for {sym}: {e}")
        time.sleep(delay)
    return results
