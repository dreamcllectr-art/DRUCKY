"""Pattern Match & Options Intelligence — Orchestrator.

15th convergence module. Runs pattern scanner (Layers 1-4) on all symbols,
gates options fetch (Layer 5) to top candidates, computes final composite,
writes results to DB.

Pipeline phase: 2.15 (after technical scoring + TA gate, before alpha modules)
"""

import json
import logging
from datetime import date

from tools.db import get_conn, upsert_many
from tools.config import (
    OPTIONS_FETCH_MAX_SYMBOLS,
    OPTIONS_MIN_PATTERN_SCORE,
    PATTERN_OPTIONS_BLEND,
)

logger = logging.getLogger(__name__)


def run(symbols: list[str] | None = None):
    """Main entry point for the daily pipeline.

    Flow:
    1. Run pattern_scanner on all symbols (cheap, price-data only)
    2. Gate: select top symbols by pattern_scan_score for options fetch
    3. Run options_intel on gated symbols
    4. Compute final pattern_options_score
    5. Write all results to DB
    """
    print("\n" + "=" * 60)
    print("  PATTERN MATCH & OPTIONS INTELLIGENCE")
    print("=" * 60)

    # ── Phase 1: Pattern Scanner (Layers 1-4) ──
    print("\n  ── Layers 1-4: Pattern Scanner ──")
    from tools.pattern_scanner import scan_all
    scan_results = scan_all(symbols)

    if not scan_results:
        print("  ✗ No pattern scan results")
        return

    # Write pattern_scan results to DB
    today = date.today().isoformat()
    columns = [
        "symbol", "date", "regime", "regime_score", "vix_percentile",
        "sector_quadrant", "rotation_score", "rs_ratio", "rs_momentum",
        "patterns_detected", "pattern_score", "sr_proximity", "volume_profile_score",
        "hurst_exponent", "mr_score", "momentum_score",
        "compression_score", "squeeze_active",
        "wyckoff_phase", "wyckoff_confidence",
        "earnings_days_to_next", "vol_regime",
        "pattern_scan_score", "layer_scores",
    ]
    rows = [tuple(r[c] for c in columns) for r in scan_results]
    upsert_many("pattern_scan", columns, rows)
    print(f"  ✓ Pattern scan: {len(scan_results)} symbols written to DB")

    # ── Phase 2: Options Intelligence Gate ──
    print("\n  ── Layer 5: Options Intelligence ──")

    # Sort by pattern_scan_score descending, take top N above threshold
    candidates = sorted(scan_results, key=lambda r: r["pattern_scan_score"], reverse=True)
    gated = [r for r in candidates if r["pattern_scan_score"] >= OPTIONS_MIN_PATTERN_SCORE]
    gated = gated[:OPTIONS_FETCH_MAX_SYMBOLS]

    gated_symbols = [r["symbol"] for r in gated]
    print(f"  Gate: {len(gated)} symbols pass threshold ({OPTIONS_MIN_PATTERN_SCORE}) "
          f"from {len(scan_results)} total")

    options_results = {}
    if gated_symbols:
        from tools.options_intel import analyze_batch
        opt_list = analyze_batch(gated_symbols)

        # Write options_intel to DB
        if opt_list:
            opt_columns = [
                "symbol", "date",
                "atm_iv", "hv_20d", "iv_premium", "iv_rank", "iv_percentile",
                "expected_move_pct", "straddle_cost",
                "volume_pc_ratio", "oi_pc_ratio", "pc_signal",
                "unusual_activity_count", "unusual_activity", "unusual_direction_bias",
                "skew_25d", "skew_direction", "term_structure_signal",
                "net_gex", "gamma_flip_level", "vanna_exposure", "max_pain",
                "put_wall", "call_wall", "dealer_regime",
                "options_score",
            ]
            opt_rows = [tuple(r.get(c) for c in opt_columns) for r in opt_list]
            upsert_many("options_intel", opt_columns, opt_rows)
            options_results = {r["symbol"]: r for r in opt_list}
            print(f"  ✓ Options intel: {len(opt_list)} symbols analyzed")
        else:
            print("  · No options data retrieved")
    else:
        print("  · No symbols above gate threshold")

    # ── Phase 3: Final Composite & Convergence Feed ──
    print("\n  ── Computing final composite scores ──")

    pw = PATTERN_OPTIONS_BLEND["pattern_weight"]
    ow = PATTERN_OPTIONS_BLEND["options_weight"]

    po_columns = [
        "symbol", "date", "pattern_scan_score", "options_score",
        "pattern_options_score", "top_pattern", "top_signal", "narrative", "status",
    ]
    po_rows = []

    for r in scan_results:
        sym = r["symbol"]
        ps_score = r["pattern_scan_score"]
        opt = options_results.get(sym)

        if opt:
            opt_score = opt["options_score"]
            final_score = pw * ps_score + ow * opt_score
        else:
            opt_score = None
            final_score = ps_score

        # Top pattern
        patterns = json.loads(r["patterns_detected"]) if r.get("patterns_detected") else []
        top_pattern = patterns[0]["pattern"] if patterns else None

        # Top signal narrative
        signals = []
        if r.get("squeeze_active"):
            signals.append("squeeze")
        if r.get("wyckoff_phase") == "accumulation":
            signals.append("accumulation")
        if opt and opt.get("dealer_regime") == "amplifying":
            signals.append("neg_GEX")
        if opt and opt.get("unusual_activity_count", 0) > 0:
            signals.append(f"{opt['unusual_activity_count']}×unusual_flow")
        top_signal = ", ".join(signals) if signals else None

        # Narrative
        parts = [f"pattern={ps_score:.0f}"]
        if opt_score is not None:
            parts.append(f"options={opt_score:.0f}")
        if r.get("wyckoff_phase"):
            parts.append(f"wyckoff={r['wyckoff_phase']}")
        if r.get("sector_quadrant"):
            parts.append(f"rotation={r['sector_quadrant']}")
        if opt and opt.get("expected_move_pct"):
            parts.append(f"exp_move=±{opt['expected_move_pct']:.1f}%")
        narrative = f"Score {final_score:.0f}: {', '.join(parts)}"

        po_rows.append((
            sym, today, ps_score, opt_score,
            round(final_score, 1), top_pattern, top_signal,
            narrative, "active",
        ))

    upsert_many("pattern_options_signals", po_columns, po_rows)

    # Summary stats
    scores = [r[4] for r in po_rows]  # pattern_options_score
    above_50 = sum(1 for s in scores if s and s > 50)
    above_70 = sum(1 for s in scores if s and s > 70)
    squeezed = sum(1 for r in scan_results if r.get("squeeze_active"))

    print(f"\n  Results:")
    print(f"    Total symbols scored: {len(po_rows)}")
    print(f"    Score > 50 (convergence-eligible): {above_50}")
    print(f"    Score > 70 (strong setups): {above_70}")
    print(f"    Active squeezes: {squeezed}")
    print(f"    Options analyzed: {len(options_results)}")
    if options_results:
        amplifying = sum(1 for o in options_results.values() if o.get("dealer_regime") == "amplifying")
        unusual_total = sum(o.get("unusual_activity_count", 0) for o in options_results.values())
        print(f"    Negative GEX (amplifying): {amplifying}")
        print(f"    Total unusual options signals: {unusual_total}")

    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from tools.db import init_db
    init_db()
    run()
