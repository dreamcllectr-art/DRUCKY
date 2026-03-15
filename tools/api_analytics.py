"""Analytics routes — discover, performance, thesis-lab, health."""

from fastapi import APIRouter
from tools.db import query

router = APIRouter()


def safe_query(sql, params=None, default=None):
    """Query that returns default instead of raising on missing table."""
    try:
        return query(sql, params)
    except Exception:
        return default if default is not None else []


# ═══════════════════════════════════════════════════════════════════════
# THESIS LAB
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/thesis/funnel")
def thesis_funnel():
    total = query("SELECT COUNT(DISTINCT symbol) as n FROM stock_universe")
    gated = query("SELECT COUNT(DISTINCT symbol) as n FROM technical_scores WHERE date = (SELECT MAX(date) FROM technical_scores) AND total_score >= 35")
    scored = query("SELECT COUNT(DISTINCT symbol) as n FROM convergence_signals WHERE date = (SELECT MAX(date) FROM convergence_signals)")
    high = query("SELECT COUNT(DISTINCT symbol) as n FROM convergence_signals WHERE date = (SELECT MAX(date) FROM convergence_signals) AND conviction_level = 'HIGH'")
    return {
        "universe": total[0]["n"] if total else 0,
        "gated": gated[0]["n"] if gated else 0,
        "scored": scored[0]["n"] if scored else 0,
        "high_conviction": high[0]["n"] if high else 0,
    }


@router.get("/api/thesis/models")
def thesis_models():
    regime = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    return {"models": [], "regime": regime[0]["regime"] if regime else "neutral"}


