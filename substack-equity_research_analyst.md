# I Built a $200,000/Year Equity Research Analyst. It Runs on My Laptop.

*Using Claude Code and Google Antigravity.*
*Feb 20, 2026*

---

While everyone argues about which chatbot is marginally smarter, the real edge is in pipelines.

## Before vs. After

| | Before | After |
|---|---|---|
| **Time** | 6–8 hours per company | One command, ~2.5 minutes |
| **Data Sources** | Bloomberg → Excel → EDGAR → news | Live data from free public APIs |
| **Cost** | $24k/year Bloomberg seat | $0 marginal cost per run |
| **Output** | Static assumptions, one "price target" | Bull / Base / Bear + stress tests |

I realized this after watching a friend spend an entire day updating a single DCF model. Smart work buried under grunt work.

So I built a system to remove the grunt work. It runs locally on my laptop and does in ~2.5 minutes what takes a human analyst hours.

---

## A Market Scanner Built to Find Real Dislocations

I open my Antigravity environment and launch Claude Code. I type one command:

```bash
python3 models/market_scanner.py --scan-all
```

Ninety seconds later, I'm looking at six sectors scanned, valuation dislocations flagged, special situations surfaced, and insider cluster buys detected. Every opportunity is filtered through three quality gates: multi-source confirmation, identifiable catalyst, and quantifiable edge.

This market scanner searches for undervalued and overvalued stocks, special situations (M&A, spinoffs, activist campaigns, index rebalancing), and sector rotation signals, then ranks everything by conviction and urgency. The sector heat map shows where the real money is flowing.

On its own, this replaces a surprising amount of what people use Bloomberg for.

When something catches my eye — say, a semiconductor name flagged as 15% undervalued with an insider cluster buy — I don't open a spreadsheet. I type a second command:

```bash
python3 models/research.py NVDA
```

A few minutes later, I have:

- Live financials
- A three-scenario DCF with sensitivity analysis
- Alt-data signals from multiple sources
- Machine-learning diagnostics trained on historical data
- Monte Carlo stress tests
- Factor exposure analysis
- Position sizing and risk limits
- A Buffett/Munger-style qualitative check

Everything is saved in a structured directory, ready to review.

---

## Why I Built This

A few months ago, I was doing research the usual way:

1. Pull financials from a screener
2. Update an Excel DCF
3. Manually check EDGAR
4. Google for sentiment
5. Paste everything into a report

I timed it. One company, done properly, took about **eight hours** — without Monte Carlo simulations, factor regressions, or alternative data.

I started wondering what would happen if the entire workflow, from market-wide scan to single-stock deep dive, ran end to end without manual intervention.

After several iterations, six Python modules, and a lot of refactoring, the answer was clear: the automated version was more thorough than my manual process. Not because it's smarter, but because **it never skips steps**.

---

## The Economics Behind It

The median equity research analyst makes about $108k. A good one costs $200k–$250k. In return, you typically get:

- Coverage of ~15–20 stocks
- Models refreshed quarterly
- Finite attention and inevitable blind spots

Once you include benefits, desk space, and a $24k/year Bloomberg terminal, the real cost is higher than most people admit.

This system runs on a laptop using free public data sources, with optional APIs for energy and patent data. The leverage comes from consistency and scale.

---

## The 5-Phase Research Pipeline

The single-stock due diligence is a 5-phase pipeline where each phase feeds the next, and the orchestrator (`research.py`) runs them in sequence.

### Phase 1: Data Gathering

Pulled in parallel:

- Five years of full financial statements (line items intact)
- ROIC, free-cash-flow margins, and leverage calculated from source data
- Dynamic peer discovery by industry
- Insider transactions from cleaned Form 4 filings
- Short interest metrics
- Raw 10-K and 10-Q filings

Everything is stored cleanly by ticker.

---

### Phase 2: A DCF That Holds Up

Most retail DCFs break down in the assumptions — static growth rates, ignored WACC sensitivity, and one scenario: "the number I want to see."

This DCF modeler is different.

**Live inputs instead of hard-coded assumptions:**

```python
# Not this:
rf = 0.04  🤦

# This:
tnx = yf.Ticker('^TNX')
rf = tnx.history(period='1d')['Close'].iloc[-1] / 100
```

**Sector-aware growth decay** — most people get this wrong. A 40% growth company doesn't grow at 40% for 10 years. The system applies intelligent decay logic:

| Company Type | Growth Rate | Decay Logic |
|---|---|---|
| Hypergrowth | >30% revenue growth | Aggressive taper → ~4% terminal |
| Moderate growers | 10–30% | Gradual fade → ~3% terminal |
| Slow growers | <10% | Minimal decay → ~2.5% terminal |

This prevents the two most common DCF errors: hypergrowth companies getting absurd 10-year projections, and moderate growers flatlining at terminal rate by year 4.

