"""Estimate Revision Momentum — tracks velocity/acceleration of analyst estimate revisions."""
import sys, time, logging
import numpy as np
from datetime import date, datetime
_project_root = str(__import__("pathlib").Path(__file__).parent.parent)
if _project_root not in sys.path: sys.path.insert(0, _project_root)
from tools.config import (
    FMP_API_KEY, EM_REVISION_VELOCITY_WEIGHT, EM_REVENUE_VELOCITY_WEIGHT,
    EM_ACCELERATION_WEIGHT, EM_SURPRISE_MOMENTUM_WEIGHT, EM_DISPERSION_WEIGHT,
    EM_CROSS_SECTIONAL_WEIGHT, EM_STRONG_REVISION_PCT, EM_MODERATE_REVISION_PCT,
    EM_SURPRISE_STREAK_BONUS, EM_DISPERSION_TIGHTENING_BONUS,
)
from tools.db import init_db, get_conn, query, upsert_many
logger = logging.getLogger(__name__)

def _fmp_get(endpoint, params=None):
    import requests
    if not FMP_API_KEY: return None
    p = {"apikey": FMP_API_KEY, **(params or {})}
    try:
        resp = requests.get(f"https://financialmodelingprep.com/api/v3{endpoint}", params=p, timeout=10)
        return resp.json() if resp.status_code == 200 else None
    except Exception: return None

def _safe_float(val): return val is not None and not (isinstance(val, float) and np.isnan(val))

def _parse_df(df, key_map=None):
    result = {}
    if df is None or (hasattr(df, 'empty') and df.empty): return result
    for period_idx in df.index:
        pd_ = {}
        for col in df.columns:
            val = df.loc[period_idx, col]
            if _safe_float(val):
                key = str(col).lower().replace(" ", "_")
                if key_map: key = key_map.get(key, key)
                pd_[key] = float(val)
        if pd_: result[str(period_idx)] = pd_
    return result

_EE_MAP = {"numberofanalysts": "num_analysts", "yearagoeps": "year_ago_eps"}
_RE_MAP = {"numberofanalysts": "num_analysts", "yearagorevenue": "year_ago_revenue"}

def _fetch_yf_estimates(symbol):
    import yfinance as yf
    result = {"eps_trend": {}, "earnings_estimate": {}, "revenue_estimate": {}, "earnings_history": []}
    try:
        t = yf.Ticker(symbol)
        try: result["eps_trend"] = _parse_df(t.eps_trend)
        except Exception: pass
        try: result["earnings_estimate"] = _parse_df(t.earnings_estimate, _EE_MAP)
        except Exception: pass
        try: result["revenue_estimate"] = _parse_df(t.revenue_estimate, _RE_MAP)
        except Exception: pass
        try:
            eh = t.earnings_history
            if eh is not None and not eh.empty:
                for idx, row in eh.iterrows():
                    actual = row.get("epsActual")
                    if not _safe_float(actual): continue
                    est, sp = row.get("epsEstimate"), row.get("surprisePercent")
                    result["earnings_history"].append({
                        "quarter": str(idx.date()) if hasattr(idx, 'date') else str(idx),
                        "actual": float(actual),
                        "estimate": float(est) if _safe_float(est) else None,
                        "surprise_pct": round(float(sp) * 100, 2) if _safe_float(sp) else None})
        except Exception: pass
    except Exception as e: logger.debug(f"yfinance estimate fetch failed for {symbol}: {e}")
    return result

def _fetch_fmp_estimates(symbol):
    result = {"eps_trend": {}, "earnings_estimate": {}, "revenue_estimate": {}, "earnings_history": []}
    estimates = _fmp_get(f"/analyst-estimates/{symbol}", {"period": "quarter", "limit": 8})
    if estimates and isinstance(estimates, list):
        for est in estimates[:4]:
            p = est.get("date", "unknown")
            result["earnings_estimate"][p] = {"avg": est.get("estimatedEpsAvg"), "low": est.get("estimatedEpsLow"),
                "high": est.get("estimatedEpsHigh"), "num_analysts": est.get("numberAnalystEstimatedEps")}
            result["revenue_estimate"][p] = {"avg": est.get("estimatedRevenueAvg"), "low": est.get("estimatedRevenueLow"),
                "high": est.get("estimatedRevenuHigh"), "num_analysts": est.get("numberAnalystsEstimatedRevenue")}
    surprises = _fmp_get(f"/earnings-surprises/{symbol}")
    if surprises and isinstance(surprises, list):
        for s in surprises[:8]:
            actual, estimated = s.get("actualEarningResult"), s.get("estimatedEarning")
            if actual is not None and estimated is not None and abs(estimated) > 0.001:
                result["earnings_history"].append({"quarter": s.get("date"), "estimate": estimated, "actual": actual,
                    "surprise_pct": round((actual - estimated) / abs(estimated) * 100, 2)})
    return result

