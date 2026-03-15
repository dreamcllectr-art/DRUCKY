"""Sector Expert Agents — dynamic domain intelligence for displacement detection."""
import sys, json, re, time
from datetime import date, datetime
from pathlib import Path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
import requests
from tools.config import GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL
from tools.db import init_db, get_conn, query

SECTOR_EXPERTS = {
    "ai_compute": {
        "expert_type": "ai_compute",
        "sectors": ["Technology", "Semiconductors", "Software", "Communication Services"],
        "core_tickers": ["NVDA", "AMD", "TSM", "ASML", "AMAT", "LRCX", "MSFT", "GOOGL", "META", "AMZN", "ORCL", "AVGO", "MRVL", "EQIX", "DLR", "VST", "CEG", "NRG"],
        "framework": "You are a senior AI/compute infrastructure analyst. Focus on GPU supply chain (NVDA CUDA moat, AMD MI300, TSM CoWoS, ASML EUV), HBM allocation, hyperscaler capex cycles (3-5yr not 1-2), power demand (~1GW per 100K GPU cluster), inference vs training mix. Consensus errors: capex supercycle duration underestimated, power infra stocks mispriced as utilities, CoWoS supply bottleneck, non-linear inference scaling.",
    },
    "energy": {
        "expert_type": "energy",
        "sectors": ["Energy", "Oil & Gas"],
        "core_tickers": ["OXY", "COP", "XOM", "CVX", "DVN", "FANG", "EOG", "MPC", "VLO", "PSX", "ET", "LNG", "VST", "CEG", "NRG"],
        "framework": "You are a senior energy analyst. Focus on OPEC+ compliance, US shale (rig count, DUC inventory, decline rates), EIA weekly data, crack spreads (3-2-1), LNG exports (HH vs JKM/TTF basis), AI power demand (nuclear renaissance), break-even analysis. Consensus errors: shale growth limits, OPEC+ discipline, energy transition timeline, AI power demand is additive.",
    },
    "biotech": {
        "expert_type": "biotech",
        "sectors": ["Healthcare", "Biotechnology", "Pharmaceuticals"],
        "core_tickers": ["LLY", "ABBV", "MRK", "PFE", "JNJ", "BMY", "AMGN", "GILD", "REGN", "VRTX", "BIIB", "MRNA"],
        "framework": "You are a senior biotech/pharma analyst. Focus on FDA PDUFA dates (BTD approval >90%), patent cliff timing (biosimilar erosion slower than expected), pipeline optionality, GLP-1 revolution (TAM $100B+), cash runway. Consensus errors: single trial failures overweighted, patent cliff stocks oversold early, rare disease sustainability, Phase 2-3 transition mispriced.",
    },
    "semiconductors": {
        "expert_type": "semiconductors",
        "sectors": ["Semiconductors", "Semiconductor Equipment"],
        "core_tickers": ["NVDA", "AMD", "INTC", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU", "MRVL", "AVGO", "QCOM", "TXN", "ON", "ADI"],
        "framework": "You are a senior semiconductor analyst. Focus on cycle position (stocks bottom 1-2Q before earnings trough), memory pricing (DRAM/NAND contract), equipment bookings (ASML orders), inventory levels, foundry utilization (TSMC monthly), HBM premium (3-5x DDR5). Consensus errors: memory cycle extrapolation, equipment stocks lead semis, AI demand masks weakness, inventory correction duration.",
    },
    "realestate": {
        "expert_type": "realestate", "sectors": ["Real Estate", "REITs"],
        "core_tickers": ["EQIX", "DLR", "PLD", "AMT", "SPG", "O", "VICI", "PSA", "EQR", "AVB", "WELL", "VTR"],
        "framework": "You are a senior REIT analyst. Focus on cap rate spreads (vs 10Y), data center demand (25-30% growth vs 10-15% supply), office quality bifurcation, rate sensitivity (long-duration fixed-rate less sensitive), NAV discounts (>20% = takeout opportunity), debt maturity wall. Consensus errors: office REITs not all equal, DC REITs undervalued, rate sensitivity overestimated, senior housing demographics.",
    },
    "defense": {
        "expert_type": "defense", "sectors": ["Aerospace & Defense", "Industrials"],
        "core_tickers": ["LMT", "RTX", "NOC", "GD", "BA", "LHX", "HII", "TDG", "HEI", "AXON"],
        "framework": "You are a senior defense analyst. Focus on backlog (book-to-bill >1.1x), margin ramp (dev 5-8% to production 12-15%), budget trajectory (bipartisan 3-5% real growth), geopolitical catalysts (NATO 2%, European rearmament), FMS pipeline ($80B+), munitions replenishment. Consensus errors: backlog durability underappreciated, production margin expansion, international sales larger than expected, sequestration fears overblown.",
    },
    "financials": {
        "expert_type": "financials", "sectors": ["Financial Services", "Banks", "Insurance", "Capital Markets"],
        "core_tickers": ["JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "BLK", "AXP", "V", "MA", "PGR", "TRV", "ALL", "MET"],
        "framework": "You are a senior financial analyst. Focus on NIM trajectory (yield curve shape #1 driver), credit cycle position (buy at peak provisions), capital return (CET1 excess = buybacks), insurance hard market (combined ratios <93%), yield curve signal (2s10s widening = banks +15-25%). Consensus errors: NIM compression fears, credit losses priced early, regional banks oversold, insurance hard market duration.",
    },
    "commodities": {
        "expert_type": "commodities", "sectors": ["Materials", "Mining", "Metals & Mining", "Agriculture"],
        "core_tickers": ["BHP", "RIO", "VALE", "FCX", "NEM", "SCCO", "CLF", "X", "AA", "ADM", "BG", "MOS", "CF", "NTR", "CTVA", "DE", "GLD", "SLV"],
        "framework": "You are a senior commodities analyst. Focus on copper (Dr. Copper, China 50%+ demand, supply constrained), gold (real rates driver, central bank buying), iron ore/steel (China property), agriculture (USDA WASDE, fertilizer costs), lithium (EV adoption curve), PMI correlation. Physical indicators: LME inventories, COMEX positioning, China PMI, Baltic Dry, fertilizer prices. Consensus errors: supply response slow (7-10yr mines), China demand written off too early, ag disruptions underpriced, gold rallies in cuts AND crises, copper structural deficit.",
    },
    "utilities": {
        "expert_type": "utilities",
        "sectors": ["Utilities", "Electric Utilities", "Gas Utilities", "Water Utilities", "Independent Power Producers"],
        "core_tickers": ["NEE", "DUK", "SO", "AEP", "XEL", "D", "EIX", "PCG", "PNW", "ES", "NI", "ATO", "SWX", "AWK", "WTRG", "SJW", "CWT", "VST", "CEG", "NRG", "AES", "BEP", "CWEN"],
        "framework": "You are a senior utilities analyst. Focus on rate base growth (6-8% CAGR = 6-8% EPS growth), regulatory quality, AI power demand (data center queues), grid modernization ($2T+ T&D), nuclear fleet value (24/7 carbon-free), water utilities (natural monopoly, M&A), gas pipe replacement. Consensus errors: growth utilities not bond proxies, AI power demand underestimated, nuclear still mispriced, CA wildfire risk manageable, water premium justified, IPPs are NOT utilities.",
    },
    "fintech": {
        "expert_type": "fintech", "sectors": ["Financials", "Information Technology"],
        "core_tickers": ["PYPL", "XYZ", "COIN", "HOOD", "FISV", "FIS", "GPN", "FOUR", "SYF", "CPAY", "BILL", "GWRE", "IBKR", "ALLY", "COF", "WEX"],
        "framework": "You are a senior fintech analyst. Focus on take rate trajectory, BNPL/credit mix (NCO >6% = trouble), crypto infra vs speculation (COIN staking+custody+Base L2), embedded finance TAM (2-5% attach rates), interchange regulation risk, deposit cost arbitrage (digital banks 50-100bps cheaper), insurance tech (GWRE cloud migration). Consensus errors: PYPL branded checkout inflecting, COIN infra floor valuation, vertical payment specialization premiums, digital bank losses over-extrapolated, FIS pure-play discount, HOOD lowest CAC in brokerage.",
    },
    "saas_cloud": {
        "expert_type": "saas_cloud", "sectors": ["Information Technology", "Communication Services"],
        "core_tickers": ["CRM", "NOW", "CRWD", "PANW", "DDOG", "FTNT", "WDAY", "ADBE", "INTU", "OKTA", "TWLO", "PLTR", "TYL", "MANH", "ROP", "DOCU"],
        "framework": "You are a senior enterprise SaaS analyst. Focus on Rule of 40 (growth-biased composition matters), NDR (>120% = expanding, watch 130->115 decline), RPO/cRPO growth vs revenue (best leading indicator), platform consolidation (CRWD 8+ modules, PANW), AI monetization (incremental $ vs retention), vertical SaaS durability (95%+ gross retention), FCF conversion (25-30% at scale). Consensus errors: NDR normalization overpenalized, cybersecurity counter-cyclical, platform companies 30x FCF actually cheap on 5yr DCF, PLTR dual-engine mispriced, vertical SaaS durability premium missing, ADBE AI threat narrative wrong 3 years running.",
    },
}


def _build_dynamic_context(symbols: list[str], expert_config: dict) -> str:
    if not symbols:
        return "No data available."
    symbol_list = ", ".join(f"'{s}'" for s in symbols[:25])
    context_parts = []
    macro = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    if macro:
        m = macro[0]
        context_parts.append(f"CURRENT MACRO REGIME: {m.get('regime', 'unknown')} (score: {m.get('total_score', 0):.0f}/100)\n  Fed={m.get('fed_funds_score', 0):.0f} YC={m.get('yield_curve_score', 0):.0f} Credit={m.get('credit_spreads_score', 0):.0f} VIX={m.get('vix_score', 0):.0f} DXY={m.get('dxy_score', 0):.0f}")
    fundamentals = query(f"SELECT symbol, metric, value FROM fundamentals WHERE symbol IN ({symbol_list}) ORDER BY symbol")
    technicals = query(f"SELECT t.symbol, t.total_score, t.trend_score, t.momentum_score FROM technical_scores t INNER JOIN (SELECT symbol, MAX(date) as mx FROM technical_scores WHERE symbol IN ({symbol_list}) GROUP BY symbol) m ON t.symbol = m.symbol AND t.date = m.mx")
    signals = query(f"SELECT s.symbol, s.signal, s.composite_score, s.rr_ratio FROM signals s INNER JOIN (SELECT symbol, MAX(date) as mx FROM signals WHERE symbol IN ({symbol_list}) GROUP BY symbol) m ON s.symbol = m.symbol AND s.date = m.mx")
    prices = query(f"SELECT p.symbol, p.close, (SELECT close FROM price_data p2 WHERE p2.symbol = p.symbol ORDER BY p2.date DESC LIMIT 1 OFFSET 5) as close_5d, (SELECT close FROM price_data p3 WHERE p3.symbol = p.symbol ORDER BY p3.date DESC LIMIT 1 OFFSET 21) as close_1m FROM price_data p INNER JOIN (SELECT symbol, MAX(date) as mx FROM price_data WHERE symbol IN ({symbol_list}) GROUP BY symbol) m ON p.symbol = m.symbol AND p.date = m.mx")
    price_map = {r["symbol"]: r for r in prices}
    fund_by_sym = {}
    for f in fundamentals:
        fund_by_sym.setdefault(f["symbol"], {})[f["metric"]] = f["value"]
    tech_map = {t["symbol"]: t for t in technicals}
    sig_map = {s["symbol"]: s for s in signals}
    context_parts.append("\nPER-STOCK CURRENT DATA:")
    for sym in symbols[:20]:
        lines = [f"\n  {sym}:"]
        p = price_map.get(sym)
        if p and p["close"]:
            price_str = f"    Price: ${p['close']:.2f}"
            if p.get("close_5d"):
                price_str += f" | 5d: {(p['close'] - p['close_5d']) / p['close_5d'] * 100:+.1f}%"
            if p.get("close_1m"):
                price_str += f" | 1m: {(p['close'] - p['close_1m']) / p['close_1m'] * 100:+.1f}%"
            lines.append(price_str)
        fd = fund_by_sym.get(sym, {})
        if fd:
            key_metrics = ["pe_ratio", "forward_pe", "revenue_growth", "earnings_growth", "roe", "debt_to_equity", "gross_margin", "operating_margin", "free_cash_flow_yield", "dividend_yield"]
            metrics = {k: fd[k] for k in key_metrics if k in fd}
            if metrics:
                lines.append(f"    Fundamentals: {', '.join(f'{k}={v:.2f}' for k, v in metrics.items())}")
        t = tech_map.get(sym)
        if t:
            lines.append(f"    Technical: {t['total_score']:.0f}/100 (trend={t['trend_score']:.0f}, momentum={t['momentum_score']:.0f})")
        s = sig_map.get(sym)
        if s:
            lines.append(f"    Signal: {s['signal']} (composite={s['composite_score']:.0f}, R:R={s.get('rr_ratio', 0):.1f})")
        bullish = fd.get("finnhub_analyst_bullish_pct")
        if bullish is not None:
            lines.append(f"    Analyst: {bullish:.0f}% bullish")
        if len(lines) > 1:
            context_parts.append("\n".join(lines))
    displacement = query(f"SELECT symbol, displacement_score, order_type, narrative FROM news_displacement WHERE symbol IN ({symbol_list}) AND date >= date('now', '-7 days') AND displacement_score >= 30 ORDER BY displacement_score DESC LIMIT 8")
    if displacement:
        context_parts.append("\nRECENT NEWS DISPLACEMENT SIGNALS:")
        for d in displacement:
            context_parts.append(f"  {d['symbol']}: score={d['displacement_score']:.0f} [{d['order_type']}] — {d['narrative'][:120]}")
    alt_signals = query(f"SELECT source, indicator, signal_direction, signal_strength, narrative FROM alternative_data WHERE date >= date('now', '-7 days') AND signal_strength >= 40 ORDER BY signal_strength DESC LIMIT 5")
    if alt_signals:
        context_parts.append("\nALTERNATIVE DATA SIGNALS:")
        for a in alt_signals:
            context_parts.append(f"  [{a['source']}] {a['signal_direction']} ({a['signal_strength']:.0f}) — {a['narrative'][:120]}")
    research = query(f"SELECT symbol, source, sentiment, relevance_score, article_summary FROM research_signals WHERE symbol IN ({symbol_list}) AND date >= date('now', '-7 days') AND relevance_score >= 60 ORDER BY relevance_score DESC LIMIT 5")
    if research:
        context_parts.append("\nRESEARCH INTELLIGENCE:")
        for r in research:
            context_parts.append(f"  {r['symbol']} ({r['source']}, {'bullish' if r['sentiment'] > 0 else 'bearish' if r['sentiment'] < 0 else 'neutral'}): {r['article_summary'][:120]}")
    foreign = query(f"SELECT symbol, market, sentiment, article_summary FROM foreign_intel_signals WHERE symbol IN ({symbol_list}) AND date >= date('now', '-7 days') AND relevance_score >= 60 AND symbol != 'UNMAPPED' ORDER BY relevance_score DESC LIMIT 3")
    if foreign:
        context_parts.append("\nFOREIGN INTELLIGENCE:")
        for f in foreign:
            context_parts.append(f"  {f['symbol']} ({f['market']}, {'bullish' if f['sentiment'] > 0 else 'bearish' if f['sentiment'] < 0 else 'neutral'}): {f['article_summary'][:120]}")
    smart = query(f"SELECT symbol, conviction_score, manager_count, top_holders FROM smart_money_scores WHERE symbol IN ({symbol_list}) AND conviction_score >= 50 ORDER BY conviction_score DESC LIMIT 5")
    if smart:
        context_parts.append("\nSMART MONEY POSITIONS:")
        for s in smart:
            context_parts.append(f"  {s['symbol']}: conviction={s['conviction_score']:.0f}, managers={s['manager_count']}")
    if expert_config["expert_type"] == "energy":
        eia = query("SELECT indicator_id, value FROM macro_indicators WHERE indicator_id LIKE 'PET.%' OR indicator_id LIKE 'NG.%' ORDER BY date DESC LIMIT 10")
        if eia:
            context_parts.append("\nEIA ENERGY DATA:")
            for e in eia:
                context_parts.append(f"  {e['indicator_id']}: {e['value']}")
    if expert_config["expert_type"] == "commodities":
        commodity_alt = query("SELECT source, indicator, value, signal_direction, signal_strength, narrative FROM alternative_data WHERE date >= date('now', '-7 days') AND source IN ('china_activity', 'baltic_dry', 'usda_crop') ORDER BY signal_strength DESC LIMIT 8")
        if commodity_alt:
            context_parts.append("\nCOMMODITY-RELEVANT ALTERNATIVE DATA:")
            for c in commodity_alt:
                context_parts.append(f"  [{c['source']}] {c['indicator']}: {c['signal_direction']} (strength={c['signal_strength']:.0f}) — {c['narrative'][:120]}")
    if expert_config["expert_type"] == "utilities":
        rates = query("SELECT indicator_id, value FROM macro_indicators WHERE indicator_id IN ('DGS10', 'DGS2', 'T10Y2Y') ORDER BY date DESC LIMIT 3")
        if rates:
            context_parts.append("\nINTEREST RATE DATA:")
            for r in rates:
                context_parts.append(f"  {r['indicator_id']}: {r['value']}")
    return "\n".join(context_parts) if context_parts else "Limited data available."


def _analyze_sector(expert_config: dict, symbols: list[str]) -> list[dict]:
    if not GEMINI_API_KEY or not symbols:
        return []
    context = _build_dynamic_context(symbols, expert_config)
    prompt = f"""{expert_config['framework']}

TODAY'S DATE: {datetime.now().strftime("%Y-%m-%d")}

LIVE DATA FOR YOUR SECTOR ({", ".join(symbols[:20])}):
{context}

TASK: Identify stocks where the market is CURRENTLY mispricing something specific. Reference specific numbers/scores/signals. For each displacement, output JSON:
{{"symbol": "<ticker>", "sector_displacement_score": <0-100>, "consensus_narrative": "<1 sentence>", "variant_narrative": "<1 sentence>", "direction": "bullish"/"bearish", "conviction_level": "high"/"medium"/"low", "key_catalysts": ["<event with date>"], "leading_indicators": ["<measurable thing>"]}}

RULES: Reference SPECIFIC data. Only flag CONCRETE mismatches. Score 80+ only for clear, imminent mispricing. Empty array [] if nothing mispriced. Return JSON array only."""
    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"}, params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}},
            timeout=45)
        resp.raise_for_status()
        raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        results = json.loads(raw)
        return results if isinstance(results, list) else [results]
    except Exception as e:
        print(f"    Gemini analysis failed for {expert_config['expert_type']}: {e}")
        return []


def run():
    """Run all sector expert analyses."""
    init_db()
    today = date.today().isoformat()
    print("\n" + "=" * 60 + "\n  SECTOR EXPERT ANALYSIS (DYNAMIC)\n" + "=" * 60)
    if not GEMINI_API_KEY:
        print("  ERROR: GEMINI_API_KEY not set"); return
    universe = query("SELECT symbol, sector FROM stock_universe WHERE sector IS NOT NULL")
    sector_symbols = {}
    for r in universe:
        sector_symbols.setdefault(r["sector"], []).append(r["symbol"])
    total_signals = 0
    for expert_name, expert_config in SECTOR_EXPERTS.items():
        matching_symbols = list(expert_config.get("core_tickers", []))
        for sector_name in expert_config["sectors"]:
            for db_sector, syms in sector_symbols.items():
                if sector_name.lower() in db_sector.lower():
                    matching_symbols.extend(syms)
        matching_symbols = list(dict.fromkeys(matching_symbols))[:25]
        if not matching_symbols:
            print(f"  [{expert_name.upper()}] No matching symbols"); continue
        print(f"  [{expert_name.upper()}] Analyzing {len(matching_symbols)} stocks...")
        assessments = _analyze_sector(expert_config, matching_symbols)
        if not assessments:
            print(f"    No displacement signals found"); continue
        rows = []
        for a in assessments:
            sym = a.get("symbol", "")
            score = a.get("sector_displacement_score", 0)
            if not sym or score < 30:
                continue
            rows.append((sym, today, expert_config["sectors"][0], expert_config["expert_type"], score,
                a.get("consensus_narrative", ""), a.get("variant_narrative", ""),
                json.dumps(a.get("leading_indicators", [])), a.get("conviction_level", "low"),
                a.get("direction", "neutral"), json.dumps(a.get("key_catalysts", [])),
                f"{a.get('direction', 'neutral').title()} — {a.get('variant_narrative', '')}"))
        if rows:
            with get_conn() as conn:
                conn.executemany("""INSERT OR REPLACE INTO sector_expert_signals
                    (symbol, date, sector, expert_type, sector_displacement_score,
                     consensus_narrative, variant_narrative, leading_indicators,
                     conviction_level, direction, key_catalysts, narrative)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
            total_signals += len(rows)
            print(f"    {len(rows)} displacement signals stored")
            for r in sorted(rows, key=lambda x: x[4], reverse=True)[:3]:
                print(f"    {r[0]}: score={r[4]:.0f} {r[9]} — {r[6][:60]}...")
        time.sleep(2)
    print(f"\n  Sector expert analysis complete: {total_signals} signals across {len(SECTOR_EXPERTS)} experts")
    print("=" * 60)


if __name__ == "__main__":
    run()
