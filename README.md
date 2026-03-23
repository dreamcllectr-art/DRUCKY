# Druckenmiller Alpha System

A multi-factor equity convergence engine that synthesizes 29 independent intelligence modules into actionable stock signals, filtered through a 10-gate cascade to surface only the highest-conviction fat pitches. Built for systematic alpha generation with institutional-grade rigor.

**Quality score: 9.55/10** (verified via 4-iteration dogfood eval — correctness, robustness, security, completeness, UX)

## What It Does

The system runs a daily pipeline after US market close that:

1. **Fetches** fresh data — prices, fundamentals, macro indicators, news, filings, alternative data, prediction markets, regulatory events
2. **Scores** every stock in a 903-stock universe (S&P 500 + 400) across 29 independent analytical lenses
3. **Gates** stocks through a 10-gate cascade — from 916 → 4 fat pitches — eliminating weak setups at each stage
4. **Converges** remaining scores into a single conviction signal per stock, weighted by the current macro regime
5. **Optimizes** module weights using Bayesian updating based on historical accuracy
6. **Alerts** you to high-conviction opportunities via email

The result is a dashboard showing which stocks have the most evidence stacked in their favor — and which are flashing warning signs.

## Architecture

```
WAT Framework (Workflows > Agents > Tools)

tools/              Python scripts — deterministic execution layer
  daily_pipeline.py      Orchestrates all 35+ pipeline phases
  convergence_engine.py  Synthesizes 29 module scores into final signal
  gate_engine.py         10-gate cascade (Universe → Fat Pitches)
  weight_optimizer.py    Bayesian weight updating from historical accuracy
  api.py                 FastAPI backend — core routes
  api_intelligence.py    Intelligence module routes (AI regulatory, execs, predictions)
  api_market_modules.py  Market module routes (worldview, energy, patterns, pairs)
  api_data_modules.py    Data module routes (earnings NLP, gov/labor/pharma intel)
  api_analytics.py       Analytics routes (performance, track record, weights)
  api_gates.py           10-gate cascade routes (10 endpoints)
                         Total: FastAPI backend across 6 route files
  db.py                  PostgreSQL schema (117 tables)
  config.py              Core thresholds and API keys
  config_modules.py      Convergence weights, regime profiles, per-module settings

dashboard/           Next.js frontend (tab-based, 4-group sidebar nav)
modal_app.py         Serverless deployment (3 cron jobs)
workflows/           Markdown SOPs
.tmp/                Intermediate data (disposable)
```

## The 29 Convergence Modules

| # | Module | Weight | What It Does |
|---|--------|--------|--------------|
| 1 | **Smart Money (13F)** | 10% | Tracks institutional position changes from SEC filings |
| 2 | **Worldview Model** | 10% | Macro thesis mapping to individual stocks (World Bank, IMF) |
| 3 | **Variant Perception** | 7% | Finds stocks where the market disagrees with fundamentals |
| 4 | **Earnings NLP** | 5% | VADER + financial lexicon sentiment on 8-K filings from SEC EDGAR |
| 5 | **Foreign Intelligence** | 5% | Translated foreign-language market analysis (6 markets, 4 languages) |
| 6 | **Research Sources** | 5% | Aggregated analyst research signals (18 sources incl. GS, MS, JPM) |
| 7 | **News Displacement** | 5% | Material news not yet reflected in price |
| 8 | **Sector Experts** | 4% | Sector rotation and consolidation thesis |
| 9 | **Pairs Trading** | 4% | Cointegrated pairs, mean-reversion and runner detection |
| 10 | **Energy Intelligence** | 4% | Supply-demand balance, EIA data, energy sector signals |
| 11 | **Prediction Markets** | 4% | Polymarket data mapped to sector/stock impacts |
| 12 | **Government Intelligence** | 4% | WARN, OSHA, EPA, FCC, lobbying filings — regulatory risk scores |
| 13 | **Labor Intelligence** | 4% | H-1B velocity, job postings, employee sentiment |
| 14 | **M&A Intelligence** | 3% | Acquisition target profiling + rumor tracking (5-day half-life) |
| 15 | **Pattern & Options** | 3% | Chart patterns + unusual options activity |
| 16 | **Estimate Momentum** | 3% | EPS/revenue revision velocity, earnings surprise streaks |
| 17 | **Consensus Blindspots** | 3% | Howard Marks second-level thinking — contrarian signals, fat pitches |
| 18 | **Supply Chain Intel** | 3% | Rail/shipping/trucking freight proxy for economic activity |
| 19 | **Digital Exhaust** | 3% | App store rankings, GitHub velocity, pricing and domain signals |
| 20 | **Pharma Intelligence** | 3% | Clinical trial phases, CMS utilization, Rx trends (healthcare only) |
| 21 | **Alternative Data** | 3% | Satellite (NDVI, ENSO), shipping, weather signals |
| 22 | **AI Regulatory** | 2% | Global AI regulation tracker across 9 jurisdictions |
| 23 | **Main Signal** | 2% | Base convergence signal from technical + fundamental scoring |
| 24 | **Reddit / Social** | 1% | Social sentiment and momentum signals |
| 25 | **AAR Rail Intel** | 2% | American Association of Railroads carloading data + FRED rail proxies |
| 26 | **Ship Tracking** | 2% | BDI, port congestion, LNG shipping volumes |
| 27 | **Patent Intel** | 2% | USPTO filing velocity by technology class |
| 28 | **UCC Filings** | 2% | Secured debt distress signals from financing statements |
| 29 | **Board Interlocks** | 2% | DEF 14A governance patterns, interlocking board memberships |

