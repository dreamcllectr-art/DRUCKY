"""Stress Test Backtester — calibrate scenario assumptions against history.

Pulls actual sector ETF drawdowns during GFC (2008-2009) and COVID
(2020-03) via yfinance, then compares to our stress_test.py scenario
assumptions. Updates STRESS_SCENARIOS with empirically-calibrated values.

Sector ETFs:
  XLK (Technology), XLF (Financials), XLE (Energy), XLV (Health Care),
  XLP (Consumer Staples), XLI (Industrials), XLB (Materials),
  XLRE (Real Estate), XLU (Utilities), XLC (Comm Services),
  XLY (Consumer Discretionary), SPY (benchmark)

Historical Crises:
  1. GFC: 2007-10-09 (SPY peak) to 2009-03-09 (SPY trough)
  2. COVID: 2020-02-19 to 2020-03-23
  3. 2022 Rate Shock: 2022-01-03 to 2022-10-12
  4. 2018 Q4 Selloff: 2018-09-20 to 2018-12-24

Output:
  - stress_backtest_results table with actual vs assumed drawdowns
  - Updated STRESS_SCENARIOS calibration recommendations
  - HTML report comparing assumptions to reality

Usage: python -m tools.stress_backtest
"""

import json
import logging
from datetime import date, datetime

from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

# ── Sector ETF → GICS Sector Mapping ────────────────────────────────
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLU": "Utilities",
    "XLC": "Communication Services",
    "XLY": "Consumer Discretionary",
    "SPY": "S&P 500",
}

# ── Historical Crisis Periods ────────────────────────────────────────
CRISIS_PERIODS = {
    "gfc": {
        "name": "Global Financial Crisis (2007-2009)",
        "peak": "2007-10-09",
        "trough": "2009-03-09",
        "scenario_map": "recession",  # Which stress scenario this calibrates
    },
    "covid": {
        "name": "COVID Crash (2020)",
        "peak": "2020-02-19",
        "trough": "2020-03-23",
        "scenario_map": "credit_crunch",  # Fast credit shock
    },
    "rate_shock_2022": {
        "name": "2022 Rate Shock",
        "peak": "2022-01-03",
        "trough": "2022-10-12",
        "scenario_map": "rate_shock",
    },
    "q4_2018": {
        "name": "Q4 2018 Selloff",
        "peak": "2018-09-20",
        "trough": "2018-12-24",
        "scenario_map": "tech_selloff",
    },
}


# ── DB Tables ────────────────────────────────────────────────────────

def _ensure_tables():
    """Create backtest tables."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stress_backtest_results (
            crisis TEXT,
            sector_etf TEXT,
            sector TEXT,
            peak_date TEXT,
            trough_date TEXT,
            peak_price REAL,
            trough_price REAL,
            actual_drawdown REAL,
            assumed_drawdown REAL,
            calibration_error REAL,
            PRIMARY KEY (crisis, sector_etf)
        );
        CREATE TABLE IF NOT EXISTS stress_calibration (
            scenario TEXT,
            sector TEXT,
            assumed_impact REAL,
            calibrated_impact REAL,
            source_crisis TEXT,
            calibration_date TEXT,
            PRIMARY KEY (scenario, sector)
        );
    """)
    conn.commit()
    conn.close()


# ── Data Fetching ────────────────────────────────────────────────────

