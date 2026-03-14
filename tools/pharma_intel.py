"""Pharma Intelligence — clinical trials, CMS utilization, and Rx trends.

Tracks clinical trial activity (ClinicalTrials.gov), Medicare claims/utilization
(CMS provider data), and prescription volume trends for healthcare/pharma stocks.
Only computes scores for Health Care sector symbols (~80 of the 903-stock universe).

Runs weekly (7-day gate). Free data sources, no API keys required.

Usage:
  python -m tools.pharma_intel
"""

import json
import logging
import time
import traceback
from datetime import date, datetime, timedelta
from urllib.parse import quote

import requests

from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

# ── Sponsor → Ticker mapping ───────────────────────────────────────────

PHARMA_SPONSOR_MAP = {
    "Pfizer": "PFE", "Eli Lilly": "LLY", "Eli Lilly and Company": "LLY",
    "Johnson & Johnson": "JNJ", "Merck Sharp & Dohme": "MRK", "Merck": "MRK",
    "AbbVie": "ABBV", "Bristol-Myers Squibb": "BMY", "Bristol Myers Squibb": "BMY",
    "Amgen": "AMGN", "Gilead Sciences": "GILD", "Regeneron Pharmaceuticals": "REGN",
    "Vertex Pharmaceuticals": "VRTX", "Moderna": "MRNA",
    "Biogen": "BIIB", "Illumina": "ILMN",
    "AstraZeneca": "AZN", "Novartis": "NVS", "Roche": "RHHBY",
    "Novo Nordisk": "NVO", "Sanofi": "SNY", "GSK": "GSK",
    "Takeda": "TAK", "Daiichi Sankyo": "DSNKY",
    "BioNTech": "BNTX", "Argenx": "ARGX",
    "Alnylam Pharmaceuticals": "ALNY", "Exact Sciences": "EXAS",
    "Intuitive Surgical": "ISRG", "Edwards Lifesciences": "EW",
    "Stryker": "SYK", "Medtronic": "MDT", "Abbott Laboratories": "ABT",
    "Becton Dickinson": "BDX", "Boston Scientific": "BSX",
    "Dexcom": "DXCM", "Hologic": "HOLX",
    "UnitedHealth Group": "UNH", "Elevance Health": "ELV",
    "Cigna": "CI", "Humana": "HUM", "Centene": "CNC",
    "HCA Healthcare": "HCA", "Tenet Healthcare": "THC",
    "CVS Health": "CVS", "Walgreens": "WBA",
    "McKesson": "MCK", "Cardinal Health": "CAH",
}

# Reverse map: ticker → list of sponsor names for lookup
TICKER_TO_SPONSORS: dict[str, list[str]] = {}
for _sponsor, _ticker in PHARMA_SPONSOR_MAP.items():
    TICKER_TO_SPONSORS.setdefault(_ticker, []).append(_sponsor)

# Phase ordering for transition scoring
PHASE_ORDER = {
    "EARLY_PHASE1": 0, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4,
}

# ── DB Table Creation ──────────────────────────────────────────────────

def _ensure_tables():
    """Create pharma_intel tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pharma_intel_raw (
            symbol TEXT,
            date TEXT,
            source TEXT,
            metric TEXT,
            value REAL,
            details TEXT,
            PRIMARY KEY (symbol, date, source, metric)
        );
        CREATE TABLE IF NOT EXISTS pharma_intel_scores (
            symbol TEXT,
            date TEXT,
            pharma_intel_score REAL,
            trial_velocity_score REAL,
            stage_shift_score REAL,
            cms_score REAL,
            rx_score REAL,
            details TEXT,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.commit()
    conn.close()


# ── Weekly Gate ────────────────────────────────────────────────────────

def _should_run() -> bool:
    """Only run once per 7 days."""
    rows = query("SELECT MAX(date) as last_run FROM pharma_intel_scores")
    if not rows or not rows[0]["last_run"]:
        return True
    last = datetime.strptime(rows[0]["last_run"], "%Y-%m-%d").date()
    return (date.today() - last).days >= 7


# ── Sector Filter ─────────────────────────────────────────────────────

def _get_healthcare_symbols() -> list[str]:
    """Get only healthcare sector symbols from universe."""
    rows = query("SELECT symbol FROM stock_universe WHERE sector = 'Health Care'")
    return [r["symbol"] for r in rows]


# ── Data Source 1: ClinicalTrials.gov ──────────────────────────────────

CT_BASE = "https://clinicaltrials.gov/api/v2/studies"
CT_ACTIVE_STATUSES = "RECRUITING,ACTIVE_NOT_RECRUITING,ENROLLING_BY_INVITATION"


def _fetch_trials_for_sponsor(sponsor_name: str) -> list[dict]:
    """Fetch active clinical trials for a sponsor from ClinicalTrials.gov v2 API."""
    params = {
        "query.spons": sponsor_name,
        "filter.overallStatus": CT_ACTIVE_STATUSES,
        "pageSize": 50,
    }
    try:
        resp = requests.get(CT_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("studies", [])
    except Exception as e:
        logger.warning(f"ClinicalTrials.gov error for {sponsor_name}: {e}")
        return []


def _parse_phase(phase_list: list[str] | str | None) -> str | None:
    """Extract the highest phase from a study's phase field."""
    if not phase_list:
        return None
    if isinstance(phase_list, str):
        phase_list = [phase_list]
    best = None
    best_order = -1
    for p in phase_list:
        clean = p.upper().replace(" ", "").replace("/", "")
        for key, order in PHASE_ORDER.items():
            if key in clean and order > best_order:
                best = key
                best_order = order
    return best


