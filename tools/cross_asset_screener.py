"""Cross-Asset Opportunity Screener — Druckenmiller Alpha System.

Multi-asset discovery engine across stocks, commodities, and crypto.
Finds fat-pitch opportunities using unified scoring with regime awareness.

Tables written:
  cross_asset_opportunities  (symbol, date, asset_class, ...)
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Optional

import numpy as np
import pandas as pd

from tools.db import get_conn, query, query_df, upsert_many

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Asset classification constants
# ---------------------------------------------------------------------------
CRYPTO_SYMBOLS: set[str] = {
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    "ADA-USD", "AVAX-USD", "DOT-USD", "AXS-USD",
}

COMMODITY_FUTURES: set[str] = {
    "CL=F", "GC=F", "SI=F", "NG=F", "HG=F", "ZW=F", "ZC=F",
    "BZ=F", "RB=F", "HO=F", "PA=F", "PL=F", "KC=F", "SB=F",
}

# Commodity → thematic label for cross-asset signals
COMMODITY_THEMES: dict[str, str] = {
    "CL=F": "Energy/Oil",      "BZ=F": "Energy/Oil",      "RB=F": "Energy/Refined",
    "HO=F": "Energy/Refined",  "NG=F": "Energy/Gas",      "GC=F": "Metals/Gold",
    "SI=F": "Metals/Silver",   "HG=F": "Metals/Copper",   "PA=F": "Metals/Palladium",
    "PL=F": "Metals/Platinum", "ZW=F": "Grains/Wheat",    "ZC=F": "Grains/Corn",
    "KC=F": "Softs/Coffee",    "SB=F": "Softs/Sugar",
}

# Sector → commodity theme alignment for cross-asset divergence signals
SECTOR_COMMODITY_MAP: dict[str, list[str]] = {
    "Energy":     ["Energy/Oil", "Energy/Gas", "Energy/Refined"],
    "Materials":  ["Metals/Copper", "Metals/Gold", "Grains/Wheat", "Grains/Corn"],
    "Industrials": ["Metals/Copper", "Energy/Oil"],
    "Consumer Staples": ["Grains/Wheat", "Grains/Corn", "Softs/Coffee", "Softs/Sugar"],
}

# Regime → asset class fit bonus/penalty (applied to regime_fit_score)
REGIME_FIT: dict[str, dict[str, float]] = {
    "strong_risk_on": {
        "equity_growth":    20.0,
        "equity_value":     -5.0,
        "equity_defensive": -10.0,
        "commodity_energy": -5.0,
        "commodity_gold":   -15.0,
        "commodity_grain":  -5.0,
        "commodity_copper":  10.0,
        "crypto":            20.0,
    },
    "risk_on": {
        "equity_growth":    10.0,
        "equity_value":     0.0,
        "equity_defensive": -5.0,
        "commodity_energy":  0.0,
        "commodity_gold":   -10.0,
        "commodity_grain":   0.0,
        "commodity_copper":  5.0,
        "crypto":            10.0,
    },
    "neutral": {
        "equity_growth":    0.0,
        "equity_value":     0.0,
        "equity_defensive": 0.0,
        "commodity_energy": 0.0,
        "commodity_gold":   0.0,
        "commodity_grain":  0.0,
        "commodity_copper": 0.0,
        "crypto":           0.0,
    },
    "risk_off": {
        "equity_growth":    -15.0,
        "equity_value":      5.0,
        "equity_defensive":  10.0,
        "commodity_energy":  5.0,
        "commodity_gold":    20.0,
        "commodity_grain":   5.0,
        "commodity_copper":  -5.0,
        "crypto":           -20.0,
    },
    "strong_risk_off": {
        "equity_growth":    -25.0,
        "equity_value":      10.0,
        "equity_defensive":  20.0,
        "commodity_energy":  0.0,
        "commodity_gold":    30.0,
        "commodity_grain":   10.0,
        "commodity_copper": -15.0,
        "crypto":           -30.0,
    },
}

# Defensive / growth sector classification
DEFENSIVE_SECTORS = {"Consumer Staples", "Utilities", "Health Care", "Real Estate"}
GROWTH_SECTORS    = {"Information Technology", "Communication Services", "Consumer Discretionary"}

# ---------------------------------------------------------------------------
# Opportunity score weights by asset class
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "Equity": {
        "technical":    0.35,
        "fundamental":  0.35,
        "momentum":     0.20,
        "regime_fit":   0.10,
    },
    "Commodity": {
        "technical":    0.50,
        "fundamental":  0.00,
        "momentum":     0.30,
        "regime_fit":   0.20,
    },
    "Crypto": {
        "technical":    0.60,
        "fundamental":  0.00,
        "momentum":     0.30,
        "regime_fit":   0.10,
    },
}

# Fat-pitch thresholds
FAT_PITCH_EQUITY_TECH     = 70.0
FAT_PITCH_EQUITY_FUND     = 50.0
FAT_PITCH_COMMODITY_TECH  = 75.0
FAT_PITCH_CRYPTO_TECH     = 75.0

# Relative value — top quartile threshold
TOP_QUARTILE = 0.75


# ---------------------------------------------------------------------------
# 1. Asset class helpers
# ---------------------------------------------------------------------------

def _classify(symbol: str) -> str:
    """Return 'Equity', 'Commodity', or 'Crypto'."""
    if symbol in CRYPTO_SYMBOLS or symbol.endswith("-USD") or symbol.endswith("-USDT"):
        return "Crypto"
    if symbol in COMMODITY_FUTURES or symbol.endswith("=F"):
        return "Commodity"
    return "Equity"


def _commodity_subclass(symbol: str) -> str:
    """Return commodity theme key for regime_fit lookup."""
    theme = COMMODITY_THEMES.get(symbol, "")
    if "Oil" in theme or "Refined" in theme:
        return "commodity_energy"
    if "Gold" in theme:
        return "commodity_gold"
    if "Copper" in theme:
        return "commodity_copper"
    if "Gas" in theme:
        return "commodity_energy"
    return "commodity_grain"


def _equity_subclass(sector: Optional[str]) -> str:
    if sector in DEFENSIVE_SECTORS:
        return "equity_defensive"
    if sector in GROWTH_SECTORS:
        return "equity_growth"
    return "equity_value"


# ---------------------------------------------------------------------------
# 2. Price data & momentum
# ---------------------------------------------------------------------------

def _load_price_data() -> pd.DataFrame:
    """Load the most recent 260 trading days of price data for all symbols."""
    logger.info("Loading price data …")
    df = query_df("""
        SELECT p.symbol, p.date, p.adj_close
        FROM price_data p
        INNER JOIN (
            SELECT symbol, MAX(date) AS latest FROM price_data GROUP BY symbol
        ) m ON p.symbol = m.symbol AND p.date >= date(m.latest, '-260 days')
        ORDER BY p.symbol, p.date
    """)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"])
    return df


def _compute_momentum(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each symbol compute momentum metrics from price history.
    Returns one row per symbol with:
      momentum_5d, momentum_20d, momentum_60d,
      rsi_14, week52_pct,  (all float, NaN if insufficient data)
    """
    records = []
    for symbol, grp in df.groupby("symbol", sort=False):
        grp = grp.dropna(subset=["adj_close"]).set_index("date").sort_index()
        prices = grp["adj_close"]
        n = len(prices)
        rec: dict = {"symbol": symbol}

        # Returns
        rec["momentum_5d"]  = float(prices.iloc[-1] / prices.iloc[-6]  - 1) if n >= 6  else float("nan")
        rec["momentum_20d"] = float(prices.iloc[-1] / prices.iloc[-21] - 1) if n >= 21 else float("nan")
        rec["momentum_60d"] = float(prices.iloc[-1] / prices.iloc[-61] - 1) if n >= 61 else float("nan")

        # RSI-14
        if n >= 15:
            delta  = prices.diff()
            gain   = delta.clip(lower=0).rolling(14).mean()
            loss   = (-delta.clip(upper=0)).rolling(14).mean()
            rs     = gain / loss.replace(0, float("nan"))
            rsi    = 100 - 100 / (1 + rs)
            rec["rsi_14"] = float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else float("nan")
        else:
            rec["rsi_14"] = float("nan")

        # 52-week percentile (where current price falls in the 52w range)
        if n >= 5:
            window = prices.iloc[max(0, n - 252):]
            lo, hi = window.min(), window.max()
            rec["week52_pct"] = float((prices.iloc[-1] - lo) / (hi - lo)) if hi > lo else 0.5
        else:
            rec["week52_pct"] = float("nan")

        records.append(rec)

    return pd.DataFrame(records)


