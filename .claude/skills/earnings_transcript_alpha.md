# Earnings Transcript Alpha Extractor

Analyze earnings call transcripts for management tone shifts, hedging language, and consensus divergence. Combines quantitative NLP with Gemini LLM analysis.

## When to Use
- Before earnings season (analyze prior transcripts for stocks you hold or are watching)
- After earnings are reported (analyze the new transcript immediately)
- When a stock moves sharply post-earnings (understand what management said)
- Pre-earnings screening for BUY-rated stocks reporting next week

## How to Run

### Default (upcoming earnings + BUY signals, with Gemini):
```bash
cd "/Users/Jurgis2/Library/Mobile Documents/com~apple~CloudDocs/Druckemiller"
python -m tools.earnings_transcript_analyzer
```

### Specific symbols:
```bash
python -m tools.earnings_transcript_analyzer --symbols AAPL,MSFT,GOOGL
```

### Quantitative only (no Gemini LLM, faster):
```bash
python -m tools.earnings_transcript_analyzer --symbols AAPL --no-gemini
```

## What It Computes

### Quantitative NLP (no LLM, instant):
| Metric | What It Measures |
|--------|-----------------|
| Uncertainty Ratio | Frequency of hedging/caution words per 1000 words |
| Confidence Ratio | Frequency of bullish/strength words per 1000 words |
| Net Sentiment | Confidence minus uncertainty (higher = more bullish) |
| Sentiment Shift | Change in net sentiment vs prior quarter |

### Gemini LLM Analysis (deep qualitative):
| Metric | What It Measures |
|--------|-----------------|
| LLM Tone (-5 to +5) | Overall management tone from bearish to bullish |
| Tone Shift | Change in tone vs prior quarter (biggest alpha signal) |
| Forward Confidence (0-10) | How confident management sounds about the future |
| Management Hedging (0-10) | How much they're qualifying/hedging statements |
| Capex/Hiring Signal | Expanding, stable, or contracting |
| Competitive Position | Strengthening, stable, or weakening |
| Accounting Flags | Any unusual accounting mentions detected |
| Key Themes | Top 3-5 topics from the call |

### Consensus Divergence (-100 to +100):
- **Negative**: Management more cautious than analyst consensus (potential miss ahead)
- **Positive**: Management more bullish than consensus (potential beat ahead)

## How to Interpret Results

### Key Signals:
1. **Tone Shift <= -2.0**: Major bearish shift — management significantly more cautious than last quarter. Even if stock is rated BUY, consider reducing.
2. **Tone Shift >= +2.0**: Major bullish shift — management significantly more confident. Look for entry if stock isn't already overbought.
3. **Consensus Divergence < -30**: Management way more cautious than Street expects — potential earnings miss coming.
4. **Consensus Divergence > +30**: Management way more bullish than Street — potential earnings beat.
5. **High Uncertainty + Low Confidence**: Classic pre-miss language pattern.

### Cross-Reference with Other Skills:
- **Positive tone shift + high variant score + clean forensics** = Highest conviction BUY
- **Negative tone shift + BUY signal** = Potential trap, investigate further
- **Accounting flags in transcript + forensic red flags** = Strong AVOID signal

### Query examples:
```sql
-- Recent tone shift alerts
SELECT symbol, quarter, llm_tone, tone_shift, consensus_divergence
FROM transcript_analysis
WHERE ABS(tone_shift) >= 2.0
ORDER BY quarter DESC;

-- Pre-earnings research: BUY stocks with transcript data
SELECT t.symbol, t.llm_tone, t.tone_shift, t.consensus_divergence,
       s.signal, s.composite_score
FROM transcript_analysis t
JOIN signals s ON t.symbol = s.symbol
WHERE s.signal IN ('BUY', 'STRONG BUY')
AND s.date = (SELECT MAX(date) FROM signals)
AND t.quarter = (SELECT MAX(quarter) FROM transcript_analysis WHERE symbol = t.symbol);

-- Combined alpha signal: all 3 skills
SELECT s.symbol, s.signal,
       f_forensic.value as forensic_score,
       f_variant.value as variant_score,
       f_tone.value as transcript_tone
FROM signals s
LEFT JOIN fundamentals f_forensic ON s.symbol = f_forensic.symbol AND f_forensic.metric = 'forensic_score'
LEFT JOIN fundamentals f_variant ON s.symbol = f_variant.symbol AND f_variant.metric = 'variant_score'
LEFT JOIN fundamentals f_tone ON s.symbol = f_tone.symbol AND f_tone.metric = 'transcript_llm_tone'
WHERE s.signal IN ('BUY', 'STRONG BUY')
AND s.date = (SELECT MAX(date) FROM signals)
ORDER BY COALESCE(f_variant.value, 0) DESC;
```

## Notes
- Transcripts cached indefinitely (they don't change after publication)
- Gemini analysis: ~1 API call per quarter per symbol, rate-limited with 1s delays
- Not part of daily pipeline — run on-demand or before earnings season
- Falls back to quantitative-only mode if GEMINI_API_KEY is not set
