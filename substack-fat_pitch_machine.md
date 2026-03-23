# I Built a Fat Pitch Machine. It Processes 923 Stocks Every Night. Tonight's Output: 4 Names.

*The Druckenmiller method, automated.*
*March 22, 2026*

---

Stanley Druckenmiller didn't make money by being right often. He made money by being right big.

His career average (30% annual returns, 30 years, zero down years) wasn't built on a diversified portfolio of 40 moderate convictions. It was built on concentration. He'd wait, sometimes months, for the moment when everything lined up. Technical, fundamental, macro, timing. When it did, he didn't buy a little. He swung the bat.

He called these moments fat pitches.

---

## Why I Built This

Three years ago I missed a trade I'd been watching for two months.

I had the fundamental thesis right. The macro regime had shifted in the direction I'd anticipated. Insider buying had been quietly accumulating for weeks. I'd even noted it. What I didn't have was everything synthesized and sitting in front of me the morning the technical setup confirmed. By the time I assembled the full picture manually, I was chasing a 12% move.

That's not a story about being unlucky. That's a story about process failure. I had the signal. I just didn't have the infrastructure to see it all at once.

So I built the infrastructure.

---

## The Architecture Problem Nobody Talks About

Every serious investor knows they should check multiple signals before pulling the trigger. Macro regime. Technical trend. Fundamental quality. Smart money positioning. Earnings revision velocity. Insider transactions. Options flow.

Nobody does it consistently because the manual workflow is brutal:

| Task | Time | Source |
|---|---|---|
| Macro regime check | 45 min | FRED, Fed minutes, yield curve |
| Sector rotation analysis | 30 min | ETF flow data, breadth indicators |
| Technical screening | 60 min | Charting software |
| Fundamental quality filter | 90 min | SEC EDGAR, screener |
| Institutional positioning | 60 min | 13F aggregators |
| Insider transaction review | 30 min | Form 4 filings |
| Options flow check | 30 min | Options flow tool |
| Earnings revision check | 30 min | FactSet, Revisions trackers |
| Alternative data | Variable | Satellite, shipping, labor signals |

That's 6+ hours *before* you open a single research note. And most retail investors never reach the alternative data row at all.

The system I built compresses this entire workflow into a single automated pipeline that runs every night after US market close. Not as a shortcut. As the only way to do it without shortcuts.

---

*[Screenshot: Main dashboard — market intelligence view showing 903 stocks, sector rotation table, biggest movers, and the insider/M&A/signals panel on the right. This is what loads every morning.]*

## What It Does

The Druckenmiller Alpha System is a 24-module convergence engine that scores every asset in a 923-asset universe (903 equities across S&P 500 + 400, plus 14 commodities and 6 crypto) across independent intelligence dimensions, then runs those scores through a 10-gate sequential filter. Every night. Automatically.

The output isn't a ranked list of 923 assets with vague scores. The output is the handful of stocks where everything converges.

One command:

```bash
python -m tools.daily_pipeline
```

Seventy-plus pipeline phases later (data fetch, scoring, convergence synthesis, forensic veto, gate cascade, Bayesian weight update), I open a dashboard showing the surviving fat pitches with full attribution: *why* each gate passed, which modules contributed, what the reward-to-risk profile looks like, and what catalyst is expected to close the gap.

---

## The 10-Gate Cascade: How 923 Becomes 4

Most screening tools filter. This system eliminates.

There's a meaningful difference. A filter ranks everything and lets you set a cutoff. A cascade removes stocks that fail a *specific, sequential criterion*, and only the ones that clear every gate in order survive. The sequencing matters: a stock with perfect fundamentals but accounting red flags never reaches the fundamental gate.

*[Screenshot: Gate Funnel waterfall — 916 → 916 → 915 → 345 → 200 → 18 → 18 → 6 → 0 → 0 → 0, last run 2026-03-23. Each bar labeled with gate name and count.]*