def _momentum_score(row: pd.Series) -> float:
    """Convert raw momentum metrics into a 0–100 score."""
    score = 50.0  # neutral baseline

    # 5d: ±5% maps to ±20 points
    m5 = row.get("momentum_5d")
    if m5 is not None and not pd.isna(m5):
        score += float(np.clip(m5 / 0.05 * 20, -25, 25))

    # 20d: ±10% maps to ±15 points
    m20 = row.get("momentum_20d")
    if m20 is not None and not pd.isna(m20):
        score += float(np.clip(m20 / 0.10 * 15, -20, 20))

    # 60d: ±20% maps to ±10 points
    m60 = row.get("momentum_60d")
    if m60 is not None and not pd.isna(m60):
        score += float(np.clip(m60 / 0.20 * 10, -15, 15))

    # RSI: overbought/oversold ±5 points
    rsi = row.get("rsi_14")
    if rsi is not None and not pd.isna(rsi):
        if rsi < 30:
            score += 5   # oversold bounce potential
        elif rsi > 70:
            score -= 5   # overbought caution

    # 52-week position: near low is opportunity (+5), near high is stretched (-3)
    wp = row.get("week52_pct")
    if wp is not None and not pd.isna(wp):
        if wp < 0.20:
            score += 5
        elif wp > 0.85:
            score -= 3

    return float(np.clip(score, 0.0, 100.0))


