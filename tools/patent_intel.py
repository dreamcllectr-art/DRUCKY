"""Patent Intelligence — USPTO patent filing velocity as a leading R&D indicator.
Produces 0-100 patent_intel_score per symbol. Weekly gate (7-day).

Tracks patent filing velocity, technology breadth (CPC classes), and
technology category signals from the USPTO PatentsView API. Accelerating
patent filings are a reliable leading indicator of R&D investment that
precedes revenue inflection by 12-24 months."""
import json, logging, re, time
from datetime import date, datetime, timedelta
import requests
from tools.db import init_db, get_conn, query, upsert_many
from tools.config import SERPER_API_KEY

logger = logging.getLogger(__name__)
WEIGHTS = {"velocity": 0.45, "quality": 0.30, "tech_category": 0.25}
NEUTRAL = 50
RATE_LIMIT_SEC = 0.5

PATENTSVIEW_URL = "https://api.patentsview.org/patents/query"

# ── Company-to-assignee mapping (top filers) ──────────────────────────
COMPANY_ASSIGNEE_MAP = {
    "AAPL": ["Apple Inc."], "GOOGL": ["Google LLC", "Alphabet Inc."],
    "MSFT": ["Microsoft Corporation", "Microsoft Technology Licensing"],
    "AMZN": ["Amazon Technologies, Inc."], "META": ["Meta Platforms, Inc.", "Facebook, Inc."],
    "NVDA": ["NVIDIA Corporation"], "IBM": ["International Business Machines"],
    "INTC": ["Intel Corporation"], "QCOM": ["Qualcomm Incorporated"],
    "CSCO": ["Cisco Technology, Inc."], "ORCL": ["Oracle International Corporation"],
    "CRM": ["Salesforce, Inc."], "ADBE": ["Adobe Inc."],
    "AVGO": ["Broadcom International Pte. Ltd."], "AMD": ["Advanced Micro Devices"],
    "TXN": ["Texas Instruments Incorporated"], "MU": ["Micron Technology"],
    "LRCX": ["Lam Research Corporation"], "AMAT": ["Applied Materials"],
    "KLAC": ["KLA Corporation"],
    "JNJ": ["Johnson & Johnson"], "PFE": ["Pfizer Inc."],
    "LLY": ["Eli Lilly and Company"], "MRK": ["Merck Sharp & Dohme"],
    "ABBV": ["AbbVie Inc."], "BMY": ["Bristol-Myers Squibb"],
    "AMGN": ["Amgen Inc."], "GILD": ["Gilead Sciences"],
    "TMO": ["Thermo Fisher Scientific"], "ABT": ["Abbott Laboratories"],
    "MDT": ["Medtronic"], "SYK": ["Stryker Corporation"],
    "BA": ["The Boeing Company"], "LMT": ["Lockheed Martin Corporation"],
    "RTX": ["Raytheon Technologies"], "GE": ["General Electric Company"],
    "CAT": ["Caterpillar Inc."], "HON": ["Honeywell International"],
    "MMM": ["3M Company"], "DE": ["Deere & Company"],
    "F": ["Ford Global Technologies"], "GM": ["General Motors"],
    "TSLA": ["Tesla, Inc."],
    "XOM": ["ExxonMobil"], "CVX": ["Chevron U.S.A."],
}

# ── CPC technology category mapping ───────────────────────────────────
CPC_CATEGORIES = {
    "G06N": "AI/ML", "G06F": "Computing",
    "H01L": "Semiconductor", "H01M": "Battery/Energy Storage",
    "H04": "Telecom/5G",
    "A61K": "Pharma", "A61P": "Pharma", "A61B": "Medical Devices",
    "C07": "Chemistry", "C12": "Biotech",
    "F03": "Renewable Energy", "H02": "Power Systems",
    "B60": "Automotive", "B25": "Robotics",
    "G16H": "Health IT",
}

