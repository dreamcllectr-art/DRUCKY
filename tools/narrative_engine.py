"""Narrative Engine — Institutional Macro Narrative Detection & Asset Mapping.

Detects which of 12 institutional-grade macro narratives are forming in real-time
data and maps each theme to the cheapest quality-adjusted exposure across all asset
classes. Scores each narrative on strength (macro confirmation), crowding (how
priced-in), and overall opportunity.

Run standalone:
    /tmp/druck_venv/bin/python -m tools.narrative_engine
"""

import json
import logging
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.db import init_db, query, upsert_many

logger = logging.getLogger(__name__)

TODAY = date.today().isoformat()

# ---------------------------------------------------------------------------
# Narrative Definitions
# ---------------------------------------------------------------------------
NARRATIVES: dict[str, dict[str, Any]] = {
    "commodity_supercycle": {
        "name": "Commodity Supercycle",
        "description": "Structural supply constraints + EM demand + reshoring driving multi-year commodity bull",
        "macro_conditions": ["yield_curve_steepening", "dollar_weakening", "inflation_above_target"],
        "leading_assets": {
            "equities": ["CF", "MOS", "NUE", "FCX", "CLF", "LYB", "DOW", "BHP", "VALE"],
            "commodities": ["CL=F", "GC=F", "ZW=F", "ZC=F", "HG=F"],
            "crypto": [],
        },
        "confirming_indicators": ["energy_prices_rising", "dollar_index_falling", "EM_growth_accelerating"],
        "macro_keys": {
            "yield_curve_10y3m": ("positive", 0.0),   # (direction, threshold)
            "breakeven_10y": ("positive", 2.0),        # inflation above 2%
            "T10Y2Y": ("positive", 0.0),               # steepening
        },
    },
    "ai_infrastructure": {
        "name": "AI Infrastructure Buildout",
        "description": "Exponential data center + power + cooling + chip demand from AI adoption",
        "macro_conditions": ["tech_capex_rising", "power_demand_growth"],
        "leading_assets": {
            "equities": ["NVDA", "VST", "CEG", "ETR", "SMCI", "ANET", "CDNS", "KLAC", "LRCX", "ON"],
            "commodities": ["HG=F"],
            "crypto": ["ETH-USD"],
        },
        "macro_keys": {
            "core_capex_orders": ("positive", 0.0),    # rising capex orders
            "industrial_production": ("positive", 0.0),
        },
    },
    "reshoring_manufacturing": {
        "name": "Reshoring & Manufacturing Renaissance",
        "description": "US manufacturing expansion driven by CHIPS Act, IRA, and supply chain diversification",
        "macro_conditions": ["capex_rising", "industrial_production_growing"],
        "leading_assets": {
            "equities": ["CAT", "DE", "EMR", "ROK", "AME", "GE", "HON", "ITW", "PH", "ETN"],
            "commodities": ["HG=F", "ZW=F"],
            "crypto": [],
        },
        "macro_keys": {
            "industrial_production": ("positive", 0.0),
            "core_capex_orders": ("positive", 0.0),
            "nonfarm_payrolls": ("positive", 0.0),
        },
    },
    "rate_normalization": {
        "name": "Rate Normalization / Cut Cycle",
        "description": "Fed cutting cycle benefits rate-sensitive sectors and long duration assets",
        "macro_conditions": ["fed_funds_falling", "yield_curve_steepening", "inflation_declining"],
        "leading_assets": {
            "equities": ["XLRE", "BXP", "SPG", "O", "WELL", "KRE", "USB", "HBAN"],
            "commodities": ["GC=F"],
            "crypto": ["BTC-USD"],
        },
        "macro_keys": {
            "federal_funds": ("negative", 0.0),        # falling fed funds
            "yield_curve_10y3m": ("positive", 0.0),    # steepening
            "core_cpi": ("negative", 0.0),             # inflation declining
        },
    },
    "energy_transition": {
        "name": "Energy Transition & Electrification",
        "description": "Structural shift to clean energy creating multi-decade demand for solar, wind, batteries, copper",
        "macro_conditions": ["carbon_prices_rising", "policy_tailwind"],
        "leading_assets": {
            "equities": ["FSLR", "ENPH", "SEDG", "NEE", "ORMAT", "BEP", "CWEN", "ALB", "LTHM"],
            "commodities": ["HG=F", "SI=F"],
            "crypto": [],
        },
        "macro_keys": {
            "industrial_production": ("positive", 0.0),
            "building_permits": ("positive", 0.0),
        },
    },
    "defense_rearmament": {
        "name": "Defense Rearmament Supercycle",
        "description": "NATO budget increases + conflict premium + cyber spending secular growth",
        "macro_conditions": ["geopolitical_tensions_high", "defense_budgets_rising"],
        "leading_assets": {
            "equities": ["LMT", "RTX", "NOC", "GD", "LHX", "LDOS", "SAIC", "CACI", "CRWD", "PANW"],
            "commodities": [],
            "crypto": [],
        },
        "macro_keys": {
            "hy_oas": ("negative", 0.0),               # spreads not blowing out = defense spending sustained
            "stl_fin_stress": ("negative", 0.0),
        },
    },
    "dollar_debasement": {
        "name": "Dollar Debasement / Real Assets",
        "description": "Fiscal excess + debt monetization drives flight to real assets and inflation hedges",
        "macro_conditions": ["deficit_expanding", "debt_gdp_rising", "fed_balance_sheet_expanding"],
        "leading_assets": {
            "equities": ["NEM", "GOLD", "AEM", "WPM", "RGLD", "FNV"],
            "commodities": ["GC=F", "SI=F", "CL=F"],
            "crypto": ["BTC-USD"],
        },
        "macro_keys": {
            "fed_balance_sheet": ("positive", 0.0),    # expanding balance sheet
            "breakeven_10y": ("positive", 2.0),
            "m2": ("positive", 0.0),
        },
    },
    "consumer_bifurcation": {
        "name": "Consumer Bifurcation",
        "description": "High-end consumer resilient while low-end stressed — bifurcation creates relative value",
        "macro_conditions": ["consumer_sentiment_mixed", "savings_rate_declining_low_end"],
        "leading_assets": {
            "equities": ["LVMH", "TPR", "RL", "CPRI", "DG", "DLTR", "COST", "WMT"],
            "commodities": [],
            "crypto": [],
        },
        "macro_keys": {
            "umich_sentiment": ("negative", 0.0),      # declining sentiment = bifurcation
            "retail_sales": ("positive", 0.0),         # but retail still holding
        },
    },
    "healthcare_innovation": {
        "name": "Healthcare Innovation Cycle",
        "description": "GLP-1, gene therapy, AI diagnostics creating multi-year growth runway for select biotech/pharma",
        "macro_conditions": ["healthcare_spend_growing", "aging_demographics"],
        "leading_assets": {
            "equities": ["LLY", "NVO", "REGN", "VRTX", "GILD", "BIIB", "INCY", "EXEL", "RCUS"],
            "commodities": [],
            "crypto": [],
        },
        "macro_keys": {
            "industrial_production": ("positive", 0.0),
            "nonfarm_payrolls": ("positive", 0.0),
        },
    },
    "credit_stress": {
        "name": "Credit Stress Cycle",
        "description": "Rising defaults + HY spread widening + regional bank stress = defensive rotation",
        "macro_conditions": ["hy_spreads_widening", "defaults_rising", "credit_conditions_tightening"],
        "leading_assets": {
            "equities": ["JPM", "GS", "MS", "WFC"],
            "commodities": ["GC=F"],
            "crypto": [],
        },
        "macro_keys": {
            "hy_oas": ("positive", 400.0),             # HY spreads above 400bps = stress
            "stl_fin_stress": ("positive", 0.5),       # STLFS above 0.5 = elevated stress
            "nfci": ("positive", 0.0),                 # NFCI above 0 = tighter conditions
        },
    },
    "geopolitical_fragmentation": {
        "name": "Geopolitical Fragmentation",
        "description": "Deglobalization + friend-shoring + food/energy security premium across supply chains",
        "macro_conditions": ["trade_volumes_declining", "commodity_price_volatility_high"],
        "leading_assets": {
            "equities": ["ADM", "BG", "TSN", "SQM", "MP", "CTRA", "DVN", "PXD"],
            "commodities": ["ZW=F", "ZC=F", "CL=F", "NG=F"],
            "crypto": [],
        },
        "macro_keys": {
            "hy_oas": ("positive", 350.0),
            "breakeven_10y": ("positive", 2.0),
            "stl_fin_stress": ("positive", 0.0),
        },
    },
    "crypto_adoption": {
        "name": "Crypto Institutional Adoption",
        "description": "ETF flows + institutional treasury allocation + DeFi maturation driving structural crypto demand",
        "macro_conditions": ["risk_on_regime", "dollar_weakening", "inflation_above_target"],
        "leading_assets": {
            "equities": ["COIN", "MSTR", "MARA", "RIOT"],
            "commodities": [],
            "crypto": ["BTC-USD", "ETH-USD", "SOL-USD"],
        },
        "macro_keys": {
            "yield_curve_10y3m": ("positive", 0.0),    # risk-on: positive yield curve
            "breakeven_10y": ("positive", 2.0),
            "nfci": ("negative", 0.0),                 # loose financial conditions
        },
    },
}

