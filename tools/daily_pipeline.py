"""Daily Pipeline — orchestrates all data fetching, scoring, and signal generation.

Pipeline phases (designed for sequential execution, ~30-45 min total):

  Phase 1:   Data ingestion (universe, prices, fundamentals, macro, news)
  Phase 1.5: Energy data (EIA + infrastructure)
  Phase 2:   Scoring (technical, fundamental, macro regime)
  Phase 2.05: Economic dashboard (FRED indicators + heat index)
  Phase 2.1: TA gate (filter symbols for expensive Phase 2.5+ modules)
  Phase 2.3: Core alpha modules (smart money, variant, worldview, research, alt data)
  Phase 2.5: Extended alpha (sector experts, foreign intel, news displacement)
  Phase 2.55: Estimate revision momentum
  Phase 2.6: AI regulatory intelligence
  Phase 2.7: Deal-based modules (pairs trading, M&A, insider, energy intel)
  Phase 2.75: Pattern & options intelligence
  Phase 2.85: Alt Alpha II (earnings NLP, gov intel, labor, supply chain, digital, pharma)
  Phase 2.9: Consensus blindspots (reads ALL other module outputs)
  Phase 3:   Convergence engine + signal generation
  Phase 3.56: Cross-asset screener (stocks + commodities + crypto fat pitches)
  Phase 3.57: Narrative engine (12 macro narratives)
  Phase 3.58: Signal IC backtester (Spearman IC per module × horizon × regime)
  Phase 3.5: Devil's advocate (bear cases for HIGH conviction)
  Phase 4:   Alerts

Usage:
  python -m tools.daily_pipeline          # run full pipeline locally
  modal run modal_app.py::daily_pipeline  # run on Modal
"""

import logging
import threading
import time
import traceback
from datetime import datetime, date

logger = logging.getLogger(__name__)

# Expected max duration per phase (seconds). Exceeded = SLA warning.
_PHASE_SLA = {
    "Phase 1.2: Price Data": 120,
    "Phase 1.3: Fundamentals (yfinance)": 600,
    "Phase 1.5: News Sentiment (Finnhub)": 400,
    "Phase 1.6: FMP v2 (short interest, analyst, DCF, institutional)": 300,
    "Phase 1.7: Stocktwits Retail Sentiment": 700,
    "Phase 1.14: Alpha Vantage Technical Indicators (batch rotation)": 800,
}

_thread_local = threading.local()