**Other live inputs:**
- 10-Year Treasury yield feeds WACC
- Actual beta and effective tax rates
- Bull / Base / Bear scenarios
- Full WACC × terminal growth sensitivity grid

The output is a pitch-ready Excel model.

---

### Phase 3: Alt-Data Signal Fusion

The signal fusion engine combines five alternative data sources into a single composite alpha score.

**1. Options Flow Analysis**

Analyzes the first 3 option expirations to detect:
- **Unusual activity:** Volume 5x+ open interest = someone knows something
- **Directional bias:** Put/Call ratio below 0.7 = bullish; above 1.3 = bearish
- **Uncertainty pricing:** High implied volatility = market expects a big move

**2. Insider Intelligence**

Two layers: queries SEC EDGAR directly for Form 4 filing counts, then cross-references with yfinance for buy/sell direction and dollar values. Scoring is size-aware — mega-cap routine compensation selling vs. mid-cap cluster buys above $1M are treated very differently.

**3. Sentiment Analysis (NLP)**

Pulls the latest 15 news headlines and scores each on a bullish-to-bearish scale. Scores are dampened by 20% to avoid overreacting to noise, with a consensus bonus when bullish headlines outnumber bearish by 2:1 or more.

**4. Patent Velocity**

For tech/pharma, queries the European Patent Office (EPO) API for year-over-year patent filings. 500+ patents with 20%+ YoY growth = strong innovation moat. Falls back to R&D spending growth from yfinance when EPO keys aren't configured.

**5. Energy Exposure**

Queries the EIA.gov API for natural gas and electricity price trends. Rising energy costs = headwind for energy-intensive companies (data centers, manufacturing).

**The Composite Score**

| Signal | Weight |
|---|---|
| Options Flow | 20% |
| Insider | 20% |
| Sentiment | 15% |
| Patents (tech) | 30% |
| Energy (infra) | 15% |

A composite above **+0.4** = strong bullish signal. Below **-0.4** = bearish.

---

### Phase 4: ML-Hybrid Engine

This is where the system started catching things I used to miss.

**Random Forest Model**
Trained on 10 years of quarterly financial data, looking at six key factors: net income margin, FCF margin, revenue growth, debt/EBITDA, ROIC, and peer-relative valuation. Outputs which factors matter most *right now*.

**Isolation Forest + Z-Score Anomaly Detection**
Flags abnormal data points — revenue inflection points (growth acceleration >2 standard deviations), margin jumps, ROIC shifts. These are the quarters where something fundamental changed.

**Logistic Regression Scenario Probabilities**
Trained on 5 years of monthly VIX, 10Y yield, and SPX momentum data, the classifier outputs calibrated Bull / Base / Bear probabilities based on current macro conditions.

**Monte Carlo Stress Tests**
Full DCF recalculated 1,000 times, perturbing:
- Growth rates: ±10%
- WACC: ±1pp
- FCF margins: ±2.5pp
- Terminal growth: ±0.5pp

Output is a probability distribution of fair values with VaR at the 5th and 1st percentile.

**The Alpha Calculation**

Compares the probability-weighted fair value against current market price. If implied alpha > 10%, the system flags: `EDGE > 10% THRESHOLD`. If below -10%: `OVERVALUED > 10%`.

---

### Phase 5: Multi-Agent Validation

At real funds, the analyst presents their thesis and a risk manager, portfolio manager, and devil's advocate try to destroy it. Good ideas survive; bad ones die. This system simulates that with three specialized agents.

**Agent 1 — Risk:**
- Kelly Criterion for optimal position sizing (capped at 5% maximum)
- 99% Historical VaR
- Fama-French 3-Factor regression (Market, Size, Value)
- Stress tests: 2008 GFC analog (-55%), 2022 rate hike analog (-66%), catalyst failure (-30%)

**Agent 2 — Benchmark:**
- Constructs alpha signal from 60d momentum, RSI(14), and relative strength vs. sector ETF
- Backtests "buy when score > 0.6, hold 90 days" over 3 years out-of-sample
- Includes 10bps round-trip transaction costs
- Compares Sharpe ratio and alpha vs. buy-and-hold and sector ETF

**Agent 3 — Edge Decay:**
- Fits exponential decay curve to signal's autocorrelation function
- Calculates half-life in trading days: "How long does this edge last?"
- Simulates four regime shifts: rate hike +50bps, recession 30% probability, VIX spike, growth-to-value rotation
- Computes Edge Sustainability Score

**The Verdict**
If 2 or 3 agents say DEPLOY → position greenlighted with sizing and stop-loss. If 2 or 3 say NO-GO → idea killed. CONDITIONAL verdicts flagged for human review.

---

## The Buffett/Munger Bonus

Quantitative analysis without qualitative judgment is dangerous. The Moat Lane (`moat_lane.py`, 696 lines) runs four pillars of qualitative assessment.

