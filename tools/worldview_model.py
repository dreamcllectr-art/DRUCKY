"""Macro Worldview Model — Thesis to Stock Expression.

Translates the current macro regime into the BEST stock expressions.
"Given what we believe is happening in the world, which stocks are the
most efficient vehicles to express that view RIGHT NOW?"

Two-layer architecture:
  1. Rule engine: macro sub-scores -> active theses -> sector tilts
     (deterministic, grounded in actual macro data)
  2. LLM narrative: Gemini generates the "why this stock, why now" sentence
     for the top 20 highest-scoring names (qualitative color only)

Thesis definitions (domestic):
  tight_money, easy_money, strong_dollar, weak_dollar,
  credit_stress, steepening_curve, ai_capex_supercycle

Thesis definitions (global macro — World Bank / IMF):
  em_slowdown, global_trade_contraction, sovereign_risk, capital_rotation_to_dm

Output: worldview_signals table with Thesis Alignment Score (0-100) per stock.
The score blends: sector_tilt (50%) + technical_score (30%) + fundamental_score (20%)
A stock must ALSO have good technicals — thesis alone doesn't make a buy.

Usage: python -m tools.worldview_model
"""

import sys
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
)
from tools.db import init_db, upsert_many, query


# ── Thesis Definitions ─────────────────────────────────────────────────
# Each thesis defines:
#   - trigger: lambda of macro sub-scores -> bool
#   - bullish_sectors: sectors that benefit
#   - bearish_sectors: sectors that suffer
#   - tagged_symbols: direct symbol-level tags (bypass sector routing)
#   - description: plain-English summary

