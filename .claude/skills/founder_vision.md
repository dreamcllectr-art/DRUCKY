# Founder Vision & Capital Allocation Analyzer

Identifies Bezos-quality thinking in CEO annual letters before the market prices it in.

**The core insight:** When Amazon's income statement was all red in 1997, the only tell was Bezos' shareholder letter — clarity of thought, long-term orientation, specific theory of value creation. AI can now apply that lens systematically to hundreds of companies.

This is a qualitative signal that none of the other three tools capture. It answers: *is the person running this company exceptional?*

---

## When to Use

- **Before entering a large position**: Does management quality justify conviction?
- **When forensics + variant scores align**: Clean books + mispricing + exceptional CEO = maximum conviction
- **When a new CEO takes over**: Is the quality of thinking rising or falling?
- **For portfolio reviews**: Are any of your holdings showing deteriorating letter quality (management decay signal)?
- **For deep research**: Pull 5 years of letters for one company to understand how the thesis has evolved

---

## How to Run

```bash
cd "/Users/Jurgis2/Library/Mobile Documents/com~apple~CloudDocs/Druckemiller"

# Default: analyze current BUY/STRONG BUY signals
python -m tools.founder_letter_analyzer

# Specific companies and years
python -m tools.founder_letter_analyzer --symbols AMZN,NVR,FRFHF --years 2023

# Full 5-year history for deep research on one company
python -m tools.founder_letter_analyzer --symbols AMZN --years 2019,2020,2021,2022,2023

# Re-analyze a cached result (e.g. after Gemini prompt was updated)
python -m tools.founder_letter_analyzer --symbols NVDA --force

# Fetch and cache letters without Gemini analysis (useful for batch pre-caching)
python -m tools.founder_letter_analyzer --no-llm
```

---

## The 8 Scoring Dimensions

Each dimension is scored 0-10 with a **required direct quote** from the letter. No black boxes.

| Dimension | Weight | What separates 9-10 from 5 |
|-----------|--------|---------------------------|
| Capital Allocation | 20% | Every investment explained with expected returns + opportunity cost explicitly discussed |
| Long-term Orientation | 15% | Explicit multi-year framing, willingness to sacrifice current earnings for future value |
| Failure Attribution | 15% | Names specific failures, takes personal responsibility, extracts learnings — doesn't blame macro |
| Moat Articulation | 15% | Explains the *causal mechanism* of WHY they win — not "great people" but the actual structural advantage |
| Vision Specificity | 10% | Strategy specific enough to be proven wrong in 5 years. Falsifiable commitments. |
| Customer/Value Focus | 10% | Obsessed with end-user outcomes, specific customer metrics cited |
| Intellectual Honesty | 10% | Distinguishes what they know vs. believe, acknowledges genuine uncertainty |
| Founder Mindset | 5% | Talks like an owner who loves the business, not a manager running processes |

---

## Tier Classification

| Tier | Score | What it means |
|------|-------|---------------|
| **BEZOS-TIER** | 85-100 | Read every word. Consider position regardless of current valuation. |
| **BUFFETT-TIER** | 70-84 | Exceptional capital allocator. High management quality confidence. |
| **ABOVE AVERAGE** | 55-69 | Genuine thought. Warrants deeper investigation. |
| **AVERAGE** | 40-54 | Competent but undistinctive. Standard institutional quality. |
| **BUREAUCRATIC** | 25-39 | Management-speak heavy. Proceed with caution. |
| **RED FLAGS** | 0-24 | Concerning patterns detected. Investigate before any position. |

---

## The YoY Trajectory Signal

**This is a standalone alpha signal separate from the absolute tier.**

A CEO whose letters are improving year-over-year is getting better at thinking and communicating — typically their capital allocation decisions are improving too. A CEO whose letters are deteriorating (more generic, more bureaucratic, more external blame) is often a leading indicator of underperformance.

- `improved` = letters are becoming more specific, more honest, more long-term oriented
- `consistent` = thesis is stable and coherent
- `shifted` = strategy has changed, warranting investigation but not necessarily negative
- `concerning_shift` = sudden pivot, increased blame attribution, loss of specificity — warning signal

---

## How to Interpret Output

### After running, look for:

1. **Exceptional passages** — Gemini extracts only genuinely notable quotes. If you see one, read the full letter.
2. **Red flags** — Specific patterns: chronic external blame, strategy pivots without explanation, buzzword density
3. **Investor verdict** — Gemini's direct 2-3 sentence assessment. Read this first.
4. **YoY consistency** — Is the thesis getting clearer or murkier year over year?

---

## Query Examples

