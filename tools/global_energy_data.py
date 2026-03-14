"""Global Energy Markets Data Ingestion — institutional-grade energy benchmarks.

Fetches and caches global energy market data that the existing energy_intel
module lacks. This is the data layer; scoring is in global_energy_markets.py.

Data sources (all free, no API keys required):
  1. yfinance: TTF, Brent, WTI, Henry Hub, RBOB, Heating Oil futures
  2. yfinance: Multi-month futures curves (contango/backwardation detection)
  3. yfinance: Computed crack spreads (3-2-1 US Gulf, NWE proxy)
  4. EIA API: Henry Hub spot price (weekly)
  5. World Bank: Global commodity price indices
  6. Calculated: TTF-HH basis, Brent-WTI spread, regional crack spreads

Pipeline phase: 1.5c (after energy_intel_data, before scoring modules)

DB tables:
  - global_energy_benchmarks: daily benchmark prices (TTF, Brent, WTI, HH, etc.)
  - global_energy_curves: futures term structure snapshots
  - global_energy_spreads: computed basis spreads and crack spreads
  - global_energy_carbon: EU ETS carbon credit tracking
"""

import sys
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import EIA_API_KEY
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────
# Benchmark Definitions
# ─────────────────────────────────────────────────────────

# Core benchmarks to track daily
BENCHMARKS = {
    # European gas
    "TTF":      {"ticker": "TTF=F",  "name": "Dutch TTF Natural Gas",      "unit": "EUR/MWh", "region": "europe"},
    # Crude oil
    "BRENT":    {"ticker": "BZ=F",   "name": "ICE Brent Crude",            "unit": "USD/bbl", "region": "global"},
    "WTI":      {"ticker": "CL=F",   "name": "NYMEX WTI Crude",            "unit": "USD/bbl", "region": "us"},
    # Natural gas
    "HH":       {"ticker": "NG=F",   "name": "Henry Hub Natural Gas",      "unit": "USD/MMBtu", "region": "us"},
    # Refined products (for crack spread calculation)
    "RBOB":     {"ticker": "RB=F",   "name": "RBOB Gasoline",              "unit": "USD/gal", "region": "us"},
    "HO":       {"ticker": "HO=F",   "name": "NY Harbor Heating Oil",      "unit": "USD/gal", "region": "us"},
    # Metals (energy-adjacent)
    "COPPER":   {"ticker": "HG=F",   "name": "Copper (demand proxy)",      "unit": "USD/lb",  "region": "global"},
}

# Futures curve contracts (front months for term structure)
# yfinance uses CLF26, CLG26, ... for WTI; BZF26, BZG26, ... for Brent
# Month codes: F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun, N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec
MONTH_CODES = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]

CURVE_CONTRACTS = {
    "WTI": {"base": "CL", "months": 6},   # 6 front months
    "BRENT": {"base": "BZ", "months": 6},
    "HH": {"base": "NG", "months": 6},
    "TTF": {"base": "TTF", "months": 4},   # Fewer months available
}

# Key computed spreads
SPREAD_DEFINITIONS = {
    "brent_wti": {
        "name": "Brent-WTI Spread",
        "long": "BRENT", "short": "WTI",
        "description": "Atlantic basin arb; wide = tight Brent, export economics",
        "normal_range": (2.0, 8.0),  # Typical $2-8 spread
    },
    "ttf_hh": {
        "name": "TTF-HH Basis (LNG Arb)",
        "long": "TTF", "short": "HH",
        "description": "LNG export economics; wide = profitable US LNG exports",
        "normal_range": (3.0, 15.0),  # Varies widely
        "conversion": "ttf_to_mmbtu",  # TTF is EUR/MWh, need to convert
    },
    "crack_321": {
        "name": "3-2-1 Crack Spread (US Gulf)",
        "description": "Refiner margin proxy: (2×RBOB + 1×HO)/3 - WTI",
        "type": "crack",
    },
}


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


