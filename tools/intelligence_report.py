"""Investment Memo Generator — institutional-quality research output."""

import json, logging, re, time
from datetime import date
import requests
from tools.config import GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL
from tools.db import init_db, query, upsert_many

logger = logging.getLogger(__name__)
MEMO_MAX_SIGNALS = 15
MEMO_GEMINI_TEMPERATURE = 0.3
MEMO_MIN_CONVERGENCE = 40.0


class CitationVerifier:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.verified_facts = {}
        self._load_source_data()

    def _load_source_data(self):
        rows = query("SELECT close, volume FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 1", [self.symbol])
        if rows:
            self.verified_facts["current_price"] = rows[0]["close"]
            self.verified_facts["current_volume"] = rows[0]["volume"]
        for r in query("SELECT metric, value FROM fundamentals WHERE symbol = ?", [self.symbol]):
            if r["value"] is not None: self.verified_facts[f"fund_{r['metric']}"] = r["value"]
        rows = query("SELECT * FROM technical_scores WHERE symbol = ? ORDER BY date DESC LIMIT 1", [self.symbol])
        if rows:
            for k, v in dict(rows[0]).items():
                if v is not None and k not in ("symbol", "date"): self.verified_facts[f"tech_{k}"] = v
        rows = query("SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [self.symbol])
        if rows:
            for k, v in dict(rows[0]).items():
                if v is not None and k not in ("symbol", "date", "narrative", "active_modules"):
                    self.verified_facts[f"conv_{k}"] = v

    def verify_claim(self, claim_key: str, claimed_value) -> str:
        if claimed_value is None: return "UNVERIFIED"
        if claim_key in self.verified_facts:
            source_val = self.verified_facts[claim_key]
            if source_val is not None:
                try: return "VERIFIED" if abs(float(source_val) - float(claimed_value)) < 0.01 else "INFERRED"
                except (ValueError, TypeError): return "INFERRED"
        for fk in self.verified_facts:
            if claim_key in fk or fk in claim_key: return "INFERRED"
        return "UNVERIFIED"

    def build_citation_block(self, data: dict) -> list[dict]:
        citations = []
        for key, value in data.items():
            if value is None: continue
            status = self.verify_claim(key, value)
            source = ("price_data" if "price" in key else "fundamentals" if "fund_" in key else
                      "technical_scores" if "tech_" in key else "convergence_signals" if "conv_" in key else "derived")
            citations.append({"key": key, "value": value, "status": status, "source": source})
        return citations


def _assemble_memo_data(symbol: str) -> dict:
    data = {"symbol": symbol}
    table_queries = [
        ("convergence", "SELECT * FROM convergence_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
        ("variant", "SELECT * FROM variant_analysis WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
        ("devils_advocate", "SELECT * FROM devils_advocate WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
        ("technicals", "SELECT * FROM technical_scores WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
        ("insider", "SELECT * FROM insider_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
        ("estimate_momentum", "SELECT * FROM estimate_momentum_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
        ("smart_money", "SELECT * FROM smart_money_scores WHERE symbol = ? ORDER BY date DESC LIMIT 1"),
    ]
    for key, sql in table_queries:
        rows = query(sql, [symbol])
        if rows: data[key] = dict(rows[0])
    # Consensus blindspot
    rows = query("SELECT * FROM consensus_blindspot_signals WHERE symbol = ? AND symbol != '_MARKET' ORDER BY date DESC LIMIT 1", [symbol])
    if rows: data["consensus_blindspot"] = dict(rows[0])
    # Fundamentals KV
    fund_rows = query("SELECT metric, value FROM fundamentals WHERE symbol = ?", [symbol])
    if fund_rows: data["fundamentals"] = {r["metric"]: r["value"] for r in fund_rows}
    # M&A
    rows = query("SELECT * FROM ma_signals WHERE symbol = ? ORDER BY date DESC LIMIT 1", [symbol])
    if rows: data["ma"] = dict(rows[0])
    # Pairs
    rows = query("SELECT * FROM pair_signals WHERE symbol_a = ? OR symbol_b = ? ORDER BY date DESC LIMIT 3", [symbol, symbol])
    if rows: data["pairs"] = [dict(r) for r in rows]
    # Sector info
    rows = query("SELECT * FROM stock_universe WHERE symbol = ?", [symbol])
    if rows:
        data["sector"] = rows[0]["sector"]; data["company_name"] = rows[0]["name"]
        data["industry"] = rows[0].get("industry", "")
    # Price context
    rows = query("SELECT date, close FROM price_data WHERE symbol = ? ORDER BY date DESC LIMIT 252", [symbol])
    if rows and len(rows) > 21:
        cur = rows[0]["close"]; data["current_price"] = cur
        if rows[21]["close"]: data["return_30d"] = round((cur - rows[21]["close"]) / rows[21]["close"] * 100, 1)
        if len(rows) > 42 and rows[42]["close"]: data["return_60d"] = round((cur - rows[42]["close"]) / rows[42]["close"] * 100, 1)
    rows = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    if rows: data["regime"] = dict(rows[0])
    try:
        rows = query("SELECT * FROM signal_conflicts WHERE symbol = ? ORDER BY date DESC LIMIT 5", [symbol])
        if rows: data["conflicts"] = [dict(r) for r in rows]
    except Exception: pass
    rows = query("SELECT * FROM forensic_alerts WHERE symbol = ? ORDER BY date DESC LIMIT 3", [symbol])
    if rows: data["forensic_alerts"] = [dict(r) for r in rows]
    return data


def _build_memo_prompt(data: dict) -> str:
    s = data["symbol"]; co = data.get("company_name", s); sec = data.get("sector", "Unknown")
    conv = data.get("convergence", {}); var = data.get("variant", {}); da = data.get("devils_advocate", {})
    fund = data.get("fundamentals", {}); cbs = data.get("consensus_blindspot", {}); em = data.get("estimate_momentum", {})
    insider = data.get("insider", {}); sm = data.get("smart_money", {}); regime = data.get("regime", {}); conflicts = data.get("conflicts", [])
    def _pd(obj, key="details"):
        raw = obj.get(key, "")
        if isinstance(raw, str) and raw.startswith("{"):
            try: return json.loads(raw)
            except Exception: pass
        return raw
    vd = _pd(var); ed = _pd(em)
    return f"""You are a senior equity analyst at a $5B long/short fund writing an internal investment memo.

STOCK: {s} ({co}) -- {sec}  DATE: {date.today().isoformat()}

CONVERGENCE: Score={conv.get('convergence_score','N/A')}/100 Conviction={conv.get('conviction_level','N/A')} Modules({conv.get('module_count',0)}): {conv.get('active_modules','[]')}
Narrative: {conv.get('narrative','N/A')}
SmartMoney={conv.get('smartmoney_score','N/A')} Variant={conv.get('variant_score','N/A')} Worldview={conv.get('worldview_score','N/A')} EstMom={conv.get('estimate_momentum_score','N/A')} CBS={conv.get('consensus_blindspots_score','N/A')} Insider={insider.get('insider_score','N/A')}

FUNDAMENTALS: P/E={fund.get('pe_ratio',fund.get('trailingPE','N/A'))} FwdPE={fund.get('forwardPE','N/A')} ROE={fund.get('roe',fund.get('returnOnEquity','N/A'))} D/E={fund.get('debtToEquity','N/A')} GrossM={fund.get('grossMargins','N/A')} OpM={fund.get('operatingMargins','N/A')} MCap={fund.get('marketCap','N/A')} RevGrowth={fund.get('revenueGrowth','N/A')}

PRICE: ${data.get('current_price','N/A')} 30d={data.get('return_30d','N/A')}% 60d={data.get('return_60d','N/A')}%
VARIANT: {json.dumps(vd,indent=1) if isinstance(vd,dict) else vd}
BEAR: Thesis={da.get('bear_thesis','N/A')} Kill={da.get('kill_scenario','N/A')} Risk={da.get('risk_score','N/A')}/100
CONFLICTS: {json.dumps(conflicts,indent=1) if conflicts else 'None'}
REGIME: {regime.get('regime','N/A')}

Write a concise memo as JSON: {{"thesis":"<2-3 sentences>","signal_summary":"<3-4 sentences>","variant_perception":"<2-3 sentences>","bear_case":"<2-3 sentences>","key_risks":["risk1","risk2","risk3"],"kill_scenarios":["event1","event2"],"position_guidance":"<1-2 sentences>","monitoring_triggers":["trigger1","trigger2","trigger3"],"time_horizon":"<short|medium|long-term>","conviction_note":"<1 sentence>"}}

Rules: Ground every claim in data above. Reference specific scores. Bear case must be genuine. Be direct."""


def _call_gemini_memo(prompt: str) -> dict | None:
    if not GEMINI_API_KEY: return None
    try:
        resp = requests.post(f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"}, params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": MEMO_GEMINI_TEMPERATURE, "maxOutputTokens": 4096}}, timeout=60)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            parsed = json.loads(m.group())
            if all(k in parsed for k in ["thesis", "signal_summary", "variant_perception", "bear_case", "key_risks", "position_guidance"]):
                return parsed
        return None
    except Exception as e:
        logger.error(f"Gemini memo call failed: {e}"); return None


def _fmt_pct(val):
    if val is None: return "N/A"
    try: return f"{float(val)*100:.1f}%"
    except (ValueError, TypeError): return str(val)


def render_memo_html(symbol, memo, data, citations):
    conv = data.get("convergence", {}); da = data.get("devils_advocate", {}); fund = data.get("fundamentals", {})
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
        conflicts_html = '<div style="background:#2a1a1a;border-left:3px solid #FF8A65;padding:12px;margin:12px 0;border-radius:4px;"><h3 style="color:#FF8A65;margin-top:0;">Signal Conflicts</h3>'
        for c in conflicts: conflicts_html += f'<p style="color:#E0E0E0;margin:4px 0;">{c.get("conflict_type","")}: {c.get("description","")}</p>'
        conflicts_html += '</div>'
    ret30 = data.get('return_30d', 0) or 0
    ret_color = '#00C853' if ret30 >= 0 else '#FF1744'
    return f"""<div style="font-family:-apple-system,BlinkMacSystemFont,'SF Pro',sans-serif;background:#0E1117;color:#E0E0E0;padding:24px;max-width:720px;margin:0 auto;">
    <div style="border-bottom:2px solid #333;padding-bottom:16px;margin-bottom:20px;">
        <h1 style="color:white;margin:0;font-size:24px;">INVESTMENT MEMO: {symbol} <span style="font-size:14px;color:#888;font-weight:normal;">-- {data.get('company_name',symbol)}</span></h1>
        <p style="color:#888;margin:4px 0 0 0;font-size:13px;">{date.today().strftime('%B %d, %Y')} | {data.get('sector','Unknown')} | Convergence: <span style="color:{conv_color};">{conv.get('convergence_score',0):.0f}/100 ({conviction})</span> | Risk: <span style="color:{risk_color};">{risk_score}/100</span></p>
        <p style="color:#555;margin:2px 0 0 0;font-size:11px;">Citations: {verified} verified | {inferred} inferred | {unverified} unverified</p>
    </div>
    <div style="background:#1a2332;border-left:3px solid #4FC3F7;padding:16px;margin:12px 0;border-radius:4px;">
        <h2 style="color:#4FC3F7;margin:0 0 8px 0;font-size:14px;text-transform:uppercase;">Thesis</h2>
        <p style="color:#E0E0E0;font-size:15px;line-height:1.6;margin:0;">{memo.get('thesis','')}</p>
    </div>
    <div style="margin:16px 0;"><h3 style="color:#B0BEC5;font-size:13px;text-transform:uppercase;">Signal Summary</h3><p style="color:#CCC;font-size:14px;line-height:1.5;">{memo.get('signal_summary','')}</p></div>
    <div style="display:flex;gap:12px;margin:16px 0;flex-wrap:wrap;">
        <div style="background:#1e2130;padding:12px 16px;border-radius:6px;flex:1;min-width:100px;"><div style="color:#888;font-size:11px;">P/E</div><div style="color:white;font-size:18px;font-weight:600;">{fund.get('pe_ratio',fund.get('trailingPE','N/A'))}</div></div>
        <div style="background:#1e2130;padding:12px 16px;border-radius:6px;flex:1;min-width:100px;"><div style="color:#888;font-size:11px;">ROE</div><div style="color:white;font-size:18px;font-weight:600;">{_fmt_pct(fund.get('roe',fund.get('returnOnEquity')))}</div></div>
        <div style="background:#1e2130;padding:12px 16px;border-radius:6px;flex:1;min-width:100px;"><div style="color:#888;font-size:11px;">30d Return</div><div style="color:{ret_color};font-size:18px;font-weight:600;">{data.get('return_30d','N/A')}%</div></div>
        <div style="background:#1e2130;padding:12px 16px;border-radius:6px;flex:1;min-width:100px;"><div style="color:#888;font-size:11px;">Smart Money</div><div style="color:white;font-size:18px;font-weight:600;">{conv.get('smartmoney_score','N/A')}</div></div>
    </div>
    <div style="margin:16px 0;"><h3 style="color:#B0BEC5;font-size:13px;text-transform:uppercase;">Variant Perception</h3><p style="color:#CCC;font-size:14px;line-height:1.5;">{memo.get('variant_perception','')}</p></div>
    {conflicts_html}
    <div style="background:#1a1a2e;border-left:3px solid #FF8A65;padding:16px;margin:12px 0;border-radius:4px;">
        <h3 style="color:#FF8A65;margin:0 0 8px 0;font-size:13px;text-transform:uppercase;">Bear Case (Risk: {risk_score}/100)</h3>
        <p style="color:#CCC;font-size:14px;line-height:1.5;margin:0;">{memo.get('bear_case','')}</p>
    </div>
    <div style="display:flex;gap:16px;margin:16px 0;flex-wrap:wrap;">
        <div style="flex:1;min-width:200px;"><h3 style="color:#B0BEC5;font-size:13px;text-transform:uppercase;">Key Risks</h3><ul style="color:#CCC;font-size:13px;line-height:1.6;padding-left:18px;">{risks_html}</ul></div>
        <div style="flex:1;min-width:200px;"><h3 style="color:#B0BEC5;font-size:13px;text-transform:uppercase;">Kill Scenarios (90d)</h3><ul style="color:#CCC;font-size:13px;line-height:1.6;padding-left:18px;">{kills_html}</ul></div>
    </div>
    <div style="background:#1e2130;padding:14px 16px;border-radius:6px;margin:16px 0;">
        <h3 style="color:#B0BEC5;font-size:13px;text-transform:uppercase;margin:0 0 6px 0;">Position Guidance</h3>
        <p style="color:#E0E0E0;font-size:14px;margin:0;">{memo.get('position_guidance','')}</p>
        <p style="color:#888;font-size:12px;margin:6px 0 0 0;">Time Horizon: {memo.get('time_horizon','N/A')} | Conviction: {memo.get('conviction_note','N/A')}</p>
    </div>
    <div style="margin:16px 0;"><h3 style="color:#B0BEC5;font-size:13px;text-transform:uppercase;">Monitoring Triggers</h3><ul style="color:#CCC;font-size:13px;line-height:1.6;padding-left:18px;">{triggers_html}</ul></div>
    <div style="border-top:1px solid #333;padding-top:12px;margin-top:20px;">
        <p style="color:#555;font-size:11px;margin:0;">Druckenmiller Alpha System | {conv.get('module_count',0)} modules | {verified}/{verified+inferred+unverified} verified | Not investment advice</p>
    </div></div>"""


def generate_memo(symbol: str) -> dict | None:
    data = _assemble_memo_data(symbol)
    conv = data.get("convergence", {})
    if not conv: return None
    verifier = CitationVerifier(symbol)
    fund = data.get("fundamentals", {})
    citation_data = {"current_price": data.get("current_price"), "fund_pe_ratio": fund.get("pe_ratio", fund.get("trailingPE")),
        "fund_roe": fund.get("roe", fund.get("returnOnEquity")), "fund_marketCap": fund.get("marketCap", fund.get("market_cap")),
        "conv_convergence_score": conv.get("convergence_score"), "conv_module_count": conv.get("module_count"),
        "tech_total_score": data.get("technicals", {}).get("total_score")}
    citations = verifier.build_citation_block(citation_data)
    memo = _call_gemini_memo(_build_memo_prompt(data))
    if not memo: return None
    html = render_memo_html(symbol, memo, data, citations)
    regime = data.get("regime", {}).get("regime", "neutral")
    metadata = json.dumps({"citations": citations, "convergence_score": conv.get("convergence_score"),
        "conviction_level": conv.get("conviction_level"), "risk_score": data.get("devils_advocate", {}).get("risk_score"),
        "module_count": conv.get("module_count")})
    markdown = (f"# Investment Memo: {symbol}\n*{date.today().strftime('%B %d, %Y')}*\n\n"
        f"## Thesis\n{memo.get('thesis','')}\n\n## Signal Summary\n{memo.get('signal_summary','')}\n\n"
        f"## Variant Perception\n{memo.get('variant_perception','')}\n\n## Bear Case\n{memo.get('bear_case','')}\n\n"
        f"## Position Guidance\n{memo.get('position_guidance','')}\n")
    upsert_many("intelligence_reports",
        ["topic", "topic_type", "expert_type", "regime", "symbols_covered", "report_html", "report_markdown", "metadata"],
        [(symbol, "investment_memo", "convergence", regime, symbol, html, markdown, metadata)])
    return {"symbol": symbol, "memo": memo, "html": html, "citations": citations}


def run():
    init_db()
    today = date.today().isoformat()
    print("\n" + "=" * 60 + "\n  INVESTMENT MEMO GENERATOR\n" + "=" * 60)
    signals = query("SELECT symbol, convergence_score, conviction_level, module_count FROM convergence_signals WHERE date = ? AND conviction_level IN ('HIGH', 'NOTABLE') AND convergence_score >= ? ORDER BY convergence_score DESC LIMIT ?",
        [today, MEMO_MIN_CONVERGENCE, MEMO_MAX_SIGNALS])
    if not signals:
        print("  No HIGH/NOTABLE signals above threshold"); print("=" * 60); return
    print(f"  Generating memos for {len(signals)} signals...")
    generated = 0
    for sig in signals:
        result = generate_memo(sig["symbol"])
        if result:
            generated += 1
            v = sum(1 for c in result["citations"] if c["status"] == "VERIFIED")
            print(f"  {sig['symbol']:>6} | score={sig['convergence_score']:.0f} | citations: {v}/{len(result['citations'])} verified | MEMO GENERATED")
        else:
            print(f"  {sig['symbol']:>6} | SKIPPED")
        time.sleep(1.5)
    print(f"\n  Memos generated: {generated}/{len(signals)}\n" + "=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); init_db(); run()
