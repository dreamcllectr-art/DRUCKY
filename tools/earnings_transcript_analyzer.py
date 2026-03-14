"""Earnings Transcript Alpha Extractor — detect tone shifts, hedging, consensus divergence.

Uses:
- FMP earnings call transcripts (full text)
- Quantitative NLP (word frequency analysis, no LLM)
- Gemini LLM for deep qualitative analysis
- FMP analyst estimates for consensus divergence

Not part of daily pipeline — triggered on-demand around earnings season.
"""

import sys
import json
import time
import argparse
import re
import requests
from datetime import datetime

_project_root = str(__import__("pathlib").Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from tools.config import FMP_API_KEY, GEMINI_API_KEY, GEMINI_BASE, GEMINI_MODEL
from tools.db import init_db, upsert_many, query, query_df
from tools.fetch_fmp_fundamentals import fmp_get


# ── Word Lists for Quantitative NLP ──────────────────────────────────

UNCERTAINTY_WORDS = {
    "uncertain", "uncertainty", "challenging", "headwind", "headwinds",
    "difficult", "risk", "risks", "cautious", "concerned", "concern",
    "volatile", "volatility", "pressure", "pressures", "slowdown",
    "decelerate", "decelerating", "deteriorate", "deteriorating",
    "weaken", "weakening", "softer", "softness", "downturn",
    "unpredictable", "unclear", "worried", "disappointing",
}

CONFIDENCE_WORDS = {
    "strong", "strength", "confident", "confidence", "accelerate",
    "accelerating", "acceleration", "record", "exceeded", "exceeding",
    "momentum", "robust", "outstanding", "exceptional", "outperform",
    "outperformance", "optimistic", "tailwind", "tailwinds",
    "opportunity", "opportunities", "upside", "growth", "expanding",
    "expansion", "improving", "improvement", "resilient", "resilience",
    "best-in-class", "unprecedented", "transformative",
}

GUIDANCE_WORDS = {
    "expect", "expects", "expecting", "anticipate", "anticipates",
    "forecast", "outlook", "guidance", "guide", "project", "projects",
    "target", "targets", "committed", "on track", "reiterate",
    "raise", "raising", "increase", "increasing",
}


def fetch_transcript(symbol, year, quarter):
    """Fetch earnings call transcript from FMP."""
    data = fmp_get(f"/earning_call_transcript/{symbol}",
                   {"year": year, "quarter": quarter})
    if not data or not isinstance(data, list) or not data:
        return None
    return data[0].get("content", "")


def get_recent_quarters(n=4):
    """Get the last N calendar quarters as (year, quarter) tuples."""
    now = datetime.now()
    quarters = []
    year = now.year
    q = (now.month - 1) // 3  # 0-indexed current quarter

    for _ in range(n):
        if q <= 0:
            q = 4
            year -= 1
        quarters.append((year, q))
        q -= 1

    return quarters


def quantitative_nlp(text):
    """Compute word frequency metrics from transcript text."""
    if not text:
        return {}

    # Normalize text
    words = re.findall(r'\b[a-z]+(?:-[a-z]+)*\b', text.lower())
    total_words = len(words)
    if total_words < 100:
        return {}

    word_set = set(words)

    # Count occurrences
    uncertainty_count = sum(words.count(w) for w in UNCERTAINTY_WORDS)
    confidence_count = sum(words.count(w) for w in CONFIDENCE_WORDS)
    guidance_count = sum(words.count(w) for w in GUIDANCE_WORDS)

    # Ratios per 1000 words
    uncertainty_ratio = (uncertainty_count / total_words) * 1000
    confidence_ratio = (confidence_count / total_words) * 1000

    return {
        "word_count": total_words,
        "uncertainty_ratio": round(uncertainty_ratio, 2),
        "confidence_ratio": round(confidence_ratio, 2),
        "guidance_density": round((guidance_count / total_words) * 1000, 2),
        "net_sentiment": round(confidence_ratio - uncertainty_ratio, 2),
    }


def gemini_analyze(text, symbol, quarter_label):
    """Use Gemini to analyze transcript for qualitative signals."""
    if not GEMINI_API_KEY or not text:
        return {}

    # Truncate to ~8000 words to fit context
    words = text.split()
    if len(words) > 8000:
        text = " ".join(words[:4000] + ["... [TRUNCATED] ..."] + words[-4000:])

    prompt = f"""You are an expert equity analyst. Analyze this {symbol} {quarter_label} earnings call transcript.

Return ONLY a JSON object with these fields (no markdown, no explanation):
{{
  "tone": <float from -5.0 (very bearish) to +5.0 (very bullish)>,
  "forward_confidence": <float from 0 to 10, how confident management sounds about future>,
  "accounting_flags": <string, any mention of accounting changes, restatements, or unusual items. "none" if clean>,
  "capex_hiring_signal": <"expanding", "stable", or "contracting">,
  "key_themes": <list of 3-5 key themes/topics from the call>,
  "management_hedging": <float from 0 to 10, how much management is hedging/qualifying their statements>,
  "competitive_position": <"strengthening", "stable", or "weakening" based on competitive commentary>
}}

TRANSCRIPT:
{text}"""

    try:
        resp = requests.post(
            f"{GEMINI_BASE}/models/{GEMINI_MODEL}:generateContent",
            params={"key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        # Extract text from Gemini response
        content = result["candidates"][0]["content"]["parts"][0]["text"]

        # Parse JSON from response (handle markdown code blocks)
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r'^```(?:json)?\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        parsed = json.loads(content)
        return {
            "llm_tone": parsed.get("tone", 0),
            "llm_forward_confidence": parsed.get("forward_confidence", 5),
            "llm_accounting_flags": parsed.get("accounting_flags", "none"),
            "llm_capex_signal": parsed.get("capex_hiring_signal", "stable"),
            "llm_hedging": parsed.get("management_hedging", 5),
            "llm_competitive": parsed.get("competitive_position", "stable"),
            "key_themes": json.dumps(parsed.get("key_themes", [])),
        }
    except Exception as e:
        print(f"    Gemini error for {symbol}: {e}")
        return {}


def compute_consensus_divergence(llm_result, symbol):
    """Compare LLM tone assessment against consensus estimate direction."""
    estimates = fmp_get(f"/analyst-estimates/{symbol}", {"period": "annual", "limit": 2})
    if not estimates or not isinstance(estimates, list) or len(estimates) < 2:
        return 0

    # Get forward growth expectations
    rev_curr = estimates[0].get("estimatedRevenueAvg")
    rev_next = estimates[1].get("estimatedRevenueAvg") if len(estimates) > 1 else None

    if not rev_curr or not rev_next or rev_curr <= 0:
        return 0

    consensus_growth = (rev_next - rev_curr) / rev_curr

    # LLM tone: -5 to +5, normalize to -1 to +1
    llm_tone = llm_result.get("llm_tone", 0)
    tone_normalized = llm_tone / 5.0

    # Forward confidence: 0-10, normalize
    fwd_conf = llm_result.get("llm_forward_confidence", 5)
    conf_signal = (fwd_conf - 5) / 5.0  # -1 to +1

    # Hedging: 0-10, higher = more hedging = more cautious
    hedging = llm_result.get("llm_hedging", 5)
    hedge_signal = -(hedging - 5) / 5.0  # Flip: more hedging = negative

    # Management signal composite (-1 to +1)
    mgmt_signal = (tone_normalized * 0.5 + conf_signal * 0.3 + hedge_signal * 0.2)

    # Consensus signal (simplified)
    if consensus_growth > 0.15:
        consensus_signal = 0.8
    elif consensus_growth > 0.05:
        consensus_signal = 0.4
    elif consensus_growth > 0:
        consensus_signal = 0.1
    elif consensus_growth > -0.05:
        consensus_signal = -0.2
    else:
        consensus_signal = -0.6

    # Divergence: negative = management more cautious than Street
    divergence = (mgmt_signal - consensus_signal) * 100

    return round(max(-100, min(100, divergence)), 1)


def analyze_symbol(symbol, use_gemini=True):
    """Full transcript analysis for a single symbol."""
    quarters = get_recent_quarters(4)
    results = []

    for year, q in quarters:
        quarter_label = f"Q{q} {year}"
        transcript = fetch_transcript(symbol, year, q)
        if not transcript or len(transcript) < 500:
            continue

        # Quantitative NLP
        quant = quantitative_nlp(transcript)
        if not quant:
            continue

        # Gemini analysis (optional)
        llm = {}
        if use_gemini and GEMINI_API_KEY:
            llm = gemini_analyze(transcript, symbol, quarter_label)
            time.sleep(1)  # Rate limiting

        # Consensus divergence
        divergence = 0
        if llm:
            divergence = compute_consensus_divergence(llm, symbol)

        results.append({
            "symbol": symbol,
            "quarter": f"{year}Q{q}",
            "year": year,
            "quarter_label": quarter_label,
            "word_count": quant.get("word_count", 0),
            "uncertainty_ratio": quant.get("uncertainty_ratio", 0),
            "confidence_ratio": quant.get("confidence_ratio", 0),
            "net_sentiment": quant.get("net_sentiment", 0),
            "llm_tone": llm.get("llm_tone"),
            "tone_shift": None,  # Computed below
            "consensus_divergence": divergence,
            "key_themes": llm.get("key_themes", "[]"),
        })

    # Compute tone shifts (quarter over quarter)
    for i in range(len(results) - 1):
        curr = results[i]
        prev = results[i + 1]  # Older quarter
        if curr.get("llm_tone") is not None and prev.get("llm_tone") is not None:
            curr["tone_shift"] = round(curr["llm_tone"] - prev["llm_tone"], 2)
        # Also compute NLP sentiment shift
        curr["sentiment_shift"] = round(
            curr["net_sentiment"] - prev["net_sentiment"], 2
        )

    return results


def run(symbols=None, use_gemini=True):
    """Run transcript analysis for specified symbols."""
    init_db()

    if not FMP_API_KEY:
        print("  ERROR: FMP_API_KEY not set in .env")
        return

    if symbols is None:
        # Default: stocks with upcoming earnings or current BUY signals
        upcoming = query(
            "SELECT DISTINCT symbol FROM earnings_calendar "
            "WHERE date >= date('now') AND date <= date('now', '+14 days')"
        )
        if upcoming:
            symbols = [r["symbol"] for r in upcoming]
            print(f"Analyzing transcripts for {len(symbols)} stocks with upcoming earnings...")
        else:
            # Fall back to BUY signals
            signals = query(
                "SELECT DISTINCT symbol FROM signals WHERE signal IN ('BUY', 'STRONG BUY') "
                "AND date = (SELECT MAX(date) FROM signals) LIMIT 30"
            )
            symbols = [r["symbol"] for r in signals] if signals else []
            if symbols:
                print(f"Analyzing transcripts for {len(symbols)} BUY-rated stocks...")
            else:
                print("  No upcoming earnings or BUY signals. Specify --symbols.")
                return

    print(f"  Gemini LLM analysis: {'enabled' if use_gemini and GEMINI_API_KEY else 'disabled (quantitative only)'}")

    all_db_rows = []
    all_fund_rows = []
    tone_alerts = []

    for i, symbol in enumerate(symbols):
        print(f"  [{i+1}/{len(symbols)}] Analyzing {symbol}...")
        results = analyze_symbol(symbol, use_gemini=use_gemini)

        if not results:
            print(f"    No transcripts found for {symbol}")
            continue

        latest = results[0]  # Most recent quarter

        # Store in transcript_analysis table
        for r in results:
            all_db_rows.append((
                r["symbol"], r["quarter"], r["year"], r["quarter_label"],
                r["word_count"], r["uncertainty_ratio"], r["confidence_ratio"],
                r.get("llm_tone"), r.get("tone_shift"), r["consensus_divergence"],
                r.get("key_themes", "[]"),
            ))

        # Store key metrics in fundamentals table for cross-referencing
        if latest.get("llm_tone") is not None:
            all_fund_rows.append((symbol, "transcript_llm_tone", latest["llm_tone"]))
        if latest.get("tone_shift") is not None:
            all_fund_rows.append((symbol, "transcript_tone_shift", latest["tone_shift"]))
        all_fund_rows.append((symbol, "transcript_uncertainty_ratio", latest["uncertainty_ratio"]))
        all_fund_rows.append((symbol, "transcript_confidence_ratio", latest["confidence_ratio"]))
        all_fund_rows.append((symbol, "transcript_consensus_divergence", latest["consensus_divergence"]))

        # Flag significant tone shifts
        tone_shift = latest.get("tone_shift")
        if tone_shift is not None:
            if tone_shift <= -2.0:
                tone_alerts.append((symbol, tone_shift, "BEARISH SHIFT", latest.get("consensus_divergence", 0)))
            elif tone_shift >= 2.0:
                tone_alerts.append((symbol, tone_shift, "BULLISH SHIFT", latest.get("consensus_divergence", 0)))

        print(f"    {len(results)} quarters | Tone: {latest.get('llm_tone', 'N/A')} | "
              f"Shift: {latest.get('tone_shift', 'N/A')} | "
              f"Divergence: {latest['consensus_divergence']}")

        time.sleep(0.3)

    # Save
    upsert_many("transcript_analysis",
                ["symbol", "quarter", "year", "transcript_date",
                 "word_count", "uncertainty_ratio", "confidence_ratio",
                 "llm_tone", "tone_shift", "consensus_divergence", "key_themes"],
                all_db_rows)
    upsert_many("fundamentals", ["symbol", "metric", "value"], all_fund_rows)

    # Summary
    print(f"\n  Transcript analysis complete: {len(all_db_rows)} quarter-transcripts analyzed")

    if tone_alerts:
        tone_alerts.sort(key=lambda x: abs(x[1]), reverse=True)
        print(f"\n  TONE SHIFT ALERTS:")
        print(f"    {'Symbol':12s} | {'Shift':>6s} | {'Direction':>14s} | {'Divergence':>10s}")
        print(f"    {'-'*12}-+-{'-'*6}-+-{'-'*14}-+-{'-'*10}")
        for sym, shift, direction, div in tone_alerts:
            print(f"    {sym:12s} | {shift:+5.1f} | {direction:>14s} | {div:+9.1f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Earnings Transcript Alpha Extractor")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--no-gemini", action="store_true", help="Skip Gemini LLM analysis (quantitative only)")
    args = parser.parse_args()

    sym_list = args.symbols.split(",") if args.symbols else None
    run(sym_list, use_gemini=not args.no_gemini)