# FRED series name to DB indicator key mapping
_FRED_TO_DB: dict[str, str] = {
    "federal_funds": "FEDFUNDS",
    "m2": "M2SL",
    "yield_curve_10y3m": "T10Y3M",
    "breakeven_10y": "T10YIE",
    "hy_oas": "BAMLH0A0HYM2",
    "T10Y2Y": "T10Y2Y",
    "core_capex_orders": "ACOGNO",
    "industrial_production": "INDPRO",
    "nonfarm_payrolls": "PAYEMS",
    "core_cpi": "CPILFESL",
    "building_permits": "PERMIT",
    "umich_sentiment": "UMCSENT",
    "retail_sales": "RSAFS",
    "fed_balance_sheet": "WALCL",
    "stl_fin_stress": "STLFSI4",
    "nfci": "NFCI",
}

# Narrative macro_keys use internal names; map them to DB indicators
_MACRO_KEY_TO_FRED: dict[str, str] = {
    "federal_funds": "FEDFUNDS",
    "yield_curve_10y3m": "T10Y3M",
    "breakeven_10y": "T10YIE",
    "hy_oas": "BAMLH0A0HYM2",
    "T10Y2Y": "T10Y2Y",
    "core_capex_orders": "ACOGNO",
    "industrial_production": "INDPRO",
    "nonfarm_payrolls": "PAYEMS",
    "core_cpi": "CPILFESL",
    "building_permits": "PERMIT",
    "umich_sentiment": "UMCSENT",
    "retail_sales": "RSAFS",
    "fed_balance_sheet": "WALCL",
    "stl_fin_stress": "STLFSI4",
    "nfci": "NFCI",
    "m2": "M2SL",
}


