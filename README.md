# Druckenmiller Alpha System

A multi-factor equity convergence engine that synthesizes 14 independent intelligence modules into actionable stock signals. Built for systematic alpha generation with institutional-grade rigor.

## What It Does

The system runs a daily pipeline after US market close that:

1. **Fetches** fresh data — prices, fundamentals, macro indicators, news, filings, alternative data
2. **Scores** every stock in the universe across 14 independent analytical lenses
3. **Converges** those scores into a single conviction signal per stock, weighted by the current macro regime
4. **Alerts** you to high-conviction opportunities via email

The result is a dashboard showing which stocks have the most evidence stacked in their favor — and which are flashing warning signs.

## Architecture

```
WAT Framework (Workflows > Agents > Tools)

tools/              49 Python scripts — deterministic execution layer
  daily_pipeline.py    Orchestrates all 35+ pipeline phases
  convergence_engine.py  Synthesizes 14 module scores into final signal
  api.py               FastAPI backend (72 endpoints)
  db.py                SQLite schema (60+ tables)
  config.py            All thresholds, weights, and regime profiles

dashboard/           Next.js frontend (18 pages)
modal_app.py         Serverless deployment (3 cron jobs)
workflows/           Markdown SOPs
.tmp/                Intermediate data (disposable)
```

## The 14 Convergence Modules

| # | Module | Weight | What It Does |
|---|--------|--------|--------------|
| 1 | **Smart Money (13F)** | 17% | Tracks institutional position changes from SEC filings |
| 2 | **Technical Scoring** | 12% | Price action, momentum, volume analysis |
| 3 | **Fundamental Scoring** | 12% | Valuation, growth, quality metrics |
| 4 | **Signal Generator** | 10% | Composite buy/sell signal from technicals + fundamentals |
| 5 | **Variant Perception** | 7% | Finds stocks where the market disagrees with fundamentals |
| 6 | **Sector Experts** | 7% | Sector rotation and consolidation thesis |
| 7 | **Pairs Trading** | 5% | Cointegrated pairs, mean-reversion and runner detection |
| 8 | **Prediction Markets** | 5% | Polymarket data mapped to sector/stock impacts |
| 9 | **Alternative Data** | 5% | Satellite (NDVI, ENSO), shipping, weather signals |
| 10 | **M&A Intelligence** | 4% | Acquisition target profiling + rumor tracking |
| 11 | **Pattern & Options** | 4% | Chart patterns + unusual options activity |
| 12 | **News Displacement** | 4% | Material news not yet reflected in price |
| 13 | **Foreign Intelligence** | 4% | Translated foreign-language market analysis |
| 14 | **Research Sources** | 4% | Aggregated analyst research signals |

**Bonus modules** (not in convergence weights but feed the system):
- Insider Trading — boosts/penalizes smart money scores based on SEC Form 4 filings
- Economic Dashboard — 23 FRED indicators + Macro Heat Index
- Worldview Model — macro thesis mapping (including World Bank/IMF global data)
- Hyperliquid Gap Monitor — weekend perp prices predict Monday equity gaps
- Accounting Forensics — red flags that veto convergence signals
- Devil's Advocate — contrarian risk analysis on high-conviction picks
- Base Rate Tracker — historical accuracy tracking
- Paper Trader — simulated portfolio performance

**Regime-adaptive weights**: The system maintains 5 weight profiles (strong_risk_off through strong_risk_on) that shift module importance based on the current macro regime. In risk-off environments, defensive modules get more weight; in risk-on, momentum and M&A get amplified.

## Dashboard Pages

| Page | What You See |
|------|-------------|
| **Home** | System status, top signals, regime indicator |
| **Screener** | Filter and sort the full stock universe |
| **Synthesis** | Convergence scores with module-level breakdown |
| **Economic** | 23 FRED indicators across 4 tabs (Leading, Coincident, Lagging, Liquidity) |
| **Pairs** | Cointegrated pairs, runners, mean-reversion opportunities |
| **Insider** | Unusual activity, cluster buys, insider+smart money convergence |
| **Energy** | Supply-demand balance, EIA data, energy sector intelligence |
| **M&A** | Acquisition targets, rumor tracker, deal pipeline |
| **Patterns** | Chart patterns + options flow intelligence |
| **Displacement** | News events not yet priced in |
| **Alt Data** | Satellite, weather, and alternative data signals |
| **Worldview** | Macro thesis mapping to individual stocks |
| **Predictions** | Prediction market signals and sector impacts |
| **Hyperliquid** | Weekend gap predictions, cross-deployer spreads, accuracy tracking |
| **Watchlist** | Personal watchlist with alerts |
| **Portfolio** | Paper trading performance |
| **Thesis** | Investment thesis builder and checklist |
| **Asset Detail** | Deep dive on any individual symbol |

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLite (WAL mode)
- **Frontend**: Next.js, TypeScript, Tailwind CSS, Lightweight Charts
- **Deployment**: Modal (serverless) — API endpoint + 3 scheduled cron jobs
- **Data Sources**: FMP, FRED, SEC EDGAR, Finnhub, Polymarket, Hyperliquid, NOAA, NASA MODIS, World Bank, IMF, Reddit, Serper, yfinance
- **LLM**: Google Gemini (news classification, M&A rumor scoring, foreign intel translation)

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- API keys (see `.env.example`)