# ─────────────────────────────────────────────────────────
# 1. Benchmark Price Fetching
# ─────────────────────────────────────────────────────────

def _fetch_benchmark_prices() -> dict[str, dict]:
    """Fetch current + historical prices for all benchmarks via yfinance."""
    print("  Fetching global energy benchmark prices...")

    try:
        import yfinance as yf
    except ImportError:
        print("    ERROR: yfinance not installed")
        return {}

    tickers = {k: v["ticker"] for k, v in BENCHMARKS.items()}
    results = {}
    today_str = date.today().isoformat()
    rows = []

    # Fetch 90 days of history for each benchmark
    for bm_id, ticker in tickers.items():
        try:
            data = yf.download(
                ticker,
                period="90d",
                interval="1d",
                progress=False,
                timeout=15,
            )
            if data.empty:
                logger.warning(f"  No data for {bm_id} ({ticker})")
                continue

            # Flatten multi-level columns if present
            if hasattr(data.columns, 'levels') and data.columns.nlevels > 1:
                data.columns = data.columns.get_level_values(0)

            meta = BENCHMARKS[bm_id]
            latest_close = float(data["Close"].iloc[-1])
            results[bm_id] = {
                "price": latest_close,
                "high_90d": float(data["High"].max()),
                "low_90d": float(data["Low"].min()),
            }

            # Compute returns
            if len(data) >= 5:
                results[bm_id]["return_1w"] = (
                    (latest_close - float(data["Close"].iloc[-5])) /
                    float(data["Close"].iloc[-5]) * 100
                )
            if len(data) >= 22:
                results[bm_id]["return_1m"] = (
                    (latest_close - float(data["Close"].iloc[-22])) /
                    float(data["Close"].iloc[-22]) * 100
                )

            # Store full history
            for idx, row in data.iterrows():
                dt = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10]
                rows.append((
                    bm_id, dt, meta["name"], meta["unit"], meta["region"],
                    float(row["Open"]) if row["Open"] == row["Open"] else None,
                    float(row["High"]) if row["High"] == row["High"] else None,
                    float(row["Low"]) if row["Low"] == row["Low"] else None,
                    float(row["Close"]) if row["Close"] == row["Close"] else None,
                    int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,
                    today_str,
                ))

            logger.info(f"    {bm_id}: ${latest_close:.2f} ({len(data)} days)")

        except Exception as e:
            logger.warning(f"  Failed to fetch {bm_id}: {e}")
            continue

    # Persist
    if rows:
        upsert_many(
            "global_energy_benchmarks",
            ["benchmark_id", "date", "name", "unit", "region",
             "open", "high", "low", "close", "volume", "last_updated"],
            rows,
        )

    print(f"    Fetched {len(results)} benchmarks, {len(rows)} price records")
    return results


# ─────────────────────────────────────────────────────────
# 2. Futures Term Structure (Contango/Backwardation)
# ─────────────────────────────────────────────────────────

def _get_curve_tickers(base: str, n_months: int) -> list[tuple[str, int]]:
    """Generate yfinance tickers for N front-month contracts.

    Returns [(ticker, months_out), ...].
    """
    now = datetime.now()
    current_month = now.month
    current_year = now.year % 100  # 2-digit year

    contracts = []
    for i in range(n_months):
        month_idx = (current_month + i) % 12  # 0-indexed
        year = current_year + (current_month + i - 1) // 12
        month_code = MONTH_CODES[month_idx]
        ticker = f"{base}{month_code}{year}"
        contracts.append((ticker, i + 1))

    return contracts


