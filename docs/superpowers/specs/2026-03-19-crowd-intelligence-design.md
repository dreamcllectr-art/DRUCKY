# Crowd Intelligence System — Design Spec
**Date:** 2026-03-19
**Status:** Approved
**Target:** 0.0001% institutional-grade crowd positioning intelligence

---

## 1. Purpose

Build a universal crowd intelligence system that answers the single most important positioning question in markets:

> **Where is the crowd — retail, institutional, and smart money — positioned right now, and where do they diverge?**

The alpha lives in the divergence. When retail is euphoric and smart money is quietly exiting, that is a distribution signal. When retail is fearful and insiders are cluster-buying, that is the highest-IC setup in markets. This system detects both, daily, using only free data sources.

Designed for: hedge fund PMs, quant analysts, and sophisticated retail investors who want an institutional-grade positioning read without a Bloomberg terminal.

---

## 2. Deliverables

### 2a. Universal Claude Skill
```
~/.claude/plugins/crowd-intelligence/
├── SKILL.md
├── crowd_retail.py
├── crowd_institutional.py
├── crowd_smart.py
└── crowd_engine.py
```
Invocable from any project via `/crowd-intelligence`. Self-contained. All Python scripts travel with the skill. Auto-detects environment (pipeline vs standalone).

### 2b. Druckenmiller Pipeline Integration
```
~/druckenmiller/tools/
├── crowd_retail.py          (symlink → skill folder)
├── crowd_institutional.py   (symlink → skill folder)
├── crowd_smart.py           (symlink → skill folder)
└── crowd_engine.py          (symlink → skill folder)

~/druckenmiller/
└── crowd_report.py          (standalone CLI)
```
Runs daily in `daily_pipeline.py`. Writes to `crowd_intelligence` SQLite table. Served via `/api/crowd-intelligence` FastAPI endpoint. Displayed in new dashboard tab.

---

## 3. Data Sources — 12 Free Sources Across 3 Layers

### Layer 1: Retail Crowding (contrarian/risk signals)
| Source | Signal | Cadence | Half-Life | IC |
|--------|--------|---------|-----------|-----|
| Reddit PRAW (WSB, r/investing, r/stocks) | Ticker mention velocity + sentiment delta | Daily | 2 days | -0.02 |
| CNN Fear & Greed Index (public API) | Market risk appetite 0-100 | Daily | 1 day | -0.04 |
| AAII Sentiment Survey (scraped) | Bulls% - Bears% spread | Weekly | 7 days | -0.03 |
| Google Trends (pytrends) | Search interest surge = retail FOMO | Daily | 3 days | -0.02 |

**Critical framing:** Retail signals are CONTRARIAN. High retail enthusiasm = crowding risk = negative alpha adjustment. This layer never generates a direct buy signal — it flags what is dangerously crowded or deeply unloved.

### Layer 2: Institutional Positioning (trend/flow signals)
| Source | Signal | Cadence | Half-Life | IC |
|--------|--------|---------|-----------|-----|
| ICI.org fund flows (free CSV) | Weekly ETF + mutual fund flows by sector | Weekly | 7 days | 0.07 |
| CFTC COT Report (free CSV) | Commercials vs non-commercials net futures positioning | Weekly | 14 days | 0.07 |
| FINRA ATS dark pool prints (free) | Block trades off-exchange = institutional accumulation | Daily | 5 days | 0.05 |
| SEC EDGAR 13F + FMP API | Quarterly hedge fund holdings changes | Quarterly | 180 days | 0.06 |
| FINRA short interest (free) | Short interest + days-to-cover | Bi-monthly | 14 days | 0.05 |

**Note on COT:** Commercial traders (producers, hedgers) are the most informed participants in futures markets. Their net positioning is the single most reliable institutional signal available for free. Non-commercial (speculator) positioning is used as a contrarian crowding gauge.

