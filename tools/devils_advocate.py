"""Devil's Advocate Module — adversarial bear case generator.

For every HIGH-conviction convergence signal, generates the strongest
possible counter-thesis using Gemini. Forces confrontation with the
bear case BEFORE capital is deployed.

Purpose: counteract confirmation bias. When 3+ modules agree, it's
tempting to assume the trade is a lock. This module exists to find
the fatal flaw that consensus is ignoring.

Output: devils_advocate table with bear_thesis, kill_scenario,
historical_analog, and risk_score per HIGH signal. If risk_score > 75,
a WARNING flag is appended to the convergence narrative.

Usage: python -m tools.devils_advocate
"""

import json
import logging
import re
import time
from datetime import date, timedelta

import requests

from tools.config import (
    GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL,
    DA_MAX_SIGNALS, DA_WARNING_THRESHOLD, DA_GEMINI_TEMPERATURE,
)
from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)


# ── Price Context ─────────────────────────────────────────────────────

def _get_price_context(symbol: str) -> dict:
    """Compute recent price action context for a symbol.

    Returns: {return_30d, return_60d, vs_200dma} as percentages,
    or zeros if insufficient data.
    """
    rows = query(
        """
        SELECT date, close FROM price_data
        WHERE symbol = ?
        ORDER BY date DESC
        LIMIT 252
        """,
        [symbol],
    )

    if not rows or rows[0]["close"] is None:
        return {"return_30d": 0.0, "return_60d": 0.0, "vs_200dma": 0.0}

    current_price = rows[0]["close"]
    result = {"return_30d": 0.0, "return_60d": 0.0, "vs_200dma": 0.0}

    # 30-day return (approx 21 trading days)
    if len(rows) > 21 and rows[21]["close"]:
        result["return_30d"] = round(
            (current_price - rows[21]["close"]) / rows[21]["close"] * 100, 1
        )

    # 60-day return (approx 42 trading days)
    if len(rows) > 42 and rows[42]["close"]:
        result["return_60d"] = round(
            (current_price - rows[42]["close"]) / rows[42]["close"] * 100, 1
        )

    # Price vs 200-day MA
    if len(rows) >= 200:
        ma_200 = sum(r["close"] for r in rows[:200] if r["close"]) / 200
        if ma_200 > 0:
            result["vs_200dma"] = round(
                (current_price - ma_200) / ma_200 * 100, 1
            )

    return result


# ── Prompt Construction ───────────────────────────────────────────────

def _build_prompt(symbol: str, context: dict) -> str:
    """Build the adversarial Gemini prompt.

    The prompt is designed to elicit a specific, data-grounded bear case,
    not generic risk disclaimers. Temperature is set high (0.7) to
    encourage creative adversarial thinking.
    """
    return f"""You are a short-seller with a 30-year track record who has made billions betting against consensus. You are NOT a risk manager writing disclaimers. You are trying to MAKE MONEY by finding what's wrong with this trade.

STOCK: {symbol} ({context.get('sector', 'Unknown')})
BULL CASE: {context.get('module_count', 0)} independent modules agree. Convergence score: {context.get('convergence_score', 0):.0f}/100.
Active modules: {context.get('active_modules', '[]')}
Worldview narrative: {context.get('narrative', 'N/A')}

MACRO CONTEXT:
Regime: {context.get('regime', 'neutral')} (total score: {context.get('macro_total', 0)})
Fed funds score: {context.get('fed_funds', 0)}, Credit spreads score: {context.get('credit_spreads', 0)}, VIX score: {context.get('vix', 0)}

RECENT PRICE ACTION:
30-day return: {context.get('return_30d', 0)}%
60-day return: {context.get('return_60d', 0)}%
Current price vs 200-day MA: {context.get('vs_200dma', 0)}%

YOUR TASK: Destroy this bull case. Find the fatal flaw. You must respond with EXACTLY this JSON structure and nothing else:

{{"bear_thesis": "<2-3 sentences. The single strongest reason this trade will lose money. Be specific — name the mechanism, the timing, the catalyst. No hedging language like 'could' or 'might'. State it as fact.>", "kill_scenario": "<1-2 sentences. The specific, observable event that would prove the bull case wrong within 90 days. Must be measurable — a data release, an earnings miss threshold, a price level, a policy action.>", "historical_analog": "<1-2 sentences. A specific past situation (include year and stock/sector) where similar multi-module convergence and conviction led to losses. What happened and why the consensus was wrong.>", "risk_score": <integer 0-100, where 100 means the bull case is almost certainly wrong. Score above 70 only if you can identify a specific imminent catalyst that would break the thesis.>, "killers": [{{"name": "<specific threat name>", "probability": <integer 0-100>, "impact": <integer 0-100, where 100 = company-ending>, "score": <integer, probability * impact / 100>}}, {{"name": "<specific threat name>", "probability": <integer 0-100>, "impact": <integer 0-100>, "score": <integer>}}, {{"name": "<specific threat name>", "probability": <integer 0-100>, "impact": <integer 0-100>, "score": <integer>}}]}}

Rules:
- Do NOT list generic risks like "market downturn" or "recession could happen"
- Every point must be SPECIFIC to {symbol} and its current situation
- The historical analog must be a REAL event, not hypothetical
- If the bull case is genuinely strong, say so with a low risk_score — do not manufacture fake bearishness
- The 3 killers must be the top 3 thesis-specific threats, ordered by score descending. Each killer name must be a concrete mechanism (e.g. "AMD market share gain in data center GPUs"), not a category"""


