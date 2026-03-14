"""Sector Expert Agents — dynamic domain intelligence for displacement detection.

Each expert combines:
  1. Analytical framework (what to look for, common consensus errors)
  2. LIVE data pulled from the DB (prices, fundamentals, technicals, news,
     macro regime, alternative data, research signals)

The expert sees the CURRENT state of its sector, not stale descriptions.
It identifies where consensus is structurally wrong RIGHT NOW.

Experts:
  - AI/Compute: GPU supply chain, hyperscaler capex, compute scaling
  - Energy: OPEC+, EIA inventories, crack spreads, power demand
  - Biotech: FDA pipeline, patent cliffs, binary catalysts
  - Semiconductors: inventory cycles, memory pricing, equipment bookings
  - Real Estate: cap rates, data center demand, rate sensitivity
  - Defense: backlog, margin ramp, geopolitical spending
  - Financials: NIM, credit quality, capital return
  - Commodities: copper, gold, agriculture, lithium, physical indicators
  - Utilities: rate base growth, nuclear, AI power demand, water
  - Fintech: payments, crypto infra, digital banking, embedded finance
  - SaaS/Cloud: enterprise SaaS, cybersecurity, vertical SaaS, platform consolidation

Usage: python -m tools.sector_experts
"""

import sys
import json
import re
import time
from datetime import date, datetime
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.config import GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL
from tools.db import init_db, get_conn, query


# ── Expert Definitions ───────────────────────────────────────────────
# Framework only — the DATA comes from _build_dynamic_context()

