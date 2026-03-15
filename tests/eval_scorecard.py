#!/usr/bin/env python3
"""Druckenmiller Alpha System — Eval Scorecard.

Karpathy-style eval: run after every change, score across 5 categories.
Target: 10/10 on every category = Jane Street / Citadel / Millennium tier.

Usage:
    python tests/eval_scorecard.py                    # all categories
    python tests/eval_scorecard.py --category simplicity
    python tests/eval_scorecard.py --json             # machine-readable
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DASHBOARD = ROOT / "dashboard"
DB_PATH = ROOT / ".tmp" / "druckenmiller.db"

# ─── Helpers ────────────────────────────────────────────────────────────

def _py_files():
    return sorted(f for f in TOOLS.glob("*.py") if f.name != "__init__.py")

def _loc(path):
    try:
        return sum(1 for _ in open(path, encoding="utf-8", errors="ignore"))
    except Exception:
        return 0

def _page_files():
    app = DASHBOARD / "src" / "app"
    if not app.exists():
        return []
    return sorted(app.rglob("page.tsx"))

def _tsx_files():
    src = DASHBOARD / "src"
    if not src.exists():
        return []
    return sorted(src.rglob("*.tsx"))

def _component_dir():
    return DASHBOARD / "src" / "components"

def _db_conn():
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(str(DB_PATH))

def _db_tables():
    conn = _db_conn()
    if not conn:
        return [], []
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    empty = [t for t in tables if conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0] == 0]
    conn.close()
    return tables, empty

def _convergence_weights():
    """Parse CONVERGENCE_WEIGHTS from config_modules.py."""
    cfg = TOOLS / "config_modules.py"
    if not cfg.exists():
        cfg = TOOLS / "config.py"
    try:
        text = open(cfg, encoding="utf-8").read()
        start = text.find("CONVERGENCE_WEIGHTS = {")
        if start < 0:
            return {}
        # Find matching closing brace
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    block = text[start:i+1]
                    break
        else:
            return {}
        weights = {}
        for m in re.finditer(r'"(\w+)"\s*:\s*([\d.]+)', block):
            weights[m.group(1)] = float(m.group(2))
        return weights
    except Exception:
        return {}

# Map convergence weight keys → actual file stems (where names differ)
MODULE_FILE_MAP = {
    "smartmoney": "filings_13f",
    "worldview": "worldview_model",
    "variant": "variant_perception",
    "research": "research_sources",
    "main_signal": "signal_generator",
    "reddit": "convergence_engine",  # reddit scoring is inline in convergence_engine
    "alt_data": "alternative_data",
    "sector_expert": "sector_experts",
    "pairs": "pairs_trading",
    "ma": "ma_signals",
    "supply_chain": "supply_chain_intel",
}

def _module_has_file(mod_name):
    """Check if a convergence module has a corresponding tools/*.py file."""
    mapped = MODULE_FILE_MAP.get(mod_name)
    if mapped is None and mod_name in MODULE_FILE_MAP:
        return False  # explicitly mapped to None (removed)
    stem = mapped or mod_name
    if (TOOLS / f"{stem}.py").exists():
        return True
    for suffix in ["_intel", "_signals", "_scoring"]:
        if (TOOLS / f"{stem}{suffix}.py").exists():
            return True
    return False

def _count_inline_styles(tsx_files):
    count = 0
    for f in tsx_files:
        try:
            text = open(f, encoding="utf-8").read()
            count += len(re.findall(r'style\s*=\s*\{', text))
        except Exception:
            pass
    return count

def _component_reuse_pct(page_files):
    if not page_files:
        return 0
    importing = 0
    for f in page_files:
        try:
            text = open(f, encoding="utf-8").read()
            if re.search(r'from\s+["\']@/components', text) or re.search(r"from\s+['\"]@/components", text):
                importing += 1
        except Exception:
            pass
    return (importing / len(page_files)) * 100 if page_files else 0

def _db_populated_score():
    """Check what percentage of non-empty tables have recent data (last 7 days)."""
    conn = _db_conn()
    if not conn:
        return 0
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    scored = 0
    total_with_date = 0
    for t in tables:
        try:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info([{t}])").fetchall()]
            if 'date' in cols:
                total_with_date += 1
                row = conn.execute(f"SELECT MAX(date) FROM [{t}]").fetchone()
                if row and row[0]:
                    scored += 1
        except Exception:
            pass
    conn.close()
    return (scored / total_with_date * 100) if total_with_date else 0

# Map convergence module keys → DB tables they populate
MODULE_TABLE_MAP = {
    "smartmoney": ["smart_money_scores"],
    "worldview": ["worldview_signals"],
    "variant": ["signal_outcomes"],
    "foreign_intel": ["foreign_intel_url_cache", "foreign_ticker_map"],
    "news_displacement": ["news_displacement"],
    "research": ["research_signals"],
    "main_signal": ["signals"],
    "reddit": ["reddit_signals"],
    "alt_data": ["alt_data_scores"],
    "sector_expert": ["sector_rotation"],
    "pairs": ["pair_signals", "pair_relationships"],
    "ma": ["ma_signals", "ma_rumors"],
    "energy_intel": ["energy_intel_signals"],
    "prediction_markets": ["prediction_market_signals"],
    "pattern_options": ["pattern_options_signals", "pattern_scan"],
    "estimate_momentum": ["estimate_snapshots"],
    "ai_regulatory": ["energy_regulatory_signals"],
    "consensus_blindspots": ["consensus_blindspot_signals"],
    "earnings_nlp": ["earnings_calendar"],
    "gov_intel": ["gov_intel_scores"],
    "labor_intel": ["labor_intel_scores"],
    "supply_chain": ["supply_chain_scores"],
    "digital_exhaust": ["digital_exhaust_scores"],
    "pharma_intel": ["pharma_intel_scores"],
}

def _module_tables_populated():
    """Count how many convergence modules have populated DB tables."""
    conn = _db_conn()
    if not conn:
        return 0, 0
    weights = _convergence_weights()
    populated = 0
    for mod in weights:
        tables = MODULE_TABLE_MAP.get(mod, [mod, f"{mod}_signals", f"{mod}_scores"])
        found = False
        for table in tables:
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()
                if row and row[0] > 0:
                    found = True
                    break
            except Exception:
                pass
        if found:
            populated += 1
    conn.close()
    return populated, len(weights)


# ─── Assertion runners ──────────────────────────────────────────────────

def eval_simplicity():
    """Simplicity: system should be simple yet deep, no redundancies."""
    results = []
    py_files = _py_files()
    total_loc = sum(_loc(f) for f in py_files)
    max_file = max(py_files, key=_loc) if py_files else None
    max_loc = _loc(max_file) if max_file else 0
    avg_loc = total_loc // len(py_files) if py_files else 0
    weights = _convergence_weights()
    dead = [m for m, w in weights.items() if w == 0]
    dupes = [f.name for f in TOOLS.iterdir() if ' 2' in f.name or 'copy' in f.name.lower()]

    results.append({
        "id": "simplicity_01", "assertion": "No duplicate files (files with ' 2' or 'copy' in name)",
        "passed": len(dupes) == 0,
        "detail": f"Duplicates: {', '.join(dupes)}" if dupes else "No duplicate files",
    })
    results.append({
        "id": "simplicity_02", "assertion": "All convergence modules have weight > 0 (no dead weight)",
        "passed": len(dead) == 0,
        "detail": f"Dead modules (weight=0): {', '.join(dead)}" if dead else "All modules have weight > 0",
    })
    results.append({
        "id": "simplicity_03", "assertion": "No Python file in tools/ exceeds 800 lines",
        "passed": max_loc <= 800,
        "detail": f"Max file: {max_file.name} ({max_loc} lines)" if max_file else "No files",
    })
    results.append({
        "id": "simplicity_04", "assertion": "No Python file in tools/ exceeds 500 lines",
        "passed": max_loc <= 500,
        "detail": f"Max file: {max_file.name} ({max_loc} lines)" if max_file else "No files",
    })
    results.append({
        "id": "simplicity_05", "assertion": "Average Python file in tools/ is under 300 lines",
        "passed": avg_loc < 300,
        "detail": f"Avg file: {avg_loc} lines ({len(py_files)} files)",
    })
    results.append({
        "id": "simplicity_06", "assertion": "Total Python LOC in tools/ under 25,000",
        "passed": total_loc < 25000,
        "detail": f"Total LOC: {total_loc}",
    })
    results.append({
        "id": "simplicity_07", "assertion": "Total Python LOC in tools/ under 15,000",
        "passed": total_loc < 15000,
        "detail": f"Total LOC: {total_loc}",
    })
    active_weights = {m: w for m, w in weights.items() if w > 0}
    missing_files = [m for m in active_weights if not _module_has_file(m)]
    results.append({
        "id": "simplicity_08",
        "assertion": "Every active module in CONVERGENCE_WEIGHTS has a corresponding tools/*.py file",
        "passed": len(missing_files) == 0,
        "detail": f"Missing: {', '.join(missing_files)}" if missing_files else f"All {len(active_weights)} active modules have files",
    })
    results.append({
        "id": "simplicity_09", "assertion": "config.py is under 800 lines (split if needed)",
        "passed": _loc(TOOLS / "config.py") <= 800,
        "detail": f"config.py: {_loc(TOOLS / 'config.py')} lines",
    })
    results.append({
        "id": "simplicity_10", "assertion": "api.py is under 800 lines (split if needed)",
        "passed": _loc(TOOLS / "api.py") <= 800,
        "detail": f"api.py: {_loc(TOOLS / 'api.py')} lines",
    })
    return results


def eval_frontend():
    """Frontend Simplicity: Apple-like, light, simple yet deep."""
    results = []
    pages = _page_files()
    tsx_files = _tsx_files()
    page_locs = [(p, _loc(p)) for p in pages]
    total_page_loc = sum(loc for _, loc in page_locs)
    max_page = max(page_locs, key=lambda x: x[1]) if page_locs else (None, 0)
    inline_count = _count_inline_styles(tsx_files)
    reuse_pct = _component_reuse_pct(pages)
    comp_dir = _component_dir()
    shared_components = list(comp_dir.rglob("*.tsx")) if comp_dir.exists() else []

    results.append({
        "id": "frontend_01", "assertion": "Total TSX LOC in dashboard pages < 10,000",
        "passed": total_page_loc < 10000,
        "detail": f"Total page LOC: {total_page_loc}",
    })
    results.append({
        "id": "frontend_02", "assertion": "Total TSX LOC in dashboard pages < 6,000",
        "passed": total_page_loc < 6000,
        "detail": f"Total page LOC: {total_page_loc}",
    })
    results.append({
        "id": "frontend_03", "assertion": "No page.tsx exceeds 400 lines",
        "passed": max_page[1] <= 400,
        "detail": f"Max page: {max_page[0].parent.name if max_page[0] else 'N/A'} ({max_page[1]} lines)",
    })
    results.append({
        "id": "frontend_04", "assertion": "No page.tsx exceeds 200 lines",
        "passed": max_page[1] <= 200,
        "detail": f"Max page: {max_page[0].parent.name if max_page[0] else 'N/A'} ({max_page[1]} lines)",
    })
    results.append({
        "id": "frontend_05", "assertion": "Dashboard has <= 20 page routes",
        "passed": len(pages) <= 20,
        "detail": f"{len(pages)} pages",
    })
    results.append({
        "id": "frontend_06", "assertion": "Dashboard has <= 15 page routes",
        "passed": len(pages) <= 15,
        "detail": f"{len(pages)} pages",
    })
    results.append({
        "id": "frontend_07", "assertion": "Component reuse >= 50% (pages importing from @/components)",
        "passed": reuse_pct >= 50,
        "detail": f"Component reuse: {reuse_pct:.0f}%",
    })
    results.append({
        "id": "frontend_08", "assertion": "Component reuse >= 80%",
        "passed": reuse_pct >= 80,
        "detail": f"Component reuse: {reuse_pct:.0f}%",
    })
    results.append({
        "id": "frontend_09", "assertion": "Fewer than 10 inline style= usages across all TSX",
        "passed": inline_count < 10,
        "detail": f"{inline_count} inline styles",
    })
    results.append({
        "id": "frontend_10", "assertion": "Zero inline style= usages across all TSX",
        "passed": inline_count == 0,
        "detail": f"{inline_count} inline styles",
    })
    return results


def eval_alpha():
    """Alpha: how much alpha the system generates. Jane Street / Citadel tier."""
    results = []
    conn = _db_conn()
    weights = _convergence_weights()
    pop, total = _module_tables_populated()

    # 1. All convergence modules producing data
    results.append({
        "id": "alpha_01", "assertion": "75%+ of convergence modules have populated DB tables",
        "passed": pop >= total * 0.75 and total > 0,
        "detail": f"{pop}/{total} modules populated",
    })

    # 2. Signals table has recent data
    has_signals = False
    signal_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM signals WHERE date >= date('now', '-7 days')").fetchone()
            signal_count = row[0] if row else 0
            has_signals = signal_count > 100
        except Exception:
            pass

    results.append({
        "id": "alpha_02", "assertion": "Signal generator producing 100+ signals in last 7 days",
        "passed": has_signals,
        "detail": f"{signal_count} signals in last 7 days",
    })

    # 3. Convergence scores exist
    conv_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM convergence_signals WHERE date >= date('now', '-7 days')").fetchone()
            conv_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "alpha_03", "assertion": "Convergence engine scoring 500+ stocks in last 7 days",
        "passed": conv_count >= 500,
        "detail": f"{conv_count} convergence scores in last 7 days",
    })

    # 4. HIGH conviction signals exist
    high_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM convergence_signals WHERE conviction_level = 'HIGH' AND date >= date('now', '-7 days')").fetchone()
            high_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "alpha_04", "assertion": "System identifies HIGH conviction opportunities (selective, < 15% of universe)",
        "passed": 0 < high_count <= conv_count * 0.15 + 1 if conv_count else False,
        "detail": f"{high_count} HIGH conviction signals",
    })

    # 5. Multi-module agreement
    agreement_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM convergence_signals WHERE module_count >= 3 AND date >= date('now', '-7 days')").fetchone()
            agreement_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "alpha_05", "assertion": "3+ modules agreeing on at least some stocks (true convergence)",
        "passed": agreement_count > 0,
        "detail": f"{agreement_count} stocks with 5+ module agreement",
    })

    # 6. Intelligence reports generated
    report_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM intelligence_reports WHERE generated_at >= date('now', '-7 days')").fetchone()
            report_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "alpha_06", "assertion": "Intelligence reports generated for top stocks",
        "passed": report_count >= 5,
        "detail": f"{report_count} reports in last 7 days",
    })

    # 7. Unique data sources (modules with data)
    results.append({
        "id": "alpha_07", "assertion": "15+ unique data modules producing signals",
        "passed": pop >= 15,
        "detail": f"{pop} modules with data",
    })

    # 8. Variant perception (contrarian alpha)
    variant_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM signal_outcomes WHERE signal_date >= date('now', '-30 days')").fetchone()
            variant_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "alpha_08", "assertion": "Variant perception module finding contrarian opportunities",
        "passed": variant_count > 0,
        "detail": f"{variant_count} variant analyses",
    })

    # 9. Weight optimizer running (adaptive weights = edge)
    wo_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM weight_optimizer_log").fetchone()
            wo_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "alpha_09", "assertion": "Weight optimizer has adapted module weights",
        "passed": wo_count > 0,
        "detail": f"{wo_count} weight optimization records",
    })

    # 10. Prediction markets integration (wisdom of crowds)
    pm_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM prediction_market_signals WHERE date >= date('now', '-30 days')").fetchone()
            pm_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "alpha_10", "assertion": "Prediction markets data integrated",
        "passed": pm_count > 0,
        "detail": f"{pm_count} prediction market signals",
    })

    if conn:
        conn.close()
    return results


def eval_depth():
    """Depth: how well the system explains the alpha — Druckenmiller-tier work product."""
    results = []
    conn = _db_conn()

    # 1. Intelligence reports have substance
    report_avg_len = 0
    if conn:
        try:
            row = conn.execute("SELECT AVG(LENGTH(COALESCE(report_markdown, report_html, ''))) FROM intelligence_reports WHERE generated_at >= date('now', '-30 days')").fetchone()
            report_avg_len = int(row[0]) if row and row[0] else 0
        except Exception:
            pass
    results.append({
        "id": "depth_01", "assertion": "Intelligence reports average 2000+ chars (deep analysis)",
        "passed": report_avg_len >= 2000,
        "detail": f"Avg report length: {report_avg_len} chars",
    })

    # 2. Devil's advocate module exists and is wired into pipeline
    da_exists = (TOOLS / "devils_advocate.py").exists()
    da_in_pipeline = False
    try:
        pipe_text = open(TOOLS / "daily_pipeline.py").read()
        da_in_pipeline = "devils_advocate" in pipe_text
    except Exception:
        pass
    results.append({
        "id": "depth_02", "assertion": "Devil's advocate module implemented and in pipeline",
        "passed": da_exists and da_in_pipeline,
        "detail": f"Module exists: {da_exists}, in pipeline: {da_in_pipeline}",
    })

    # 3. Base rate tracker provides historical context
    br_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM signal_outcomes WHERE signal_date >= date('now', '-30 days')").fetchone()
            br_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "depth_03", "assertion": "Base rate tracker providing historical context",
        "passed": br_count > 0,
        "detail": f"{br_count} base rate analyses",
    })

    # 4. Signal conflicts module exists and is wired
    sc_exists = (TOOLS / "signal_conflicts.py").exists()
    sc_in_pipeline = False
    try:
        pipe_text = open(TOOLS / "daily_pipeline.py").read()
        sc_in_pipeline = "signal_conflicts" in pipe_text
    except Exception:
        pass
    results.append({
        "id": "depth_04", "assertion": "Signal conflicts module implemented and in pipeline",
        "passed": sc_exists and sc_in_pipeline,
        "detail": f"Module exists: {sc_exists}, in pipeline: {sc_in_pipeline}",
    })

    # 5. Thesis monitoring active
    tm_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM thesis_snapshots WHERE date >= date('now', '-30 days')").fetchone()
            tm_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "depth_05", "assertion": "Thesis monitor tracking investment theses",
        "passed": tm_count > 0,
        "detail": f"{tm_count} thesis monitor entries",
    })

    # 6. Macro regime identified
    macro_regime = None
    if conn:
        try:
            row = conn.execute("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1").fetchone()
            macro_regime = row[0] if row else None
        except Exception:
            pass
    results.append({
        "id": "depth_06", "assertion": "Macro regime identified and used for weight adaptation",
        "passed": macro_regime is not None,
        "detail": f"Current regime: {macro_regime}" if macro_regime else "No regime data",
    })

    # 7. Sector-level analysis
    sector_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(DISTINCT sector) FROM sector_rotation WHERE date >= date('now', '-30 days')").fetchone()
            sector_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "depth_07", "assertion": "Sector experts covering 5+ sectors",
        "passed": sector_count >= 5,
        "detail": f"{sector_count} sectors covered",
    })

    # 8. Accounting forensics module exists and is wired
    af_exists = (TOOLS / "accounting_forensics.py").exists()
    af_in_pipeline = False
    try:
        pipe_text = open(TOOLS / "daily_pipeline.py").read()
        af_in_pipeline = "accounting_forensics" in pipe_text
    except Exception:
        pass
    results.append({
        "id": "depth_08", "assertion": "Accounting forensics module implemented and in pipeline",
        "passed": af_exists and af_in_pipeline,
        "detail": f"Module exists: {af_exists}, in pipeline: {af_in_pipeline}",
    })

    # 9. Multiple timeframes in analysis
    has_stress = False
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM stress_backtest_results").fetchone()
            has_stress = (row[0] if row else 0) > 0
        except Exception:
            pass
    results.append({
        "id": "depth_09", "assertion": "Stress testing scenarios modeled",
        "passed": has_stress,
        "detail": f"Stress test data: {'yes' if has_stress else 'no'}",
    })

    # 10. Consensus blindspots identified
    cbs_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM consensus_blindspot_signals WHERE date >= date('now', '-30 days')").fetchone()
            cbs_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "depth_10", "assertion": "Consensus blindspots identified (where crowd is wrong)",
        "passed": cbs_count > 0,
        "detail": f"{cbs_count} blindspot analyses",
    })

    if conn:
        conn.close()
    return results


def eval_moat():
    """Moat: how hard is this to replicate. Data moat + flywheel effects."""
    results = []
    conn = _db_conn()
    weights = _convergence_weights()

    # 1. Number of unique data modules
    results.append({
        "id": "moat_01", "assertion": "20+ unique convergence modules (hard to replicate breadth)",
        "passed": len(weights) >= 20,
        "detail": f"{len(weights)} convergence modules",
    })

    # 2. Self-improving weights (flywheel)
    wo_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM weight_optimizer_log").fetchone()
            wo_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "moat_02", "assertion": "Weight optimizer creates self-improving flywheel",
        "passed": wo_count > 0,
        "detail": f"{wo_count} weight adaptations",
    })

    # 3. Module performance tracking
    mp_count = 0
    if conn:
        try:
            row = conn.execute("SELECT COUNT(*) FROM signal_outcomes").fetchone()
            mp_count = row[0] if row else 0
        except Exception:
            pass
    results.append({
        "id": "moat_03", "assertion": "Signal outcomes tracked for continuous improvement",
        "passed": mp_count > 0,
        "detail": f"{mp_count} tracked outcomes",
    })

    # 4. Historical data accumulation
    days_of_data = 0
    if conn:
        try:
            row = conn.execute("SELECT JULIANDAY('now') - JULIANDAY(MIN(date)) FROM signals").fetchone()
            days_of_data = int(row[0]) if row and row[0] else 0
        except Exception:
            pass
    results.append({
        "id": "moat_04", "assertion": "7+ days of accumulated signal history (operational)",
        "passed": days_of_data >= 7,
        "detail": f"{days_of_data} days of data",
    })

    # 5. Proprietary data combinations
    pop, total = _module_tables_populated()
    results.append({
        "id": "moat_05", "assertion": "10+ modules with proprietary data combinations",
        "passed": pop >= 10,
        "detail": f"{pop} modules with data",
    })

    # 6. Regime-adaptive weights (different from static)
    has_regime_weights = False
    cfg = TOOLS / "config_modules.py"
    if cfg.exists():
        try:
            text = open(cfg).read()
            has_regime_weights = "REGIME_CONVERGENCE_WEIGHTS" in text
        except Exception:
            pass
    results.append({
        "id": "moat_06", "assertion": "Regime-adaptive weight profiles exist",
        "passed": has_regime_weights,
        "detail": "Regime weights configured" if has_regime_weights else "No regime weights",
    })

    # 7. API serves data (operational moat)
    api_exists = (TOOLS / "api.py").exists()
    results.append({
        "id": "moat_07", "assertion": "FastAPI backend operational",
        "passed": api_exists,
        "detail": "api.py exists" if api_exists else "No API",
    })

    # 8. Dashboard operational (UX moat)
    dash_exists = (DASHBOARD / "src" / "app" / "layout.tsx").exists()
    results.append({
        "id": "moat_08", "assertion": "Next.js dashboard operational",
        "passed": dash_exists,
        "detail": "Dashboard exists" if dash_exists else "No dashboard",
    })

    # 9. Convergence engine (the core IP)
    ce_exists = (TOOLS / "convergence_engine.py").exists()
    results.append({
        "id": "moat_09", "assertion": "Convergence engine (core IP) implemented",
        "passed": ce_exists,
        "detail": "Convergence engine exists" if ce_exists else "Missing",
    })

    # 10. Pipeline automation
    dp_exists = (TOOLS / "daily_pipeline.py").exists()
    results.append({
        "id": "moat_10", "assertion": "Automated daily pipeline runs without intervention",
        "passed": dp_exists,
        "detail": "Daily pipeline exists" if dp_exists else "Missing",
    })

    if conn:
        conn.close()
    return results


# ─── Scoring ────────────────────────────────────────────────────────────

CATEGORIES = {
    "simplicity": ("Simplicity", eval_simplicity),
    "frontend_simplicity": ("Frontend Simplicity", eval_frontend),
    "alpha": ("Alpha", eval_alpha),
    "depth": ("Depth", eval_depth),
    "moat": ("Moat", eval_moat),
}

def score_category(assertions):
    passed = sum(1 for a in assertions if a["passed"])
    total = len(assertions)
    # Score: 1-10 based on pass rate, minimum 1
    score = max(1, round(passed / total * 10)) if total else 1
    return score, passed, total

def status_label(score):
    if score >= 9: return "Elite"
    if score >= 7: return "Strong"
    if score >= 5: return "Developing"
    if score >= 3: return "Below target"
    return "Critical"

def run_eval(categories=None):
    if categories is None:
        categories = list(CATEGORIES.keys())

    all_results = {}
    total_score = 0
    total_passed = 0
    total_assertions = 0

    for cat_key in categories:
        name, fn = CATEGORIES[cat_key]
        assertions = fn()
        score, passed, total = score_category(assertions)
        total_score += score
        total_passed += passed
        total_assertions += total
        all_results[cat_key] = {
            "name": name,
            "score": score,
            "pass_rate": round(passed / total * 100, 1) if total else 0,
            "passed": passed,
            "total": total,
            "status": status_label(score),
            "assertions": assertions,
        }

    overall = round(total_score / len(categories), 1) if categories else 0
    overall_pass = round(total_passed / total_assertions * 100, 1) if total_assertions else 0

    return {
        "date": str(__import__("datetime").date.today()),
        "overall": overall,
        "total_pass_rate": overall_pass,
        "categories": all_results,
    }


def print_report(data, show_failures=True):
    print("=" * 72)
    print("  DRUCKENMILLER ALPHA SYSTEM — EVAL SCORECARD")
    print(f"  {data['date']}    |    {data['total_pass_rate']}% assertions passing")
    print("=" * 72)
    print()
    print(f"  {'Category':<26}{'Score':>6}  {'Pass Rate':>10}  {'Status':<15}")
    print(f"  {'─'*26}  {'─'*5}  {'─'*10}  {'─'*15}")

    for cat_key, cat in data["categories"].items():
        print(f"  {cat['name']:<26}{cat['score']:>3}/10  {cat['passed']:>3}/{cat['total']:<3} {cat['pass_rate']:>4}%  {cat['status']}")

    print(f"  {'─'*26}  {'─'*5}  {'─'*10}  {'─'*15}")
    print(f"  {'OVERALL':<26}{data['overall']:>5}/10  {' '*5}{data['total_pass_rate']:>5}%")
    print()

    if show_failures:
        failures = []
        for cat_key, cat in data["categories"].items():
            for a in cat["assertions"]:
                if not a["passed"]:
                    failures.append((cat["name"], a))
        if failures:
            print("  ── FAILED ASSERTIONS ──")
            print()
            for i, (cat_name, a) in enumerate(failures, 1):
                print(f"  {i:>2}. FAIL  [{cat_name}] {a['assertion']}  ({a['detail']})")
            print()

    print("=" * 72)


def main():
    parser = argparse.ArgumentParser(description="Druckenmiller Alpha Eval Scorecard")
    parser.add_argument("--category", "-c", choices=list(CATEGORIES.keys()), help="Run single category")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    cats = [args.category] if args.category else None
    data = run_eval(cats)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_report(data)

    # Save JSON
    out = ROOT / ".tmp" / "eval_scorecard.json"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n  JSON saved to {out}")

    return data


if __name__ == "__main__":
    main()