def _vel_contribution(vel):
    abs_vel = abs(vel)
    if abs_vel >= EM_STRONG_REVISION_PCT: c = 100
    elif abs_vel >= EM_MODERATE_REVISION_PCT: c = 30 + 70 * (abs_vel - EM_MODERATE_REVISION_PCT) / (EM_STRONG_REVISION_PCT - EM_MODERATE_REVISION_PCT)
    else: c = abs_vel / EM_MODERATE_REVISION_PCT * 30
    return c if vel > 0 else c * 0.3

def _compute_eps_revision_velocity(eps_trend):
    result = {"velocity_7d": None, "velocity_30d": None, "velocity_90d": None, "velocity_score": 0}
    for _, pd_ in eps_trend.items():
        cur = pd_.get("current")
        if cur is None: continue
        for suffix, key in [("7daysago", "velocity_7d"), ("30daysago", "velocity_30d"), ("90daysago", "velocity_90d")]:
            ago = pd_.get(suffix)
            if ago and abs(ago) > 0.001: result[key] = round((cur - ago) / abs(ago) * 100, 3)
        break
    score = sum(_vel_contribution(v) * w for v, w in
                [(result["velocity_7d"], 0.5), (result["velocity_30d"], 0.3), (result["velocity_90d"], 0.2)] if v is not None)
    result["velocity_score"] = round(min(100, max(0, score)), 1)
    return result

def _compute_revenue_revision_velocity(rev_estimates):
    result = {"rev_velocity_score": 0}
    for _, pd_ in rev_estimates.items():
        avg = pd_.get("avg")
        if avg is None: continue
        num = pd_.get("num_analysts") or pd_.get("number_of_analysts")
        result.update({"rev_avg_estimate": avg, "rev_num_analysts": num,
                       "analyst_coverage_boost": round(min(1.0, (num or 1) / 10) if num else 0.5, 2)})
        break
    return result

def _compute_revision_acceleration(eps_trend):
    result = {"acceleration": None, "acceleration_score": 0}
    for _, pd_ in eps_trend.items():
        cur, a7, a30, a90 = pd_.get("current"), pd_.get("7daysago"), pd_.get("30daysago"), pd_.get("90daysago")
        if cur is None: continue
        vel_recent = (cur - a7) / abs(a7) if a7 and abs(a7) > 0.001 else None
        vel_older = (a30 - a90) / abs(a90) if a30 and a90 and abs(a90) > 0.001 else None
        if vel_recent is not None and vel_older is not None:
            accel = round(vel_recent - vel_older, 4)
            result["acceleration"] = accel
            result["acceleration_score"] = round(min(100, accel * 500), 1) if accel > 0 else round(max(0, 30 + accel * 200), 1)
        break
    return result

def _compute_surprise_momentum(earnings_history):
    result = {"beat_streak": 0, "miss_streak": 0, "avg_surprise_pct": 0, "surprise_score": 0}
    if not earnings_history: return result
    surprises = []
    for e in earnings_history:
        s = e.get("surprise_pct") or e.get("surprise(%)") or e.get("surprisepercent")
        if s is not None:
            try: surprises.append(float(s))
            except (ValueError, TypeError): continue
    if not surprises: return result
    beat_streak = miss_streak = 0
    for s in surprises:
        if s > 0:
            if miss_streak > 0: break
            beat_streak += 1
        elif s < 0:
            if beat_streak > 0: break
            miss_streak += 1
        else: break
    result["beat_streak"], result["miss_streak"] = beat_streak, miss_streak
    result["avg_surprise_pct"] = round(np.mean(surprises[:4]), 2)
    score = {4: 60, 3: 45, 2: 25, 1: 10}.get(min(beat_streak, 4), 0) if beat_streak else 0
    avg_s = result["avg_surprise_pct"]
    score += 30 if avg_s > 10 else 20 if avg_s > 5 else 10 if avg_s > 2 else 0
    if miss_streak >= 3: score = max(0, score - 40)
    elif miss_streak >= 2: score = max(0, score - 20)
    if len(surprises) >= 2 and surprises[0] > surprises[1] > 0: score += EM_SURPRISE_STREAK_BONUS
    result["surprise_score"] = round(min(100, max(0, score)), 1)
    return result