# Sector-level bullish signals from technology categories
TECH_CATEGORY_SECTOR_SIGNAL = {
    "AI/ML": 85, "Computing": 75, "Semiconductor": 80,
    "Battery/Energy Storage": 80, "Telecom/5G": 70,
    "Pharma": 75, "Medical Devices": 70, "Biotech": 80,
    "Chemistry": 60, "Renewable Energy": 80, "Power Systems": 70,
    "Automotive": 65, "Robotics": 80, "Health IT": 75,
}


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS patent_intel_raw (
            symbol TEXT, date TEXT, patent_count_90d INTEGER, prior_count_90d INTEGER,
            filing_velocity REAL, cpc_classes TEXT, details TEXT,
            PRIMARY KEY (symbol, date));
        CREATE TABLE IF NOT EXISTS patent_intel_scores (
            symbol TEXT, date TEXT, patent_intel_score REAL, velocity_score REAL,
            quality_score REAL, tech_category_score REAL, details TEXT,
            PRIMARY KEY (symbol, date));""")
    conn.commit(); conn.close()


def _should_run():
    rows = query("SELECT MAX(date) as last_run FROM patent_intel_scores")
    if not rows or not rows[0]["last_run"]: return True
    return (date.today() - datetime.strptime(rows[0]["last_run"], "%Y-%m-%d").date()).days >= 7


def _classify_cpc(cpc_id):
    """Map a CPC subgroup ID to a human-readable technology category."""
    if not cpc_id:
        return None
    cpc_upper = cpc_id.upper().strip()
    # Try longest prefix first for specificity
    for prefix in sorted(CPC_CATEGORIES.keys(), key=len, reverse=True):
        if cpc_upper.startswith(prefix):
            return CPC_CATEGORIES[prefix]
    return None


def _query_patentsview(assignee_name, start_date, end_date):
    """Query PatentsView API for patents granted to an assignee in a date range.
    Returns list of patent dicts with number, date, title, cpc codes."""
    params = {
        "q": json.dumps({"_and": [
            {"_gte": {"patent_date": start_date}},
            {"_lte": {"patent_date": end_date}},
            {"assignee_organization": assignee_name}
        ]}),
        "f": json.dumps(["patent_number", "patent_date", "patent_title", "cpc_subgroup_id"]),
        "o": json.dumps({"per_page": 100})
    }
    try:
        resp = requests.get(PATENTSVIEW_URL, params=params, timeout=20)
        time.sleep(RATE_LIMIT_SEC)
        if resp.status_code != 200:
            logger.warning("PatentsView returned %d for %s", resp.status_code, assignee_name)
            return []
        data = resp.json()
        patents = data.get("patents", [])
        if patents is None:
            return []
        return patents
    except Exception as e:
        logger.warning("PatentsView query failed for %s: %s", assignee_name, e)
        time.sleep(RATE_LIMIT_SEC)
        return []


def _extract_cpc_classes(patents):
    """Extract unique CPC class prefixes (4-char) from patent results."""
    classes = set()
    for p in patents:
        # PatentsView nests CPC data in various formats
        cpc_list = p.get("cpcs", p.get("cpc_subgroup_id", []))
        if isinstance(cpc_list, str):
            cpc_list = [{"cpc_subgroup_id": cpc_list}]
        elif isinstance(cpc_list, list):
            pass
        else:
            continue
        for cpc_item in cpc_list:
            cpc_id = cpc_item if isinstance(cpc_item, str) else cpc_item.get("cpc_subgroup_id", "")
            if cpc_id and len(cpc_id) >= 4:
                classes.add(cpc_id[:4])
    return classes


def _extract_tech_categories(cpc_classes):
    """Map CPC classes to technology categories."""
    categories = set()
    for cls in cpc_classes:
        cat = _classify_cpc(cls)
        if cat:
            categories.add(cat)
    return categories


def _fetch_patent_data():
    """Fetch patent filing data for all tracked companies from USPTO PatentsView.
    Returns dict of {symbol: {count_90d, prior_90d, velocity, cpc_classes, tech_categories}}."""
    today = date.today()
    recent_start = (today - timedelta(days=90)).isoformat()
    recent_end = today.isoformat()
    prior_start = (today - timedelta(days=180)).isoformat()
    prior_end = (today - timedelta(days=91)).isoformat()

    results = {}
    total_patents = 0
    session = requests.Session()

    for ticker, assignees in COMPANY_ASSIGNEE_MAP.items():
        recent_patents = []
        prior_patents = []

        for assignee in assignees:
            # Fetch recent 90-day patents
            recent = _query_patentsview(assignee, recent_start, recent_end)
            recent_patents.extend(recent)

            # Fetch prior 90-day patents
            prior = _query_patentsview(assignee, prior_start, prior_end)
            prior_patents.extend(prior)

        count_90d = len(recent_patents)
        prior_90d = len(prior_patents)
        total_patents += count_90d

        # Calculate filing velocity
        if prior_90d > 0:
            velocity = (count_90d - prior_90d) / prior_90d
        elif count_90d > 0:
            velocity = 1.0
        else:
            velocity = 0.0

        # Extract CPC classes and categories
        all_patents = recent_patents + prior_patents
        cpc_classes = _extract_cpc_classes(all_patents)
        tech_categories = _extract_tech_categories(cpc_classes)

        results[ticker] = {
            "count_90d": count_90d,
            "prior_90d": prior_90d,
            "velocity": round(velocity, 4),
            "cpc_classes": sorted(cpc_classes),
            "tech_categories": sorted(tech_categories),
        }

        # Store raw data
        today_str = today.isoformat()
        upsert_many("patent_intel_raw",
            ["symbol", "date", "patent_count_90d", "prior_count_90d",
             "filing_velocity", "cpc_classes", "details"],
            [(ticker, today_str, count_90d, prior_90d, round(velocity, 4),
              json.dumps(sorted(cpc_classes)),
              json.dumps({
                  "assignees": assignees,
                  "tech_categories": sorted(tech_categories),
                  "recent_patent_count": count_90d,
                  "prior_patent_count": prior_90d,
              }))])

    print(f"    Queried {len(COMPANY_ASSIGNEE_MAP)} companies, found {total_patents} patents")
    return results


def _compute_velocity_score(velocity):
    """Filing Velocity score (0-100) based on 90-day growth rate."""
    if velocity > 0.20:
        # Growth > 20%: score 85-100
        return min(100, round(85 + (velocity - 0.20) * 75, 1))
    elif velocity > 0.05:
        # Growth 5-20%: score 65-85
        return round(65 + (velocity - 0.05) / 0.15 * 20, 1)
    elif velocity > -0.05:
        # Growth -5% to +5%: score 45-65
        return round(45 + (velocity + 0.05) / 0.10 * 20, 1)
    elif velocity > -0.20:
        # Growth -20% to -5%: score 25-45
        return round(25 + (velocity + 0.20) / 0.15 * 20, 1)
    else:
        # Growth < -20%: score 0-25
        return max(0, round(25 + (velocity + 0.20) * 125, 1))


def _compute_quality_score(cpc_classes):
    """Patent Quality score (0-100) based on technology breadth (distinct CPC classes)."""
    n = len(cpc_classes)
    if n >= 5:
        return 80.0
    elif n >= 3:
        return 65.0
    elif n >= 1:
        return 50.0
    else:
        return 40.0


def _compute_tech_category_score(tech_categories):
    """Technology Category Signal score (0-100) based on which tech areas are active."""
    if not tech_categories:
        return NEUTRAL
    scores = []
    for cat in tech_categories:
        if cat in TECH_CATEGORY_SECTOR_SIGNAL:
            scores.append(TECH_CATEGORY_SECTOR_SIGNAL[cat])
    if not scores:
        return NEUTRAL
    # Use the average of matched category signals
    return round(sum(scores) / len(scores), 1)


def _compute_scores(patent_data):
    """Compute composite patent_intel_score for each symbol."""
    today_str = date.today().isoformat()
    rows = []

    for ticker in sorted(patent_data.keys()):
        d = patent_data[ticker]
        v_score = _compute_velocity_score(d["velocity"])
        q_score = _compute_quality_score(d["cpc_classes"])
        t_score = _compute_tech_category_score(d["tech_categories"])

        composite = round(
            v_score * WEIGHTS["velocity"] +
            q_score * WEIGHTS["quality"] +
            t_score * WEIGHTS["tech_category"],
            1
        )

        rows.append((
            ticker, today_str, composite, v_score, q_score, t_score,
            json.dumps({
                "velocity_score": v_score,
                "quality_score": q_score,
                "tech_category_score": t_score,
                "weights": WEIGHTS,
                "filing_velocity": d["velocity"],
                "patent_count_90d": d["count_90d"],
                "prior_count_90d": d["prior_90d"],
                "cpc_class_count": len(d["cpc_classes"]),
                "tech_categories": d["tech_categories"],
            })
        ))

    upsert_many("patent_intel_scores",
        ["symbol", "date", "patent_intel_score", "velocity_score",
         "quality_score", "tech_category_score", "details"], rows)

    print(f"  Scored {len(rows)} symbols")
    return rows


def run():
    init_db(); _ensure_tables()
    print("\n" + "=" * 60)
    print("  PATENT INTELLIGENCE (USPTO)")
    print("=" * 60)
    if not _should_run():
        print("  Skipping -- last run < 7 days ago")
        print("=" * 60)
        return
    print("  [1/2] USPTO patent filing velocity ...")
    patent_data = _fetch_patent_data()
    print("  [2/2] Computing composite scores ...")
    rows = _compute_scores(patent_data)
    if rows:
        avg = sum(r[2] for r in rows) / len(rows)
        top = sorted(rows, key=lambda r: r[2], reverse=True)[:5]
        bot = sorted(rows, key=lambda r: r[2])[:5]
        print(f"\n  Average score: {avg:.1f}")
        for label, items in [("Top 5", top), ("Bottom 5", bot)]:
            print(f"\n  {label}:")
            for r in items:
                print(f"    {r[0]:<8} {r[2]:>5.1f}  (Vel={r[3]:.0f} Qual={r[4]:.0f} Tech={r[5]:.0f})")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