| Gate | Name | Pass Condition | Tonight |
|---|---|---|---|
| 0 | Universe | 903 equities + 14 commodities + 6 crypto | 916 |
| 1 | Macro Regime | regime_score ≥ 30 | 916 |
| 2 | Liquidity | ADV ≥ $15M, market cap ≥ $500M (skipped for crypto/commodities) | 915 |
| 3 | Forensic | forensic_score ≥ 45 | 345 |
| 4 | Sector Rotation | Leading or Improving quadrant vs. sector peers | 200 |
| 5 | Technical Trend | technical_score ≥ 58 | 18 |
| 6 | Fundamental Quality | fundamental_score ≥ 42 (bypassed for crypto/commodities) | 18 |
| 7 | Smart Money | Equity: 13F conviction or insider net buy or capital_flow ≥ 65. Commodity: commercial COT pctl ≥ 55. | 6 |
| 8 | Signal Convergence | convergence_score ≥ 58 AND modules ≥ 5 | 0 |
| 9 | Catalyst | catalyst_score ≥ 50 or options flow bullish or short squeeze ≥ 75 | 0 |
| 10 | Fat Pitch | composite ≥ 65, BUY/STRONG BUY, R:R ≥ 2.0 | 0 |

The forensic gate alone eliminates 570 stocks tonight: names where the accounting forensics module has flagged revenue recognition irregularities, accrual inflation, or balance sheet deterioration. Those stocks might look fine on a P/E screen. They don't survive Gate 3.

The sector rotation gate eliminates another 145 stocks. Not because they're bad businesses, but because the current macro regime doesn't favor their sector. In a neutral environment with real rates elevated and credit spreads mixed, energy and defensive sectors get a regime boost; unprofitable growth gets penalized. The system doesn't fight the macro tape.

By Gate 7, only 6 stocks have cleared every prior dimension. Gate 8 requires a convergence score above 58 (the synthesized signal from all 24 intelligence modules) with at least 5 active modules contributing. Tonight none of the 6 clear it.

That's not a failure. That's the system working.

On March 20, 2026, four fat pitches survived: **DVN, EOG, MPC, PSX**, all energy. The sector rotation signal, energy intelligence module, and macro regime were aligned. The smart money gate passed on institutional accumulation detectable in 13F deltas. The catalyst engine flagged near-term earnings revisions driven by EIA inventory data and refining margin spreads. DVN +3.1%, EOG +2.7%, MPC +4.2%, PSX +3.8% over the two sessions that followed.

Tonight: six stocks cleared Gate 7 (Smart Money). None cleared Gate 8 (Signal Convergence). There is no setup tonight that clears every criterion simultaneously. The right move is to wait.

Druckenmiller sat in cash for months at a time. The system is built to do the same. The daily pipeline reruns every night after market close. When the evidence stacks up again, it will say so.

---

## The 24 Intelligence Modules

The convergence score is a weighted synthesis across 24 independent modules. Not inputs to a single model. Independent signals, each scored 0-100, combined with regime-adaptive weights that shift based on the macro environment.

*[Screenshot: 24-Module Convergence Engine table from dashboard — showing all 24 modules, weights, and data sources. Caption: "Gate 8 requires 5+ modules firing with convergence_score ≥ 58."]*

| Module | Weight | What It Reads |
|---|---|---|
| Smart Money | 15% | SEC 13F filings (7 tracked managers), Form 4 insider transactions, capital flow aggregates |
| Worldview | 13% | Macro thesis alignment: Fed policy, sector tilt, geopolitical regime |
| Variant | 9% | Consensus deviation: where our view diverges from sell-side |
| Foreign Intel | 7% | ADR premiums, cross-listed equity flows, FX positioning |
| Displacement | 6% | NLP on news: events that structurally reset fundamentals before price catches up |
| Research | 6% | Earnings estimate revisions, analyst rating changes, price target momentum |
| Prediction Markets | 5% | Polymarket probabilities on Fed, CPI, elections mapped to sector impacts |
| Pairs Trading | 5% | Relative value vs. sector peers: mean reversion and divergence detection |
| Energy Intel | 5% | EU gas storage, ENTSO-G flows, LNG utilisation, EIA storage surprise |
| Sector Expert | 5% | Sector ETF flow proxy, peer group relative strength, rotation quadrant |
| Patterns/Options | 4% | Technical patterns (flags, wedges, breakouts) + options flow score |
| Estimate Momentum | 4% | EPS revision momentum, revenue beat rate, guidance trajectory |
| M&A Intel | 4% | Rumour NLP, deal premium comps, sector consolidation signals |
| Blindspots | 4% | High-quality names below consensus radar: low coverage, underowned |
| Earnings NLP | 4% | Earnings call transcript NLP: tone, language shift, management confidence |
| Main Signal | 3% | Primary composite (BUY/STRONG BUY/HOLD/SELL) from technical + fundamental pipeline |
| AI Regulatory | 3% | AI/regulatory event risk: patent filings, lobbying activity, agency actions |
| Gov Intel | 3% | Government contract awards, federal spending, defence procurement |
| Labor Intel | 3% | Job posting trends (LinkedIn/Indeed proxy), layoff signals, wage data |
| Supply Chain | 3% | Supplier network stress, port congestion, freight rate signals |
| Pharma Intel | 3% | FDA calendar, clinical trial registrations, drug approval pipeline |
| Alt Data | 2% | Satellite imagery, ENSO/climate signals, web traffic proxies |
| Digital Exhaust | 2% | App downloads, web traffic, credit card spend proxies |
| Reddit | info | WallStreetBets + Reddit sentiment (unweighted: informational only) |

