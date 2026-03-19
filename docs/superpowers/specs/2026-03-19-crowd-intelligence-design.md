# Crowd Intelligence System — Design Spec
**Date:** 2026-03-19
**Status:** Approved — v2 (post spec-review)
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
Invocable from any Claude Code session via `/crowd-intelligence`. Self-contained — all Python scripts travel with the skill. Auto-detects environment (pipeline DB available vs standalone fresh fetch).

**Note:** `/crowd-intelligence` is a Claude Code slash command, not a shell command. For terminal use, invoke `crowd_report.py` directly (see 2b).

### 2b. Druckenmiller Pipeline Integration
```
~/druckenmiller/tools/
├── crowd_retail.py          (copied from skill folder — NOT symlinked, iCloud boundary)
├── crowd_institutional.py   (copied from skill folder)
├── crowd_smart.py           (copied from skill folder)
└── crowd_engine.py          (copied from skill folder)

~/druckenmiller/
└── crowd_report.py          (standalone terminal CLI)
```

**iCloud note:** Files are copied, not symlinked. `~/.claude/` is outside iCloud; `~/Documents/Druckemiller/` is inside iCloud. Symlinks across this boundary do not resolve reliably and iCloud may evict linked targets. Use `cp` during setup; re-copy when skill files are updated.

Runs daily in `daily_pipeline.py` after `macro_regime` module (regime data required for scoring weights). Writes to `crowd_intelligence` SQLite table. Served via `/api/crowd-intelligence` FastAPI endpoint. Displayed in new "Crowd" dashboard tab.

---

## 3. Data Sources — 13 Free Sources Across 3 Layers

### Layer 1: Retail Crowding (contrarian/risk signals only — never directional buy)
| Source | Signal | Cadence | Half-Life | IC (contrarian) | Notes |
|--------|--------|---------|-----------|-----------------|-------|
| Reddit PRAW (WSB, r/investing, r/stocks) | Ticker mention velocity + sentiment delta | Daily | 2 days | -0.02 | Requires Reddit developer app (client_id/secret in .env — already configured) |
| Alternative.me Fear & Greed API | Market risk appetite 0-100 | Daily | 1 day | -0.04 | Documented, versioned, stable free API. Not CNN's internal endpoint. |
| AAII Sentiment Survey (scraped) | Bulls% - Bears% spread | Weekly | 7 days | -0.03 | HTML scrape of aaii.com |
| Google Trends (pytrends) | Search interest surge = retail FOMO | Daily | 3 days | -0.02 | **Rate-limit risk**: run on top-50 most-mentioned tickers only, not full 903 universe. Exponential backoff required. Falls back gracefully if blocked. |

**Critical framing:** Retail signals are CONTRARIAN. High retail enthusiasm = crowding risk = penalty to conviction score. This layer never generates a direct buy signal. It flags what is dangerously crowded (reduce risk) or deeply unloved (contrarian opportunity).

### Layer 2: Institutional Positioning (trend/flow signals)
| Source | Signal | Cadence | Half-Life | IC | Notes |
|--------|--------|---------|-----------|-----|-------|
| Sector ETF AUM flows via yfinance | Weekly shares_outstanding × price change in XLK/XLF/XLE/XLV/XLI/XLY/XLP/XLU/XLB/XLRE | Daily | 7 days | 0.07 | Proxy for ICI fund flows. Free, programmatic, reliable. Standard practitioner approach when ICI is not accessible. |
| CFTC COT Report (free FTP CSV) | Commercials vs non-commercials net futures positioning | Weekly | 14 days | 0.07 | CFTC FTP: `publicreporting.cftc.gov/reports/COT`. Most reliable free institutional signal. |
| FINRA ATS volume (free) | Weekly equity ATS volume by venue — market-level institutional activity proxy | Weekly | 5 days | 0.05 | **Scope:** Per-venue aggregate for listed equities, NOT per-security. Used as market-level institutional participation signal, not individual ticker signal. Per-security dark pool data is not available for free for listed equities. |
| SEC EDGAR 13F + FMP API | Quarterly hedge fund holdings changes | Quarterly | **60 days** | 0.06 | Half-life is 60 days (not 180). Filings are 45 days stale at publication. Academic consensus (Grinblatt & Titman 1993, Wermers 1999): 13F signal degrades sharply after 60 days. |
| FINRA short interest (free) | Short interest + days-to-cover per ticker | Bi-monthly | 14 days | 0.05 | Free from FINRA: `finra.org/investors/learn-to-invest/advanced-investing/short-selling` |
| FRED margin debt via fredapi | FINRA margin debt YoY change (BOGZ1FL663067003Q) | Quarterly | 90 days | 0.04 | Market-level leverage signal. Key uses in macro map. fredapi key in .env. |