**Regime-adaptive weights**: The system maintains 5 weight profiles (strong_risk_off through strong_risk_on) that shift module importance based on the current macro regime. A Bayesian weight optimizer updates weights daily based on historical prediction accuracy.

**Supporting modules** (not in convergence weights but feed the system):
- Insider Trading — boosts/penalizes smart money scores based on SEC Form 4 filings
- Economic Dashboard — 23 FRED indicators + Macro Heat Index
- Hyperliquid Gap Monitor — weekend perp prices predict Monday equity gaps
- Accounting Forensics — red flags that veto convergence signals
- Devil's Advocate — contrarian risk analysis on high-conviction picks
- Base Rate Tracker — historical accuracy tracking
- Paper Trader — simulated portfolio performance
- Weight Optimizer — Bayesian weight updating from track record
- Short Interest Intel — short squeeze and crowded short detection
- Retail Sentiment — Stocktwits + social retail flow signals
- On-Chain Intel — Nansen + Etherscan on-chain activity signals
- Analyst Intel — price target revisions, rating changes
- Options Flow Intel — unusual options activity and positioning
- Capital Flows Intel — fund flow and sector rotation signals
- Catalyst Engine — event-driven catalyst scoring

## 10-Gate Cascade

Stocks must survive 10 sequential gates to be declared a fat pitch. Each gate eliminates based on a specific criterion:

| Gate | Name | Criterion | Typical Output |
|------|------|-----------|----------------|
| 0 | Universe | All tracked stocks | 916 |
| 1 | Macro Regime | regime_fit_score >= -20 | ~916 |
| 2 | Liquidity | ADV >= $5M, mktcap >= $500M | ~916 |
| 3 | Forensic | No accounting red flags | ~878 |
| 4 | Sector Rotation | Sector in favorable regime | ~343 |
| 5 | Technical Trend | Price trend confirmation | ~148 |
| 6 | Fundamental | Quality fundamentals | ~66 |
| 7 | Smart Money | Institutional buying evidence | ~33 |
| 8 | Convergence | convergence_score >= 52 | ~9 |
| 9 | Catalyst | Near-term catalyst present | ~4 |
| 10 | Fat Pitch | composite >= 60, R:R >= 1.5 | ~4 |

The gate funnel is accessible via the **Investment Funnel** dashboard page (`/v2/gates`) as a 3-panel waterfall view.

## Dashboard

The dashboard uses a 4-group sidebar with 11 linked pages.