# ── Gemini Call ───────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> dict | None:
    """Call Gemini and parse the JSON response.

    Returns parsed dict or None on failure.
    """
    if not GEMINI_API_KEY:
        logger.warning("No GEMINI_API_KEY — skipping devil's advocate")
        return None

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": DA_GEMINI_TEMPERATURE,
                    "maxOutputTokens": 768,
                },
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            parsed = json.loads(json_match.group())
            # Validate required fields
            required = ["bear_thesis", "kill_scenario", "historical_analog", "risk_score"]
            if all(k in parsed for k in required):
                # Clamp risk_score to 0-100
                parsed["risk_score"] = max(0, min(100, int(parsed["risk_score"])))
                # Validate and clamp killers if present
                if "killers" in parsed and isinstance(parsed["killers"], list):
                    for k in parsed["killers"]:
                        k["probability"] = max(0, min(100, int(k.get("probability", 0))))
                        k["impact"] = max(0, min(100, int(k.get("impact", 0))))
                        k["score"] = k["probability"] * k["impact"] // 100
                    parsed["killers"] = sorted(parsed["killers"], key=lambda x: x["score"], reverse=True)[:3]
                else:
                    parsed["killers"] = []
                return parsed

        logger.warning(f"Could not parse Gemini response: {text[:200]}")
        return None

    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return None


# ── Convergence Narrative Update ──────────────────────────────────────

def _update_convergence_narrative(
    symbol: str, today: str, bear_thesis: str, risk_score: int, warning: bool
):
    """Append the bear case to the existing convergence narrative."""
    rows = query(
        "SELECT narrative FROM convergence_signals WHERE symbol = ? AND date = ?",
        [symbol, today],
    )
    if not rows:
        return

    existing = rows[0]["narrative"] or ""
    bear_summary = bear_thesis[:120]

    if warning:
        updated = f"[DA WARNING rs={risk_score}] {existing} | BEAR: {bear_summary}"
    else:
        updated = f"{existing} | BEAR (rs={risk_score}): {bear_summary}"

    with get_conn() as conn:
        conn.execute(
            "UPDATE convergence_signals SET narrative = ? WHERE symbol = ? AND date = ?",
            [updated, symbol, today],
        )


# ── Main ──────────────────────────────────────────────────────────────

def run():
    """Run the Devil's Advocate module on today's HIGH conviction signals."""
    init_db()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  DEVIL'S ADVOCATE")
    print("=" * 60)

    # Get today's HIGH conviction signals, ordered by score
    signals = query(
        """
        SELECT symbol, convergence_score, module_count, conviction_level,
               active_modules, narrative,
               smartmoney_score, worldview_score, variant_score,
               research_score, foreign_intel_score
        FROM convergence_signals
        WHERE date = ? AND conviction_level = 'HIGH'
        ORDER BY convergence_score DESC
        LIMIT ?
        """,
        [today, DA_MAX_SIGNALS],
    )

    if not signals:
        print("  No HIGH conviction signals today — nothing to challenge")
        print("=" * 60)
        return

    print(f"  Challenging {len(signals)} HIGH conviction signals...")

    # Get macro context (reused across all signals)
    macro_rows = query("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    macro = dict(macro_rows[0]) if macro_rows else {}

    # Get sector info
    universe = query("SELECT symbol, sector FROM stock_universe")
    sector_map = {r["symbol"]: r["sector"] for r in universe}

    results = []
    warnings = 0

    for sig in signals:
        symbol = sig["symbol"]
        price_ctx = _get_price_context(symbol)

        # Build full context for prompt
        context = {
            "sector": sector_map.get(symbol, "Unknown"),
            "convergence_score": sig["convergence_score"],
            "module_count": sig["module_count"],
            "active_modules": sig["active_modules"],
            "narrative": sig["narrative"],
            "regime": macro.get("regime", "neutral"),
            "macro_total": macro.get("total_score", 0),
            "fed_funds": macro.get("fed_funds_score", 0),
            "credit_spreads": macro.get("credit_spreads_score", 0),
            "vix": macro.get("vix_score", 0),
            **price_ctx,
        }

        prompt = _build_prompt(symbol, context)
        parsed = _call_gemini(prompt)

        if parsed:
            warning_flag = 1 if parsed["risk_score"] > DA_WARNING_THRESHOLD else 0
            if warning_flag:
                warnings += 1

            bull_context = json.dumps({
                "convergence_score": sig["convergence_score"],
                "module_count": sig["module_count"],
                "active_modules": sig["active_modules"],
            })

            results.append((
                symbol, today,
                parsed["bear_thesis"],
                parsed["kill_scenario"],
                parsed["historical_analog"],
                parsed["risk_score"],
                bull_context,
                macro.get("regime", "neutral"),
                warning_flag,
                json.dumps(parsed["killers"]),
            ))

            # Update convergence narrative with bear case
            _update_convergence_narrative(
                symbol, today,
                parsed["bear_thesis"],
                parsed["risk_score"],
                bool(warning_flag),
            )

            status = "WARNING" if warning_flag else "ok"
            print(f"  {symbol:>6} | risk={parsed['risk_score']:>3} | {status} | {parsed['bear_thesis'][:70]}")
        else:
            print(f"  {symbol:>6} | SKIPPED (Gemini parse failure)")

        time.sleep(1.0)  # Rate limit

    # Write to database
    if results:
        upsert_many(
            "devils_advocate",
            ["symbol", "date", "bear_thesis", "kill_scenario",
             "historical_analog", "risk_score", "bull_context",
             "regime_at_signal", "warning_flag", "killers"],
            results,
        )

    print(f"\n  Analyzed: {len(results)}/{len(signals)} signals")
    print(f"  Warnings (risk > {DA_WARNING_THRESHOLD}): {warnings}")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    run()
