# Accounting Forensics Scanner

Detect earnings manipulation, accounting red flags, and earnings quality across the stock universe. Uses Beneish M-Score, accruals analysis, cash conversion trends, and more.

## When to Use
- Before taking a position in any stock (verify books are clean)
- After the daily pipeline generates BUY signals (filter out red flags)
- When investigating specific companies for accounting irregularities
- Weekly full-universe scan to catch emerging red flags

## How to Run

### Full universe scan:
```bash
cd "/Users/Jurgis2/Library/Mobile Documents/com~apple~CloudDocs/Druckemiller"
python -m tools.accounting_forensics
```

### Specific symbols:
```bash
python -m tools.accounting_forensics --symbols AAPL,MSFT,TSLA
```

## What It Computes

| Metric | What It Detects |
|--------|----------------|
| Beneish M-Score | Probability of earnings manipulation (>-1.78 = likely manipulator) |
| Accruals Ratio | Earnings not backed by cash (>0.10 = red flag) |
| Cash Conversion | OCF vs Net Income ratio (<0.80 = poor quality) |
| Cash Conversion Trend | Deteriorating cash quality over 5 years |
| Receivables Flag | Channel stuffing (AR growing >1.5x revenue) |
| Inventory Flag | Inventory buildup (growing >1.5x COGS) |
| Depreciation Trend | Extending asset lives to boost earnings |
| Piotroski F-Score | Financial strength (0-9, <4 = weak) |
| Altman Z-Score | Bankruptcy probability (<1.8 = distress zone) |
| **Forensic Score** | **Composite 0-100 (higher = cleaner books)** |

## How to Interpret Results

### After running, do this:
1. Check `forensic_alerts` table for RED_FLAG and WARNING entries
2. Cross-reference against current BUY signals:
   - **BUY + forensic_score < 30** = DO NOT BUY (accounting red flags)
   - **SELL + forensic_score > 80** = Investigate (clean books, possibly oversold)
3. Beneish M-Score > -1.78 is the strongest single red flag — academic research shows this predicts both manipulation AND subsequent underperformance

### Query examples:
```sql
-- BUY signals with accounting red flags
SELECT s.symbol, s.signal, s.composite_score, f.value as forensic_score
FROM signals s
JOIN fundamentals f ON s.symbol = f.symbol AND f.metric = 'forensic_score'
WHERE s.signal IN ('BUY', 'STRONG BUY')
AND f.value < 30
AND s.date = (SELECT MAX(date) FROM signals);

-- All red flag alerts
SELECT * FROM forensic_alerts WHERE severity = 'RED_FLAG' ORDER BY date DESC;

-- Pristine books among oversold stocks
SELECT s.symbol, s.composite_score, f.value as forensic_score
FROM signals s
JOIN fundamentals f ON s.symbol = f.symbol AND f.metric = 'forensic_score'
WHERE s.signal IN ('SELL', 'STRONG SELL')
AND f.value >= 80
AND s.date = (SELECT MAX(date) FROM signals);
```

## Integration
- Forensic score feeds into `fundamental_scoring.py` as a quality penalty
- Part of the optional daily pipeline (runs after FMP fundamentals fetch)
- ~4 FMP API calls per symbol, cached weekly (financials only change quarterly)
