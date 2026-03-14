"""Investment Memo Generator — institutional-quality research output.

For every HIGH-conviction convergence signal, generates a structured
investment memo that a PM could act on. Pulls data from ALL modules
and synthesizes into a single, citation-verified document.

Architecture:
  1. Data Assembly: pull convergence, variant, devil's advocate, insider,
     consensus blindspot, estimate momentum, M&A, pairs data
  2. Citation Verification: tag every numerical claim as VERIFIED/INFERRED/UNVERIFIED
  3. LLM Synthesis: Gemini generates the narrative sections
  4. Output: intelligence_reports table + email-ready HTML

Memo Structure:
  - THESIS (1-2 sentences: why buy/sell, what's the variant view)
  - SIGNAL SUMMARY (which modules agree, scores)
  - VARIANT PERCEPTION (where we differ from consensus)
  - BEAR CASE (from devil's advocate)
  - KEY RISKS & KILL SCENARIOS
  - POSITION SIZING GUIDANCE
  - MONITORING TRIGGERS (what would break the thesis)

Usage: python -m tools.intelligence_report
"""

import json
import logging
import re
import time
from datetime import date

import requests

from tools.config import (
    GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
)
from tools.db import init_db, query, upsert_many

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────
MEMO_MAX_SIGNALS = 15         # Max HIGH signals to generate memos for
MEMO_GEMINI_TEMPERATURE = 0.3  # Low temp for factual synthesis
MEMO_MIN_CONVERGENCE = 40.0   # Min convergence score to generate memo


# ── Citation Verification ────────────────────────────────────────────

