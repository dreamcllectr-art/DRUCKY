"""Capital Flows Intelligence.

Sources: FMP institutional ownership + SEC 13F delta analysis.
Detects institutional accumulation, new smart money positions.
Table: capital_flow_scores
"""
import logging
from datetime import date
from tools.db import get_conn, query, upsert_many

logger = logging.getLogger(__name__)


def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
CREATE TABLE IF NOT EXISTS capital_flow_scores (
    symbol TEXT, date TEXT,
    inst_ownership_pct REAL, inst_change_qoq REAL,
    new_positions INTEGER, smart_manager_count INTEGER,
    etf_flow_score REAL, composite REAL,
    PRIMARY KEY (symbol, date)
);
    """)
    conn.commit()
    conn.close()


def _smart_managers():
    """Return set of tracked smart managers from config."""
    from tools.config import TRACKED_13F_MANAGERS
    return set(TRACKED_13F_MANAGERS.values())


def run():
    _ensure_tables()
    today = date.today().isoformat()

    # Load FMP institutional ownership (most recent)
    fmp_inst = {r["symbol"]: r for r in query(
        """SELECT symbol, institutional_pct FROM fmp_institutional
           WHERE date = (SELECT MAX(date) FROM fmp_institutional)"""
    )}

    # Load 13F filings: current quarter
    current_q = query(
        """SELECT symbol, manager, SUM(value) as total_value, COUNT(DISTINCT manager) as manager_count
           FROM filings_13f WHERE date = (SELECT MAX(date) FROM filings_13f)
           GROUP BY symbol"""
    )
    current_holdings = {r["symbol"]: r for r in current_q}

    # Load previous quarter 13F for change detection
    prev_q_rows = query(
        """SELECT symbol, manager, shares as prev_shares FROM filings_13f
           WHERE date = (SELECT MAX(date) FROM filings_13f
                        WHERE date < (SELECT MAX(date) FROM filings_13f))"""
    )
    prev_q = {}
    for r in prev_q_rows:
        if r["symbol"] not in prev_q:
            prev_q[r["symbol"]] = set()
        prev_q[r["symbol"]].add(r["manager"])

    # Load current 13F managers per symbol
    current_managers_rows = query(
        """SELECT symbol, manager, change_pct FROM filings_13f
           WHERE date = (SELECT MAX(date) FROM filings_13f)"""
    )
    current_managers = {}
    for r in current_managers_rows:
        current_managers.setdefault(r["symbol"], []).append(r)

    smart_mgrs = _smart_managers()
    all_symbols = set(fmp_inst.keys()) | set(current_holdings.keys())

    if not all_symbols:
        print("  Capital Flows: no data available")
        return

    rows = []
    for sym in all_symbols:
        inst = fmp_inst.get(sym, {})
        holdings = current_holdings.get(sym, {})
        mgr_list = current_managers.get(sym, [])
        prev_mgrs = prev_q.get(sym, set())

        inst_pct = inst.get("institutional_pct")
        manager_count = holdings.get("manager_count", 0) or 0

        # Count new positions (managers not in previous quarter)
        current_mgr_names = {r["manager"] for r in mgr_list}
        new_positions = len(current_mgr_names - prev_mgrs)

        # Count smart money managers
        smart_count = sum(1 for r in mgr_list if r["manager"] in smart_mgrs)

        # QoQ change from change_pct column
        avg_change = None
        if mgr_list:
            changes = [r["change_pct"] for r in mgr_list if r.get("change_pct") is not None]
            if changes:
                avg_change = sum(changes) / len(changes)

        # Score computation
        score = 50.0

        # Institutional ownership level
        if inst_pct is not None:
            if 40 <= inst_pct <= 80:
                score += 5  # Sweet spot
            elif inst_pct > 95:
                score -= 10  # Crowded
            elif inst_pct < 20:
                score += 5  # Underfollowed = discovery potential

        # QoQ change
        if avg_change is not None:
            if avg_change > 20:
                score += 20  # Strong accumulation
            elif avg_change > 5:
                score += 10
            elif avg_change < -20:
                score -= 20
            elif avg_change < -5:
                score -= 10

        # New positions from tracked smart managers
        if new_positions > 0:
            score += min(15, new_positions * 5)
        if smart_count > 2:
            score += 15
        elif smart_count > 0:
            score += 8

        rows.append((sym, today, inst_pct, avg_change, new_positions,
                     smart_count, None, round(max(0, min(100, score)), 1)))

    if rows:
        upsert_many("capital_flow_scores",
                    ["symbol", "date", "inst_ownership_pct", "inst_change_qoq",
                     "new_positions", "smart_manager_count",
                     "etf_flow_score", "composite"],
                    rows)

    accumulating = sum(1 for r in rows if r[7] > 65)
    print(f"  Capital Flows: {len(rows)} symbols | {accumulating} showing institutional accumulation")