THESIS_DEFINITIONS = {
    "tight_money": {
        "trigger": lambda s: (s.get("fed_funds_score", 0) < -5 and
                              s.get("real_rates_score", 0) < -3),
        "bullish_sectors": ["Financials", "Energy"],
        "bearish_sectors": ["Technology", "Consumer Discretionary", "Real Estate",
                            "Communication Services"],
        "tagged_symbols": [],
        "description": "Fed tightening + rising real rates: value over growth, financials win",
    },
    "easy_money": {
        "trigger": lambda s: (s.get("fed_funds_score", 0) > 5 and
                              s.get("m2_score", 0) > 3),
        "bullish_sectors": ["Technology", "Consumer Discretionary", "Communication Services",
                            "Real Estate"],
        "bearish_sectors": ["Financials"],
        "tagged_symbols": [],
        "description": "Fed cutting + M2 expanding: risk-on, growth and duration win",
    },
    "strong_dollar": {
        "trigger": lambda s: s.get("dxy_score", 0) < -5,
        "bullish_sectors": ["Utilities", "Consumer Staples", "Health Care"],
        "bearish_sectors": ["Materials", "Energy", "Industrials"],
        "tagged_symbols": [],
        "description": "Strong USD headwind: domestic-facing defensive sectors win",
    },
    "weak_dollar": {
        "trigger": lambda s: s.get("dxy_score", 0) > 5,
        "bullish_sectors": ["Materials", "Energy", "Industrials"],
        "bearish_sectors": ["Consumer Staples", "Utilities"],
        "tagged_symbols": [],
        "description": "Weak USD tailwind: commodity producers and multinationals win",
    },
    "credit_stress": {
        "trigger": lambda s: s.get("credit_spreads_score", 0) < -5,
        "bullish_sectors": ["Utilities", "Consumer Staples", "Health Care"],
        "bearish_sectors": ["Financials", "Real Estate", "Consumer Discretionary",
                            "Industrials"],
        "tagged_symbols": [],
        "description": "Credit stress: defensives outperform, avoid levered sectors",
    },
    "steepening_curve": {
        "trigger": lambda s: s.get("yield_curve_score", 0) > 8,
        "bullish_sectors": ["Financials"],
        "bearish_sectors": ["Utilities", "Real Estate"],
        "tagged_symbols": [],
        "description": "Steepening yield curve: bank NIM expansion, long duration loses",
    },
    "risk_off": {
        "trigger": lambda s: s.get("vix_score", 0) < -8 and s.get("total_score", 0) < -20,
        "bullish_sectors": ["Utilities", "Consumer Staples", "Health Care"],
        "bearish_sectors": ["Technology", "Consumer Discretionary", "Materials",
                            "Energy", "Industrials"],
        "tagged_symbols": ["GLD", "GC=F"],
        "description": "Risk-off regime: defensives, gold, quality wins; cyclicals suffer",
    },
    "ai_capex_supercycle": {
        "trigger": lambda s: s.get("research_ai_capex_score", 0) > 50,
        "bullish_sectors": ["Technology", "Communication Services"],
        "bearish_sectors": [],
        "tagged_symbols": ["NVDA", "AMD", "TSM", "AVGO", "MSFT", "GOOGL",
                           "META", "AMZN", "ORCL", "AMAT", "LRCX", "ASML"],
        "description": "AI compute capex cycle: semiconductor and hyperscaler beneficiaries",
    },
    # ── Global Macro Theses (World Bank / IMF data) ──────────────────
    "em_slowdown": {
        "trigger": lambda s: s.get("em_gdp_trend", 0) < -1.0,
        "bullish_sectors": ["Utilities", "Consumer Staples", "Health Care"],
        "bearish_sectors": ["Materials", "Industrials", "Energy"],
        "tagged_symbols": [],
        "description": "EM growth decelerating: commodity demand weakens, defensive sectors win",
    },
    "global_trade_contraction": {
        "trigger": lambda s: s.get("global_trade_trend", 0) < -2.0,
        "bullish_sectors": ["Utilities", "Consumer Staples"],
        "bearish_sectors": ["Industrials", "Materials", "Technology"],
        "tagged_symbols": [],
        "description": "Global trade volumes contracting: multinationals and shippers under pressure",
    },
    "sovereign_risk": {
        "trigger": lambda s: s.get("sovereign_debt_stress", 0) > 1.5,
        "bullish_sectors": ["Utilities", "Consumer Staples", "Health Care"],
        "bearish_sectors": ["Financials", "Real Estate"],
        "tagged_symbols": ["GLD"],
        "description": "Sovereign debt stress rising in major economies: flight to quality, gold benefits",
    },
    "capital_rotation_to_dm": {
        "trigger": lambda s: (s.get("dm_gdp_advantage", 0) > 1.5 and
                              s.get("dxy_score", 0) < -3),
        "bullish_sectors": ["Technology", "Health Care", "Financials"],
        "bearish_sectors": ["Materials"],
        "tagged_symbols": [],
        "description": "Capital rotating from EM to DM: US large-cap quality benefits from inflows",
    },
}

# Tilt contribution per sector match
BULLISH_SECTOR_TILT = +0.35
BEARISH_SECTOR_TILT = -0.35
TAGGED_SYMBOL_TILT = +0.55   # Direct symbol match is stronger signal
TAGGED_BEARISH_TILT = -0.45

# How many top stocks to generate LLM narratives for
NARRATIVE_TOP_N = 20


# ── Global Macro Data (World Bank / IMF) ──────────────────────────────

# Key EM economies for aggregate tracking
_EM_COUNTRIES_WB = "CHN;IND;BRA;IDN;MEX;TUR;THA;ZAF"
_DM_COUNTRIES_WB = "USA;GBR;DEU;JPN;FRA;CAN"

# World Bank indicator IDs
_WB_GDP_GROWTH = "NY.GDP.MKTP.KD.ZG"          # GDP growth (annual %)
_WB_TRADE_PCT_GDP = "NE.TRD.GNFS.ZS"          # Trade (% of GDP)
_WB_CURRENT_ACCOUNT = "BN.CAB.XOKA.CD"        # Current account balance ($)
_WB_DEBT_TO_GDP = "GC.DOD.TOTL.GD.ZS"         # Central govt debt (% of GDP)

