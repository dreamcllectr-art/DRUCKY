# Variant Perception Engine

Find the fattest mispricings by comparing what the market is pricing against historical base rates, analyst estimate biases, and probabilistic fair value scenarios.

## When to Use
- After daily scan generates BUY/STRONG BUY signals (rank by conviction)
- When building a new position (understand how your view differs from consensus)
- Sector deep-dives (run on all stocks in a sector to find relative value)
- Weekly analysis of the watchlist

## How to Run

### Default (analyzes current BUY signals):
```bash
cd "/Users/Jurgis2/Library/Mobile Documents/com~apple~CloudDocs/Druckemiller"
python -m tools.variant_perception
```

### Specific symbols:
```bash
python -m tools.variant_perception --symbols AAPL,MSFT,GOOGL
```

### Full universe:
```bash
python -m tools.variant_perception --all
```

## What It Computes

| Metric | What It Tells You |
|--------|------------------|
| Implied Growth | What growth rate the market is currently pricing in |
| Base Rate Growth | Historical 5yr/10yr revenue CAGR (what the company actually does) |
| Growth Gap | Implied minus base rate (positive = market expects acceleration) |
| Estimate Bias | Do analysts chronically under/over-estimate this company? |
| Revision Momentum | Are forward estimates being revised up or down? |
| Fair Value (Bull/Base/Bear) | 3-scenario DCF with probability weights |
| Prob-Weighted Fair Value | Expected value across all scenarios |
| Upside % | How much the stock is mispriced vs probabilistic fair value |
| **Variant Score** | **Composite 0-100 (higher = bigger mispricing opportunity)** |

## How to Interpret Results

### The "Fat Pitch" Framework:
1. **Variant Score > 75**: Large mispricing — market is significantly wrong about growth trajectory
2. **Variant Score 65-75**: Meaningful mispricing — worth deep investigation
3. **Variant Score 50-65**: Moderate — consensus roughly correct
4. **Variant Score < 50**: Market may be right, or overvalued

### Cross-Reference (CRITICAL):
- **High variant + forensic_score > 70** = High conviction opportunity
- **High variant + forensic_score < 30** = REJECT (don't take variant views on companies cooking the books)
- **High variant + positive estimate bias** = Strongest signal (market AND analysts are both too low)
- **High variant + negative growth gap** = Market pricing deceleration that history doesn't support

### Query examples:
```sql
-- Alpha Conviction ranking: high variant + clean books
SELECT v.symbol, v.variant_score, v.upside_pct, v.growth_gap, v.estimate_bias,
       f.value as forensic_score
FROM variant_analysis v
JOIN fundamentals f ON v.symbol = f.symbol AND f.metric = 'forensic_score'
WHERE v.variant_score >= 65 AND f.value >= 60
AND v.date = (SELECT MAX(date) FROM variant_analysis)
ORDER BY v.variant_score DESC;

-- Biggest growth gap opportunities
SELECT symbol, variant_score, implied_growth, base_rate_growth, growth_gap, upside_pct
FROM variant_analysis
WHERE growth_gap < -0.05
AND date = (SELECT MAX(date) FROM variant_analysis)
ORDER BY growth_gap ASC;
```

## Integration
- Variant score stored in `fundamentals` table and `variant_analysis` table
- Scenario weights adjust by macro regime (more bearish weights in risk-off)
- Optional step in daily pipeline (runs after forensics)
- ~6 FMP API calls per symbol