SECTOR_EXPERTS = {
    "ai_compute": {
        "expert_type": "ai_compute",
        "sectors": ["Technology", "Semiconductors", "Software", "Communication Services"],
        "core_tickers": ["NVDA", "AMD", "TSM", "ASML", "AMAT", "LRCX", "MSFT", "GOOGL", "META", "AMZN", "ORCL", "AVGO", "MRVL", "EQIX", "DLR", "VST", "CEG", "NRG"],
        "framework": """You are a senior AI/compute infrastructure analyst. Your edge is understanding the physical constraints of the AI buildout.

ANALYTICAL FRAMEWORK:
- GPU supply chain: NVDA (CUDA moat), AMD (MI300 challenger), TSM (CoWoS packaging bottleneck), ASML (EUV monopoly)
- HBM allocation: SK Hynix leads, Samsung catching up. HBM is the binding constraint on GPU production
- Hyperscaler capex: When multiple hyperscalers raise capex simultaneously = demand is real. Watch quarterly guidance
- Power demand: Each 100K GPU cluster = ~1GW. Grid interconnection takes 3-5 years. Power is the ultimate bottleneck
- Inference vs Training mix: Training drives GPU demand, inference drives edge/efficiency plays. The ratio matters

COMMON CONSENSUS ERRORS:
- Market underestimates duration of capex supercycles (3-5 years not 1-2)
- Power infrastructure stocks (VST, CEG, NRG) often mispriced as utilities when they're AI plays
- CoWoS/packaging constraints mean NVDA supply, not demand, is the bottleneck
- Inference demand scales non-linearly — market extrapolates training growth to inference incorrectly""",
    },

    "energy": {
        "expert_type": "energy",
        "sectors": ["Energy", "Oil & Gas"],
        "core_tickers": ["OXY", "COP", "XOM", "CVX", "DVN", "FANG", "EOG", "MPC", "VLO", "PSX", "ET", "LNG", "VST", "CEG", "NRG"],
        "framework": """You are a senior energy analyst with deep knowledge of physical supply-demand balances.

ANALYTICAL FRAMEWORK:
- OPEC+ compliance: actual production vs quotas. Cheating = bearish, compliance = supportive
- US shale: rig count trend, well productivity, DUC inventory, decline rate. Shale response to price is the swing factor
- EIA weekly data: crude stocks vs seasonal norms, refinery utilization, gasoline demand, nat gas storage
- Crack spreads: 3-2-1 crack spread measures refiner profitability. Wide cracks = refiner earnings beats
- LNG exports: structural growth story. Henry Hub vs JKM/TTF basis = US gas demand floor
- Power demand: AI data centers creating NEW structural demand for baseload power. Nuclear renaissance = real
- Break-even analysis: which producers make money at current strip? Sort by break-even, buy cheapest with catalysts

COMMON CONSENSUS ERRORS:
- Market assumes shale can grow forever (decline rates accelerating, tier-1 inventory depleting)
- OPEC+ is more disciplined than market expects (Saudi needs $80+ Brent for fiscal balance)
- Energy transition timeline always overestimated — fossil fuels needed for decades
- AI power demand is genuinely additive — not substitution, pure new demand growth""",
    },

    "biotech": {
        "expert_type": "biotech",
        "sectors": ["Healthcare", "Biotechnology", "Pharmaceuticals"],
        "core_tickers": ["LLY", "ABBV", "MRK", "PFE", "JNJ", "BMY", "AMGN", "GILD", "REGN", "VRTX", "BIIB", "MRNA"],
        "framework": """You are a senior biotech/pharma analyst with 15 years covering FDA pipelines.

ANALYTICAL FRAMEWORK:
- FDA PDUFA dates: binary events the market often misprices. Approval probability for drugs with positive Phase 3 + BTD is >90%
- Patent cliff timing: When does exclusivity expire? Biologic biosimilar erosion is SLOWER than market expects (30-50% over 3-5yr, not 80% in 1yr)
- Pipeline optionality: how many shots on goal? Small-cap with 3+ late-stage programs = undervalued option portfolio
- GLP-1 revolution: LLY/NVO dominating. Total TAM $100B+. Second-order effects on medical devices, bariatric surgery
- Cash runway: <18 months = dilution risk. >3 years = can fund through next catalyst

COMMON CONSENSUS ERRORS:
- Market overweights single trial failures, ignores pipeline depth
- Patent cliff stocks often oversold 18-24 months before expiry
- Rare disease revenue sustainability underestimated (orphan drug exclusivity = 7yr moat)
- Phase 2→3 transition probability mispriced in small caps""",
    },

    "semiconductors": {
        "expert_type": "semiconductors",
        "sectors": ["Semiconductors", "Semiconductor Equipment"],
        "core_tickers": ["NVDA", "AMD", "INTC", "TSM", "ASML", "AMAT", "LRCX", "KLAC", "MU", "MRVL", "AVGO", "QCOM", "TXN", "ON", "ADI"],
        "framework": """You are a senior semiconductor analyst with deep knowledge of cycle dynamics.

ANALYTICAL FRAMEWORK:
- Cycle position: Where are we? Downturn→Trough→Recovery→Peak. Stocks bottom 1-2 quarters before earnings trough
- Memory pricing: DRAM/NAND spot vs contract prices. 2+ consecutive quarters of rising contract prices = upcycle has legs
- Equipment bookings: ASML orders = leading indicator for future wafer capacity. Rising orders = cycle turning up
- Inventory: Channel inventories building (bearish) or depleting (bullish)? Check distribution reports
- Foundry utilization: TSMC monthly revenue as proxy. Below 80% = pressure, above 90% = pricing power
- HBM premium: 3-5x ASP vs commodity DDR5. Allocated 4+ quarters out. Scarcity = pricing power

COMMON CONSENSUS ERRORS:
- Memory cycle: market ALWAYS extrapolates current pricing too far in both directions
- Equipment stocks bottom before semis (capex cut = future supply constraint = bullish)
- AI GPU demand masks consumer/auto/industrial weakness (or vice versa)
- Inventory correction duration overestimated by 1-2 quarters""",
    },

    "realestate": {
        "expert_type": "realestate",
        "sectors": ["Real Estate", "REITs"],
        "core_tickers": ["EQIX", "DLR", "PLD", "AMT", "SPG", "O", "VICI", "PSA", "EQR", "AVB", "WELL", "VTR"],
        "framework": """You are a senior REIT/real estate analyst specializing in structural shifts.

ANALYTICAL FRAMEWORK:
- Cap rate spreads: Current cap rate minus 10Y Treasury yield. >250bps = REITs cheap, <150bps = expensive
- Data center demand: AI-driven power/space needs growing 25-30% vs supply growing 10-15% = pricing power
- Office reality: Class A urban trophy is NOT the same as suburban commodity. Vacancy varies 10-30% by quality
- Rate sensitivity: REITs with long-duration fixed-rate debt (7+ yr WAM) are LESS rate-sensitive than market assumes
- NAV discount: When public REITs trade at >20% discount to private market values = buyback/takeout opportunity
- Debt maturity wall: Companies that locked in 2020-2021 rates face 200-300bps higher refinancing costs

COMMON CONSENSUS ERRORS:
- All office REITs treated as equally doomed (Class A urban holding up)
- Data center REITs undervalued when power constraints limit new supply
- Rate sensitivity overestimated for fixed-rate debt REITs
- Senior housing (WELL, VTR) demographics ignored: baby boomer demand + zero new supply""",
    },

    "defense": {
        "expert_type": "defense",
        "sectors": ["Aerospace & Defense", "Industrials"],
        "core_tickers": ["LMT", "RTX", "NOC", "GD", "BA", "LHX", "HII", "TDG", "HEI", "AXON"],
        "framework": """You are a senior defense/aerospace analyst with government contract expertise.

ANALYTICAL FRAMEWORK:
- Backlog analysis: Book-to-bill >1.1x for 2+ quarters = accelerating revenue ahead. Funded vs unfunded backlog matters
- Margin ramp: Development (cost-plus, 5-8% margins) → Production (fixed-price, 12-15% margins). This transition is underestimated
- Budget trajectory: Bipartisan support for defense spending. 3-5% real growth trajectory. Watch NDAA and appropriations bills
- Geopolitical catalysts: NATO 2% GDP commitment, European rearmament post-Ukraine, Indo-Pacific buildup
- International FMS: Foreign Military Sales pipeline $80B+. Each win = 20+ year sustainment revenue
- Munitions replenishment: Ukraine/Middle East depleted stocks → multi-year replacement orders

COMMON CONSENSUS ERRORS:
- Multi-year backlog = visible but underappreciated earnings durability
- Production ramp margin expansion surprises to the upside
- International sales cycles longer than expected but LARGER than anticipated
- Budget sequestration fears overblown — bipartisan support is real""",
    },

    "financials": {
        "expert_type": "financials",
        "sectors": ["Financial Services", "Banks", "Insurance", "Capital Markets"],
        "core_tickers": ["JPM", "BAC", "WFC", "GS", "MS", "C", "SCHW", "BLK", "AXP", "V", "MA", "PGR", "TRV", "ALL", "MET"],
        "framework": """You are a senior financial sector analyst specializing in bank/insurance economics.

ANALYTICAL FRAMEWORK:
- NIM trajectory: Asset-sensitive banks benefit from rate rises, liability-sensitive from cuts. Yield curve shape is the #1 driver
- Credit cycle position: Early delinquencies → provisions build → charge-offs peak → reserve release. Buy at peak provisions (trough earnings)
- Capital return: CET1 ratio vs regulatory minimum. Excess capital = buybacks. JPM/BAC/WFC buy back 3-5% of shares annually
- Insurance hard market: P&C premiums rising 5-15% annually. Combined ratios below 93% = printing money. Hard markets last 3-5 years
- Yield curve signal: 2s10s spread widening = bank stocks rally 15-25% over 6 months. Most reliable predictor

COMMON CONSENSUS ERRORS:
- NIM compression fears overblown when yield curve steepens
- Credit losses come later than expected but market prices them in EARLY (buy the panic)
- Regional banks oversold during stress events (deposit flight fear > reality)
- Insurance hard market duration underestimated (3-5 years not 1-2)""",
    },
    "commodities": {
        "expert_type": "commodities",
        "sectors": ["Materials", "Mining", "Metals & Mining", "Agriculture"],
        "core_tickers": ["BHP", "RIO", "VALE", "FCX", "NEM", "SCCO", "CLF", "X", "AA", "ADM", "BG", "MOS", "CF", "NTR", "CTVA", "DE", "GLD", "SLV"],
        "framework": """You are a senior commodities analyst with deep knowledge of physical supply-demand balances across metals, agriculture, and industrial materials.

ANALYTICAL FRAMEWORK:
- Copper: The "Dr. Copper" thesis — best real-time gauge of global industrial activity. China = 50%+ of demand. Supply constrained (no major new mines for 5+ years). Electrification/EVs = structural demand growth
- Gold: Rates reality vs narrative. Real rates (TIPS yield) are the driver, not nominal. Central bank buying is structural ($1T+ reserves diversification). DXY inverse correlation
- Iron ore/Steel: China property = demand driver. Blast furnace utilization, rebar/HRC spread. Australian/Brazilian supply discipline matters
- Agriculture: Weather-driven cycles. USDA WASDE reports = key catalyst. Fertilizer costs (MOS, CF, NTR) drive farmer profitability. China stockpiling behavior
- Lithium/Battery metals: EV adoption curve. Supply response from Albemarle, SQM, Pilbara. Oversupply cycle → eventual deficit as mines close
- Industrial metals: PMI correlation. When global PMIs inflect from contraction to expansion = buy materials

KEY PHYSICAL INDICATORS:
- LME warehouse inventories (copper, aluminum, zinc) — depletion = tightening
- COMEX positioning — managed money net long/short
- China PMI (Caixin manufacturing) — leading indicator for metals demand
- Baltic Dry Index — shipping demand = real trade activity
- Fertilizer prices (DAP, urea, potash) — input costs for ag profitability

COMMON CONSENSUS ERRORS:
- Market assumes commodity supply can respond quickly (new mines take 7-10 years)
- China demand always written off too early ("property collapse" narrative vs actual import data)
- Agricultural supply disruptions underpriced until inventories are visibly low
- Gold rallies in BOTH rate cutting AND crisis environments — not just one
- Copper structural deficit underappreciated: electrification + AI power demand = new supercycle argument""",
    },

    "utilities": {
        "expert_type": "utilities",
        "sectors": ["Utilities", "Electric Utilities", "Gas Utilities", "Water Utilities", "Independent Power Producers"],
        "core_tickers": ["NEE", "DUK", "SO", "AEP", "XEL", "D", "EIX", "PCG", "PNW", "ES",
                         "NI", "ATO", "SWX", "AWK", "WTRG", "SJW", "CWT",
                         "VST", "CEG", "NRG", "AES", "BEP", "CWEN"],
        "framework": """You are a senior utilities analyst with deep knowledge of rate case mechanics and power market dynamics.

ANALYTICAL FRAMEWORK:
- Rate base growth: The mechanical EPS growth driver. 6-8% rate base CAGR = 6-8% earnings growth. Watch capex plans and rider mechanisms
- Regulatory quality: Constructive PUCs (Georgia, Indiana, Texas) vs adversarial (California, Connecticut). Regulatory lag matters enormously
- AI power demand: Data center interconnection queues growing exponentially. Utilities with service territories near data center clusters benefit most (D, PNW, SO)
- Grid modernization: $2T+ in T&D investment needed. Transformer shortage, substation backlogs = multi-year capex visibility
- Interest rate sensitivity: Utilities are long-duration assets. Rising rates compress P/Es. But rate base growth can offset if fast enough
- Nuclear fleet value: Post-Fukushima derating was wrong. Nuclear is the only 24/7 carbon-free baseload. PPAs repricing dramatically higher
- Water utilities: Natural monopoly franchises, zero competition, M&A consolidation of 50K+ municipal systems. Premium valuations justified
- Gas pipe replacement: Multi-decade infrastructure replacement programs = 8-10% rate base CAGR with formula rate mechanisms

COMMON CONSENSUS ERRORS:
- Market treats all utilities as bond proxies (growth utilities with 7%+ rate base CAGR are growth stocks)
- AI power demand impact underestimated for utilities with data center service territories (D, PNW, SO)
- Nuclear fleet value still mispriced despite Microsoft/Google PPAs proving the thesis
- Wildfire risk in California is now manageable (wildfire funds, undergrounding, insurance) — market still penalizes excessively
- Water utilities premium is justified by monopoly franchise + acquisition-driven growth
- IPPs (VST, CEG, NRG) are NOT utilities — they are power market / AI infrastructure plays with different valuation frameworks""",
    },

    "fintech": {
        "expert_type": "fintech",
        "sectors": ["Financials", "Information Technology"],
        "core_tickers": ["PYPL", "XYZ", "COIN", "HOOD", "FISV", "FIS", "GPN", "FOUR", "SYF", "CPAY", "BILL", "GWRE", "IBKR", "ALLY", "COF", "WEX"],
        "framework": """You are a senior fintech analyst covering payments, digital banking, crypto infrastructure, and embedded finance. Your edge is understanding unit economics inflection points that traditional bank analysts miss because they model fintech like banks instead of like software platforms.

ANALYTICAL FRAMEWORK:
- Take rate trajectory: Payment processors (PYPL, XYZ, GPN, FISV) live and die by take rate basis points. Declining take rate with rising volume is healthy (scale); declining take rate with flat volume is competitive displacement. Track take rate * TPV growth = revenue growth
- BNPL/credit mix: PYPL, XYZ, SYF, ALLY are increasingly lending businesses. Net charge-off rate vs net interest margin spread is the real P&L driver. NCO >6% on unsecured consumer = trouble. Watch delinquency roll rates (30->60->90 day transition rates) as leading indicator
- Crypto infrastructure vs speculation: COIN revenue is 85%+ transaction-based and wildly cyclical. Staking revenue + custody + Base L2 fees are the secular story. HOOD crypto revenue similarly binary. Separate transaction revenue (cyclical) from infrastructure revenue (durable)
- Embedded finance TAM: Merchant cash advances (XYZ), BNPL (PYPL), vertical SaaS payments (FOUR, BILL) — when software companies monetize financial services, attach rates of 2-5% on embedded payments are 10-20x the margin of the software itself
- Interchange regulation risk: Durbin amendment expansion to credit cards would compress V/MA margins 20-30bps — but more critically would compress FISV/FIS/GPN processing margins. Watch CFPB rulemaking and Congressional markup language
- Deposit cost arbitrage: Digital banks (ALLY, COF) fund at 50-100bps below branch-heavy banks but market prices them at same NIM multiple. Funding advantage is structural, not cyclical
- Insurance technology: GWRE is the Salesforce of P&C insurance — 70%+ of top-50 carriers on platform. Cloud migration ARR inflection creates multi-year re-rating as perpetual license converts to subscription

COMMON CONSENSUS ERRORS:
- PYPL perennially mispriced on Braintree branded vs unbranded volume mix — branded checkout margin is 4-5x unbranded, and branded share is stabilizing after 3 years of decline. Market extrapolates unbranded growth as dilutive when mix is actually inflecting
- COIN valued as pure crypto speculation when custody + staking + Base L2 are building durable infrastructure revenue. At cycle troughs, infrastructure revenue alone can support a $15-20B floor valuation
- Market treats all payment processors as identical when vertical specialization creates 200-400bps take rate premiums (FOUR in restaurants/hospitality, CPAY in fleet/corporate, WEX in benefits)
- Digital bank credit losses are over-extrapolated from subprime vintages — ALLY auto loss severity peaked and recovery rates are improving, but stock still prices in peak NCOs
- FIS post-Worldpay separation is a clean banking technology story trading at discount — market hasn't re-rated it from conglomerate discount despite pure-play status
- HOOD dismissed as meme stock platform when it has the lowest customer acquisition cost in brokerage ($30-50 vs $200-500 at SCHW) and fastest growing gold subscriber base (recurring revenue)""",
    },

    "saas_cloud": {
        "expert_type": "saas_cloud",
        "sectors": ["Information Technology", "Communication Services"],
        "core_tickers": ["CRM", "NOW", "CRWD", "PANW", "DDOG", "FTNT", "WDAY", "ADBE", "INTU", "OKTA", "TWLO", "PLTR", "TYL", "MANH", "ROP", "DOCU"],
        "framework": """You are a senior enterprise software analyst specializing in SaaS business model dynamics. Your edge is understanding when recurring revenue compounding creates non-linear value inflections that traditional tech analysts miss by focusing on quarterly revenue beats instead of cohort economics.

ANALYTICAL FRAMEWORK:
- Rule of 40 as quality filter: Revenue growth % + FCF margin % must exceed 40 for best-in-class. But the COMPOSITION matters — 35% growth + 10% margin is worth a premium over 10% growth + 35% margin because growth compounds. Sort by Rule of 40 then weight toward growth-biased names
- Net dollar retention (NDR): >120% = customers expanding faster than churning, the business grows even with zero new logos. NDR 130%+ (DDOG, CRWD, NOW historically) justifies 15-20x revenue. NDR declining from 130 to 115 over 3 quarters = seat expansion exhaustion, not just tough comps — watch for this inflection
- RPO and cRPO growth vs revenue: Remaining Performance Obligations (RPO) is contracted future revenue. When cRPO growth exceeds revenue growth by 5%+ for 2 consecutive quarters, revenue is about to accelerate. When cRPO decelerates below revenue growth, the opposite. This is the single best leading indicator for SaaS
- Platform consolidation: Cybersecurity is consolidating from 30+ point solutions to 3-5 platforms. CRWD (endpoint->cloud->identity) and PANW (firewall->SASE->SOC) are the winners. Module attach rates (CRWD: avg 8+ modules per customer vs 5 two years ago) drive NDR expansion without new logos
- AI monetization reality vs hype: ACTUAL incremental AI revenue contribution matters. CRM Einstein GPT, NOW AI agents, PLTR AIP — separate companies charging incremental dollars for AI features (durable) from companies just adding AI to existing SKUs for retention (no incremental revenue). Track AI-specific ARR disclosures
- Vertical SaaS durability: TYL (government), MANH (supply chain), ROP portfolio — vertical SaaS has 95%+ gross retention because switching costs are extreme (re-implementation takes 12-24 months). Market undervalues this durability by applying horizontal SaaS multiples
- FCF conversion: SaaS should convert 25-30% of revenue to unlevered FCF at scale. Companies below 20% despite scale (OKTA, WDAY historically) have cost structure problems. Companies above 35% (ADBE, INTU, FTNT) are under-earning on growth — watch for growth re-acceleration catalysts

COMMON CONSENSUS ERRORS:
- Market over-penalizes NDR deceleration from 135% to 120% — 120% NDR is still excellent and the 135% was the anomaly (COVID pull-forward). Names like DDOG and TWLO get crushed on NDR normalization when the absolute level is still best-in-class
- Cybersecurity spending is non-discretionary and counter-cyclical. In every recession since 2008, security budgets grew while overall IT budgets contracted. CRWD, PANW, and FTNT drawdowns during macro fear = buying opportunities with 6-12 month payoffs of 30-50%
- Platform companies (CRM, NOW, INTU) trading at 30x FCF are actually cheap when you model 15-20% FCF compounding for 5+ years — the terminal value at 20x FCF in year 5 implies 15%+ IRR from current prices, which most investors miss by anchoring on current-year multiples
- PLTR is systematically mispriced by sell-side because government contract revenue (55% of total) has 98% renewal rates and AIP commercial traction is creating a second growth curve — the dual-engine model is unique and analysts model each segment independently instead of seeing the platform flywheel
- Vertical SaaS (TYL, MANH, ROP subsidiaries) trades at discounts to horizontal SaaS despite HIGHER gross retention, LOWER churn, and MORE predictable revenue — the market applies a "boring" discount to names that should command a durability premium
- ADBE is repeatedly written off as "disrupted by AI" when its actual AI features (Firefly, Generative Fill) are driving higher engagement and upsell to premium tiers — every AI threat narrative for ADBE has been wrong for 3 consecutive years""",
    },
}


