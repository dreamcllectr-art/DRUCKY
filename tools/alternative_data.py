"""Alternative Data Ingestion — physical-world signals that lead price.

Data sources (all free):
  - NOAA Weather Alerts: extreme weather → energy, agriculture, insurance
  - NASA FIRMS: wildfire hotspots near critical infrastructure
  - Google Trends: consumer demand shifts before earnings
  - USDA Crop Reports: crop conditions vs 5-year avg → ag commodities
  - China Activity Proxy: steel/coal/copper composite via yfinance
  - Baltic Dry Index: global trade demand via yfinance

Why this exists: Financial data is lagging. Physical-world signals
(weather, fires, shipping, crops) lead price by days to weeks.
This is the earliest warning layer in the system.

Usage: python -m tools.alternative_data
"""

import sys
import json
import math
import time
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import (
    NASA_FIRMS_API_KEY, USDA_API_KEY,
    ENSO_MODERATE_THRESHOLD, ENSO_STRONG_THRESHOLD,
    ENSO_MODERATE_STRENGTH, ENSO_STRONG_STRENGTH,
    NDVI_ZSCORE_THRESHOLD, NDVI_STRESS_BASE_STRENGTH, NDVI_QUERY_DELAY,
)
from tools.db import init_db, get_conn, query


# ── Sector-to-ticker mapping ─────────────────────────────────────────

SECTOR_TICKERS = {
    "energy": ["OXY", "COP", "XOM", "CVX", "DVN", "FANG", "EOG", "PXD", "MPC", "VLO", "PSX"],
    "insurance": ["ALL", "TRV", "CB", "PGR", "MET", "AIG"],
    "agriculture": ["ADM", "BG", "DE", "MOS", "CF", "NTR", "CTVA", "FMC"],
    "shipping": ["ZIM", "SBLK", "GOGL", "DAC", "MATX"],
    "materials": ["BHP", "RIO", "FCX", "VALE", "NEM", "SCCO", "CLF", "X"],
    "industrials": ["CAT", "CMI", "GE", "HON", "ETN", "ROK"],
    "utilities_power": ["VST", "CEG", "NRG", "NEE", "SO", "DUK"],
    "retail": ["WMT", "AMZN", "COST", "TGT", "HD", "LOW"],
    "tech_consumer": ["AAPL", "GOOGL", "META", "MSFT", "NFLX", "CRM"],
    # Sub-sectors for satellite signals (opposite implications for crop stress)
    "fertilizer": ["CF", "MOS", "NTR", "CTVA", "FMC"],
    "grain_processors": ["ADM", "BG"],
    "farm_equipment": ["DE", "AGCO", "CNHI"],
}


# ── NOAA Weather Alerts ──────────────────────────────────────────────

def fetch_noaa_weather() -> list[dict]:
    """Fetch active NOAA weather alerts. No API key needed.

    Maps extreme weather to affected sectors:
    - Hurricane/tropical storm → energy (Gulf production), insurance
    - Drought → agriculture
    - Freeze/winter storm → energy (nat gas demand), agriculture
    - Wildfire → insurance, utilities
    """
    signals = []
    try:
        resp = requests.get(
            "https://api.weather.gov/alerts/active",
            headers={"User-Agent": "DruckenmillerAlpha/1.0"},
            params={"status": "actual", "severity": "Extreme,Severe"},
            timeout=15,
        )
        resp.raise_for_status()
        alerts = resp.json().get("features", [])

        # Categorize by event type
        event_counts = {}
        for alert in alerts:
            props = alert.get("properties", {})
            event = props.get("event", "").lower()
            severity = props.get("severity", "")
            area = props.get("areaDesc", "")

            if severity not in ("Extreme", "Severe"):
                continue

            key = event.split()[0] if event else "unknown"
            if key not in event_counts:
                event_counts[key] = {"count": 0, "areas": set(), "severity": severity}
            event_counts[key]["count"] += 1
            # Take first 3 area names
            if len(event_counts[key]["areas"]) < 3:
                event_counts[key]["areas"].add(area[:50])

        # Map events to investment signals
        EVENT_MAPPING = {
            "hurricane": {"sectors": ["energy", "insurance"], "direction": "mixed", "base_strength": 80},
            "tropical": {"sectors": ["energy", "insurance"], "direction": "mixed", "base_strength": 70},
            "tornado": {"sectors": ["insurance"], "direction": "bearish", "base_strength": 60},
            "drought": {"sectors": ["agriculture"], "direction": "bullish", "base_strength": 65},
            "freeze": {"sectors": ["energy", "agriculture"], "direction": "bullish", "base_strength": 60},
            "winter": {"sectors": ["energy"], "direction": "bullish", "base_strength": 55},
            "flood": {"sectors": ["agriculture", "insurance"], "direction": "mixed", "base_strength": 60},
            "fire": {"sectors": ["insurance", "utilities_power"], "direction": "bearish", "base_strength": 65},
            "heat": {"sectors": ["energy", "utilities_power"], "direction": "bullish", "base_strength": 55},
        }

        for event_key, data in event_counts.items():
            mapping = None
            for pattern, m in EVENT_MAPPING.items():
                if pattern in event_key:
                    mapping = m
                    break
            if not mapping:
                continue

            # Scale strength by count
            count_multiplier = min(1.5, 1.0 + data["count"] / 20)
            strength = min(100, mapping["base_strength"] * count_multiplier)

            affected_tickers = []
            for sector in mapping["sectors"]:
                affected_tickers.extend(SECTOR_TICKERS.get(sector, []))

            areas_str = ", ".join(list(data["areas"])[:3])
            signals.append({
                "source": "noaa_weather",
                "indicator": f"weather_{event_key}",
                "value": data["count"],
                "signal_direction": mapping["direction"],
                "signal_strength": strength,
                "affected_sectors": json.dumps(mapping["sectors"]),
                "affected_tickers": json.dumps(affected_tickers),
                "narrative": f"{data['count']} active {event_key} alerts ({areas_str}). "
                             f"Impacts {', '.join(mapping['sectors'])}.",
            })

        print(f"    NOAA: {len(alerts)} alerts → {len(signals)} investment signals")

    except Exception as e:
        print(f"    NOAA: Failed — {e}")

    return signals


