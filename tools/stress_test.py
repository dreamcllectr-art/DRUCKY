"""Portfolio Stress Testing — macro shock scenario analysis.

Answers: "What happens to my book if rates move 100bps?"

Takes current HIGH/NOTABLE convergence positions and runs them through
defined macro shock scenarios, computing expected P&L impact per stock
and aggregate portfolio drawdown.

Scenarios:
  1. RECESSION:       GDP -2%, unemployment +3%, SPX -25%
  2. RATE_SHOCK:      Fed funds +200bps, 10Y +150bps
  3. USD_RALLY:       DXY +10%, EM currencies -15%
  4. CHINA_SLOWDOWN:  China GDP halves, commodity demand -20%
  5. CREDIT_CRUNCH:   HY spreads +300bps, bank lending freeze
  6. INFLATION_SPIKE: CPI +3%, real rates deeply negative
  7. TECH_SELLOFF:    Sector rotation out of growth, -30% tech

Each scenario defines sector-level beta impacts that get applied
to individual stock positions based on sector + beta.

Usage: python -m tools.stress_test
"""

import json
import logging
from datetime import date

from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)


# ── Scenario Definitions ────────────────────────────────────────────

STRESS_SCENARIOS = {
    "recession": {
        "name": "Recession (-25% SPX)",
        "description": "GDP contracts 2%, unemployment rises 3pp, broad equity selloff",
        "market_shock": -0.25,  # SPX drawdown
        "sector_impacts": {
            "Technology":              -0.30,
            "Consumer Discretionary":  -0.35,
            "Communication Services":  -0.28,
            "Financials":              -0.32,
            "Industrials":             -0.28,
            "Materials":               -0.30,
            "Real Estate":             -0.25,
            "Energy":                  -0.22,
            "Health Care":             -0.12,
            "Consumer Staples":        -0.08,
            "Utilities":               -0.05,
        },
    },
    "rate_shock": {
        "name": "Rate Shock (+200bps)",
        "description": "Fed hikes aggressively, 10Y yield spikes 150bps",
        "market_shock": -0.15,
        "sector_impacts": {
            "Technology":              -0.22,
            "Consumer Discretionary":  -0.18,
            "Communication Services":  -0.20,
            "Financials":              +0.05,  # Banks benefit from steeper curve
            "Industrials":             -0.10,
            "Materials":               -0.08,
            "Real Estate":             -0.25,
            "Energy":                  -0.05,
            "Health Care":             -0.10,
            "Consumer Staples":        -0.06,
            "Utilities":               -0.18,
        },
    },
    "usd_rally": {
        "name": "USD Rally (+10% DXY)",
        "description": "Dollar surges on safe-haven flows, EM currencies collapse",
        "market_shock": -0.08,
        "sector_impacts": {
            "Technology":              -0.12,  # Multinational earnings hit
            "Consumer Discretionary":  -0.10,
            "Communication Services":  -0.08,
            "Financials":              -0.05,
            "Industrials":             -0.10,
            "Materials":               -0.15,
            "Real Estate":             -0.03,
            "Energy":                  -0.12,
            "Health Care":             -0.06,
            "Consumer Staples":        -0.08,
            "Utilities":               +0.02,
        },
    },
    "china_slowdown": {
        "name": "China Slowdown (GDP halves)",
        "description": "China GDP growth drops to 2-3%, commodity demand craters",
        "market_shock": -0.12,
        "sector_impacts": {
            "Technology":              -0.15,  # Supply chain + demand
            "Consumer Discretionary":  -0.12,
            "Communication Services":  -0.06,
            "Financials":              -0.08,
            "Industrials":             -0.18,
            "Materials":               -0.25,
            "Real Estate":             -0.05,
            "Energy":                  -0.20,
            "Health Care":             -0.04,
            "Consumer Staples":        -0.03,
            "Utilities":               -0.02,
        },
    },
    "credit_crunch": {
        "name": "Credit Crunch (+300bps HY spreads)",
        "description": "High-yield spreads blow out, bank lending freezes",
        "market_shock": -0.20,
        "sector_impacts": {
            "Technology":              -0.15,
            "Consumer Discretionary":  -0.25,
            "Communication Services":  -0.18,
            "Financials":              -0.35,
            "Industrials":             -0.20,
            "Materials":               -0.22,
            "Real Estate":             -0.30,
            "Energy":                  -0.18,
            "Health Care":             -0.10,
            "Consumer Staples":        -0.05,
            "Utilities":               -0.08,
        },
    },
    "inflation_spike": {
        "name": "Inflation Spike (+3% CPI)",
        "description": "CPI surges 3pp, real rates deeply negative, cost pressures",
        "market_shock": -0.10,
        "sector_impacts": {
            "Technology":              -0.18,
            "Consumer Discretionary":  -0.20,
            "Communication Services":  -0.12,
            "Financials":              -0.05,
            "Industrials":             -0.08,
            "Materials":               +0.10,  # Commodity producers benefit
            "Real Estate":             -0.05,
            "Energy":                  +0.15,  # Energy producers benefit
            "Health Care":             -0.06,
            "Consumer Staples":        -0.04,  # Pricing power
            "Utilities":               -0.10,
        },
    },
    "tech_selloff": {
        "name": "Tech Rotation (-30% Nasdaq)",
        "description": "Sector rotation out of growth/momentum into value",
        "market_shock": -0.12,
        "sector_impacts": {
            "Technology":              -0.30,
            "Consumer Discretionary":  -0.15,
            "Communication Services":  -0.25,
            "Financials":              +0.05,
            "Industrials":             +0.03,
            "Materials":               +0.05,
            "Real Estate":             +0.02,
            "Energy":                  +0.08,
            "Health Care":             +0.02,
            "Consumer Staples":        +0.04,
            "Utilities":               +0.05,
        },
    },
}