# ── Dynamic Context Builder ──────────────────────────────────────────

def _build_dynamic_context(symbols: list[str], expert_config: dict) -> str:
    """Build rich, LIVE data context for the expert from the database.

    This is what makes the analysis dynamic — every run pulls fresh data.
    """
    if not symbols:
        return "No data available."

    symbol_list = ", ".join(f"'{s}'" for s in symbols[:25])
    context_parts = []

    # 1. Current macro regime (affects ALL sectors)
    macro = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    if macro:
        m = macro[0]
        context_parts.append(
            f"CURRENT MACRO REGIME: {m.get('regime', 'unknown')} (score: {m.get('total_score', 0):.0f}/100)\n"
            f"  Fed Funds: {m.get('fed_funds_score', 0):.0f} | Yield Curve: {m.get('yield_curve_score', 0):.0f} | "
            f"Credit Spreads: {m.get('credit_spreads_score', 0):.0f} | VIX: {m.get('vix_score', 0):.0f} | DXY: {m.get('dxy_score', 0):.0f}"
        )

    # 2. Per-symbol fundamentals + technicals + signals
    fundamentals = query(f"""
        SELECT symbol, metric, value FROM fundamentals
        WHERE symbol IN ({symbol_list})
        ORDER BY symbol
    """)
    technicals = query(f"""
        SELECT t.symbol, t.total_score, t.trend_score, t.momentum_score
        FROM technical_scores t
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM technical_scores
                    WHERE symbol IN ({symbol_list}) GROUP BY symbol) m
        ON t.symbol = m.symbol AND t.date = m.mx
    """)
    signals = query(f"""
        SELECT s.symbol, s.signal, s.composite_score, s.rr_ratio
        FROM signals s
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM signals
                    WHERE symbol IN ({symbol_list}) GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.mx
    """)

    # Recent price performance
    prices = query(f"""
        SELECT p.symbol, p.close,
               (SELECT close FROM price_data p2 WHERE p2.symbol = p.symbol
                ORDER BY p2.date DESC LIMIT 1 OFFSET 5) as close_5d,
               (SELECT close FROM price_data p3 WHERE p3.symbol = p.symbol
                ORDER BY p3.date DESC LIMIT 1 OFFSET 21) as close_1m
        FROM price_data p
        INNER JOIN (SELECT symbol, MAX(date) as mx FROM price_data
                    WHERE symbol IN ({symbol_list}) GROUP BY symbol) m
        ON p.symbol = m.symbol AND p.date = m.mx
    """)
    price_map = {r["symbol"]: r for r in prices}

    # Build per-symbol fundamentals map
    fund_by_sym = {}
    for f in fundamentals:
        if f["symbol"] not in fund_by_sym:
            fund_by_sym[f["symbol"]] = {}
        fund_by_sym[f["symbol"]][f["metric"]] = f["value"]

    tech_map = {t["symbol"]: t for t in technicals}
    sig_map = {s["symbol"]: s for s in signals}

    context_parts.append("\nPER-STOCK CURRENT DATA:")
    for sym in symbols[:20]:
        lines = [f"\n  {sym}:"]
        # Price
        p = price_map.get(sym)
        if p and p["close"]:
            price_str = f"    Price: ${p['close']:.2f}"
            if p.get("close_5d"):
                chg_5d = (p["close"] - p["close_5d"]) / p["close_5d"] * 100
                price_str += f" | 5d: {chg_5d:+.1f}%"
            if p.get("close_1m"):
                chg_1m = (p["close"] - p["close_1m"]) / p["close_1m"] * 100
                price_str += f" | 1m: {chg_1m:+.1f}%"
            lines.append(price_str)

        # Fundamentals
        fd = fund_by_sym.get(sym, {})
        if fd:
            key_metrics = ["pe_ratio", "forward_pe", "revenue_growth", "earnings_growth",
                           "roe", "debt_to_equity", "gross_margin", "operating_margin",
                           "free_cash_flow_yield", "dividend_yield"]
            metrics = {k: fd[k] for k in key_metrics if k in fd}
            if metrics:
                lines.append(f"    Fundamentals: {', '.join(f'{k}={v:.2f}' for k, v in metrics.items())}")

        # Technical
        t = tech_map.get(sym)
        if t:
            lines.append(f"    Technical: {t['total_score']:.0f}/100 (trend={t['trend_score']:.0f}, momentum={t['momentum_score']:.0f})")

        # Signal
        s = sig_map.get(sym)
        if s:
            lines.append(f"    Signal: {s['signal']} (composite={s['composite_score']:.0f}, R:R={s.get('rr_ratio', 0):.1f})")

        # Analyst sentiment from fundamentals
        bullish = fd.get("finnhub_analyst_bullish_pct")
        if bullish is not None:
            lines.append(f"    Analyst: {bullish:.0f}% bullish")

        if len(lines) > 1:
            context_parts.append("\n".join(lines))

    # 3. Recent news displacement signals for this sector
    displacement = query(f"""
        SELECT symbol, displacement_score, order_type, narrative
        FROM news_displacement
        WHERE symbol IN ({symbol_list})
          AND date >= date('now', '-7 days')
          AND displacement_score >= 30
        ORDER BY displacement_score DESC LIMIT 8
    """)
    if displacement:
        context_parts.append("\nRECENT NEWS DISPLACEMENT SIGNALS (material news not priced in):")
        for d in displacement:
            context_parts.append(f"  {d['symbol']}: score={d['displacement_score']:.0f} [{d['order_type']}] — {d['narrative'][:120]}")

    # 4. Alternative data signals affecting this sector
    alt_signals = query(f"""
        SELECT source, indicator, signal_direction, signal_strength, narrative
        FROM alternative_data
        WHERE date >= date('now', '-7 days')
          AND signal_strength >= 40
        ORDER BY signal_strength DESC LIMIT 5
    """)
    if alt_signals:
        context_parts.append("\nALTERNATIVE DATA SIGNALS (physical-world indicators):")
        for a in alt_signals:
            context_parts.append(f"  [{a['source']}] {a['signal_direction']} ({a['signal_strength']:.0f}) — {a['narrative'][:120]}")

    # 5. Research intelligence
    research = query(f"""
        SELECT symbol, source, sentiment, relevance_score, article_summary
        FROM research_signals
        WHERE symbol IN ({symbol_list})
          AND date >= date('now', '-7 days')
          AND relevance_score >= 60
        ORDER BY relevance_score DESC LIMIT 5
    """)
    if research:
        context_parts.append("\nRESEARCH INTELLIGENCE (curated sources):")
        for r in research:
            sentiment_label = "bullish" if r["sentiment"] > 0 else "bearish" if r["sentiment"] < 0 else "neutral"
            context_parts.append(f"  {r['symbol']} ({r['source']}, {sentiment_label}): {r['article_summary'][:120]}")

    # 6. Foreign intel
    foreign = query(f"""
        SELECT symbol, market, sentiment, article_summary
        FROM foreign_intel_signals
        WHERE symbol IN ({symbol_list})
          AND date >= date('now', '-7 days')
          AND relevance_score >= 60
          AND symbol != 'UNMAPPED'
        ORDER BY relevance_score DESC LIMIT 3
    """)
    if foreign:
        context_parts.append("\nFOREIGN INTELLIGENCE:")
        for f in foreign:
            sent = "bullish" if f["sentiment"] > 0 else "bearish" if f["sentiment"] < 0 else "neutral"
            context_parts.append(f"  {f['symbol']} ({f['market']}, {sent}): {f['article_summary'][:120]}")

    # 7. Smart money activity
    smart = query(f"""
        SELECT symbol, conviction_score, manager_count, top_holders
        FROM smart_money_scores
        WHERE symbol IN ({symbol_list})
          AND conviction_score >= 50
        ORDER BY conviction_score DESC LIMIT 5
    """)
    if smart:
        context_parts.append("\nSMART MONEY POSITIONS (13F filings):")
        for s in smart:
            context_parts.append(f"  {s['symbol']}: conviction={s['conviction_score']:.0f}, managers={s['manager_count']}")

    # 8. EIA data for energy expert
    if expert_config["expert_type"] == "energy":
        eia = query("""
            SELECT indicator_id, value FROM macro_indicators
            WHERE indicator_id LIKE 'PET.%' OR indicator_id LIKE 'NG.%'
            ORDER BY date DESC LIMIT 10
        """)
        if eia:
            context_parts.append("\nEIA ENERGY DATA (latest):")
            for e in eia:
                context_parts.append(f"  {e['indicator_id']}: {e['value']}")

    # 9. Commodity-specific data: alt data signals (China activity, Baltic Dry, crop data)
    if expert_config["expert_type"] == "commodities":
        commodity_alt = query("""
            SELECT source, indicator, value, signal_direction, signal_strength, narrative
            FROM alternative_data
            WHERE date >= date('now', '-7 days')
              AND source IN ('china_activity', 'baltic_dry', 'usda_crop')
            ORDER BY signal_strength DESC LIMIT 8
        """)
        if commodity_alt:
            context_parts.append("\nCOMMODITY-RELEVANT ALTERNATIVE DATA:")
            for c in commodity_alt:
                context_parts.append(f"  [{c['source']}] {c['indicator']}: {c['signal_direction']} "
                                     f"(strength={c['signal_strength']:.0f}) — {c['narrative'][:120]}")

    # 10. Interest rate data for utilities expert
    if expert_config["expert_type"] == "utilities":
        rates = query("""
            SELECT indicator_id, value FROM macro_indicators
            WHERE indicator_id IN ('DGS10', 'DGS2', 'T10Y2Y')
            ORDER BY date DESC LIMIT 3
        """)
        if rates:
            context_parts.append("\nINTEREST RATE DATA (critical for utility valuations):")
            for r in rates:
                context_parts.append(f"  {r['indicator_id']}: {r['value']}")

    return "\n".join(context_parts) if context_parts else "Limited data available."