# ---------------------------------------------------------------------------
# 3. Load existing scores from DB
# ---------------------------------------------------------------------------

def _load_technical_scores() -> dict[str, float]:
    """Latest total_score from technical_scores per symbol, normalised 0–100."""
    rows = query("""
        SELECT t.symbol, t.total_score
        FROM technical_scores t
        INNER JOIN (SELECT symbol, MAX(date) AS mx FROM technical_scores GROUP BY symbol) m
          ON t.symbol = m.symbol AND t.date = m.mx
        WHERE t.total_score IS NOT NULL
    """)
    # total_score is already 0–100 (sum of 6 sub-scores each 0–25 → max ~100)
    return {r["symbol"]: float(np.clip(r["total_score"], 0, 100)) for r in rows}


def _load_fundamental_scores() -> dict[str, float]:
    """Latest total_score from fundamental_scores per symbol, normalised 0–100."""
    rows = query("""
        SELECT f.symbol, f.total_score
        FROM fundamental_scores f
        INNER JOIN (SELECT symbol, MAX(date) AS mx FROM fundamental_scores GROUP BY symbol) m
          ON f.symbol = m.symbol AND f.date = m.mx
        WHERE f.total_score IS NOT NULL
    """)
    return {r["symbol"]: float(np.clip(r["total_score"], 0, 100)) for r in rows}


def _load_convergence_scores() -> dict[str, tuple[float, str]]:
    """Latest (convergence_score, conviction_level) from convergence_signals."""
    rows = query("""
        SELECT c.symbol, c.convergence_score, c.conviction_level
        FROM convergence_signals c
        INNER JOIN (SELECT symbol, MAX(date) AS mx FROM convergence_signals GROUP BY symbol) m
          ON c.symbol = m.symbol AND c.date = m.mx
        WHERE c.convergence_score IS NOT NULL
    """)
    return {r["symbol"]: (float(r["convergence_score"]), r["conviction_level"] or "") for r in rows}


def _load_stock_universe() -> dict[str, dict]:
    """sector + name for equity symbols."""
    rows = query("SELECT symbol, name, sector, industry FROM stock_universe")
    return {r["symbol"]: {"name": r.get("name", ""), "sector": r.get("sector", ""), "industry": r.get("industry", "")} for r in rows}


# ---------------------------------------------------------------------------
# 4. Regime
# ---------------------------------------------------------------------------

def _load_regime() -> str:
    rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    if rows:
        return rows[0]["regime"] or "neutral"
    return "neutral"


def _regime_fit_score(symbol: str, asset_class: str, sector: Optional[str], regime: str) -> float:
    """Return regime fit bonus on a 0–100 scale (50 = neutral)."""
    fit_map = REGIME_FIT.get(regime, REGIME_FIT["neutral"])

    if asset_class == "Crypto":
        delta = fit_map.get("crypto", 0.0)
    elif asset_class == "Commodity":
        subclass = _commodity_subclass(symbol)
        delta = fit_map.get(subclass, 0.0)
    else:
        subclass = _equity_subclass(sector)
        delta = fit_map.get(subclass, 0.0)

    # Delta ∈ [-30, +30] → score ∈ [20, 80]
    return float(np.clip(50.0 + delta, 0.0, 100.0))