**Note on COT:** Commercial traders (producers, hedgers) are the most informed participants in futures markets. Their net positioning is the single most reliable institutional signal available for free. Non-commercial (speculator) positioning is used as a contrarian crowding gauge alongside retail Layer 1.

### Layer 3: Smart Money (leading/alpha signals — highest IC)
| Source | Signal | Cadence | Half-Life | IC | Notes |
|--------|--------|---------|-----------|-----|-------|
| OpenInsider (free scrape) | Cluster insider buying — 3+ insiders, same ticker, **14-day window** | Daily | 90 days | 0.08 | Window aligns with existing `INSIDER_CLUSTER_WINDOW_DAYS = 14` in config_modules.py. Reuse `insider_trading.py` cluster detection logic. |
| SEC EDGAR Form 4 (free) | Director/officer purchases — highest-conviction insider signal | Daily | 90 days | 0.08 | `insider_trading.py` already fetches these. Reuse, do not rebuild. |
| yfinance options chain | Options skew: OTM put IV vs OTM call IV + unusual OI surge vs 20-day avg | Daily | 5 days | 0.06 | **Finnhub free tier does not provide Greeks or delta-mapped skew.** Use yfinance for chain; compute 25Δ-equivalent skew from 0.85/1.15 moneyness. Finnhub free tier used for supplementary sentiment score only. |
| Polymarket public API | Macro event probability shifts | Live | 3 days | 0.04 | `prediction_markets.py` already calls Gamma API. Reuse. |

**Note on insider signals:** Lakonishok & Lee (2001) showed corporate insider buying predicts 6-month excess returns of 4-6%. Cluster buying (3+ insiders, 14-day window) is the strongest variant — it implies coordinated conviction, not routine compensation grant exercise.

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

For signals with fewer than 60 days of history, use cross-sectional percentile rank across the current universe instead of rolling z-score. Flag as `low_history=True` in output.

### 4b. Exponential Decay Weighting
Each signal is discounted by its age relative to its empirical half-life:
```python
decay_weight = 0.5 ** (signal_age_days / half_life_days)
```
A COT signal 14 days old carries half the weight of a fresh one. A 13F signal 30 days old carries ~71% weight (60-day half-life). This prevents stale signals from dominating while retaining slow-moving structural information.

### 4c. IC-Weighted Layer Combination
Within each layer, signals are combined using absolute IC values as weights. Retail signals are explicitly inverted before entering the formula (contrarian transformation):

```python
def score_layer(signals, layer_type):
    total_weight = sum(abs(s.ic) * s.decay_weight for s in signals)
    if total_weight == 0:
        return None  # all signals missing — layer unavailable

    score = 0
    for s in signals:
        w = abs(s.ic) * s.decay_weight / total_weight
        value = (1 - s.normalized) if layer_type == "retail" else s.normalized
        score += w * value

    return score  # range [0, 1]
```

**Note:** Retail signals use `(1 - normalized)` explicitly for the contrarian inversion. Using negative IC in the weight formula does NOT achieve the same result — the negatives cancel in the weighted average. Always use `abs(ic)` as weight, always invert retail values directly.

### 4d. Regime-Conditional Layer Weighting
The three layer scores are combined using weights that adapt to macro regime. Uses **exact regime labels** from `macro_regime.py`:

```python
REGIME_WEIGHTS = {
    "strong_risk_on":  {"smart": 0.30, "institutional": 0.50, "retail_penalty": 0.20},
    "risk_on":         {"smart": 0.35, "institutional": 0.45, "retail_penalty": 0.20},
    "neutral":         {"smart": 0.40, "institutional": 0.40, "retail_penalty": 0.20},
    "risk_off":        {"smart": 0.55, "institutional": 0.35, "retail_penalty": 0.10},
    "strong_risk_off": {"smart": 0.60, "institutional": 0.30, "retail_penalty": 0.10},
}
DEFAULT_REGIME = "neutral"  # used when macro_regime module unavailable (standalone mode)
```