def _compute_dispersion_change(earnings_est):
    result = {"dispersion_pct": None, "dispersion_score": 50}
    for _, pd_ in earnings_est.items():
        h, l, a = pd_.get("high"), pd_.get("low"), pd_.get("avg")
        if h is not None and l is not None and a is not None and abs(a) > 0.001:
            d = (h - l) / abs(a) * 100
            result["dispersion_pct"] = round(d, 2)
            result["dispersion_score"] = (70 + EM_DISPERSION_TIGHTENING_BONUS if d < 10 else 60 if d < 20 else 50 if d < 40 else 35 if d < 60 else 20)
            break
    return result

def _compute_cross_sectional_rank(symbol, velocity_score):
    result = {"sector_rank_pct": None, "sector_rank_score": 50}
    try:
        sector_rows = query("SELECT sector FROM stock_universe WHERE symbol = ?", [symbol])
        if not sector_rows: return result
        peer_rows = query("""SELECT em.velocity_score FROM estimate_momentum_signals em
            JOIN stock_universe su ON em.symbol = su.symbol
            WHERE su.sector = ? AND em.date = ? AND em.velocity_score IS NOT NULL""",
            [sector_rows[0]["sector"], date.today().isoformat()])
        if len(peer_rows) < 3: return result
        scores = [r["velocity_score"] for r in peer_rows]
        rp = sum(1 for s in scores if s < velocity_score) / len(scores) * 100
        result["sector_rank_pct"] = round(rp, 1)
        result["sector_rank_score"] = 95 if rp >= 90 else 75 if rp >= 75 else 55 if rp >= 50 else 35 if rp >= 25 else 15
    except Exception as e: logger.debug(f"Cross-sectional rank failed for {symbol}: {e}")
    return result

def _compute_historical_velocity(symbol, current_eps_avg, current_rev_avg):
    result = {"hist_eps_velocity": None, "hist_rev_velocity": None, "hist_score": 0}
    if current_eps_avg is None: return result
    try:
        rows = query("SELECT date, eps_current_avg, rev_current_avg FROM estimate_snapshots WHERE symbol = ? ORDER BY date DESC LIMIT 30", [symbol])
        if not rows: return result
        snap_7d = snap_30d = None; today = date.today()
        for r in rows:
            try:
                delta = (today - datetime.strptime(r["date"], "%Y-%m-%d").date()).days
                if 5 <= delta <= 10 and not snap_7d: snap_7d = r
                elif 25 <= delta <= 35 and not snap_30d: snap_30d = r
            except Exception: continue
        score = 0
        if snap_7d and snap_7d["eps_current_avg"] and abs(snap_7d["eps_current_avg"]) > 0.001:
            vel = (current_eps_avg - snap_7d["eps_current_avg"]) / abs(snap_7d["eps_current_avg"]) * 100
            result["hist_eps_velocity"] = round(vel, 3)
            score += 60 if vel > EM_STRONG_REVISION_PCT else 35 if vel > EM_MODERATE_REVISION_PCT else 15 if vel > 0 else 0
        if snap_30d and snap_30d["eps_current_avg"] and abs(snap_30d["eps_current_avg"]) > 0.001:
            vel_30 = (current_eps_avg - snap_30d["eps_current_avg"]) / abs(snap_30d["eps_current_avg"]) * 100
            score += 25 if vel_30 > EM_MODERATE_REVISION_PCT else 10 if vel_30 > 0 else 0
        if current_rev_avg and snap_7d and snap_7d.get("rev_current_avg"):
            old_rev = snap_7d["rev_current_avg"]
            if old_rev and abs(old_rev) > 1000:
                rev_vel = (current_rev_avg - old_rev) / abs(old_rev) * 100
                result["hist_rev_velocity"] = round(rev_vel, 3)
                if rev_vel > 2: score += 15
        result["hist_score"] = round(min(100, max(0, score)), 1)
    except Exception as e: logger.debug(f"Historical velocity failed for {symbol}: {e}")
    return result