# ---------------------------------------------------------------------------
# Data Loaders
# ---------------------------------------------------------------------------

def _load_macro_indicators() -> dict[str, dict]:
    """Load latest value and 3-month trend for each macro indicator from DB."""
    indicators: dict[str, dict] = {}
    all_fred_ids = list(set(_FRED_TO_DB.values()))
    for fred_id in all_fred_ids:
        try:
            rows = query(
                "SELECT value, date FROM macro_indicators WHERE indicator=? ORDER BY date DESC LIMIT 6",
                [fred_id],
            )
            if not rows:
                continue
            latest_val = rows[0]["value"]
            # 3-month trend: slope sign from last 3+ readings
            if len(rows) >= 2:
                vals = [r["value"] for r in reversed(rows)]
                trend = vals[-1] - vals[0]  # positive = rising
            else:
                trend = 0.0
            indicators[fred_id] = {
                "value": latest_val,
                "trend": trend,
                "date": rows[0]["date"],
            }
        except Exception as e:
            logger.debug(f"Macro indicator {fred_id} unavailable: {e}")
    return indicators


def _load_price_data() -> dict[str, pd.DataFrame]:
    """Load 90 days of price data for all relevant symbols."""
    all_symbols: set[str] = set()
    for ndata in NARRATIVES.values():
        assets = ndata.get("leading_assets", {})
        for asset_list in assets.values():
            all_symbols.update(asset_list)

    symbol_prices: dict[str, pd.DataFrame] = {}
    for sym in all_symbols:
        try:
            rows = query(
                "SELECT date, close, adj_close FROM price_data WHERE symbol=? AND date>=date('now','-90 days') ORDER BY date ASC",
                [sym],
            )
            if rows:
                df = pd.DataFrame(rows)
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date").sort_index()
                # Use adj_close if available, else close
                df["px"] = df["adj_close"].fillna(df["close"])
                symbol_prices[sym] = df
        except Exception as e:
            logger.debug(f"Price data for {sym} unavailable: {e}")
    return symbol_prices