class CitationVerifier:
    """Tags numerical claims with verification status.

    VERIFIED:   exact value found in source data
    INFERRED:   derived from source data via calculation
    UNVERIFIED: cannot trace to any source — flag for review
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.verified_facts = {}
        self._load_source_data()

    def _load_source_data(self):
        """Load all source data for this symbol."""
        # Price data
        rows = query("""
            SELECT close, volume FROM price_data
            WHERE symbol = ? ORDER BY date DESC LIMIT 1
        """, [self.symbol])
        if rows:
            self.verified_facts["current_price"] = rows[0]["close"]
            self.verified_facts["current_volume"] = rows[0]["volume"]

        # Fundamentals (KV store)
        rows = query(
            "SELECT metric, value FROM fundamentals WHERE symbol = ?",
            [self.symbol])
        for r in rows:
            if r["value"] is not None:
                self.verified_facts[f"fund_{r['metric']}"] = r["value"]

        # Technical scores
        rows = query("""
            SELECT * FROM technical_scores
            WHERE symbol = ? ORDER BY date DESC LIMIT 1
        """, [self.symbol])
        if rows:
            for k, v in dict(rows[0]).items():
                if v is not None and k not in ("symbol", "date"):
                    self.verified_facts[f"tech_{k}"] = v

        # Convergence
        rows = query("""
            SELECT * FROM convergence_signals
            WHERE symbol = ? ORDER BY date DESC LIMIT 1
        """, [self.symbol])
        if rows:
            for k, v in dict(rows[0]).items():
                if v is not None and k not in ("symbol", "date", "narrative", "active_modules"):
                    self.verified_facts[f"conv_{k}"] = v

    def verify_claim(self, claim_key: str, claimed_value) -> str:
        """Verify a single numerical claim.

        Returns: 'VERIFIED', 'INFERRED', or 'UNVERIFIED'
        """
        if claimed_value is None:
            return "UNVERIFIED"

        # Direct match
        if claim_key in self.verified_facts:
            source_val = self.verified_facts[claim_key]
            if source_val is not None:
                try:
                    if abs(float(source_val) - float(claimed_value)) < 0.01:
                        return "VERIFIED"
                    else:
                        return "INFERRED"
                except (ValueError, TypeError):
                    return "INFERRED"

        # Check partial key matches
        for fact_key, fact_val in self.verified_facts.items():
            if claim_key in fact_key or fact_key in claim_key:
                return "INFERRED"

        return "UNVERIFIED"

    def build_citation_block(self, data: dict) -> list[dict]:
        """Build citation metadata for all data points in a memo.

        Returns list of {key, value, status, source_table} dicts.
        """
        citations = []
        for key, value in data.items():
            if value is None:
                continue
            status = self.verify_claim(key, value)
            source = "price_data" if "price" in key else \
                     "fundamentals" if "fund_" in key else \
                     "technical_scores" if "tech_" in key else \
                     "convergence_signals" if "conv_" in key else \
                     "derived"
            citations.append({
                "key": key,
                "value": value,
                "status": status,
                "source": source,
            })
        return citations


# ── Data Assembly ────────────────────────────────────────────────────

def _assemble_memo_data(symbol: str) -> dict:
    """Pull ALL relevant data for a symbol from across all modules.

    Returns a rich context dict for memo generation.
    """
    data = {"symbol": symbol}

    # 1. Convergence signal
    rows = query("""
        SELECT * FROM convergence_signals
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["convergence"] = dict(rows[0])

    # 2. Variant perception
    rows = query("""
        SELECT * FROM variant_analysis
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["variant"] = dict(rows[0])

    # 3. Devil's advocate
    rows = query("""
        SELECT * FROM devils_advocate
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["devils_advocate"] = dict(rows[0])

    # 4. Fundamentals (KV store: symbol, metric, value)
    fund_rows = query(
        "SELECT metric, value FROM fundamentals WHERE symbol = ?", [symbol])
    if fund_rows:
        data["fundamentals"] = {r["metric"]: r["value"] for r in fund_rows}

    # 5. Technical scores
    rows = query("""
        SELECT * FROM technical_scores
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["technicals"] = dict(rows[0])

    # 6. Insider signals
    rows = query("""
        SELECT * FROM insider_signals
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["insider"] = dict(rows[0])

    # 7. Consensus blindspots
    rows = query("""
        SELECT * FROM consensus_blindspot_signals
        WHERE symbol = ? AND symbol != '_MARKET'
        ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["consensus_blindspot"] = dict(rows[0])

    # 8. Estimate momentum
    rows = query("""
        SELECT * FROM estimate_momentum_signals
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["estimate_momentum"] = dict(rows[0])

    # 9. M&A intelligence
    rows = query("""
        SELECT * FROM ma_signals
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["ma"] = dict(rows[0])

    # 10. Pairs trading
    rows = query("""
        SELECT * FROM pair_signals
        WHERE runner_symbol = ? OR symbol_a = ? OR symbol_b = ?
        ORDER BY date DESC LIMIT 3
    """, [symbol, symbol, symbol])
    if rows:
        data["pairs"] = [dict(r) for r in rows]

    # 11. Smart money
    rows = query("""
        SELECT * FROM smart_money_scores
        WHERE symbol = ? ORDER BY date DESC LIMIT 1
    """, [symbol])
    if rows:
        data["smart_money"] = dict(rows[0])

    # 12. Sector info
    rows = query("SELECT * FROM stock_universe WHERE symbol = ?", [symbol])
    if rows:
        data["sector"] = rows[0]["sector"]
        data["company_name"] = rows[0]["name"]
        data["industry"] = rows[0].get("industry", "")

    # 13. Price context (30d, 60d returns)
    rows = query("""
        SELECT date, close FROM price_data
        WHERE symbol = ? ORDER BY date DESC LIMIT 252
    """, [symbol])
    if rows and len(rows) > 21:
        current = rows[0]["close"]
        data["current_price"] = current
        if rows[21]["close"]:
            data["return_30d"] = round(
                (current - rows[21]["close"]) / rows[21]["close"] * 100, 1)
        if len(rows) > 42 and rows[42]["close"]:
            data["return_60d"] = round(
                (current - rows[42]["close"]) / rows[42]["close"] * 100, 1)

    # 14. Macro regime
    rows = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    if rows:
        data["regime"] = dict(rows[0])

    # 15. Signal conflicts (from convergence_conflicts if available)
    try:
        rows = query("""
            SELECT * FROM signal_conflicts
            WHERE symbol = ? ORDER BY date DESC LIMIT 5
        """, [symbol])
        if rows:
            data["conflicts"] = [dict(r) for r in rows]
    except Exception:
        pass

    # 16. Forensic alerts
    rows = query("""
        SELECT * FROM forensic_alerts
        WHERE symbol = ? ORDER BY date DESC LIMIT 3
    """, [symbol])
    if rows:
        data["forensic_alerts"] = [dict(r) for r in rows]

    return data


# ── LLM Memo Generation ─────────────────────────────────────────────

def _build_memo_prompt(data: dict) -> str:
    """Build the Gemini prompt for memo generation."""
    symbol = data["symbol"]
    company = data.get("company_name", symbol)
    sector = data.get("sector", "Unknown")
    conv = data.get("convergence", {})
    variant = data.get("variant", {})
    da = data.get("devils_advocate", {})
    fund = data.get("fundamentals", {})
    cbs = data.get("consensus_blindspot", {})
    em = data.get("estimate_momentum", {})
    insider = data.get("insider", {})
    sm = data.get("smart_money", {})
    regime = data.get("regime", {})
    conflicts = data.get("conflicts", [])

    # Parse details JSON fields safely
    def _parse_details(obj, key="details"):
        raw = obj.get(key, "")
        if isinstance(raw, str) and raw.startswith("{"):
            try:
                return json.loads(raw)
            except Exception:
                pass
        return raw

    variant_details = _parse_details(variant)
    em_details = _parse_details(em)

    return f"""You are a senior equity analyst at a $5B long/short hedge fund writing an internal investment memo. Your PM reads these to decide whether to allocate capital. Every sentence must earn its place.

STOCK: {symbol} ({company}) — {sector}
DATE: {date.today().isoformat()}

═══ CONVERGENCE DATA ═══
Convergence Score: {conv.get('convergence_score', 'N/A')}/100
Conviction Level: {conv.get('conviction_level', 'N/A')}
Active Modules ({conv.get('module_count', 0)}): {conv.get('active_modules', '[]')}
Narrative: {conv.get('narrative', 'N/A')}

Key Module Scores:
  Smart Money: {conv.get('smartmoney_score', 'N/A')} | Managers: {sm.get('manager_count', 0)} | Top: {sm.get('top_holders', 'N/A')}
  Variant: {conv.get('variant_score', 'N/A')} | Thesis: {variant.get('thesis', 'N/A')}
  Worldview: {conv.get('worldview_score', 'N/A')}
  Estimate Momentum: {conv.get('estimate_momentum_score', 'N/A')} | Details: {em_details}
  Consensus Blindspot: {conv.get('consensus_blindspots_score', 'N/A')} | Gap: {cbs.get('gap_type', 'N/A')}
  Insider: {insider.get('insider_score', 'N/A')} | Cluster: {insider.get('cluster_buy', 0)} | C-Suite: {insider.get('large_csuite', 0)}

═══ FUNDAMENTALS ═══
P/E: {fund.get('pe_ratio', fund.get('trailingPE', 'N/A'))} | Forward P/E: {fund.get('forwardPE', 'N/A')}
ROE: {fund.get('roe', fund.get('returnOnEquity', 'N/A'))} | Debt/Equity: {fund.get('debtToEquity', fund.get('debt_equity', 'N/A'))}
Gross Margin: {fund.get('grossMargins', fund.get('gross_margin', 'N/A'))} | Operating Margin: {fund.get('operatingMargins', fund.get('operating_margin', 'N/A'))}
Market Cap: {fund.get('marketCap', fund.get('market_cap', 'N/A'))} | Beta: {fund.get('beta', 'N/A')}
Revenue Growth: {fund.get('revenueGrowth', fund.get('revenue_growth', 'N/A'))}

═══ PRICE ACTION ═══
Current Price: ${data.get('current_price', 'N/A')}
30-Day Return: {data.get('return_30d', 'N/A')}%
60-Day Return: {data.get('return_60d', 'N/A')}%

═══ VARIANT PERCEPTION ═══
{json.dumps(variant_details, indent=2) if isinstance(variant_details, dict) else variant_details}

═══ BEAR CASE (Devil's Advocate) ═══
Bear Thesis: {da.get('bear_thesis', 'N/A')}
Kill Scenario: {da.get('kill_scenario', 'N/A')}
Historical Analog: {da.get('historical_analog', 'N/A')}
Risk Score: {da.get('risk_score', 'N/A')}/100

═══ SIGNAL CONFLICTS ═══
{json.dumps(conflicts, indent=2) if conflicts else 'None detected'}

═══ MACRO REGIME ═══
Regime: {regime.get('regime', 'N/A')}

YOUR TASK: Write a concise investment memo in EXACTLY this JSON structure:

{{"thesis": "<2-3 sentences. The core investment thesis — what you believe the market is getting wrong about {symbol} and why. State the variant view clearly. This is the sentence the PM will read first.>",
"signal_summary": "<3-4 sentences summarizing which modules agree and why the convergence is meaningful. Reference specific scores.>",
"variant_perception": "<2-3 sentences on where our view differs from consensus and what data supports our divergence. Reference the variant score and any estimate momentum.>",
"bear_case": "<2-3 sentences. The strongest counterargument. Be honest about the risks. Reference the devil's advocate findings.>",
"key_risks": ["<risk 1 — specific and measurable>", "<risk 2>", "<risk 3>"],
"kill_scenarios": ["<event that would invalidate the thesis within 90 days>", "<event 2>"],
"position_guidance": "<1-2 sentences. Suggested sizing approach based on conviction level, volatility, and risk score. Be specific about whether this is a full-size or starter position.>",
"monitoring_triggers": ["<data point to watch that would strengthen/weaken thesis>", "<trigger 2>", "<trigger 3>"],
"time_horizon": "<short-term (1-4 weeks) | medium-term (1-3 months) | long-term (3-12 months)>",
"conviction_note": "<1 sentence — your honest assessment of conviction level, including any reservations>"}}

Rules:
- Every claim must be grounded in the data provided above. Do NOT invent metrics.
- Reference specific module scores when making claims about signal strength.
- The bear case must be genuine, not a strawman.
- Position guidance must account for the risk score from devil's advocate.
- Be direct and opinionated — hedging language weakens the memo."""


def _call_gemini_memo(prompt: str) -> dict | None:
    """Call Gemini for memo generation."""
    if not GEMINI_API_KEY:
        logger.warning("No GEMINI_API_KEY — skipping memo generation")
        return None

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": MEMO_GEMINI_TEMPERATURE,
                    "maxOutputTokens": 1500,
                },
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()
        text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Extract JSON
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            parsed = json.loads(json_match.group())
            required = ["thesis", "signal_summary", "variant_perception",
                        "bear_case", "key_risks", "position_guidance"]
            if all(k in parsed for k in required):
                return parsed

        logger.warning(f"Could not parse memo response: {text[:200]}")
        return None

    except Exception as e:
        logger.error(f"Gemini memo call failed: {e}")
        return None


# ── HTML Rendering ───────────────────────────────────────────────────

def render_memo_html(symbol: str, memo: dict, data: dict,
                     citations: list[dict]) -> str:
    """Render a memo as email-ready HTML."""
    conv = data.get("convergence", {})
    da = data.get("devils_advocate", {})
    fund = data.get("fundamentals", {})

    # Citation summary
    verified = sum(1 for c in citations if c["status"] == "VERIFIED")
    inferred = sum(1 for c in citations if c["status"] == "INFERRED")
    unverified = sum(1 for c in citations if c["status"] == "UNVERIFIED")

    risk_score = da.get("risk_score", 0)
    risk_color = "#FF1744" if risk_score > 75 else "#FFD54F" if risk_score > 50 else "#69F0AE"

    conviction = conv.get("conviction_level", "WATCH")
    conv_color = "#00C853" if conviction == "HIGH" else "#69F0AE" if conviction == "NOTABLE" else "#FFD54F"

    risks_html = "".join(f"<li>{r}</li>" for r in memo.get("key_risks", []))
    kills_html = "".join(f"<li>{k}</li>" for k in memo.get("kill_scenarios", []))
    triggers_html = "".join(f"<li>{t}</li>" for t in memo.get("monitoring_triggers", []))

    conflicts = data.get("conflicts", [])
    conflicts_html = ""
    if conflicts:
        conflicts_html = '<div style="background:#2a1a1a; border-left:3px solid #FF8A65; padding:12px; margin:12px 0; border-radius:4px;">'
        conflicts_html += '<h3 style="color:#FF8A65; margin-top:0;">Signal Conflicts Detected</h3>'
        for c in conflicts:
            conflicts_html += f'<p style="color:#E0E0E0; margin:4px 0;">{c.get("conflict_type", "")}: {c.get("description", "")}</p>'
        conflicts_html += '</div>'

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', sans-serif; background:#0E1117; color:#E0E0E0; padding:24px; max-width:720px; margin:0 auto;">

    <!-- Header -->
    <div style="border-bottom:2px solid #333; padding-bottom:16px; margin-bottom:20px;">
        <h1 style="color:white; margin:0; font-size:24px;">
            INVESTMENT MEMO: {symbol}
            <span style="font-size:14px; color:#888; font-weight:normal;"> — {data.get('company_name', symbol)}</span>
        </h1>
        <p style="color:#888; margin:4px 0 0 0; font-size:13px;">
            {date.today().strftime('%B %d, %Y')} · {data.get('sector', 'Unknown')} ·
            Convergence: <span style="color:{conv_color};">{conv.get('convergence_score', 0):.0f}/100 ({conviction})</span> ·
            Risk: <span style="color:{risk_color};">{risk_score}/100</span>
        </p>
        <p style="color:#555; margin:2px 0 0 0; font-size:11px;">
            Citations: {verified} verified · {inferred} inferred · {unverified} unverified
        </p>
    </div>

    <!-- Thesis -->
    <div style="background:#1a2332; border-left:3px solid #4FC3F7; padding:16px; margin:12px 0; border-radius:4px;">
        <h2 style="color:#4FC3F7; margin:0 0 8px 0; font-size:14px; text-transform:uppercase; letter-spacing:1px;">Thesis</h2>
        <p style="color:#E0E0E0; font-size:15px; line-height:1.6; margin:0;">{memo.get('thesis', '')}</p>
    </div>

    <!-- Signal Summary -->
    <div style="margin:16px 0;">
        <h3 style="color:#B0BEC5; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Signal Summary</h3>
        <p style="color:#CCC; font-size:14px; line-height:1.5;">{memo.get('signal_summary', '')}</p>
    </div>

    <!-- Key Metrics Row -->
    <div style="display:flex; gap:12px; margin:16px 0; flex-wrap:wrap;">
        <div style="background:#1e2130; padding:12px 16px; border-radius:6px; flex:1; min-width:100px;">
            <div style="color:#888; font-size:11px;">P/E</div>
            <div style="color:white; font-size:18px; font-weight:600;">{fund.get('pe_ratio', fund.get('trailingPE', 'N/A'))}</div>
        </div>
        <div style="background:#1e2130; padding:12px 16px; border-radius:6px; flex:1; min-width:100px;">
            <div style="color:#888; font-size:11px;">ROE</div>
            <div style="color:white; font-size:18px; font-weight:600;">{_fmt_pct(fund.get('roe', fund.get('returnOnEquity')))}</div>
        </div>
        <div style="background:#1e2130; padding:12px 16px; border-radius:6px; flex:1; min-width:100px;">
            <div style="color:#888; font-size:11px;">30d Return</div>
            <div style="color:{'#00C853' if (data.get('return_30d', 0) or 0) >= 0 else '#FF1744'}; font-size:18px; font-weight:600;">{data.get('return_30d', 'N/A')}%</div>
        </div>
        <div style="background:#1e2130; padding:12px 16px; border-radius:6px; flex:1; min-width:100px;">
            <div style="color:#888; font-size:11px;">Smart Money</div>
            <div style="color:white; font-size:18px; font-weight:600;">{conv.get('smartmoney_score', 'N/A')}</div>
        </div>
    </div>

    <!-- Variant Perception -->
    <div style="margin:16px 0;">
        <h3 style="color:#B0BEC5; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Variant Perception</h3>
        <p style="color:#CCC; font-size:14px; line-height:1.5;">{memo.get('variant_perception', '')}</p>
    </div>

    {conflicts_html}

    <!-- Bear Case -->
    <div style="background:#1a1a2e; border-left:3px solid #FF8A65; padding:16px; margin:12px 0; border-radius:4px;">
        <h3 style="color:#FF8A65; margin:0 0 8px 0; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Bear Case (Risk Score: {risk_score}/100)</h3>
        <p style="color:#CCC; font-size:14px; line-height:1.5; margin:0;">{memo.get('bear_case', '')}</p>
    </div>

    <!-- Two Column: Risks + Kill Scenarios -->
    <div style="display:flex; gap:16px; margin:16px 0; flex-wrap:wrap;">
        <div style="flex:1; min-width:200px;">
            <h3 style="color:#B0BEC5; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Key Risks</h3>
            <ul style="color:#CCC; font-size:13px; line-height:1.6; padding-left:18px;">{risks_html}</ul>
        </div>
        <div style="flex:1; min-width:200px;">
            <h3 style="color:#B0BEC5; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Kill Scenarios (90d)</h3>
            <ul style="color:#CCC; font-size:13px; line-height:1.6; padding-left:18px;">{kills_html}</ul>
        </div>
    </div>

    <!-- Position Guidance -->
    <div style="background:#1e2130; padding:14px 16px; border-radius:6px; margin:16px 0;">
        <h3 style="color:#B0BEC5; font-size:13px; text-transform:uppercase; letter-spacing:1px; margin:0 0 6px 0;">Position Guidance</h3>
        <p style="color:#E0E0E0; font-size:14px; margin:0;">{memo.get('position_guidance', '')}</p>
        <p style="color:#888; font-size:12px; margin:6px 0 0 0;">
            Time Horizon: {memo.get('time_horizon', 'N/A')} ·
            Conviction: {memo.get('conviction_note', 'N/A')}
        </p>
    </div>

    <!-- Monitoring Triggers -->
    <div style="margin:16px 0;">
        <h3 style="color:#B0BEC5; font-size:13px; text-transform:uppercase; letter-spacing:1px;">Monitoring Triggers</h3>
        <ul style="color:#CCC; font-size:13px; line-height:1.6; padding-left:18px;">{triggers_html}</ul>
    </div>

    <!-- Footer -->
    <div style="border-top:1px solid #333; padding-top:12px; margin-top:20px;">
        <p style="color:#555; font-size:11px; margin:0;">
            Generated by Druckenmiller Alpha System · {conv.get('module_count', 0)} modules ·
            {verified}/{verified + inferred + unverified} claims verified ·
            Not investment advice
        </p>
    </div>
    </div>
    """


def _fmt_pct(val):
    """Format a decimal as percentage string."""
    if val is None:
        return "N/A"
    try:
        return f"{float(val) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(val)


# ── Main ─────────────────────────────────────────────────────────────

def generate_memo(symbol: str) -> dict | None:
    """Generate an investment memo for a single symbol.

    Returns the memo dict or None on failure.
    """
    data = _assemble_memo_data(symbol)
    conv = data.get("convergence", {})

    if not conv:
        logger.info(f"{symbol}: no convergence data, skipping memo")
        return None

    # Build citation verification
    verifier = CitationVerifier(symbol)
    fund = data.get("fundamentals", {})
    citation_data = {
        "current_price": data.get("current_price"),
        "fund_pe_ratio": fund.get("pe_ratio", fund.get("trailingPE")),
        "fund_roe": fund.get("roe", fund.get("returnOnEquity")),
        "fund_marketCap": fund.get("marketCap", fund.get("market_cap")),
        "conv_convergence_score": conv.get("convergence_score"),
        "conv_module_count": conv.get("module_count"),
        "tech_total_score": data.get("technicals", {}).get("total_score"),
    }
    citations = verifier.build_citation_block(citation_data)

    # Generate memo via LLM
    prompt = _build_memo_prompt(data)
    memo = _call_gemini_memo(prompt)

    if not memo:
        logger.warning(f"{symbol}: memo generation failed")
        return None

    # Render HTML
    html = render_memo_html(symbol, memo, data, citations)

    # Store in DB — match existing intelligence_reports schema
    # Columns: topic, topic_type, expert_type, regime, symbols_covered,
    #          report_html, report_markdown, metadata
    regime = data.get("regime", {}).get("regime", "neutral")
    metadata = json.dumps({
        "citations": citations,
        "convergence_score": conv.get("convergence_score"),
        "conviction_level": conv.get("conviction_level"),
        "risk_score": data.get("devils_advocate", {}).get("risk_score"),
        "module_count": conv.get("module_count"),
    })

    # Build markdown summary for report_markdown
    markdown = (
        f"# Investment Memo: {symbol}\n"
        f"*{date.today().strftime('%B %d, %Y')}*\n\n"
        f"## Thesis\n{memo.get('thesis', '')}\n\n"
        f"## Signal Summary\n{memo.get('signal_summary', '')}\n\n"
        f"## Variant Perception\n{memo.get('variant_perception', '')}\n\n"
        f"## Bear Case\n{memo.get('bear_case', '')}\n\n"
        f"## Position Guidance\n{memo.get('position_guidance', '')}\n"
    )

    upsert_many(
        "intelligence_reports",
        ["topic", "topic_type", "expert_type", "regime",
         "symbols_covered", "report_html", "report_markdown", "metadata"],
        [(symbol, "investment_memo", "convergence", regime,
          symbol, html, markdown, metadata)],
    )

    return {
        "symbol": symbol,
        "memo": memo,
        "html": html,
        "citations": citations,
    }


def run():
    """Generate investment memos for all HIGH conviction signals."""
    init_db()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  INVESTMENT MEMO GENERATOR")
    print("=" * 60)

    # Get HIGH conviction signals
    signals = query("""
        SELECT symbol, convergence_score, conviction_level, module_count
        FROM convergence_signals
        WHERE date = ? AND conviction_level IN ('HIGH', 'NOTABLE')
          AND convergence_score >= ?
        ORDER BY convergence_score DESC
        LIMIT ?
    """, [today, MEMO_MIN_CONVERGENCE, MEMO_MAX_SIGNALS])

    if not signals:
        print("  No HIGH/NOTABLE signals above threshold — no memos to generate")
        print("=" * 60)
        return

    print(f"  Generating memos for {len(signals)} signals...")

    generated = 0
    for sig in signals:
        symbol = sig["symbol"]
        result = generate_memo(symbol)

        if result:
            generated += 1
            citations = result["citations"]
            verified = sum(1 for c in citations if c["status"] == "VERIFIED")
            total = len(citations)
            print(f"  {symbol:>6} | score={sig['convergence_score']:.0f} | "
                  f"citations: {verified}/{total} verified | MEMO GENERATED")
        else:
            print(f"  {symbol:>6} | SKIPPED (generation failed)")

        time.sleep(1.5)  # Rate limit

    print(f"\n  Memos generated: {generated}/{len(signals)}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    run()