@router.get("/api/thesis/checklist/{symbol}")
def thesis_checklist(symbol: str):
    conv = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    da = query("SELECT * FROM devils_advocate WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    forensic = query("SELECT * FROM forensic_alerts WHERE symbol = ? ORDER BY date DESC LIMIT 3", [symbol])
    conflicts = query("SELECT * FROM signal_conflicts WHERE symbol = ? ORDER BY date DESC LIMIT 5", [symbol])
    return {
        "symbol": symbol,
        "convergence": conv[0] if conv else {},
        "devils_advocate": da[0] if da else {},
        "forensic_alerts": forensic,
        "signal_conflicts": conflicts,
    }


# ═══════════════════════════════════════════════════════════════════════
# DISCOVERY — unified enriched view for progressive filtering
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/discover")
def discover():
    """Unified discovery endpoint: convergence + sector + conflicts + special signals.
    Uses parallel queries (SQLite WAL mode) with graceful degradation per enrichment source."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Base query — always required
    stocks = query("""
        SELECT c.*, su.name as company_name, su.sector, su.industry
        FROM convergence_signals c
        LEFT JOIN stock_universe su ON c.symbol = su.symbol
        WHERE c.date = (SELECT MAX(date) FROM convergence_signals)
        ORDER BY c.convergence_score DESC
    """)
    if not stocks:
        return []

    # Enrichment queries — each can fail independently
    def q_conflicts():
        return query("""
            SELECT symbol, COUNT(*) as conflict_count,
                   MAX(severity) as max_severity,
                   GROUP_CONCAT(conflict_type, ', ') as conflict_types
            FROM signal_conflicts
            WHERE date = (SELECT MAX(date) FROM signal_conflicts)
            GROUP BY symbol
        """)

    def q_fat_pitches():
        return query("""
            SELECT symbol, fat_pitch_score, fat_pitch_count, fat_pitch_conditions, gap_type
            FROM consensus_blindspot_signals
            WHERE date = (SELECT MAX(date) FROM consensus_blindspot_signals)
            AND fat_pitch_count >= 3
        """)

    def q_insider():
        return query("""
            SELECT symbol, insider_score, cluster_count, narrative as insider_narrative
            FROM insider_signals
            WHERE date = (SELECT MAX(date) FROM insider_signals)
            AND cluster_buy = 1
        """)

    def q_ma():
        return query("""
            SELECT symbol, ma_score, deal_stage, acquirer_name, best_headline
            FROM ma_signals
            WHERE date = (SELECT MAX(date) FROM ma_signals)
            AND ma_score >= 50
        """)

    def q_options():
        return query("""
            SELECT symbol, options_score, unusual_activity_count, unusual_direction_bias, iv_rank
            FROM options_intel
            WHERE date = (SELECT MAX(date) FROM options_intel)
            AND unusual_activity_count >= 2
        """)

    # Run enrichment queries in parallel — each degrades gracefully to empty
    enrichment = {"conflicts": [], "fat_pitches": [], "insider": [], "ma": [], "options": []}
    labels = ["conflicts", "fat_pitches", "insider", "ma", "options"]
    fns = [q_conflicts, q_fat_pitches, q_insider, q_ma, q_options]

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fn): label for fn, label in zip(fns, labels)}
        for fut in as_completed(futures):
            label = futures[fut]
            try:
                enrichment[label] = fut.result()
            except Exception:
                enrichment[label] = []  # Degrade gracefully

    # Build lookup dicts
    conflict_map = {r["symbol"]: r for r in enrichment["conflicts"]}
    fp_map = {r["symbol"]: r for r in enrichment["fat_pitches"]}
    insider_map = {r["symbol"]: r for r in enrichment["insider"]}
    ma_map = {r["symbol"]: r for r in enrichment["ma"]}
    opts_map = {r["symbol"]: r for r in enrichment["options"]}

    # Enrich each stock
    for s in stocks:
        sym = s["symbol"]
        c = conflict_map.get(sym)
        s["conflict_count"] = c["conflict_count"] if c else 0
        s["max_conflict_severity"] = c["max_severity"] if c else None
        fp = fp_map.get(sym)
        s["is_fat_pitch"] = 1 if fp else 0
        s["fat_pitch_score"] = fp["fat_pitch_score"] if fp else None
        s["fat_pitch_conditions"] = fp["fat_pitch_conditions"] if fp else None
        ins = insider_map.get(sym)
        s["has_insider_cluster"] = 1 if ins else 0
        s["insider_score"] = ins["insider_score"] if ins else None
        ma = ma_map.get(sym)
        s["is_ma_target"] = 1 if ma else 0
        s["ma_target_score"] = ma["ma_score"] if ma else None
        s["deal_stage"] = ma["deal_stage"] if ma else None
        opt = opts_map.get(sym)
        s["has_unusual_options"] = 1 if opt else 0
        s["options_score"] = opt["options_score"] if opt else None
        s["unusual_options_count"] = opt["unusual_activity_count"] if opt else 0
        s["unusual_options_bias"] = opt["unusual_direction_bias"] if opt else None
    return stocks


@router.get("/api/discover/sectors")
def discover_sectors():
    """Get all sectors with stock counts."""
    return query("""
        SELECT sector, COUNT(*) as count
        FROM stock_universe
        WHERE sector IS NOT NULL
        GROUP BY sector
        ORDER BY count DESC
    """)


# ═══════════════════════════════════════════════════════════════════════
# PERFORMANCE / DATA MOAT — Signal accuracy & adaptive weight tracking
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/performance/summary")
def performance_summary():
    """Overall signal accuracy, conviction breakdown, data sufficiency."""
    from tools.config import WO_MIN_TOTAL_SIGNALS, WO_MIN_DAYS_RUNNING, WO_MIN_OBSERVATIONS

    # Total signals
    total = query("SELECT COUNT(*) as cnt FROM signal_outcomes")
    total_signals = total[0]["cnt"] if total else 0

    # Resolved by window
    windows = {}
    for days in [1, 5, 10, 20, 30, 60, 90]:
        cnt = query(f"SELECT COUNT(*) as cnt FROM signal_outcomes WHERE return_{days}d IS NOT NULL")
        windows[f"{days}d"] = cnt[0]["cnt"] if cnt else 0

    # Days running
    first = query("SELECT MIN(signal_date) as d FROM signal_outcomes")
    first_date = first[0]["d"] if first and first[0]["d"] else None
    from datetime import date as dt, datetime
    days_running = (dt.today() - datetime.strptime(first_date, "%Y-%m-%d").date()).days if first_date else 0

    # Win rate by conviction level for each window
    conviction_stats = []
    for level in ["HIGH", "NOTABLE"]:
        level_data = {"level": level}
        for days in [5, 10, 20, 30]:
            stats = query(
                f"""SELECT COUNT(*) as total,
                           SUM(CASE WHEN return_{days}d > 0 THEN 1 ELSE 0 END) as wins,
                           AVG(return_{days}d) as avg_ret
                    FROM signal_outcomes
                    WHERE conviction_level = ? AND return_{days}d IS NOT NULL""",
                [level],
            )
            if stats and stats[0]["total"] > 0:
                s = stats[0]
                level_data[f"count_{days}d"] = s["total"]
                level_data[f"win_rate_{days}d"] = round((s["wins"] / s["total"]) * 100, 1)
                level_data[f"avg_return_{days}d"] = round(s["avg_ret"] or 0, 2)
        conviction_stats.append(level_data)

    # Data sufficiency
    data_sufficient = (
        total_signals >= WO_MIN_TOTAL_SIGNALS
        and days_running >= WO_MIN_DAYS_RUNNING
    )

    # Latest optimizer action
    latest_log = query(
        "SELECT date, action, details FROM weight_optimizer_log ORDER BY date DESC LIMIT 1"
    )

    return {
        "total_signals": total_signals,
        "resolved_by_window": windows,
        "days_running": days_running,
        "first_signal_date": first_date,
        "by_conviction": conviction_stats,
        "data_sufficient": data_sufficient,
        "latest_optimizer": latest_log[0] if latest_log else None,
    }


@router.get("/api/performance/modules")
def performance_modules(regime: str = "all", sector: str = "all"):
    """Module leaderboard with accuracy, Sharpe, and confidence intervals."""
    rows = query(
        """SELECT * FROM module_performance
           WHERE report_date = (SELECT MAX(report_date) FROM module_performance)
             AND regime = ? AND sector = ?
           ORDER BY win_rate DESC""",
        [regime, sector],
    )
    if not rows:
        # Try 'all' fallback
        rows = query(
            """SELECT * FROM module_performance
               WHERE report_date = (SELECT MAX(report_date) FROM module_performance)
                 AND regime = 'all' AND sector = 'all'
               ORDER BY win_rate DESC"""
        )

    # Add static weight for comparison
    from tools.config import CONVERGENCE_WEIGHTS
    for row in rows:
        row["static_weight"] = CONVERGENCE_WEIGHTS.get(row["module_name"], 0)

    # Get adaptive weight if available
    adaptive = query(
        """SELECT module_name, weight FROM weight_history
           WHERE regime = ? AND date = (SELECT MAX(date) FROM weight_history WHERE regime = ?)""",
        [regime if regime != "all" else "neutral", regime if regime != "all" else "neutral"],
    )
    adaptive_map = {r["module_name"]: r["weight"] for r in adaptive} if adaptive else {}

    for row in rows:
        row["adaptive_weight"] = adaptive_map.get(row["module_name"])

    return rows


@router.get("/api/performance/track-record")
def performance_track_record():
    """Monthly time series of signal accuracy."""
    rows = query(
        """SELECT
             strftime('%Y-%m', signal_date) as month,
             COUNT(*) as total_signals,
             SUM(CASE WHEN return_5d > 0 THEN 1 ELSE 0 END) as wins_5d,
             SUM(CASE WHEN return_20d > 0 THEN 1 ELSE 0 END) as wins_20d,
             SUM(CASE WHEN return_30d > 0 THEN 1 ELSE 0 END) as wins_30d,
             AVG(return_5d) as avg_5d,
             AVG(return_20d) as avg_20d,
             AVG(return_30d) as avg_30d,
             SUM(CASE WHEN return_5d IS NOT NULL THEN 1 ELSE 0 END) as resolved_5d,
             SUM(CASE WHEN return_20d IS NOT NULL THEN 1 ELSE 0 END) as resolved_20d,
             SUM(CASE WHEN return_30d IS NOT NULL THEN 1 ELSE 0 END) as resolved_30d
           FROM signal_outcomes
           GROUP BY month
           ORDER BY month"""
    )

    # Compute running win rate
    cumulative_wins = 0
    cumulative_total = 0
    for row in rows:
        resolved = row["resolved_5d"] or row["resolved_20d"] or row["resolved_30d"] or 0
        wins = row["wins_5d"] or row["wins_20d"] or row["wins_30d"] or 0
        cumulative_total += resolved
        cumulative_wins += wins
        row["cumulative_win_rate"] = round(
            (cumulative_wins / cumulative_total * 100) if cumulative_total else 0, 1
        )
        row["cumulative_total"] = cumulative_total

    return rows


@router.get("/api/performance/weight-history")
def performance_weight_history(regime: str = "all"):
    """Weight evolution audit trail."""
    target_regime = regime if regime != "all" else "neutral"
    rows = query(
        """SELECT date, module_name, weight, prior_weight, reason
           FROM weight_history
           WHERE regime = ?
           ORDER BY date DESC, weight DESC
           LIMIT 500""",
        [target_regime],
    )

    # Group by date
    from collections import defaultdict
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)

    result = []
    for dt, modules in sorted(by_date.items(), reverse=True):
        result.append({
            "date": dt,
            "modules": modules,
            "total_delta": round(sum(abs((m["weight"] or 0) - (m["prior_weight"] or 0)) for m in modules), 4),
        })

    return result


# ═══════════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/health")
def health():
    """System health check."""
    tables = query("SELECT name FROM sqlite_master WHERE type='table'")
    latest = query("SELECT MAX(date) as d FROM convergence_signals")
    return {
        "status": "ok",
        "tables": len(tables),
        "latest_data": latest[0]["d"] if latest else None,
    }


# ═══════════════════════════════════════════════════════════════════════
# CROSS-ASSET SCREENER
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/alpha/cross-asset")
def cross_asset_opportunities(limit: int = 50, asset_class: str = None, min_score: float = 60.0):
    """Top cross-asset opportunities (stocks + commodities + crypto)."""
    sql = """
        SELECT symbol, date, asset_class, sector, opportunity_score,
               technical_score, fundamental_score,
               momentum_5d, momentum_20d, momentum_60d,
               regime_fit_score, relative_value_rank,
               is_fat_pitch, fat_pitch_reason, conviction, details
        FROM cross_asset_opportunities
        WHERE date = (SELECT MAX(date) FROM cross_asset_opportunities)
          AND opportunity_score >= ?
    """
    params = [min_score]
    if asset_class:
        sql += " AND asset_class = ?"
        params.append(asset_class)
    sql += " ORDER BY opportunity_score DESC LIMIT ?"
    params.append(limit)
    rows = safe_query(sql, params)
    fat_pitches = [r for r in rows if r.get("is_fat_pitch")]
    return {
        "date": rows[0]["date"] if rows else None,
        "count": len(rows),
        "fat_pitches": len(fat_pitches),
        "opportunities": rows,
    }


@router.get("/api/alpha/cross-asset/fat-pitches")
def fat_pitches():
    """Only fat-pitch opportunities across all asset classes."""
    rows = safe_query("""
        SELECT symbol, date, asset_class, sector, opportunity_score,
               technical_score, fundamental_score, momentum_20d,
               regime_fit_score, fat_pitch_reason, conviction, details
        FROM cross_asset_opportunities
        WHERE date = (SELECT MAX(date) FROM cross_asset_opportunities)
          AND is_fat_pitch = 1
        ORDER BY opportunity_score DESC
    """)
    return {"count": len(rows), "fat_pitches": rows}


@router.get("/api/alpha/cross-asset/by-class")
def cross_asset_by_class():
    """Aggregated stats per asset class."""
    rows = safe_query("""
        SELECT asset_class,
               COUNT(*) as count,
               AVG(opportunity_score) as avg_score,
               MAX(opportunity_score) as top_score,
               SUM(is_fat_pitch) as fat_pitches
        FROM cross_asset_opportunities
        WHERE date = (SELECT MAX(date) FROM cross_asset_opportunities)
        GROUP BY asset_class
        ORDER BY avg_score DESC
    """)
    return {"breakdown": rows}


# ═══════════════════════════════════════════════════════════════════════
# NARRATIVE ENGINE
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/alpha/narratives")
def narratives(min_strength: float = 0.0):
    """All macro narratives with strength + crowding scores."""
    rows = safe_query("""
        SELECT narrative_id, narrative_name AS narrative, date,
               strength_score, crowding_score, opportunity_score, maturity,
               best_expression AS best_expressions, avoid AS worst_expressions, details
        FROM narrative_signals
        WHERE date = (SELECT MAX(date) FROM narrative_signals)
          AND strength_score >= ?
        ORDER BY strength_score DESC
    """, [min_strength])
    return {
        "date": rows[0]["date"] if rows else None,
        "count": len(rows),
        "narratives": rows,
    }


@router.get("/api/alpha/narratives/{narrative}")
def narrative_detail(narrative: str):
    """Detail for a single narrative including its asset map."""
    signal = safe_query("""
        SELECT narrative_id, narrative_name AS narrative, date,
               strength_score, crowding_score, opportunity_score, maturity,
               best_expression AS best_expressions, avoid AS worst_expressions, details
        FROM narrative_signals
        WHERE narrative_name = ? AND date = (SELECT MAX(date) FROM narrative_signals)
    """, [narrative])

    assets = safe_query("""
        SELECT symbol, asset_class, role AS direction, combined_score AS fit_score
        FROM narrative_asset_map
        WHERE narrative_id = (
            SELECT narrative_id FROM narrative_signals
            WHERE narrative_name = ? AND date = (SELECT MAX(date) FROM narrative_signals)
            LIMIT 1
        ) AND date = (SELECT MAX(date) FROM narrative_asset_map)
        ORDER BY combined_score DESC
        LIMIT 30
    """, [narrative])

    return {
        "narrative": narrative,
        "signal": signal[0] if signal else None,
        "top_assets": assets,
    }


@router.get("/api/alpha/narratives/asset-map")
def narrative_asset_map(symbol: str = None):
    """Which narratives align with a symbol (or all narrative→asset mappings)."""
    if symbol:
        rows = safe_query("""
            SELECT ns.narrative_name AS narrative, nam.role AS direction, nam.combined_score AS fit_score
            FROM narrative_asset_map nam
            JOIN narrative_signals ns ON nam.narrative_id = ns.narrative_id AND nam.date = ns.date
            WHERE nam.symbol = ? AND nam.date = (SELECT MAX(date) FROM narrative_asset_map)
            ORDER BY nam.combined_score DESC
        """, [symbol])
        return {"symbol": symbol, "narratives": rows}
    rows = safe_query("""
        SELECT nam.symbol, ns.narrative_name AS narrative, nam.role AS direction, nam.combined_score AS fit_score
        FROM narrative_asset_map nam
        JOIN narrative_signals ns ON nam.narrative_id = ns.narrative_id AND nam.date = ns.date
        WHERE nam.date = (SELECT MAX(date) FROM narrative_asset_map)
          AND nam.combined_score >= 0.6
        ORDER BY nam.combined_score DESC
        LIMIT 100
    """)
    return {"count": len(rows), "mappings": rows}


# ═══════════════════════════════════════════════════════════════════════
# SIGNAL IC BACKTESTER
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/alpha/ic/summary")
def ic_summary(regime: str = "all", horizon: int = 20):
    """IC summary for all modules at a given regime + horizon."""
    rows = safe_query("""
        SELECT module, regime, horizon_days,
               mean_ic, std_ic, information_ratio,
               ic_positive_pct, n_dates, avg_n_stocks,
               ci_low, ci_high, is_significant, pvalue
        FROM module_ic_summary
        WHERE regime = ? AND horizon_days = ?
        ORDER BY mean_ic DESC
    """, [regime, horizon])
    return {
        "regime": regime,
        "horizon_days": horizon,
        "module_count": len(rows),
        "modules": rows,
    }


@router.get("/api/alpha/ic/module/{module}")
def ic_module_detail(module: str):
    """Full IC breakdown for a single module across all regimes and horizons."""
    rows = safe_query("""
        SELECT regime, horizon_days, mean_ic, std_ic,
               information_ratio, ic_positive_pct, n_dates,
               is_significant, pvalue, ci_low, ci_high
        FROM module_ic_summary
        WHERE module = ?
        ORDER BY regime, horizon_days
    """, [module])
    series = safe_query("""
        SELECT signal_date, ic_value, n_stocks, regime
        FROM signal_ic_results
        WHERE module = ? AND horizon_days = 20
        ORDER BY signal_date DESC
        LIMIT 90
    """, [module])
    return {
        "module": module,
        "summary": rows,
        "ic_series_20d": series,
    }


@router.get("/api/alpha/ic/ranking")
def ic_ranking():
    """Ranked leaderboard: which modules have best IC across mid-term horizons."""
    rows = safe_query("""
        SELECT module,
               AVG(mean_ic) as avg_ic,
               AVG(information_ratio) as avg_ir,
               AVG(CASE WHEN is_significant THEN 1.0 ELSE 0.0 END) as sig_rate,
               MIN(mean_ic) as worst_ic,
               MAX(mean_ic) as best_ic
        FROM module_ic_summary
        WHERE regime = 'all' AND horizon_days IN (5, 10, 20)
        GROUP BY module
        ORDER BY avg_ic DESC
    """)
    return {"modules": rows}


@router.get("/api/alpha/ic/regime-comparison")
def ic_regime_comparison(module: str = None, horizon: int = 20):
    """Compare IC across regimes — shows which modules are regime-sensitive."""
    if module:
        rows = safe_query("""
            SELECT module, regime, mean_ic, information_ratio,
                   is_significant, n_dates
            FROM module_ic_summary
            WHERE module = ? AND horizon_days = ?
            ORDER BY mean_ic DESC
        """, [module, horizon])
    else:
        rows = safe_query("""
            SELECT module, regime, mean_ic, information_ratio,
                   is_significant, n_dates
            FROM module_ic_summary
            WHERE horizon_days = ? AND regime != 'all'
            ORDER BY module, mean_ic DESC
        """, [horizon])
    return {"horizon_days": horizon, "data": rows}
