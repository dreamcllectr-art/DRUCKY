"""Global Energy Markets Data Ingestion — benchmarks, curves, spreads, carbon."""

import sys, logging, time
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import EIA_API_KEY
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

BENCHMARKS = {
    "TTF":    {"ticker": "TTF=F", "name": "Dutch TTF Natural Gas", "unit": "EUR/MWh", "region": "europe"},
    "BRENT":  {"ticker": "BZ=F",  "name": "ICE Brent Crude", "unit": "USD/bbl", "region": "global"},
    "WTI":    {"ticker": "CL=F",  "name": "NYMEX WTI Crude", "unit": "USD/bbl", "region": "us"},
    "HH":     {"ticker": "NG=F",  "name": "Henry Hub Natural Gas", "unit": "USD/MMBtu", "region": "us"},
    "RBOB":   {"ticker": "RB=F",  "name": "RBOB Gasoline", "unit": "USD/gal", "region": "us"},
    "HO":     {"ticker": "HO=F",  "name": "NY Harbor Heating Oil", "unit": "USD/gal", "region": "us"},
    "COPPER": {"ticker": "HG=F",  "name": "Copper (demand proxy)", "unit": "USD/lb", "region": "global"},
}
MONTH_CODES = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]
CURVE_CONTRACTS = {"WTI": {"base": "CL", "months": 6}, "BRENT": {"base": "BZ", "months": 6},
                   "HH": {"base": "NG", "months": 6}, "TTF": {"base": "TTF", "months": 4}}
SPREAD_DEFINITIONS = {
    "brent_wti": {"name": "Brent-WTI Spread", "long": "BRENT", "short": "WTI", "normal_range": (2.0, 8.0)},
    "ttf_hh": {"name": "TTF-HH Basis (LNG Arb)", "long": "TTF", "short": "HH", "normal_range": (3.0, 15.0), "conversion": "ttf_to_mmbtu"},
    "crack_321": {"name": "3-2-1 Crack Spread (US Gulf)", "type": "crack"},
}
EUR_USD = 1.08
MWH_TO_MMBTU = 3.412


def _fetch_benchmark_prices() -> dict[str, dict]:
    print("  Fetching global energy benchmark prices...")
    try: import yfinance as yf
    except ImportError: print("    ERROR: yfinance not installed"); return {}
    results, rows, today_str = {}, [], date.today().isoformat()
    for bm_id, meta in BENCHMARKS.items():
        try:
            data = yf.download(meta["ticker"], period="90d", interval="1d", progress=False, timeout=15)
            if data.empty: continue
            if hasattr(data.columns, 'levels') and data.columns.nlevels > 1:
                data.columns = data.columns.get_level_values(0)
            latest = float(data["Close"].iloc[-1])
            results[bm_id] = {"price": latest, "high_90d": float(data["High"].max()), "low_90d": float(data["Low"].min())}
            if len(data) >= 5: results[bm_id]["return_1w"] = (latest - float(data["Close"].iloc[-5])) / float(data["Close"].iloc[-5]) * 100
            if len(data) >= 22: results[bm_id]["return_1m"] = (latest - float(data["Close"].iloc[-22])) / float(data["Close"].iloc[-22]) * 100
            for idx, row in data.iterrows():
                dt = idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10]
                rows.append((bm_id, dt, meta["name"], meta["unit"], meta["region"],
                    float(row["Open"]) if row["Open"] == row["Open"] else None,
                    float(row["High"]) if row["High"] == row["High"] else None,
                    float(row["Low"]) if row["Low"] == row["Low"] else None,
                    float(row["Close"]) if row["Close"] == row["Close"] else None,
                    int(row["Volume"]) if row["Volume"] == row["Volume"] else 0, today_str))
        except Exception as e: logger.warning(f"  Failed to fetch {bm_id}: {e}")
    if rows:
        upsert_many("global_energy_benchmarks", ["benchmark_id", "date", "name", "unit", "region", "open", "high", "low", "close", "volume", "last_updated"], rows)
    print(f"    Fetched {len(results)} benchmarks, {len(rows)} price records")
    return results


def _get_curve_tickers(base: str, n_months: int) -> list[tuple[str, int]]:
    now = datetime.now(); cm, cy = now.month, now.year % 100
    return [(f"{base}{MONTH_CODES[(cm + i) % 12]}{cy + (cm + i - 1) // 12}", i + 1) for i in range(n_months)]


