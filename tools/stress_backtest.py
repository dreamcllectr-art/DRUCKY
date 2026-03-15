"""Stress Test Backtester — calibrate scenario assumptions against historical crises.
Pulls actual sector ETF drawdowns during GFC/COVID/2022/2018 via yfinance,
compares to stress_test.py assumptions, and generates calibrated values."""
import json, logging
from datetime import date, datetime
from tools.db import init_db, get_conn, query, upsert_many
logger = logging.getLogger(__name__)

SECTOR_ETFS = {"XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care",
    "XLP": "Consumer Staples", "XLI": "Industrials", "XLB": "Materials", "XLRE": "Real Estate",
    "XLU": "Utilities", "XLC": "Communication Services", "XLY": "Consumer Discretionary", "SPY": "S&P 500"}
CRISIS_PERIODS = {
    "gfc": {"name": "Global Financial Crisis (2007-2009)", "peak": "2007-10-09", "trough": "2009-03-09", "scenario_map": "recession"},
    "covid": {"name": "COVID Crash (2020)", "peak": "2020-02-19", "trough": "2020-03-23", "scenario_map": "credit_crunch"},
    "rate_shock_2022": {"name": "2022 Rate Shock", "peak": "2022-01-03", "trough": "2022-10-12", "scenario_map": "rate_shock"},
    "q4_2018": {"name": "Q4 2018 Selloff", "peak": "2018-09-20", "trough": "2018-12-24", "scenario_map": "tech_selloff"},
}

