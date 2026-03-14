"""Pattern Scanner — Layers 1-4 of the Pattern Match & Options Intelligence module.

Pure price-based analysis. No external API calls. Runs on existing price_data table.

Layers:
  1. Market Regime Context (reads macro_scores + VIX)
  2. Sector Relative Rotation (RRG methodology)
  3. Technical Pattern Detection (chart patterns, S/R, volume profile)
  4. Statistical Patterns (Hurst, mean-reversion, momentum, compression, Wyckoff)
"""

import json
import logging
import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from scipy.stats import gaussian_kde
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

from tools.db import query, query_df, get_conn
from tools.config import (
    BENCHMARK_STOCK,
    ROTATION_RS_LOOKBACK,
    ROTATION_MOMENTUM_LOOKBACK,
    ROTATION_HISTORY_DAYS,
    PATTERN_MIN_BARS,
    PATTERN_SR_KDE_BANDWIDTH_ATR_MULT,
    PATTERN_SR_TOUCH_TOLERANCE,
    PATTERN_VOLUME_PROFILE_BINS,
    PATTERN_TRIANGLE_MIN_TOUCHES,
    PATTERN_TRIANGLE_R2_MIN,
    HURST_MIN_OBSERVATIONS,
    MR_ZSCORE_THRESHOLD,
    MR_HALF_LIFE_MIN,
    MR_HALF_LIFE_MAX,
    MOMENTUM_VR_THRESHOLD,
    COMPRESSION_HV_PERCENTILE_LOW,
    COMPRESSION_SQUEEZE_MIN_BARS,
    PATTERN_LAYER_WEIGHTS,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def _load_price_matrix() -> pd.DataFrame:
    """Load closing prices as date × symbol matrix."""
    df = query_df("""
        SELECT symbol, date, close FROM price_data
        WHERE close IS NOT NULL ORDER BY date
    """)
    if df.empty:
        return pd.DataFrame()
    pivot = df.pivot_table(index="date", columns="symbol", values="close")
    pivot = pivot.sort_index().ffill(limit=5)
    # Drop symbols with <100 data points
    pivot = pivot.dropna(axis=1, thresh=100)
    return pivot


def _load_ohlcv(symbol: str) -> pd.DataFrame:
    """Load full OHLCV for a single symbol."""
    df = query_df("""
        SELECT date, open, high, low, close, volume
        FROM price_data WHERE symbol = ? AND close IS NOT NULL
        ORDER BY date
    """, [symbol])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
    return df


def _load_sector_map() -> dict[str, str]:
    """Return {symbol: sector}."""
    rows = query("SELECT symbol, sector FROM stock_universe WHERE sector IS NOT NULL AND sector != ''")
    return {r["symbol"]: r["sector"] for r in rows}


def _atr(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    h, l, c = ohlcv["high"], ohlcv["low"], ohlcv["close"]
    tr = pd.concat([
        h - l,
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1: MARKET REGIME CONTEXT
# ═══════════════════════════════════════════════════════════════════════════

def compute_regime_context() -> dict:
    """Read existing macro regime + VIX to produce market context."""
    # Macro regime
    rows = query("SELECT regime, total_score FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = rows[0]["regime"] if rows else "neutral"
    regime_score = rows[0]["total_score"] if rows else 0

    # VIX level + percentile
    vix_df = query_df("""
        SELECT close FROM price_data WHERE symbol = '^VIX'
        AND close IS NOT NULL ORDER BY date DESC LIMIT 252
    """)
    vix_level = vix_df.iloc[0]["close"] if not vix_df.empty else 20.0
    vix_values = vix_df["close"].values if not vix_df.empty else np.array([20.0])
    vix_percentile = float(np.sum(vix_values > vix_level) / len(vix_values) * 100)

    # SPY trend filter
    spy_df = query_df("""
        SELECT close FROM price_data WHERE symbol = 'SPY'
        AND close IS NOT NULL ORDER BY date DESC LIMIT 200
    """)
    if len(spy_df) >= 200:
        price = spy_df.iloc[0]["close"]
        sma50 = spy_df.iloc[:50]["close"].mean()
        sma200 = spy_df["close"].mean()
        if price > sma50 > sma200:
            trend_filter = "bullish"
        elif price < sma50 < sma200:
            trend_filter = "bearish"
        else:
            trend_filter = "neutral"
    else:
        trend_filter = "neutral"

    return {
        "regime": regime,
        "regime_score": regime_score,
        "vix_level": vix_level,
        "vix_percentile": vix_percentile,
        "trend_filter": trend_filter,
    }


def _regime_score(ctx: dict) -> float:
    """Convert regime context to 0-100 score."""
    # Base from macro regime
    regime_map = {
        "strong_risk_on": 90, "risk_on": 70, "neutral": 50,
        "risk_off": 30, "strong_risk_off": 10,
    }
    base = regime_map.get(ctx["regime"], 50)
    # VIX penalty: high VIX = uncertainty
    vix_adj = -10 if ctx["vix_percentile"] < 20 else 0  # VIX is high (low percentile = high rank)
    return max(0, min(100, base + vix_adj))


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 2: SECTOR RELATIVE ROTATION (RRG)
# ═══════════════════════════════════════════════════════════════════════════

def compute_sector_rotation(price_matrix: pd.DataFrame,
                            sector_map: dict[str, str]) -> dict[str, dict]:
    """Compute RRG quadrant for each sector.

    Returns: {sector: {rs_ratio, rs_momentum, quadrant, rotation_score}}
    """
    if price_matrix.empty or BENCHMARK_STOCK not in price_matrix.columns:
        return {}

    benchmark = price_matrix[BENCHMARK_STOCK]

    # Build equal-weighted sector return series
    sectors = set(sector_map.values())
    sector_prices = {}
    for sec in sectors:
        members = [s for s, se in sector_map.items() if se == sec and s in price_matrix.columns]
        if len(members) < 3:
            continue
        sector_prices[sec] = price_matrix[members].mean(axis=1)

    results = {}
    for sec, sec_series in sector_prices.items():
        aligned = pd.DataFrame({"sector": sec_series, "bench": benchmark}).dropna()
        if len(aligned) < ROTATION_HISTORY_DAYS:
            continue

        # RS-Ratio: rolling relative performance
        lookback = min(ROTATION_RS_LOOKBACK, len(aligned) - 1)
        rs_raw = aligned["sector"].pct_change(lookback) - aligned["bench"].pct_change(lookback)

        # Z-score RS-Ratio against its own 252d history
        rs_mean = rs_raw.rolling(ROTATION_HISTORY_DAYS, min_periods=60).mean()
        rs_std = rs_raw.rolling(ROTATION_HISTORY_DAYS, min_periods=60).std()
        rs_ratio = ((rs_raw - rs_mean) / rs_std.replace(0, np.nan)).iloc[-1]

        # RS-Momentum: 10-day ROC of RS-Ratio
        rs_norm = (rs_raw - rs_mean) / rs_std.replace(0, np.nan)
        if len(rs_norm.dropna()) < ROTATION_MOMENTUM_LOOKBACK + 1:
            continue
        rs_momentum = float(rs_norm.iloc[-1] - rs_norm.iloc[-1 - ROTATION_MOMENTUM_LOOKBACK])

        if np.isnan(rs_ratio) or np.isnan(rs_momentum):
            continue

        rs_ratio = float(rs_ratio)

        # Classify quadrant
        if rs_ratio > 0 and rs_momentum > 0:
            quadrant = "leading"
        elif rs_ratio > 0 and rs_momentum <= 0:
            quadrant = "weakening"
        elif rs_ratio <= 0 and rs_momentum <= 0:
            quadrant = "lagging"
        else:
            quadrant = "improving"

        # Score: 50 + 25*tanh(rs_ratio) + 25*tanh(rs_momentum)
        rotation_score = 50 + 25 * math.tanh(rs_ratio) + 25 * math.tanh(rs_momentum)

        results[sec] = {
            "rs_ratio": round(rs_ratio, 4),
            "rs_momentum": round(rs_momentum, 4),
            "quadrant": quadrant,
            "rotation_score": round(max(0, min(100, rotation_score)), 1),
        }

    return results


def compute_stock_rotation(symbol: str, price_matrix: pd.DataFrame,
                           sector_map: dict[str, str]) -> dict:
    """Compute RRG positioning for a single stock within its sector."""
    sector = sector_map.get(symbol)
    if not sector or symbol not in price_matrix.columns:
        return {"rotation_score": 50, "quadrant": "neutral", "rs_ratio": 0, "rs_momentum": 0}

    # Sector benchmark = equal-weight of sector members
    members = [s for s, se in sector_map.items() if se == sector and s in price_matrix.columns and s != symbol]
    if len(members) < 2:
        return {"rotation_score": 50, "quadrant": "neutral", "rs_ratio": 0, "rs_momentum": 0}

    bench = price_matrix[members].mean(axis=1)
    stock = price_matrix[symbol]
    aligned = pd.DataFrame({"stock": stock, "bench": bench}).dropna()

    if len(aligned) < 120:
        return {"rotation_score": 50, "quadrant": "neutral", "rs_ratio": 0, "rs_momentum": 0}

    lookback = min(ROTATION_RS_LOOKBACK, len(aligned) - 1)
    rs_raw = aligned["stock"].pct_change(lookback) - aligned["bench"].pct_change(lookback)
    rs_mean = rs_raw.rolling(min(ROTATION_HISTORY_DAYS, len(rs_raw)), min_periods=60).mean()
    rs_std = rs_raw.rolling(min(ROTATION_HISTORY_DAYS, len(rs_raw)), min_periods=60).std()
    rs_norm = (rs_raw - rs_mean) / rs_std.replace(0, np.nan)

    if rs_norm.dropna().empty or len(rs_norm.dropna()) < ROTATION_MOMENTUM_LOOKBACK + 1:
        return {"rotation_score": 50, "quadrant": "neutral", "rs_ratio": 0, "rs_momentum": 0}

    rs_ratio = float(rs_norm.iloc[-1])
    rs_momentum = float(rs_norm.iloc[-1] - rs_norm.iloc[-1 - ROTATION_MOMENTUM_LOOKBACK])

    if np.isnan(rs_ratio) or np.isnan(rs_momentum):
        return {"rotation_score": 50, "quadrant": "neutral", "rs_ratio": 0, "rs_momentum": 0}

    if rs_ratio > 0 and rs_momentum > 0:
        quadrant = "leading"
    elif rs_ratio > 0 and rs_momentum <= 0:
        quadrant = "weakening"
    elif rs_ratio <= 0 and rs_momentum <= 0:
        quadrant = "lagging"
    else:
        quadrant = "improving"

    rotation_score = 50 + 25 * math.tanh(rs_ratio) + 25 * math.tanh(rs_momentum)

    return {
        "rs_ratio": round(rs_ratio, 4),
        "rs_momentum": round(rs_momentum, 4),
        "quadrant": quadrant,
        "rotation_score": round(max(0, min(100, rotation_score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 3: TECHNICAL PATTERN DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def _find_swing_points(series: pd.Series, order: int = 5) -> tuple[pd.Series, pd.Series]:
    """Find swing highs and lows using local extrema."""
    highs_idx = argrelextrema(series.values, np.greater_equal, order=order)[0]
    lows_idx = argrelextrema(series.values, np.less_equal, order=order)[0]
    return series.iloc[highs_idx], series.iloc[lows_idx]


def detect_chart_patterns(ohlcv: pd.DataFrame) -> list[dict]:
    """Detect chart patterns with statistical validation.

    Returns list of detected patterns with confidence scores.
    """
    if len(ohlcv) < PATTERN_MIN_BARS * 3:
        return []

    patterns = []
    close = ohlcv["close"]
    high = ohlcv["high"]
    low = ohlcv["low"]
    volume = ohlcv["volume"]
    current_price = close.iloc[-1]
    atr_val = _atr(ohlcv).iloc[-1] if len(ohlcv) >= 14 else close.std() * 0.1

    # Work with last 120 bars for pattern detection
    lookback = min(120, len(ohlcv))
    h = high.iloc[-lookback:]
    l = low.iloc[-lookback:]
    c = close.iloc[-lookback:]
    v = volume.iloc[-lookback:]

    swing_highs, swing_lows = _find_swing_points(h, order=5)
    _, swing_lows_low = _find_swing_points(l, order=5)

    # --- Double Top ---
    if len(swing_highs) >= 2:
        top1 = swing_highs.iloc[-2]
        top2 = swing_highs.iloc[-1]
        tol = 0.02 * top1
        if abs(top1 - top2) < tol:
            neckline = swing_lows_low.iloc[-1] if not swing_lows_low.empty else l.min()
            target = current_price - (top1 - neckline)
            # Volume should be lower on second top
            idx1 = swing_highs.index[-2]
            idx2 = swing_highs.index[-1]
            if idx1 in v.index and idx2 in v.index:
                vol_confirm = v.loc[idx2] < v.loc[idx1]
            else:
                vol_confirm = False
            conf = 0.6 + (0.2 if vol_confirm else 0) + (0.2 if current_price < neckline else 0)
            patterns.append({
                "pattern": "double_top",
                "direction": "bearish",
                "confidence": round(min(1.0, conf), 2),
                "price_target": round(target, 2),
                "invalidation": round(max(top1, top2) * 1.01, 2),
                "bars_since": int(len(c) - list(c.index).index(idx2)) if idx2 in c.index else 0,
            })

    # --- Double Bottom ---
    if len(swing_lows_low) >= 2:
        bot1 = swing_lows_low.iloc[-2]
        bot2 = swing_lows_low.iloc[-1]
        tol = 0.02 * bot1
        if abs(bot1 - bot2) < tol:
            neckline = swing_highs.iloc[-1] if not swing_highs.empty else h.max()
            target = current_price + (neckline - bot1)
            conf = 0.6 + (0.2 if current_price > neckline else 0)
            patterns.append({
                "pattern": "double_bottom",
                "direction": "bullish",
                "confidence": round(min(1.0, conf), 2),
                "price_target": round(target, 2),
                "invalidation": round(min(bot1, bot2) * 0.99, 2),
                "bars_since": 0,
            })

    # --- Ascending Triangle (flat highs, rising lows) ---
    if len(swing_highs) >= PATTERN_TRIANGLE_MIN_TOUCHES and len(swing_lows_low) >= PATTERN_TRIANGLE_MIN_TOUCHES:
        # Regression on swing highs — should be flat
        sh_idx = np.arange(len(swing_highs[-5:]))
        sh_vals = swing_highs.iloc[-5:].values
        if len(sh_idx) >= 3:
            X_h = add_constant(sh_idx)
            try:
                model_h = OLS(sh_vals, X_h).fit()
                slope_h = model_h.params[1] / sh_vals.mean()
                r2_h = model_h.rsquared

                # Regression on swing lows — should be rising
                sl_vals = swing_lows_low.iloc[-5:].values[:len(sh_idx)]
                if len(sl_vals) >= 3:
                    sl_idx = np.arange(len(sl_vals))
                    X_l = add_constant(sl_idx)
                    model_l = OLS(sl_vals, X_l).fit()
                    slope_l = model_l.params[1] / sl_vals.mean()
                    r2_l = model_l.rsquared

                    if abs(slope_h) < 0.003 and slope_l > 0.001 and r2_l > PATTERN_TRIANGLE_R2_MIN:
                        resistance = float(sh_vals.mean())
                        target = resistance + (resistance - sl_vals[-1])
                        conf = min(1.0, (r2_h + r2_l) / 2)
                        patterns.append({
                            "pattern": "ascending_triangle",
                            "direction": "bullish",
                            "confidence": round(conf, 2),
                            "price_target": round(target, 2),
                            "invalidation": round(float(sl_vals[-1]) * 0.98, 2),
                            "bars_since": 0,
                        })
            except Exception:
                pass

    # --- Descending Triangle (flat lows, falling highs) ---
    if len(swing_lows_low) >= PATTERN_TRIANGLE_MIN_TOUCHES and len(swing_highs) >= PATTERN_TRIANGLE_MIN_TOUCHES:
        sl_idx = np.arange(len(swing_lows_low[-5:]))
        sl_vals = swing_lows_low.iloc[-5:].values
        if len(sl_idx) >= 3:
            X_l = add_constant(sl_idx)
            try:
                model_l = OLS(sl_vals, X_l).fit()
                slope_l = model_l.params[1] / sl_vals.mean()
                r2_l = model_l.rsquared

                sh_vals = swing_highs.iloc[-5:].values[:len(sl_idx)]
                if len(sh_vals) >= 3:
                    sh_idx_arr = np.arange(len(sh_vals))
                    X_h = add_constant(sh_idx_arr)
                    model_h = OLS(sh_vals, X_h).fit()
                    slope_h = model_h.params[1] / sh_vals.mean()
                    r2_h = model_h.rsquared

                    if abs(slope_l) < 0.003 and slope_h < -0.001 and r2_h > PATTERN_TRIANGLE_R2_MIN:
                        support = float(sl_vals.mean())
                        target = support - (sh_vals[-1] - support)
                        conf = min(1.0, (r2_h + r2_l) / 2)
                        patterns.append({
                            "pattern": "descending_triangle",
                            "direction": "bearish",
                            "confidence": round(conf, 2),
                            "price_target": round(target, 2),
                            "invalidation": round(float(sh_vals[-1]) * 1.02, 2),
                            "bars_since": 0,
                        })
            except Exception:
                pass

    # --- Bull Flag (tight range after sharp up move) ---
    if len(c) >= 30 and atr_val and atr_val > 0:
        pre_move = c.iloc[-30:-10]
        flag = c.iloc[-10:]
        if len(pre_move) > 0 and len(flag) > 0:
            move_pct = (pre_move.iloc[-1] - pre_move.iloc[0]) / pre_move.iloc[0]
            flag_range = (flag.max() - flag.min()) / atr_val

            if move_pct > 0.05 and flag_range < 3.0:
                # Check declining volume in flag
                vol_flag = v.iloc[-10:]
                vol_slope = np.polyfit(range(len(vol_flag)), vol_flag.values, 1)[0] if len(vol_flag) > 2 else 0
                conf = 0.5 + (0.25 if vol_slope < 0 else 0) + (0.25 if flag_range < 1.5 else 0)
                target = current_price + (pre_move.iloc[-1] - pre_move.iloc[0])
                patterns.append({
                    "pattern": "bull_flag",
                    "direction": "bullish",
                    "confidence": round(min(1.0, conf), 2),
                    "price_target": round(target, 2),
                    "invalidation": round(float(flag.min()) * 0.98, 2),
                    "bars_since": 0,
                })

    # --- Bear Flag ---
    if len(c) >= 30 and atr_val and atr_val > 0:
        pre_move = c.iloc[-30:-10]
        flag = c.iloc[-10:]
        if len(pre_move) > 0 and len(flag) > 0:
            move_pct = (pre_move.iloc[-1] - pre_move.iloc[0]) / pre_move.iloc[0]
            flag_range = (flag.max() - flag.min()) / atr_val

            if move_pct < -0.05 and flag_range < 3.0:
                vol_flag = v.iloc[-10:]
                vol_slope = np.polyfit(range(len(vol_flag)), vol_flag.values, 1)[0] if len(vol_flag) > 2 else 0
                conf = 0.5 + (0.25 if vol_slope < 0 else 0) + (0.25 if flag_range < 1.5 else 0)
                target = current_price - abs(pre_move.iloc[-1] - pre_move.iloc[0])
                patterns.append({
                    "pattern": "bear_flag",
                    "direction": "bearish",
                    "confidence": round(min(1.0, conf), 2),
                    "price_target": round(target, 2),
                    "invalidation": round(float(flag.max()) * 1.02, 2),
                    "bars_since": 0,
                })

    return patterns


def _pattern_score(patterns: list[dict]) -> float:
    """Convert detected patterns to a 0-100 score."""
    if not patterns:
        return 30  # No patterns = mildly below neutral

    # Take the highest-confidence pattern
    best = max(patterns, key=lambda p: p["confidence"])
    # Bullish patterns score high, bearish low
    if best["direction"] == "bullish":
        return min(100, 50 + best["confidence"] * 50)
    else:
        return max(0, 50 - best["confidence"] * 50)


def compute_support_resistance(ohlcv: pd.DataFrame, n_levels: int = 5) -> list[dict]:
    """Detect S/R levels using Kernel Density Estimation."""
    if len(ohlcv) < 50:
        return []

    current_price = ohlcv["close"].iloc[-1]
    atr_val = _atr(ohlcv).iloc[-1]
    if not atr_val or atr_val <= 0 or np.isnan(atr_val):
        return []

    # Combine highs and lows
    prices = pd.concat([ohlcv["high"], ohlcv["low"]]).dropna().values
    if len(prices) < 20:
        return []

    bandwidth = PATTERN_SR_KDE_BANDWIDTH_ATR_MULT * atr_val
    try:
        kde = gaussian_kde(prices, bw_method=bandwidth / prices.std())
    except Exception:
        return []

    # Evaluate KDE on a grid
    price_range = np.linspace(prices.min(), prices.max(), 500)
    density = kde(price_range)

    # Find local maxima of density = price clusters
    peak_idx = argrelextrema(density, np.greater, order=10)[0]
    if len(peak_idx) == 0:
        return []

    levels = []
    tol = PATTERN_SR_TOUCH_TOLERANCE * current_price

    for idx in peak_idx:
        level = float(price_range[idx])
        # Count touches
        touches = int(np.sum(np.abs(prices - level) < tol))
        # Recency-weighted (exponential decay, half-life 30 bars)
        bar_positions = np.where(np.abs(prices[:len(ohlcv)] - level) < tol)[0]
        recency = sum(math.exp(-0.023 * (len(ohlcv) - pos)) for pos in bar_positions) if len(bar_positions) > 0 else 0
        # Volume at level
        vol_at_level = 0
        for i, row in ohlcv.iterrows():
            if abs(row["close"] - level) < tol:
                vol_at_level += row.get("volume", 0)

        strength = min(100, touches * 8 + recency * 15)
        sr_type = "support" if level < current_price else "resistance"

        levels.append({
            "level": round(level, 2),
            "type": sr_type,
            "strength": round(strength, 1),
            "touch_count": touches,
        })

    # Sort by strength, return top N
    levels.sort(key=lambda x: x["strength"], reverse=True)
    return levels[:n_levels]


def compute_volume_profile(ohlcv: pd.DataFrame) -> dict:
    """Compute volume profile: POC, value area, score."""
    if len(ohlcv) < 50:
        return {"poc": 0, "value_area_high": 0, "value_area_low": 0,
                "current_vs_va": "unknown", "volume_profile_score": 50}

    lookback = min(PATTERN_VOLUME_PROFILE_BINS * 5, len(ohlcv))
    data = ohlcv.iloc[-lookback:]
    current_price = data["close"].iloc[-1]

    # Typical price weighted by volume
    typical = (data["high"] + data["low"] + data["close"]) / 3
    price_min, price_max = typical.min(), typical.max()
    if price_max <= price_min:
        return {"poc": float(current_price), "value_area_high": float(current_price),
                "value_area_low": float(current_price), "current_vs_va": "at_poc",
                "volume_profile_score": 50}

    n_bins = PATTERN_VOLUME_PROFILE_BINS
    bins = np.linspace(price_min, price_max, n_bins + 1)
    vol_per_bin = np.zeros(n_bins)

    for i in range(len(data)):
        tp = typical.iloc[i]
        vol = data["volume"].iloc[i] if data["volume"].iloc[i] > 0 else 1
        bin_idx = min(int((tp - price_min) / (price_max - price_min) * n_bins), n_bins - 1)
        vol_per_bin[bin_idx] += vol

    # POC = bin with highest volume
    poc_idx = int(np.argmax(vol_per_bin))
    poc = float((bins[poc_idx] + bins[poc_idx + 1]) / 2)

    # Value Area = 70% of total volume centered on POC
    total_vol = vol_per_bin.sum()
    target_vol = 0.70 * total_vol
    va_low_idx, va_high_idx = poc_idx, poc_idx
    accumulated = vol_per_bin[poc_idx]

    while accumulated < target_vol and (va_low_idx > 0 or va_high_idx < n_bins - 1):
        low_vol = vol_per_bin[va_low_idx - 1] if va_low_idx > 0 else 0
        high_vol = vol_per_bin[va_high_idx + 1] if va_high_idx < n_bins - 1 else 0
        if low_vol >= high_vol and va_low_idx > 0:
            va_low_idx -= 1
            accumulated += low_vol
        elif va_high_idx < n_bins - 1:
            va_high_idx += 1
            accumulated += high_vol
        else:
            va_low_idx -= 1
            accumulated += low_vol

    va_low = float(bins[va_low_idx])
    va_high = float(bins[min(va_high_idx + 1, n_bins)])

    # Scoring
    if current_price > va_high:
        # Above value area — breakout if volume supports
        recent_vol = data["volume"].iloc[-5:].mean()
        avg_vol = data["volume"].mean()
        vol_confirm = recent_vol > avg_vol * 1.2
        score = 80 if vol_confirm else 60
        vs_va = "above_va"
    elif current_price < va_low:
        score = 35
        vs_va = "below_va"
    else:
        score = 50
        vs_va = "inside_va"

    return {
        "poc": round(poc, 2),
        "value_area_high": round(va_high, 2),
        "value_area_low": round(va_low, 2),
        "current_vs_va": vs_va,
        "volume_profile_score": float(score),
    }


def _sr_proximity_label(sr_levels: list[dict], current_price: float, atr_val: float) -> str:
    """Determine if price is near support, resistance, or between."""
    if not sr_levels or not atr_val or atr_val <= 0:
        return "between"
    for level in sr_levels:
        dist = abs(current_price - level["level"])
        if dist < atr_val * 1.5:
            return f"near_{level['type']}"
    return "between"


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 4: STATISTICAL PATTERNS
# ═══════════════════════════════════════════════════════════════════════════

def _hurst_exponent(series: pd.Series, max_lag: int = 40) -> float:
    """Compute Hurst exponent via rescaled range analysis.

    H < 0.5: mean-reverting
    H = 0.5: random walk
    H > 0.5: trending
    """
    raw = series.dropna().values
    if len(raw) < HURST_MIN_OBSERVATIONS:
        return 0.5  # Default to random walk
    # Use log returns, not raw prices — raw prices are non-stationary and always give H≈1
    vals = np.diff(np.log(raw[raw > 0]))

    lags = range(2, min(max_lag, len(vals) // 4))
    rs_values = []

    for lag in lags:
        n = len(vals) // lag
        if n < 1:
            continue
        rs_list = []
        for i in range(n):
            chunk = vals[i * lag: (i + 1) * lag]
            if len(chunk) < 2:
                continue
            mean_c = chunk.mean()
            deviations = np.cumsum(chunk - mean_c)
            R = deviations.max() - deviations.min()
            S = chunk.std(ddof=1)
            if S > 0:
                rs_list.append(R / S)
        if rs_list:
            rs_values.append((np.log(lag), np.log(np.mean(rs_list))))

    if len(rs_values) < 3:
        return 0.5

    x, y = zip(*rs_values)
    try:
        slope, _ = np.polyfit(x, y, 1)
        return max(0.0, min(1.0, slope))
    except Exception:
        return 0.5


def detect_mean_reversion_setups(ohlcv: pd.DataFrame) -> dict:
    """Multi-timeframe z-score + Hurst + OU half-life for MR detection."""
    close = ohlcv["close"]
    if len(close) < 100:
        return {"hurst": 0.5, "mr_score": 0, "zscore_20d": 0, "zscore_50d": 0, "half_life": None}

    log_prices = np.log(close)

    # Z-scores at multiple timeframes
    z20 = float((close.iloc[-1] - close.rolling(20).mean().iloc[-1]) / close.rolling(20).std().iloc[-1]) \
        if len(close) >= 20 and close.rolling(20).std().iloc[-1] > 0 else 0
    z50 = float((close.iloc[-1] - close.rolling(50).mean().iloc[-1]) / close.rolling(50).std().iloc[-1]) \
        if len(close) >= 50 and close.rolling(50).std().iloc[-1] > 0 else 0

    # Hurst exponent
    hurst = _hurst_exponent(close)

    # Ornstein-Uhlenbeck half-life
    half_life = None
    try:
        y = np.diff(log_prices.values)
        x = log_prices.values[:-1]
        X = add_constant(x)
        model = OLS(y, X).fit()
        beta = model.params[1]
        if beta < 0 and model.pvalues[1] < 0.05:
            half_life = -math.log(2) / math.log(1 + beta)
    except Exception:
        pass

    # MR Score
    mr_score = 0.0
    if hurst < 0.5:
        mr_score += 50 * (1 - hurst) / 0.5  # 0-50 based on Hurst

    # Z-score bonus
    max_z = max(abs(z20), abs(z50))
    if max_z >= MR_ZSCORE_THRESHOLD:
        mr_score += 25

    # Half-life bonus
    if half_life and MR_HALF_LIFE_MIN <= half_life <= MR_HALF_LIFE_MAX:
        mr_score += 25

    return {
        "hurst": round(hurst, 4),
        "zscore_20d": round(z20, 2),
        "zscore_50d": round(z50, 2),
        "half_life": round(half_life, 1) if half_life else None,
        "mr_score": round(max(0, min(100, mr_score)), 1),
    }


def detect_momentum_persistence(ohlcv: pd.DataFrame) -> dict:
    """Detect trending behavior via autocorrelation + variance ratio + ADX."""
    close = ohlcv["close"]
    if len(close) < 60:
        return {"hurst": 0.5, "momentum_score": 0, "adx": 0}

    returns = close.pct_change().dropna()

    # Autocorrelation at key lags
    ac1 = float(returns.autocorr(lag=1)) if len(returns) > 1 else 0
    ac5 = float(returns.autocorr(lag=5)) if len(returns) > 5 else 0

    # Variance ratio test (Lo-MacKinlay)
    def variance_ratio(rets, q):
        if len(rets) < q * 2:
            return 1.0
        var1 = rets.var()
        if var1 == 0:
            return 1.0
        q_rets = rets.rolling(q).sum().dropna()
        var_q = q_rets.var()
        return var_q / (q * var1)

    vr5 = variance_ratio(returns, 5)
    vr21 = variance_ratio(returns, 21)

    # ADX
    try:
        from ta.trend import ADXIndicator
        adx_ind = ADXIndicator(ohlcv["high"], ohlcv["low"], close, window=14)
        adx = float(adx_ind.adx().iloc[-1])
    except Exception:
        adx = 0

    # Hurst
    hurst = _hurst_exponent(close)

    # Momentum score
    momentum_score = 0.0
    if hurst > 0.5:
        momentum_score += 50 * min(1.0, (hurst - 0.5) / 0.5)
    if vr5 > MOMENTUM_VR_THRESHOLD:
        momentum_score += 25
    if adx > 25:
        momentum_score += 25

    return {
        "hurst": round(hurst, 4),
        "autocorr_1d": round(ac1, 4),
        "autocorr_5d": round(ac5, 4),
        "variance_ratio_5": round(vr5, 4),
        "variance_ratio_21": round(vr21, 4),
        "adx": round(adx, 1),
        "momentum_score": round(max(0, min(100, momentum_score)), 1),
    }


def detect_volatility_compression(ohlcv: pd.DataFrame) -> dict:
    """Detect coiled-spring setups where volatility is compressed."""
    close = ohlcv["close"]
    if len(close) < 60:
        return {"hv_20d": 0, "hv_60d": 0, "hv_ratio": 1, "hv_percentile": 50,
                "squeeze_active": False, "squeeze_duration": 0, "compression_score": 0}

    log_returns = np.log(close / close.shift(1)).dropna()

    # Historical volatility at multiple horizons
    hv20 = float(log_returns.iloc[-20:].std() * np.sqrt(252)) if len(log_returns) >= 20 else 0
    hv60 = float(log_returns.iloc[-60:].std() * np.sqrt(252)) if len(log_returns) >= 60 else 0
    hv252 = float(log_returns.std() * np.sqrt(252)) if len(log_returns) >= 100 else hv60

    hv_ratio = hv20 / hv60 if hv60 > 0 else 1.0

    # HV percentile (where current HV20 sits in 252d range)
    rolling_hv = log_returns.rolling(20).std() * np.sqrt(252)
    rolling_hv = rolling_hv.dropna()
    if len(rolling_hv) > 20:
        hv_percentile = float(np.sum(rolling_hv.values < hv20) / len(rolling_hv) * 100)
    else:
        hv_percentile = 50.0

    # Keltner/Bollinger squeeze detection
    bb_upper = close.rolling(20).mean() + 2 * close.rolling(20).std()
    bb_lower = close.rolling(20).mean() - 2 * close.rolling(20).std()
    atr_val = _atr(ohlcv)
    kc_upper = close.rolling(20).mean() + 1.5 * atr_val
    kc_lower = close.rolling(20).mean() - 1.5 * atr_val

    squeeze_series = (bb_upper < kc_upper) & (bb_lower > kc_lower)
    squeeze_active = bool(squeeze_series.iloc[-1]) if not squeeze_series.empty else False

    # Count consecutive squeeze bars
    squeeze_duration = 0
    if squeeze_active:
        for i in range(len(squeeze_series) - 1, -1, -1):
            if squeeze_series.iloc[i]:
                squeeze_duration += 1
            else:
                break

    # Compression score
    compression_score = 0.0
    if hv_percentile < COMPRESSION_HV_PERCENTILE_LOW:
        compression_score += 40 * (1 - hv_percentile / 100)
    if squeeze_active and squeeze_duration >= COMPRESSION_SQUEEZE_MIN_BARS:
        compression_score += 30
    if hv_ratio < 0.7:
        compression_score += 30

    return {
        "hv_20d": round(hv20, 4),
        "hv_60d": round(hv60, 4),
        "hv_ratio": round(hv_ratio, 3),
        "hv_percentile": round(hv_percentile, 1),
        "squeeze_active": squeeze_active,
        "squeeze_duration": squeeze_duration,
        "compression_score": round(max(0, min(100, compression_score)), 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 4.5: CYCLE ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def detect_wyckoff_phase(ohlcv: pd.DataFrame) -> dict:
    """Classify Wyckoff cycle phase: accumulation, markup, distribution, markdown."""
    close = ohlcv["close"]
    volume = ohlcv["volume"]

    if len(close) < 60:
        return {"phase": "unknown", "confidence": 0, "duration_days": 0,
                "progress_pct": 0, "cycle_score": 50}

    # Trend: 252d linear regression slope of log(close)
    lookback = min(252, len(close))
    prices = close.iloc[-lookback:]
    log_p = np.log(prices.values)
    x = np.arange(len(log_p))
    slope, intercept = np.polyfit(x, log_p, 1)
    annualized_trend = slope * 252  # Approximate annualized return

    # Price vs moving averages
    sma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else close.mean()
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.rolling(100).mean().iloc[-1]
    current = close.iloc[-1]

    # On-Balance Volume slope (last 30 bars)
    obv = (volume * np.where(close.diff() > 0, 1, -1)).cumsum()
    obv_30 = obv.iloc[-30:]
    if len(obv_30) >= 5:
        obv_slope = np.polyfit(range(len(obv_30)), obv_30.values, 1)[0]
    else:
        obv_slope = 0

    # ATR trend (expanding or contracting)
    atr_series = _atr(ohlcv)
    if len(atr_series.dropna()) >= 30:
        atr_slope = np.polyfit(range(30), atr_series.iloc[-30:].values, 1)[0]
    else:
        atr_slope = 0

    # Recent max drawdown and max rally
    recent = close.iloc[-60:]
    peak = recent.cummax()
    drawdown = ((recent - peak) / peak).min()
    trough = recent.cummin()
    rally = ((recent - trough) / trough.replace(0, np.nan)).max()

    # Phase classification
    scores = {"accumulation": 0, "markup": 0, "distribution": 0, "markdown": 0}

    # Accumulation: post-decline, sideways, OBV rising, ATR contracting
    if drawdown < -0.15:
        scores["accumulation"] += 2
    if abs(annualized_trend) < 0.15:
        scores["accumulation"] += 1
    if obv_slope > 0:
        scores["accumulation"] += 2
    if atr_slope < 0:
        scores["accumulation"] += 1

    # Markup: uptrend, above MAs, volume expanding on advances
    if current > sma50 > sma200:
        scores["markup"] += 3
    if annualized_trend > 0.15:
        scores["markup"] += 2
    if obv_slope > 0:
        scores["markup"] += 1

    # Distribution: post-rally, sideways, OBV declining
    if rally > 0.20:
        scores["distribution"] += 2
    if abs(annualized_trend) < 0.15:
        scores["distribution"] += 1
    if obv_slope < 0:
        scores["distribution"] += 2
    if atr_slope > 0:
        scores["distribution"] += 1

    # Markdown: downtrend, below MAs
    if current < sma50 < sma200:
        scores["markdown"] += 3
    if annualized_trend < -0.15:
        scores["markdown"] += 2
    if obv_slope < 0:
        scores["markdown"] += 1

    phase = max(scores, key=scores.get)
    total_pts = sum(scores.values())
    confidence = scores[phase] / max(total_pts, 1)

    # Estimate phase duration
    duration = 30  # Default

    # Cycle score: bullish phase = high score
    cycle_map = {"accumulation": 80, "markup": 70, "distribution": 30, "markdown": 15}
    cycle_score = cycle_map.get(phase, 50)
    # Adjust by confidence
    cycle_score = 50 + (cycle_score - 50) * confidence

    return {
        "phase": phase,
        "confidence": round(confidence, 2),
        "duration_days": duration,
        "progress_pct": 50,  # Simplified
        "cycle_score": round(cycle_score, 1),
    }


def compute_earnings_cycle(symbol: str) -> dict:
    """Determine earnings cycle positioning."""
    today = date.today().isoformat()

    # Next earnings
    next_rows = query("""
        SELECT date FROM earnings_calendar
        WHERE symbol = ? AND date >= ? ORDER BY date ASC LIMIT 1
    """, [symbol, today])

    # Last earnings
    last_rows = query("""
        SELECT date FROM earnings_calendar
        WHERE symbol = ? AND date < ? ORDER BY date DESC LIMIT 1
    """, [symbol, today])

    days_to_next = None
    days_since_last = None
    last_surprise_pct = None
    earnings_drift_score = 50  # Default neutral

    if next_rows:
        days_to_next = (pd.Timestamp(next_rows[0]["date"]) - pd.Timestamp(today)).days

    if last_rows:
        days_since_last = (pd.Timestamp(today) - pd.Timestamp(last_rows[0]["date"])).days

    # Pre-earnings uncertainty
    if days_to_next and days_to_next < 14:
        earnings_drift_score = 50  # Uncertainty zone

    return {
        "days_to_next": days_to_next,
        "days_since_last": days_since_last,
        "last_surprise_pct": round(last_surprise_pct, 1) if last_surprise_pct else None,
        "earnings_drift_score": round(max(0, min(100, earnings_drift_score)), 1),
    }


def detect_volatility_cycle(ohlcv: pd.DataFrame) -> dict:
    """Classify volatility regime: low, normal, high."""
    close = ohlcv["close"]
    if len(close) < 60:
        return {"vol_regime": "normal", "regime_duration": 0, "vol_cycle_score": 50}

    log_rets = np.log(close / close.shift(1)).dropna()
    hv20 = float(log_rets.iloc[-20:].std() * np.sqrt(252))
    hv252 = float(log_rets.std() * np.sqrt(252)) if len(log_rets) >= 100 else hv20

    ratio = hv20 / hv252 if hv252 > 0 else 1.0

    if ratio < 0.75:
        vol_regime = "low"
        vol_score = 70  # Low vol = potential expansion ahead (opportunity)
    elif ratio > 1.25:
        vol_regime = "high"
        vol_score = 30  # High vol = elevated risk
    else:
        vol_regime = "normal"
        vol_score = 50

    # Count consecutive days in current regime
    rolling_hv = log_rets.rolling(20).std() * np.sqrt(252)
    rolling_hv = rolling_hv.dropna()
    duration = 0
    if len(rolling_hv) > 1:
        for i in range(len(rolling_hv) - 1, -1, -1):
            r = rolling_hv.iloc[i] / hv252 if hv252 > 0 else 1
            if vol_regime == "low" and r < 0.75:
                duration += 1
            elif vol_regime == "high" and r > 1.25:
                duration += 1
            elif vol_regime == "normal" and 0.75 <= r <= 1.25:
                duration += 1
            else:
                break

    return {
        "vol_regime": vol_regime,
        "regime_duration": duration,
        "vol_cycle_score": vol_score,
    }


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITE SCORING
# ═══════════════════════════════════════════════════════════════════════════

def compute_pattern_composite(
    regime_score: float,
    rotation_score: float,
    pattern_s: float,
    sr_levels: list[dict],
    vol_profile: dict,
    mr_setup: dict,
    momentum: dict,
    compression: dict,
    wyckoff: dict,
    earnings: dict,
    vol_cycle: dict,
    regime_ctx: dict,
) -> tuple[float, dict]:
    """Blend all layer scores into 0-100 composite.

    Returns: (composite_score, layer_scores_dict)
    """
    # Layer 3: Technical = avg of pattern, S/R quality, volume profile
    sr_quality = max((l["strength"] for l in sr_levels), default=0)
    tech_score = (pattern_s * 0.50 + min(100, sr_quality) * 0.20 + vol_profile.get("volume_profile_score", 50) * 0.30)

    # Layer 4: Statistical = blend of MR, momentum, compression
    # In bullish regime, weight momentum higher; in bearish, weight MR higher
    if regime_ctx.get("trend_filter") == "bullish":
        stat_score = mr_setup["mr_score"] * 0.25 + momentum["momentum_score"] * 0.50 + compression["compression_score"] * 0.25
    elif regime_ctx.get("trend_filter") == "bearish":
        stat_score = mr_setup["mr_score"] * 0.50 + momentum["momentum_score"] * 0.20 + compression["compression_score"] * 0.30
    else:
        stat_score = mr_setup["mr_score"] * 0.33 + momentum["momentum_score"] * 0.34 + compression["compression_score"] * 0.33

    # Layer 4.5: Cycles
    cycle_score = (
        wyckoff.get("cycle_score", 50) * 0.50
        + earnings.get("earnings_drift_score", 50) * 0.25
        + vol_cycle.get("vol_cycle_score", 50) * 0.25
    )

    layer_scores = {
        "L1_regime": round(regime_score, 1),
        "L2_rotation": round(rotation_score, 1),
        "L3_technical": round(tech_score, 1),
        "L4_statistical": round(stat_score, 1),
        "L4.5_cycles": round(cycle_score, 1),
    }

    # Weighted composite
    w = PATTERN_LAYER_WEIGHTS
    composite = (
        w["regime"] * regime_score
        + w["rotation"] * rotation_score
        + w["technical"] * tech_score
        + w["statistical"] * stat_score
        + w["cycles"] * cycle_score
    )

    return round(max(0, min(100, composite)), 1), layer_scores


# ═══════════════════════════════════════════════════════════════════════════
# MAIN SCAN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def scan_all(symbols: list[str] | None = None) -> list[dict]:
    """Run the full pattern scan on all symbols (or a subset).

    Returns list of result dicts ready for DB insertion.
    """
    print("  Loading price data...")
    price_matrix = _load_price_matrix()
    if price_matrix.empty:
        print("  ✗ No price data available")
        return []

    sector_map = _load_sector_map()

    # Layer 1: regime context (once for all)
    regime_ctx = compute_regime_context()
    r_score = _regime_score(regime_ctx)
    print(f"  Regime: {regime_ctx['regime']} (score={regime_ctx['regime_score']:.0f}), "
          f"VIX={regime_ctx['vix_level']:.1f} (pct={regime_ctx['vix_percentile']:.0f}), "
          f"trend={regime_ctx['trend_filter']}")

    # Layer 2: sector rotation (once for all)
    sector_rotation = compute_sector_rotation(price_matrix, sector_map)
    # Write sector rotation to DB
    today = date.today().isoformat()
    if sector_rotation:
        with get_conn() as conn:
            for sec, data in sector_rotation.items():
                conn.execute("""INSERT OR REPLACE INTO sector_rotation
                    (sector, date, rs_ratio, rs_momentum, quadrant, rotation_score)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (sec, today, data["rs_ratio"], data["rs_momentum"],
                     data["quadrant"], data["rotation_score"]))
        leading = [s for s, d in sector_rotation.items() if d["quadrant"] == "leading"]
        lagging = [s for s, d in sector_rotation.items() if d["quadrant"] == "lagging"]
        print(f"  Sector rotation: {len(sector_rotation)} sectors | "
              f"Leading: {leading[:3]} | Lagging: {lagging[:3]}")

    # Determine which symbols to scan
    if symbols is None:
        symbols = [s for s in price_matrix.columns if s in sector_map or s in price_matrix.columns]
    symbols = [s for s in symbols if s in price_matrix.columns]
    print(f"  Scanning {len(symbols)} symbols...")

    results = []
    squeezed = 0
    pattern_count = 0

    for i, symbol in enumerate(symbols):
        if (i + 1) % 100 == 0:
            print(f"    {i + 1}/{len(symbols)} scanned...")

        try:
            ohlcv = _load_ohlcv(symbol)
            if ohlcv.empty or len(ohlcv) < PATTERN_MIN_BARS * 2:
                continue

            # Layer 2: stock rotation
            stock_rot = compute_stock_rotation(symbol, price_matrix, sector_map)
            # Use stock's own sector rotation if available, else stock's own
            sec = sector_map.get(symbol, "")
            sec_rot = sector_rotation.get(sec, {})
            rot_score = stock_rot["rotation_score"]

            # Layer 3: patterns
            patterns = detect_chart_patterns(ohlcv)
            p_score = _pattern_score(patterns)
            sr_levels = compute_support_resistance(ohlcv)
            vol_profile = compute_volume_profile(ohlcv)
            if patterns:
                pattern_count += 1

            atr_val = _atr(ohlcv).iloc[-1] if len(ohlcv) >= 14 else 0
            sr_prox = _sr_proximity_label(sr_levels, ohlcv["close"].iloc[-1], atr_val)

            # Layer 4: stats
            mr = detect_mean_reversion_setups(ohlcv)
            mom = detect_momentum_persistence(ohlcv)
            comp = detect_volatility_compression(ohlcv)
            if comp["squeeze_active"]:
                squeezed += 1

            # Layer 4.5: cycles
            wyckoff = detect_wyckoff_phase(ohlcv)
            earnings = compute_earnings_cycle(symbol)
            vol_cycle = detect_volatility_cycle(ohlcv)

            # Composite
            composite, layer_scores = compute_pattern_composite(
                r_score, rot_score, p_score, sr_levels, vol_profile,
                mr, mom, comp, wyckoff, earnings, vol_cycle, regime_ctx,
            )

            # Top pattern label
            top_pattern = patterns[0]["pattern"] if patterns else None

            results.append({
                "symbol": symbol,
                "date": today,
                "regime": regime_ctx["regime"],
                "regime_score": regime_ctx["regime_score"],
                "vix_percentile": regime_ctx["vix_percentile"],
                "sector_quadrant": stock_rot["quadrant"],
                "rotation_score": rot_score,
                "rs_ratio": stock_rot["rs_ratio"],
                "rs_momentum": stock_rot["rs_momentum"],
                "patterns_detected": json.dumps(patterns) if patterns else None,
                "pattern_score": p_score,
                "sr_proximity": sr_prox,
                "volume_profile_score": vol_profile["volume_profile_score"],
                "hurst_exponent": mr["hurst"],
                "mr_score": mr["mr_score"],
                "momentum_score": mom["momentum_score"],
                "compression_score": comp["compression_score"],
                "squeeze_active": 1 if comp["squeeze_active"] else 0,
                "wyckoff_phase": wyckoff["phase"],
                "wyckoff_confidence": wyckoff["confidence"],
                "earnings_days_to_next": earnings["days_to_next"],
                "vol_regime": vol_cycle["vol_regime"],
                "pattern_scan_score": composite,
                "layer_scores": json.dumps(layer_scores),
            })

        except Exception as e:
            logger.warning(f"Pattern scan failed for {symbol}: {e}")
            continue

    print(f"  Scan complete: {len(results)} symbols scored, "
          f"{pattern_count} with patterns, {squeezed} in squeeze")

    return results