def _load_fundamental_scores() -> dict[str, dict]:
    """Load latest fundamental and technical scores per symbol."""
    fund: dict[str, dict] = {}
    try:
        rows = query(
            """SELECT f.symbol, f.value_score, f.quality_score, f.growth_score, f.total_score as fund_total,
                      t.trend_score, t.momentum_score, t.total_score as tech_total
               FROM fundamental_scores f
               LEFT JOIN (
                   SELECT s2.symbol, s2.trend_score, s2.momentum_score, s2.total_score
                   FROM technical_scores s2
                   INNER JOIN (SELECT symbol, MAX(date) as mx FROM technical_scores GROUP BY symbol) m
                   ON s2.symbol=m.symbol AND s2.date=m.mx
               ) t ON f.symbol = t.symbol
               INNER JOIN (SELECT symbol, MAX(date) as mx FROM fundamental_scores GROUP BY symbol) mf
               ON f.symbol=mf.symbol AND f.date=mf.mx"""
        )
        for r in rows:
            fund[r["symbol"]] = dict(r)
    except Exception as e:
        logger.debug(f"Fundamental scores unavailable: {e}")
    return fund


def _load_regime() -> str:
    """Get current macro regime from DB."""
    try:
        rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
        return rows[0]["regime"] if rows else "neutral"
    except Exception:
        return "neutral"


# ---------------------------------------------------------------------------
# Momentum & Crowding Computation
# ---------------------------------------------------------------------------

def _compute_momentum(df: pd.DataFrame, days: int = 63) -> float | None:
    """Return total return over `days` trading days (0-100 percentile-ish scale)."""
    if df is None or len(df) < 5:
        return None
    px = df["px"].dropna()
    if len(px) < 5:
        return None
    lookback = min(days, len(px) - 1)
    start = px.iloc[-lookback - 1]
    end = px.iloc[-1]
    if start <= 0:
        return None
    return (end / start - 1.0) * 100.0  # raw percent return


def _momentum_to_score(mom_pct: float | None) -> float:
    """Convert raw % momentum to 0-100 score (higher = stronger uptrend)."""
    if mom_pct is None:
        return 50.0  # neutral
    # Clip: -30% = 0, 0% = 50, +30% = 100
    score = 50.0 + (mom_pct / 30.0) * 50.0
    return float(np.clip(score, 0.0, 100.0))


def _crowding_from_momentum(mom_score: float) -> float:
    """Crowding = inverse of momentum strength. High momentum = crowded (low crowding score)."""
    return 100.0 - mom_score


# ---------------------------------------------------------------------------
# Macro Confirmation Scoring
# ---------------------------------------------------------------------------

def _score_macro_confirmation(narrative_id: str, macro_data: dict[str, dict]) -> tuple[float, int]:
    """Return (strength_score 0-100, num_confirmations) for a narrative's macro_keys."""
    ndata = NARRATIVES[narrative_id]
    macro_keys = ndata.get("macro_keys", {})
    if not macro_keys:
        return 50.0, 0

    confirmations = 0
    total = len(macro_keys)

    for key, (direction, threshold) in macro_keys.items():
        fred_id = _MACRO_KEY_TO_FRED.get(key, key)
        indicator = macro_data.get(fred_id)
        if indicator is None:
            # Missing data: partial credit (neutral)
            continue

        value = indicator["value"]
        trend = indicator["trend"]

        if direction == "positive":
            # Narrative confirms if value > threshold AND trend is positive (rising)
            if value > threshold and trend > 0:
                confirmations += 1
            elif value > threshold or trend > 0:
                confirmations += 0.5  # partial
        elif direction == "negative":
            # Narrative confirms if value < threshold AND trend is negative (falling)
            if value < threshold and trend < 0:
                confirmations += 1
            elif value < threshold or trend < 0:
                confirmations += 0.5  # partial

    # Normalize: confirmations / total indicators -> 0-100 strength
    if total == 0:
        return 50.0, 0

    confirmation_ratio = confirmations / total
    # Add regime bonus: scale to 0-100 with minimum floor of 15 (narratives rarely fully dark)
    strength = 15.0 + confirmation_ratio * 85.0
    return float(np.clip(strength, 0.0, 100.0)), int(confirmations)