def _score_trials(studies: list[dict]) -> dict:
    """Score a set of clinical trials for a sponsor.

    Returns dict with:
      - total_active: count of active trials
      - new_90d: trials started in last 90 days
      - phase_counts: {phase: count}
      - advanced_phases: count of Phase 3+ trials
      - enrollment_ratio: avg (actual / target) where available
      - trial_velocity_score: 0-100
      - stage_shift_score: 0-100
    """
    today = date.today()
    cutoff_90d = today - timedelta(days=90)

    total_active = len(studies)
    new_90d = 0
    phase_counts: dict[str, int] = {}
    advanced_phases = 0
    enrollment_ratios: list[float] = []

    for study in studies:
        proto = study.get("protocolSection", {})
        status_mod = proto.get("statusModule", {})
        design_mod = proto.get("designModule", {})
        enroll_mod = proto.get("designModule", {}).get("enrollmentInfo", {})

        # Check start date for new_90d
        start_str = status_mod.get("startDateStruct", {}).get("date", "")
        if start_str:
            try:
                # Format varies: "2024-01-15" or "2024-01"
                if len(start_str) == 7:
                    start_str += "-01"
                start_dt = datetime.strptime(start_str, "%Y-%m-%d").date()
                if start_dt >= cutoff_90d:
                    new_90d += 1
            except ValueError:
                pass

        # Phase tracking
        phases = design_mod.get("phases", [])
        phase = _parse_phase(phases)
        if phase:
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
            if phase in ("PHASE3", "PHASE4"):
                advanced_phases += 1

        # Enrollment velocity
        enroll_count = enroll_mod.get("count")
        enroll_type = enroll_mod.get("type", "")
        if enroll_count and enroll_type.upper() == "ACTUAL":
            # We only have actual; compare to a reasonable baseline
            enrollment_ratios.append(1.0)  # actual means enrollment met target
        elif enroll_count and enroll_type.upper() == "ESTIMATED":
            enrollment_ratios.append(0.5)  # still enrolling

    # Compute trial velocity score (0-100)
    # Factors: total active trials, new starts, advanced phases
    if total_active == 0:
        trial_velocity_score = 30.0  # no trials = below average
    else:
        # Base from total active trials (0-40 points)
        base = min(total_active / 30.0 * 40.0, 40.0)
        # New trials bonus (0-25 points)
        new_bonus = min(new_90d / 8.0 * 25.0, 25.0)
        # Advanced phase bonus (0-25 points)
        adv_bonus = min(advanced_phases / 10.0 * 25.0, 25.0)
        # Enrollment velocity (0-10 points)
        avg_enroll = sum(enrollment_ratios) / len(enrollment_ratios) if enrollment_ratios else 0.5
        enroll_bonus = avg_enroll * 10.0
        trial_velocity_score = min(base + new_bonus + adv_bonus + enroll_bonus, 100.0)

    # Stage shift score: reward companies with trials in advanced phases
    if total_active == 0:
        stage_shift_score = 30.0
    else:
        p3_ratio = advanced_phases / max(total_active, 1)
        p2_count = phase_counts.get("PHASE2", 0)
        p2_ratio = p2_count / max(total_active, 1)
        # Phase 3+ weighted heavily
        stage_shift_score = min(p3_ratio * 60.0 + p2_ratio * 30.0 + 20.0, 100.0)

    return {
        "total_active": total_active,
        "new_90d": new_90d,
        "phase_counts": phase_counts,
        "advanced_phases": advanced_phases,
        "enrollment_ratio": sum(enrollment_ratios) / len(enrollment_ratios) if enrollment_ratios else None,
        "trial_velocity_score": round(trial_velocity_score, 1),
        "stage_shift_score": round(stage_shift_score, 1),
    }