def _analyze_sector(expert_config: dict, symbols: list[str]) -> list[dict]:
    """Run a sector expert analysis via Gemini with dynamic context."""
    if not GEMINI_API_KEY or not symbols:
        return []

    context = _build_dynamic_context(symbols, expert_config)
    symbols_str = ", ".join(symbols[:20])
    today_str = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""{expert_config['framework']}

TODAY'S DATE: {today_str}

LIVE DATA FOR YOUR SECTOR ({symbols_str}):
{context}

TASK: Using the live data above AND your analytical framework, identify stocks where the market is CURRENTLY mispricing something specific.

Your analysis must be grounded in the data shown — reference specific numbers, scores, and signals. Don't make generic statements.

For each stock with a clear displacement, output:
{{
  "symbol": "<ticker>",
  "sector_displacement_score": <0-100>,
  "consensus_narrative": "<what the market currently thinks, 1 sentence>",
  "variant_narrative": "<specifically what the data shows they're missing, 1 sentence>",
  "direction": "bullish" or "bearish",
  "conviction_level": "high" or "medium" or "low",
  "key_catalysts": ["<specific upcoming event with approximate date>"],
  "leading_indicators": ["<specific measurable thing to watch>"]
}}

RULES:
- Reference SPECIFIC data from the live feed (prices, scores, signals, news)
- Only flag stocks where you see a CONCRETE mismatch between data and price
- Skip stocks where the market is roughly right
- Score 80+ only for clear, imminent, data-supported mispricing
- Empty array [] is a valid response if nothing is mispriced