# ---------------------------------------------------------------------------
# 5. Unified opportunity score
# ---------------------------------------------------------------------------

def _opportunity_score(
    asset_class: str,
    tech_score: float,
    fund_score: float,
    mom_score: float,
    regime_score: float,
) -> float:
    weights = SCORE_WEIGHTS[asset_class]
    score = (
        tech_score    * weights["technical"]
        + fund_score  * weights["fundamental"]
        + mom_score   * weights["momentum"]
        + regime_score * weights["regime_fit"]
    )
    return float(np.clip(score, 0.0, 100.0))


# ---------------------------------------------------------------------------
# 6. Fat-pitch detection
# ---------------------------------------------------------------------------

def _detect_fat_pitch(
    symbol: str,
    asset_class: str,
    sector: Optional[str],
    tech_score: float,
    fund_score: float,
    momentum_5d: float,
    momentum_20d: float,
    regime: str,
    btc_momentum: float,
) -> tuple[bool, str]:
    """Return (is_fat_pitch, reason_str)."""
    reasons: list[str] = []

    if asset_class == "Equity":
        if tech_score >= FAT_PITCH_EQUITY_TECH and fund_score >= FAT_PITCH_EQUITY_FUND:
            uptrend = not pd.isna(momentum_20d) and momentum_20d >= 0
            if uptrend:
                reasons.append(f"Tech:{tech_score:.0f} + Fund:{fund_score:.0f} + uptrend")
            else:
                reasons.append(f"Tech:{tech_score:.0f} + Fund:{fund_score:.0f} (no uptrend yet)")
            if reasons:
                return True, " | ".join(reasons)

    elif asset_class == "Commodity":
        if tech_score >= FAT_PITCH_COMMODITY_TECH:
            commodity_regimes = {"risk_off", "strong_risk_off", "neutral", "risk_on", "strong_risk_on"}
            commodity_confirmed = regime in {"risk_off", "strong_risk_off"} or (
                symbol in {"CL=F", "BZ=F", "NG=F"} and regime in {"risk_on", "strong_risk_on"}
            ) or symbol in {"GC=F", "SI=F"}  # gold/silver are always fat-pitch at tech≥75
            if commodity_confirmed or tech_score >= 82:
                reasons.append(f"Tech:{tech_score:.0f} + macro confirms commodity trade")
                return True, " | ".join(reasons)

    elif asset_class == "Crypto":
        if tech_score >= FAT_PITCH_CRYPTO_TECH:
            is_risk_on = regime in {"risk_on", "strong_risk_on"}
            if is_risk_on and not pd.isna(btc_momentum) and btc_momentum > 0:
                reasons.append(f"Tech:{tech_score:.0f} + risk_on regime + BTC momentum positive")
                return True, " | ".join(reasons)

    return False, ""


# ---------------------------------------------------------------------------
# 7. Cross-asset divergence signals
# ---------------------------------------------------------------------------

