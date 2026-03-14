# Scoring Methodology

## Philosophy
Stan Druckenmiller's investment process codified:
1. Macro regime determines market environment
2. Technical analysis screens for the strongest setups
3. Fundamentals validate the quality
4. Only asymmetric risk/reward (3:1+) trades surface

## Macro Regime Score (-100 to +100)

Seven indicators, each -15 to +15:

| Indicator | Bullish (+15) | Bearish (-15) |
|-----------|--------------|---------------|
| Fed Funds Direction | Cutting aggressively | Hiking aggressively |
| M2 Growth (YoY) | >5% expansion | Negative / contracting |
| Real Rates | Deeply negative (<-3%) | Positive >2% |
| Yield Curve (2s10s) | Steep (>150bp) | Deeply inverted |
| Credit Spreads (HY OAS) | Tight (<3%) | Wide (>6%) |
| DXY Trend (3mo) | Weakening dollar | Strengthening dollar |
| VIX + Term Structure | Low (<15) + contango | High (>30) + backwardation |

### Regime Classification
- **Strong Risk-On** (60+): Full risk, favor longs
- **Risk-On** (20-59): Favor longs, moderate sizing
- **Neutral** (-19 to 19): Selective, reduced exposure
- **Risk-Off** (-59 to -20): Defensive, favor cash
- **Strong Risk-Off** (<-60): Heavy cash, hedges, shorts

## Technical Score (0-100)

Five sub-scores, each 0-20:

### Trend (0-20)
- Price > 50 DMA: +5
- Price > 200 DMA: +5
- Golden cross (50 > 200 DMA): +5
- ADX > 25: +5 (strong trend)

### Momentum (0-20)
- RSI 50-70: +7 (bullish), >70: +3, <30: +2
- MACD histogram positive & rising: +7
- 20-day ROC top quartile: +6

### Breakout (0-20)
- Within 5% of 52w high: +10
- Volume > 2x 20-day avg: +5
- Bollinger squeeze (bandwidth 10th percentile): +5

### Relative Strength (0-20)
- 3-month return vs benchmark (SPY/BTC/DXY inverse)
- Top decile: 20, Top quartile: 17, etc.

### Market Breadth (0-20)
- Applied uniformly to all assets
- % of S&P above 200 DMA, A/D ratio, new highs-lows

## Fundamental Score (0-100, stocks only)

Crypto and commodities default to 50 (neutral).

### Valuation (0-20)
- P/E vs sector median (lower = better)
- P/B vs sector median
- Dividend yield bonus

### Growth (0-20)
- Revenue growth YoY: >20% = 10pts
- Earnings growth YoY: >20% = 10pts

### Profitability (0-20)
- ROE > 20%: 7pts
- Gross margin > 60%: 7pts
- Operating margin > 25%: 6pts

### Financial Health (0-20)
- Debt/Equity < 50: +5
- Current ratio > 2.0: +5

### Quality (0-20)
- Insider ownership > 10%: +5

## Composite Signal

Weighted blend that shifts by macro regime:

| Regime | Macro Wt | Tech Wt | Fund Wt |
|--------|----------|---------|---------|
| Strong Risk-On | 20% | 50% | 30% |
| Risk-On | 25% | 45% | 30% |
| Neutral | 35% | 40% | 25% |
| Risk-Off | 45% | 35% | 20% |
| Strong Risk-Off | 50% | 30% | 20% |

**Rationale**: In risk-off environments, macro dominates (no amount of good technicals saves you). In risk-on, finding the strongest horses (technicals) matters most.

### Signal Classification
- STRONG BUY: Composite >= 80
- BUY: 65-79
- NEUTRAL: 40-64
- SELL: 25-39
- STRONG SELL: < 25

## Position Sizing

- **Risk per trade**: 1% for BUY, 2% for STRONG BUY
- **Size formula**: portfolio_value * risk% / (entry - stop_loss)
- **Liquidity cap**: Never exceed 5% of 20-day average daily dollar volume
- **Single position cap**: 20% of portfolio
- **Gross exposure cap**: 150%
- **Minimum R:R**: 3.0 (only signals with R:R >= 3 surface as actionable)

## Stop Loss Calculation
Lower of:
1. 2x ATR(14) below entry price
2. 2% below 50-day moving average

## Target Calculation
Target = Entry + 3x (Entry - Stop Loss)
Minimum 3:1 risk/reward ratio enforced.