# IMF DataMapper indicators
_IMF_GDP_FORECAST = "NGDP_RPCH"                # Real GDP growth forecast


def _fetch_world_bank_indicator(indicator: str, countries: str,
                                 years: int = 5) -> list[dict]:
    """Fetch World Bank indicator data. Returns list of {country, year, value}."""
    import datetime as _dt
    end_year = _dt.datetime.now().year
    start_year = end_year - years
    url = (f"https://api.worldbank.org/v2/country/{countries}"
           f"/indicator/{indicator}?date={start_year}:{end_year}"
           f"&format=json&per_page=500")
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2 or not data[1]:
            return []
        return [
            {"country": r["countryiso3code"], "year": int(r["date"]),
             "value": r["value"]}
            for r in data[1]
            if r.get("value") is not None
        ]
    except Exception as e:
        logger.warning(f"World Bank API error ({indicator}): {e}")
        return []


def _fetch_imf_gdp_forecasts() -> dict[str, dict[int, float]]:
    """Fetch IMF GDP growth forecasts. Returns {country_code: {year: growth_pct}}."""
    import datetime as _dt
    years = ",".join(str(_dt.datetime.now().year + i) for i in range(3))
    url = f"https://www.imf.org/external/datamapper/api/v1/{_IMF_GDP_FORECAST}?periods={years}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        values = data.get("values", {}).get(_IMF_GDP_FORECAST, {})
        result = {}
        for country, year_data in values.items():
            result[country] = {int(y): float(v) for y, v in year_data.items()}
        return result
    except Exception as e:
        logger.warning(f"IMF API error: {e}")
        return {}


def _compute_global_macro_scores() -> dict[str, float]:
    """Compute global macro scores from World Bank + IMF data.

    Returns dict with keys:
      em_gdp_trend:       negative = EM growth decelerating (z-score-like)
      global_trade_trend:  negative = trade contracting
      sovereign_debt_stress: positive = rising debt stress
      dm_gdp_advantage:    positive = DM outgrowing EM expectations
    """
    scores = {
        "em_gdp_trend": 0.0,
        "global_trade_trend": 0.0,
        "sovereign_debt_stress": 0.0,
        "dm_gdp_advantage": 0.0,
    }

    # --- EM GDP trend: compare recent years to 3yr average ---
    em_gdp = _fetch_world_bank_indicator(_WB_GDP_GROWTH, _EM_COUNTRIES_WB)
    if em_gdp:
        by_year: dict[int, list[float]] = {}
        for r in em_gdp:
            by_year.setdefault(r["year"], []).append(r["value"])
        yearly_avg = {y: sum(v)/len(v) for y, v in by_year.items() if v}
        sorted_years = sorted(yearly_avg.keys())
        if len(sorted_years) >= 3:
            recent = yearly_avg.get(sorted_years[-1], 0)
            hist_avg = sum(yearly_avg[y] for y in sorted_years[-4:-1]) / 3
            # Negative = EM growth decelerating
            scores["em_gdp_trend"] = recent - hist_avg

    # --- Global trade trend: YoY change in trade/GDP ---
    all_countries = f"{_EM_COUNTRIES_WB};{_DM_COUNTRIES_WB}"
    trade_data = _fetch_world_bank_indicator(_WB_TRADE_PCT_GDP, all_countries)
    if trade_data:
        by_year = {}
        for r in trade_data:
            by_year.setdefault(r["year"], []).append(r["value"])
        yearly_avg = {y: sum(v)/len(v) for y, v in by_year.items() if v}
        sorted_years = sorted(yearly_avg.keys())
        if len(sorted_years) >= 2:
            recent = yearly_avg[sorted_years[-1]]
            prev = yearly_avg[sorted_years[-2]]
            scores["global_trade_trend"] = recent - prev  # Negative = contracting

    # --- Sovereign debt stress: avg debt/GDP trend in G7 ---
    debt_data = _fetch_world_bank_indicator(_WB_DEBT_TO_GDP, _DM_COUNTRIES_WB)
    if debt_data:
        by_year = {}
        for r in debt_data:
            by_year.setdefault(r["year"], []).append(r["value"])
        yearly_avg = {y: sum(v)/len(v) for y, v in by_year.items() if v}
        sorted_years = sorted(yearly_avg.keys())
        if len(sorted_years) >= 2:
            recent = yearly_avg[sorted_years[-1]]
            prev = yearly_avg[sorted_years[-2]]
            # Positive = debt rising (stress increasing)
            scores["sovereign_debt_stress"] = (recent - prev) / 10.0  # Scale down

    # --- DM vs EM GDP advantage (IMF forward-looking) ---
    imf = _fetch_imf_gdp_forecasts()
    if imf:
        em_codes = ["CHN", "IND", "BRA", "IDN", "MEX", "TUR"]
        dm_codes = ["USA", "GBR", "DEU", "JPN", "FRA", "CAN"]
        import datetime as _dt
        next_year = _dt.datetime.now().year + 1

        em_forecasts = [imf[c].get(next_year, 0) for c in em_codes if c in imf]
        dm_forecasts = [imf[c].get(next_year, 0) for c in dm_codes if c in imf]

        if em_forecasts and dm_forecasts:
            em_avg = sum(em_forecasts) / len(em_forecasts)
            dm_avg = sum(dm_forecasts) / len(dm_forecasts)
            # Positive = DM outperforming EM on growth expectations
            # (adjusted: EM normally grows faster, so shrinking gap = DM advantage)
            scores["dm_gdp_advantage"] = dm_avg - em_avg + 3.0  # +3 offsets normal EM premium

    return scores