### Local Development

```bash
# Backend
python -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env  # Add your API keys
venv/bin/python -m tools.daily_pipeline  # Run the full pipeline

# Dashboard
cd dashboard
npm install
npm run dev  # http://localhost:3000

# API server
venv/bin/uvicorn tools.api:app --reload  # http://localhost:8000
```

### Deploy to Modal

```bash
modal setup          # One-time login
modal deploy modal_app.py  # Deploy everything
```

This deploys:
- **API endpoint** — serves all 72 routes
- **Daily pipeline** — runs Mon-Fri at 11 PM UTC (after US market close)
- **HL weekend monitor** — hourly on Sat/Sun (Hyperliquid gap tracking)
- **HL Monday backfill** — Monday 4 PM UTC (gap accuracy verification)

## Pipeline Phases

The daily pipeline runs ~35 steps in sequence:

1. **Phase 1 (FETCH)** — Stock universe, prices, macro data, fundamentals, news, EIA energy data
2. **Phase 1.5 (ALT DATA)** — Alternative data + energy intelligence data
3. **Phase 2 (SCORE)** — Market breadth, macro regime, technical scoring, fundamental scoring
4. **Phase 2.05 (ECON)** — 23 FRED economic indicators + Heat Index
5. **Phase 2.1 (TA GATE)** — Technical pre-screening gate
6. **Phase 2.15 (PATTERNS)** — Chart pattern detection + options intelligence
7. **Phase 2.5 (ALPHA EDGE)** — Accounting forensics, variant perception
8. **Phase 2.7 (EXTENDED)** — 13F filings, insider trading, research, Reddit, earnings transcripts, founder letters, foreign intel, news displacement, sector experts, pairs trading, M&A, energy intel
9. **Phase 3 (SIGNALS)** — Signal generation, position sizing
10. **Phase 3.5 (WORLDVIEW)** — Macro-to-stock thesis mapping
11. **Phase 3.9 (CONVERGENCE)** — Master synthesis across all 14 modules
12. **Phase 3.95 (DEVIL'S ADVOCATE)** — Contrarian risk analysis
13. **Phase 3.97 (BASE RATE)** — Historical accuracy tracking
14. **Phase 3.98 (PAPER TRADER)** — Simulated portfolio updates
15. **Phase 4 (ALERTS)** — Check triggers, send email notifications

Each step has error handling — the pipeline continues on individual step failures and sends a failure summary email.

## Database

SQLite with WAL mode. 60+ tables including:
- `stock_universe` — ~940 stocks tracked
- `convergence_signals` — final synthesized scores (21 columns for all module scores)
- Individual module tables (`smart_money_scores`, `pair_signals`, `ma_signals`, etc.)
- `economic_dashboard` + `economic_heat_index` — macro indicators
- `hl_price_snapshots` + `hl_gap_signals` — Hyperliquid data

Database lives at `.tmp/druckenmiller.db` locally (~27 MB) and on a Modal persistent volume in production.

## Key Design Decisions

- **Regime-adaptive weights** — Module importance shifts with the macro environment, not static
- **Forensic veto** — Accounting red flags can block otherwise high-conviction signals
- **Bayesian priors** — M&A scoring uses sector base rates and market cap attractiveness curves
- **Rumor decay** — M&A rumors have a 5-day half-life with persistence bonuses for recurring mentions
- **Calibrated thresholds** — Scoring thresholds are set from actual data distribution, not arbitrary cutoffs
- **Graceful degradation** — Slow APIs (World Bank, ORNL) timeout gracefully and score 0 rather than crash the pipeline