### Layer 3: Smart Money (leading/alpha signals)
| Source | Signal | Cadence | Half-Life | IC |
|--------|--------|---------|-----------|-----|
| OpenInsider (free scrape) | Cluster insider buying — 3+ insiders same ticker same month | Daily | 90 days | 0.08 |
| SEC EDGAR Form 4 (free) | Director/officer purchases — highest-conviction insider signal | Daily | 90 days | 0.08 |
| Finnhub free tier | Options: 25-delta skew + unusual OI surge vs 20-day avg | Daily | 5 days | 0.06 |
| Polymarket public API | Macro event probability shifts | Live | 3 days | 0.04 |

**Note on insider signals:** Lakonishok & Lee (2001) showed corporate insider buying predicts 6-month excess returns of 4-6%. Cluster buying (3+ insiders, same ticker, same month) is the strongest variant — it implies coordinated conviction, not routine compensation.

---

## 4. Scoring Engine

### 4a. Signal Normalization
Each raw signal is z-score normalized against its own 252-day rolling history:
```
normalized = (value - rolling_mean_252) / rolling_std_252
normalized = clip(normalized, -3, 3) / 3  → range [-1, 1]
normalized = (normalized + 1) / 2          → range [0, 1]
```
This converts heterogeneous signals (dollar flows, percentages, mention counts) into a common scale with historical context. A score of 0.8 means "80th percentile of the past year."

### 4b. Exponential Decay Weighting
Each signal is discounted by its age relative to its empirical half-life:
```python
decay_weight = 0.5 ** (signal_age_days / half_life_days)
```
A COT signal 14 days old carries half the weight of a fresh one. A 13F signal 90 days old still carries ~70% weight (180-day half-life). This prevents stale signals from dominating.

### 4c. IC-Weighted Layer Combination
Within each layer, signals are combined weighted by their estimated Information Coefficient:
```python
layer_score = sum(signal.ic * decay_weight * normalized_value
                  for signal in layer_signals)
              / sum(signal.ic * decay_weight for signal in layer_signals)
```
Higher-IC signals earn proportionally more weight. Retail signals enter as their inverse (1 - normalized) because they are contrarian.

### 4d. Regime-Conditional Layer Weighting
The three layer scores are combined using weights that adapt to macro regime (sourced from existing FRED macro_regime module):

```python
REGIME_WEIGHTS = {
    "risk_on":     {"smart": 0.35, "institutional": 0.45, "retail_penalty": 0.20},
    "risk_off":    {"smart": 0.55, "institutional": 0.35, "retail_penalty": 0.10},
    "transition":  {"smart": 0.45, "institutional": 0.35, "retail_penalty": 0.20},
    "stagflation": {"smart": 0.50, "institutional": 0.40, "retail_penalty": 0.10},
}
```

**Theory:** In risk-off regimes, smart money (insiders, options flow) is most predictive because informed actors respond first to deteriorating conditions. In risk-on, institutional trend-following is reliable. The retail penalty is always present — retail crowding always represents risk to a position.

### 4e. Final Conviction Score
```python
raw = (weights.smart * smart_score
     + weights.institutional * institutional_score
     - weights.retail_penalty * retail_crowding_score)

alignment = 1 - (std([smart_score, institutional_score, (1-retail_score)]) / 50)

conviction = clip(raw * alignment, 0, 100)
```
Alignment multiplier: when all three layers agree, the score is amplified. When they diverge, it is discounted — uncertainty is priced in.

### 4f. Price/Volume Confirmation Gate
Every signal must pass before surfacing in the report:

```python
# Bullish signals require:
# - Price above 50-day MA (trend intact)
# - 5-day avg volume > 20-day avg volume (expanding participation)
# - RSI(14) < 72 (not overbought)

# Bearish/distribution signals require:
# - Price below 20-day MA
# - Volume expansion on down days

# Gate failure: signal is logged but excluded from report output
# Purpose: eliminate false positives, add technical confirmation layer
```

---

## 5. Divergence Signal Taxonomy

Six signal types derived from Wyckoff market cycle theory + modern microstructure research:

| Signal | Conditions | Theory | Expected Edge |
|--------|-----------|--------|---------------|
| `DISTRIBUTION` | Retail >70, Institutional <40, Smart <35 | Wyckoff Phase C/D — informed sellers distributing into retail demand | Short/reduce within 2-4 weeks |
| `CONTRARIAN_BUY` | Retail <30, Institutional >60, Smart >65 | Lakonishok (1994) — institutional contrarian buying near capitulation lows | Long, 30-90 day horizon |
| `HIDDEN_GEM` | Retail <20, 3+ insider buys, unusual call OI | Maximum information asymmetry — insiders + options = highest-IC setup | Long, 60-180 day horizon |
| `SHORT_SQUEEZE` | Short days-to-cover >10, Institutional >55, Retail fear present | Forced covering + institutional support = asymmetric upside | Long, 5-15 day horizon |
| `CROWDED_FADE` | Retail >75, dark pool selling, ICI outflow | Smart money distributing into ETF inflows — near-term reversal risk | Reduce/short, 1-3 week horizon |
| `STEALTH_ACCUM` | ICI inflow, dark pool buying, Retail <40 | Institutional accumulation before retail discovery — earliest-stage signal | Long, 90-180 day horizon |

---

## 6. Report Output Structure

```
═══════════════════════════════════════════════════════════════════
  CROWD INTELLIGENCE REPORT
  Date: 2026-03-19  |  Regime: Risk-On  |  Universe: 903 stocks
  Sources: Reddit / ICI / CFTC / FINRA / SEC / Finnhub / Polymarket
═══════════════════════════════════════════════════════════════════

[1] MACRO POSITIONING MAP
    Fear & Greed:    67  (Greed)          [1-week change: +8]
    AAII Bulls:      52% Bears: 24%        [Spread: +28 — mild complacency]
    COT Aggregate:   Net Long (S&P futs)   [Speculators: 73rd pctile long]
    ICI Flows:       +$4.2B equity inflow  [3rd consecutive week]
    Margin Debt:     Expanding             [YoY: +12%]
    MACRO SIGNAL:    MILD CROWDED — monitor for distribution

[2] SECTOR CROWDING MAP
    CROWDED LONG (fade risk):   Technology [84], Financials [71], Discretionary [68]
    NEUTRAL:                    Healthcare [52], Industrials [49], Energy [44]
    UNDEROWNED (opportunity):   Utilities [23], Materials [31], Staples [33]
    CROWDED SHORT (squeeze risk): Real Estate [18]

[3] TOP 10 DIVERGENCE ALERTS  (highest alpha — confirmation gate passed)
    ┌─────────┬────────┬────────┬────────┬──────────────────┬─────────────────┐
    │ Ticker  │ Retail │  Inst  │ Smart  │ Signal           │ Horizon         │
    ├─────────┼────────┼────────┼────────┼──────────────────┼─────────────────┤
    │ NVDA    │   19   │   78   │   84   │ CONTRARIAN_BUY ★ │ 60-180d         │
    │ AAPL    │   82   │   31   │   28   │ DISTRIBUTION     │ Reduce 2-4w     │
    │ XOM     │   21   │   71   │   76   │ HIDDEN_GEM ★★    │ 90-180d         │
    │ GME     │   91   │   22   │   18   │ CROWDED_FADE     │ Fade 1-3w       │
    │ MS      │   33   │   69   │   71   │ STEALTH_ACCUM ★  │ 90-180d         │
    └─────────┴────────┴────────┴────────┴──────────────────┴─────────────────┘

[4] TOP 10 CONVICTION SCORES  (all layers aligned)
    MSFT    91  BULLISH  — Inst:88, Smart:87, Retail:low (contrarian support)
    JPM     87  BULLISH  — Inst:84, Smart:81, ICI inflow 4w consecutive
    NEE     84  BULLISH  — Underowned sector + insider cluster + dark pool bid

[5] RISK FLAGS
    ► Tech sector COT speculators at 89th pctile — historically precedes 5-8% correction
    ► AAII bulls 3-week rising streak — watch for mean reversion
    ► 3 DISTRIBUTION signals in mega-caps — reduce concentration risk
```

---

## 7. File Architecture