def _fetch_clinical_trials(healthcare_symbols: list[str]) -> dict[str, dict]:
    """Fetch and score clinical trials for all healthcare symbols with known sponsors.

    Returns {symbol: trial_score_dict}.
    """
    results: dict[str, dict] = {}
    processed_tickers: set[str] = set()

    for sponsor, ticker in PHARMA_SPONSOR_MAP.items():
        if ticker in processed_tickers:
            continue
        if ticker not in healthcare_symbols:
            continue

        sponsors = TICKER_TO_SPONSORS.get(ticker, [sponsor])
        all_studies: list[dict] = []

        for sp in sponsors:
            print(f"  [CT.gov] Fetching trials for {sp} ({ticker})...")
            studies = _fetch_trials_for_sponsor(sp)
            all_studies.extend(studies)
            time.sleep(0.5)  # rate limit

        # Deduplicate by NCT ID
        seen_ncts: set[str] = set()
        unique_studies: list[dict] = []
        for s in all_studies:
            nct = s.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "")
            if nct and nct not in seen_ncts:
                seen_ncts.add(nct)
                unique_studies.append(s)
            elif not nct:
                unique_studies.append(s)

        score_data = _score_trials(unique_studies)
        results[ticker] = score_data
        processed_tickers.add(ticker)

    return results


# ── Data Source 2: CMS Medicare Utilization (proxy approach) ───────────

# For MVP: use managed care / hospital / device company stock performance
# as a proxy for healthcare utilization trends.
# Companies strongly correlated with Medicare utilization:
UTILIZATION_PROXIES = {
    # Managed care
    "UNH": "managed_care", "ELV": "managed_care", "CI": "managed_care",
    "HUM": "managed_care", "CNC": "managed_care",
    # Hospitals
    "HCA": "hospital", "THC": "hospital",
    # Distributors
    "MCK": "distributor", "CAH": "distributor",
    # Pharmacy retail
    "CVS": "pharmacy", "WBA": "pharmacy",
    # Devices
    "MDT": "device", "ABT": "device", "BSX": "device",
    "SYK": "device", "EW": "device", "ISRG": "device",
    "BDX": "device", "DXCM": "device", "HOLX": "device",
}


def _compute_cms_scores(healthcare_symbols: list[str]) -> dict[str, float]:
    """Compute CMS / utilization proxy scores for healthcare symbols.

    Uses recent price momentum of managed care and hospital stocks as a proxy
    for healthcare utilization trends. Also checks for any available price data
    to gauge sector health.
    """
    scores: dict[str, float] = {}
    today = date.today().isoformat()
    lookback_30 = (date.today() - timedelta(days=45)).isoformat()
    lookback_90 = (date.today() - timedelta(days=120)).isoformat()

    # Get sector-level utilization signal from proxy stocks
    proxy_returns: dict[str, list[float]] = {
        "managed_care": [], "hospital": [], "distributor": [],
        "pharmacy": [], "device": [],
    }

    for symbol, category in UTILIZATION_PROXIES.items():
        rows = query(
            """SELECT close FROM price_data
               WHERE symbol = ? AND date >= ?
               ORDER BY date ASC""",
            [symbol, lookback_90],
        )
        if len(rows) >= 2:
            ret = (rows[-1]["close"] - rows[0]["close"]) / rows[0]["close"]
            proxy_returns[category].append(ret)

    # Compute category averages
    category_scores: dict[str, float] = {}
    for cat, returns in proxy_returns.items():
        if returns:
            avg_ret = sum(returns) / len(returns)
            # Map return to 0-100 score: -20% → 20, 0% → 50, +20% → 80
            score = max(10, min(90, 50 + avg_ret * 150))
            category_scores[cat] = score
        else:
            category_scores[cat] = 50.0  # neutral

    # Overall utilization score (average of categories)
    overall_util = sum(category_scores.values()) / len(category_scores) if category_scores else 50.0

    for sym in healthcare_symbols:
        if sym in UTILIZATION_PROXIES:
            cat = UTILIZATION_PROXIES[sym]
            # Direct proxy: use its own category score weighted with overall
            scores[sym] = round(category_scores.get(cat, 50.0) * 0.7 + overall_util * 0.3, 1)
        else:
            # Non-proxy healthcare stock: use overall utilization as baseline
            scores[sym] = round(overall_util, 1)

    return scores