def _fetch_futures_curves(benchmarks: dict) -> dict[str, dict]:
    print("  Fetching futures term structure...")
    try: import yfinance as yf
    except ImportError: return {}
    today_str = date.today().isoformat(); curves, rows = {}, []
    for curve_id, spec in CURVE_CONTRACTS.items():
        contracts = _get_curve_tickers(spec["base"], spec["months"])
        prices = []
        try:
            data = yf.download([t for t, _ in contracts], period="5d", interval="1d", progress=False, timeout=15)
            if data.empty:
                if curve_id in benchmarks: prices = [(1, benchmarks[curve_id]["price"])]
                continue
            for ticker, months_out in contracts:
                try:
                    col = data["Close"][ticker] if len(contracts) > 1 and hasattr(data.columns, 'levels') else data["Close"]
                    latest = col.dropna()
                    if not latest.empty:
                        p = float(latest.iloc[-1]); prices.append((months_out, p))
                        rows.append((curve_id, today_str, months_out, ticker, p, today_str))
                except (KeyError, IndexError): continue
        except Exception:
            if curve_id in benchmarks: prices = [(1, benchmarks[curve_id]["price"])]
        if len(prices) >= 2:
            front, back = prices[0][1], prices[-1][1]
            spread_pct = ((back - front) / front * 100) if front else 0
            curves[curve_id] = {"structure": "contango" if back > front else "backwardation",
                "front_price": front, "back_price": back, "spread": back - front, "spread_pct": spread_pct, "n_months": len(prices)}
        elif len(prices) == 1:
            curves[curve_id] = {"structure": "flat", "front_price": prices[0][1], "back_price": prices[0][1], "spread": 0, "spread_pct": 0, "n_months": 1}
    if rows: upsert_many("global_energy_curves", ["curve_id", "date", "months_out", "contract_ticker", "price", "last_updated"], rows)
    print(f"    {len(curves)} curves analyzed")
    return curves


def _compute_spreads(benchmarks: dict) -> dict[str, dict]:
    print("  Computing basis + crack spreads...")
    today_str = date.today().isoformat(); spreads, rows = {}, []
    if "BRENT" in benchmarks and "WTI" in benchmarks:
        brent, wti = benchmarks["BRENT"]["price"], benchmarks["WTI"]["price"]
        spread = brent - wti
        lo, hi = SPREAD_DEFINITIONS["brent_wti"]["normal_range"]
        assessment = "wide" if spread > hi else ("narrow" if spread < lo else "normal")
        spreads["brent_wti"] = {"value": spread, "assessment": assessment, "description": f"${spread:.2f}/bbl ({assessment})"}
        rows.append(("brent_wti", today_str, "Brent-WTI Spread", spread, brent, wti, assessment, "USD/bbl", today_str))
    if "TTF" in benchmarks and "HH" in benchmarks:
        ttf_usd = benchmarks["TTF"]["price"] * EUR_USD / MWH_TO_MMBTU
        hh = benchmarks["HH"]["price"]; basis = ttf_usd - hh
        lo, hi = SPREAD_DEFINITIONS["ttf_hh"]["normal_range"]
        assessment = "wide" if basis > hi else ("narrow" if basis < lo else ("negative" if basis < 0 else "normal"))
        spreads["ttf_hh"] = {"value": basis, "assessment": assessment, "description": f"${basis:.2f}/MMBtu ({assessment})"}
        rows.append(("ttf_hh", today_str, "TTF-HH LNG Arb Basis", basis, ttf_usd, hh, assessment, "USD/MMBtu", today_str))
    if "WTI" in benchmarks and "RBOB" in benchmarks and "HO" in benchmarks:
        wti = benchmarks["WTI"]["price"]; rbob_bbl = benchmarks["RBOB"]["price"] * 42; ho_bbl = benchmarks["HO"]["price"] * 42
        crack = (2 * rbob_bbl + ho_bbl) / 3 - wti
        assessment = "excellent" if crack > 30 else ("strong" if crack > 20 else ("normal" if crack > 10 else ("weak" if crack > 0 else "negative")))
        spreads["crack_321"] = {"value": crack, "assessment": assessment, "description": f"${crack:.2f}/bbl ({assessment})"}
        rows.append(("crack_321", today_str, "3-2-1 Crack Spread", crack, wti, rbob_bbl, assessment, "USD/bbl", today_str))
        gas_crack = rbob_bbl - wti
        a = "strong" if gas_crack > 15 else ("normal" if gas_crack > 5 else "weak")
        spreads["gasoline_crack"] = {"value": gas_crack, "assessment": a, "description": f"${gas_crack:.2f}/bbl"}
        rows.append(("gasoline_crack", today_str, "Gasoline Crack", gas_crack, wti, rbob_bbl, a, "USD/bbl", today_str))
        diesel_crack = ho_bbl - wti
        a = "strong" if diesel_crack > 20 else ("normal" if diesel_crack > 10 else "weak")
        spreads["diesel_crack"] = {"value": diesel_crack, "assessment": a, "description": f"${diesel_crack:.2f}/bbl"}
        rows.append(("diesel_crack", today_str, "Diesel/HO Crack", diesel_crack, wti, ho_bbl, a, "USD/bbl", today_str))
    if rows: upsert_many("global_energy_spreads", ["spread_id", "date", "name", "value", "leg_a", "leg_b", "assessment", "unit", "last_updated"], rows)
    for sid, s in spreads.items(): print(f"    {sid}: {s['description']}")
    return spreads