# ── NASA FIRMS (Fire Hotspots) ───────────────────────────────────────

# Critical infrastructure zones (lat, lon, radius_km, name, sectors)
INFRA_ZONES = [
    (29.75, -95.35, 150, "Gulf Coast Refining", ["energy"]),
    (30.00, -90.00, 100, "Louisiana Petrochemical", ["energy"]),
    (36.00, -119.00, 200, "California Central Valley", ["agriculture"]),
    (34.00, -118.50, 100, "Southern California", ["insurance", "utilities_power"]),
    (37.50, -122.00, 80, "San Francisco Bay", ["insurance", "tech_consumer"]),
    (41.00, -90.00, 200, "Midwest Corn Belt", ["agriculture"]),
    (32.00, -100.00, 200, "Texas Permian Basin", ["energy"]),
]


def fetch_nasa_firms() -> list[dict]:
    """Fetch active fire hotspots near critical infrastructure."""
    signals = []
    if not NASA_FIRMS_API_KEY:
        print("    NASA FIRMS: Skipped (no API key — get free key at firms.modaps.eosdis.nasa.gov)")
        return signals

    try:
        # FIRMS API: last 48 hours, US region
        resp = requests.get(
            f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{NASA_FIRMS_API_KEY}/VIIRS_SNPP_NRT/world/2",
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"    NASA FIRMS: API returned {resp.status_code}")
            return signals

        lines = resp.text.strip().split("\n")
        if len(lines) < 2:
            return signals

        # Parse CSV — find fires near infrastructure zones
        for zone_lat, zone_lon, radius_km, zone_name, zone_sectors in INFRA_ZONES:
            fire_count = 0
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                try:
                    lat, lon = float(parts[0]), float(parts[1])
                except ValueError:
                    continue

                # Rough distance calc (good enough for this purpose)
                dlat = abs(lat - zone_lat) * 111
                dlon = abs(lon - zone_lon) * 111 * math.cos(math.radians(zone_lat))
                dist = math.sqrt(dlat**2 + dlon**2)

                if dist <= radius_km:
                    fire_count += 1

            if fire_count >= 5:  # Only flag significant clusters
                strength = min(100, 40 + fire_count * 2)
                affected_tickers = []
                for sector in zone_sectors:
                    affected_tickers.extend(SECTOR_TICKERS.get(sector, []))

                signals.append({
                    "source": "nasa_firms",
                    "indicator": f"fires_{zone_name.lower().replace(' ', '_')}",
                    "value": fire_count,
                    "signal_direction": "bearish" if "insurance" in zone_sectors else "bullish",
                    "signal_strength": strength,
                    "affected_sectors": json.dumps(zone_sectors),
                    "affected_tickers": json.dumps(affected_tickers),
                    "narrative": f"{fire_count} fire hotspots detected near {zone_name} (48h). "
                                 f"Potential impact on {', '.join(zone_sectors)}.",
                })

        print(f"    NASA FIRMS: {len(lines)-1} hotspots → {len(signals)} infrastructure alerts")

    except Exception as e:
        print(f"    NASA FIRMS: Failed — {e}")

    return signals


# ── Google Trends ────────────────────────────────────────────────────