| Group | Page | Route | What You See |
|-------|------|-------|--------------|
| **Market** | Terminal | `/v2/terminal` | Full-screen stock terminal — signal details, insider activity, AI exec analysis |
| | Macro | `/macro` | Macro regime dashboard, FRED indicators, Heat Index |
| **Signals** | Conviction | `/` | System status, top signals, fat pitches, regime indicator |
| | Investment Funnel | `/v2/gates` | 10-gate waterfall — 916 stocks → fat pitches |
| | Screener | `/signals` | Insider, Blindspots, Displacement, Pairs, Est. Momentum, M&A, Alt Data |
| **Portfolio** | Holdings | `/v2/conviction` | Portfolio positions and conviction scores |
| | Alpha Stack | `/v2/alpha` | IC backtesting, module accuracy, alpha synthesis |
| | Performance | `/performance` | Module leaderboard, accuracy tracking, weight evolution |
| **Tools** | Risk | `/v2/risk` | Signal conflicts, stress test scenarios, thesis builder |
| | Journal | `/v2/journal` | Trade journal and notes |

Additional pages accessible via direct route:
- `/asset/[symbol]` — Asset detail (Overview, Convergence, Trade Setup, Regulatory tabs)
- `/intelligence` — AI regulatory tracker, exec signals, prediction markets
- `/energy` — EIA supply/demand, production, flows, global energy
- `/patterns` — Chart patterns, options flow, cycles, rotation
- `/discover` — AI-powered stock discovery and trading ideas
- `/reports` — Generated intelligence reports
- `/portfolio` — Paper trading performance

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, PostgreSQL (117 tables)
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS, Lightweight Charts
- **Deployment**: Modal (serverless) — API endpoint + 3 scheduled cron jobs
- **Data Sources**: FMP, FRED, SEC EDGAR, Finnhub, Polymarket, Hyperliquid, NOAA, NASA MODIS, World Bank, IMF, Reddit, Serper, yfinance, Federal Register, EU AI Act sources, ClinicalTrials.gov, BLS H-1B, OSHA/EPA/FCC public APIs, App Store/GitHub, AAR rail data, BDI shipping, USPTO patents, UCC filings, Alpha Vantage, FINRA short interest, EPO patents, Nansen, Etherscan, USDA, Stocktwits, CoinGecko
- **LLM**: Google Gemini 2.5 Flash (news classification, M&A rumor scoring, foreign intel translation, regulatory event classification, prediction market mapping, earnings call sentiment)

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- API keys (see `.env.template`)

### Local Development

```bash
# Backend (use /tmp venv — avoid iCloud-evicted venv)
python3 -m venv /tmp/druck_venv
/tmp/druck_venv/bin/pip install -r requirements.txt
cp .env.template .env  # Add your API keys
/tmp/druck_venv/bin/python -u -m tools.daily_pipeline  # Run the full pipeline

# Dashboard
cd dashboard
npm install
npm run dev -- --port 3333
# Opens at http://localhost:3333

# API server (136+ endpoints across 6 route files)
/tmp/druck_venv/bin/uvicorn tools.api:app --reload
# Opens at http://localhost:8000
```

### Deploy to Modal

```bash
modal setup              # One-time login
modal deploy modal_app.py  # Deploy everything
```

This deploys:
- **API endpoint** — serves all API routes
- **Daily pipeline** — runs Mon-Fri at 11 PM UTC (after US market close)
- **HL weekend monitor** — hourly on Sat/Sun (Hyperliquid gap tracking)
- **HL Monday backfill** — Monday 4 PM UTC (gap accuracy verification)

## Pipeline Phases

The daily pipeline runs 70+ phases in sequence:

1. **Phase 1 (FETCH)** — Stock universe, prices, macro data, fundamentals, news, EIA energy data
2. **Phase 1.5 (ALT DATA)** — Alternative data (satellite NDVI, ENSO) + energy intelligence
3. **Phase 2 (SCORE)** — Market breadth, macro regime, technical scoring, fundamental scoring
4. **Phase 2.05 (ECON)** — 23 FRED economic indicators + Heat Index
5. **Phase 2.1 (TA GATE)** — Technical pre-screening gate
6. **Phase 2.15 (PATTERNS)** — Chart pattern detection + options intelligence
7. **Phase 2.5 (ALPHA EDGE)** — Accounting forensics, variant perception
8. **Phase 2.55 (ESTIMATE MOMENTUM)** — EPS/revenue revision velocity, surprise streaks
9. **Phase 2.6 (AI REGULATORY)** — Global AI regulation monitoring across 9 jurisdictions
10. **Phase 2.7 (EXTENDED)** — 13F filings, insider trading, research, Reddit, earnings NLP, foreign intel, news displacement, sector experts, pairs trading, M&A, energy intel, gov/labor/pharma intel, supply chain, digital exhaust
11. **Phase 2.75 (NEW INTEL)** — Short interest, retail sentiment, on-chain, analyst intel, options flow, capital flows, catalyst engine
12. **Phase 2.8 (CONSENSUS BLINDSPOTS)** — Second-level thinking, fat pitch detection
13. **Phase 3 (SIGNALS)** — Signal generation, position sizing, prediction markets
14. **Phase 3.5 (WORLDVIEW)** — Macro-to-stock thesis mapping (World Bank, IMF)
15. **Phase 3.55 (WEIGHT OPTIMIZER)** — Bayesian weight updating from track record
16. **Phase 3.9 (CONVERGENCE)** — Master synthesis across all 29 modules
17. **Phase 3.95 (DEVIL'S ADVOCATE)** — Contrarian risk analysis
18. **Phase 3.97 (BASE RATE)** — Historical accuracy tracking
19. **Phase 3.98 (PAPER TRADER)** — Simulated portfolio updates
20. **Phase 3.99 (GATES)** — 10-gate cascade, fat pitch selection
21. **Phase 4 (ALERTS)** — Check triggers, send email notifications

Each step has error handling — the pipeline continues on individual step failures and sends a failure summary email.

## Database

PostgreSQL. 117 tables including:
- `stock_universe` — 903 stocks tracked (S&P 500 + 400)
- `convergence_signals` — final synthesized scores (all 29 module scores)
- Individual module tables (`smart_money_scores`, `pair_signals`, `ma_signals`, `estimate_momentum_signals`, `consensus_blindspot_signals`, `regulatory_signals`, `earnings_nlp_scores`, `gov_intel_scores`, `labor_intel_scores`, `supply_chain_scores`, `digital_exhaust_scores`, `pharma_intel_scores`, `short_interest_scores`, `retail_sentiment_scores`, `onchain_intel_scores`, `analyst_intel_scores`, `options_flow_intel_scores`, `capital_flows_scores`, `catalyst_scores`, etc.)
- `economic_dashboard` + `economic_heat_index` — macro indicators
- `hl_price_snapshots` + `hl_gap_signals` — Hyperliquid data
- `weight_history` + `weight_optimizer_log` — adaptive weight tracking
- `module_performance` + `signal_outcomes` — accuracy tracking
- `gate_results` — 10-gate cascade per-stock results

Database runs locally via PostgreSQL and on a Modal persistent volume in production.

## Key Design Decisions

- **10-gate cascade** — Systematic funnel from 916 stocks to ~4 fat pitches; each gate has a specific, measurable criterion
- **Regime-adaptive weights** — Module importance shifts with the macro environment, not static
- **Bayesian weight optimization** — Weights update daily based on historical prediction accuracy
- **Forensic veto** — Accounting red flags can block otherwise high-conviction signals
- **Second-level thinking** — Consensus Blindspots module detects crowded trades and contrarian opportunities
- **Bayesian priors** — M&A scoring uses sector base rates and market cap attractiveness curves
- **Rumor decay** — M&A rumors have a 5-day half-life with persistence bonuses for recurring mentions
- **Calibrated thresholds** — Scoring thresholds are set from actual data distribution, not arbitrary cutoffs
- **Graceful degradation** — Slow APIs (World Bank, ORNL) timeout gracefully and score 0 rather than crash the pipeline
- **Global regulatory coverage** — 9 jurisdictions, 15 regulatory bodies, jurisdiction-weighted scoring
