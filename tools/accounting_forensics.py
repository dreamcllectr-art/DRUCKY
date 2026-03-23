"""Accounting Forensics Scanner — detect earnings manipulation & quality red flags.
Beneish M-Score, accruals ratio, cash conversion, receivables/inventory flags,
Piotroski F-Score & Altman Z-Score. Composite forensic score (0-100)."""
import sys, time, argparse
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
_project_root = str(__import__("pathlib").Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
from tools.config import (FMP_API_KEY, BENEISH_MANIPULATION_THRESHOLD, ACCRUALS_RED_FLAG,
    CASH_CONVERSION_MIN, GROWTH_DIVERGENCE_FLAG, FORENSIC_RED_ALERT, FORENSIC_WARNING, PIOTROSKI_WEAK, ALTMAN_DISTRESS)
from tools.db import init_db, upsert_many, query, get_conn
from tools.fetch_fmp_fundamentals import fmp_get

def _safe(val, default=None):
    if val is None: return default
    try: return float(val)
    except (ValueError, TypeError): return default

def _slope(values):
    clean = [v for v in values if v is not None]
    if len(clean) < 3: return None
    return float(np.polyfit(np.arange(len(clean)), clean, 1)[0])

def fetch_financials(symbol):
    income = fmp_get(f"/income-statement/{symbol}", {"period": "annual", "limit": 5})
    balance = fmp_get(f"/balance-sheet-statement/{symbol}", {"period": "annual", "limit": 5})
    cashflow = fmp_get(f"/cash-flow-statement/{symbol}", {"period": "annual", "limit": 5})
    if not income or not balance or not cashflow: return None, None, None
    if not isinstance(income, list) or not isinstance(balance, list) or not isinstance(cashflow, list): return None, None, None
    return income, balance, cashflow

def fetch_fmp_scores(symbol):
    data = fmp_get(f"/score", {"symbol": symbol})
    if not data or not isinstance(data, list) or not data: return None, None
    return _safe(data[0].get("piotroskiScore")), _safe(data[0].get("altmanZScore"))

def compute_accruals(income, balance, cashflow):
    if not income or not cashflow or not balance: return {}
    ni = _safe(income[0].get("netIncome"), 0)
    ocf = _safe(cashflow[0].get("operatingCashFlow"), 0)
    ta = _safe(balance[0].get("totalAssets"), 1)
    metrics = {}
    if ta > 0: metrics["forensic_accruals_ratio"] = round((ni - ocf) / ta, 4)
    if ni > 0: metrics["forensic_cash_conversion"] = round(ocf / ni, 4)
    conversions = []
    for i in range(min(len(income), len(cashflow))):
        n = _safe(income[i].get("netIncome"), 0)
        c = _safe(cashflow[i].get("operatingCashFlow"), 0)
        if n > 0: conversions.append(c / n)
    if len(conversions) >= 3:
        trend = _slope(list(reversed(conversions)))
        if trend is not None: metrics["forensic_cash_conversion_trend"] = round(trend, 4)
    return metrics

def _growth_flag(curr, prev, curr_ref, prev_ref, threshold):
    if prev_ref <= 0 or prev <= 0: return {}
    ref_growth = (curr_ref - prev_ref) / prev_ref
    val_growth = (curr - prev) / prev
    return 1 if (val_growth > ref_growth * threshold and val_growth > 0.05) else 0

def compute_receivables_flag(income, balance):
    if len(income) < 2 or len(balance) < 2: return {}
    flag = _growth_flag(_safe(balance[0].get("netReceivables"), 0), _safe(balance[1].get("netReceivables"), 0),
                        _safe(income[0].get("revenue"), 0), _safe(income[1].get("revenue"), 0), GROWTH_DIVERGENCE_FLAG)
    return {"forensic_receivables_flag": flag} if isinstance(flag, int) else {}

def compute_inventory_flag(income, balance):
    if len(income) < 2 or len(balance) < 2: return {}
    flag = _growth_flag(_safe(balance[0].get("inventory"), 0), _safe(balance[1].get("inventory"), 0),
                        _safe(income[0].get("costOfRevenue"), 0), _safe(income[1].get("costOfRevenue"), 0), GROWTH_DIVERGENCE_FLAG)
    return {"forensic_inventory_flag": flag} if isinstance(flag, int) else {}

def compute_depreciation_trend(income, balance):
    ratios = []
    for i in range(min(len(income), len(balance))):
        depr = _safe(income[i].get("depreciationAndAmortization"), 0)
        ppe = _safe(balance[i].get("propertyPlantEquipmentNet"), 0)
        if ppe > 0 and depr > 0: ratios.append(depr / ppe)
    if len(ratios) < 3: return {}
    metrics = {"forensic_depr_ratio": round(ratios[0], 4)}
    trend = _slope(list(reversed(ratios)))
    if trend is not None: metrics["forensic_depr_trend"] = round(trend, 4)
    return metrics

def compute_beneish_mscore(income, balance, cashflow):
    """M-Score > -1.78 suggests likely earnings manipulation (Beneish 1999)."""
    if len(income) < 2 or len(balance) < 2 or len(cashflow) < 2: return {}
    inc_c, inc_p, bs_c, bs_p, cf_c = income[0], income[1], balance[0], balance[1], cashflow[0]
    g = lambda d, k: _safe(d.get(k), 0)
    rev_c, rev_p = g(inc_c, "revenue"), g(inc_p, "revenue")
    ar_c, ar_p = g(bs_c, "netReceivables"), g(bs_p, "netReceivables")
    gp_c, gp_p = g(inc_c, "grossProfit"), g(inc_p, "grossProfit")
    ta_c, ta_p = g(bs_c, "totalAssets"), g(bs_p, "totalAssets")
    ppe_c, ppe_p = g(bs_c, "propertyPlantEquipmentNet"), g(bs_p, "propertyPlantEquipmentNet")
    depr_c, depr_p = g(inc_c, "depreciationAndAmortization"), g(inc_p, "depreciationAndAmortization")
    sga_c, sga_p = g(inc_c, "sellingGeneralAndAdministrativeExpenses"), g(inc_p, "sellingGeneralAndAdministrativeExpenses")
    ni_c, ocf_c = g(inc_c, "netIncome"), g(cf_c, "operatingCashFlow")
    ltd_c, ltd_p = g(bs_c, "longTermDebt"), g(bs_p, "longTermDebt")
    cl_c, cl_p = g(bs_c, "totalCurrentLiabilities"), g(bs_p, "totalCurrentLiabilities")
    ca_c, ca_p = g(bs_c, "totalCurrentAssets"), g(bs_p, "totalCurrentAssets")
    if rev_p <= 0 or ta_p <= 0 or ta_c <= 0 or rev_c <= 0: return {}
    def ratio(a, b): return a / b if b > 0 else 1.0
    dsri = ratio(ar_c / rev_c, ar_p / rev_p) if rev_c > 0 and rev_p > 0 else 1.0
    gmi = ratio(gp_p / rev_p if rev_p > 0 else 0, gp_c / rev_c if rev_c > 0 else 1)
    aq_c = 1 - (ca_c + ppe_c) / ta_c if ta_c > 0 else 0
    aq_p = 1 - (ca_p + ppe_p) / ta_p if ta_p > 0 else 0
    aqi = ratio(aq_c, aq_p)
    sgi = ratio(rev_c, rev_p)
    depi = ratio(depr_p / (depr_p + ppe_p) if (depr_p + ppe_p) > 0 else 0, depr_c / (depr_c + ppe_c) if (depr_c + ppe_c) > 0 else 1)
    sgai = ratio(sga_c / rev_c if rev_c > 0 else 0, sga_p / rev_p if rev_p > 0 else 1)
    lvgi = ratio((ltd_c + cl_c) / ta_c if ta_c > 0 else 0, (ltd_p + cl_p) / ta_p if ta_p > 0 else 1)
    tata = (ni_c - ocf_c) / ta_c if ta_c > 0 else 0
    mscore = -4.84 + 0.920*dsri + 0.528*gmi + 0.404*aqi + 0.892*sgi + 0.115*depi - 0.172*sgai + 4.679*tata - 0.327*lvgi
    return {"forensic_mscore": round(mscore, 4)}

def compute_forensic_score(metrics, piotroski, altman):
    """Composite forensic score (0-100). Higher = cleaner books."""
    score = 50
    ar = metrics.get("forensic_accruals_ratio")
    if ar is not None:
        if ar < 0: score += 10
        elif ar < 0.05: score += 5
        elif ar > ACCRUALS_RED_FLAG: score -= 15
        elif ar > 0.07: score -= 8
    cc = metrics.get("forensic_cash_conversion")
    if cc is not None:
        if cc > 1.2: score += 10
        elif cc > 1.0: score += 5
        elif cc < CASH_CONVERSION_MIN: score -= 15
        elif cc < 0.9: score -= 8
    cct = metrics.get("forensic_cash_conversion_trend")
    if cct is not None:
        if cct > 0.02: score += 5
        elif cct < -0.05: score -= 5
    if metrics.get("forensic_receivables_flag") == 1: score -= 8
    if metrics.get("forensic_inventory_flag") == 1: score -= 8
    dt = metrics.get("forensic_depr_trend")
    if dt is not None and dt < -0.01: score -= 5
    ms = metrics.get("forensic_mscore")
    if ms is not None:
        if ms > BENEISH_MANIPULATION_THRESHOLD: score -= 20
        elif ms > -2.22: score -= 8
        elif ms < -3.0: score += 10
    if piotroski is not None:
        if piotroski >= 7: score += 10
        elif piotroski >= 5: score += 3
        elif piotroski < PIOTROSKI_WEAK: score -= 10
    if altman is not None:
        if altman > 3.0: score += 7
        elif altman < ALTMAN_DISTRESS: score -= 7
    return max(0, min(100, score))

def generate_alerts(symbol, dt, metrics, piotroski, altman):
    alerts = []
    def _add(cond, val, key, sev_fn, msg):
        if cond: alerts.append((symbol, dt, key, sev_fn(val) if callable(sev_fn) else sev_fn, msg))
    ar = metrics.get("forensic_accruals_ratio")
    if ar is not None and ar > ACCRUALS_RED_FLAG:
        _add(True, ar, "HIGH_ACCRUALS", lambda v: "RED_FLAG" if v > 0.15 else "WARNING", f"Accruals ratio {ar:.3f} (>{ACCRUALS_RED_FLAG})")
    cc = metrics.get("forensic_cash_conversion")
    if cc is not None and cc < CASH_CONVERSION_MIN:
        _add(True, cc, "LOW_CASH_CONVERSION", lambda v: "RED_FLAG" if v < 0.5 else "WARNING", f"Cash conversion {cc:.2f} (<{CASH_CONVERSION_MIN})")
    if metrics.get("forensic_receivables_flag") == 1:
        alerts.append((symbol, dt, "RECEIVABLES_STUFFING", "WARNING", "Receivables growing >1.5x revenue growth"))
    if metrics.get("forensic_inventory_flag") == 1:
        alerts.append((symbol, dt, "INVENTORY_BUILDUP", "WARNING", "Inventory growing >1.5x COGS growth"))
    depr_t = metrics.get("forensic_depr_trend")
    if depr_t is not None and depr_t < -0.01:
        alerts.append((symbol, dt, "DEPR_MANIPULATION", "WARNING", f"Depreciation/PPE declining (slope {depr_t:.4f})"))
    ms = metrics.get("forensic_mscore")
    if ms is not None and ms > BENEISH_MANIPULATION_THRESHOLD:
        alerts.append((symbol, dt, "HIGH_MSCORE", "RED_FLAG", f"Beneish M-Score {ms:.2f} (>{BENEISH_MANIPULATION_THRESHOLD})"))
    if piotroski is not None and piotroski < PIOTROSKI_WEAK:
        alerts.append((symbol, dt, "LOW_PIOTROSKI", "WARNING", f"Piotroski F-Score {piotroski:.0f} (<{PIOTROSKI_WEAK})"))
    if altman is not None and altman < ALTMAN_DISTRESS:
        alerts.append((symbol, dt, "DISTRESS_ZONE", "RED_FLAG", f"Altman Z-Score {altman:.2f} (<{ALTMAN_DISTRESS})"))
    return alerts

def _process_symbol(symbol, today):
    """Process one symbol — designed for ThreadPoolExecutor."""
    income, balance, cashflow = fetch_financials(symbol)
    if income is None:
        return None
    metrics = {}
    metrics.update(compute_accruals(income, balance, cashflow))
    metrics.update(compute_receivables_flag(income, balance))
    metrics.update(compute_inventory_flag(income, balance))
    metrics.update(compute_depreciation_trend(income, balance))
    metrics.update(compute_beneish_mscore(income, balance, cashflow))
    piotroski, altman = fetch_fmp_scores(symbol)
    if piotroski is not None: metrics["forensic_piotroski"] = piotroski
    if altman is not None: metrics["forensic_altman_z"] = altman
    fscore = compute_forensic_score(metrics, piotroski, altman)
    metrics["forensic_score"] = fscore
    fund_rows = [(symbol, mn, float(v)) for mn, v in metrics.items() if v is not None]
    alerts = generate_alerts(symbol, today, metrics, piotroski, altman)
    return fund_rows, alerts, fscore, metrics.get("forensic_mscore")


def run(symbols=None):
    init_db()
    if not FMP_API_KEY: print("  ERROR: FMP_API_KEY not set in .env"); return
    if symbols is None:
        symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
    if not symbols: print("  No stocks to analyze."); return

    # Cache-gate: skip symbols with recent forensics AND no recent earnings
    cached = {r["symbol"] for r in query(
        "SELECT DISTINCT symbol FROM fundamentals WHERE metric = 'forensic_score'"
    )}
    recent_earnings = {r["symbol"] for r in query(
        "SELECT DISTINCT symbol FROM earnings_calendar WHERE date >= (CURRENT_DATE - INTERVAL '45 days')::text"
    )}
    # Re-run if: no cached score, OR recent earnings (annual financials changed)
    symbols = [s for s in symbols if s not in cached or s in recent_earnings]
    skipped = len([r for r in query("SELECT symbol FROM stock_universe")]) - len(symbols)
    print(f"Running accounting forensics on {len(symbols)} stocks (skipped {skipped} cached)...")

    today = datetime.now().strftime("%Y-%m-%d")
    all_fund_rows, all_alerts, red_flags, pristine = [], [], [], []
    done = 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_process_symbol, sym, today): sym for sym in symbols}
        for fut in as_completed(futures):
            result = fut.result()
            done += 1
            if result is None:
                continue
            fund_rows, alerts, fscore, mscore = result
            all_fund_rows.extend(fund_rows)
            all_alerts.extend(alerts)
            if fscore < FORENSIC_RED_ALERT:
                red_flags.append((futures[fut], fscore, mscore))
            elif fscore >= 80:
                pristine.append((futures[fut], fscore))
            if done % 50 == 0:
                print(f"  Processed {done}/{len(symbols)} stocks...")
    upsert_many("fundamentals", ["symbol", "metric", "value"], all_fund_rows)
    if all_alerts:
        upsert_many("forensic_alerts", ["symbol", "date", "alert_type", "severity", "detail"], all_alerts)
    print(f"\n  Forensic analysis complete: {len(all_fund_rows)} data points, {len(all_alerts)} alerts")
    if red_flags:
        red_flags.sort(key=lambda x: x[1])
        print(f"\n  RED FLAGS ({len(red_flags)} stocks with forensic score < {FORENSIC_RED_ALERT}):")
        for sym, score, ms in red_flags[:20]:
            print(f"    {sym:12s} | Forensic: {score:5.0f} | {f'M-Score: {ms:.2f}' if ms is not None else 'M-Score: N/A'}")
    if pristine:
        pristine.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  PRISTINE BOOKS ({len(pristine)} stocks with forensic score >= 80):")
        for sym, score in pristine[:20]: print(f"    {sym:12s} | Forensic: {score:5.0f}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Accounting Forensics Scanner")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    args = parser.parse_args()
    run(args.symbols.split(",") if args.symbols else None)
