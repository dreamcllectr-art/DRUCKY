---
name: macro-regime-detector
description: >
  Run, interpret, and debug the macro regime engine. Use when the user wants to check
  the current macro regime, understand why the regime score changed, investigate cross-asset
  ratio signals, or diagnose macro_regime.py output.
---

## Macro Regime Detection Workflow

The system uses a two-layer model in `tools/macro_regime.py`:

| Layer | Indicators | Score Range | Characteristics |
|---|---|---|---|
| FRED Fundamentals | fed_funds, m2, real_rates, yield_curve, credit_spreads, dxy, vix | ±84 | Lagging, high-precision |
| Cross-Asset Ratios | SPY/TLT, IWM/SPY, XLY/XLP | ±30 | Leading/coincident |
| **Total** | | **±100** | Clamped |

---

### Step 1 — Run the Engine

```bash
cd ~/druckenmiller
/tmp/druck_venv/bin/python -u -m tools.macro_regime
```

If `macro_indicators` table is empty, run the macro fetcher first:
```bash
/tmp/druck_venv/bin/python -u -m tools.fetch_macro
```

If cross-asset ETFs are missing (TLT, IWM, XLY, XLP not in `price_data`), fetch prices:
```bash
/tmp/druck_venv/bin/python -u -m tools.fetch_prices
```

---

### Step 2 — Read Current Regime

```python
from tools.db import query_df
import json

row = query_df("""
    SELECT date, regime, total_score,
           fed_funds_score, m2_score, real_rates_score, yield_curve_score,
           credit_spreads_score, dxy_score, vix_score, details
    FROM macro_scores
    ORDER BY date DESC LIMIT 1
""").iloc[0]

cross = json.loads(row["details"] or "{}")
print(f"Regime: {row['regime']} ({row['total_score']:+.0f})")
print(f"Cross-asset: SPY/TLT={cross.get('spy_tlt',0):+.1f}, "
      f"IWM/SPY={cross.get('iwm_spy',0):+.1f}, XLY/XLP={cross.get('xly_xlp',0):+.1f}")
```

---

### Step 3 — Interpret the Regime

**Regime thresholds** (from `tools/config.py MACRO_REGIME`):
- `strong_risk_on`: ≥60
- `risk_on`: ≥20
- `neutral`: ≥-20
- `risk_off`: ≥-60
- `strong_risk_off`: <-60

**Cross-asset signal matrix:**

| SPY/TLT | IWM/SPY | XLY/XLP | Interpretation |
|---|---|---|---|
| + | + | + | Regime confirmed, full conviction |
| + | + | - | Reflation without consumer strength — industrials/materials, not consumer disc |
| + | - | + | Large-cap leadership, late cycle — mega-cap tech, not small caps |
| - | - | - | Risk-off confirmed — raise cash, defensives |
| mixed | mixed | mixed | Transition underway — reduce size, wait for clarity |

**Regime-to-posture mapping:**
- `strong_risk_on`: 100% deployed, concentrated in 3-5 leaders
- `risk_on`: 80-100% long, sector leaders
- `neutral`: 50-70% long, factor-balanced
- `risk_off`: 30-50% long, defensive quality
- `strong_risk_off`: 0-30% long, cash/hedges

---

### Step 4 — Check Regime History (trend matters)

```python
history = query_df("""
    SELECT date, regime, total_score
    FROM macro_scores
    ORDER BY date DESC LIMIT 10
""")
print(history.to_string(index=False))
```

A regime improving over 3+ days is more actionable than a single-day reading.

---

### Step 5 — Diagnose Low Cross-Asset Scores

If cross-asset scores are all 0 (ETFs not fetched yet):

```bash
# Verify ETFs exist in price_data
/tmp/druck_venv/bin/python -c "
from tools.db import query_df
etfs = query_df(\"SELECT symbol, MAX(date) as latest FROM price_data WHERE symbol IN ('TLT','IWM','XLY','XLP') GROUP BY symbol\")
print(etfs)
"
```

If empty, fetch prices to populate cross-asset ETFs:
```bash
/tmp/druck_venv/bin/python -u -m tools.fetch_prices
```

---

### Scoring Reference

**FRED Layer (each ±15):**
- `fed_funds`: cutting → bullish (−1% cut = +15)
- `m2`: YoY growth >5% = +15
- `real_rates`: deeply negative = +15
- `yield_curve`: 2s10s steep = +15
- `credit_spreads`: HY OAS tight (<3%) = +15
- `dxy`: weakening dollar = +15
- `vix`: <15 + contango = +10 to +15

**Cross-Asset Layer (each ±10, 63-day momentum):**
- `spy_tlt`: SPY/TLT ratio +5% → +10 (stocks beating bonds)
- `iwm_spy`: IWM/SPY ratio +3% → +10 (small caps leading)
- `xly_xlp`: XLY/XLP ratio +2.5% → +10 (cyclicals leading defensives)

---

### References
- Engine: `tools/macro_regime.py`
- Config: `tools/config.py` → `MACRO_REGIME`, `CROSS_ASSET_ETFS`
- DB table: `macro_scores` (details column = JSON cross-asset scores)
- Price data: `tools/fetch_prices.py` (cross-asset ETFs fetched as "benchmark")