def fetch_google_trends() -> list[dict]:
    """Fetch Google Trends data for key consumer/economic terms.

    Spikes in search interest are leading indicators for:
    - "layoffs" → bearish labor market → Fed policy
    - "recession" → consumer fear → risk-off
    - Product searches → retail earnings
    """
    signals = []
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("    Google Trends: Skipped (pip install pytrends)")
        return signals

    TREND_QUERIES = [
        {
            "keywords": ["layoffs", "unemployment"],
            "sectors": ["industrials"],
            "direction_if_rising": "bearish",
            "indicator": "labor_distress",
        },
        {
            "keywords": ["recession"],
            "sectors": ["retail", "industrials"],
            "direction_if_rising": "bearish",
            "indicator": "recession_fear",
        },
        {
            "keywords": ["buy iPhone", "buy laptop"],
            "sectors": ["tech_consumer"],
            "direction_if_rising": "bullish",
            "indicator": "consumer_tech_demand",
        },
        {
            "keywords": ["buy house", "mortgage rates"],
            "sectors": [],
            "direction_if_rising": "mixed",
            "indicator": "housing_demand",
        },
    ]

    try:
        pytrends = TrendReq(hl="en-US", tz=300, timeout=(10, 25))

        for tq in TREND_QUERIES:
            try:
                pytrends.build_payload(tq["keywords"], timeframe="now 7-d", geo="US")
                interest = pytrends.interest_over_time()

                if interest.empty:
                    continue

                # Compare last 2 days vs previous 5 days
                recent = interest.iloc[-2:].mean()
                earlier = interest.iloc[:-2].mean()

                for kw in tq["keywords"]:
                    if kw not in recent or kw not in earlier:
                        continue

                    recent_val = recent[kw]
                    earlier_val = earlier[kw]

                    if earlier_val <= 0:
                        continue

                    change_pct = (recent_val - earlier_val) / earlier_val * 100
                    zscore = change_pct / 20  # rough normalization

                    # Only flag significant moves (>20% change)
                    if abs(change_pct) < 20:
                        continue

                    is_rising = change_pct > 0
                    direction = tq["direction_if_rising"] if is_rising else (
                        "bullish" if tq["direction_if_rising"] == "bearish" else "bearish"
                    )

                    strength = min(100, 30 + abs(change_pct) * 0.5)
                    affected_tickers = []
                    for sector in tq["sectors"]:
                        affected_tickers.extend(SECTOR_TICKERS.get(sector, []))

                    signals.append({
                        "source": "google_trends",
                        "indicator": f"trends_{tq['indicator']}_{kw.replace(' ', '_')}",
                        "value": recent_val,
                        "value_zscore": zscore,
                        "signal_direction": direction,
                        "signal_strength": strength,
                        "affected_sectors": json.dumps(tq["sectors"]),
                        "affected_tickers": json.dumps(affected_tickers),
                        "narrative": f"Google Trends '{kw}': {change_pct:+.0f}% vs prior week. "
                                     f"{'Rising' if is_rising else 'Falling'} search interest.",
                    })

                time.sleep(2)  # pytrends rate limiting

            except Exception as e:
                print(f"    Google Trends: '{tq['keywords']}' failed — {e}")
                time.sleep(3)

        print(f"    Google Trends: {len(signals)} signals")

    except Exception as e:
        print(f"    Google Trends: Failed — {e}")

    return signals


# ── USDA Crop Data ───────────────────────────────────────────────────

