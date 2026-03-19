"""Crowd Intelligence Engine — scoring, divergence detection, report generation."""
import sys, json, logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import numpy as np

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)

REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "strong_risk_on":  {"smart": 0.30, "institutional": 0.50, "retail_penalty": 0.20},
    "risk_on":         {"smart": 0.35, "institutional": 0.45, "retail_penalty": 0.20},
    "neutral":         {"smart": 0.40, "institutional": 0.40, "retail_penalty": 0.20},
    "risk_off":        {"smart": 0.55, "institutional": 0.35, "retail_penalty": 0.10},
    "strong_risk_off": {"smart": 0.60, "institutional": 0.30, "retail_penalty": 0.10},
}
DEFAULT_REGIME = "neutral"


def normalize_signal_value(value: float, history: list[float]) -> float:
    """Z-score normalize value against rolling history, rescale to [0, 1]."""
    arr = np.array(history, dtype=float)
    if len(arr) < 2:
        return 0.5
    mean = float(np.mean(arr))
    std  = float(np.std(arr))
    if std < 1e-9:
        return 0.5
    z = (value - mean) / std
    z_clipped = float(np.clip(z, -3.0, 3.0)) / 3.0
    return float((z_clipped + 1.0) / 2.0)


def apply_decay(signal: Signal) -> float:
    """Return exponential decay weight for signal given its age."""
    return signal.decay_weight


def score_layer(signals: list[Signal], layer_type: str) -> Optional[float]:
    """Combine signals within a layer using IC-weighted, decay-adjusted average.

    For 'retail' layer: values are inverted (1 - normalized) — contrarian.
    Returns None if no signals available.
    """
    if not signals:
        return None
    total_weight = sum(abs(s.ic) * s.decay_weight for s in signals)
    if total_weight < 1e-12:
        return None
    score = 0.0
    for s in signals:
        w = abs(s.ic) * s.decay_weight / total_weight
        value = (1.0 - s.normalized) if layer_type == "retail" else s.normalized
        score += w * value
    return float(np.clip(score, 0.0, 1.0))


def compute_conviction(
    retail: float,
    institutional: float,
    smart: float,
    regime: str = DEFAULT_REGIME,
) -> float:
    """Compute final conviction score [0-100].

    retail is a crowding score — higher retail = more penalty.
    Alignment multiplier: max disagreement → score = 0.
    """
    weights = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS[DEFAULT_REGIME])
    raw = (
        weights["smart"]          * smart
      + weights["institutional"]  * institutional
      - weights["retail_penalty"] * retail
    )
    aligned_retail = 1.0 - retail
    std = float(np.std([smart, institutional, aligned_retail]))
    alignment = max(0.0, 1.0 - (std / 0.577))
    return float(np.clip(raw * alignment * 100.0, 0.0, 100.0))


def run_divergence_detector(
    retail_score: float,
    institutional_score: float,
    smart_score: float,
    short_dtc: Optional[float],
    has_catalyst: bool,
    insider_cluster: bool = False,
    unusual_calls: bool = False,
) -> Optional[str]:
    """Classify divergence signal type. Priority order matters — most specific first."""
    if retail_score < 20 and insider_cluster and unusual_calls:
        return "HIDDEN_GEM"
    if short_dtc is not None and short_dtc > 10 and institutional_score > 55 and has_catalyst:
        return "SHORT_SQUEEZE"
    if retail_score > 70 and institutional_score < 40 and smart_score < 35:
        return "DISTRIBUTION"
    if retail_score > 75 and (institutional_score < 45 or smart_score < 35):
        return "CROWDED_FADE"
    if retail_score < 30 and institutional_score > 60 and smart_score > 65:
        return "CONTRARIAN_BUY"
    if institutional_score > 65 and smart_score > 60 and retail_score < 40:
        return "STEALTH_ACCUM"
    return None


def detect_regime() -> str:
    """Fetch current macro regime from DB or return DEFAULT_REGIME."""
    try:
        from tools.db import query
        rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
        if rows and rows[0].get("regime") in REGIME_WEIGHTS:
            return rows[0]["regime"]
    except Exception:
        pass
    return DEFAULT_REGIME


# ── RSI helper ─────────────────────────────────────────────────────────────

def _rsi(close: "pd.Series", period: int = 14) -> "pd.Series":
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.where(loss > 1e-10)
    return 100 - (100 / (1 + rs))


def _earnings_within_days(ticker: str, days: int = 21) -> bool:
    """Check if ticker has earnings within next N days using DB calendar."""
    try:
        from tools.db import query
        import datetime as _dt
        today = _dt.date.today().isoformat()
        future = (_dt.date.today() + _dt.timedelta(days=days)).isoformat()
        rows = query(
            "SELECT 1 FROM earnings_calendar WHERE symbol=? AND date BETWEEN ? AND ? LIMIT 1",
            [ticker, today, future]
        )
        return bool(rows)
    except Exception:
        return False