def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS stress_backtest_results (crisis TEXT, sector_etf TEXT, sector TEXT,
            peak_date TEXT, trough_date TEXT, peak_price REAL, trough_price REAL, actual_drawdown REAL,
            assumed_drawdown REAL, calibration_error REAL, PRIMARY KEY (crisis, sector_etf));
        CREATE TABLE IF NOT EXISTS stress_calibration (scenario TEXT, sector TEXT, assumed_impact REAL,
            calibrated_impact REAL, source_crisis TEXT, calibration_date TEXT, PRIMARY KEY (scenario, sector));""")
    conn.commit(); conn.close()

def _fetch_crisis_data(tickers, start, end):
    try: import yfinance as yf
    except ImportError: logger.error("yfinance not installed"); return {}
    results = {}
    for ticker in tickers:
        try:
            data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if data.empty or len(data) < 5: continue
            close_col = data["Close"]
            if hasattr(close_col, 'columns'): close_col = close_col.iloc[:, 0]
            peak_price, trough_price = float(close_col.max()), float(close_col.min())
            results[ticker] = {"peak_price": round(peak_price, 2), "trough_price": round(trough_price, 2),
                "peak_date": str(close_col.idxmax().date()), "trough_date": str(close_col.idxmin().date()),
                "drawdown": round((trough_price - peak_price) / peak_price, 4) if peak_price > 0 else 0.0}
        except Exception as e: logger.warning(f"{ticker}: fetch failed: {e}")
    return results

def _calibrate_scenarios(backtest_results):
    from tools.stress_test import STRESS_SCENARIOS
    calibrations = {}
    for crisis_key, crisis_data in backtest_results.items():
        scenario_key = CRISIS_PERIODS[crisis_key]["scenario_map"]
        if scenario_key not in STRESS_SCENARIOS: continue
        scenario = STRESS_SCENARIOS[scenario_key]
        for ticker, actual in crisis_data.items():
            sector = SECTOR_ETFS.get(ticker)
            if not sector or sector == "S&P 500": continue
            assumed = scenario["sector_impacts"].get(sector, scenario["market_shock"])
            calibrations[(scenario_key, sector)] = {"scenario": scenario_key, "sector": sector,
                "assumed_impact": assumed, "actual_drawdown": actual["drawdown"],
                "calibrated_impact": actual["drawdown"], "error": round(abs(assumed - actual["drawdown"]), 4),
                "source_crisis": crisis_key, "conservative": assumed < actual["drawdown"]}
    return calibrations

def _generate_updated_scenarios(calibrations):
    from tools.stress_test import STRESS_SCENARIOS
    import copy
    updated = copy.deepcopy(STRESS_SCENARIOS)
    for (sk, sector), cal in calibrations.items():
        if sk in updated:
            old = updated[sk]["sector_impacts"].get(sector)
            if old is not None:
                updated[sk]["sector_impacts"][sector] = round(cal["actual_drawdown"] * 0.6 + old * 0.4, 3)
    return updated

def _render_backtest_html(backtest_results, calibrations):
    from tools.stress_test import STRESS_SCENARIOS
    html = f'<div style="font-family:-apple-system,sans-serif;background:#0E1117;color:#E0E0E0;padding:24px;max-width:900px;">'
    html += f'<h1 style="color:white;">Stress Test Backtester</h1><p style="color:#888;">{date.today().strftime("%B %d, %Y")}</p>'
    for ck, ci in CRISIS_PERIODS.items():
        data = backtest_results.get(ck, {})
        if not data: continue
        spy_dd = data.get("SPY", {}).get("drawdown", 0)
        html += f'<div style="margin:24px 0;"><h2 style="color:#4FC3F7;">{ci["name"]}</h2>'
        html += f'<p style="color:#888;font-size:13px;">Peak: {ci["peak"]} -> Trough: {ci["trough"]} · SPY: <span style="color:#FF1744;">{spy_dd*100:.1f}%</span> · Maps to: <span style="color:#FFD54F;">{ci["scenario_map"]}</span></p>'
        html += '<table style="width:100%;border-collapse:collapse;"><tr style="border-bottom:2px solid #333;"><th style="text-align:left;padding:8px;color:#888;">Sector</th><th style="text-align:right;padding:8px;color:#888;">Actual</th><th style="text-align:right;padding:8px;color:#888;">Assumed</th><th style="text-align:right;padding:8px;color:#888;">Error</th><th style="text-align:left;padding:8px;color:#888;">Assessment</th></tr>'
        sk = ci["scenario_map"]
        scenario = STRESS_SCENARIOS.get(sk, {})
        si = scenario.get("sector_impacts", {})
        for ticker in sorted(data.keys()):
            if ticker == "SPY": continue
            sector = SECTOR_ETFS.get(ticker, ticker)
            ad = data[ticker]["drawdown"]
            assumed = si.get(sector, scenario.get("market_shock", 0))
            err = abs(assumed - ad)
            if err < 0.03: assessment, ac = "ACCURATE", "#69F0AE"
            elif assumed > ad: assessment, ac = "TOO CONSERVATIVE", "#FFD54F"
            else: assessment, ac = "UNDERESTIMATES RISK", "#FF1744"
            ec = "#FF1744" if err > 0.1 else "#FFD54F" if err > 0.05 else "#69F0AE"
            html += f'<tr style="border-bottom:1px solid #1e2130;"><td style="padding:8px;">{sector} ({ticker})</td><td style="text-align:right;padding:8px;color:#FF8A65;">{ad*100:.1f}%</td><td style="text-align:right;padding:8px;color:#B0BEC5;">{assumed*100:.1f}%</td><td style="text-align:right;padding:8px;color:{ec};">{err*100:.1f}pp</td><td style="padding:8px;color:{ac};font-size:12px;">{assessment}</td></tr>'
        html += '</table></div>'
    tc = len(calibrations)
    ue = sum(1 for c in calibrations.values() if not c["conservative"])
    acc = sum(1 for c in calibrations.values() if c["error"] < 0.03)
    html += f'<div style="background:#1e2130;padding:16px;border-radius:8px;margin:24px 0;"><h3 style="color:#B0BEC5;margin-top:0;">Summary</h3>'
    html += f'<p style="color:#CCC;">{tc} pairs · <span style="color:#69F0AE;">{acc} accurate</span> · <span style="color:#FF1744;">{ue} underestimate</span></p></div></div>'
    return html

def run():
    init_db(); _ensure_tables(); today = date.today().isoformat()
    print("\n" + "=" * 60 + "\n  STRESS TEST BACKTESTER\n" + "=" * 60)
    tickers = list(SECTOR_ETFS.keys())
    all_results = {}
    for ck, ci in CRISIS_PERIODS.items():
        print(f"\n  Fetching {ci['name']}...")
        data = _fetch_crisis_data(tickers, ci["peak"], ci["trough"])
        if not data: print(f"    SKIPPED (no data)"); continue
        all_results[ck] = data
        print(f"    SPY: {data.get('SPY', {}).get('drawdown', 0)*100:.1f}% | {len(data)} ETFs")
        from tools.stress_test import STRESS_SCENARIOS
        sk = ci["scenario_map"]
        scenario = STRESS_SCENARIOS.get(sk, {})
        si = scenario.get("sector_impacts", {})
        rows = []
        for ticker, result in data.items():
            sector = SECTOR_ETFS.get(ticker, ticker)
            assumed = si.get(sector, scenario.get("market_shock", 0))
            err = abs(assumed - result["drawdown"])
            rows.append((ck, ticker, sector, result["peak_date"], result["trough_date"], result["peak_price"], result["trough_price"], result["drawdown"], assumed, err))
            icon = "+" if err * 100 < 3 else "!" if err * 100 < 10 else "X"
            print(f"    {icon} {ticker:>4} ({sector:<25}) actual={result['drawdown']*100:+6.1f}%  assumed={assumed*100:+6.1f}%  error={err*100:.1f}pp")
        if rows: upsert_many("stress_backtest_results", ["crisis", "sector_etf", "sector", "peak_date", "trough_date", "peak_price", "trough_price", "actual_drawdown", "assumed_drawdown", "calibration_error"], rows)
    if not all_results: print("  No backtest data\n" + "=" * 60); return
    calibrations = _calibrate_scenarios(all_results)
    _generate_updated_scenarios(calibrations)
    cal_rows = [(c["scenario"], c["sector"], c["assumed_impact"], c["calibrated_impact"], c["source_crisis"], today) for c in calibrations.values()]
    if cal_rows: upsert_many("stress_calibration", ["scenario", "sector", "assumed_impact", "calibrated_impact", "source_crisis", "calibration_date"], cal_rows)
    html = _render_backtest_html(all_results, calibrations)
    upsert_many("intelligence_reports", ["topic", "topic_type", "expert_type", "regime", "symbols_covered", "report_html", "metadata"],
        [("stress_backtest", "backtest", "risk", "neutral", ",".join(tickers), html, json.dumps({"crises": list(all_results.keys()), "calibrations": len(calibrations)}))])
    ue = sum(1 for c in calibrations.values() if not c["conservative"])
    print(f"\n  Calibration complete: {len(calibrations)} pairs | Risk underestimates: {ue}")
    sorted_cals = sorted(calibrations.values(), key=lambda x: -x["error"])
    if sorted_cals:
        print("\n  Biggest errors:")
        for c in sorted_cals[:5]:
            print(f"    {c['scenario']:<15} {c['sector']:<25} assumed={c['assumed_impact']*100:+.1f}% actual={c['actual_drawdown']*100:+.1f}% ({'UNDER' if not c['conservative'] else 'OVER'})")
    print("=" * 60)
    return calibrations

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); init_db(); run()