def fetch_usda_data() -> list[dict]:
    """Fetch USDA crop condition data. Compare current conditions to 5-year average.

    Poor conditions → bullish for ag commodity prices.
    """
    signals = []
    if not USDA_API_KEY:
        print("    USDA: Skipped (no API key — get free key at quickstats.nass.usda.gov)")
        return signals

    # Key crops to monitor
    CROPS = [
        {"commodity": "CORN", "ticker_impact": ["ADM", "BG", "DE", "CF"]},
        {"commodity": "SOYBEANS", "ticker_impact": ["ADM", "BG", "MOS", "DE"]},
        {"commodity": "WHEAT", "ticker_impact": ["ADM", "BG"]},
    ]

    current_year = datetime.now().year

    for crop_info in CROPS:
        try:
            params = {
                "key": USDA_API_KEY,
                "commodity_desc": crop_info["commodity"],
                "statisticcat_desc": "CONDITION",
                "unit_desc": "PCT GOOD",
                "year": current_year,
                "freq_desc": "WEEKLY",
                "format": "JSON",
            }
            resp = requests.get(
                "https://quickstats.nass.usda.gov/api/api_GET/",
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                continue

            data = resp.json().get("data", [])
            if not data:
                continue

            # Get latest condition and compare to history
            latest = max(data, key=lambda x: x.get("week_ending", ""))
            good_pct = float(latest.get("Value", 0))

            # Historical comparison (rough 5-year avg for these crops)
            HISTORICAL_AVG = {"CORN": 60, "SOYBEANS": 58, "WHEAT": 48}
            avg = HISTORICAL_AVG.get(crop_info["commodity"], 55)

            deviation = good_pct - avg  # negative = worse conditions = bullish for prices

            if abs(deviation) < 5:
                continue

            direction = "bullish" if deviation < 0 else "bearish"
            strength = min(100, 30 + abs(deviation) * 2)

            signals.append({
                "source": "usda_crop",
                "indicator": f"crop_condition_{crop_info['commodity'].lower()}",
                "value": good_pct,
                "value_zscore": deviation / 10,
                "signal_direction": direction,
                "signal_strength": strength,
                "affected_sectors": json.dumps(["agriculture"]),
                "affected_tickers": json.dumps(crop_info["ticker_impact"]),
                "narrative": f"{crop_info['commodity']} condition: {good_pct:.0f}% good "
                             f"(5yr avg: {avg}%, deviation: {deviation:+.0f}pp). "
                             f"{'Below-average conditions bullish for prices.' if deviation < 0 else 'Above-average conditions bearish.'}",
            })

        except Exception as e:
            print(f"    USDA {crop_info['commodity']}: Failed — {e}")

    print(f"    USDA: {len(signals)} crop condition signals")
    return signals


# ── China Activity Proxy (via yfinance) ──────────────────────────────

def fetch_china_activity_proxy() -> list[dict]:
    """Compute China economic activity proxy from commodity prices.

    Composite of steel rebar, coking coal, copper — all sensitive to Chinese demand.
    Rising = China activity accelerating = bullish for materials/commodities.
    """
    signals = []
    try:
        import yfinance as yf

        # Proxies for China activity (available on yfinance)
        tickers = {
            "HG=F": "Copper",        # Copper futures
            "GC=F": "Gold",           # Gold (safe haven inverse)
        }

        data = yf.download(list(tickers.keys()), period="3mo", interval="1d", progress=False)

        if data.empty:
            print("    China proxy: No data")
            return signals

        closes = data["Close"]

        # Compute 7d vs 30d momentum for each
        momentums = {}
        for ticker, name in tickers.items():
            if ticker not in closes.columns:
                continue
            series = closes[ticker].dropna()
            if len(series) < 30:
                continue

            recent_7d = series.iloc[-7:].mean()
            prior_30d = series.iloc[-30:-7].mean()

            if prior_30d > 0:
                momentum = (recent_7d - prior_30d) / prior_30d * 100
                momentums[name] = momentum

        if not momentums:
            return signals

        # Copper rising = China demand up
        copper_momentum = momentums.get("Copper", 0)
        # Gold rising = risk-off (invert for activity signal)
        gold_momentum = momentums.get("Gold", 0)

        # Composite: copper up + gold down = strong China activity signal
        activity_score = copper_momentum - gold_momentum * 0.5

        if abs(activity_score) < 2:
            return signals

        direction = "bullish" if activity_score > 0 else "bearish"
        strength = min(100, 30 + abs(activity_score) * 5)

        affected = SECTOR_TICKERS["materials"] + SECTOR_TICKERS["industrials"]

        signals.append({
            "source": "china_activity",
            "indicator": "china_activity_composite",
            "value": round(activity_score, 2),
            "value_zscore": activity_score / 5,
            "signal_direction": direction,
            "signal_strength": strength,
            "affected_sectors": json.dumps(["materials", "industrials"]),
            "affected_tickers": json.dumps(affected),
            "narrative": f"China activity proxy: {activity_score:+.1f} "
                         f"(Copper 7d/30d: {copper_momentum:+.1f}%, Gold: {gold_momentum:+.1f}%). "
                         f"{'Accelerating' if activity_score > 0 else 'Decelerating'} demand signal.",
        })

        print(f"    China proxy: activity={activity_score:+.1f} ({direction})")

    except Exception as e:
        print(f"    China proxy: Failed — {e}")

    return signals


# ── Baltic Dry Index ─────────────────────────────────────────────────

def fetch_baltic_dry() -> list[dict]:
    """Fetch Baltic Dry Index as global trade demand proxy.

    BDI rising = global trade improving = bullish for shipping, industrials, EM.
    """
    signals = []
    try:
        import yfinance as yf

        # Try to get BDI or shipping proxy
        # yfinance doesn't have BDI directly, use SBLK (Star Bulk Carriers) as proxy
        data = yf.download("SBLK", period="3mo", interval="1d", progress=False)

        if data.empty or len(data) < 30:
            print("    Baltic Dry: Insufficient data")
            return signals

        closes = data["Close"]
        if hasattr(closes, 'columns'):
            closes = closes.iloc[:, 0]

        recent_7d = closes.iloc[-7:].mean()
        ma_30d = closes.iloc[-30:].mean()
        ma_90d = closes.mean()

        momentum_30d = (recent_7d - ma_30d) / ma_30d * 100 if ma_30d > 0 else 0
        momentum_90d = (recent_7d - ma_90d) / ma_90d * 100 if ma_90d > 0 else 0

        if abs(momentum_30d) < 3:
            return signals

        direction = "bullish" if momentum_30d > 0 else "bearish"
        strength = min(100, 30 + abs(momentum_30d) * 2)

        affected = SECTOR_TICKERS["shipping"] + SECTOR_TICKERS["industrials"][:3]

        signals.append({
            "source": "baltic_dry",
            "indicator": "shipping_demand_proxy",
            "value": round(float(recent_7d), 2),
            "value_zscore": momentum_30d / 10,
            "signal_direction": direction,
            "signal_strength": strength,
            "affected_sectors": json.dumps(["shipping", "industrials"]),
            "affected_tickers": json.dumps(affected),
            "narrative": f"Shipping demand proxy (SBLK): {momentum_30d:+.1f}% vs 30d avg, "
                         f"{momentum_90d:+.1f}% vs 90d avg. "
                         f"Global trade {'improving' if direction == 'bullish' else 'weakening'}.",
        })

        print(f"    Baltic Dry proxy: {momentum_30d:+.1f}% 30d momentum ({direction})")

    except Exception as e:
        print(f"    Baltic Dry: Failed — {e}")

    return signals


# ── NOAA ENSO / ONI Index (Satellite-Derived SST) ────────────────────

def fetch_enso_index() -> list[dict]:
    """Fetch ENSO Oceanic Niño Index from NOAA Climate Prediction Center.

    El Niño/La Niña is the single strongest climate→market signal.
    IMF research (Cashin et al. 2017) shows ENSO explains 3-6% of commodity
    price variance with multi-quarter lead times.

    - El Niño (ONI ≥ +0.5): bullish energy (higher nat gas demand from
      weather disruption), bearish agriculture (crop stress in Australia,
      SE Asia, reduced Indian monsoon).
    - La Niña (ONI ≤ -0.5): bullish agriculture/fertilizer (higher crop
      prices from US drought risk), mixed insurance (fewer Atlantic hurricanes).

    No API key needed. Data from satellite-derived sea surface temperatures.
    """
    signals = []
    try:
        # NOAA CPC Oceanic Niño Index — updated monthly, based on
        # satellite + buoy SST observations in the Niño 3.4 region
        resp = requests.get(
            "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt",
            timeout=15,
        )
        resp.raise_for_status()

        # Parse whitespace-delimited text:
        # SEAS  YEAR   TOTAL   ANOM
        # DJF   1950   24.72  -1.53
        lines = resp.text.strip().split("\n")
        if len(lines) < 3:
            print("    ENSO: Insufficient data")
            return signals

        # Extract last 4 quarters for trend analysis
        records = []
        for line in lines[1:]:  # skip header
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                records.append({
                    "season": parts[0],
                    "year": int(parts[1]),
                    "anom": float(parts[3]),
                })
            except (ValueError, IndexError):
                continue

        if len(records) < 4:
            print("    ENSO: Not enough historical records")
            return signals

        latest = records[-1]
        oni = latest["anom"]
        prev_3 = [r["anom"] for r in records[-4:-1]]
        prev_avg = sum(prev_3) / len(prev_3)

        # Trend: is ONI strengthening or weakening?
        trend = oni - prev_avg  # positive = warming, negative = cooling
        is_strengthening = abs(oni) > abs(prev_avg)

        # Only fire signal if in El Niño or La Niña phase
        if abs(oni) < ENSO_MODERATE_THRESHOLD:
            print(f"    ENSO: ONI {oni:+.2f} (neutral, no signal)")
            return signals

        # Determine phase and strength
        is_el_nino = oni > 0
        phase = "el_nino" if is_el_nino else "la_nina"

        if abs(oni) >= ENSO_STRONG_THRESHOLD:
            strength = ENSO_STRONG_STRENGTH
            intensity = "Strong"
        else:
            strength = ENSO_MODERATE_STRENGTH
            intensity = "Moderate"

        # Boost strength if phase is strengthening
        if is_strengthening:
            strength = min(100, strength + 10)

        # El Niño signals
        if is_el_nino:
            # Bullish energy — weather disruption increases nat gas demand
            energy_tickers = SECTOR_TICKERS["energy"]
            signals.append({
                "source": "noaa_enso",
                "indicator": f"enso_{phase}_energy",
                "value": oni,
                "value_zscore": oni / 0.5,  # ONI units are already anomaly
                "signal_direction": "bullish",
                "signal_strength": strength,
                "affected_sectors": json.dumps(["energy"]),
                "affected_tickers": json.dumps(energy_tickers),
                "narrative": (
                    f"ENSO ONI at {oni:+.1f} ({intensity} El Niño, "
                    f"{'strengthening' if is_strengthening else 'weakening'} "
                    f"trend {trend:+.2f} over 3 quarters). "
                    f"Historically bullish for nat gas and energy equities. "
                    f"Weather disruption increases demand volatility."
                ),
            })

            # Bearish agriculture — crop stress in key growing regions
            ag_tickers = SECTOR_TICKERS["agriculture"]
            signals.append({
                "source": "noaa_enso",
                "indicator": f"enso_{phase}_agriculture",
                "value": oni,
                "value_zscore": oni / 0.5,
                "signal_direction": "bearish",
                "signal_strength": strength,
                "affected_sectors": json.dumps(["agriculture"]),
                "affected_tickers": json.dumps(ag_tickers),
                "narrative": (
                    f"ENSO ONI at {oni:+.1f} ({intensity} El Niño). "
                    f"Crop stress likely in Australia/SE Asia. "
                    f"Reduced Indian monsoon impacts global grain supply."
                ),
            })

        # La Niña signals
        else:
            # Bullish fertilizer — drought risk raises crop prices, more input demand
            fert_tickers = SECTOR_TICKERS["fertilizer"]
            signals.append({
                "source": "noaa_enso",
                "indicator": f"enso_{phase}_fertilizer",
                "value": oni,
                "value_zscore": oni / -0.5,
                "signal_direction": "bullish",
                "signal_strength": strength,
                "affected_sectors": json.dumps(["fertilizer"]),
                "affected_tickers": json.dumps(fert_tickers),
                "narrative": (
                    f"ENSO ONI at {oni:+.1f} ({intensity} La Niña, "
                    f"{'strengthening' if is_strengthening else 'weakening'} "
                    f"trend {trend:+.2f} over 3 quarters). "
                    f"US drought risk raises crop prices → higher fertilizer demand."
                ),
            })

            # Mixed insurance — La Niña = fewer Atlantic hurricanes but more Pacific storms
            ins_tickers = SECTOR_TICKERS["insurance"]
            signals.append({
                "source": "noaa_enso",
                "indicator": f"enso_{phase}_insurance",
                "value": oni,
                "value_zscore": oni / -0.5,
                "signal_direction": "mixed",
                "signal_strength": max(40, strength - 15),  # weaker signal for insurance
                "affected_sectors": json.dumps(["insurance"]),
                "affected_tickers": json.dumps(ins_tickers),
                "narrative": (
                    f"ENSO ONI at {oni:+.1f} ({intensity} La Niña). "
                    f"Historically fewer Atlantic hurricanes but increased "
                    f"US drought/wildfire risk. Mixed insurance impact."
                ),
            })

        phase_label = "El Niño" if is_el_nino else "La Niña"
        print(f"    ENSO: ONI {oni:+.2f} ({intensity} {phase_label}, "
              f"trend {trend:+.2f}) → {len(signals)} signals")

    except Exception as e:
        print(f"    ENSO: Failed — {e}")

    return signals


# ── NASA MODIS NDVI (Satellite Crop Health) ──────────────────────────

# Key US agricultural regions for NDVI monitoring
# (lat, lon, name, primary_crop, affected_sectors)
AG_REGIONS = [
    (41.0, -89.5, "Corn Belt", "corn",
     {"stress_bullish": ["fertilizer"], "stress_bearish": ["farm_equipment"]}),
    (38.0, -99.0, "Great Plains", "wheat",
     {"stress_bullish": ["fertilizer"], "stress_bearish": ["farm_equipment"]}),
    (36.0, -119.0, "Central Valley", "mixed",
     {"stress_bullish": ["fertilizer"], "stress_bearish": ["agriculture"]}),
    (33.0, -90.5, "Delta", "soybeans",
     {"stress_bullish": ["fertilizer", "grain_processors"], "stress_bearish": ["farm_equipment"]}),
    (47.0, -118.0, "PNW", "wheat",
     {"stress_bullish": ["fertilizer"], "stress_bearish": ["farm_equipment"]}),
]


def fetch_ndvi_crop_health() -> list[dict]:
    """Fetch NASA MODIS NDVI for key US agricultural regions.

    NDVI (Normalized Difference Vegetation Index) measures crop health
    from space. Academic research (Funk 2015, Brown 2013) demonstrates
    NDVI anomalies predict crop yield deviations 4-8 weeks before USDA
    reports — this is EARLIER and more OBJECTIVE than the self-reported
    USDA data already in the system.

    Uses the ORNL MODIS Web Service (free, no auth required).
    MOD13Q1 product: 250m resolution, 16-day composites updated every 8 days.
    """
    signals = []

    try:
        today = date.today()
        year = today.year

        # MODIS day-of-year format: A{year}{doy} (e.g., A2026065)
        doy = today.timetuple().tm_yday
        # Request last 64 days of data (4 composites for current + historical comparison)
        start_doy = max(1, doy - 64)

        for lat, lon, region_name, crop, sector_map in AG_REGIONS:
            try:
                # ORNL MODIS Web Service — free, no auth
                resp = requests.get(
                    "https://modis.ornl.gov/rst/api/v1/MOD13Q1/subset",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "band": "250m_16_days_NDVI",
                        "startDate": f"A{year}{start_doy:03d}",
                        "endDate": f"A{year}{doy:03d}",
                        "kmAboveBelow": 0,
                        "kmLeftRight": 0,
                    },
                    timeout=30,
                )

                if resp.status_code != 200:
                    print(f"    NDVI {region_name}: API returned {resp.status_code}")
                    time.sleep(NDVI_QUERY_DELAY)
                    continue

                data = resp.json()
                subsets = data.get("subset", [])

                if not subsets:
                    print(f"    NDVI {region_name}: No data returned")
                    time.sleep(NDVI_QUERY_DELAY)
                    continue

                # Extract NDVI values (scale factor: 0.0001)
                ndvi_values = []
                for subset in subsets:
                    raw = subset.get("data", [])
                    if raw:
                        # NDVI valid range: -2000 to 10000 (after scale = -0.2 to 1.0)
                        val = raw[0]  # single pixel (kmAboveBelow=0)
                        if -2000 <= val <= 10000:
                            ndvi_values.append(val * 0.0001)

                if len(ndvi_values) < 2:
                    print(f"    NDVI {region_name}: Insufficient data points ({len(ndvi_values)})")
                    time.sleep(NDVI_QUERY_DELAY)
                    continue

                # Current = latest composite, historical mean = all prior
                current_ndvi = ndvi_values[-1]
                historical_ndvi = ndvi_values[:-1]
                hist_mean = sum(historical_ndvi) / len(historical_ndvi)

                if len(historical_ndvi) >= 2:
                    hist_std = (sum((v - hist_mean) ** 2 for v in historical_ndvi)
                                / len(historical_ndvi)) ** 0.5
                else:
                    hist_std = 0.05  # fallback: ~5% of typical NDVI range

                # Avoid division by zero
                if hist_std < 0.01:
                    hist_std = 0.01

                zscore = (current_ndvi - hist_mean) / hist_std

                # Only fire signal for significant deviations
                if abs(zscore) < NDVI_ZSCORE_THRESHOLD:
                    time.sleep(NDVI_QUERY_DELAY)
                    continue

                is_stress = zscore < 0
                strength = min(100, NDVI_STRESS_BASE_STRENGTH + abs(zscore) * 10)

                if is_stress:
                    # Crop stress — bullish for fertilizer/commodity prices
                    bullish_sectors = sector_map["stress_bullish"]
                    affected_tickers = []
                    for sector in bullish_sectors:
                        affected_tickers.extend(SECTOR_TICKERS.get(sector, []))

                    signals.append({
                        "source": "nasa_ndvi",
                        "indicator": f"ndvi_stress_{region_name.lower().replace(' ', '_')}",
                        "value": round(current_ndvi, 4),
                        "value_zscore": round(zscore, 2),
                        "signal_direction": "bullish",
                        "signal_strength": strength,
                        "affected_sectors": json.dumps(bullish_sectors),
                        "affected_tickers": json.dumps(affected_tickers),
                        "narrative": (
                            f"{region_name} NDVI z-score {zscore:.1f} "
                            f"(current: {current_ndvi:.3f}, mean: {hist_mean:.3f}). "
                            f"Vegetation health significantly below average — "
                            f"early {crop} stress signal. "
                            f"Bullish for grain futures and fertilizer demand."
                        ),
                    })

                    # Bearish for farm equipment (drought = less planting)
                    bearish_sectors = sector_map["stress_bearish"]
                    bearish_tickers = []
                    for sector in bearish_sectors:
                        bearish_tickers.extend(SECTOR_TICKERS.get(sector, []))

                    if bearish_tickers:
                        signals.append({
                            "source": "nasa_ndvi",
                            "indicator": f"ndvi_stress_{region_name.lower().replace(' ', '_')}_bearish",
                            "value": round(current_ndvi, 4),
                            "value_zscore": round(zscore, 2),
                            "signal_direction": "bearish",
                            "signal_strength": max(40, strength - 15),
                            "affected_sectors": json.dumps(bearish_sectors),
                            "affected_tickers": json.dumps(bearish_tickers),
                            "narrative": (
                                f"{region_name} NDVI z-score {zscore:.1f}. "
                                f"Crop stress may reduce {crop} acreage and "
                                f"equipment demand."
                            ),
                        })

                else:
                    # Bumper crop — bearish for commodity prices, mixed for processors
                    affected_tickers = SECTOR_TICKERS.get("fertilizer", [])
                    signals.append({
                        "source": "nasa_ndvi",
                        "indicator": f"ndvi_surplus_{region_name.lower().replace(' ', '_')}",
                        "value": round(current_ndvi, 4),
                        "value_zscore": round(zscore, 2),
                        "signal_direction": "bearish",
                        "signal_strength": max(40, strength - 10),
                        "affected_sectors": json.dumps(["fertilizer"]),
                        "affected_tickers": json.dumps(affected_tickers),
                        "narrative": (
                            f"{region_name} NDVI z-score +{zscore:.1f} "
                            f"(current: {current_ndvi:.3f}, mean: {hist_mean:.3f}). "
                            f"Exceptional vegetation health — bumper {crop} crop likely. "
                            f"Bearish for grain futures and fertilizer demand."
                        ),
                    })

                time.sleep(NDVI_QUERY_DELAY)

            except Exception as e:
                print(f"    NDVI {region_name}: Failed — {e}")
                time.sleep(NDVI_QUERY_DELAY)

        print(f"    NASA NDVI: {len(AG_REGIONS)} regions scanned → {len(signals)} crop health signals")

    except Exception as e:
        print(f"    NASA NDVI: Failed — {e}")

    return signals