def _fetch_crisis_data(tickers: list[str], start: str, end: str) -> dict:
    """Fetch price data for tickers during a crisis period.

    Uses yfinance. Returns {ticker: {peak_price, trough_price, drawdown}}.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return {}

    results = {}

    # Extend date range to capture peak and trough
    for ticker in tickers:
        try:
            data = yf.download(
                ticker, start=start, end=end,
                progress=False, auto_adjust=True,
            )
            if data.empty or len(data) < 5:
                logger.warning(f"{ticker}: insufficient data for crisis period")
                continue

            # Handle MultiIndex columns from yfinance
            if hasattr(data.columns, 'levels'):
                close_col = data["Close"]
                if hasattr(close_col, 'columns'):
                    close_col = close_col.iloc[:, 0]
            else:
                close_col = data["Close"]

            peak_price = float(close_col.max())
            trough_price = float(close_col.min())
            peak_date = str(close_col.idxmax().date())
            trough_date = str(close_col.idxmin().date())

            if peak_price > 0:
                drawdown = (trough_price - peak_price) / peak_price
            else:
                drawdown = 0.0

            results[ticker] = {
                "peak_price": round(peak_price, 2),
                "trough_price": round(trough_price, 2),
                "peak_date": peak_date,
                "trough_date": trough_date,
                "drawdown": round(drawdown, 4),
            }

        except Exception as e:
            logger.warning(f"{ticker}: fetch failed: {e}")
            continue

    return results


# ── Calibration ──────────────────────────────────────────────────────

def _calibrate_scenarios(backtest_results: dict) -> dict:
    """Compare actual drawdowns to our scenario assumptions.

    Returns calibration recommendations per scenario per sector.
    """
    from tools.stress_test import STRESS_SCENARIOS

    calibrations = {}

    for crisis_key, crisis_data in backtest_results.items():
        crisis_info = CRISIS_PERIODS[crisis_key]
        scenario_key = crisis_info["scenario_map"]

        if scenario_key not in STRESS_SCENARIOS:
            continue

        scenario = STRESS_SCENARIOS[scenario_key]
        sector_impacts = scenario["sector_impacts"]

        for ticker, actual in crisis_data.items():
            sector = SECTOR_ETFS.get(ticker)
            if not sector or sector == "S&P 500":
                continue

            assumed = sector_impacts.get(sector, scenario["market_shock"])
            actual_dd = actual["drawdown"]

            calibrations[(scenario_key, sector)] = {
                "scenario": scenario_key,
                "sector": sector,
                "assumed_impact": assumed,
                "actual_drawdown": actual_dd,
                "calibrated_impact": actual_dd,  # Use actual as new calibrated value
                "error": round(abs(assumed - actual_dd), 4),
                "source_crisis": crisis_key,
                "conservative": assumed < actual_dd,  # Are we underestimating risk?
            }

    return calibrations


def _generate_updated_scenarios(calibrations: dict) -> dict:
    """Generate updated STRESS_SCENARIOS with calibrated values.

    Uses a blend: 60% actual historical + 40% current assumption
    to avoid overfitting to a single crisis.
    """
    from tools.stress_test import STRESS_SCENARIOS
    import copy

    updated = copy.deepcopy(STRESS_SCENARIOS)
    BLEND_ACTUAL = 0.6
    BLEND_ASSUMED = 0.4

    for (scenario_key, sector), cal in calibrations.items():
        if scenario_key in updated:
            old = updated[scenario_key]["sector_impacts"].get(sector)
            if old is not None:
                blended = (cal["actual_drawdown"] * BLEND_ACTUAL +
                           old * BLEND_ASSUMED)
                updated[scenario_key]["sector_impacts"][sector] = round(blended, 3)

    return updated


# ── HTML Report ──────────────────────────────────────────────────────

def _render_backtest_html(backtest_results: dict, calibrations: dict) -> str:
    """Render backtest comparison as HTML."""
    html = f"""
    <div style="font-family: -apple-system, sans-serif; background:#0E1117; color:#E0E0E0; padding:24px; max-width:900px;">
    <h1 style="color:white;">Stress Test Backtester</h1>
    <p style="color:#888;">{date.today().strftime('%B %d, %Y')} — Calibrating scenarios against historical crises</p>
    """

    for crisis_key, crisis_info in CRISIS_PERIODS.items():
        data = backtest_results.get(crisis_key, {})
        if not data:
            continue

        spy_dd = data.get("SPY", {}).get("drawdown", 0)
        html += f"""
        <div style="margin:24px 0;">
            <h2 style="color:#4FC3F7; margin-bottom:8px;">{crisis_info['name']}</h2>
            <p style="color:#888; font-size:13px;">
                Peak: {crisis_info['peak']} → Trough: {crisis_info['trough']} ·
                SPY: <span style="color:#FF1744;">{spy_dd*100:.1f}%</span> ·
                Maps to: <span style="color:#FFD54F;">{crisis_info['scenario_map']}</span>
            </p>
            <table style="width:100%; border-collapse:collapse; margin:8px 0;">
            <tr style="border-bottom:2px solid #333;">
                <th style="text-align:left; padding:8px; color:#888;">Sector</th>
                <th style="text-align:right; padding:8px; color:#888;">Actual</th>
                <th style="text-align:right; padding:8px; color:#888;">Our Assumption</th>
                <th style="text-align:right; padding:8px; color:#888;">Error</th>
                <th style="text-align:left; padding:8px; color:#888;">Assessment</th>
            </tr>
        """

        from tools.stress_test import STRESS_SCENARIOS
        scenario_key = crisis_info["scenario_map"]
        scenario = STRESS_SCENARIOS.get(scenario_key, {})
        sector_impacts = scenario.get("sector_impacts", {})

        for ticker in sorted(data.keys()):
            if ticker == "SPY":
                continue
            sector = SECTOR_ETFS.get(ticker, ticker)
            actual_dd = data[ticker]["drawdown"]
            assumed = sector_impacts.get(sector, scenario.get("market_shock", 0))
            error = abs(assumed - actual_dd)

            if error < 0.03:
                assessment = "ACCURATE"
                assess_color = "#69F0AE"
            elif assumed > actual_dd:
                assessment = "TOO CONSERVATIVE"
                assess_color = "#FFD54F"
            else:
                assessment = "UNDERESTIMATES RISK"
                assess_color = "#FF1744"

            html += f"""
            <tr style="border-bottom:1px solid #1e2130;">
                <td style="padding:8px;">{sector} ({ticker})</td>
                <td style="text-align:right; padding:8px; color:#FF8A65;">{actual_dd*100:.1f}%</td>
                <td style="text-align:right; padding:8px; color:#B0BEC5;">{assumed*100:.1f}%</td>
                <td style="text-align:right; padding:8px; color:{'#FF1744' if error > 0.1 else '#FFD54F' if error > 0.05 else '#69F0AE'};">{error*100:.1f}pp</td>
                <td style="padding:8px; color:{assess_color}; font-size:12px;">{assessment}</td>
            </tr>"""

        html += "</table></div>"

    # Summary stats
    total_cals = len(calibrations)
    underestimates = sum(1 for c in calibrations.values() if not c["conservative"])
    accurate = sum(1 for c in calibrations.values() if c["error"] < 0.03)

    html += f"""
    <div style="background:#1e2130; padding:16px; border-radius:8px; margin:24px 0;">
        <h3 style="color:#B0BEC5; margin-top:0;">Calibration Summary</h3>
        <p style="color:#CCC;">
            {total_cals} sector-scenario pairs tested ·
            <span style="color:#69F0AE;">{accurate} accurate (±3pp)</span> ·
            <span style="color:#FF1744;">{underestimates} underestimate risk</span> ·
            <span style="color:#FFD54F;">{total_cals - accurate - underestimates} too conservative</span>
        </p>
    </div>
    <p style="color:#555; font-size:11px;">
        Calibrated values use 60/40 blend (actual/assumed) to avoid overfitting.
        Source: yfinance sector ETF data.
    </p>
    </div>"""

    return html


# ── Main ─────────────────────────────────────────────────────────────

def run():
    """Run stress test backtester against historical crises."""
    init_db()
    _ensure_tables()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  STRESS TEST BACKTESTER")
    print("=" * 60)

    tickers = list(SECTOR_ETFS.keys())
    all_backtest_results = {}

    for crisis_key, crisis_info in CRISIS_PERIODS.items():
        print(f"\n  Fetching {crisis_info['name']}...")
        data = _fetch_crisis_data(
            tickers, crisis_info["peak"], crisis_info["trough"])

        if not data:
            print(f"    SKIPPED (no data)")
            continue

        all_backtest_results[crisis_key] = data
        spy_dd = data.get("SPY", {}).get("drawdown", 0)
        print(f"    SPY: {spy_dd*100:.1f}% | {len(data)} ETFs fetched")

        # Persist per-sector results
        rows = []
        from tools.stress_test import STRESS_SCENARIOS
        scenario_key = crisis_info["scenario_map"]
        scenario = STRESS_SCENARIOS.get(scenario_key, {})
        sector_impacts = scenario.get("sector_impacts", {})

        for ticker, result in data.items():
            sector = SECTOR_ETFS.get(ticker, ticker)
            assumed = sector_impacts.get(sector, scenario.get("market_shock", 0))
            error = abs(assumed - result["drawdown"])

            rows.append((
                crisis_key, ticker, sector,
                result["peak_date"], result["trough_date"],
                result["peak_price"], result["trough_price"],
                result["drawdown"], assumed, error,
            ))

            dd_pct = result["drawdown"] * 100
            assumed_pct = assumed * 100
            err_pct = error * 100
            icon = "✓" if err_pct < 3 else "!" if err_pct < 10 else "✗"
            print(f"    {icon} {ticker:>4} ({sector:<25}) actual={dd_pct:+6.1f}%  "
                  f"assumed={assumed_pct:+6.1f}%  error={err_pct:.1f}pp")

        if rows:
            upsert_many(
                "stress_backtest_results",
                ["crisis", "sector_etf", "sector", "peak_date", "trough_date",
                 "peak_price", "trough_price", "actual_drawdown",
                 "assumed_drawdown", "calibration_error"],
                rows,
            )

    if not all_backtest_results:
        print("  No backtest data available")
        print("=" * 60)
        return

    # Calibrate
    calibrations = _calibrate_scenarios(all_backtest_results)
    updated_scenarios = _generate_updated_scenarios(calibrations)

    # Persist calibrations
    cal_rows = [
        (c["scenario"], c["sector"], c["assumed_impact"],
         c["calibrated_impact"], c["source_crisis"], today)
        for c in calibrations.values()
    ]
    if cal_rows:
        upsert_many(
            "stress_calibration",
            ["scenario", "sector", "assumed_impact", "calibrated_impact",
             "source_crisis", "calibration_date"],
            cal_rows,
        )

    # Generate HTML report
    html = _render_backtest_html(all_backtest_results, calibrations)
    upsert_many(
        "intelligence_reports",
        ["topic", "topic_type", "expert_type", "regime",
         "symbols_covered", "report_html", "metadata"],
        [("stress_backtest", "backtest", "risk", "neutral",
          ",".join(tickers), html,
          json.dumps({
              "crises": list(all_backtest_results.keys()),
              "calibrations": len(calibrations),
          }))],
    )

    # Print calibration summary
    underestimates = sum(1 for c in calibrations.values() if not c["conservative"])
    print(f"\n  Calibration complete: {len(calibrations)} sector-scenario pairs")
    print(f"  Risk underestimates: {underestimates}")

    # Print the biggest calibration errors
    sorted_cals = sorted(calibrations.values(), key=lambda x: -x["error"])
    if sorted_cals:
        print("\n  Biggest calibration errors:")
        for c in sorted_cals[:5]:
            direction = "UNDER" if not c["conservative"] else "OVER"
            print(f"    {c['scenario']:<15} {c['sector']:<25} "
                  f"assumed={c['assumed_impact']*100:+.1f}% "
                  f"actual={c['actual_drawdown']*100:+.1f}% "
                  f"({direction})")

    print("=" * 60)
    return calibrations


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    run()