def _composite_score(velocity, rev_velocity, acceleration, surprise, dispersion, cross_sect, hist_velocity):
    effective_eps = max(velocity.get("velocity_score", 0), hist_velocity.get("hist_score", 0))
    components = [
        (effective_eps, EM_REVISION_VELOCITY_WEIGHT), (rev_velocity.get("rev_velocity_score", 0), EM_REVENUE_VELOCITY_WEIGHT),
        (acceleration.get("acceleration_score", 0), EM_ACCELERATION_WEIGHT), (surprise.get("surprise_score", 0), EM_SURPRISE_MOMENTUM_WEIGHT),
        (dispersion.get("dispersion_score", 50), EM_DISPERSION_WEIGHT), (cross_sect.get("sector_rank_score", 50), EM_CROSS_SECTIONAL_WEIGHT)]
    ws = sum(w for _, w in components)
    return round(sum(s * w for s, w in components) / ws if ws else 0, 1)

def _store_snapshot(symbol, data):
    today = date.today().isoformat()
    eps_avg = eps_high = eps_low = num_analysts = rev_avg = None
    for src, keys in [(data.get("earnings_estimate", {}), ["0q", "+1q", "0y", "+1y"])]:
        for k in keys:
            if k in src:
                eps_avg, eps_high, eps_low, num_analysts = src[k].get("avg"), src[k].get("high"), src[k].get("low"), src[k].get("num_analysts")
                break
        if eps_avg is None:
            for _, v in src.items(): eps_avg, eps_high, eps_low, num_analysts = v.get("avg"), v.get("high"), v.get("low"), v.get("num_analysts"); break
    re = data.get("revenue_estimate", {})
    for k in ["0q", "+1q", "0y", "+1y"]:
        if k in re: rev_avg = re[k].get("avg"); break
    if rev_avg is None:
        for _, v in re.items(): rev_avg = v.get("avg"); break
    if eps_avg is None and rev_avg is None: return eps_avg, rev_avg
    upsert_many("estimate_snapshots",
        ["symbol", "date", "eps_current_avg", "eps_current_high", "eps_current_low", "rev_current_avg", "num_analysts"],
        [(symbol, today, eps_avg, eps_high, eps_low, rev_avg, num_analysts)])
    return eps_avg, rev_avg

def analyze_symbol(symbol):
    data = _fetch_yf_estimates(symbol)
    has_data = data["eps_trend"] or data["earnings_estimate"] or data["earnings_history"]
    if not has_data:
        data = _fetch_fmp_estimates(symbol)
        has_data = data["earnings_estimate"] or data["earnings_history"]
    if not has_data: return None
    eps_avg, rev_avg = _store_snapshot(symbol, data)
    velocity = _compute_eps_revision_velocity(data["eps_trend"])
    rev_velocity = _compute_revenue_revision_velocity(data["revenue_estimate"])
    acceleration = _compute_revision_acceleration(data["eps_trend"])
    surprise = _compute_surprise_momentum(data["earnings_history"])
    dispersion = _compute_dispersion_change(data["earnings_estimate"])
    hist_velocity = _compute_historical_velocity(symbol, eps_avg, rev_avg)
    cross_sect = _compute_cross_sectional_rank(symbol, velocity.get("velocity_score", 0))
    em_score = _composite_score(velocity, rev_velocity, acceleration, surprise, dispersion, cross_sect, hist_velocity)
    return {"symbol": symbol, "em_score": em_score,
        "eps_velocity_7d": velocity.get("velocity_7d"), "eps_velocity_30d": velocity.get("velocity_30d"),
        "eps_velocity_90d": velocity.get("velocity_90d"), "velocity_score": velocity.get("velocity_score", 0),
        "rev_velocity_score": rev_velocity.get("rev_velocity_score", 0),
        "acceleration": acceleration.get("acceleration"), "acceleration_score": acceleration.get("acceleration_score", 0),
        "beat_streak": surprise.get("beat_streak", 0), "miss_streak": surprise.get("miss_streak", 0),
        "avg_surprise_pct": surprise.get("avg_surprise_pct", 0), "surprise_score": surprise.get("surprise_score", 0),
        "dispersion_pct": dispersion.get("dispersion_pct"), "dispersion_score": dispersion.get("dispersion_score", 50),
        "sector_rank_pct": cross_sect.get("sector_rank_pct"), "sector_rank_score": cross_sect.get("sector_rank_score", 50),
        "hist_eps_velocity": hist_velocity.get("hist_eps_velocity"), "hist_rev_velocity": hist_velocity.get("hist_rev_velocity"),
        "hist_score": hist_velocity.get("hist_score", 0)}