**Munger Inversion:** "What would kill this investment?" Three killers are scored on probability and impact. If any killer has >30% probability AND >30% impact, the Buffett Score is hard-capped at **6.0/10**. No exceptions.

**Five Mental Models Applied:**
1. Circle of Competence
2. Margin of Safety (PEG-adjusted)
3. Lollapalooza Effect
4. Incentive-Caused Bias
5. Mr. Market

**Output:**
- Buffett Score out of 10
- Alpha Adjustment (positive or negative)
- Conviction level: HIGH / MODERATE / LOW / AVOID
- Verdict: Own Forever / Watchlist / Pass / Avoid

---

## What You Get

Running `python3 models/research.py NVDA` produces a complete research package for any public company in under 5 minutes:

- `signals_fusion.csv`
- `ml_insights.md`
- `validation_report.md`
- `moat_lane.md`
- Full Excel workbook with Dashboard, Bull/Base/Bear, Sensitivity, ML Insights, Monte Carlo, and Sensitivity Tornado sheets

---

## Try It Yourself: The 30-Minute Version

You don't need to write a single line of code to get 80% of the value. Here's how, using AI tools you already have.

**Step 1: Set up your AI workspace**

Open Claude, ChatGPT, or Gemini as your research co-pilot.

**Step 2: Pull live financials**

> *"Pull the latest financials for NVDA. I need: current price, forward P/E, revenue growth rate, free cash flow margin, ROIC (calculated from EBIT × (1 - tax rate) ÷ invested capital), and Debt/EBITDA. Also show me the 5 closest peers by industry with their current P/E and EV/EBITDA for comparison."*

**Step 3: Run a quick DCF**

> *"Now run a 3-scenario DCF for NVDA. Use the current 10-Year Treasury yield as the risk-free rate, the stock's actual beta, and a 4.2% equity risk premium. Project 10 years of free cash flow with growth decay — fast decay for hypergrowth, slow decay for mature. Give me Bull, Base, and Bear fair values, plus a 5×5 sensitivity table of WACC vs terminal growth rate."*

**Step 4: Check the alternative data**

> *"Check the alt-data signals for NVDA: (1) Options flow — is put/call ratio bullish or bearish? Any unusual volume? (2) Insider transactions: net buying or selling over the last 6 months? Dollar amounts? (3) News sentiment: summarize the last 10 headlines and give me an overall bullish/neutral/bearish read. (4) Any notable recent patent activity?"*

**Step 5: Get the final verdict**

> *"Based on everything above — the fundamentals, the DCF fair value range, the peer comparison, and the alt-data signals — give me: (1) Your probability-weighted fair value, (2) The implied upside or downside from current price, (3) The top 3 risks that could kill this thesis, and (4) A conviction level: HIGH / MODERATE / LOW / AVOID."*

Four prompts. 30 minutes. More signal on a single ticker than most retail investors generate in a week. Run this for 10 tickers on a Sunday night and you have an institutional-quality watchlist.

> **The difference between the manual version and the full system?** The full system adds Monte Carlo simulations, ML anomaly detection, multi-agent validation debates, and Buffett/Munger qualitative overlays — and runs in 2.5 minutes instead of 30.

---

## The Complete Alpha Terminal (Paid Subscribers)

### What's Included

All 7 Python modules, fully tested and production-ready:

| Module | Description |
|---|---|
| `research.py` | Orchestrator — single command runs everything |
| `data_gatherer.py` | Financial data + SEC EDGAR filings + peer comps |
| `dcf_modeler.py` | 3-scenario DCF with live WACC + sensitivity matrix |
| `signals_gatherer.py` | 5-source alt-data fusion engine |
| `ml_valuation_hybrid.py` | Random Forest + anomaly detection + Monte Carlo + logistic scenario probs |
| `alpha_validator.py` | 3-agent debate engine (Risk / Benchmark / Edge Decay) |
| `moat_lane.py` | Buffett/Munger qualitative overlay |

Plus the skills framework (4 governance modules) and the `CLAUDE.md` config file for Claude Code integration.

### Quick Deploy

1. Download the folder
2. Open in Google Antigravity or Claude Code
3. Ask Claude Code to install dependencies: *"Look at my files and install the required dependencies."*
4. Run on any ticker:

```bash
python3 models/research.py NVDA
```

5. Check your output: `signals_fusion.csv`, `ml_insights.md`, `validation_report.md`, `moat_lane.md`

### Optional API Keys (for premium signals)

- **European Patent Office API:** https://developers.epo.org/
- **U.S. Energy Information Administration (EIA) API:** https://www.eia.gov/opendata/register.php

### Files

[Download from Google Drive](https://drive.google.com/file/d/1vzvjHiL7VIjgPH9-z3tkG7k4phhEwGf-/view?usp=sharing)

---

*Build fast. Invest smart. Automate everything in between.*

*Contact: jurgis@evoaai.com | [LinkedIn](https://linkedin.com)*