def _fetch_carbon_prices() -> dict:
    print("  Fetching carbon credit prices...")
    today_str = date.today().isoformat()
    try:
        import yfinance as yf
        for ticker in ["ECF=F", "CKZ25.L", "KRBN"]:
            try:
                data = yf.download(ticker, period="90d", interval="1d", progress=False, timeout=10)
                if data.empty: continue
                if hasattr(data.columns, 'levels') and data.columns.nlevels > 1: data.columns = data.columns.get_level_values(0)
                latest = float(data["Close"].iloc[-1])
                result = {"price": latest, "source": ticker, "unit": "EUR/tonne" if ticker != "KRBN" else "USD/share"}
                closes = data["Close"].dropna().values
                if len(closes) > 10:
                    import numpy as np
                    result["median_90d"] = float(np.percentile(closes, 50))
                    result["percentile"] = float(sum(1 for c in closes if c <= latest) / len(closes) * 100)
                rows = [(
                    "EU_ETS", idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx)[:10],
                    ticker, float(row["Close"]), result.get("unit", "EUR/tonne"), today_str
                ) for idx, row in data.iterrows() if row["Close"] == row["Close"]]
                if rows: upsert_many("global_energy_carbon", ["market_id", "date", "source_ticker", "price", "unit", "last_updated"], rows)
                print(f"    EU ETS ({ticker}): {latest:.2f}"); return result
            except Exception: continue
    except ImportError: pass
    print("    Carbon prices unavailable"); return {}


def _compute_historical_spreads():
    print("  Computing historical spread statistics...")
    stats = {}
    def _calc_stats(label, values):
        if len(values) < 20: return
        avg = sum(values) / len(values)
        std = (sum((v - avg) ** 2 for v in values) / len(values)) ** 0.5
        stats[label] = {"current": values[0], "avg_90d": avg, "std_90d": std,
            "zscore": (values[0] - avg) / std if std > 0 else 0, "min_90d": min(values), "max_90d": max(values)}
        print(f"    {label}: z={stats[label]['zscore']:+.2f} (current={values[0]:.2f}, avg={avg:.2f})")
    rows = query("SELECT b.close as bc, w.close as wc FROM global_energy_benchmarks b JOIN global_energy_benchmarks w ON b.date=w.date WHERE b.benchmark_id='BRENT' AND w.benchmark_id='WTI' AND b.close IS NOT NULL AND w.close IS NOT NULL ORDER BY b.date DESC LIMIT 90")
    _calc_stats("brent_wti", [r["bc"] - r["wc"] for r in rows])
    rows = query("SELECT t.close as tc, h.close as hc FROM global_energy_benchmarks t JOIN global_energy_benchmarks h ON t.date=h.date WHERE t.benchmark_id='TTF' AND h.benchmark_id='HH' AND t.close IS NOT NULL AND h.close IS NOT NULL ORDER BY t.date DESC LIMIT 90")
    _calc_stats("ttf_hh", [r["tc"] * EUR_USD / MWH_TO_MMBTU - r["hc"] for r in rows])
    rows = query("SELECT w.close as wti, r.close as rbob, h.close as ho FROM global_energy_benchmarks w JOIN global_energy_benchmarks r ON w.date=r.date JOIN global_energy_benchmarks h ON w.date=h.date WHERE w.benchmark_id='WTI' AND r.benchmark_id='RBOB' AND h.benchmark_id='HO' AND w.close IS NOT NULL AND r.close IS NOT NULL AND h.close IS NOT NULL ORDER BY w.date DESC LIMIT 90")
    _calc_stats("crack_321", [(2 * r["rbob"] * 42 + r["ho"] * 42) / 3 - r["wti"] for r in rows])
    return stats


def run():
    init_db()
    print("\n  === GLOBAL ENERGY MARKETS DATA INGESTION ===")
    benchmarks = _fetch_benchmark_prices()
    curves = _fetch_futures_curves(benchmarks)
    spreads = _compute_spreads(benchmarks)
    carbon = _fetch_carbon_prices()
    spread_stats = _compute_historical_spreads()
    print(f"\n  Summary: {len(benchmarks)} benchmarks")
    for bm_id, bm in benchmarks.items(): print(f"    {bm_id:8s}: ${bm['price']:>8.2f}  (1w: {bm.get('return_1w',0):+.1f}%)")
    if curves:
        print(f"  Term structure:")
        for cid, c in curves.items(): print(f"    {cid:8s}: {c['structure']:15s} ({c['spread_pct']:+.2f}%)")
    if spreads: print(f"  Spreads: {len(spreads)} computed")
    if carbon: print(f"  Carbon: EU ETS = {carbon.get('price', 'N/A')}")
    print("  === GLOBAL ENERGY DATA INGESTION COMPLETE ===\n")
    return {"benchmarks": benchmarks, "curves": curves, "spreads": spreads, "carbon": carbon, "spread_stats": spread_stats}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); run()
