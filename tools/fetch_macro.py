"""Fetch macro indicators from FRED (via REST API, SSL-safe)."""

import time
import requests
from datetime import datetime, timedelta
from tools.config import FRED_API_KEY, FRED_SERIES, ECONOMIC_INDICATORS
from tools.db import init_db, upsert_many

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def _fetch_fred_series(series_id, start_date_str):
    """Fetch FRED series observations via REST API."""
    resp = requests.get(FRED_BASE, params={
        "series_id": series_id,
        "observation_start": start_date_str,
        "api_key": FRED_API_KEY,
        "file_type": "json",
    }, verify=False, timeout=20)
    resp.raise_for_status()
    return resp.json().get("observations", [])


def _fetch_all(series_dict, start_date, label):
    """Fetch all series in a dict, return rows list."""
    rows = []
    for name, series_id in series_dict.items():
        try:
            obs = _fetch_fred_series(series_id, start_date)
            count = 0
            for o in obs:
                val_str = o.get("value", ".")
                if val_str != ".":
                    rows.append((series_id, o["date"], float(val_str)))
                    count += 1
            print(f"  {name} ({series_id}): {count} observations")
            time.sleep(0.5)  # FRED rate limit safety (120 req/min)
        except Exception as e:
            print(f"  Warning: Failed to fetch {name} ({series_id}): {e}")
    return rows


def run():
    """Fetch all FRED macro series (core + economic indicators)."""
    init_db()

    if not FRED_API_KEY or FRED_API_KEY == "your_fred_api_key_here":
        print("ERROR: Set FRED_API_KEY in .env")
        return

    # 6 years of history for z-score calculations
    start_date = (datetime.now() - timedelta(days=365 * 6)).strftime("%Y-%m-%d")

    print("── Core Macro Series ──")
    rows = _fetch_all(FRED_SERIES, start_date, "core")

    print("\n── Economic Indicators ──")
    rows += _fetch_all(ECONOMIC_INDICATORS, start_date, "economic")

    upsert_many("macro_indicators", ["indicator_id", "date", "value"], rows)
    print(f"\nTotal: {len(rows)} macro data points saved.")


if __name__ == "__main__":
    run()
