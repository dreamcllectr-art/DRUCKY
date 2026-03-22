"""TA Pre-Screening Gate — filters assets before expensive Phase 2.5+ modules.

Tiered gate with overrides:
  - TA >= TA_GATE_FULL  → full analysis (forensics, variant, news displacement)
  - TA >= TA_GATE_SKIP  → partial (news displacement only)
  - TA <  TA_GATE_SKIP  → skipped (no expensive per-stock analysis)

Overrides (always get full analysis):
  - Watchlist symbols
  - Prior BUY/STRONG BUY signals
  - New IPOs with < N days of price data
"""

from tools.db import init_db, query_df
from tools.config import (
    TA_GATE_SKIP,
    TA_GATE_FULL,
    TA_GATE_OVERRIDE_WATCHLIST,
    TA_GATE_OVERRIDE_EXISTING_SIGNALS,
    TA_GATE_NEW_IPO_DAYS,
)


def get_gated_symbols():
    """Return tiered symbol lists based on technical scores and overrides.

    Returns dict with keys:
        full     — symbols that get all expensive modules
        partial  — symbols that get news displacement only
        skipped  — symbols below TA_GATE_SKIP (no expensive analysis)
        overrides — symbols that bypassed the gate via override
    """
    init_db()

    # Latest technical scores
    scores_df = query_df("""
        SELECT symbol, total_score
        FROM technical_scores
        WHERE date = (SELECT MAX(date) FROM technical_scores)
    """)

    if scores_df.empty:
        print("  TA Gate: no technical scores found — passing all symbols through")
        return {"full": [], "partial": [], "skipped": [], "overrides": []}

    # Build override set
    overrides = set()

    if TA_GATE_OVERRIDE_WATCHLIST:
        wl = query_df("SELECT symbol FROM watchlist")
        if not wl.empty:
            overrides.update(wl["symbol"].tolist())

    if TA_GATE_OVERRIDE_EXISTING_SIGNALS:
        sigs = query_df("""
            SELECT DISTINCT symbol FROM signals
            WHERE date = (SELECT MAX(date) FROM signals)
              AND signal IN ('BUY', 'STRONG BUY')
        """)
        if not sigs.empty:
            overrides.update(sigs["symbol"].tolist())

    # New IPOs: symbols with fewer than N days of price data
    new_ipos = query_df(f"""
        SELECT symbol, COUNT(*) as days
        FROM price_data
        WHERE asset_class != 'benchmark'
        GROUP BY symbol
        HAVING COUNT(*) < {TA_GATE_NEW_IPO_DAYS}
    """)
    if not new_ipos.empty:
        overrides.update(new_ipos["symbol"].tolist())

    # Classify symbols into tiers
    full = []
    partial = []
    skipped = []
    override_list = []

    for _, row in scores_df.iterrows():
        sym = row["symbol"]
        score = row["total_score"]

        if sym in overrides:
            full.append(sym)
            override_list.append(sym)
        elif score >= TA_GATE_FULL:
            full.append(sym)
        elif score >= TA_GATE_SKIP:
            partial.append(sym)
        else:
            skipped.append(sym)

    print(f"  TA Gate: {len(full)} full / {len(partial)} partial / "
          f"{len(skipped)} skipped / {len(override_list)} overrides "
          f"(thresholds: skip<{TA_GATE_SKIP}, full>={TA_GATE_FULL})")

    return {
        "full": full,
        "partial": partial,
        "skipped": skipped,
        "overrides": override_list,
    }


if __name__ == "__main__":
    result = get_gated_symbols()
    print(f"\nFull ({len(result['full'])}): {result['full'][:10]}{'...' if len(result['full']) > 10 else ''}")
    print(f"Partial ({len(result['partial'])}): {result['partial'][:10]}{'...' if len(result['partial']) > 10 else ''}")
    print(f"Skipped ({len(result['skipped'])}): {result['skipped'][:10]}{'...' if len(result['skipped']) > 10 else ''}")
    print(f"Overrides ({len(result['overrides'])}): {result['overrides'][:10]}{'...' if len(result['overrides']) > 10 else ''}")