# ── Core Logic ─────────────────────────────────────────────────────────

def _get_macro_sub_scores() -> dict:
    """Read latest macro regime scores from DB."""
    rows = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    if not rows:
        return {}
    return dict(rows[0])


def _get_research_ai_score() -> float:
    """
    Proxy for AI capex thesis: average relevance of recent Epoch AI / SemiAnalysis articles.
    If no research data, default to 0 (thesis doesn't fire).
    """
    rows = query(
        """
        SELECT AVG(relevance_score) as avg_score
        FROM research_signals
        WHERE source IN ('epoch_ai', 'semianalysis')
        AND date >= date('now', '-14 days')
        AND symbol IS NULL
        """
    )
    if rows and rows[0]["avg_score"] is not None:
        return float(rows[0]["avg_score"])
    return 0.0


def _get_active_theses(macro_scores: dict) -> list[str]:
    """Evaluate each thesis trigger and return list of active thesis keys."""
    # Augment scores with research-derived signals
    augmented = dict(macro_scores)
    augmented["research_ai_capex_score"] = _get_research_ai_score()

    # Augment with global macro data (World Bank / IMF)
    # These are slow-moving, so failures are gracefully handled
    try:
        global_scores = _compute_global_macro_scores()
        augmented.update(global_scores)
        if any(v != 0 for v in global_scores.values()):
            print(f"  Global macro scores: " + ", ".join(
                f"{k}={v:+.2f}" for k, v in global_scores.items() if v != 0
            ))
    except Exception as e:
        logger.warning(f"Global macro data unavailable: {e}")

    active = []
    for thesis_key, thesis in THESIS_DEFINITIONS.items():
        try:
            if thesis["trigger"](augmented):
                active.append(thesis_key)
        except Exception:
            pass
    return active


def _compute_sector_tilt(sector: str, symbol: str, active_theses: list[str]) -> float:
    """
    Compute cumulative sector tilt for a stock given active theses.
    Returns value in [-1.0, +1.0].
    """
    tilt = 0.0
    for thesis_key in active_theses:
        thesis = THESIS_DEFINITIONS[thesis_key]
        # Direct symbol tag (highest signal)
        if symbol in thesis.get("tagged_symbols", []):
            tilt += TAGGED_SYMBOL_TILT
        elif sector in thesis.get("bullish_sectors", []):
            tilt += BULLISH_SECTOR_TILT
        elif sector in thesis.get("bearish_sectors", []):
            tilt += BEARISH_SECTOR_TILT

    return max(-1.0, min(1.0, tilt))