# ---------------------------------------------------------------------------
# Asset-Level Scoring
# ---------------------------------------------------------------------------

def _score_asset(
    symbol: str,
    asset_class: str,
    price_data: dict[str, pd.DataFrame],
    fund_scores: dict[str, dict],
) -> dict:
    """Return quality_score, timing_score, crowding_score, combined_score for one asset."""
    # Technical / timing score
    df = price_data.get(symbol)
    mom_1m = _compute_momentum(df, days=21)
    mom_3m = _compute_momentum(df, days=63)
    timing_score = _momentum_to_score(mom_3m)
    crowding = _crowding_from_momentum(timing_score)

    # Fundamental quality (equities only; commodities/crypto get neutral)
    fund = fund_scores.get(symbol, {})
    if asset_class == "equities" and fund:
        quality_score = float(fund.get("quality_score") or 50.0)
        # Blend: value + quality + growth
        value_s = float(fund.get("value_score") or 50.0)
        growth_s = float(fund.get("growth_score") or 50.0)
        fund_total = float(fund.get("fund_total") or 50.0)
        quality_score = (quality_score * 0.4 + value_s * 0.3 + growth_s * 0.3)
        quality_score = float(np.clip(quality_score, 0.0, 100.0))
    else:
        # For commodities and crypto, use momentum as proxy for quality
        quality_score = 50.0
        if df is not None and len(df) >= 10:
            # Volatility-adjusted: prefer low-volatility with positive momentum
            px = df["px"].dropna()
            if len(px) >= 10:
                returns = px.pct_change().dropna()
                vol = float(returns.std() * np.sqrt(252) * 100)  # annualized vol %
                mom = mom_3m if mom_3m is not None else 0.0
                # Sharpe-proxy: momentum / vol
                sharpe_proxy = mom / max(vol, 1.0)
                quality_score = float(np.clip(50.0 + sharpe_proxy * 20.0, 0.0, 100.0))

    # Combined: quality + timing, anti-correlated with crowding
    # Best = high quality + early (uncrowded) momentum
    combined = quality_score * 0.5 + timing_score * 0.3 + (100 - crowding) * 0.2
    combined = float(np.clip(combined, 0.0, 100.0))

    return {
        "quality_score": quality_score,
        "timing_score": timing_score,
        "crowding_score": crowding,
        "combined_score": combined,
        "mom_1m_pct": mom_1m,
        "mom_3m_pct": mom_3m,
        "in_universe": df is not None and len(df) >= 5,
    }


def _rank_assets_for_narrative(
    narrative_id: str,
    price_data: dict[str, pd.DataFrame],
    fund_scores: dict[str, dict],
) -> dict:
    """Score every leading asset and return ranked lists for best/worst expression."""
    ndata = NARRATIVES[narrative_id]
    all_assets: list[tuple[str, str]] = []
    for asset_class, symbols in ndata["leading_assets"].items():
        for sym in symbols:
            all_assets.append((sym, asset_class))

    scored: list[dict] = []
    for sym, asset_class in all_assets:
        scores = _score_asset(sym, asset_class, price_data, fund_scores)
        if not scores["in_universe"]:
            continue  # skip if no price data
        scores["symbol"] = sym
        scores["asset_class"] = asset_class
        scored.append(scores)

    if not scored:
        return {"best": [], "avoid": [], "all": []}

    # Sort by combined_score desc for best expressions
    scored.sort(key=lambda x: x["combined_score"], reverse=True)

    best = scored[:3]
    # Avoid: most crowded (lowest crowding_score = most crowded)
    avoid_sorted = sorted(scored, key=lambda x: x["crowding_score"])
    avoid = [a for a in avoid_sorted[:2] if a["crowding_score"] < 30]

    return {"best": best, "avoid": avoid, "all": scored}


