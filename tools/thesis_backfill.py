"""Thesis Snapshot Backfill — populate thesis_snapshots from historical data.

Reads all historical worldview_signals dates and generates thesis-level
snapshots for each date. This gives the thesis_monitor module historical
data to compare against, enabling thesis break detection from day one.

Usage: python -m tools.thesis_backfill
"""

import json
import logging
from datetime import date

from tools.db import init_db, get_conn, query, upsert_many
from tools.thesis_monitor import _build_thesis_snapshot, _ensure_tables

logger = logging.getLogger(__name__)


def run():
    """Backfill thesis snapshots for all historical worldview_signals dates."""
    init_db()
    _ensure_tables()

    print("\n" + "=" * 60)
    print("  THESIS SNAPSHOT BACKFILL")
    print("=" * 60)

    # Get all distinct dates in worldview_signals
    dates = query("""
        SELECT DISTINCT date FROM worldview_signals ORDER BY date
    """)
    if not dates:
        print("  No worldview_signals data to backfill from")
        print("=" * 60)
        return

    # Check which dates already have snapshots
    existing = query("SELECT DISTINCT date FROM thesis_snapshots")
    existing_dates = {r["date"] for r in existing}

    to_backfill = [d["date"] for d in dates if d["date"] not in existing_dates]
    print(f"  Total worldview dates: {len(dates)}")
    print(f"  Already snapshotted: {len(existing_dates)}")
    print(f"  To backfill: {len(to_backfill)}")

    if not to_backfill:
        print("  Nothing to backfill — all dates covered")
        print("=" * 60)
        return

    total_theses = 0
    for target_date in to_backfill:
        snapshot = _build_thesis_snapshot(target_date)
        if snapshot:
            snap_rows = []
            for thesis, data in snapshot.items():
                snap_rows.append((
                    target_date,
                    thesis,
                    "active",
                    data["avg_score"],
                    json.dumps({
                        "symbol_count": data["symbol_count"],
                        "top_symbols": data["top_symbols"],
                        "regime": data["regime"],
                    }),
                ))
            upsert_many(
                "thesis_snapshots",
                ["date", "thesis", "direction", "confidence", "affected_sectors"],
                snap_rows,
            )
            total_theses += len(snapshot)
            thesis_names = ", ".join(snapshot.keys())
            print(f"  {target_date}: {len(snapshot)} theses ({thesis_names})")
        else:
            print(f"  {target_date}: no active theses")

    print(f"\n  Backfilled {len(to_backfill)} dates, {total_theses} thesis snapshots")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