def _tilt_to_score(tilt: float) -> float:
    """Convert sector tilt [-1, +1] to 0-100 score."""
    return (tilt + 1.0) / 2.0 * 100.0


def _compute_thesis_alignment_score(
    sector_tilt: float,
    tech_score: float,
    fund_score: float,
) -> float:
    """
    Blend: sector_tilt_score (50%) + technical (30%) + fundamental (20%).
    A strong macro thesis requires technical confirmation — avoids catching falling knives.
    """
    tilt_score = _tilt_to_score(sector_tilt)
    return (tilt_score * 0.50) + (tech_score * 0.30) + (fund_score * 0.20)


def _generate_narrative_gemini(
    symbol: str,
    sector: str,
    active_theses: list[str],
    score: float,
) -> str:
    """Generate a one-sentence investment narrative using Gemini Flash."""
    if not GEMINI_API_KEY or not active_theses:
        theses_str = ", ".join(active_theses) if active_theses else "current macro environment"
        return (f"{symbol} ({sector}) scores {score:.0f}/100 given active theses: "
                f"{theses_str}")

    theses_descriptions = [
        THESIS_DEFINITIONS[t]["description"]
        for t in active_theses
        if t in THESIS_DEFINITIONS
    ]
    theses_text = "; ".join(theses_descriptions)

    prompt = (
        f"In exactly one sentence (under 160 characters), explain why {symbol} "
        f"({sector}) is a strong expression of these macro theses: {theses_text}. "
        f"Be specific about the mechanism. Speak like Stan Druckenmiller."
    )

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 128},
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text[:200]
    except Exception as e:
        return (f"{symbol} ({sector}) aligns with {', '.join(active_theses[:2])} thesis. "
                f"Score: {score:.0f}/100.")


def _build_thesis_narrative_template(
    symbol: str,
    sector: str,
    active_theses: list[str],
    score: float,
) -> str:
    """Fast template-based narrative (no API call)."""
    if not active_theses:
        return f"{symbol}: no active macro thesis alignment at this time."
    thesis_short = " + ".join(t.replace("_", " ") for t in active_theses[:2])
    return f"{symbol} ({sector}): best expression of {thesis_short} thesis. Score {score:.0f}/100."


