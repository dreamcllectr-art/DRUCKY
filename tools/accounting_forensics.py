"""Accounting Forensics Scanner — detect earnings manipulation & quality red flags.

Computes per symbol:
- Beneish M-Score (8 components, composite) — probability of earnings manipulation
- Accruals ratio — earnings backed by cash or just accounting entries?
- Cash conversion quality & trend — is OCF consistently tracking net income?
- Receivables stuffing — AR growing faster than revenue?
- Inventory buildup — inventory growing faster than COGS?
- Depreciation manipulation — extending asset lives to boost earnings?
- Piotroski F-Score & Altman Z-Score (from FMP /score endpoint)
- Composite forensic score (0-100)

Academic basis: Beneish (1999), Sloan (1996) accruals anomaly.
"""

import sys
import time
import argparse
import numpy as np
from datetime import datetime

_project_root = str(__import__("pathlib").Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import (
    FMP_API_KEY, BENEISH_MANIPULATION_THRESHOLD, ACCRUALS_RED_FLAG,
    CASH_CONVERSION_MIN, GROWTH_DIVERGENCE_FLAG, FORENSIC_RED_ALERT,
    FORENSIC_WARNING, PIOTROSKI_WEAK, ALTMAN_DISTRESS,
)
from tools.db import init_db, upsert_many, query, get_conn
from tools.fetch_fmp_fundamentals import fmp_get


def _safe(val, default=None):
    """Safely convert to float, returning default if None/invalid."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _slope(values):
    """Compute linear regression slope for a list of values (oldest first)."""
    clean = [v for v in values if v is not None]
    if len(clean) < 3:
        return None
    x = np.arange(len(clean))
    return float(np.polyfit(x, clean, 1)[0])


def fetch_financials(symbol):
    """Fetch 5 years of income stmt, balance sheet, cash flow from FMP."""
    income = fmp_get(f"/income-statement/{symbol}", {"period": "annual", "limit": 5})
    balance = fmp_get(f"/balance-sheet-statement/{symbol}", {"period": "annual", "limit": 5})
    cashflow = fmp_get(f"/cash-flow-statement/{symbol}", {"period": "annual", "limit": 5})

    if not income or not balance or not cashflow:
        return None, None, None
    if not isinstance(income, list) or not isinstance(balance, list) or not isinstance(cashflow, list):
        return None, None, None

    return income, balance, cashflow


def fetch_fmp_scores(symbol):
    """Fetch Piotroski F-Score and Altman Z-Score from FMP."""
    data = fmp_get(f"/score", {"symbol": symbol})
    if not data or not isinstance(data, list) or not data:
        return None, None
    d = data[0]
    piotroski = _safe(d.get("piotroskiScore"))
    altman = _safe(d.get("altmanZScore"))
    return piotroski, altman


def compute_accruals(income, balance, cashflow):
    """Compute accruals ratio and cash conversion for latest year."""
    if not income or not cashflow or not balance:
        return {}

    latest_inc = income[0]
    latest_cf = cashflow[0]
    latest_bs = balance[0]

    net_income = _safe(latest_inc.get("netIncome"), 0)
    ocf = _safe(latest_cf.get("operatingCashFlow"), 0)
    total_assets = _safe(latest_bs.get("totalAssets"), 1)

    metrics = {}

    # Accruals ratio: (NI - OCF) / Total Assets
    if total_assets > 0:
        accruals_ratio = (net_income - ocf) / total_assets
        metrics["forensic_accruals_ratio"] = round(accruals_ratio, 4)

    # Cash conversion: OCF / NI (should be > 1.0 for healthy companies)
    if net_income > 0:
        cash_conversion = ocf / net_income
        metrics["forensic_cash_conversion"] = round(cash_conversion, 4)

    # Cash conversion trend over available years
    conversions = []
    for i in range(min(len(income), len(cashflow))):
        ni = _safe(income[i].get("netIncome"), 0)
        cf = _safe(cashflow[i].get("operatingCashFlow"), 0)
        if ni > 0:
            conversions.append(cf / ni)

    if len(conversions) >= 3:
        # Reverse so oldest is first for slope calculation
        trend = _slope(list(reversed(conversions)))
        if trend is not None:
            metrics["forensic_cash_conversion_trend"] = round(trend, 4)

    return metrics


def compute_receivables_flag(income, balance):
    """Check if receivables are growing faster than revenue (channel stuffing)."""
    if len(income) < 2 or len(balance) < 2:
        return {}

    rev_curr = _safe(income[0].get("revenue"), 0)
    rev_prev = _safe(income[1].get("revenue"), 0)
    ar_curr = _safe(balance[0].get("netReceivables"), 0)
    ar_prev = _safe(balance[1].get("netReceivables"), 0)

    if rev_prev <= 0 or ar_prev <= 0:
        return {}

    rev_growth = (rev_curr - rev_prev) / rev_prev
    ar_growth = (ar_curr - ar_prev) / ar_prev

    flag = 1 if (ar_growth > rev_growth * GROWTH_DIVERGENCE_FLAG and ar_growth > 0.05) else 0
    return {"forensic_receivables_flag": flag}


def compute_inventory_flag(income, balance):
    """Check if inventory is growing faster than COGS."""
    if len(income) < 2 or len(balance) < 2:
        return {}

    cogs_curr = _safe(income[0].get("costOfRevenue"), 0)
    cogs_prev = _safe(income[1].get("costOfRevenue"), 0)
    inv_curr = _safe(balance[0].get("inventory"), 0)
    inv_prev = _safe(balance[1].get("inventory"), 0)

    if cogs_prev <= 0 or inv_prev <= 0:
        return {}

    cogs_growth = (cogs_curr - cogs_prev) / cogs_prev
    inv_growth = (inv_curr - inv_prev) / inv_prev

    flag = 1 if (inv_growth > cogs_growth * GROWTH_DIVERGENCE_FLAG and inv_growth > 0.05) else 0
    return {"forensic_inventory_flag": flag}


def compute_depreciation_trend(income, balance):
    """Check if depreciation/PPE ratio is declining (extending asset lives)."""
    ratios = []
    for i in range(min(len(income), len(balance))):
        depr = _safe(income[i].get("depreciationAndAmortization"), 0)
        ppe = _safe(balance[i].get("propertyPlantEquipmentNet"), 0)
        if ppe > 0 and depr > 0:
            ratios.append(depr / ppe)

    if len(ratios) < 3:
        return {}

    # Reverse so oldest first
    trend = _slope(list(reversed(ratios)))
    metrics = {"forensic_depr_ratio": round(ratios[0], 4)}
    if trend is not None:
        metrics["forensic_depr_trend"] = round(trend, 4)
    return metrics


def compute_beneish_mscore(income, balance, cashflow):
    """Compute Beneish M-Score from 8 component indices.

    M-Score = -4.84 + 0.920*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
              + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI

    Score > -1.78 suggests likely earnings manipulation.
    """
    if len(income) < 2 or len(balance) < 2 or len(cashflow) < 2:
        return {}

    # Current and prior year
    inc_c, inc_p = income[0], income[1]
    bs_c, bs_p = balance[0], balance[1]
    cf_c = cashflow[0]

    # Extract values
    rev_c = _safe(inc_c.get("revenue"), 0)
    rev_p = _safe(inc_p.get("revenue"), 0)
    ar_c = _safe(bs_c.get("netReceivables"), 0)
    ar_p = _safe(bs_p.get("netReceivables"), 0)
    gp_c = _safe(inc_c.get("grossProfit"), 0)
    gp_p = _safe(inc_p.get("grossProfit"), 0)
    ta_c = _safe(bs_c.get("totalAssets"), 0)
    ta_p = _safe(bs_p.get("totalAssets"), 0)
    ppe_c = _safe(bs_c.get("propertyPlantEquipmentNet"), 0)
    ppe_p = _safe(bs_p.get("propertyPlantEquipmentNet"), 0)
    depr_c = _safe(inc_c.get("depreciationAndAmortization"), 0)
    depr_p = _safe(inc_p.get("depreciationAndAmortization"), 0)
    sga_c = _safe(inc_c.get("sellingGeneralAndAdministrativeExpenses"), 0)
    sga_p = _safe(inc_p.get("sellingGeneralAndAdministrativeExpenses"), 0)
    ni_c = _safe(inc_c.get("netIncome"), 0)
    ocf_c = _safe(cf_c.get("operatingCashFlow"), 0)
    ltd_c = _safe(bs_c.get("longTermDebt"), 0)
    ltd_p = _safe(bs_p.get("longTermDebt"), 0)
    cl_c = _safe(bs_c.get("totalCurrentLiabilities"), 0)
    cl_p = _safe(bs_p.get("totalCurrentLiabilities"), 0)
    ca_c = _safe(bs_c.get("totalCurrentAssets"), 0)
    ca_p = _safe(bs_p.get("totalCurrentAssets"), 0)

    # Guard against division by zero
    if rev_p <= 0 or ta_p <= 0 or ta_c <= 0 or rev_c <= 0:
        return {}

    # 1. DSRI - Days Sales in Receivables Index
    dsr_c = ar_c / rev_c if rev_c > 0 else 0
    dsr_p = ar_p / rev_p if rev_p > 0 else 0
    dsri = dsr_c / dsr_p if dsr_p > 0 else 1.0

    # 2. GMI - Gross Margin Index
    gm_c = gp_c / rev_c if rev_c > 0 else 0
    gm_p = gp_p / rev_p if rev_p > 0 else 0
    gmi = gm_p / gm_c if gm_c > 0 else 1.0

    # 3. AQI - Asset Quality Index (non-current, non-PPE assets / total assets)
    aq_c = 1 - (ca_c + ppe_c) / ta_c if ta_c > 0 else 0
    aq_p = 1 - (ca_p + ppe_p) / ta_p if ta_p > 0 else 0
    aqi = aq_c / aq_p if aq_p > 0 else 1.0

    # 4. SGI - Sales Growth Index
    sgi = rev_c / rev_p if rev_p > 0 else 1.0

    # 5. DEPI - Depreciation Index
    depr_rate_c = depr_c / (depr_c + ppe_c) if (depr_c + ppe_c) > 0 else 0
    depr_rate_p = depr_p / (depr_p + ppe_p) if (depr_p + ppe_p) > 0 else 0
    depi = depr_rate_p / depr_rate_c if depr_rate_c > 0 else 1.0

    # 6. SGAI - SGA Expense Index
    sga_ratio_c = sga_c / rev_c if rev_c > 0 else 0
    sga_ratio_p = sga_p / rev_p if rev_p > 0 else 0
    sgai = sga_ratio_c / sga_ratio_p if sga_ratio_p > 0 else 1.0

    # 7. LVGI - Leverage Index
    lev_c = (ltd_c + cl_c) / ta_c if ta_c > 0 else 0
    lev_p = (ltd_p + cl_p) / ta_p if ta_p > 0 else 0
    lvgi = lev_c / lev_p if lev_p > 0 else 1.0

    # 8. TATA - Total Accruals to Total Assets
    tata = (ni_c - ocf_c) / ta_c if ta_c > 0 else 0

    # Composite M-Score
    mscore = (-4.84
              + 0.920 * dsri
              + 0.528 * gmi
              + 0.404 * aqi
              + 0.892 * sgi
              + 0.115 * depi
              - 0.172 * sgai
              + 4.679 * tata
              - 0.327 * lvgi)

    return {"forensic_mscore": round(mscore, 4)}


def compute_forensic_score(metrics, piotroski, altman):
    """Composite forensic score (0-100). Higher = cleaner books."""
    score = 50  # Start neutral

    # Accruals ratio (weight: 15 pts)
    ar = metrics.get("forensic_accruals_ratio")
    if ar is not None:
        if ar < 0:
            score += 10  # Negative accruals = cash > earnings, very healthy
        elif ar < 0.05:
            score += 5
        elif ar > ACCRUALS_RED_FLAG:
            score -= 15
        elif ar > 0.07:
            score -= 8

    # Cash conversion (weight: 15 pts)
    cc = metrics.get("forensic_cash_conversion")
    if cc is not None:
        if cc > 1.2:
            score += 10
        elif cc > 1.0:
            score += 5
        elif cc < CASH_CONVERSION_MIN:
            score -= 15
        elif cc < 0.9:
            score -= 8

    # Cash conversion trend (weight: 5 pts)
    cct = metrics.get("forensic_cash_conversion_trend")
    if cct is not None:
        if cct > 0.02:
            score += 5
        elif cct < -0.05:
            score -= 5

    # Receivables flag (weight: 8 pts)
    if metrics.get("forensic_receivables_flag") == 1:
        score -= 8

    # Inventory flag (weight: 8 pts)
    if metrics.get("forensic_inventory_flag") == 1:
        score -= 8

    # Depreciation trend (weight: 5 pts)
    dt = metrics.get("forensic_depr_trend")
    if dt is not None and dt < -0.01:
        score -= 5

    # Beneish M-Score (weight: 20 pts — biggest single signal)
    ms = metrics.get("forensic_mscore")
    if ms is not None:
        if ms > BENEISH_MANIPULATION_THRESHOLD:
            score -= 20  # Likely manipulator
        elif ms > -2.22:
            score -= 8   # Grey zone
        elif ms < -3.0:
            score += 10  # Very clean

    # Piotroski F-Score (weight: 10 pts)
    if piotroski is not None:
        if piotroski >= 7:
            score += 10
        elif piotroski >= 5:
            score += 3
        elif piotroski < PIOTROSKI_WEAK:
            score -= 10

    # Altman Z-Score (weight: 7 pts)
    if altman is not None:
        if altman > 3.0:
            score += 7
        elif altman < ALTMAN_DISTRESS:
            score -= 7

    return max(0, min(100, score))


def generate_alerts(symbol, date, metrics, piotroski, altman):
    """Generate forensic alert rows for flagged issues."""
    alerts = []

    ar = metrics.get("forensic_accruals_ratio")
    if ar is not None and ar > ACCRUALS_RED_FLAG:
        severity = "RED_FLAG" if ar > 0.15 else "WARNING"
        alerts.append((symbol, date, "HIGH_ACCRUALS", severity,
                        f"Accruals ratio {ar:.3f} (>{ACCRUALS_RED_FLAG})"))

    cc = metrics.get("forensic_cash_conversion")
    if cc is not None and cc < CASH_CONVERSION_MIN:
        severity = "RED_FLAG" if cc < 0.5 else "WARNING"
        alerts.append((symbol, date, "LOW_CASH_CONVERSION", severity,
                        f"Cash conversion {cc:.2f} (<{CASH_CONVERSION_MIN})"))

    if metrics.get("forensic_receivables_flag") == 1:
        alerts.append((symbol, date, "RECEIVABLES_STUFFING", "WARNING",
                        "Receivables growing >1.5x revenue growth"))

    if metrics.get("forensic_inventory_flag") == 1:
        alerts.append((symbol, date, "INVENTORY_BUILDUP", "WARNING",
                        "Inventory growing >1.5x COGS growth"))

    dt = metrics.get("forensic_depr_trend")
    if dt is not None and dt < -0.01:
        alerts.append((symbol, date, "DEPR_MANIPULATION", "WARNING",
                        f"Depreciation/PPE declining (slope {dt:.4f}) — may be extending asset lives"))

    ms = metrics.get("forensic_mscore")
    if ms is not None and ms > BENEISH_MANIPULATION_THRESHOLD:
        alerts.append((symbol, date, "HIGH_MSCORE", "RED_FLAG",
                        f"Beneish M-Score {ms:.2f} (>{BENEISH_MANIPULATION_THRESHOLD}) — likely manipulation"))

    if piotroski is not None and piotroski < PIOTROSKI_WEAK:
        alerts.append((symbol, date, "LOW_PIOTROSKI", "WARNING",
                        f"Piotroski F-Score {piotroski:.0f} (<{PIOTROSKI_WEAK})"))

    if altman is not None and altman < ALTMAN_DISTRESS:
        alerts.append((symbol, date, "DISTRESS_ZONE", "RED_FLAG",
                        f"Altman Z-Score {altman:.2f} (<{ALTMAN_DISTRESS}) — bankruptcy risk"))

    return alerts


def run(symbols=None):
    """Run accounting forensics for all stocks or a specified list."""
    init_db()

    if not FMP_API_KEY:
        print("  ERROR: FMP_API_KEY not set in .env")
        return

    if symbols is None:
        symbols = [r["symbol"] for r in query("SELECT symbol FROM stock_universe")]
    if not symbols:
        print("  No stocks to analyze.")
        return

    print(f"Running accounting forensics on {len(symbols)} stocks...")

    today = datetime.now().strftime("%Y-%m-%d")
    all_fund_rows = []
    all_alerts = []
    red_flags = []
    pristine = []

    for i, symbol in enumerate(symbols):
        # Fetch financial statements
        income, balance, cashflow = fetch_financials(symbol)
        if income is None:
            continue

        # Compute all forensic metrics
        metrics = {}
        metrics.update(compute_accruals(income, balance, cashflow))
        metrics.update(compute_receivables_flag(income, balance))
        metrics.update(compute_inventory_flag(income, balance))
        metrics.update(compute_depreciation_trend(income, balance))
        metrics.update(compute_beneish_mscore(income, balance, cashflow))

        # Fetch FMP pre-computed scores
        piotroski, altman = fetch_fmp_scores(symbol)
        if piotroski is not None:
            metrics["forensic_piotroski"] = piotroski
        if altman is not None:
            metrics["forensic_altman_z"] = altman

        # Composite forensic score
        fscore = compute_forensic_score(metrics, piotroski, altman)
        metrics["forensic_score"] = fscore

        # Store in fundamentals table
        for metric_name, value in metrics.items():
            if value is not None:
                all_fund_rows.append((symbol, metric_name, float(value)))

        # Generate alerts
        alerts = generate_alerts(symbol, today, metrics, piotroski, altman)
        all_alerts.extend(alerts)

        # Track for summary
        if fscore < FORENSIC_RED_ALERT:
            red_flags.append((symbol, fscore, metrics.get("forensic_mscore")))
        elif fscore >= 80:
            pristine.append((symbol, fscore))

        if (i + 1) % 50 == 0:
            print(f"  Processed {i + 1}/{len(symbols)} stocks...")
            time.sleep(0.5)

    # Save to database
    upsert_many("fundamentals", ["symbol", "metric", "value"], all_fund_rows)
    if all_alerts:
        upsert_many("forensic_alerts",
                     ["symbol", "date", "alert_type", "severity", "detail"],
                     all_alerts)

    # Summary
    print(f"\n  Forensic analysis complete: {len(all_fund_rows)} data points, {len(all_alerts)} alerts")

    if red_flags:
        red_flags.sort(key=lambda x: x[1])
        print(f"\n  RED FLAGS ({len(red_flags)} stocks with forensic score < {FORENSIC_RED_ALERT}):")
        for sym, score, ms in red_flags[:20]:
            ms_str = f"M-Score: {ms:.2f}" if ms is not None else "M-Score: N/A"
            print(f"    {sym:12s} | Forensic: {score:5.0f} | {ms_str}")

    if pristine:
        pristine.sort(key=lambda x: x[1], reverse=True)
        print(f"\n  PRISTINE BOOKS ({len(pristine)} stocks with forensic score >= 80):")
        for sym, score in pristine[:20]:
            print(f"    {sym:12s} | Forensic: {score:5.0f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Accounting Forensics Scanner")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols (default: full universe)")
    args = parser.parse_args()

    sym_list = args.symbols.split(",") if args.symbols else None
    run(sym_list)