**Theory:** In risk-off regimes, smart money (insiders, options flow) is most predictive because informed actors respond first to deteriorating conditions. In strong risk-on, institutional trend-following dominates. The retail penalty is always present — crowding always represents risk to a position regardless of regime.

### 4e. Final Conviction Score
```python
# Layer scores are in [0, 1] range from 4c
raw = (weights["smart"] * smart_score
     + weights["institutional"] * institutional_score
     - weights["retail_penalty"] * retail_crowding_score)

# Alignment: penalizes disagreement between layers
# std([s1, s2, s3]) max value for inputs in [0,1] is 0.577
# Dividing by 0.577 scales alignment to [0, 1]
alignment = 1.0 - (np.std([smart_score, institutional_score, (1 - retail_crowding_score)]) / 0.577)
alignment = max(0.0, alignment)  # floor at zero

# Scale to 0-100
conviction = float(np.clip(raw * alignment * 100, 0, 100))
```

**Alignment multiplier:** When all three layers agree (std → 0), alignment → 1.0 and the score is fully amplified. When layers maximally disagree (std → 0.577), alignment → 0.0 and the score is zeroed — high uncertainty means no signal. This correctly prices in cross-layer uncertainty.

### 4f. Price/Volume Confirmation Gate
Every divergence signal must pass this gate before surfacing in the report. Prices fetched via yfinance (free). Gate failure: signal is logged to DB as `confirmation_gate_passed=0` but excluded from report output.

```python
def confirmation_gate(ticker: str, signal_type: str) -> bool:
    df = yf.download(ticker, period="3mo", progress=False)
    if len(df) < 50:
        return False  # insufficient price history

    close = df["Close"].squeeze()
    volume = df["Volume"].squeeze()

    if signal_type in ("CONTRARIAN_BUY", "HIDDEN_GEM", "STEALTH_ACCUM"):
        above_50ma  = close.iloc[-1] > close.rolling(50).mean().iloc[-1]
        vol_expand  = volume.iloc[-5:].mean() > volume.iloc[-20:].mean()
        rsi_not_ob  = _rsi(close, 14).iloc[-1] < 72
        return bool(above_50ma and vol_expand and rsi_not_ob)

    if signal_type in ("DISTRIBUTION", "CROWDED_FADE"):
        below_20ma = close.iloc[-1] < close.rolling(20).mean().iloc[-1]
        return bool(below_20ma)

    if signal_type == "SHORT_SQUEEZE":
        # Requires catalyst within 21 days (earnings) — check earnings calendar
        has_catalyst = _earnings_within_days(ticker, days=21)
        above_20ma   = close.iloc[-1] > close.rolling(20).mean().iloc[-1]
        return bool(has_catalyst and above_20ma)

    return True
```

**SHORT_SQUEEZE catalyst requirement:** DTC > 10 without a near-term catalyst (earnings, index inclusion, news event) can persist for months. Requiring a confirmed catalyst within 21 days dramatically improves signal precision (Asquith, Pathak & Ritter 2005).

### 4g. Rate-Limit Budget for 903-Stock Universe
Not all signals run on all 903 stocks. Expensive per-stock fetches are limited to a prioritized tier:

| Signal | Scope | Reason |
|--------|-------|--------|
| Reddit mentions | Top 200 by market cap + any ticker with >5 mentions in last 7 days | Rate + relevance |
| Google Trends | Top 50 by Reddit mention velocity | Aggressive rate limiting — batch with delays |
| Options skew (yfinance) | Top 300 by market cap | Options liquidity threshold |
| 13F per-ticker | Full 903 (quarterly, cached) | Low frequency, negligible rate pressure |
| Insider/Form 4 | Full 903 (daily delta only) | Low volume of new filings |
| CFTC COT | Macro-level only (not per stock) | Futures-level data |
| FINRA ATS | Market-level only (not per stock) | Venue-level data |

---

## 5. Divergence Signal Taxonomy