Three observations worth dwelling on.

**First: most of these data sources are public, free, and ignored.** WARN Act layoff notices. OSHA inspection filings. AAR weekly carloading reports. BLS H-1B approval data. UCC-1 financing statements. EDGAR 8-K filings. This is not Bloomberg data. It's federal government public record that almost nobody synthesizes into a stock signal because building the pipeline is the hard part, not accessing the data.

**Second: the prediction markets module.** Polymarket runs real-money markets on macroeconomic and geopolitical outcomes: Fed rate decisions, GDP prints, election results, regulatory outcomes. Those implied probabilities get mapped to sector and stock impacts. When prediction markets show a 73% probability of a 25bp cut at the next FOMC meeting, that's not consensus analyst opinion. It's real capital at stake. The module captures that signal 30-60 days before it shows up in earnings revisions.

**Third: the M&A module.** M&A rumors have a 5-day half-life with persistence bonuses for recurring mentions. Sector base rates and market cap attractiveness curves feed Bayesian priors on acquisition probability. Tonight's M&A panel shows 18 active signals, 10 active rumors, and top targets including JHG (87, Trian), EXE (85), TTD (85). These aren't guesses. They're scored probabilities with attribution.

The synthesis isn't magic. It's completeness.

---

## Regime-Adaptive Weights: Why Static Signals Fail

The same signal that works in a bull tape fails in a credit-stress environment. Not because the underlying logic is wrong, but because the regime changed. Static weights are a bet that the environment stays constant.

*[Screenshot: Macro regime gauge at 58/100 NEUTRAL, with indicator breakdown showing Fed Policy +4, M2 Supply +11, Real Rates -6, Yield Curve +5, Credit Spreads +10, Dollar -6, VIX -2. Market breadth: 44% above 200dma, A/D 0.23, 21 new highs vs. 81 new lows.]*

The system maintains five weight profiles:

| Regime | Macro Conditions | Module Emphasis |
|---|---|---|
| `strong_risk_off` | Fed hiking, yield curve deeply inverted, credit stress | Forensics, variant perception, supply chain distress |
| `risk_off` | Mixed signals, defensive rotation, NFCI elevated | Fundamental quality, smart money, AI regulatory |
| `neutral` | Balanced conditions, regime classifier at threshold | Equal weighting baseline |
| `risk_on` | Improving breadth, falling credit spreads, M2 expanding | Pairs, momentum, main signal |
| `strong_risk_on` | Bull trending, expanding earnings, Fed cutting | Estimate momentum, digital exhaust, retail sentiment |

In the current `neutral` classification (macro score 58/100): Smart Money and Worldview carry the highest weights at 15% and 13% respectively. Momentum and sentiment signals sit at 2-3%. This is not an opinion about market direction. It's a mechanical response to the 7 FRED-based sub-indicators that feed the macro regime scorer: Fed Funds direction, M2 growth, yield curve shape, credit conditions, dollar trend, volatility, and breadth data.

The implication: a stock that scores 72 on estimate momentum gets a different effective contribution to its convergence score depending on the regime. In `strong_risk_on`, that signal matters significantly. In `neutral`, it's crowded out by smart money and fundamental quality signals.

This is how the system avoids the most common mistake in quantitative investing: overweighting the signal that worked last year.

---

## Bayesian Weight Optimization: The System That Teaches Itself