# ── Confirmation gate ──────────────────────────────────────────────────────

def run_confirmation_gate(ticker: str, signal_type: str) -> bool:
    """Price/volume confirmation gate using yfinance.

    Bullish signals require: above 50-day MA, volume expansion, RSI < 72.
    Bearish signals require: below 20-day MA.
    SHORT_SQUEEZE requires: catalyst within 21 days + above 20-day MA.
    """
    try:
        import yfinance as yf
        df = yf.download(ticker, period="3mo", progress=False, auto_adjust=True)
        if df.empty or len(df) < 50:
            return False

        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze()

        if signal_type in ("CONTRARIAN_BUY", "HIDDEN_GEM", "STEALTH_ACCUM"):
            above_50ma  = bool(close.iloc[-1] > close.rolling(50).mean().iloc[-1])
            vol_expand  = bool(volume.iloc[-5:].mean() > volume.iloc[-20:].mean())
            rsi_val = _rsi(close, 14).iloc[-1]
            rsi_not_ob = bool(not np.isnan(float(rsi_val)) and float(rsi_val) < 72)
            return above_50ma and vol_expand and rsi_not_ob

        if signal_type in ("DISTRIBUTION", "CROWDED_FADE"):
            return bool(close.iloc[-1] < close.rolling(20).mean().iloc[-1])

        if signal_type == "SHORT_SQUEEZE":
            has_catalyst = _earnings_within_days(ticker, days=21)
            above_20ma   = bool(close.iloc[-1] > close.rolling(20).mean().iloc[-1])
            return has_catalyst and above_20ma

        return True
    except Exception as e:
        logger.debug(f"Confirmation gate {ticker} failed: {e}")
        return False


# ── Sector crowding ────────────────────────────────────────────────────────

def _classify_sector_crowding(score: float) -> str:
    if score >= 70:  return "CROWDED_LONG"
    if score <= 20:  return "CROWDED_SHORT"
    if score <= 30:  return "UNDEROWNED"
    return "NEUTRAL"


# ── DB write ───────────────────────────────────────────────────────────────