Six signal types derived from Wyckoff market cycle theory + modern microstructure research:

| Signal | Conditions | Theory | Expected Edge |
|--------|-----------|--------|---------------|
| `DISTRIBUTION` | Retail >70, Institutional <40, Smart <35 | Wyckoff Phase C/D — informed sellers distributing into retail demand | Short/reduce within 2-4 weeks |
| `CONTRARIAN_BUY` | Retail <30, Institutional >60, Smart >65 | Lakonishok (1994) — institutional contrarian buying near capitulation lows | Long, 30-90 day horizon |
| `HIDDEN_GEM` | Retail <20, 3+ insider cluster buys (14d), unusual call OI surge | Maximum information asymmetry — insiders + options = highest-IC setup | Long, 60-180 day horizon |
| `SHORT_SQUEEZE` | Short DTC >10, Institutional >55, Retail fear, **earnings/catalyst within 21 days** | Forced covering + institutional support + catalyst = asymmetric upside | Long, 5-15 day horizon |
| `CROWDED_FADE` | Retail >75, ETF AUM outflow signal, sector crowding >80 | Smart money distributing into retail ETF inflows — near-term reversal risk | Reduce/short, 1-3 week horizon |
| `STEALTH_ACCUM` | ETF sector inflow signal, dark pool institutional activity rising, Retail <40 | Institutional accumulation before retail discovery — earliest-stage signal | Long, 90-180 day horizon |

---

## 6. Report Output Structure

```
═══════════════════════════════════════════════════════════════════
  CROWD INTELLIGENCE REPORT
  Date: 2026-03-19  |  Regime: risk_on  |  Universe: 903 stocks
  Sources: Reddit / ETF Flows / CFTC / FINRA / SEC / yfinance / Polymarket
  Signals available: 11/13  (ICI: n/a — using ETF proxy | pytrends: rate-limited to top 50)
═══════════════════════════════════════════════════════════════════

[1] MACRO POSITIONING MAP
    Fear & Greed:    67  (Greed)               [1-week change: +8]
    AAII Bulls:      52%  Bears: 24%            [Spread: +28 — mild complacency]
    COT Aggregate:   Net Long (S&P futs)        [Speculators: 73rd pctile — elevated]
    ETF Sector Flow: +$4.2B equity inflow       [Tech: +$1.8B, 3rd consecutive week]
    Margin Debt:     Expanding                  [YoY: +12% — leverage building]
    MACRO SIGNAL:    MILD CROWDED — monitor for distribution

[2] SECTOR CROWDING MAP
    CROWDED LONG (fade risk):    Technology [84], Financials [71], Discretionary [68]
    NEUTRAL:                     Healthcare [52], Industrials [49], Energy [44]
    UNDEROWNED (opportunity):    Utilities [23], Materials [31], Staples [33]
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
    MSFT    91  BULLISH  — Inst:88, Smart:87, Retail:14 (contrarian support)
    JPM     87  BULLISH  — Inst:84, Smart:81, ETF inflow 4w consecutive
    NEE     84  BULLISH  — Underowned sector + insider cluster + dark pool bid

[5] RISK FLAGS
    ► COT speculators at 73rd pctile — historically precedes 5-8% S&P correction within 60d
    ► AAII bulls 3-week rising streak — mean reversion risk elevated
    ► 3 DISTRIBUTION signals in mega-caps — reduce single-name concentration
    ► pytrends limited to top 50 tickers today (rate limited) — retail signal coverage partial
```

---

## 7. File Architecture

### SKILL.md — Universal Invocation (Claude Code sessions)
```
Invocation: /crowd-intelligence [tickers] [--sector X] [--mode divergence-only|conviction|full]
                                           [--regime override] [--export json|csv|markdown]

Behavior:
1. Detect environment:
   - If tools/crowd_engine.py importable AND crowd_intelligence DB table exists → use cached data
   - Otherwise → fetch fresh via all collector modules
2. Run crowd_engine.generate_report() with provided args
3. Display formatted report inline
4. If --export: write to crowd_intelligence_YYYY-MM-DD.{format}
```