# ── Stress Calculation ───────────────────────────────────────────────

def _get_portfolio_positions() -> list[dict]:
    """Get current HIGH/NOTABLE convergence positions with sector + price.

    Note: fundamentals table is a KV store (symbol, metric, value),
    so we pivot beta and marketCap via subqueries.
    """
    rows = query("""
        SELECT cs.symbol, cs.convergence_score, cs.conviction_level,
               cs.module_count,
               su.sector, su.name,
               fb.value as beta,
               fm.value as marketCap,
               p.close as current_price
        FROM convergence_signals cs
        JOIN stock_universe su ON cs.symbol = su.symbol
        LEFT JOIN fundamentals fb
            ON cs.symbol = fb.symbol AND fb.metric = 'beta'
        LEFT JOIN fundamentals fm
            ON cs.symbol = fm.symbol AND fm.metric = 'marketCap'
        LEFT JOIN (
            SELECT p1.symbol, p1.close FROM price_data p1
            INNER JOIN (SELECT symbol, MAX(date) as mx FROM price_data GROUP BY symbol) p2
            ON p1.symbol = p2.symbol AND p1.date = p2.mx
        ) p ON cs.symbol = p.symbol
        WHERE cs.date = (SELECT MAX(date) FROM convergence_signals)
          AND cs.conviction_level IN ('HIGH', 'NOTABLE')
        ORDER BY cs.convergence_score DESC
    """)

    return [dict(r) for r in rows]


def stress_test_scenario(positions: list[dict], scenario_key: str) -> dict:
    """Run a single stress scenario against portfolio positions.

    Returns: {scenario, total_impact, position_impacts: [{symbol, sector, impact_pct, ...}]}
    """
    scenario = STRESS_SCENARIOS[scenario_key]
    sector_impacts = scenario["sector_impacts"]
    market_shock = scenario["market_shock"]

    position_results = []
    total_weighted_impact = 0.0
    total_weight = 0.0

    for pos in positions:
        sector = pos.get("sector", "Unknown")
        beta = pos.get("beta") or 1.0
        price = pos.get("current_price") or 0

        # Sector-specific impact, scaled by stock beta
        base_impact = sector_impacts.get(sector, market_shock)
        # Beta adjustment: high-beta stocks move more, clamp to [0.3, 2.5]
        # Use abs(beta) to handle negative-beta stocks correctly
        beta_float = float(beta)
        beta_mult = max(0.3, min(2.5, abs(beta_float))) if beta_float >= 0 else -max(0.3, min(2.5, abs(beta_float)))
        stock_impact = base_impact * beta_mult

        # Weight by convergence score (higher conviction = larger position assumed)
        conv_score = pos.get("convergence_score", 50)
        weight = conv_score / 100.0

        position_results.append({
            "symbol": pos["symbol"],
            "name": pos.get("name", ""),
            "sector": sector,
            "conviction": pos.get("conviction_level", ""),
            "convergence_score": conv_score,
            "beta": round(float(beta), 2),
            "current_price": price,
            "impact_pct": round(stock_impact * 100, 1),
            "implied_price": round(price * (1 + stock_impact), 2) if price else 0,
        })

        total_weighted_impact += stock_impact * weight
        total_weight += weight

    avg_impact = total_weighted_impact / total_weight if total_weight else 0

    # Sort by impact (worst first)
    position_results.sort(key=lambda x: x["impact_pct"])

    return {
        "scenario": scenario_key,
        "scenario_name": scenario["name"],
        "description": scenario["description"],
        "portfolio_impact_pct": round(avg_impact * 100, 1),
        "worst_hit": position_results[0] if position_results else None,
        "best_positioned": position_results[-1] if position_results else None,
        "position_count": len(position_results),
        "positions": position_results,
    }