# ---------------------------------------------------------------------------
# Maturity Classification
# ---------------------------------------------------------------------------

def _classify_maturity(
    strength: float,
    crowding_score: float,
    asset_confirmations: int,
    asset_count: int,
) -> str:
    """Classify narrative maturity stage."""
    confirmation_ratio = asset_confirmations / max(asset_count, 1)

    if strength < 40:
        return "fading"
    if crowding_score >= 70 and strength >= 50:
        # High crowding_score means UNCROWDED (early)
        return "early"
    if crowding_score >= 45 and strength >= 60:
        return "forming"
    if crowding_score < 35 and strength >= 65:
        return "consensus"
    # Default based on strength
    if strength >= 70:
        return "forming"
    return "fading"


# ---------------------------------------------------------------------------
# Narrative Scoring
# ---------------------------------------------------------------------------

def _score_narrative(
    narrative_id: str,
    macro_data: dict[str, dict],
    price_data: dict[str, pd.DataFrame],
    fund_scores: dict[str, dict],
    regime: str,
) -> dict:
    """Full scoring for one narrative. Returns complete signal dict."""
    ndata = NARRATIVES[narrative_id]

    # 1. Macro strength
    strength_score, macro_confirmations = _score_macro_confirmation(narrative_id, macro_data)

    # 2. Asset momentum / crowding
    asset_ranks = _rank_assets_for_narrative(narrative_id, price_data, fund_scores)
    all_assets = asset_ranks["all"]

    # Average crowding across leading assets that are in universe
    if all_assets:
        avg_crowding = float(np.mean([a["crowding_score"] for a in all_assets]))
        asset_confirmations = sum(1 for a in all_assets if a["timing_score"] > 55)
    else:
        avg_crowding = 50.0
        asset_confirmations = 0

    # Regime adjustment
    regime_boost = {
        "strong_risk_on": 5.0,
        "risk_on": 3.0,
        "neutral": 0.0,
        "risk_off": -5.0,
        "strong_risk_off": -10.0,
    }
    # Narrative-specific regime boosts
    regime_narrative_boost: dict[str, list[str]] = {
        "strong_risk_on": ["ai_infrastructure", "crypto_adoption", "reshoring_manufacturing"],
        "risk_on": ["healthcare_innovation", "consumer_bifurcation"],
        "risk_off": ["dollar_debasement", "credit_stress", "defense_rearmament"],
        "strong_risk_off": ["dollar_debasement", "credit_stress"],
    }
    boost = regime_boost.get(regime, 0.0)
    if narrative_id in regime_narrative_boost.get(regime, []):
        boost += 8.0  # extra boost if regime aligns with narrative

    strength_score = float(np.clip(strength_score + boost, 0.0, 100.0))

    # 3. Opportunity = strength × crowding / 100 (both needed)
    opportunity_score = (strength_score * avg_crowding) / 100.0

    # 4. Maturity
    total_asset_count = len(all_assets)
    maturity = _classify_maturity(strength_score, avg_crowding, asset_confirmations, total_asset_count)

    # 5. Best expression labels
    best_expr = []
    for a in asset_ranks["best"]:
        entry = {
            "symbol": a["symbol"],
            "asset_class": a["asset_class"],
            "quality_score": round(a["quality_score"], 1),
            "timing_score": round(a["timing_score"], 1),
            "combined_score": round(a["combined_score"], 1),
            "mom_3m_pct": round(a["mom_3m_pct"], 1) if a.get("mom_3m_pct") is not None else None,
        }
        best_expr.append(entry)

    avoid_expr = []
    for a in asset_ranks["avoid"]:
        avoid_expr.append({
            "symbol": a["symbol"],
            "asset_class": a["asset_class"],
            "crowding_score": round(a["crowding_score"], 1),
            "timing_score": round(a["timing_score"], 1),
            "reason": "overbought" if a["timing_score"] > 70 else "crowded",
        })

    details = {
        "regime": regime,
        "macro_confirmations": macro_confirmations,
        "asset_confirmations": asset_confirmations,
        "total_assets_in_universe": total_asset_count,
        "avg_asset_crowding": round(avg_crowding, 1),
        "best_expression": best_expr,
        "avoid": avoid_expr,
        "macro_keys_checked": list(ndata.get("macro_keys", {}).keys()),
        "scored_at": datetime.now().isoformat(),
    }

    return {
        "narrative_id": narrative_id,
        "narrative_name": ndata["name"],
        "description": ndata["description"],
        "strength_score": round(strength_score, 2),
        "crowding_score": round(avg_crowding, 2),
        "opportunity_score": round(opportunity_score, 2),
        "maturity": maturity,
        "best_expression": json.dumps(best_expr),
        "avoid": json.dumps(avoid_expr),
        "macro_confirmations": macro_confirmations,
        "asset_confirmations": asset_confirmations,
        "details": json.dumps(details),
        # Parsed for output
        "_best_expr_parsed": best_expr,
        "_avoid_parsed": avoid_expr,
        "_asset_ranks": asset_ranks,
    }


