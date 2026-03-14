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
  Phase 2.8: Consensus blindspots (reads ALL other module outputs)
  Phase 3:   Convergence engine + signal generation
  Phase 3.5: Devil's advocate (bear cases for HIGH conviction)
  Phase 4:   Alerts

Usage:
  python -m tools.daily_pipeline          # run full pipeline locally
  modal run modal_app.py::daily_pipeline  # run on Modal
"""

import logging
import time
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)


def _run_phase(name: str, fn, *args, **kwargs):
    """Run a pipeline phase with timing and error handling."""
    print(f"\n{'─' * 60}")
    print(f"  ▶ {name}")
    print(f"{'─' * 60}")
    t0 = time.time()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.time() - t0
        print(f"  ✓ {name} completed in {elapsed:.1f}s")
        return result
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ✗ {name} FAILED after {elapsed:.1f}s: {e}")
        logger.error(f"{name} failed: {traceback.format_exc()}")
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

    # ── Phase 1.5: Energy Data ──
    from tools.fetch_eia_data import run as fetch_eia
    _run_phase("Phase 1.5a: EIA Energy Data", fetch_eia)

    from tools.energy_intel_data import run as fetch_energy_data
    _run_phase("Phase 1.5b: Energy Intelligence Data", fetch_energy_data)

    from tools.global_energy_data import run as fetch_global_energy
    _run_phase("Phase 1.5c: Global Energy Markets Data (TTF, curves, spreads)", fetch_global_energy)

    from tools.energy_physical_flows import run as fetch_physical_flows
    _run_phase("Phase 1.5d: Energy Physical Flows (GIE EU Storage, ENTSO-G, CFTC CoT, LNG)", fetch_physical_flows)

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

    # ── Phase 2.8: Prediction Markets ──
    from tools.prediction_markets import run as run_pm
    _run_phase("Phase 2.8a: Prediction Markets (Polymarket)", run_pm)

    # ── Phase 2.8: AI Exec Tracker ──
    from tools.ai_exec_tracker import run as run_ai_exec
    _run_phase("Phase 2.8b: AI Executive Investment Tracker", run_ai_exec)

    # ── Phase 2.9: Consensus Blindspots (LAST — reads all other modules) ──
    from tools.consensus_blindspots import run as run_cbs
    _run_phase("Phase 2.9: Consensus Blindspots (Howard Marks)", run_cbs)

    # ── Phase 3: Convergence & Signals ──
    from tools.convergence_engine import run as run_convergence
    _run_phase("Phase 3.1: Convergence Engine (18 modules)", run_convergence)

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
    print("\n" + "=" * 60)
    print(f"  PIPELINE COMPLETE — {total:.0f}s ({total/60:.1f} min)")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    main()