def _fetch_futures_curves(benchmarks: dict) -> dict[str, dict]:
    """Fetch futures curves and detect contango/backwardation."""
    print("  Fetching futures term structure...")

    try:
        import yfinance as yf
    except ImportError:
        return {}

    today_str = date.today().isoformat()
    curves = {}
    rows = []

    for curve_id, spec in CURVE_CONTRACTS.items():
        contracts = _get_curve_tickers(spec["base"], spec["months"])
        prices = []

        # Batch download
        ticker_list = [t for t, _ in contracts]
        try:
            data = yf.download(
                ticker_list,
                period="5d",
                interval="1d",
                progress=False,
                timeout=15,
            )

            if data.empty:
                # Fallback: try front month only from benchmarks
                if curve_id in benchmarks:
                    prices = [(1, benchmarks[curve_id]["price"])]
                continue

            for ticker, months_out in contracts:
                try:
                    if len(ticker_list) > 1 and hasattr(data.columns, 'levels'):
                        col_data = data["Close"][ticker]
                    else:
                        col_data = data["Close"]

                    latest = col_data.dropna()
                    if not latest.empty:
                        price = float(latest.iloc[-1])
                        prices.append((months_out, price))
                        rows.append((
                            curve_id, today_str, months_out, ticker,
                            price, today_str,
                        ))
                except (KeyError, IndexError):
                    continue

        except Exception as e:
            logger.warning(f"  Curve fetch failed for {curve_id}: {e}")
            # Use front month from benchmarks as fallback
            if curve_id in benchmarks:
                prices = [(1, benchmarks[curve_id]["price"])]

        if len(prices) >= 2:
            front = prices[0][1]
            back = prices[-1][1]
            spread = back - front
            spread_pct = (spread / front * 100) if front else 0

            structure = "contango" if spread > 0 else "backwardation"
            curves[curve_id] = {
                "structure": structure,
                "front_price": front,
                "back_price": back,
                "spread": spread,
                "spread_pct": spread_pct,
                "n_months": len(prices),
            }
            logger.info(f"    {curve_id}: {structure} ({spread_pct:+.2f}% over {len(prices)} months)")
        elif len(prices) == 1:
            curves[curve_id] = {
                "structure": "flat",
                "front_price": prices[0][1],
                "back_price": prices[0][1],
                "spread": 0,
                "spread_pct": 0,
                "n_months": 1,
            }

    # Persist
    if rows:
        upsert_many(
            "global_energy_curves",
            ["curve_id", "date", "months_out", "contract_ticker",
             "price", "last_updated"],
            rows,
        )

    print(f"    {len(curves)} curves analyzed")
    return curves


# ─────────────────────────────────────────────────────────
# 3. Basis Spreads & Crack Spreads
# ─────────────────────────────────────────────────────────