Return a JSON array. No markdown, no explanation."""

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 2048,
                },
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)

        results = json.loads(raw)
        if not isinstance(results, list):
            results = [results]
        return results

    except Exception as e:
        print(f"    Gemini analysis failed for {expert_config['expert_type']}: {e}")
        return []


def run():
    """Run all sector expert analyses."""
    init_db()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  SECTOR EXPERT ANALYSIS (DYNAMIC)")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("  ERROR: GEMINI_API_KEY not set")
        return

    # Get universe grouped by sector
    universe = query("SELECT symbol, sector FROM stock_universe WHERE sector IS NOT NULL")
    sector_symbols = {}
    for r in universe:
        sector = r["sector"]
        if sector not in sector_symbols:
            sector_symbols[sector] = []
        sector_symbols[sector].append(r["symbol"])

    total_signals = 0

    for expert_name, expert_config in SECTOR_EXPERTS.items():
        # Find symbols: core tickers + universe matches
        matching_symbols = list(expert_config.get("core_tickers", []))

        for sector_name in expert_config["sectors"]:
            for db_sector, syms in sector_symbols.items():
                if sector_name.lower() in db_sector.lower():
                    matching_symbols.extend(syms)

        matching_symbols = list(dict.fromkeys(matching_symbols))[:25]  # Dedupe, preserve order, cap

        if not matching_symbols:
            print(f"  [{expert_name.upper()}] No matching symbols in universe")
            continue

        print(f"  [{expert_name.upper()}] Analyzing {len(matching_symbols)} stocks with live data...")

        assessments = _analyze_sector(expert_config, matching_symbols)

        if not assessments:
            print(f"    No displacement signals found")
            continue

        # Store results
        rows = []
        for assessment in assessments:
            sym = assessment.get("symbol", "")
            if not sym:
                continue

            score = assessment.get("sector_displacement_score", 0)
            if score < 30:
                continue

            rows.append((
                sym,
                today,
                expert_config["sectors"][0],
                expert_config["expert_type"],
                score,
                assessment.get("consensus_narrative", ""),
                assessment.get("variant_narrative", ""),
                json.dumps(assessment.get("leading_indicators", [])),
                assessment.get("conviction_level", "low"),
                assessment.get("direction", "neutral"),
                json.dumps(assessment.get("key_catalysts", [])),
                f"{assessment.get('direction', 'neutral').title()} — {assessment.get('variant_narrative', '')}",
            ))

        if rows:
            with get_conn() as conn:
                conn.executemany(
                    """INSERT OR REPLACE INTO sector_expert_signals
                       (symbol, date, sector, expert_type, sector_displacement_score,
                        consensus_narrative, variant_narrative, leading_indicators,
                        conviction_level, direction, key_catalysts, narrative)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
            total_signals += len(rows)
            print(f"    {len(rows)} displacement signals stored")

            for r in sorted(rows, key=lambda x: x[4], reverse=True)[:3]:
                print(f"    {r[0]}: score={r[4]:.0f} {r[9]} — {r[6][:60]}...")

        time.sleep(2)  # Rate limit between expert calls

    print(f"\n  Sector expert analysis complete: {total_signals} signals across "
          f"{len(SECTOR_EXPERTS)} experts")
    print("=" * 60)


if __name__ == "__main__":
    run()