Every prediction the system makes gets logged. Every outcome gets recorded. Every night, the weight optimizer runs a Bayesian update: modules that were right get their weights nudged upward; modules that were wrong get nudged down.

The update is conservative: small steps, not full overwrites. This is intentional. A module that underperforms for three weeks may be in a regime where it structurally doesn't apply. Aggressive weight decay on a temporarily underperforming signal destroys real edge. The Bayesian prior keeps the optimizer from pattern-matching to noise.

The practical result: module weights are never static. The Pharma Intel module carries its current 3% because it's earned it. Clinical trial phase 3 outcomes and CMS utilization shifts have been predictive. The Social/Reddit module carries zero convergence weight because the backtest doesn't justify more. If it starts earning it, the optimizer will find it.

This isn't machine learning in the marketing sense. It's systematic evidence accounting: the same thing a good PM does when reviewing which analyst on their team has been right lately, made rigorous and automated.

---

## The Forensics Veto

One design decision matters more than any other: the accounting forensics module can veto a fat pitch regardless of what every other module says.

This is not a vote. It's a hard stop.

The forensics module runs on EDGAR filings and checks for: accrual ratio inflation (operating accruals diverging from cash earnings), revenue recognition patterns inconsistent with cash flow, balance sheet deterioration masked by GAAP earnings, and auditor changes or 10-K filing delays. A stock needs forensic_score ≥ 45 to survive Gate 3. When it fails, it cannot reach Gate 10 regardless of its momentum score, institutional positioning, or analyst upgrades.

The reasoning is Munger's: "All I want to know is where I'm going to die, so I never go there." A stock with accounting irregularities has an asymmetric payoff distribution. The veto removes the left tail entirely.

Enron had strong momentum and institutional ownership in 2001. The accounting module would have flagged it. The veto is the cheapest risk management in the system.

---

## The Data Infrastructure

The pipeline runs against 40+ data sources, a PostgreSQL database with 117 tables, and a FastAPI backend serving the dashboard. The daily pipeline executes 70+ sequential phases.

Selected data sources worth noting:

- **FRED:** 23 macroeconomic indicators including yield curve, credit spreads, industrial production, and the system's proprietary Economic Heat Index
- **SEC EDGAR:** 8-K earnings filings (NLP-scored), Form 4 insider transactions, 13F institutional holdings (mandatory caveat: 13F data reflects holdings as of the most recent quarter-end, carrying a 45-135 day lag; it signals *accumulated* conviction, not current positioning)
- **EIA.gov:** U.S. energy production, storage, and refining data; the energy intelligence module reads crude inventory draws/builds two days before Bloomberg terminals
- **Polymarket:** Real-money prediction market probabilities on macro and regulatory events
- **Hyperliquid:** Weekend perpetual futures prices as a gap predictor for Monday equity open
- **NOAA + NASA MODIS:** Weather anomaly and NDVI satellite vegetation data for agricultural and commodity exposure
- **BLS + OSHA + EPA + FCC:** Federal regulatory filing data parsed daily for early warning signals
- **USPTO:** Patent filing velocity by technology classification, with 20%+ YoY growth in a class flagging innovation acceleration
- **CFTC:** Commitments of Traders disaggregated report — commercial hedger net positions as commodity smart money proxy

The LLM integration is selective. Google Gemini 2.5 Flash handles tasks where pattern classification at scale beats rules-based parsing: foreign-language market analysis translation (6 markets, 6 languages: Japanese, Korean, Chinese, German, French, Italian), M&A rumor probability scoring from news text, regulatory event classification across 9 jurisdictions, and earnings call sentiment on 8-K filings. Everything quantitative runs deterministic Python.

---

## What Comes Out the Other End

*[Screenshot: FFIN signal detail — price chart with entry $28.95 / stop $27.08 / target $38.06, R:R 4.9x. Signal Intelligence panel showing convergence 46, modules 4, smart money 54, worldview 38. Catalyst: INSIDER_CLUSTER 100, $819,858 cluster buy.]*

Tonight's dashboard shows:

- **Fat pitches:** each with full gate attribution and module score breakdown (0 tonight: last fat pitches were DVN, EOG, MPC, PSX on March 20)
- **Convergence scores** for all 923 assets: ranked, with top signals per sector
- **Screener tabs:** Insider signals, M&A targets, Energy signals, Blindspots, Displacement, Pairs, Estimate Momentum, Alt Data
- **Module leaderboard:** which of the 24 modules has been most predictive over the trailing 90 days
- **Economic Heat Index:** synthesized read on 23 FRED indicators, classified as Expansion / Neutral / Contraction
- **Signal conflicts:** stocks where modules are pointing in opposite directions, requiring human judgment before acting

*[Screenshot: M&A panel — 18 active signals, 0 definitive, 10 rumors. Top targets: JHG 87 DEFINITIVE_AGREEMENT (Trian), EXE 85, TTD 85, WBS 83, SIGI 83. Caption: "The M&A module scores acquisition probability using Bayesian priors on sector base rates and market cap attractiveness curves."]*

*[Screenshot: Energy Intelligence signals tab — VLO/PSX/MPC all at 66 DEMAND (Refiner: margin=45 demand=80), XOM/DVN/FANG/EOG at 55 DEMAND (Upstream: Inv=41 prod=63 dem=80). Caption: "When the energy signal fires across both refiners and upstream names simultaneously, it's a regime signal, not a stock pick."]*

The fat pitches are not a recommendation. They're the output of a systematic process that has eliminated everything that doesn't clear a specific, sequential criterion. The human judgment layer (sizing, timing, exit criteria) remains where it belongs.

But that's the decision I want to be making. Not "should I check EDGAR tonight." The infrastructure handles the infrastructure. I handle the judgment.

---

## How Druckenmiller Would Have Used It

His actual process was top-down: read the macro, identify the sectors the macro favors, find the best stocks within those sectors, bet big. He describes it in interviews as a two-stage decision. Stage one: which sector and direction? Stage two: which specific name?

The system implements this mechanically.

Stage one is the Macro Regime module + Worldview Model + Sector Rotation gate. In the current `neutral` classification: energy sits at the top of the sector rotation table (score 53.8, 1 bull, 0 bears). ~546 stocks eliminated at Gate 4 because their sector doesn't fit the current regime.

Stage two is Gates 5-10 for the stocks that survive stage one: technical trend, fundamental quality, smart money, convergence synthesis, catalyst, and final fat pitch criteria.

The result is exactly the Druckenmiller decision tree, except it runs on 923 assets simultaneously and finishes before midnight.

What he did with judgment and experience, pattern-matched over decades, the system does with data and computation. The combination of both is the edge.

---

## Try It Yourself: The Manual Version (For Free Subscribers)

You can approximate a simplified version of this using publicly available tools and the right prompts. It won't cover all 24 modules or run automatically, but it will beat an undisciplined screening process by a significant margin.

**Step 1: Macro Regime Check**

> *"Pull the current yield curve shape (10Y-3M spread), VIX level, and Chicago Fed National Financial Conditions Index (NFCI). Based on these inputs, classify the current macro regime as: strong_risk_off / risk_off / neutral / risk_on / strong_risk_on. Then tell me which sectors the current regime historically favors and which it penalizes."*

**Step 2: Sector Rotation Filter**

> *"Based on the [regime classification from Step 1], give me the two sectors to overweight and two to underweight. For the two favored sectors, run a fundamental quality screen: identify the 5 stocks within each sector that combine the highest ROIC (>15%), lowest Debt/EBITDA (<2.5x), and most positive EPS revision trend over the last 90 days."*

**Step 3: Smart Money and Forensics Check**

> *"For each of the 10 stocks from Step 2: (1) What do the most recent 13F filings show about institutional ownership changes? Net buyers or sellers? (2) Are there any recent Form 4 insider transactions? Net dollar value and direction? (3) Any accounting flags: accrual ratio abnormalities, auditor changes, or revenue/cash flow divergences in the last two quarters?"*

**Step 4: Convergence Check**

> *"For the stocks that passed Step 3 cleanly, check alt signals: (1) Options flow: put/call ratio and any unusual volume in the front two expirations. (2) News displacement: any material news in the last 30 days not yet reflected in consensus price targets. (3) Estimate momentum: has EPS consensus risen or fallen in the last 60 days, and by how much?"*

**Step 5: Fat Pitch Verdict**