def _compute_spreads(benchmarks: dict) -> dict[str, dict]:
    """Compute basis spreads (Brent-WTI, TTF-HH) and crack spreads."""
    print("  Computing basis + crack spreads...")

    today_str = date.today().isoformat()
    spreads = {}
    rows = []

    # TTF EUR/MWh → USD/MMBtu conversion (approximate)
    # 1 MWh = 3.412 MMBtu, and EUR/USD ~ 1.08
    EUR_USD = 1.08
    MWH_TO_MMBTU = 3.412

    # Brent-WTI spread
    if "BRENT" in benchmarks and "WTI" in benchmarks:
        brent = benchmarks["BRENT"]["price"]
        wti = benchmarks["WTI"]["price"]
        spread = brent - wti
        normal_lo, normal_hi = SPREAD_DEFINITIONS["brent_wti"]["normal_range"]

        if spread > normal_hi:
            assessment = "wide"
        elif spread < normal_lo:
            assessment = "narrow"
        else:
            assessment = "normal"

        spreads["brent_wti"] = {
            "value": spread,
            "assessment": assessment,
            "brent": brent,
            "wti": wti,
            "description": f"${spread:.2f}/bbl ({assessment})",
        }
        rows.append(("brent_wti", today_str, "Brent-WTI Spread",
                     spread, brent, wti, assessment, "USD/bbl", today_str))

    # TTF-HH basis (LNG arb)
    if "TTF" in benchmarks and "HH" in benchmarks:
        ttf_eur_mwh = benchmarks["TTF"]["price"]
        hh_usd_mmbtu = benchmarks["HH"]["price"]

        # Convert TTF to USD/MMBtu for comparison
        ttf_usd_mmbtu = ttf_eur_mwh * EUR_USD / MWH_TO_MMBTU

        basis = ttf_usd_mmbtu - hh_usd_mmbtu
        normal_lo, normal_hi = SPREAD_DEFINITIONS["ttf_hh"]["normal_range"]

        if basis > normal_hi:
            assessment = "wide"  # Very profitable LNG exports
        elif basis < normal_lo:
            assessment = "narrow"  # Marginal LNG economics
        elif basis < 0:
            assessment = "negative"  # Shut-in LNG economics
        else:
            assessment = "normal"

        spreads["ttf_hh"] = {
            "value": basis,
            "assessment": assessment,
            "ttf_eur_mwh": ttf_eur_mwh,
            "ttf_usd_mmbtu": ttf_usd_mmbtu,
            "hh_usd_mmbtu": hh_usd_mmbtu,
            "description": f"${basis:.2f}/MMBtu ({assessment}) — LNG arb",
        }
        rows.append(("ttf_hh", today_str, "TTF-HH LNG Arb Basis",
                     basis, ttf_usd_mmbtu, hh_usd_mmbtu, assessment, "USD/MMBtu", today_str))

    # 3-2-1 Crack Spread (US Gulf)
    if "WTI" in benchmarks and "RBOB" in benchmarks and "HO" in benchmarks:
        wti = benchmarks["WTI"]["price"]
        rbob_gal = benchmarks["RBOB"]["price"]
        ho_gal = benchmarks["HO"]["price"]

        # Convert products from $/gal to $/bbl (42 gal/bbl)
        rbob_bbl = rbob_gal * 42
        ho_bbl = ho_gal * 42

        # 3-2-1: (2*gasoline + 1*heating oil) / 3 - crude
        crack = (2 * rbob_bbl + 1 * ho_bbl) / 3 - wti

        if crack > 30:
            assessment = "excellent"  # Historically strong margins
        elif crack > 20:
            assessment = "strong"
        elif crack > 10:
            assessment = "normal"
        elif crack > 0:
            assessment = "weak"
        else:
            assessment = "negative"  # Refiners losing money

        spreads["crack_321"] = {
            "value": crack,
            "assessment": assessment,
            "wti": wti,
            "rbob_bbl": rbob_bbl,
            "ho_bbl": ho_bbl,
            "description": f"${crack:.2f}/bbl ({assessment})",
        }
        rows.append(("crack_321", today_str, "3-2-1 Crack Spread (US Gulf)",
                     crack, wti, rbob_bbl, assessment, "USD/bbl", today_str))

        # Gasoline crack (simpler)
        gas_crack = rbob_bbl - wti
        spreads["gasoline_crack"] = {
            "value": gas_crack,
            "assessment": "strong" if gas_crack > 15 else ("normal" if gas_crack > 5 else "weak"),
            "description": f"${gas_crack:.2f}/bbl",
        }
        rows.append(("gasoline_crack", today_str, "Gasoline Crack",
                     gas_crack, wti, rbob_bbl, spreads["gasoline_crack"]["assessment"],
                     "USD/bbl", today_str))

        # Heating oil / diesel crack
        diesel_crack = ho_bbl - wti
        spreads["diesel_crack"] = {
            "value": diesel_crack,
            "assessment": "strong" if diesel_crack > 20 else ("normal" if diesel_crack > 10 else "weak"),
            "description": f"${diesel_crack:.2f}/bbl",
        }
        rows.append(("diesel_crack", today_str, "Diesel/HO Crack",
                     diesel_crack, wti, ho_bbl, spreads["diesel_crack"]["assessment"],
                     "USD/bbl", today_str))

    # Persist
    if rows:
        upsert_many(
            "global_energy_spreads",
            ["spread_id", "date", "name", "value", "leg_a", "leg_b",
             "assessment", "unit", "last_updated"],
            rows,
        )

    for sid, s in spreads.items():
        print(f"    {sid}: {s['description']}")

    return spreads