def _compute_concentration_risk(positions: list[dict]) -> dict:
    """Analyze sector concentration in current HIGH/NOTABLE positions."""
    sector_counts = {}
    sector_scores = {}

    for pos in positions:
        sector = pos.get("sector", "Unknown")
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        if sector not in sector_scores:
            sector_scores[sector] = []
        sector_scores[sector].append(pos.get("convergence_score", 0))

    # Herfindahl index (concentration measure)
    total = len(positions)
    hhi = sum((count / total) ** 2 for count in sector_counts.values()) if total > 0 else 0

    concentration = {
        "sector_breakdown": {
            s: {"count": c, "pct": round(c / total * 100, 1),
                "avg_score": round(sum(sector_scores[s]) / len(sector_scores[s]), 1)}
            for s, c in sorted(sector_counts.items(), key=lambda x: -x[1])
        },
        "hhi": round(hhi, 3),
        "concentration_level": "HIGH" if hhi > 0.25 else "MODERATE" if hhi > 0.15 else "DIVERSIFIED",
        "top_sector": max(sector_counts, key=sector_counts.get) if sector_counts else "N/A",
        "top_sector_pct": round(max(sector_counts.values()) / total * 100, 1) if total > 0 else 0,
    }

    return concentration


# ── Output ───────────────────────────────────────────────────────────

def render_stress_html(results: list[dict], concentration: dict) -> str:
    """Render stress test results as HTML."""
    html = f"""
    <div style="font-family: -apple-system, sans-serif; background:#0E1117; color:#E0E0E0; padding:24px; max-width:800px;">
    <h1 style="color:white;">Portfolio Stress Test</h1>
    <p style="color:#888;">{date.today().strftime('%B %d, %Y')} — {results[0]['position_count'] if results else 0} positions analyzed</p>

    <!-- Concentration -->
    <div style="background:#1e2130; padding:16px; border-radius:8px; margin:16px 0;">
        <h3 style="color:#B0BEC5; margin-top:0;">Concentration Risk: <span style="color:{'#FF1744' if concentration['concentration_level'] == 'HIGH' else '#FFD54F' if concentration['concentration_level'] == 'MODERATE' else '#69F0AE'};">{concentration['concentration_level']}</span></h3>
        <p style="color:#888; font-size:13px;">HHI: {concentration['hhi']} · Top sector: {concentration['top_sector']} ({concentration['top_sector_pct']}%)</p>
    </div>

    <!-- Scenario Table -->
    <table style="width:100%; border-collapse:collapse; margin:16px 0;">
    <tr style="border-bottom:2px solid #333;">
        <th style="text-align:left; padding:10px; color:#888;">Scenario</th>
        <th style="text-align:right; padding:10px; color:#888;">Portfolio Impact</th>
        <th style="text-align:left; padding:10px; color:#888;">Worst Hit</th>
        <th style="text-align:left; padding:10px; color:#888;">Best Positioned</th>
    </tr>
    """

    for r in sorted(results, key=lambda x: x["portfolio_impact_pct"]):
        impact = r["portfolio_impact_pct"]
        color = "#FF1744" if impact < -15 else "#FF8A65" if impact < -10 else "#FFD54F" if impact < -5 else "#69F0AE"
        worst = r.get("worst_hit", {})
        best = r.get("best_positioned", {})

        html += f"""
        <tr style="border-bottom:1px solid #1e2130;">
            <td style="padding:10px;">
                <div style="color:white; font-weight:600;">{r['scenario_name']}</div>
                <div style="color:#666; font-size:11px;">{r['description'][:60]}</div>
            </td>
            <td style="text-align:right; padding:10px; color:{color}; font-weight:700; font-size:18px;">{impact:+.1f}%</td>
            <td style="padding:10px; color:#FF8A65;">{worst.get('symbol', 'N/A')} ({worst.get('impact_pct', 0):+.1f}%)</td>
            <td style="padding:10px; color:#69F0AE;">{best.get('symbol', 'N/A')} ({best.get('impact_pct', 0):+.1f}%)</td>
        </tr>"""

    html += """</table>

    <!-- Sector Breakdown -->
    <h3 style="color:#B0BEC5; margin-top:24px;">Sector Exposure</h3>
    <div style="display:flex; flex-wrap:wrap; gap:8px;">
    """

    for sector, info in concentration["sector_breakdown"].items():
        html += f"""
        <div style="background:#1e2130; padding:8px 14px; border-radius:6px; min-width:120px;">
            <div style="color:#888; font-size:11px;">{sector}</div>
            <div style="color:white; font-size:16px; font-weight:600;">{info['pct']}%</div>
            <div style="color:#666; font-size:11px;">{info['count']} stocks · avg {info['avg_score']:.0f}</div>
        </div>"""

    html += """</div>
    <p style="color:#555; font-size:11px; margin-top:20px;">
        Impact estimates use sector-level betas adjusted by individual stock beta.
        Not a prediction — a sensitivity analysis.
    </p>
    </div>"""

    return html