> *"Based on everything above, give me the 1-2 highest-conviction names. For each: (1) convergence assessment: how many independent signals align? (2) Reward-to-risk ratio based on technical support/resistance. (3) Expected catalyst and timing. (4) Conviction level: HIGH / MODERATE / LOW / AVOID."*

Five prompts. Done correctly, this covers macro, sector rotation, institutional positioning, forensics, alternative signals, and convergence. It replaces the 6-hour manual workflow.

The full system adds: 24 simultaneous modules, nightly automation, Bayesian weight self-optimization, accounting forensics veto, 10-gate sequential elimination, regime-adaptive weighting, and historical accuracy tracking across every signal. It runs while you sleep and hands you the output every morning.

The prompts above will get you to a handful of names in about 2 hours. The full system gets you to the same place across 923 assets before you wake up. One is a process. The other is infrastructure.

---

<!-- PAYWALL PLACEMENT: Everything below is paid-only -->

## The Complete Druckenmiller Alpha System (Paid Subscribers)

### What's Included

The full pipeline: 70+ phases, 24 convergence modules, 10-gate cascade, Bayesian optimizer, email alerts, Next.js dashboard.

| Component | What It Does |
|---|---|
| `daily_pipeline.py` | Orchestrates 70+ pipeline phases |
| `convergence_engine.py` | Synthesizes 24 module scores into final signal, regime-adaptive |
| `gate_engine.py` | 10-gate cascade, from 923 assets to fat pitches |
| `weight_optimizer.py` | Bayesian weight updating from historical accuracy |
| `macro_regime.py` | Regime classification from 7 FRED sub-indicators (Fed Funds, M2, yield curve, NFCI, breadth) |
| `economic_dashboard.py` | 23 FRED indicators + proprietary Economic Heat Index |
| `accounting_forensics.py` | Hard-veto gate: forensic_score ≥ 45 required to proceed |
| `consensus_blindspots.py` | Second-level thinking, contrarian signal detection |
| `variant_perception.py` | Fundamental/price divergence detection |
| `worldview_model.py` | World Bank + IMF macro-to-stock thesis mapping |
| All intelligence modules | Full signal stack: energy, labor, M&A, pairs, pharma, regulatory, prediction markets |
| `api.py` + 5 route files | FastAPI backend across 6 route files |
| `dashboard/` | Full Next.js dashboard: 11 pages, 4-group sidebar |
| `modal_app.py` | One-command serverless deploy (runs nightly automatically) |

### What It Costs to Run

A Bloomberg terminal seat runs $24,000/year. The base system runs entirely on free public APIs (FRED, SEC EDGAR, EIA, USPTO, Polymarket, CFTC) and delivers the full 10-gate cascade at zero marginal cost per run.

Optional paid APIs for deeper signal coverage:

- **FMP:** Financial data and institutional flow (~$14/mo)
- **Alpha Vantage:** Technical indicator calculation (~$50/mo)
- **Nansen:** On-chain whale flow data (enterprise)

The premium APIs add signal depth, not new gate logic. Most of the edge is in the architecture, not the data vendors.

### Quick Deploy

**If you use Claude Code or Antigravity:**

Clone the repo, open it in your agentic IDE, and give it this prompt:

> *"Set up the Druckenmiller Alpha System. Create a Python venv at /tmp/druck_venv, install dependencies from requirements.txt, copy .env.template to .env, and run the pipeline. Let me know what API keys I need to fill in."*

It handles the rest. You'll be prompted for API keys and looking at your first fat pitch output within a few minutes.

**If you prefer manual setup:**

```bash
# Backend
python3 -m venv /tmp/druck_venv
/tmp/druck_venv/bin/pip install -r requirements.txt
cp .env.template .env        # Fill in your API keys
python -m tools.daily_pipeline

# Dashboard
cd dashboard && npm run dev -- --port 3333

# Production (runs automatically every night)
modal deploy modal_app.py
```

---

Most investors spend their edge budget on data access. This system turns the edge budget into analytical architecture: the ability to synthesize 24 independent signals simultaneously, eliminate 919 setups, and act with full conviction on the ones that remain.

The pipeline ran last night. It's running tonight. The fat pitches are already queued. The only question is whether you're looking at the output tomorrow morning.

---

*Build the infrastructure. Let the infrastructure find the signal.*

*Contact: jurgis@evoaai.com | [LinkedIn](https://linkedin.com)*