# ── Data Source 3: Prescription / Rx Trends ────────────────────────────

# Pharma companies whose revenue is heavily driven by Rx volume
RX_HEAVY_TICKERS = {
    "PFE", "LLY", "MRK", "ABBV", "BMY", "AMGN", "GILD", "REGN", "VRTX",
    "MRNA", "BIIB", "AZN", "NVS", "NVO", "SNY", "GSK", "TAK", "BNTX",
    "ALNY", "ARGX",
}


def _compute_rx_scores(healthcare_symbols: list[str]) -> dict[str, float]:
    """Compute prescription trend scores using price momentum as proxy.

    CMS Part D data is lagged ~1 year, so for MVP we use recent price performance
    of Rx-heavy pharma stocks relative to sector as a proxy for volume trends.
    """
    scores: dict[str, float] = {}
    lookback = (date.today() - timedelta(days=60)).isoformat()

    # Compute sector average return
    sector_returns: list[float] = []
    symbol_returns: dict[str, float] = {}

    for sym in healthcare_symbols:
        rows = query(
            """SELECT close FROM price_data
               WHERE symbol = ? AND date >= ?
               ORDER BY date ASC""",
            [sym, lookback],
        )
        if len(rows) >= 2:
            ret = (rows[-1]["close"] - rows[0]["close"]) / rows[0]["close"]
            symbol_returns[sym] = ret
            sector_returns.append(ret)

    sector_avg = sum(sector_returns) / len(sector_returns) if sector_returns else 0.0

    for sym in healthcare_symbols:
        if sym in symbol_returns:
            relative_ret = symbol_returns[sym] - sector_avg
            # Rx-heavy companies get a boost/penalty based on relative performance
            if sym in RX_HEAVY_TICKERS:
                # Map relative return to score: -10% → 25, 0% → 55, +10% → 85
                base_score = 55 + relative_ret * 300
            else:
                # Non-Rx companies: more neutral, smaller range
                base_score = 50 + relative_ret * 150
            scores[sym] = round(max(10, min(90, base_score)), 1)
        else:
            scores[sym] = 50.0  # neutral

    return scores


# ── Main Scoring Logic ─────────────────────────────────────────────────

def _compute_final_scores(
    healthcare_symbols: list[str],
    trial_data: dict[str, dict],
    cms_scores: dict[str, float],
    rx_scores: dict[str, float],
) -> list[tuple]:
    """Combine all sub-scores into final pharma_intel_score.

    Returns list of tuples for upsert into pharma_intel_scores.
    """
    today = date.today().isoformat()
    rows = []

    for sym in healthcare_symbols:
        # Trial velocity score (combined velocity + stage shift)
        td = trial_data.get(sym)
        if td:
            trial_score = td["trial_velocity_score"] * 0.6 + td["stage_shift_score"] * 0.4
            stage_shift = td["stage_shift_score"]
        else:
            trial_score = 50.0  # neutral for companies without trial data
            stage_shift = 50.0

        cms = cms_scores.get(sym, 50.0)
        rx = rx_scores.get(sym, 50.0)

        # Weighted composite
        # trial_velocity: 0.45, cms: 0.25, rx: 0.30
        pharma_score = round(
            trial_score * 0.45 +
            cms * 0.25 +
            rx * 0.30,
            1,
        )
        pharma_score = max(0, min(100, pharma_score))

        details = json.dumps({
            "trial_velocity": round(trial_score, 1),
            "stage_shift": round(stage_shift, 1),
            "cms": cms,
            "rx": rx,
            "has_trial_data": td is not None,
            "active_trials": td["total_active"] if td else 0,
            "new_trials_90d": td["new_90d"] if td else 0,
            "advanced_phases": td["advanced_phases"] if td else 0,
        })

        rows.append((
            sym, today, pharma_score,
            round(trial_score, 1), round(stage_shift, 1),
            cms, rx, details,
        ))

    return rows


