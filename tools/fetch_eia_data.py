"""Fetch EIA (Energy Information Administration) commodity data.

EIA provides the definitive weekly data on:
- US crude oil inventories (inventory builds/draws are major price catalysts)
- Natural gas storage (weekly storage report moves nat gas significantly)
- Gasoline inventories & demand
- Refinery utilization rates

These inventory changes are the fundamental catalysts for energy commodity trading.
A surprise inventory draw in crude = bullish for CL=F. A build = bearish.
"""

import requests
from datetime import datetime, timedelta
from tools.config import EIA_API_KEY
from tools.db import init_db, upsert_many


EIA_API_BASE = "https://api.eia.gov/v2"

# Key series: (series_id, description, commodity_ticker)
EIA_SERIES = [
    # Crude Oil
    ("PET.WCESTUS1.W", "US Crude Oil Stocks (Mbbl)", "CL=F"),
    ("PET.WCRFPUS2.W", "US Crude Production (Mb/d)", "CL=F"),
    ("PET.MCREXUS2.W", "US Crude Exports (Mb/d)", "CL=F"),
    ("PET.WCRRIUS2.W", "US Crude Imports (Mb/d)", "CL=F"),
    # Natural Gas
    ("NG.NW2_EPG0_SWO_R48_BCF.W", "US Nat Gas Storage (Bcf)", "NG=F"),
    ("NG.N9070US2.A", "US Nat Gas Production (MMcf/d)", "NG=F"),
    # Petroleum Products
    ("PET.WGTSTUS1.W", "US Gasoline Stocks (Mbbl)", "CL=F"),
    ("PET.WDISTUS1.W", "US Distillate Stocks (Mbbl)", "CL=F"),
    ("PET.WPULEUS3.W", "US Refinery Utilization (%)", "CL=F"),
]


def fetch_series(series_id, start_date=None):
    """Fetch a single EIA series."""
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")

    # EIA API v2 format
    url = f"{EIA_API_BASE}/seriesid/{series_id}"
    params = {
        "api_key": EIA_API_KEY,
        "start": start_date,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 104,  # 2 years of weekly data
    }

    try:
        resp = requests.get(url, params=params, timeout=15, verify=False)
        if resp.status_code != 200:
            return []
        data = resp.json()
        series_data = data.get("response", {}).get("data", [])
        return [(d["period"], float(d["value"])) for d in series_data if d.get("value") is not None]
    except Exception as e:
        print(f"    Warning: EIA fetch failed for {series_id}: {e}")
        return []


def compute_weekly_change(values):
    """Compute week-over-week change. values = [(date, value)] sorted desc."""
    if len(values) < 2:
        return None
    return values[0][1] - values[1][1]


def compute_yoy_change(values):
    """Compute year-over-year change vs 52 weeks ago."""
    if len(values) < 52:
        return None
    return values[0][1] - values[52][1]


def run():
    """Fetch and store EIA energy data."""
    init_db()

    if not EIA_API_KEY:
        print("  ERROR: EIA_API_KEY not set in .env")
        return

    print("Fetching EIA energy commodity data...")

    macro_rows = []  # Store in macro_indicators for use in commodity analysis
    commodity_signal_rows = []  # Derived signals for commodity scoring

    for series_id, description, commodity in EIA_SERIES:
        values = fetch_series(series_id)
        if not values:
            print(f"  No data for {description}")
            continue

        print(f"  {description}: {len(values)} weeks of data")

        # Store raw series
        for date_str, val in values:
            macro_rows.append((series_id, date_str, val))

        # Compute derived signals
        if len(values) >= 2:
            wow_change = compute_weekly_change(values)
            latest_val = values[0][1]
            latest_date = values[0][0]

            # For crude/gasoline/distillate: inventory BUILD = bearish, DRAW = bullish
            # For production: rising = bearish, falling = bullish (tighter supply)
            if "Stocks" in description or "Storage" in description:
                if wow_change is not None:
                    # Store draw/build as a signal
                    macro_rows.append((
                        f"{series_id}_WOW_CHANGE",
                        latest_date,
                        wow_change
                    ))
                    print(f"    WoW change: {wow_change:+,.0f} ({'DRAW' if wow_change < 0 else 'BUILD'})")

            if len(values) >= 52:
                yoy = compute_yoy_change(values)
                if yoy is not None:
                    macro_rows.append((f"{series_id}_YOY_CHANGE", latest_date, yoy))

    upsert_many("macro_indicators", ["indicator_id", "date", "value"], macro_rows)
    print(f"\n  Saved {len(macro_rows)} EIA data points.")

    # Print current energy snapshot
    print("\n  === ENERGY SNAPSHOT ===")
    for series_id, description, _ in EIA_SERIES[:5]:
        latest = [r for r in macro_rows if r[0] == series_id]
        if latest:
            latest.sort(key=lambda x: x[1], reverse=True)
            val = latest[0][2]
            date = latest[0][1]

            change_id = f"{series_id}_WOW_CHANGE"
            change_rows = [r for r in macro_rows if r[0] == change_id]
            change_str = ""
            if change_rows:
                chg = change_rows[0][2]
                change_str = f"  WoW: {chg:+,.1f}"

            print(f"  {description[:30]:30s}: {val:>10,.1f} ({date}){change_str}")


if __name__ == "__main__":
    run()