```sql
-- All Bezos/Buffett-tier companies (updated by the tool)
SELECT symbol, tier, composite_score, investor_verdict
FROM letter_analysis
WHERE year = 2023
AND tier IN ('bezos_tier', 'buffett_tier')
ORDER BY composite_score DESC;

-- Companies with declining letter quality (management decay signal)
SELECT symbol, year, composite_score, consistency_with_prior, thesis_summary
FROM letter_analysis
WHERE consistency_with_prior = 'concerning_shift'
ORDER BY year DESC;

-- Exceptional passages worth reading
SELECT symbol, year, tier, exceptional_passages
FROM letter_analysis
WHERE exceptional_passages != '[]'
AND year >= 2022
ORDER BY composite_score DESC;

-- Companies with red flags in letter despite BUY signal
SELECT la.symbol, s.signal, la.tier, la.composite_score,
       la.red_flags, la.investor_verdict
FROM letter_analysis la
JOIN signals s ON la.symbol = s.symbol
    AND s.date = (SELECT MAX(date) FROM signals)
WHERE la.tier IN ('bureaucratic', 'red_flags')
AND s.signal IN ('BUY', 'STRONG BUY');
```

---

## The Trifecta Query — Maximum Conviction

This is the ultimate cross-skill query. Run it after all four alpha edge tools have executed.

**Reasoning:** If the market is mispricing the stock (variant perception), the books are clean (forensics), the transcript shows positive tone, AND the CEO writes like Bezos — that is the rarest alignment of signals. Size up.

```sql
SELECT la.symbol, la.tier,
       la.composite_score  AS letter_score,
       la.investor_verdict,
       s.signal,
       f_f.value  AS forensic_score,
       f_v.value  AS variant_score,
       f_u.value  AS upside_pct,
       f_t.value  AS transcript_tone,
       f_tr.value AS letter_trajectory
FROM letter_analysis la
JOIN signals s ON la.symbol = s.symbol
    AND s.date = (SELECT MAX(date) FROM signals)
LEFT JOIN fundamentals f_f  ON la.symbol = f_f.symbol  AND f_f.metric  = 'forensic_score'
LEFT JOIN fundamentals f_v  ON la.symbol = f_v.symbol  AND f_v.metric  = 'variant_score'
LEFT JOIN fundamentals f_u  ON la.symbol = f_u.symbol  AND f_u.metric  = 'variant_upside_pct'
LEFT JOIN fundamentals f_t  ON la.symbol = f_t.symbol  AND f_t.metric  = 'transcript_llm_tone'
LEFT JOIN fundamentals f_tr ON la.symbol = f_tr.symbol AND f_tr.metric = 'letter_yoy_trajectory'
WHERE la.tier IN ('bezos_tier', 'buffett_tier', 'above_average')
    AND s.signal IN ('BUY', 'STRONG BUY')
    AND COALESCE(f_f.value, 50) >= 55   -- clean books (no red flags)
    AND COALESCE(f_v.value, 0)  >= 55   -- meaningful mispricing
ORDER BY la.composite_score + COALESCE(f_v.value, 0) DESC;
```

**How to read the output:**
- `letter_score >= 70` + `variant_score >= 65` + `forensic_score >= 65` = maximum conviction, consider position sizing up
- `letter_trajectory = 1` (improved) = additional positive signal
- Any `red_flags` in letter analysis = read them before sizing up

---

## Data Sources & Fetching Cascade

The tool tries four strategies in order, stopping at the first success:

1. **EDGAR EX-13** — The Annual Report to Shareholders exhibit filed with the SEC. This is where Bezos' letters are. Most signal-rich source.
2. **EDGAR 10-K letter section** — Extracts the "Dear Shareholders" section from the main 10-K document if no EX-13 exists.
3. **Firecrawl** — Scrapes the company's investor relations page directly.
4. **Serper + Firecrawl** — Searches for the letter online, fetches the top results.

Letters are cached permanently in `.tmp/letters/{SYMBOL}_{YEAR}.txt` — they don't change after publication.

Not all companies write shareholder letters. Financial companies and many industrials only have 10-K MD&A sections. The `source` field in `letter_analysis` tells you what was analyzed.

---

## Integration with Scoring Pipeline

The tool writes three metrics to the `fundamentals` table for cross-pipeline use:
- `letter_composite_score` — 0-100 composite
- `letter_tier` — numeric: 5=bezos_tier, 4=buffett_tier, 3=above_average, 2=average, 1=bureaucratic, 0=red_flags
- `letter_yoy_trajectory` — 1=improved, 0=consistent, -1=shifted, -2=concerning_shift

These feed into `fundamental_scoring.py`'s `score_quality_smart_money()` function:
- Bezos-tier CEO: +3 quality pts
- Buffett-tier CEO: +2 quality pts
- Red flags: -3 quality pts
- Bureaucratic: -1 quality pt
- Improving trajectory: +2 quality pts
- Concerning shift: -3 quality pts

Not part of daily pipeline — run on-demand for research and position decisions.