# ---------------------------------------------------------------------------
# DB Persistence
# ---------------------------------------------------------------------------

def _persist_narrative_signals(results: list[dict]) -> None:
    """Upsert narrative_signals rows."""
    cols = [
        "narrative_id", "date", "narrative_name", "strength_score",
        "crowding_score", "opportunity_score", "maturity",
        "best_expression", "avoid", "macro_confirmations",
        "asset_confirmations", "details",
    ]
    rows = []
    for r in results:
        rows.append((
            r["narrative_id"], TODAY, r["narrative_name"],
            r["strength_score"], r["crowding_score"], r["opportunity_score"],
            r["maturity"], r["best_expression"], r["avoid"],
            r["macro_confirmations"], r["asset_confirmations"], r["details"],
        ))
    upsert_many("narrative_signals", cols, rows)


def _persist_asset_map(results: list[dict]) -> None:
    """Upsert narrative_asset_map rows for each scored asset."""
    cols = [
        "narrative_id", "symbol", "date", "asset_class", "role",
        "quality_score", "timing_score", "crowding_score", "combined_score",
    ]
    rows = []
    for r in results:
        asset_ranks = r.get("_asset_ranks", {})
        all_assets = asset_ranks.get("all", [])
        best_syms = {a["symbol"] for a in asset_ranks.get("best", [])}
        avoid_syms = {a["symbol"] for a in asset_ranks.get("avoid", [])}

        for a in all_assets:
            sym = a["symbol"]
            if sym in best_syms:
                role = "best_expression"
            elif sym in avoid_syms:
                role = "avoid"
            else:
                role = "confirming"
            rows.append((
                r["narrative_id"], sym, TODAY, a["asset_class"], role,
                round(a["quality_score"], 2), round(a["timing_score"], 2),
                round(a["crowding_score"], 2), round(a["combined_score"], 2),
            ))
    if rows:
        upsert_many("narrative_asset_map", cols, rows)


# ---------------------------------------------------------------------------
# Output Formatting
# ---------------------------------------------------------------------------

_MATURITY_LABELS = {
    "early": "EARLY",
    "forming": "FORMING",
    "consensus": "CONSENSUS",
    "fading": "FADING",
}

_MATURITY_COLORS = {
    "early": "★ HIGH ALPHA WINDOW",
    "forming": "GOOD RISK/REWARD",
    "consensus": "⚠ LATE/CROWDED",
    "fading": "✗ AVOID",
}


def _format_best_expr(best_expr: list[dict]) -> str:
    parts = []
    for a in best_expr:
        sym = a["symbol"]
        qs = a.get("quality_score")
        ts = a.get("timing_score")
        mom = a.get("mom_3m_pct")
        if qs is not None and ts is not None:
            parts.append(f"{sym} (fund:{qs:.0f}, tech:{ts:.0f})")
        else:
            parts.append(sym)
    return ", ".join(parts)