def _store_raw_data(trial_data: dict[str, dict], cms_scores: dict[str, float],
                    rx_scores: dict[str, float]):
    """Store raw metrics in pharma_intel_raw for audit trail."""
    today = date.today().isoformat()
    raw_rows = []

    for sym, td in trial_data.items():
        raw_rows.append((sym, today, "clinicaltrials", "total_active",
                         td["total_active"], json.dumps(td["phase_counts"])))
        raw_rows.append((sym, today, "clinicaltrials", "new_90d",
                         td["new_90d"], None))
        raw_rows.append((sym, today, "clinicaltrials", "advanced_phases",
                         td["advanced_phases"], None))
        raw_rows.append((sym, today, "clinicaltrials", "trial_velocity_score",
                         td["trial_velocity_score"], None))
        raw_rows.append((sym, today, "clinicaltrials", "stage_shift_score",
                         td["stage_shift_score"], None))

    for sym, score in cms_scores.items():
        raw_rows.append((sym, today, "cms_proxy", "utilization_score",
                         score, None))

    for sym, score in rx_scores.items():
        raw_rows.append((sym, today, "rx_proxy", "rx_trend_score",
                         score, None))

    if raw_rows:
        upsert_many(
            "pharma_intel_raw",
            ["symbol", "date", "source", "metric", "value", "details"],
            raw_rows,
        )


# ── Entry Point ────────────────────────────────────────────────────────

def run():
    """Run the Pharma Intelligence module."""
    print("=" * 60)
    print("PHARMA INTELLIGENCE MODULE")
    print("=" * 60)

    init_db()
    _ensure_tables()

    if not _should_run():
        print("  Skipping — last run was less than 7 days ago.")
        return

    # Get healthcare symbols
    healthcare_symbols = _get_healthcare_symbols()
    if not healthcare_symbols:
        print("  No healthcare symbols found in stock_universe. Skipping.")
        return
    print(f"  Found {len(healthcare_symbols)} healthcare sector symbols.")

    # Source 1: Clinical trials
    print("\n── Clinical Trials (ClinicalTrials.gov) ──")
    try:
        trial_data = _fetch_clinical_trials(healthcare_symbols)
        print(f"  Fetched trial data for {len(trial_data)} sponsors/tickers.")
    except Exception as e:
        logger.error(f"Clinical trials fetch failed: {e}")
        traceback.print_exc()
        trial_data = {}

    # Source 2: CMS utilization proxy
    print("\n── CMS Utilization Proxy ──")
    try:
        cms_scores = _compute_cms_scores(healthcare_symbols)
        print(f"  Computed CMS proxy scores for {len(cms_scores)} symbols.")
    except Exception as e:
        logger.error(f"CMS score computation failed: {e}")
        traceback.print_exc()
        cms_scores = {}

    # Source 3: Rx trends proxy
    print("\n── Prescription Trends ──")
    try:
        rx_scores = _compute_rx_scores(healthcare_symbols)
        print(f"  Computed Rx trend scores for {len(rx_scores)} symbols.")
    except Exception as e:
        logger.error(f"Rx score computation failed: {e}")
        traceback.print_exc()
        rx_scores = {}

    # Store raw data
    print("\n── Storing raw data ──")
    try:
        _store_raw_data(trial_data, cms_scores, rx_scores)
        print("  Raw data stored.")
    except Exception as e:
        logger.error(f"Raw data storage failed: {e}")
        traceback.print_exc()

    # Compute and store final scores
    print("\n── Computing final scores ──")
    score_rows = _compute_final_scores(healthcare_symbols, trial_data,
                                       cms_scores, rx_scores)

    upsert_many(
        "pharma_intel_scores",
        ["symbol", "date", "pharma_intel_score", "trial_velocity_score",
         "stage_shift_score", "cms_score", "rx_score", "details"],
        score_rows,
    )

    # Summary
    if score_rows:
        scores = [r[2] for r in score_rows]
        avg_score = sum(scores) / len(scores)
        top_5 = sorted(score_rows, key=lambda r: r[2], reverse=True)[:5]
        print(f"\n  Scored {len(score_rows)} healthcare symbols.")
        print(f"  Average pharma_intel_score: {avg_score:.1f}")
        print(f"  Top 5:")
        for r in top_5:
            print(f"    {r[0]:6s}  score={r[2]:.1f}  (trial={r[3]:.0f}  cms={r[5]:.0f}  rx={r[6]:.0f})")

    print("\n" + "=" * 60)
    print("PHARMA INTELLIGENCE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    run()