# ── Main ─────────────────────────────────────────────────────────────

def run():
    """Run portfolio stress test across all scenarios."""
    init_db()
    _ensure_tables()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  PORTFOLIO STRESS TEST")
    print("=" * 60)

    positions = _get_portfolio_positions()
    if not positions:
        print("  No HIGH/NOTABLE positions to stress test")
        print("=" * 60)
        return

    print(f"  Testing {len(positions)} positions across {len(STRESS_SCENARIOS)} scenarios...")

    # Concentration analysis
    concentration = _compute_concentration_risk(positions)
    print(f"  Concentration: {concentration['concentration_level']} "
          f"(HHI={concentration['hhi']}, top={concentration['top_sector']} {concentration['top_sector_pct']}%)")

    # Run all scenarios
    results = []
    for scenario_key in STRESS_SCENARIOS:
        result = stress_test_scenario(positions, scenario_key)
        results.append(result)

        worst = result.get("worst_hit", {})
        best = result.get("best_positioned", {})
        print(f"  {result['scenario_name']:<30} | Portfolio: {result['portfolio_impact_pct']:+6.1f}% | "
              f"Worst: {worst.get('symbol', 'N/A')} ({worst.get('impact_pct', 0):+.1f}%) | "
              f"Best: {best.get('symbol', 'N/A')} ({best.get('impact_pct', 0):+.1f}%)")

    # Persist results
    stress_rows = []
    for r in results:
        stress_rows.append((
            today,
            r["scenario"],
            r["scenario_name"],
            r["portfolio_impact_pct"],
            r["position_count"],
            json.dumps(r["positions"]),
            r["worst_hit"]["symbol"] if r.get("worst_hit") else None,
            r["best_positioned"]["symbol"] if r.get("best_positioned") else None,
        ))

    upsert_many(
        "stress_test_results",
        ["date", "scenario", "scenario_name", "portfolio_impact_pct",
         "position_count", "position_details", "worst_hit", "best_positioned"],
        stress_rows,
    )

    # Persist concentration
    upsert_many(
        "concentration_risk",
        ["date", "hhi", "concentration_level", "top_sector",
         "top_sector_pct", "details"],
        [(today, concentration["hhi"], concentration["concentration_level"],
          concentration["top_sector"], concentration["top_sector_pct"],
          json.dumps(concentration["sector_breakdown"]))],
    )

    # Render HTML report — match existing intelligence_reports schema
    html = render_stress_html(results, concentration)
    # Get current regime
    regime_rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = regime_rows[0]["regime"] if regime_rows else "neutral"
    symbols = ",".join(p["symbol"] for p in positions[:20])

    upsert_many(
        "intelligence_reports",
        ["topic", "topic_type", "expert_type", "regime",
         "symbols_covered", "report_html", "metadata"],
        [("portfolio_stress_test", "stress_test", "risk",
          regime, symbols, html,
          json.dumps({"scenarios": len(results), "positions": len(positions)}))],
    )

    # Summary
    worst_scenario = min(results, key=lambda x: x["portfolio_impact_pct"])
    print(f"\n  Worst scenario: {worst_scenario['scenario_name']} ({worst_scenario['portfolio_impact_pct']:+.1f}%)")
    print("=" * 60)


def _ensure_tables():
    """Create stress test tables."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stress_test_results (
            date TEXT,
            scenario TEXT,
            scenario_name TEXT,
            portfolio_impact_pct REAL,
            position_count INTEGER,
            position_details TEXT,
            worst_hit TEXT,
            best_positioned TEXT,
            PRIMARY KEY (date, scenario)
        );
        CREATE TABLE IF NOT EXISTS concentration_risk (
            date TEXT PRIMARY KEY,
            hhi REAL,
            concentration_level TEXT,
            top_sector TEXT,
            top_sector_pct REAL,
            details TEXT
        );
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    run()