def _compute_cross_asset_signals(df: pd.DataFrame, universe: dict) -> list[str]:
    """
    Identify cross-asset divergences that hint at sector rotations.
    Returns a list of human-readable signal strings.
    """
    signals: list[str] = []

    # Threshold: opportunity score ≥ 65 = "strong"
    STRONG = 65.0

    # Build commodity theme → avg score map
    commodity_theme_scores: dict[str, list[float]] = {}
    for _, row in df[df["asset_class"] == "Commodity"].iterrows():
        theme = COMMODITY_THEMES.get(row["symbol"], "Other")
        commodity_theme_scores.setdefault(theme, []).append(row["opportunity_score"])
    commodity_theme_avg = {t: float(np.mean(v)) for t, v in commodity_theme_scores.items()}

    # Build equity sector → avg score map
    sector_scores: dict[str, list[float]] = {}
    eq = df[df["asset_class"] == "Equity"]
    for _, row in eq.iterrows():
        sym = row["symbol"]
        sector = universe.get(sym, {}).get("sector", "") or ""
        if sector:
            sector_scores.setdefault(sector, []).append(row["opportunity_score"])
    sector_avg = {s: float(np.mean(v)) for s, v in sector_scores.items()}

    # Check each sector–commodity pairing
    for sector, themes in SECTOR_COMMODITY_MAP.items():
        seq = sector_avg.get(sector, 50.0)
        for theme in themes:
            ceq = commodity_theme_avg.get(theme, 50.0)
            if seq >= STRONG and ceq >= STRONG:
                signals.append(
                    f"  {sector} STRONG (equities, {seq:.0f}) + {theme} STRONG ({ceq:.0f})"
                    f" → {'Inflation rotation' if 'Grain' in theme else 'Infrastructure trade'}"
                )
            elif seq >= STRONG and ceq < 40.0:
                signals.append(
                    f"  {sector} equities STRONG ({seq:.0f}) but {theme} WEAK ({ceq:.0f})"
                    f" → Equity-led, commodity lagging — watch for commodity catch-up"
                )
            elif ceq >= STRONG and seq < 40.0:
                signals.append(
                    f"  {theme} STRONG ({ceq:.0f}) but {sector} equities WEAK ({seq:.0f})"
                    f" → Commodity leading — rotation into {sector} equities likely"
                )

    # Crypto vs equities divergence
    crypto_avg = df[df["asset_class"] == "Crypto"]["opportunity_score"].mean()
    equity_avg = df[df["asset_class"] == "Equity"]["opportunity_score"].mean()
    if not pd.isna(crypto_avg) and not pd.isna(equity_avg):
        if crypto_avg - equity_avg > 15:
            signals.append(
                f"  Crypto OUTPERFORMING equities (+{crypto_avg - equity_avg:.0f} pts)"
                f" → Risk appetite high; watch for equity catch-up or crypto reversal"
            )
        elif equity_avg - crypto_avg > 15:
            signals.append(
                f"  Equities OUTPERFORMING crypto (+{equity_avg - crypto_avg:.0f} pts)"
                f" → Capital rotating into fundamentals; risk-off crypto pressure"
            )

    return signals


# ---------------------------------------------------------------------------
# 8. Conviction label from opportunity score
# ---------------------------------------------------------------------------

def _conviction_label(score: float, is_fat_pitch: bool) -> str:
    if is_fat_pitch and score >= 80:
        return "FAT_PITCH_HIGH"
    if is_fat_pitch:
        return "FAT_PITCH"
    if score >= 75:
        return "HIGH"
    if score >= 60:
        return "NOTABLE"
    if score >= 45:
        return "WATCH"
    return "LOW"


# ---------------------------------------------------------------------------
# 9. Main run()
# ---------------------------------------------------------------------------