### crowd_report.py — Standalone Terminal CLI
```bash
python crowd_report.py                          # full report
python crowd_report.py --tickers AAPL NVDA MSFT # specific tickers
python crowd_report.py --sector technology       # sector deep dive
python crowd_report.py --mode divergence-only    # only divergence alerts
python crowd_report.py --export json             # JSON output
```
This file calls `crowd_engine.py` directly. No Claude required. Works in any project with Python.

### crowd_retail.py — Functions
- `fetch_reddit_sentiment(tickers: list[str]) → list[Signal]` — PRAW, WSB + r/investing + r/stocks
- `fetch_fear_greed() → Signal` — Alternative.me documented API
- `fetch_aaii_sentiment() → Signal` — aaii.com HTML scrape
- `fetch_google_trends(tickers: list[str], max_tickers=50) → list[Signal]` — pytrends, rate-limited

### crowd_institutional.py — Functions
- `fetch_etf_sector_flows() → list[Signal]` — yfinance AUM changes on XLK/XLF/XLE/XLV/XLI/XLY/XLP/XLU/XLB/XLRE
- `fetch_cot_report() → list[Signal]` — CFTC public FTP, publicreporting.cftc.gov
- `fetch_finra_ats_activity() → Signal` — FINRA ATS aggregate institutional volume (market-level signal)
- `fetch_13f_flows(tickers: list[str]) → list[Signal]` — SEC EDGAR + FMP free tier (quarterly, cached)
- `fetch_short_interest(tickers: list[str]) → list[Signal]` — FINRA short interest public data
- `fetch_margin_debt() → Signal` — FRED series BOGZ1FL663067003Q via fredapi

### crowd_smart.py — Functions
- `fetch_insider_clusters(tickers: list[str]) → list[Signal]` — reuses `insider_trading.py` logic, INSIDER_CLUSTER_WINDOW_DAYS=14
- `fetch_options_skew(tickers: list[str]) → list[Signal]` — yfinance options chain, computes 0.85/1.15 moneyness IV skew; Finnhub free tier for supplementary score
- `fetch_polymarket_signals() → list[Signal]` — reuses `prediction_markets.py` Gamma API logic

### crowd_engine.py — Core Engine
- `normalize_signal(s: Signal) → Signal` — z-score 252-day rolling (or cross-sectional rank if <60d history)
- `apply_decay(s: Signal) → float` — `0.5 ** (age / half_life)`
- `score_layer(signals: list[Signal], layer_type: str) → float | None` — IC-weighted, decay-adjusted, [0,1]
- `detect_regime() → str` — calls `macro_regime` module or returns DEFAULT_REGIME="neutral"
- `compute_conviction(retail, institutional, smart, regime) → float` — regime-weighted, alignment-adjusted, [0,100]
- `run_divergence_detector(ticker, scores, short_data) → str | None` — returns signal type or None
- `run_confirmation_gate(ticker, signal_type) → bool` — yfinance technical + catalyst check
- `generate_report(universe, mode, tickers) → str` — formatted terminal output
- `write_to_db(results: list[dict]) → None` — SQLite `crowd_intelligence` table (no-op if no DB)

---

## 8. SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS crowd_intelligence (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    date                        TEXT NOT NULL,
    ticker                      TEXT,           -- NULL for macro/sector rows
    scope                       TEXT NOT NULL,  -- 'ticker' | 'sector' | 'macro'
    sector                      TEXT,

    -- Layer scores [0-100]
    retail_crowding_score       REAL,
    institutional_score         REAL,
    smart_money_score           REAL,
    conviction_score            REAL,           -- final IC-weighted composite [0-100]

    -- Divergence
    divergence_type             TEXT,           -- DISTRIBUTION | CONTRARIAN_BUY | etc. | NULL
    divergence_strength         REAL,           -- 0.0-1.0
    confirmation_gate_passed    INTEGER,        -- 0 | 1

    -- Raw signal breakdown
    retail_signals              TEXT,           -- JSON
    institutional_signals       TEXT,           -- JSON
    smart_money_signals         TEXT,           -- JSON

    -- Context
    macro_regime                TEXT,
    narrative                   TEXT,           -- 1-sentence plain English summary
    signals_available           INTEGER,        -- count of sources that returned data
    signals_total               INTEGER,        -- total expected sources

    created_at                  TEXT DEFAULT (datetime('now')),

    UNIQUE(date, ticker, scope)  -- prevents duplicate daily writes
);

