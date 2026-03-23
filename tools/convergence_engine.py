"""Convergence Engine — master signal synthesis.
Weights 24 modules, produces conviction levels (HIGH/NOTABLE/WATCH/BLOCKED)."""
import json, logging
from datetime import date
from tools.db import get_conn, query
from tools.config import (CONVERGENCE_WEIGHTS, CONVICTION_HIGH, CONVICTION_NOTABLE, REGIME_CONVERGENCE_WEIGHTS)

logger = logging.getLogger(__name__)
MODULE_THRESHOLD = 50.0

def _qmax(table, score_col):
    return query(f"""SELECT s.symbol, s.{score_col} FROM {table} s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM {table} GROUP BY symbol) m
        ON s.symbol=m.symbol AND s.date=m.mx WHERE s.{score_col} IS NOT NULL""")

def _safe_load(fn, name):
    try: return fn()
    except Exception as e: logger.warning(f"{name} scores unavailable: {e}"); return {}

def _load_module_scores():
    modules = {}
    for key, table, col in [
        ("main_signal","signals","composite_score"), ("smartmoney","smart_money_scores","conviction_score"),
        ("worldview","worldview_signals","thesis_alignment_score"), ("variant","variant_analysis","variant_score"),
        ("alt_data","alt_data_scores","alt_data_score"), ("earnings_nlp","earnings_nlp_scores","earnings_nlp_score"),
        ("gov_intel","gov_intel_scores","gov_intel_score"), ("labor_intel","labor_intel_scores","labor_intel_score"),
        ("supply_chain","supply_chain_scores","supply_chain_score"),
        ("digital_exhaust","digital_exhaust_scores","digital_exhaust_score"),
        ("pharma_intel","pharma_intel_scores","pharma_intel_score"),
        ("aar_rail","aar_rail_scores","aar_rail_score"),
        ("ship_tracking","ship_tracking_scores","ship_tracking_score"),
        ("patent_intel","patent_intel_scores","patent_intel_score"),
        ("ucc_filings","ucc_filings_scores","ucc_filings_score"),
        ("board_interlocks","board_interlocks_scores","board_interlocks_score"),
        # New modules
        ("short_interest","short_interest_scores","score"),
        ("retail_sentiment","retail_sentiment_scores","score"),
        ("analyst_intel","analyst_scores","composite_score"),
        ("options_flow","options_flow_scores","score"),
        ("capital_flows","capital_flow_scores","composite"),
    ]:
        modules[key] = _safe_load(lambda t=table,c=col: {r["symbol"]:r[c] for r in _qmax(t,c)}, key)
    modules["reddit"] = _safe_load(
        lambda: {r["symbol"]:r["score"] for r in _qmax("reddit_signals","score")}, "reddit")
    modules["onchain_intel"] = _safe_load(
        lambda: {r["asset"]:r["composite"] for r in _qmax("onchain_scores","composite")},
        "onchain_intel")
    def _research():
        rows = query("""SELECT symbol, AVG(sentiment*relevance_score) as avg_score FROM research_signals
            WHERE symbol IS NOT NULL AND date>=date('now','-7 days') GROUP BY symbol""")
        return {r["symbol"]: max(0,min(100,(r["avg_score"]+100)/2)) for r in rows}
    modules["research"] = _safe_load(_research, "research")
    def _foreign():
        from tools.foreign_intel import compute_foreign_intel_scores
        return compute_foreign_intel_scores()
    modules["foreign_intel"] = _safe_load(_foreign, "foreign_intel")
    for key, table, col, extra in [
        ("news_displacement","news_displacement","displacement_score","status='active'"),
        ("sector_expert","sector_expert_signals","sector_displacement_score",""),
        ("pairs","pair_signals","pairs_score","status='active' AND runner_symbol IS NOT NULL"),
        ("ma","ma_signals","ma_score","status='active'"),
        ("energy_intel","energy_intel_signals","energy_intel_score",""),
        ("prediction_markets","prediction_market_signals","pm_score","status='active'"),
        ("pattern_options","pattern_options_signals","pattern_options_score","status='active'"),
        ("estimate_momentum","estimate_momentum_signals","em_score",""),
        ("ai_regulatory","regulatory_signals","reg_score","status='active'"),
        ("consensus_blindspots","consensus_blindspot_signals","cbs_score","symbol != '_MARKET'"),
    ]:
        sym_col = "runner_symbol" if "pair" in table else "symbol"
        def _mk(t=table,c=col,e=extra,sc=sym_col):
            rows = query(f"SELECT {sc} as symbol, MAX({c}) as score FROM {t} WHERE date>=date('now','-7 days') {'AND '+e if e else ''} GROUP BY {sc}")
            return {r["symbol"]:r["score"] for r in rows if r["score"]}
        modules[key] = _safe_load(_mk, key)
    return modules

def _check_forensic_block(symbol):
    return bool(query("SELECT severity FROM forensic_alerts WHERE symbol=? AND severity='CRITICAL' ORDER BY date DESC LIMIT 1", [symbol]))