def run() -> None:
    """Run the cross-asset screener, save results to DB, and print summary."""
    from tools.db import init_db
    init_db()

    today = date.today().isoformat()
    logger.info("=== CROSS-ASSET OPPORTUNITY SCREENER — %s ===", today)

    # Load regime
    regime = _load_regime()
    logger.info("Regime: %s", regime)

    # Load price data and compute momentum
    price_df = _load_price_data()
    if price_df.empty:
        logger.error("No price data found — aborting.")
        return

    mom_df = _compute_momentum(price_df)
    mom_df = mom_df.set_index("symbol")

    # BTC momentum for crypto fat-pitch check
    btc_mom = float(mom_df.loc["BTC-USD", "momentum_20d"]) if "BTC-USD" in mom_df.index else float("nan")

    # Load scores
    tech_scores  = _load_technical_scores()
    fund_scores  = _load_fundamental_scores()
    conv_scores  = _load_convergence_scores()
    universe     = _load_stock_universe()

    # All symbols
    all_symbols = price_df["symbol"].unique().tolist()
    logger.info("Total symbols: %d", len(all_symbols))

    # Build master dataframe
    rows: list[dict] = []
    for sym in all_symbols:
        asset_class = _classify(sym)
        sector      = universe.get(sym, {}).get("sector") or None

        tech  = tech_scores.get(sym, 50.0)   # default 50 if missing (neutral)
        fund  = fund_scores.get(sym, 0.0)    # 0 for non-equities (weight=0)
        conv, conviction_str = conv_scores.get(sym, (None, ""))

        mom_row     = mom_df.loc[sym] if sym in mom_df.index else pd.Series(dtype=float)
        mom5        = float(mom_row.get("momentum_5d",  float("nan")))
        mom20       = float(mom_row.get("momentum_20d", float("nan")))
        mom60       = float(mom_row.get("momentum_60d", float("nan")))
        mom_sc      = _momentum_score(mom_row)

        reg_fit     = _regime_fit_score(sym, asset_class, sector, regime)

        opp_score   = _opportunity_score(asset_class, tech, fund, mom_sc, reg_fit)

        is_fp, fp_reason = _detect_fat_pitch(
            sym, asset_class, sector, tech, fund,
            mom5, mom20, regime, btc_mom
        )

        # Combine convergence bonus: if convergence HIGH, nudge score +3
        if conv is not None and conviction_str in ("HIGH", "NOTABLE"):
            opp_score = float(np.clip(opp_score + (3.0 if conviction_str == "HIGH" else 1.5), 0, 100))

        rows.append({
            "symbol":            sym,
            "asset_class":       asset_class,
            "sector":            sector or "",
            "theme":             COMMODITY_THEMES.get(sym, "") if asset_class == "Commodity" else (sector or ""),
            "opportunity_score": round(opp_score, 2),
            "technical_score":   round(tech, 2),
            "fundamental_score": round(fund, 2),
            "momentum_5d":       round(mom5, 4)  if not pd.isna(mom5)  else None,
            "momentum_20d":      round(mom20, 4) if not pd.isna(mom20) else None,
            "momentum_60d":      round(mom60, 4) if not pd.isna(mom60) else None,
            "momentum_score":    round(mom_sc, 2),
            "regime_fit_score":  round(reg_fit, 2),
            "is_fat_pitch":      1 if is_fp else 0,
            "fat_pitch_reason":  fp_reason,
            "conviction":        _conviction_label(opp_score, is_fp),
            "convergence_score": round(conv, 2) if conv is not None else None,
        })

    master = pd.DataFrame(rows)

    # Relative value rank within asset class (percentile, 0–1)
    master["relative_value_rank"] = master.groupby("asset_class")["opportunity_score"].rank(pct=True)

    # Top-quartile flag
    master["is_top_quartile"] = master["relative_value_rank"] >= TOP_QUARTILE

    # Cross-asset signals
    cross_signals = _compute_cross_asset_signals(master, universe)

    # Persist to DB
    _save_to_db(master, today)

    # Print report
    _print_report(master, regime, cross_signals)


# ---------------------------------------------------------------------------
# 10. DB persistence
# ---------------------------------------------------------------------------

def _save_to_db(df: pd.DataFrame, today: str) -> None:
    """Upsert results into cross_asset_opportunities."""
    cols = (
        "symbol", "date", "asset_class", "sector",
        "opportunity_score", "technical_score", "fundamental_score",
        "momentum_5d", "momentum_20d", "momentum_60d",
        "regime_fit_score", "relative_value_rank",
        "is_fat_pitch", "fat_pitch_reason",
        "conviction", "details",
    )

    rows = []
    for _, r in df.iterrows():
        details = json.dumps({
            "momentum_score":    r.get("momentum_score"),
            "convergence_score": r.get("convergence_score"),
            "theme":             r.get("theme", ""),
            "is_top_quartile":   bool(r.get("is_top_quartile", False)),
        })
        rows.append((
            r["symbol"],
            today,
            r["asset_class"],
            r.get("sector", ""),
            r["opportunity_score"],
            r["technical_score"],
            r["fundamental_score"],
            r.get("momentum_5d"),
            r.get("momentum_20d"),
            r.get("momentum_60d"),
            r["regime_fit_score"],
            r["relative_value_rank"],
            int(r["is_fat_pitch"]),
            r.get("fat_pitch_reason", ""),
            r["conviction"],
            details,
        ))

    if rows:
        upsert_many("cross_asset_opportunities", list(cols), rows)
        logger.info("Saved %d opportunities to cross_asset_opportunities.", len(rows))


# ---------------------------------------------------------------------------
# 11. Report printer
# ---------------------------------------------------------------------------

def _fmt_mom(val) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "   n/a"
    return f"{val * 100:+.1f}%"