# ─────────────────────────────────────────────────────────
# 4. Carbon Markets (EU ETS proxy)
# ─────────────────────────────────────────────────────────

def _fetch_carbon_prices() -> dict:
    """Fetch EU ETS carbon credit prices.

    Primary: yfinance ECF=F (ICE EUA futures) or proxy via web.
    Fallback: Trading Economics free endpoint.
    """
    print("  Fetching carbon credit prices...")

    today_str = date.today().isoformat()
    result = {}

    try:
        import yfinance as yf

        # Try ICE EUA futures
        for ticker in ["ECF=F", "CKZ25.L", "KRBN"]:
            try:
                data = yf.download(ticker, period="90d", interval="1d",
                                   progress=False, timeout=10)
                if not data.empty:
                    if hasattr(data.columns, 'levels') and data.columns.nlevels > 1:
                        data.columns = data.columns.get_level_values(0)

                    latest = float(data["Close"].iloc[-1])
                    result = {
                        "price": latest,
                        "source": ticker,
                        "unit": "EUR/tonne" if ticker != "KRBN" else "USD/share",
                    }

                    # Compute 90d percentile
                    closes = data["Close"].dropna().values
                    if len(closes) > 10:
                        import numpy as np
                        pctl = float(np.percentile(closes, [25, 50, 75]).tolist()[1])
                        result["median_90d"] = pctl
                        result["percentile"] = float(
                            sum(1 for c in closes if c <= latest) / len(closes) * 100
                        )

                    rows = []
                    for idx, row in data.iterrows():
                        dt = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10]
                        close_val = float(row["Close"]) if row["Close"] == row["Close"] else None
                        if close_val is not None:
                            rows.append((
                                "EU_ETS", dt, ticker, close_val,
                                result.get("unit", "EUR/tonne"), today_str,
                            ))

                    if rows:
                        upsert_many(
                            "global_energy_carbon",
                            ["market_id", "date", "source_ticker", "price",
                             "unit", "last_updated"],
                            rows,
                        )

                    print(f"    EU ETS ({ticker}): {latest:.2f}")
                    return result

            except Exception:
                continue

    except ImportError:
        pass

    if not result:
        print("    Carbon prices unavailable (no working ticker found)")

    return result


# ─────────────────────────────────────────────────────────
# 5. Historical Spread Computation (for z-scoring)
# ─────────────────────────────────────────────────────────