def _print_results(results: list[dict], regime: str) -> None:
    """Print formatted narrative analysis to stdout."""
    print()
    print("=" * 65)
    print("  NARRATIVE ENGINE")
    print("=" * 65)
    print(f"  Date: {TODAY} | Macro Regime: {regime}")
    print()

    # Sort by opportunity score desc
    sorted_results = sorted(results, key=lambda x: x["opportunity_score"], reverse=True)

    active = [r for r in sorted_results if r["maturity"] in ("early", "forming", "consensus")]
    fading = [r for r in sorted_results if r["maturity"] == "fading"]

    print("ACTIVE NARRATIVES (ranked by opportunity):")
    print("━" * 65)

    for i, r in enumerate(active, 1):
        maturity_label = _MATURITY_LABELS.get(r["maturity"], r["maturity"].upper())
        opp = r["opportunity_score"]
        strength = r["strength_score"]
        crowd = r["crowding_score"]
        name = r["narrative_name"].upper()
        alpha_tag = _MATURITY_COLORS.get(r["maturity"], "")

        print(f"{i:2d}. {name:<35} [{maturity_label}] Opp: {opp:.1f} | Str: {strength:.0f} | Uncrowd: {crowd:.0f}")
        print(f"    {alpha_tag}")

        best_expr = r.get("_best_expr_parsed", [])
        if best_expr:
            print(f"    Best: {_format_best_expr(best_expr)}")

        avoid_parsed = r.get("_avoid_parsed", [])
        if avoid_parsed:
            avoid_strs = [f"{a['symbol']} ({a.get('reason','crowded')})" for a in avoid_parsed]
            print(f"    Avoid: {', '.join(avoid_strs)}")

        macro_conf = r["macro_confirmations"]
        asset_conf = r["asset_confirmations"]
        print(f"    Confirms: {macro_conf} macro / {asset_conf} asset momentum")
        print()

    if fading:
        print("FADING / AVOID:")
        print("─" * 40)
        for r in fading:
            print(f"  {r['narrative_name']:<35} Str: {r['strength_score']:.0f}")
        print()

    # Highest alpha windows
    early_forming = [r for r in sorted_results if r["maturity"] in ("early", "forming")]
    if early_forming:
        print("HIGHEST ALPHA WINDOWS:")
        for r in early_forming[:3]:
            best = r.get("_best_expr_parsed", [])
            if best:
                top_assets = ", ".join(a["symbol"] for a in best[:2])
                desc_snippet = r["description"][:60] + "..." if len(r["description"]) > 60 else r["description"]
                print(f"  → {r['narrative_name']}: {top_assets}")
                print(f"    {desc_snippet}")
        print()

    print("=" * 65)
    print(f"  Narratives scored: {len(results)} | Saved to DB: narrative_signals, narrative_asset_map")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def run() -> list[dict]:
    """Run full narrative engine: score all 12 narratives and persist to DB."""
    init_db()

    print(f"[narrative_engine] Loading data... ({TODAY})")
    macro_data = _load_macro_indicators()
    price_data = _load_price_data()
    fund_scores = _load_fundamental_scores()
    regime = _load_regime()

    print(f"[narrative_engine] Macro indicators loaded: {len(macro_data)}")
    print(f"[narrative_engine] Price series loaded: {len(price_data)}")
    print(f"[narrative_engine] Fundamental scores: {len(fund_scores)}")
    print(f"[narrative_engine] Regime: {regime}")
    print()

    results = []
    for narrative_id in NARRATIVES:
        try:
            result = _score_narrative(narrative_id, macro_data, price_data, fund_scores, regime)
            results.append(result)
        except Exception as e:
            logger.error(f"Error scoring narrative {narrative_id}: {e}", exc_info=True)

    # Persist
    try:
        _persist_narrative_signals(results)
        _persist_asset_map(results)
        print(f"[narrative_engine] Persisted {len(results)} narratives to DB.")
    except Exception as e:
        logger.error(f"DB persistence failed: {e}", exc_info=True)
        print(f"[narrative_engine] WARNING: DB persistence failed: {e}")

    # Print formatted output
    _print_results(results, regime)

    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run()