# ── Score Computation ────────────────────────────────────────────────

def _compute_symbol_scores(today: str):
    """Compute alt_data_score per symbol from recent alternative_data signals."""

    # Get all signals from last 7 days
    signals = query("""
        SELECT source, indicator, signal_direction, signal_strength,
               affected_sectors, affected_tickers, date
        FROM alternative_data
        WHERE date >= date('now', '-7 days')
    """)

    if not signals:
        return

    # Get all symbols and their sectors
    universe = query("SELECT symbol, sector FROM stock_universe")
    symbol_sectors = {r["symbol"]: r["sector"] for r in universe}

    # Build per-symbol score
    symbol_scores = {}

    for sig in signals:
        try:
            tickers = json.loads(sig["affected_tickers"] or "[]")
            sectors = json.loads(sig["affected_sectors"] or "[]")
        except (json.JSONDecodeError, TypeError):
            continue

        strength = sig["signal_strength"] or 0

        # Recency decay: today=1.0, 3d=0.7, 7d=0.3
        days_ago = (date.today() - date.fromisoformat(sig["date"])).days
        decay = max(0.3, 1.0 - days_ago * 0.1)

        weighted_strength = strength * decay

        # Direct ticker matches
        for ticker in tickers:
            if ticker not in symbol_scores:
                symbol_scores[ticker] = {"total": 0, "signals": []}
            symbol_scores[ticker]["total"] += weighted_strength
            symbol_scores[ticker]["signals"].append(f"{sig['source']}:{sig['indicator']}")

        # Sector matches (lower weight)
        for sym, sector in symbol_sectors.items():
            if sector and any(s in sector.lower() for s in sectors):
                if sym not in symbol_scores:
                    symbol_scores[sym] = {"total": 0, "signals": []}
                symbol_scores[sym]["total"] += weighted_strength * 0.3

    # Normalize to 0-100 and store
    if not symbol_scores:
        return

    max_score = max(s["total"] for s in symbol_scores.values()) or 1
    rows = []
    for symbol, data in symbol_scores.items():
        normalized = min(100, data["total"] / max_score * 100)
        if normalized < 10:
            continue
        contributing = json.dumps(list(set(data["signals"]))[:5])
        rows.append((symbol, today, normalized, contributing))

    if rows:
        with get_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO alt_data_scores
                   (symbol, date, alt_data_score, contributing_signals)
                   VALUES (?, ?, ?, ?)""",
                rows,
            )

    print(f"  Scored {len(rows)} symbols with alt data signals")


# ── Main Entry ───────────────────────────────────────────────────────

def run():
    """Run all alternative data fetchers and compute per-symbol scores."""
    init_db()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  ALTERNATIVE DATA INGESTION")
    print("=" * 60)

    all_signals = []

    # Run each data source (each handles its own errors gracefully)
    print("  Fetching alternative data sources...")
    all_signals.extend(fetch_noaa_weather())
    all_signals.extend(fetch_nasa_firms())
    all_signals.extend(fetch_google_trends())
    all_signals.extend(fetch_usda_data())
    all_signals.extend(fetch_china_activity_proxy())
    all_signals.extend(fetch_baltic_dry())

    # Satellite-derived data sources
    print("  Fetching satellite data sources...")
    all_signals.extend(fetch_enso_index())
    all_signals.extend(fetch_ndvi_crop_health())

    # Store raw signals
    if all_signals:
        rows = []
        for sig in all_signals:
            rows.append((
                today,
                sig["source"],
                sig["indicator"],
                sig.get("value"),
                sig.get("value_zscore"),
                sig.get("affected_sectors", "[]"),
                sig.get("affected_tickers", "[]"),
                sig.get("signal_direction", "neutral"),
                sig.get("signal_strength", 0),
                sig.get("narrative", ""),
                json.dumps(sig),  # raw_data
            ))

        with get_conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO alternative_data
                   (date, source, indicator, value, value_zscore,
                    affected_sectors, affected_tickers, signal_direction,
                    signal_strength, narrative, raw_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    # Compute per-symbol scores
    print("  Computing per-symbol alt data scores...")
    _compute_symbol_scores(today)

    # Summary
    print(f"\n  Alternative data complete: {len(all_signals)} signals from "
          f"{len(set(s['source'] for s in all_signals))} sources")
    print("=" * 60)


if __name__ == "__main__":
    run()