### SKILL.md — Universal Invocation
```
Invocation: /crowd-intelligence [tickers] [--sector X] [--mode divergence-only|conviction|full]
                                           [--regime override] [--export json|csv|markdown]

Behavior:
1. Detect environment (pipeline DB available? → use cache. Standalone? → fetch fresh)
2. Run crowd_engine.py with provided args
3. Display formatted report
4. If --export: write to crowd_intelligence_YYYY-MM-DD.{format}
```

### crowd_retail.py
- fetch_reddit_sentiment(tickers) → PRAW API, WSB + r/investing + r/stocks
- fetch_fear_greed() → CNN public endpoint
- fetch_aaii_sentiment() → AAII.com scrape
- fetch_google_trends(tickers) → pytrends

### crowd_institutional.py
- fetch_ici_flows() → ici.org free CSV download
- fetch_cot_report() → CFTC public FTP CSV
- fetch_finra_dark_pool(tickers) → FINRA ATS public data
- fetch_13f_flows(tickers) → SEC EDGAR + FMP free tier
- fetch_short_interest(tickers) → FINRA short interest public data

### crowd_smart.py
- fetch_insider_clusters(tickers) → OpenInsider scrape + SEC Form 4 EDGAR
- fetch_options_skew(tickers) → Finnhub free tier (put/call + OI surge)
- fetch_polymarket_signals() → Polymarket public API

### crowd_engine.py
- normalize_signals(signals) → z-score, clip, rescale
- apply_decay(signals) → exponential half-life weighting
- score_layer(signals) → IC-weighted combination
- detect_regime() → calls macro_regime module or defaults to "risk_on"
- compute_conviction(retail, institutional, smart, regime) → final score
- run_divergence_detector(scores) → classify signal type
- run_confirmation_gate(ticker, signal_type) → yfinance technical filter
- generate_report(universe, mode) → formatted terminal output
- write_to_db(results) → SQLite crowd_intelligence table (if pipeline)

---

## 8. Dependencies

All free, no paid API required for core functionality:
```
praw>=7.7          # Reddit
pytrends>=4.9      # Google Trends
yfinance>=0.2      # Prices + technical gate
requests>=2.31     # All HTTP scraping
pandas>=2.0        # Data processing
numpy>=1.26        # Numerical operations
beautifulsoup4     # AAII + OpenInsider scraping
```
Optional enhancements (already available in this project):
```
finnhub-python     # Options skew (free tier key in .env)
fmp-python         # 13F data (free tier key in .env)
fredapi            # Margin debt (free key in .env)
```

---

## 9. Integration Points

### daily_pipeline.py
```python
from tools.crowd_engine import run_crowd_intelligence
# Add to pipeline run order after macro_regime (regime needed for weighting)
run_crowd_intelligence(universe=STOCK_UNIVERSE, write_db=True)
```

### FastAPI endpoint
```
GET /api/crowd-intelligence
GET /api/crowd-intelligence/{ticker}
GET /api/crowd-intelligence/sector/{sector}
GET /api/crowd-intelligence/divergences
```

### Dashboard tab
New tab in existing sidebar: "Crowd" — shows macro map, sector crowding heatmap, divergence alerts table, conviction leaderboard.

---

## 10. Quality Standards

- Every signal has a published academic or practitioner citation
- Every weight has an empirical or theoretical justification
- Graceful degradation: if any source fails, system runs on remaining sources and flags missing data
- No signal is surfaced without passing the price/volume confirmation gate
- Report clearly labels data freshness (age of each signal)
- Retail signals are always framed as crowding/risk signals, never directional buy signals

---

## 11. Skill Invocation Examples

```bash
# Full report on entire universe
/crowd-intelligence

# Single ticker deep dive
/crowd-intelligence NVDA

# Divergence signals only (highest alpha)
/crowd-intelligence --mode divergence-only

# Sector positioning map
/crowd-intelligence --sector technology

# Export for quant pipeline
/crowd-intelligence --export json > crowd_2026-03-19.json

# Works in any project — no Druckenmiller DB needed
cd ~/some-other-project && /crowd-intelligence AAPL MSFT GOOGL
```