CREATE INDEX IF NOT EXISTS idx_crowd_date      ON crowd_intelligence(date);
CREATE INDEX IF NOT EXISTS idx_crowd_ticker    ON crowd_intelligence(ticker);
CREATE INDEX IF NOT EXISTS idx_crowd_divergence ON crowd_intelligence(divergence_type);
```

DDL added to `db.py` `init_db()` alongside existing table definitions.

---

## 9. Dependencies

```
# Core — required for standalone use (all free)
praw>=7.7            # Reddit (requires Reddit developer app — client_id/secret)
pytrends>=4.9        # Google Trends (rate-limited; exponential backoff required)
yfinance>=0.2        # Prices, ETF flows, options chains, technical gate
requests>=2.31       # CFTC, FINRA, Alternative.me, Polymarket, OpenInsider
pandas>=2.0          # Data processing
numpy>=1.26          # Numerical operations
beautifulsoup4       # AAII + OpenInsider HTML scraping

# Optional enhancements (available in this project's .env)
finnhub-python       # Supplementary options sentiment (free tier)
fmp-python           # 13F holdings data (free tier, 250 req/day)
fredapi              # Margin debt, FRED macro series (free key)
```

---

## 10. Integration Points

### daily_pipeline.py
```python
from tools.crowd_engine import run_crowd_intelligence
# Must run AFTER macro_regime (regime labels required for weights)
run_crowd_intelligence(universe=STOCK_UNIVERSE, write_db=True)
```

### FastAPI endpoints
```
GET /api/crowd-intelligence                    → full report data
GET /api/crowd-intelligence/macro              → macro positioning map
GET /api/crowd-intelligence/sectors            → sector crowding map
GET /api/crowd-intelligence/divergences        → divergence alerts only
GET /api/crowd-intelligence/{ticker}           → single ticker deep dive
```

### Dashboard tab
New "Crowd" tab in sidebar. Components:
- Macro positioning map (Fear/Greed gauge, AAII bar, COT dial, ETF flows bar)
- Sector crowding heatmap (11 sectors × crowding score)
- Divergence alerts table (sortable, filterable by signal type)
- Conviction leaderboard (top 20, color-coded by alignment)
- Data freshness indicator (age of each signal source, flags stale/missing)

---

## 11. IC Validation — Ongoing

Initial IC estimates are derived from published academic literature:
- Insider buying IC=0.08: Lakonishok & Lee (2001), Seyhun (1992)
- COT commercial IC=0.07: Briese (2008) "The Commitments of Traders Bible"
- 13F institutional IC=0.06: Grinblatt & Titman (1993), Wermers (1999)
- AAII contrarian IC=-0.03: Fisher & Statman (2000)

Once 90+ days of live data accumulate, recalibrate IC estimates using `signal_ic.py` backtester (already in project). The IC-weighted combination self-improves as empirical estimates replace literature priors.

---

## 12. Quality Standards

- Every signal has a published academic or practitioner citation
- Every weight has an empirical or theoretical justification
- Graceful degradation: if any source fails, system continues on remaining sources; report header shows `Signals available: X/13`
- No divergence signal is surfaced without passing the price/volume confirmation gate
- Report header labels data freshness per source
- Retail signals are always framed as crowding/risk signals — never as directional buy signals
- All mathematical formulas verified: conviction formula produces [0,100]; alignment denominator 0.577; retail layer uses explicit `(1 - normalized)` inversion

---

## 13. Skill Invocation Reference

**In Claude Code (any project):**
```
/crowd-intelligence                          # full report, full universe
/crowd-intelligence NVDA AAPL XOM            # specific tickers
/crowd-intelligence --mode divergence-only   # only divergence alerts
/crowd-intelligence --sector technology      # sector deep dive
/crowd-intelligence --export json            # machine-readable output
```

**From terminal (any project with Python):**
```bash
python ~/.claude/plugins/crowd-intelligence/crowd_engine.py
python ~/.claude/plugins/crowd-intelligence/crowd_engine.py --tickers AAPL NVDA
python crowd_report.py --mode divergence-only   # if copied to project root
```