def _get_checkpoint_conn():
    """Per-thread SQLite connection for pipeline checkpoints (local state only)."""
    if not hasattr(_thread_local, 'conn') or _thread_local.conn is None:
        import sqlite3 as _sqlite3, os as _os
        checkpoint_db = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..", ".tmp", "pipeline_checkpoints.db"))
        _os.makedirs(_os.path.dirname(checkpoint_db), exist_ok=True)
        _thread_local.conn = _sqlite3.connect(checkpoint_db, check_same_thread=False)
        _thread_local.conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
                run_date TEXT,
                phase_name TEXT,
                status TEXT,
                duration_seconds REAL,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (run_date, phase_name)
            )
        """)
        _thread_local.conn.commit()
    return _thread_local.conn


def _is_done_today(name: str) -> bool:
    """Return True if this phase already completed successfully today."""
    today = date.today().isoformat()
    conn = _get_checkpoint_conn()
    row = conn.execute(
        "SELECT 1 FROM pipeline_checkpoints WHERE run_date=? AND phase_name=? AND status='completed'",
        (today, name)
    ).fetchone()
    return row is not None


def _save_checkpoint(name: str, status: str, elapsed: float):
    today = date.today().isoformat()
    conn = _get_checkpoint_conn()
    conn.execute(
        "INSERT OR REPLACE INTO pipeline_checkpoints (run_date, phase_name, status, duration_seconds) VALUES (?,?,?,?)",
        (today, name, status, round(elapsed, 2))
    )
    conn.commit()


def _run_phase(name: str, fn, *args, skip_if_done: bool = True, **kwargs):
    """Run a pipeline phase with checkpointing, SLA monitoring, and error handling."""
    # Checkpointing — skip phases already completed today
    if skip_if_done and _is_done_today(name):
        print(f"\n  ⏭  {name} — already completed today, skipping")
        return None

    print(f"\n{'─' * 60}")
    print(f"  ▶ {name}")
    print(f"{'─' * 60}")
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.time() - t0
        # SLA check
        sla = _PHASE_SLA.get(name)
        if sla and elapsed > sla:
            print(f"  ⚠  SLA BREACH: {elapsed:.0f}s (limit {sla}s) — consider optimizing")
        print(f"  ✓ {name} completed in {elapsed:.1f}s")
        _save_checkpoint(name, "completed", elapsed)
        return result
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ✗ {name} FAILED after {elapsed:.1f}s: {e}")
        logger.error(f"{name} failed: {traceback.format_exc()}")
        _save_checkpoint(name, "failed", elapsed)
        return None


def main():
    """Run the full daily pipeline."""
    pipeline_start = time.time()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 60)
    print("  DRUCKENMILLER ALPHA SYSTEM — DAILY PIPELINE")
    print(f"  Started: {now}")
    print("=" * 60)

    # ── Phase 0: Database initialization ──
    from tools.db import init_db
    _run_phase("Phase 0: Database Init", init_db)

    # ── Phase 1: Data Ingestion ──
    from tools.fetch_stock_universe import run as fetch_universe
    _run_phase("Phase 1.1: Stock Universe (S&P 500 + 400)", fetch_universe)

    from tools.fetch_prices import run as fetch_prices
    _run_phase("Phase 1.2: Price Data", fetch_prices)

    from tools.fetch_fundamentals import run as fetch_fundamentals
    _run_phase("Phase 1.3: Fundamentals (yfinance)", fetch_fundamentals)

    from tools.fetch_macro import run as fetch_macro
    _run_phase("Phase 1.4: Macro Indicators (FRED)", fetch_macro)

    from tools.fetch_news_sentiment import run as fetch_news
    _run_phase("Phase 1.5: News Sentiment (Finnhub)", fetch_news)

    # ── Phase 1.6–1.14: Independent fetchers — run in parallel ──
    import concurrent.futures

    # Pre-import all fetcher modules before threading (avoids import-lock issues)
    from tools.fetch_fmp_v2 import run as fetch_fmp_v2
    from tools.fetch_stocktwits import run as fetch_stocktwits
    from tools.fetch_coingecko import run as fetch_coingecko
    from tools.fetch_sec_edgar import run as fetch_edgar
    from tools.fetch_eia_data import run as fetch_eia
    from tools.energy_intel_data import run as fetch_energy_data
    from tools.global_energy_data import run as fetch_global_energy
    from tools.energy_physical_flows import run as fetch_physical_flows
    from tools.fetch_finra_short import run as fetch_finra
    from tools.fetch_usda import run as fetch_usda
    from tools.fetch_nansen import run as fetch_nansen
    from tools.fetch_etherscan import run as fetch_etherscan
    from tools.fetch_epo import run as fetch_epo
    from tools.fetch_alpha_vantage_tech import run as fetch_av_tech

    parallel_phases = [
        ("Phase 1.6: FMP v2 (short interest, analyst, DCF, institutional)", fetch_fmp_v2),
        ("Phase 1.7: Stocktwits Retail Sentiment", fetch_stocktwits),
        ("Phase 1.8: CoinGecko Crypto Data", fetch_coingecko),
        ("Phase 1.9: SEC EDGAR (Form 4 + 13F metadata)", fetch_edgar),
        ("Phase 1.5a: EIA Energy Data", fetch_eia),
        ("Phase 1.5b: Energy Intelligence Data", fetch_energy_data),
        ("Phase 1.5c: Global Energy Markets Data (TTF, curves, spreads)", fetch_global_energy),
        ("Phase 1.5d: Energy Physical Flows (GIE EU Storage, ENTSO-G, CFTC CoT, LNG)", fetch_physical_flows),
        ("Phase 1.10: FINRA Short Interest (semi-monthly)", fetch_finra),
        ("Phase 1.11: USDA Agricultural Data", fetch_usda),
        ("Phase 1.12a: Nansen On-Chain Intelligence (crypto)", fetch_nansen),
        ("Phase 1.12b: Etherscan Ethereum On-Chain", fetch_etherscan),
        ("Phase 1.13: EPO Patent Intelligence (European Patents)", fetch_epo),
        ("Phase 1.14: Alpha Vantage Technical Indicators (batch rotation)", fetch_av_tech),
    ]

    # Filter out phases already done today
    to_run = [(n, f) for n, f in parallel_phases if not _is_done_today(n)]
    already_done = len(parallel_phases) - len(to_run)
    if already_done:
        print(f"\n  ⏭  {already_done} fetch phases already completed today — skipping")

    if to_run:
        print(f"\n  ⚡ Running {len(to_run)} fetch phases in parallel...")
        t_parallel = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(_run_phase, name, fn, skip_if_done=False): name
                       for name, fn in to_run}
            for future in concurrent.futures.as_completed(futures):
                pass  # results already printed inside _run_phase
        print(f"  ⚡ All parallel fetches done in {time.time() - t_parallel:.1f}s")

    # ── Data Freshness Gate ──
    # Validate upstream data before running expensive scoring phases
    from tools.db import query as db_query
    price_rows = db_query("SELECT COUNT(*) as n FROM price_data WHERE date = date('now')")
    price_count = price_rows[0]["n"] if price_rows else 0
    if price_count < 100:
        print(f"\n  ⚠  DATA FRESHNESS WARNING: only {price_count} price rows for today")
        print("     Scoring phases will use prior-day data — results may be stale")
    else:
        print(f"\n  ✓ Data freshness OK: {price_count} price rows for today")

    # ── Phase 1.99: Market Breadth (must run BEFORE technical scoring) ──
    from tools.market_breadth import run as run_breadth
    _run_phase("Phase 1.99: Market Breadth Indicators", run_breadth)

    # ── Phase 2: Scoring ──
    from tools.technical_scoring import run as score_technical
    _run_phase("Phase 2.1: Technical Scoring", score_technical)

    from tools.fundamental_scoring import run as score_fundamental
    _run_phase("Phase 2.2: Fundamental Scoring", score_fundamental)

    from tools.macro_regime import run as score_macro
    _run_phase("Phase 2.3: Macro Regime Scoring", score_macro)

    # ── Phase 2.05: Economic Dashboard ──
    from tools.economic_dashboard import run as run_economic
    _run_phase("Phase 2.05: Economic Dashboard (23 FRED series)", run_economic)

    # ── Phase 2.1: TA Gate ──
    from tools.ta_gate import get_gated_symbols
    gate_result = _run_phase("Phase 2.1: TA Pre-Screening Gate", get_gated_symbols)
    gated_symbols = gate_result.get("full", []) if gate_result else None

    # ── Phase 2.2: New intelligence modules (pre-alpha) ──
    from tools.short_interest_intel import run as run_short_interest
    _run_phase("Phase 2.2: Short Interest Intelligence", run_short_interest)

    from tools.retail_sentiment import run as run_retail_sentiment
    _run_phase("Phase 2.25: Retail Sentiment Intelligence", run_retail_sentiment)

    # ── Phase 2.3: Core Alpha Modules ──
    try:
        from tools.accounting_forensics import run as run_forensics
        _run_phase("Phase 2.3a: Accounting Forensics", run_forensics)
    except ImportError as e:
        print(f"  ✗ Phase 2.3a: Accounting Forensics SKIPPED (ImportError: {e})")

    from tools.filings_13f import run as run_13f
    _run_phase("Phase 2.3b: Smart Money (13F Filings)", run_13f)

    from tools.variant_perception import run as run_variant
    _run_phase("Phase 2.3c: Variant Perception", run_variant, gated_symbols)

    from tools.worldview_model import run as run_worldview
    _run_phase("Phase 2.3d: Worldview Model (macro theses)", run_worldview)

    from tools.research_sources import run as run_research
    _run_phase("Phase 2.3e: Research Sources", run_research)

    from tools.alternative_data import run as run_alt_data
    _run_phase("Phase 2.3f: Alternative Data (satellite + ENSO)", run_alt_data)

    # ── Phase 2.5: Extended Alpha ──
    from tools.sector_experts import run as run_sectors
    _run_phase("Phase 2.5a: Sector Experts (11 domains)", run_sectors)

    from tools.foreign_intel import run as run_foreign
    _run_phase("Phase 2.5b: Foreign Intelligence", run_foreign)

    from tools.news_displacement import run as run_displacement
    _run_phase("Phase 2.5c: News Displacement", run_displacement, gated_symbols)

    # ── Phase 2.55: Estimate Momentum ──
    from tools.estimate_momentum import run as run_em
    _run_phase("Phase 2.55: Estimate Revision Momentum", run_em, gated_symbols)

    # ── Phase 2.6: AI Regulatory ──
    from tools.ai_regulatory import run as run_regulatory
    _run_phase("Phase 2.6: AI Regulatory Intelligence (9 jurisdictions)", run_regulatory)

    # ── Phase 2.7: Deal-Based Modules ──
    from tools.pairs_trading import run as run_pairs
    _run_phase("Phase 2.7a: Pairs Trading", run_pairs)

    from tools.ma_signals import run as run_ma
    _run_phase("Phase 2.7b: M&A Intelligence", run_ma)

    from tools.insider_trading import run as run_insider
    _run_phase("Phase 2.7c: Insider Trading (Form 4)", run_insider)

    from tools.energy_intel import run as run_energy
    _run_phase("Phase 2.7d: Energy Intelligence", run_energy)

    from tools.energy_infrastructure import run as run_energy_infra
    _run_phase("Phase 2.7e: Energy Infrastructure", run_energy_infra)

    from tools.global_energy_markets import run as run_gem
    _run_phase("Phase 2.7f: Global Energy Markets (10-signal: TTF, flows, CoT, storage)", run_gem)

    from tools.energy_stress_test import run as run_stress
    _run_phase("Phase 2.7g: Energy Regime & Stress Test (5 scenarios)", run_stress)

    # ── Phase 2.75: Pattern & Options ──
    from tools.pattern_options import run as run_patterns
    _run_phase("Phase 2.75: Pattern & Options Intelligence", run_patterns, gated_symbols)

    from tools.options_flow_intel import run as run_options_flow
    _run_phase("Phase 2.76: Options Flow Intelligence", run_options_flow)

    # ── Phase 2.8: Prediction Markets ──
    from tools.prediction_markets import run as run_pm
    _run_phase("Phase 2.8a: Prediction Markets (Polymarket)", run_pm)

    # ── Phase 2.8: AI Exec Tracker ──
    from tools.ai_exec_tracker import run as run_ai_exec
    _run_phase("Phase 2.8b: AI Executive Investment Tracker", run_ai_exec)

    # ── Phase 2.85: Alt Alpha II (6 new modules, weekly-gated) ──
    from tools.earnings_nlp import run as run_earnings_nlp
    _run_phase("Phase 2.85a: Earnings NLP (EDGAR 8-K + VADER)", run_earnings_nlp)

    from tools.gov_intel import run as run_gov_intel
    _run_phase("Phase 2.85b: Government Intelligence (WARN, OSHA, EPA, FCC, lobbying)", run_gov_intel)

    from tools.labor_intel import run as run_labor_intel
    _run_phase("Phase 2.85c: Labor Intelligence (H-1B, job postings)", run_labor_intel)

    from tools.supply_chain_intel import run as run_supply_chain
    _run_phase("Phase 2.85d: Supply Chain Intelligence (rail, shipping, trucking)", run_supply_chain)

    from tools.digital_exhaust import run as run_digital_exhaust
    _run_phase("Phase 2.85e: Digital Exhaust (app store, GitHub, pricing)", run_digital_exhaust)

    from tools.pharma_intel import run as run_pharma_intel
    _run_phase("Phase 2.85f: Pharma Intelligence (ClinicalTrials.gov, CMS)", run_pharma_intel)

    # ── Phase 2.86: Alt Alpha III (5 new alt-data modules, weekly-gated) ──
    from tools.aar_rail_intel import run as run_aar_rail
    _run_phase("Phase 2.86a: AAR Rail Carloadings (FRED + rail momentum)", run_aar_rail)

    from tools.ship_tracking_intel import run as run_ship_tracking
    _run_phase("Phase 2.86b: Ship Tracking Intelligence (BDI, freight, ports)", run_ship_tracking)

    from tools.patent_intel import run as run_patent_intel
    _run_phase("Phase 2.86c: Patent Intelligence (USPTO filing velocity)", run_patent_intel)

    from tools.ucc_filings_intel import run as run_ucc_filings
    _run_phase("Phase 2.86d: UCC Filings Intelligence (secured debt distress)", run_ucc_filings)

    from tools.board_interlocks_intel import run as run_board_interlocks
    _run_phase("Phase 2.86e: Board Interlocks Intelligence (DEF 14A governance)", run_board_interlocks)

    # ── Phase 2.86f: New alpha intelligence modules ──
    from tools.analyst_intel import run as run_analyst_intel
    _run_phase("Phase 2.87: Analyst Intelligence (unified FMP + Finnhub)", run_analyst_intel)

    from tools.capital_flows_intel import run as run_capital_flows
    _run_phase("Phase 2.88: Capital Flows Intelligence (institutional + 13F delta)", run_capital_flows)

    from tools.onchain_intel import run as run_onchain
    _run_phase("Phase 2.89: On-Chain Intelligence (crypto assets)", run_onchain)

    # ── Phase 2.9: Consensus Blindspots (LAST — reads all other modules) ──
    from tools.consensus_blindspots import run as run_cbs
    _run_phase("Phase 2.9: Consensus Blindspots (Howard Marks)", run_cbs)

    # ── Phase 3: Convergence & Signals ──
    from tools.convergence_engine import run as run_convergence
    _run_phase("Phase 3.1: Convergence Engine (24 modules)", run_convergence)

    from tools.signal_generator import run as run_signals
    _run_phase("Phase 3.2: Signal Generator", run_signals)

    from tools.devils_advocate import run as run_devil
    _run_phase("Phase 3.3: Devil's Advocate (bear cases)", run_devil)

    # ── Phase 3.4: Cross-Signal Conflict Detection ──
    from tools.signal_conflicts import run as run_conflicts
    _run_phase("Phase 3.4: Cross-Signal Conflict Detector", run_conflicts)

    # ── Phase 3.5: Base Rate Tracking ──
    from tools.base_rate_tracker import run as run_base_rates
    _run_phase("Phase 3.5: Base Rate Tracker", run_base_rates)

    # ── Phase 3.55: Adaptive Weight Optimizer (data moat flywheel) ──
    from tools.weight_optimizer import run as run_weight_optimizer
    _run_phase("Phase 3.55: Adaptive Weight Optimizer", run_weight_optimizer)

    # ── Phase 3.56: Cross-Asset Screener ──
    from tools.cross_asset_screener import run as run_cross_asset
    _run_phase("Phase 3.56: Cross-Asset Screener (stocks + commodities + crypto)", run_cross_asset)

    # ── Phase 3.57: Narrative Engine ──
    from tools.narrative_engine import run as run_narrative
    _run_phase("Phase 3.57: Narrative Engine (12 macro narratives)", run_narrative)

    # ── Phase 3.575: Catalyst Engine ──
    from tools.catalyst_engine import run as run_catalyst
    _run_phase("Phase 3.575: Catalyst Engine (M&A, insider, options, breakout)", run_catalyst)

    # ── Phase 3.58: Signal IC Backtester ──
    from tools.signal_ic import run as run_signal_ic
    _run_phase("Phase 3.58: Signal IC Backtester (Spearman IC per module)", run_signal_ic)

    # ── Phase 3.59: Gate Engine ──
    from tools.gate_engine import run as run_gates
    _run_phase("Phase 3.59: Gate Engine (10-gate cascade — 923 assets)", run_gates)

    # ── Phase 3.6: Investment Memo Generation ──
    from tools.intelligence_report import run as run_memos
    _run_phase("Phase 3.6: Investment Memo Generator (HIGH signals)", run_memos)

    # ── Phase 3.7: Portfolio Stress Testing ──
    from tools.stress_test import run as run_stress
    _run_phase("Phase 3.7: Portfolio Stress Test (7 scenarios)", run_stress)

    # ── Phase 3.8: Thesis Break Monitoring ──
    from tools.thesis_monitor import run as run_thesis_monitor
    _run_phase("Phase 3.8: Thesis Break Monitor (7/14/30d lookback)", run_thesis_monitor)

    # ── Phase 4: Alerts ──
    from tools.check_alerts import run as run_alerts
    _run_phase("Phase 4: Check Alerts", run_alerts)

    # ── Summary ──
    total = time.time() - pipeline_start
    today = date.today().isoformat()
    cp_conn = _get_checkpoint_conn()
    cp_rows = cp_conn.execute(
        "SELECT phase_name, status FROM pipeline_checkpoints WHERE run_date=? ORDER BY rowid",
        (today,)
    ).fetchall()
    failed = [r[0] for r in cp_rows if r[1] == "failed"]
    skipped_today = [r[0] for r in cp_rows if r[1] == "completed"]

    print("\n" + "=" * 60)
    print(f"  PIPELINE COMPLETE — {total:.0f}s ({total/60:.1f} min)")
    print(f"  Phases completed: {len(skipped_today)} | Failed: {len(failed)}")
    if failed:
        print(f"  ✗ Failed phases: {', '.join(failed)}")
    print("=" * 60)



if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    main()