def run():
    """Main entry: compute worldview signals for all stocks."""
    init_db()
    today = date.today().isoformat()
    print("Worldview Model: Translating macro thesis to stock expression...")

    # Load macro regime
    macro_scores = _get_macro_sub_scores()
    if not macro_scores:
        print("  Warning: No macro scores found — run macro_regime first")
        return

    regime = macro_scores.get("regime", "neutral")
    total_score = macro_scores.get("total_score", 0)
    print(f"  Current regime: {regime} (score: {total_score:.1f})")

    # Get active theses
    active_theses = _get_active_theses(macro_scores)
    if active_theses:
        print(f"  Active theses ({len(active_theses)}): {', '.join(active_theses)}")
        for thesis in active_theses:
            print(f"    → {THESIS_DEFINITIONS[thesis]['description']}")
    else:
        print("  No strong macro theses active — neutral regime, no strong tilts")

    # Get all stocks with technical + fundamental scores
    stock_scores = query(
        """
        SELECT u.symbol, u.sector,
               COALESCE(t.total_score, 50) as tech_score,
               COALESCE(f.total_score, 50) as fund_score
        FROM stock_universe u
        LEFT JOIN (
            SELECT symbol, total_score FROM technical_scores
            WHERE date = (SELECT MAX(date) FROM technical_scores WHERE symbol = technical_scores.symbol)
        ) t ON u.symbol = t.symbol
        LEFT JOIN (
            SELECT symbol, total_score FROM fundamental_scores
            WHERE date = (SELECT MAX(date) FROM fundamental_scores WHERE symbol = fundamental_scores.symbol)
        ) f ON u.symbol = f.symbol
        """
    )

    if not stock_scores:
        print("  Warning: No stock scores found — run scoring modules first")
        return

    print(f"  Scoring {len(stock_scores)} stocks against active theses...")

    # Compute thesis alignment scores
    results = []
    for row in stock_scores:
        symbol = row["symbol"]
        sector = row["sector"] or "Unknown"
        tech = row["tech_score"] or 50.0
        fund = row["fund_score"] or 50.0

        sector_tilt = _compute_sector_tilt(sector, symbol, active_theses)
        score = _compute_thesis_alignment_score(sector_tilt, tech, fund)

        results.append({
            "symbol": symbol,
            "sector": sector,
            "sector_tilt": sector_tilt,
            "score": score,
            "tech": tech,
            "fund": fund,
        })

    # Rank by score
    results.sort(key=lambda x: x["score"], reverse=True)

    # Generate LLM narratives for top stocks only (cost/speed optimization)
    top_symbols = {r["symbol"] for r in results[:NARRATIVE_TOP_N] if r["sector_tilt"] > 0.2}

    rows = []
    narrative_count = 0
    for rank, r in enumerate(results, 1):
        symbol = r["symbol"]

        # Get relevant theses for this specific stock
        stock_theses = [
            t for t in active_theses
            if (symbol in THESIS_DEFINITIONS[t].get("tagged_symbols", [])
                or r["sector"] in THESIS_DEFINITIONS[t].get("bullish_sectors", [])
                or r["sector"] in THESIS_DEFINITIONS[t].get("bearish_sectors", []))
        ]

        # Generate narrative: Gemini for top high-conviction, template for rest
        if symbol in top_symbols and GEMINI_API_KEY and narrative_count < 15:
            narrative = _generate_narrative_gemini(symbol, r["sector"], stock_theses, r["score"])
            narrative_count += 1
            time.sleep(0.3)  # Gemini rate limit
        else:
            narrative = _build_thesis_narrative_template(symbol, r["sector"], stock_theses, r["score"])

        rows.append((
            symbol, today, regime,
            round(r["score"], 2),
            round(r["sector_tilt"], 4),
            rank,
            json.dumps(stock_theses),
            narrative,
        ))

    if rows:
        upsert_many(
            "worldview_signals",
            ["symbol", "date", "regime", "thesis_alignment_score",
             "sector_tilt", "macro_expression_rank", "active_theses", "narrative"],
            rows,
        )

    # Print top expressions of current worldview
    top_results = [r for r in results[:20] if r["sector_tilt"] > 0.1]
    print(f"\n  TOP WORLDVIEW EXPRESSIONS (regime: {regime}):")
    print(f"  {'Symbol':<8} {'Sector':<26} {'Score':>6} {'Tilt':>5}  Active Theses")
    print(f"  {'-'*75}")
    for r in top_results[:12]:
        symbol = r["symbol"]
        active_for_stock = [
            t[:12] for t in active_theses
            if (symbol in THESIS_DEFINITIONS[t].get("tagged_symbols", [])
                or r["sector"] in THESIS_DEFINITIONS[t].get("bullish_sectors", []))
        ]
        theses_str = ", ".join(active_for_stock[:2]) or "—"
        print(f"  {symbol:<8} {r['sector'][:25]:<26} {r['score']:>6.1f} {r['sector_tilt']:>+5.2f}  {theses_str}")

    if active_theses:
        print(f"\n  ACTIVE THESIS COUNT: {len(active_theses)}")
        for thesis in active_theses:
            defn = THESIS_DEFINITIONS[thesis]
            print(f"  ▸ {thesis}: {defn['description']}")

    print(f"\nWorldview complete: {len(rows)} stocks scored, {narrative_count} LLM narratives generated")


if __name__ == "__main__":
    run()