def write_to_db(results: list[dict]) -> None:
    """Write crowd intelligence results to SQLite. No-op if DB unavailable."""
    if not results:
        return
    try:
        from tools.db import get_conn
        conn = get_conn()
        cur  = conn.cursor()
        for r in results:
            cur.execute("""
                INSERT OR REPLACE INTO crowd_intelligence
                (date, ticker, scope, sector,
                 retail_crowding_score, institutional_score, smart_money_score, conviction_score,
                 divergence_type, divergence_strength, confirmation_gate_passed,
                 retail_signals, institutional_signals, smart_money_signals,
                 macro_regime, narrative, signals_available, signals_total)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r.get("date"), r.get("ticker"), r.get("scope", "ticker"), r.get("sector"),
                r.get("retail"), r.get("institutional"), r.get("smart"), r.get("conviction"),
                r.get("divergence_type"), r.get("divergence_strength"), r.get("gate_passed"),
                json.dumps(r.get("retail_signals", [])),
                json.dumps(r.get("institutional_signals", [])),
                json.dumps(r.get("smart_signals", [])),
                r.get("regime"), r.get("narrative"),
                r.get("signals_available", 0), r.get("signals_total", 13),
            ))
        conn.commit()
        conn.close()
        logger.info(f"Wrote {len(results)} crowd intelligence rows to DB")
    except Exception as e:
        logger.warning(f"write_to_db failed: {e}")


# ── Report generation ──────────────────────────────────────────────────────

def generate_report(results: list[dict], mode: str = "full") -> str:
    """Generate formatted crowd intelligence report string."""
    today = date.today().isoformat()
    macro_rows  = [r for r in results if r.get("scope") == "macro"]
    sector_rows = sorted([r for r in results if r.get("scope") == "sector"],
                         key=lambda x: x.get("conviction", 0), reverse=True)
    divergence  = sorted([r for r in results if r.get("divergence_type") and r.get("gate_passed")],
                         key=lambda x: x.get("divergence_strength", 0), reverse=True)
    conviction  = sorted([r for r in results if r.get("scope") == "ticker" and not r.get("divergence_type")],
                         key=lambda x: x.get("conviction", 0), reverse=True)

    regime      = results[0].get("regime", "neutral") if results else "neutral"
    n_available = results[0].get("signals_available", 0) if results else 0
    n_total     = results[0].get("signals_total", 13) if results else 13

    lines = [
        "═" * 67,
        "  CROWD INTELLIGENCE REPORT",
        f"  Date: {today}  |  Regime: {regime}",
        f"  Signals available: {n_available}/{n_total}",
        "  Sources: Reddit/Alternative.me/AAII/CFTC/FINRA/SEC/yfinance/Polymarket",
        "═" * 67,
    ]

    if mode in ("full", "macro"):
        lines.append("\n[1] MACRO POSITIONING MAP")
        for m in macro_rows[:6]:
            lines.append(f"    {m.get('narrative', '')}")

    if mode in ("full", "sector"):
        lines.append("\n[2] SECTOR CROWDING MAP")
        crowded = [r for r in sector_rows if r.get("conviction", 50) >= 70]
        neutral = [r for r in sector_rows if 30 <= r.get("conviction", 50) < 70]
        under   = [r for r in sector_rows if r.get("conviction", 50) < 30]
        if crowded:
            names = ", ".join(f"{r['sector']} [{r['conviction']:.0f}]" for r in crowded)
            lines.append(f"    CROWDED LONG:   {names}")
        if neutral:
            names = ", ".join(f"{r['sector']} [{r['conviction']:.0f}]" for r in neutral)
            lines.append(f"    NEUTRAL:        {names}")
        if under:
            names = ", ".join(f"{r['sector']} [{r['conviction']:.0f}]" for r in under)
            lines.append(f"    UNDEROWNED:     {names}")

    if mode in ("full", "divergence-only", "divergence"):
        lines.append("\n[3] TOP 10 DIVERGENCE ALERTS  (confirmation gate passed)")
        if divergence:
            lines.append(f"    {'Ticker':<8} {'Retail':>6} {'Inst':>6} {'Smart':>6}  {'Signal':<20} {'Horizon'}")
            lines.append(f"    {'-'*8} {'-'*6} {'-'*6} {'-'*6}  {'-'*20} {'-'*10}")
            for r in divergence[:10]:
                star = " ★★" if r["divergence_type"] == "HIDDEN_GEM" else (" ★" if r["divergence_type"] in ("CONTRARIAN_BUY","STEALTH_ACCUM") else "")
                lines.append(
                    f"    {r['ticker']:<8} {r.get('retail',0):>6.0f} {r.get('institutional',0):>6.0f} "
                    f"{r.get('smart',0):>6.0f}  {r['divergence_type'] + star:<20} {r.get('horizon','')}"
                )
        else:
            lines.append("    No divergence signals passing confirmation gate today.")

    if mode in ("full", "conviction"):
        lines.append("\n[4] TOP 10 CONVICTION SCORES  (all layers aligned)")
        for r in conviction[:10]:
            lines.append(
                f"    {r['ticker']:<8} {r.get('conviction',0):>4.0f}  {r.get('narrative','')}"
            )

    lines.append("")
    return "\n".join(lines)


# ── Horizon lookup ─────────────────────────────────────────────────────────

DIVERGENCE_HORIZONS = {
    "DISTRIBUTION":   "Reduce 2-4w",
    "CONTRARIAN_BUY": "60-180d",
    "HIDDEN_GEM":     "90-180d",
    "SHORT_SQUEEZE":  "5-15d",
    "CROWDED_FADE":   "Fade 1-3w",
    "STEALTH_ACCUM":  "90-180d",
}


# ── Main pipeline entry point ──────────────────────────────────────────────

def run_crowd_intelligence(
    universe: list[str] | None = None,
    tickers: list[str] | None = None,
    mode: str = "full",
    write_db: bool = True,
    sector: str | None = None,
) -> list[dict]:
    """Full crowd intelligence run. Called by daily_pipeline.py and crowd_report.py.

    Args:
        universe: full stock universe (903 symbols). If None, fetches from DB.
        tickers:  subset to analyze. If None, uses full universe.
        mode:     'full' | 'divergence-only' | 'conviction' | 'sector'
        write_db: persist results to SQLite
        sector:   filter to specific sector if provided

    Returns:
        list of result dicts (also written to DB if write_db=True)
    """
    from tools.crowd_retail import fetch_all_retail
    from tools.crowd_institutional import fetch_all_institutional
    from tools.crowd_smart import fetch_all_smart

    # Resolve universe
    if universe is None:
        try:
            from tools.db import query
            _universe_rows = query("SELECT symbol, sector FROM stock_universe ORDER BY market_cap DESC LIMIT 903")
            universe = [r["symbol"] for r in _universe_rows]
            _sector_map: dict = {r["symbol"]: r["sector"] for r in _universe_rows}
        except Exception:
            universe = []
            _sector_map = {}
    else:
        _sector_map = {}

    scan_tickers = tickers or universe
    if sector:
        try:
            from tools.db import query
            rows = query("SELECT symbol FROM stock_universe WHERE sector=?", [sector])
            scan_tickers = [r["symbol"] for r in rows]
        except Exception:
            pass

    today   = date.today().isoformat()
    regime  = detect_regime()
    results: list[dict] = []

    logger.info(f"Crowd intelligence run: {len(scan_tickers)} tickers, regime={regime}")

    # ── Fetch all layers ──────────────────────────────────────────────────
    retail_sigs = fetch_all_retail(scan_tickers)
    inst_sigs   = fetch_all_institutional(scan_tickers)
    smart_sigs  = fetch_all_smart(scan_tickers)

    # ── Macro-level row ───────────────────────────────────────────────────
    market_retail = [s for s in retail_sigs if not s.name.startswith("reddit_") and not s.name.startswith("gtrends_")]
    market_inst   = [s for s in inst_sigs   if "_flow_" in s.name or "cot" in s.name or "ats" in s.name or "margin" in s.name]
    market_smart  = [s for s in smart_sigs  if "polymarket" in s.name]

    macro_retail = score_layer(market_retail, "retail")
    macro_inst   = score_layer(market_inst, "institutional")
    macro_smart  = score_layer(market_smart, "smart")

    if all(x is not None for x in [macro_retail, macro_inst, macro_smart]):
        macro_conviction = compute_conviction(macro_retail, macro_inst, macro_smart, regime)
        results.append({
            "date": today, "ticker": None, "scope": "macro", "sector": None,
            "retail": macro_retail * 100, "institutional": macro_inst * 100,
            "smart": macro_smart * 100, "conviction": macro_conviction,
            "divergence_type": None, "gate_passed": 1,
            "regime": regime,
            "signals_available": len(retail_sigs) + len(inst_sigs) + len(smart_sigs),
            "signals_total": 13,
            "narrative": f"Macro: Retail crowding {macro_retail*100:.0f}/100 | Inst {macro_inst*100:.0f}/100 | Smart {macro_smart*100:.0f}/100",
        })

    # ── Per-ticker rows ───────────────────────────────────────────────────
    for ticker in scan_tickers[:500]:  # cap at 500 for runtime
        t_retail_all = [s for s in retail_sigs
                        if "fear_greed" in s.name or "aaii" in s.name
                        or f"reddit_mentions_{ticker}" in s.name
                        or f"gtrends_{ticker}" in s.name]

        t_inst  = [s for s in inst_sigs
                   if f"_{ticker}" in s.name or "etf_flow" in s.name
                   or "cot" in s.name or "ats" in s.name or "margin" in s.name]
        t_smart = [s for s in smart_sigs if f"_{ticker}" in s.name or "polymarket" in s.name]

        r_score = score_layer(t_retail_all, "retail")
        i_score = score_layer(t_inst, "institutional")
        s_score = score_layer(t_smart, "smart")

        # Need at least 2 layers to score
        available = sum(x is not None for x in [r_score, i_score, s_score])
        if available < 2:
            continue

        r_score = r_score or 0.5
        i_score = i_score or 0.5
        s_score = s_score or 0.5

        conviction = compute_conviction(r_score, i_score, s_score, regime)

        # Divergence detection
        insider_cluster = any(f"insider_cluster_{ticker}" in s.name and s.ic >= 0.08 for s in t_smart)
        unusual_calls   = any(f"options_skew_{ticker}" in s.name and s.normalized < 0.3 for s in t_smart)
        short_sigs      = [s for s in inst_sigs if f"short_dtc_{ticker}" in s.name]
        short_dtc       = float(short_sigs[0].value) if short_sigs else None
        has_catalyst    = _earnings_within_days(ticker) if short_dtc and short_dtc > 10 else False

        div_type = run_divergence_detector(
            retail_score=r_score * 100,
            institutional_score=i_score * 100,
            smart_score=s_score * 100,
            short_dtc=short_dtc,
            has_catalyst=has_catalyst,
            insider_cluster=insider_cluster,
            unusual_calls=unusual_calls,
        )

        gate_passed = 1
        if div_type:
            gate_passed = int(run_confirmation_gate(ticker, div_type))

        ticker_sector = _sector_map.get(ticker)

        div_strength = abs((r_score - i_score) + (r_score - s_score)) / 2 if div_type else 0.0

        results.append({
            "date": today, "ticker": ticker, "scope": "ticker", "sector": ticker_sector,
            "retail": r_score * 100, "institutional": i_score * 100,
            "smart": s_score * 100, "conviction": conviction,
            "divergence_type": div_type,
            "divergence_strength": round(div_strength, 3),
            "gate_passed": gate_passed,
            "regime": regime,
            "horizon": DIVERGENCE_HORIZONS.get(div_type, "") if div_type else "",
            "signals_available": available,
            "signals_total": 3,
            "narrative": f"Inst:{i_score*100:.0f} Smart:{s_score*100:.0f} Retail:{r_score*100:.0f}",
            "retail_signals": [s.name for s in t_retail_all],
            "institutional_signals": [s.name for s in t_inst],
            "smart_signals": [s.name for s in t_smart],
        })

    if write_db:
        write_to_db(results)

    return results