def _compute_historical_spreads():
    """Compute historical spreads from stored benchmark data for z-score analysis."""
    print("  Computing historical spread statistics...")

    # Brent-WTI historical
    brent_wti_rows = query("""
        SELECT b.date,
               b.close as brent_close,
               w.close as wti_close,
               (b.close - w.close) as spread
        FROM global_energy_benchmarks b
        JOIN global_energy_benchmarks w ON b.date = w.date
        WHERE b.benchmark_id = 'BRENT' AND w.benchmark_id = 'WTI'
        AND b.close IS NOT NULL AND w.close IS NOT NULL
        ORDER BY b.date DESC
        LIMIT 90
    """)

    stats = {}

    if len(brent_wti_rows) >= 20:
        spreads = [r["spread"] for r in brent_wti_rows]
        avg = sum(spreads) / len(spreads)
        std = (sum((s - avg) ** 2 for s in spreads) / len(spreads)) ** 0.5
        current = spreads[0]
        zscore = (current - avg) / std if std > 0 else 0

        stats["brent_wti"] = {
            "current": current,
            "avg_90d": avg,
            "std_90d": std,
            "zscore": zscore,
            "min_90d": min(spreads),
            "max_90d": max(spreads),
        }

    # TTF-HH historical (requires conversion)
    ttf_hh_rows = query("""
        SELECT t.date,
               t.close as ttf_close,
               h.close as hh_close
        FROM global_energy_benchmarks t
        JOIN global_energy_benchmarks h ON t.date = h.date
        WHERE t.benchmark_id = 'TTF' AND h.benchmark_id = 'HH'
        AND t.close IS NOT NULL AND h.close IS NOT NULL
        ORDER BY t.date DESC
        LIMIT 90
    """)

    EUR_USD = 1.08
    MWH_TO_MMBTU = 3.412

    if len(ttf_hh_rows) >= 20:
        bases = [(r["ttf_close"] * EUR_USD / MWH_TO_MMBTU - r["hh_close"]) for r in ttf_hh_rows]
        avg = sum(bases) / len(bases)
        std = (sum((b - avg) ** 2 for b in bases) / len(bases)) ** 0.5
        current = bases[0]
        zscore = (current - avg) / std if std > 0 else 0

        stats["ttf_hh"] = {
            "current": current,
            "avg_90d": avg,
            "std_90d": std,
            "zscore": zscore,
            "min_90d": min(bases),
            "max_90d": max(bases),
        }

    # 3-2-1 crack historical
    crack_rows = query("""
        SELECT w.date,
               w.close as wti,
               r.close as rbob,
               h.close as ho
        FROM global_energy_benchmarks w
        JOIN global_energy_benchmarks r ON w.date = r.date
        JOIN global_energy_benchmarks h ON w.date = h.date
        WHERE w.benchmark_id = 'WTI' AND r.benchmark_id = 'RBOB'
        AND h.benchmark_id = 'HO'
        AND w.close IS NOT NULL AND r.close IS NOT NULL AND h.close IS NOT NULL
        ORDER BY w.date DESC
        LIMIT 90
    """)

    if len(crack_rows) >= 20:
        cracks = [(2 * r["rbob"] * 42 + r["ho"] * 42) / 3 - r["wti"] for r in crack_rows]
        avg = sum(cracks) / len(cracks)
        std = (sum((c - avg) ** 2 for c in cracks) / len(cracks)) ** 0.5
        current = cracks[0]
        zscore = (current - avg) / std if std > 0 else 0

        stats["crack_321"] = {
            "current": current,
            "avg_90d": avg,
            "std_90d": std,
            "zscore": zscore,
            "min_90d": min(cracks),
            "max_90d": max(cracks),
        }

    for sid, s in stats.items():
        print(f"    {sid}: z={s['zscore']:+.2f} (current={s['current']:.2f}, avg={s['avg_90d']:.2f})")

    return stats


# ─────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────

def run():
    """Main entry point — called by daily_pipeline.py Phase 1.5c."""
    init_db()

    print("\n  === GLOBAL ENERGY MARKETS DATA INGESTION ===")

    # 1. Benchmark prices (TTF, Brent, WTI, HH, RBOB, HO, Copper)
    benchmarks = _fetch_benchmark_prices()

    # 2. Futures term structure (contango/backwardation)
    curves = _fetch_futures_curves(benchmarks)

    # 3. Basis spreads + crack spreads
    spreads = _compute_spreads(benchmarks)

    # 4. Carbon markets (EU ETS)
    carbon = _fetch_carbon_prices()

    # 5. Historical spread statistics
    spread_stats = _compute_historical_spreads()

    # Summary
    print(f"\n  Summary:")
    print(f"    Benchmarks: {len(benchmarks)} fetched")
    for bm_id, bm in benchmarks.items():
        ret_1w = bm.get("return_1w", 0)
        print(f"      {bm_id:8s}: ${bm['price']:>8.2f}  (1w: {ret_1w:+.1f}%)")

    if curves:
        print(f"    Term structure:")
        for cid, c in curves.items():
            print(f"      {cid:8s}: {c['structure']:15s} ({c['spread_pct']:+.2f}% over {c['n_months']}mo)")

    if spreads:
        print(f"    Spreads: {len(spreads)} computed")

    if carbon:
        print(f"    Carbon: EU ETS = {carbon.get('price', 'N/A')}")

    print("  === GLOBAL ENERGY DATA INGESTION COMPLETE ===\n")

    return {
        "benchmarks": benchmarks,
        "curves": curves,
        "spreads": spreads,
        "carbon": carbon,
        "spread_stats": spread_stats,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