def run():
    print("\n" + "="*60 + "\n  CONVERGENCE ENGINE\n" + "="*60)
    module_scores = _load_module_scores()
    all_symbols = set()
    for md in module_scores.values(): all_symbols.update(md.keys())
    regime_rows = query("SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = regime_rows[0]["regime"] if regime_rows else "neutral"
    weight_source = "static"
    weights = REGIME_CONVERGENCE_WEIGHTS.get(regime, CONVERGENCE_WEIGHTS)
    try:
        from tools.config import WO_ENABLE_ADAPTIVE
        if WO_ENABLE_ADAPTIVE:
            ar = query("SELECT module_name,weight FROM weight_history WHERE regime=? AND date=(SELECT MAX(date) FROM weight_history WHERE regime=?)",
                       [regime, regime])
            if ar and len(ar) >= 10:
                aw = {r["module_name"]:r["weight"] for r in ar}
                base = REGIME_CONVERGENCE_WEIGHTS.get(regime, CONVERGENCE_WEIGHTS)
                for m in base:
                    if m not in aw: aw[m] = base[m]
                if 0.95 <= sum(aw.values()) <= 1.05: weights = aw; weight_source = "adaptive"
    except Exception: pass
    print(f"  Modules: {list(module_scores.keys())}")
    print(f"  Weights: {regime} ({weight_source}) | Symbols: {len(all_symbols)}")
    today = date.today().isoformat(); results = []
    mod_keys = ["main_signal","smartmoney","worldview","variant","research","reddit","foreign_intel",
        "news_displacement","alt_data","sector_expert","pairs","ma","energy_intel","prediction_markets",
        "pattern_options","estimate_momentum","ai_regulatory","consensus_blindspots",
        "earnings_nlp","gov_intel","labor_intel","supply_chain","digital_exhaust","pharma_intel",
        "aar_rail","ship_tracking","patent_intel","ucc_filings","board_interlocks",
        "short_interest","retail_sentiment","onchain_intel","analyst_intel","options_flow","capital_flows"]
    for symbol in all_symbols:
        active = []
        weighted_sum = active_weight_sum = 0.0
        for mod, w in weights.items():
            sc = module_scores.get(mod, {}).get(symbol)  # None = no data, 0 = genuine bearish
            if sc is None:
                continue  # no data for this module/symbol — exclude from denominator entirely
            if sc > MODULE_THRESHOLD: active.append(mod)
            weighted_sum += sc * w
            active_weight_sum += w  # count all modules with real data, including genuine 0-scores
        # Divide by active module weights so score stays in 0-100 range
        # even when most modules have no data yet
        conv_score = weighted_sum / active_weight_sum if active_weight_sum else 0
        mc = len(active)
        blocked = _check_forensic_block(symbol)
        if blocked: conviction = "BLOCKED"
        elif mc >= CONVICTION_HIGH: conviction = "HIGH"
        elif mc >= CONVICTION_NOTABLE: conviction = "NOTABLE"
        elif mc >= 1: conviction = "WATCH"
        else: continue
        parts = ", ".join(f"{m}={module_scores.get(m,{}).get(symbol,0):.0f}" for m in active)
        narrative = f"{conviction} conviction: {mc} modules agree ({parts})"
        row = [symbol, today, conv_score, mc, conviction, 1 if blocked else 0]
        row += [module_scores.get(k, {}).get(symbol) for k in mod_keys]
        row += [json.dumps(active), narrative]
        results.append(tuple(row))
    if results:
        cols = ("symbol,date,convergence_score,module_count,conviction_level,forensic_blocked,"
                "main_signal_score,smartmoney_score,worldview_score,variant_score,research_score,"
                "reddit_score,foreign_intel_score,news_displacement_score,alt_data_score,"
                "sector_expert_score,pairs_score,ma_score,energy_intel_score,prediction_markets_score,"
                "pattern_options_score,estimate_momentum_score,ai_regulatory_score,"
                "consensus_blindspots_score,earnings_nlp_score,gov_intel_score,labor_intel_score,"
                "supply_chain_score,digital_exhaust_score,pharma_intel_score,"
                "aar_rail_score,ship_tracking_score,patent_intel_score,ucc_filings_score,board_interlocks_score,"
                "short_interest_score,retail_sentiment_score,onchain_intel_score,"
                "analyst_intel_score,options_flow_score,capital_flows_score,"
                "active_modules,narrative")
        placeholders = ",".join(["?"]*43)
        with get_conn() as conn:
            conn.executemany(f"INSERT OR REPLACE INTO convergence_signals ({cols}) VALUES ({placeholders})", results)
    high = sum(1 for r in results if r[4]=="HIGH")
    notable = sum(1 for r in results if r[4]=="NOTABLE")
    watch = sum(1 for r in results if r[4]=="WATCH")
    blk = sum(1 for r in results if r[4]=="BLOCKED")
    print(f"\n  Results: {len(results)} symbols")
    print(f"  HIGH: {high} | NOTABLE: {notable} | WATCH: {watch} | BLOCKED: {blk}\n" + "="*60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from tools.db import init_db; init_db(); run()