def _print_report(df: pd.DataFrame, regime: str, cross_signals: list[str]) -> None:
    fat_pitches  = df[df["is_fat_pitch"] == 1]
    total_assets = len(df)
    n_fp         = len(fat_pitches)

    header = (
        f"\n{'=' * 68}\n"
        f"  CROSS-ASSET OPPORTUNITY SCREEN\n"
        f"  Regime: {regime.upper():20s} | Assets: {total_assets} | Fat Pitches: {n_fp}\n"
        f"{'=' * 68}"
    )
    print(header)

    # Top 10 overall
    top10 = df.nlargest(10, "opportunity_score")
    print("\nTOP OPPORTUNITIES (ALL CLASSES):")
    for rank, (_, row) in enumerate(top10.iterrows(), 1):
        fp_tag = " | FAT PITCH" if row["is_fat_pitch"] else ""
        mom_tag = _fmt_mom(row.get("momentum_20d"))
        fund_part = f" Fund:{row['fundamental_score']:.0f}" if row["asset_class"] == "Equity" else ""
        print(
            f"  {rank:2d}. {row['symbol']:<10s} | {row['asset_class']:<10s}"
            f" | Score: {row['opportunity_score']:5.1f}{fp_tag}"
            f" | Tech:{row['technical_score']:.0f}{fund_part} Mom:{mom_tag}"
        )

    # Top 5 per asset class
    for cls in ["Equity", "Commodity", "Crypto"]:
        sub = df[df["asset_class"] == cls].nlargest(5, "opportunity_score")
        if sub.empty:
            continue
        print(f"\nTOP {cls.upper()} OPPORTUNITIES:")
        for _, row in sub.iterrows():
            fp_tag = " ★" if row["is_fat_pitch"] else "  "
            sector_tag = f" | {row['sector']}" if row["sector"] else ""
            mom_tag = _fmt_mom(row.get("momentum_20d"))
            fund_part = f" Fund:{row['fundamental_score']:.0f}" if cls == "Equity" else ""
            print(
                f"  {fp_tag} {row['symbol']:<10s}{sector_tag:<30s}"
                f" Score:{row['opportunity_score']:5.1f}"
                f" Tech:{row['technical_score']:.0f}{fund_part} Mom:{mom_tag}"
            )

    # Fat pitches
    if not fat_pitches.empty:
        print(f"\nFAT PITCHES ({n_fp}):")
        for _, row in fat_pitches.sort_values("opportunity_score", ascending=False).iterrows():
            label = row.get("sector") or COMMODITY_THEMES.get(row["symbol"], row["asset_class"])
            print(
                f"  {row['symbol']:<10s} — {label:<30s}"
                f" Score:{row['opportunity_score']:5.1f}"
                f" | {row.get('fat_pitch_reason', '')}"
            )
    else:
        print("\nFAT PITCHES: None detected")

    # Cross-asset signals
    print("\nCROSS-ASSET SIGNALS:")
    if cross_signals:
        for sig in cross_signals:
            print(sig)
    else:
        print("  No significant cross-asset divergences detected.")

    # Relative value leaders (top quartile summary)
    tq = df[df["is_top_quartile"]]
    eq_tq  = len(tq[tq["asset_class"] == "Equity"])
    cm_tq  = len(tq[tq["asset_class"] == "Commodity"])
    cr_tq  = len(tq[tq["asset_class"] == "Crypto"])
    print(f"\nTOP-QUARTILE ASSETS: {len(tq)} total"
          f"  (Equity: {eq_tq}  Commodity: {cm_tq}  Crypto: {cr_tq})")

    print("=" * 68 + "\n")


# ---------------------------------------------------------------------------
# DB migration: ensure cross_asset_opportunities table exists
# This is also called from db.py init_db() — but we add it here defensively.
# ---------------------------------------------------------------------------

def _ensure_table() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cross_asset_opportunities (
            symbol              TEXT,
            date                TEXT,
            asset_class         TEXT,
            sector              TEXT,
            opportunity_score   REAL,
            technical_score     REAL,
            fundamental_score   REAL,
            momentum_5d         REAL,
            momentum_20d        REAL,
            momentum_60d        REAL,
            regime_fit_score    REAL,
            relative_value_rank REAL,
            is_fat_pitch        INTEGER DEFAULT 0,
            fat_pitch_reason    TEXT,
            conviction          TEXT,
            details             TEXT,
            PRIMARY KEY (symbol, date)
        )
    """)
    conn.commit()
    conn.close()


# Run table creation on import (safe — CREATE IF NOT EXISTS)
try:
    _ensure_table()
except Exception as _e:
    logger.warning("Could not ensure cross_asset_opportunities table: %s", _e)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    run()