def run(symbols=None):
    print("\n" + "=" * 60 + "\n  ESTIMATE REVISION MOMENTUM\n" + "=" * 60)
    init_db()
    if symbols is None:
        rows = query("SELECT symbol FROM stock_universe WHERE asset_class = 'stock'")
        symbols = [r["symbol"] for r in rows]
    if not symbols: print("  No symbols in universe."); return
    print(f"  Analyzing {len(symbols)} symbols...")
    today = date.today().isoformat(); results, errors, no_data = [], 0, 0
    for i, symbol in enumerate(symbols):
        if i > 0 and i % 100 == 0: print(f"    Progress: {i}/{len(symbols)} ({len(results)} scored, {no_data} no data)")
        try:
            result = analyze_symbol(symbol)
            if result is None: no_data += 1; continue
            r = result
            results.append((r["symbol"], today, r["em_score"], r["eps_velocity_7d"], r["eps_velocity_30d"],
                r["eps_velocity_90d"], r["velocity_score"], r["rev_velocity_score"], r["acceleration"],
                r["acceleration_score"], r["beat_streak"], r["miss_streak"], r["avg_surprise_pct"],
                r["surprise_score"], r["dispersion_pct"], r["dispersion_score"], r["sector_rank_pct"],
                r["sector_rank_score"], r["hist_eps_velocity"], r["hist_rev_velocity"], r["hist_score"]))
            if i % 5 == 0: time.sleep(0.3)
        except Exception as e:
            errors += 1
            if errors <= 5: logger.warning(f"  Error analyzing {symbol}: {e}")
    if results:
        upsert_many("estimate_momentum_signals",
            ["symbol", "date", "em_score", "eps_velocity_7d", "eps_velocity_30d", "eps_velocity_90d",
             "velocity_score", "rev_velocity_score", "acceleration", "acceleration_score",
             "beat_streak", "miss_streak", "avg_surprise_pct", "surprise_score",
             "dispersion_pct", "dispersion_score", "sector_rank_pct", "sector_rank_score",
             "hist_eps_velocity", "hist_rev_velocity", "hist_score"], results)
    scores = [r[2] for r in results if r[2] is not None]
    print(f"\n  Results: {len(results)} symbols scored, {no_data} no data, {errors} errors")
    if scores:
        strong, moderate, weak = sum(1 for s in scores if s >= 70), sum(1 for s in scores if 50 <= s < 70), sum(1 for s in scores if s < 50)
        print(f"  Score distribution: avg={np.mean(scores):.1f}, median={np.median(scores):.1f}, max={max(scores):.1f}")
        print(f"  Strong (>=70): {strong} | Moderate (50-69): {moderate} | Weak (<50): {weak}")
    if results:
        top = sorted(results, key=lambda r: r[2] or 0, reverse=True)[:10]
        print(f"\n  Top 10 estimate momentum:")
        for r in top:
            sym, _, score, v7, *_ = r
            print(f"    {sym:6s} score={score:.0f}  7d={'%+.1f%%' % v7 if v7 else 'n/a'}  beat_streak={r[10]}")
    print("=" * 60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = __import__("argparse").ArgumentParser(description="Estimate Revision Momentum")
    parser.add_argument("--symbols", nargs="+"); parser.add_argument("--test", action="store_true")
    args = parser.parse_args(); init_db()
    if args.test:
        for sym in ["AAPL", "NVDA", "MSFT", "TSLA", "META"]:
            r = analyze_symbol(sym)
            print(f"\n{sym}: {'em=%s v7d=%s beat=%s disp=%s' % (r['em_score'], r['eps_velocity_7d'], r['beat_streak'], r['dispersion_pct']) if r else 'no data'}")
    elif args.symbols: run(args.symbols)
    else: run()
