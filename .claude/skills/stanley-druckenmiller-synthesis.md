---
name: stanley-druckenmiller-synthesis
description: >
  Synthesize all Druckenmiller Alpha System module outputs into a single high-conviction
  investment thesis with sector positioning, top stock candidates, and exposure guidance.
  Use when the user wants a macro-to-stock investment thesis from the current system state,
  asks "what does the system say to buy", or wants a weekly portfolio review.
---

## Druckenmiller Synthesis Workflow

Druckenmiller's philosophy: **"Be right once a year on a big theme. Concentrate there. Size up."**
This skill reads the system's live DB outputs and synthesizes them into that framework.

---

### Step 1 — Read Macro Regime

```python
from tools.db import query_df
import json

regime = query_df("""
    SELECT date, regime, total_score, fed_funds_score, m2_score, real_rates_score,
           yield_curve_score, credit_spreads_score, dxy_score, vix_score, details
    FROM macro_scores
    ORDER BY date DESC LIMIT 1
""")
```

Parse `details` JSON for cross-asset ratio scores (spy_tlt, iwm_spy, xly_xlp).

**Interpret:**
- `strong_risk_on` (+60 to +100): Full deployment, growth tilt, size into leaders
- `risk_on` (+20 to +60): 80-100% net long, favor momentum
- `neutral` (-20 to +20): 50-70% long, balanced sector mix
- `risk_off` (-60 to -20): 30-50% long, defensive tilt, tighten stops
- `strong_risk_off` (-100 to -60): 0-30% long, raise cash, hedge

Cross-asset confirmation: if spy_tlt > 0 and xly_xlp > 0 → regime confirmed. If diverging → regime transition underway, reduce conviction.

---

### Step 2 — Read Market Breadth

```python
breadth = query_df("""
    SELECT date, pct_above_200ma, advance_decline_ratio, new_highs, new_lows, breadth_score
    FROM market_breadth
    ORDER BY date DESC LIMIT 5
""")
```

**Interpret breadth_score (0-20):**
- ≥15: Healthy, broad participation — high conviction long
- 10-14: Moderate — selective, focus on leaders
- 5-9: Narrowing — reduce exposure, leaders only
- <5: Deteriorating — defensive posture

---

### Step 3 — Read IC-Weighted Module Performance

```python
ic_summary = query_df("""
    SELECT module, regime, horizon_days, mean_ic, ic_t_stat, sharpe_ic
    FROM module_ic_summary
    WHERE regime = '<current_regime>'
    ORDER BY mean_ic DESC
""")
```

Identify the top 3-4 modules with highest `mean_ic` and `ic_t_stat > 1.5` in the current regime.
These are the modules whose signals to weight most heavily.

---

### Step 4 — Pull Top Stock Candidates

```python
# Get convergence scores (multi-module agreement)
top_stocks = query_df("""
    SELECT c.symbol, c.convergence_score, c.date,
           t.total_score as tech_score,
           f.total_score as fundamental_score,
           s.conviction_score as smart_money_score
    FROM convergence_signals c
    LEFT JOIN technical_scores t ON c.symbol = t.symbol AND c.date = t.date
    LEFT JOIN fundamental_scores f ON c.symbol = f.symbol AND c.date = f.date
    LEFT JOIN smart_money_scores s ON c.symbol = s.symbol AND c.date = s.date
    WHERE c.date = (SELECT MAX(date) FROM convergence_signals)
    ORDER BY c.convergence_score DESC
    LIMIT 20
""")
```

Filter for stocks where the top IC modules (from Step 3) all score positively.

---

### Step 5 — Identify the Dominant Theme

Look at the top 10-15 candidates from Step 4. What sector are they clustered in?
Cross-reference with:
- `xly_xlp` ratio direction → cyclicals or defensives?
- `iwm_spy` ratio direction → small cap leadership or large cap?
- Recent macro signals (yield curve, real rates) → growth or value?

**State the dominant theme in one sentence.** Example:
> "Monetary easing + steepening yield curve + financials leading → early-cycle reflation trade; banks and industrials are the fat pitch."

---

### Step 6 — Build the Thesis Output

Structure the output as:

```
## DRUCKENMILLER ALPHA SYNTHESIS — [DATE]

### Macro Regime: [REGIME] ([SCORE])
[2-3 sentence characterization of current macro environment]

### Cross-Asset Confirmation: [CONFIRMED/TRANSITIONING/DIVERGING]
- SPY/TLT ratio: [direction] → [implication]
- IWM/SPY ratio: [direction] → [implication]
- XLY/XLP ratio: [direction] → [implication]

### Breadth: [HEALTHY/MODERATE/NARROW/DETERIORATING] (score: X/20)
[1-2 sentences on breadth interpretation]

### Dominant Theme
[One sentence. This is the core thesis.]

### Top Module Signals (this regime)
[Table: module | mean_IC | regime | best horizon]

### High-Conviction Candidates (1-5 names max)
[Table: symbol | sector | convergence | tech | fundamental | smart_money | thesis fit]

### Portfolio Posture
- Net exposure: [X%]
- Sector tilt: [growth/value/defensive]
- Top position size: [concentrated or diversified]
- Risk-off trigger: [specific condition that invalidates thesis]
```

---

### References
- Macro regime data: `macro_scores` table (tools/macro_regime.py)
- Cross-asset ratios: `details` JSON column in macro_scores (SPY/TLT, IWM/SPY, XLY/XLP)
- Breadth: `market_breadth` table (tools/market_breadth.py)
- IC performance: `module_ic_summary` table (tools/signal_ic.py)
- Stock scores: `convergence_signals`, `technical_scores`, `fundamental_scores`, `smart_money_scores`
- Druckenmiller philosophy: concentrated positions on one big macro theme per year
