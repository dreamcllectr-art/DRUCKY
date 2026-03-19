# Druckenmiller Dashboard Redesign — Full Spec

**Date:** 2026-03-19
**Status:** Reviewed (25 issues from spec review resolved)
**Author:** Claude (Technical Co-founder) + Jurgis (Product Owner)

---

## 1. Vision

Replace the current 15-page, 40+ tab dashboard with a **5-view architecture** modeled on how the world's best macro traders actually make decisions.

**Design philosophy:** The system should think like Druckenmiller (macro regime → high-conviction bets), filter like Jane Street (ruthless signal-to-noise), challenge like Soros (where is consensus wrong?), and present like Bloomberg (information density without clutter).

**Core principle:** The dashboard is a **funnel, not a catalog**. It progressively narrows from ~903 instruments to 5-20 actionable positions, showing its reasoning at every stage. Nothing is hidden — rejected candidates are visible with explanations — but attention is directed toward what matters most.

---

## 2. The 5 Views

### View 1: ENVIRONMENT (replaces: Home, Macro, Economic Indicators, Energy global data)

**Purpose:** Answer "What game are we playing?" in under 10 seconds.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  REGIME: [RISK_ON / NEUTRAL / RISK_OFF]  ← large, colored  │
│  Score: 67/100    Changed: 3 days ago    Trend: improving   │
├────────────┬────────────┬────────────┬──────────────────────┤
│ LIQUIDITY  │ RATES      │ CREDIT     │ VOLATILITY           │
│ M2: +11%   │ FFR: 4.0   │ HY OAS: 10│ VIX: -2              │
│ [green]    │ [green]    │ [green]    │ [green]              │
├────────────┴────────────┴────────────┴──────────────────────┤
│ ASSET CLASS SIGNALS (horizontal strip)                      │
│ Equities: ●● | Bonds: ○ | Commodities: ●●● | Crypto: ●    │
│ FX (DXY): ○○ | Gold: ●● | Oil: ●●                         │
├─────────────────────────────────────────────────────────────┤
│ LEADING INDICATORS (sparklines)                             │
│ Yield Curve ~~~  Credit Spreads ~~~  M2 Growth ~~~          │
│ ISM ~~~  Initial Claims ~~~  NDVI/ENSO ~~~                  │
├─────────────────────────────────────────────────────────────┤
│ CROSS-CUTTING INTELLIGENCE                                  │
│ ▸ Energy: Crude draws accelerating (+2.1σ vs seasonal)      │
│ ▸ Shipping: BDI up 15% WoW, port congestion easing          │
│ ▸ Rail: Intermodal +4.2% YoY (consumer strength)            │
│ ▸ Prediction Markets: 72% prob rate cut by June             │
│ ▸ Worldview: 3 active theses (AI capex, reshoring, energy)  │
├─────────────────────────────────────────────────────────────┤
│ REGIME CHANGE ALERTS (if any)                               │
│ ⚠ Credit spreads widened 40bps in 5 days — watch for shift  │
└─────────────────────────────────────────────────────────────┘
```

**Data sources:** macro_scores, economic_dashboard, economic_heat_index, energy_eia_enhanced, energy_supply_anomalies, supply_chain_scores (rail/shipping), prediction_market_signals, worldview_signals, market_breadth, sector_rotation.

**Key design decisions:**
- Macro indicators color-coded: green = bullish, red = bearish, yellow = neutral. Inverse indicators (VIX, credit spreads, DXY, real rates) have flipped logic.
- Asset class signals derived from ETF proxies (SPY, TLT, GLD, USO, UUP, BITO) + regime model output. Phase 1 uses existing macro_scores + convergence data. Phases 2-4 add real multi-asset data.
- Cross-cutting intelligence is auto-generated from module outputs — the 5 most significant non-ticker-specific findings from the latest pipeline run.
- Regime change alerts trigger when any of: regime score moves >10 pts in 3 days, credit spreads widen >30bps in a week, VIX crosses 25, yield curve inverts/un-inverts.

**Expandable deep-dives:** The Cross-Cutting Intelligence section supports "expand" actions. Clicking an energy bullet opens an inline energy deep-dive panel (supply/demand balance, inventory charts, trade flows) — preserving the depth of the current 4-tab energy view without requiring a separate page. Same pattern for economic indicators: clicking a sparkline opens that indicator's full history chart inline.

**What it replaces:**
- Home page top section (regime badge, breadth bar)
- Macro page (regime tab + economic indicators tab)
- Energy (all 4 tabs) — compressed to cross-cutting bullets + expandable deep-dive panels
- Parts of Synthesis (macro/breadth summary cards)

**Cold start fallback:** Before the pipeline runs asset class signal generation, the Asset Class Signals strip shows: "Asset class signals populate after next pipeline run. Showing regime-derived estimates." and uses macro_scores to infer directional tilts.

---

### View 2: FUNNEL (replaces: Home, Synthesis, Discover, Patterns, Signal Intelligence, Intelligence)

**Purpose:** The Druckenmiller cascade. Start broad, end with actionable picks.

This is the core of the dashboard. It's a **6-stage progressive filter** that narrows the universe from ~903+ instruments to a handful of high-conviction positions.

**Stage 1: Universe & Regime Context**
- Shows: Total universe count, current macro regime, regime-adaptive weights active
- Filter: None (this is the starting point)
- Source: stock_universe + macro_scores
- Display: Small header bar. "903 equities | Regime: NEUTRAL | 29 modules active"

**Stage 2: Asset Class Allocation**
- Shows: Which asset classes the regime favors
- Filter: Regime model recommends overweight/underweight per class
- Source: macro_scores regime → asset class mapping (new logic)
- Display: Horizontal bar showing allocation tilt. "Equities: Overweight | Bonds: Underweight | Commodities: Neutral | Crypto: Underweight"
- Phase 1: Informational only (equities-focused). Phases 2-4 add real filtering.
- User can override: Click any asset class to force include/exclude

**Stage 3: Sector & Theme Filter**
- Shows: Sectors ranked by regime favorability + thematic alignment
- Filter: Sectors with negative rotation scores get flagged (not removed)
- Source: sector_rotation, worldview_signals (active theses → sector tilts), energy_intel_signals, ai_regulatory, pharma_intel, ma_signals (sector M&A heat)
- Display: Sector cards with rotation score, thesis alignment, and stock count. Flagged sectors shown in muted colors with "X stocks filtered" count.
- Count: e.g., "645 stocks in 7 favored sectors | 258 in 4 flagged sectors"

**Stage 4: Technical Gate (The Druckenmiller Filter)**
- Shows: Stocks that pass/fail the chart confirmation test
- Filter criteria (extends existing `ta_gate.py` logic with additional checks):
  - Price vs 50/200 DMA (trend) — from technical_scores
  - RSI not overbought/oversold (momentum) — from technical_scores
  - Volume confirmation (accumulation vs distribution) — from technical_scores
  - Pattern match score > configurable threshold (default: TA_GATE_FULL from config.py) — from pattern_options_signals
  - Options flow not contradictory (new check) — from options_intel
- Relationship to existing ta_gate.py: Stage 4 **wraps** the existing TA gate as its core, adding the options flow check and the visual pass/fail UI. The existing `TA_GATE_SKIP` and `TA_GATE_FULL` thresholds from config.py are used. No duplicate logic.
- Source: technical_scores, pattern_options_signals, options_intel
- Display: Two columns — "PASSED" (green border) and "FLAGGED" (amber border, with reason). Each stock shows a mini chart thumbnail + key technical levels.
- Count: e.g., "312 passed technical gate | 333 flagged (124 below 200DMA, 89 overbought, 120 no pattern)"
- User override: Click any flagged stock to promote it to "passed" (manual override badge shown)

**Stage 5: Conviction Filter (The Evidence Stack)**
- Shows: Multi-factor evidence for each technically-confirmed stock
- Filter: Convergence score ranking. Stocks need ≥2 active modules (score > 50) to rank.
- Source: convergence_signals (all 29 module scores), insider_signals, consensus_blindspot_signals, variant_analysis, earnings_nlp_scores, news_displacement, estimate_momentum_signals, smart_money_scores, research_signals, foreign_intel_signals
- Display: Table sorted by convergence_score DESC. Each row is expandable:

```
┌──────────────────────────────────────────────────────────┐
│ ADM  63.0  HIGH  6 modules  ▸ Expand                     │
├──────────────────────────────────────────────────────────┤
│ [Expanded panel]                                         │
│                                                          │
│ MODULE SCORES (heatmap strip — 29 colored cells)         │
│ Smart Money: 72 | Worldview: 68 | Variant: 61 | ...      │
│                                                          │
│ KEY EVIDENCE:                                            │
│ • Insider cluster buy: 3 C-suite in 14 days ($2.1M)     │
│ • Consensus blindspot: 81.4 CBS — Street too bearish     │
│ • Estimate momentum: +5.2% EPS revision velocity         │
│ • Variant perception: 15% upside to fair value           │
│                                                          │
│ RISKS:                                                   │
│ • Devil's advocate: Commodity cycle peak risk             │
│ • Signal conflict: Pairs z-score suggests mean reversion  │
│ • Forensic: Clean (no flags)                             │
│                                                          │
│ CHART (inline candlestick with entry/stop/target)        │
│ Entry: $52.30 | Stop: $48.50 | Target: $61.00 | R:R 2.3 │
└──────────────────────────────────────────────────────────┘
```

- Count: e.g., "47 HIGH conviction | 89 NOTABLE | 176 WATCH"

**Stage 6: Position Sizing & Risk**
- Shows: Final position recommendations with sizing
- Filter: HIGH conviction + forensic clean + R:R > 1.5
- Source: signals (entry/stop/target), convergence_signals (conviction), forensic_alerts, devils_advocate, signal_conflicts
- Display: The "Conviction Board" — see View 3.
- This stage transitions into View 3.

**Funnel UI Architecture:**

```
┌─────────────────────────────────────────────────────────┐
│ FUNNEL PROGRESS BAR                                     │
│ [903] → [645] → [312] → [47 HIGH] → [12 ACTIONABLE]   │
│  Universe  Sector  Technical  Conviction  Position       │
│                       ▲ You are here                    │
├─────────────────────────────────────────────────────────┤
│ STAGE CONTENT (changes based on selected stage)         │
│                                                         │
│ [Left panel: Active stage content]                      │
│ [Right panel: Rejected/flagged with reasons]            │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

The progress bar at top is always visible. Clicking any stage shows that stage's content. The numbers update in real-time as you adjust filters or override decisions.

**Key design decisions:**
- Every stock that gets filtered out shows WHY. "Failed technical gate: below 200 DMA, distribution volume pattern."
- Users can click into any rejected stock to see its full dossier and manually promote it.
- The funnel runs automatically each day after the pipeline. Users see the latest results immediately.
- Stage transitions are animated — stocks visually flow from one stage to the next.
- Each stage has a small "override count" badge showing how many manual overrides are active.
- **Ad-hoc screening mode:** The Funnel has a "Filter" toggle (top-right) that opens a multi-factor filter panel. This allows queries like "show me all stocks with insider cluster buys AND positive estimate momentum, regardless of stage." Results display in the same table format as Stage 5 but bypass the cascade. This preserves the current Discover page's ad-hoc screening capability.
- **Watchlist integration:** The Funnel progress bar includes a "Watchlist" tab alongside the stages. This shows user-saved tickers with their current funnel stage position and convergence data. Users can add any ticker to the watchlist from any view via right-click or a bookmark icon. Watchlist is stored in the existing `watchlist` table.

---

### View 3: CONVICTION BOARD (replaces: parts of Home, Asset Detail page)

**Purpose:** The final picks — your active trade ideas with full dossiers.

**Layout:**

```
┌─────────────────────────────────────────────────────────┐
│ CONVICTION BOARD — 12 Actionable Positions               │
│ Total exposure: $1.2M | Sectors: 5 | Avg R:R: 2.4       │
├───────────┬─────────────────────────────────────────────┤
│ POSITION  │ DOSSIER (right panel, updates on selection)  │
│ LIST      │                                              │
│           │ ┌─────────────────────────────────────────┐  │
│ ● ADM     │ │ CHART (candlestick + entry/stop/target) │  │
│   63.0 H  │ │                                         │  │
│   +2.3 R:R│ └─────────────────────────────────────────┘  │
│           │                                              │
│ ● FFIN    │ THESIS: Why this trade                       │
│   61.6 H  │ "ADM: Commodity cycle inflection + insider   │
│   +1.8 R:R│  cluster buy. 6 modules confirm. Variant     │
│           │  perception sees 15% upside to fair value.   │
│ ● BMY     │  Worldview thesis: reshoring + food security  │
│   61.4 H  │  drives ag demand."                          │
│   +2.1 R:R│                                              │
│           │ EVIDENCE (module strip + key bullets)         │
│ ● COKE    │ RISKS (devil's advocate + conflicts)         │
│   61.3 H  │ FUNDAMENTALS (key ratios)                    │
│   +1.5 R:R│ TRADE SETUP (entry, stop, target, size)      │
│           │ SIMILAR TRADES (pairs, sector peers)          │
│ ...       │                                              │
├───────────┴─────────────────────────────────────────────┤
│ BLOCKED POSITIONS (forensic vetoes — collapsed by default)│
│ ▸ XYZ — BLOCKED: Accounting red flag (revenue recognition)│
└─────────────────────────────────────────────────────────┘
```

**Dossier sections (for each selected stock):**

1. **Chart** — Candlestick with entry level (green), stop loss (red), target (blue), current price. 50/200 DMA overlaid. Volume bars below. Patterns annotated.
   - Source: price_data, signals (entry/stop/target), pattern_scan

2. **Thesis** — Auto-generated narrative explaining WHY this stock is here. Combines convergence narrative + worldview thesis + variant perception.
   - Source: convergence_signals.narrative, worldview_signals.narrative, variant_analysis.thesis, devils_advocate.bear_thesis

3. **Evidence** — Module heatmap strip (29 cells) + top 5 contributing modules with detail.
   - Source: convergence_signals (all module score columns)

4. **Risks** — Devil's advocate bear case, signal conflicts, forensic status, stress test exposure.
   - Source: devils_advocate, signal_conflicts, forensic_alerts, stress_test_results

5. **Fundamentals** — Key ratios: P/E, EV/EBITDA, revenue growth, margins, debt/equity. Color-coded vs sector median.
   - Source: fundamentals table

6. **Trade Setup** — Entry, stop, target, R:R ratio, position size (dollars + shares), % of portfolio.
   - Source: signals table

7. **Catalysts** — Upcoming earnings, M&A rumors, regulatory events, insider activity.
   - Source: earnings_calendar, ma_rumors, regulatory_events, insider_signals

**Key design decisions:**
- This is a **master-detail** layout. Left panel is the ranked list; right panel is the selected stock's full dossier.
- List is sorted by convergence_score DESC by default. Can re-sort by R:R ratio, sector, or recency.
- BLOCKED positions (forensic veto) shown at bottom in a collapsed section — visible but clearly separated.
- The thesis narrative is the most important element. It answers "why should I care?" in 2-3 sentences.
- Chart is interactive — lightweight-charts library (already in the project).

---

### View 4: RISK (new — partially replaces: Risk & Thesis, Performance)

**Purpose:** Portfolio-level risk management and edge monitoring.

**Layout:**

```
┌─────────────────────────────────────────────────────────┐
│ RISK OVERVIEW                                            │
├────────────┬────────────┬────────────┬──────────────────┤
│ EXPOSURE   │ CONCENTRA. │ CORRELATION│ EDGE HEALTH      │
│ $1.2M long │ HHI: 0.08  │ Avg: 0.32  │ 24/29 modules   │
│ $0 short   │ Low risk   │ Diversified│ producing signal │
├────────────┴────────────┴────────────┴──────────────────┤
│                                                          │
│ SECTOR EXPOSURE (horizontal stacked bar)                 │
│ Tech 28% | Healthcare 22% | Financials 18% | Energy 15% │
│                                                          │
│ STRESS SCENARIOS                                         │
│ ┌──────────────┬──────────┬───────────────────────────┐  │
│ │ Scenario     │ Impact   │ Worst Hit                 │  │
│ │ -20% crash   │ -$180K   │ ADM (-24%), FFIN (-19%)   │  │
│ │ Rate spike   │ -$95K    │ FFIN (-15%), BG (-12%)    │  │
│ │ Oil shock    │ +$45K    │ Benefits energy positions  │  │
│ └──────────────┴──────────┴───────────────────────────┘  │
│                                                          │
│ SIGNAL CONFLICTS (active)                                │
│ ▸ ADM: Pairs z-score (-1.8) vs Convergence bullish       │
│ ▸ BMY: Insider selling vs Smart Money accumulation        │
│                                                          │
│ EDGE DECAY TRACKING                                      │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ Module           │ IC (30d) │ IC (90d) │ Trend     │  │
│ │ Smart Money      │ 0.12     │ 0.15     │ stable    │  │
│ │ Variant          │ 0.08     │ 0.11     │ declining │  │
│ │ Insider          │ 0.18     │ 0.14     │ improving │  │
│ │ ...              │          │          │           │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                          │
│ MODULE WEIGHTS (current regime)                          │
│ Adaptive optimizer: ON | Last update: today               │
│ [Treemap visualization of current weights]                │
│                                                          │
│ TRACK RECORD                                             │
│ Overall win rate: 62% | Avg win: +8.2% | Avg loss: -4.1% │
│ Profit factor: 2.0 | Sharpe: 1.4                        │
│ [Monthly returns heatmap]                                │
└─────────────────────────────────────────────────────────┘
```

**Data sources:** portfolio, signal_outcomes, module_performance, module_ic_summary, weight_history, stress_test_results, concentration_risk, signal_conflicts.

**Key design decisions:**
- Edge decay is Jane Street's obsession — if a module's IC is declining, its weight should decrease. This view surfaces that.
- Track record provides accountability. Every signal is tracked for 1d/5d/10d/20d/30d/60d/90d outcomes.
- Stress scenarios use the existing stress_test_results table.
- Signal conflicts surface contradictions between modules — these are often the most informative signals.

---

### View 5: JOURNAL (new)

**Purpose:** Trade thesis tracking and outcome attribution. Every prop desk requires this.

**Layout:**

```
┌─────────────────────────────────────────────────────────┐
│ TRADE JOURNAL                                            │
├─────────────────────────────────────────────────────────┤
│ OPEN POSITIONS (from portfolio table)                    │
│ ┌─────────┬────────┬────────┬────────┬────────────────┐ │
│ │ Symbol  │ Entry  │ P&L    │ Days   │ Thesis Status  │ │
│ │ ADM     │ $52.30 │ +4.2%  │ 12     │ On track ●     │ │
│ │ FFIN    │ $38.10 │ -1.1%  │ 5      │ Watching ◐     │ │
│ │ BMY     │ $41.50 │ +2.8%  │ 8      │ On track ●     │ │
│ └─────────┴────────┴────────┴────────┴────────────────┘ │
│                                                          │
│ SELECTED POSITION: ADM                                   │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ ENTRY THESIS (auto-captured at position open):      │  │
│ │ "Commodity cycle inflection. 6 modules confirmed.   │  │
│ │  Insider cluster buy. Variant sees 15% upside."     │  │
│ │                                                     │  │
│ │ WHAT'S CHANGED SINCE ENTRY:                         │  │
│ │ • Convergence: 63.0 → 65.2 (+2.2) ↑                │  │
│ │ • Insider: New purchase by CFO ($400K)              │  │
│ │ • Estimate momentum: EPS revised up 3%              │  │
│ │ • Risk: Credit spreads widened (macro headwind)     │  │
│ │                                                     │  │
│ │ DECISION LOG:                                       │  │
│ │ [User can add notes: "Holding — thesis intact"]     │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                          │
│ CLOSED TRADES (with outcome attribution)                 │
│ ┌─────────┬────────┬────────┬──────────────────────────┐ │
│ │ Symbol  │ P&L    │ Days   │ Why It Worked/Failed     │ │
│ │ GILD    │ +12.3% │ 34     │ Thesis: Pharma pipeline  │ │
│ │ NXT     │ -5.1%  │ 18     │ Stopped out: sector rot. │ │
│ └─────────┴────────┴────────┴──────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Data sources:** portfolio (open + closed), convergence_signals (historical), signals (historical), devils_advocate, signal_outcomes, journal_entries, watchlist.

**Key design decisions:**
- Entry thesis is auto-captured from convergence_signals.narrative at the time of position open. Stored in `portfolio.entry_thesis` and `portfolio.entry_convergence_snapshot` (JSON of all module scores at open date).
- "What's changed" compares current module scores to the entry_convergence_snapshot. Uses `/api/convergence/{symbol}` (current) vs stored snapshot (entry).
- Decision log allows the user to annotate trades — this builds the feedback loop that makes great traders great.
- Outcome attribution on closed trades: which modules were right? Which were wrong? This feeds back into the weight optimizer.
- **Hyperliquid data** surfaces here for crypto positions (Phase 2): weekend gap predictions, deployer spread signals, and gap accuracy tracking. In Phase 1, HL data is accessible via Command Palette search ("HL gaps", "hyperliquid") which opens a lightweight panel.
- **Thematic ideas** are preserved: the Journal includes a "Themes" sub-tab showing active thematic narratives (from `narrative_signals` + `thematic_ideas` tables) mapped to open positions. This answers "which of my positions express the AI capex theme?"

---

## 3. Navigation

The sidebar collapses from 15 items to 5:

```
┌──────────────┐
│ ◉ Environment│  ← Macro regime + cross-cutting intel
│ ◎ Funnel     │  ← 6-stage progressive filter (DEFAULT VIEW)
│ ◎ Conviction │  ← Final picks + dossiers
│ ◎ Risk       │  ← Portfolio risk + edge monitoring
│ ◎ Journal    │  ← Trade log + outcome tracking
├──────────────┤
│ ⌘K Search    │  ← Command palette (already exists)
│ ⚙ Settings   │  ← Pipeline status, data freshness
└──────────────┘
```

**Default view:** Funnel. This is where you spend 80% of your time.

**Asset Detail:** No longer a separate page. Clicking any ticker anywhere opens its full dossier as a **slide-over panel** from the right (60% width). This means you never lose context — you can view a stock's detail while still seeing the funnel or conviction board.

**Command Palette (Cmd+K):** Already exists. Becomes the primary way to jump to any stock, module, or view. Type a ticker → see its dossier. Type "regime" → jump to environment. Type "risk" → jump to risk view.

---

## 4. What Gets Cut

| Current Page/Tab | Disposition |
|------------------|-------------|
| Home | **Merged** into Funnel (conviction cards) + Environment (regime/breadth) |
| Synthesis | **Merged** into Funnel Stage 5 (convergence heatmap lives here) |
| Discover | **Replaced** by Funnel (discover IS the funnel) |
| Macro (Regime tab) | **Moved** to Environment |
| Macro (Economic Indicators tab) | **Moved** to Environment (leading indicators section) |
| Energy (all 4 tabs) | **Moved**: Supply/Production/Flows/Global → Environment cross-cutting intel with expandable deep-dive panels (preserves full depth). Ticker-level energy scores → Funnel expandable panels. |
| Patterns (Scanner/Rotation/Options/Cycles) | **Moved** to Funnel Stage 4 (Technical Gate). Rotation → Environment. |
| Signal Intelligence (7 tabs) | **Dissolved**: Each tab's data feeds into Funnel Stage 5 expandable panels. Insider, Blindspots, Displacement, Pairs, Est. Momentum, M&A, Alt Data become evidence bullets in the conviction filter. |
| Intelligence (Regulatory/AI Exec/Predictions) | **Moved**: Regulatory → Funnel expandable panels (regulatory risk section). AI Exec → conviction evidence. Predictions → Environment (cross-cutting intel). |
| Performance (Overview/Module/Track Record/Weights) | **Moved** to Risk view (edge decay + track record sections) |
| Reports & Ideas | **Cut** as standalone pages. Thematic ideas preserved in Journal "Themes" sub-tab. The funnel output + conviction board replace generated reports. |
| Portfolio | **Moved** to Journal view |
| Risk & Thesis (Conflicts/Stress Test/Thesis Lab) | **Moved** to Risk view |
| Alpha (IC/Narratives) | **Moved**: IC → Risk (edge decay). Narratives → Environment (active theses) or Funnel Stage 3 (sector/theme filter). |
| Asset Detail (separate page) | **Replaced** by slide-over dossier panel |

---

## 5. Data Model Changes

### New Tables

```sql
-- Funnel state tracking (persists user overrides)
CREATE TABLE IF NOT EXISTS funnel_overrides (
    symbol TEXT,
    stage TEXT,  -- 'sector', 'technical', 'conviction'
    action TEXT, -- 'promote', 'demote'
    reason TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT, -- auto-expire after N days (default: 14 days from created_at)
    PRIMARY KEY (symbol, stage)
);
-- Note: Overrides auto-expire after 14 days. The funnel query filters WHERE expires_at > datetime('now').
-- Users can refresh an override (resets expires_at) from the UI.

-- Trade journal entries (user notes, linked to specific portfolio positions)
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER REFERENCES portfolio(id), -- links to specific position
    symbol TEXT NOT NULL,
    entry_type TEXT, -- 'note', 'thesis_update', 'exit_reason'
    content TEXT,
    convergence_snapshot TEXT, -- JSON of module scores at time of entry
    created_at TEXT DEFAULT (datetime('now'))
);

-- Asset class signals (Phase 1: ETF proxies)
CREATE TABLE IF NOT EXISTS asset_class_signals (
    asset_class TEXT, -- 'equities', 'bonds', 'commodities', 'crypto', 'fx', 'gold'
    date TEXT,
    proxy_symbol TEXT, -- SPY, TLT, GLD, USO, UUP, BITO
    regime_signal TEXT, -- 'overweight', 'neutral', 'underweight'
    score REAL,
    rationale TEXT,
    details TEXT, -- JSON: source indicators, ETF technicals, regime model inputs
    PRIMARY KEY (asset_class, date)
);

-- Funnel stage counts (daily snapshot for progress bar)
CREATE TABLE IF NOT EXISTS funnel_snapshot (
    date TEXT,
    run_id TEXT DEFAULT (datetime('now')), -- supports multiple runs per day
    universe_count INTEGER,
    sector_passed INTEGER,
    sector_flagged INTEGER,
    technical_passed INTEGER,
    technical_flagged INTEGER,
    conviction_high INTEGER,
    conviction_notable INTEGER,
    conviction_watch INTEGER,
    actionable_count INTEGER,
    PRIMARY KEY (date, run_id)
);
```

**Portfolio table additions** (via ALTER TABLE migrations in db.py):

```sql
-- Columns added to existing portfolio table for Journal view
ALTER TABLE portfolio ADD COLUMN entry_thesis TEXT;
-- Auto-captured from convergence_signals.narrative at position open
ALTER TABLE portfolio ADD COLUMN entry_convergence_snapshot TEXT;
-- JSON of all 29 module scores at entry date, enabling "what's changed" deltas
```

### New API Endpoints

```
# Environment
GET  /api/environment              — Aggregated: regime + indicators + asset class signals + cross-cutting intel
GET  /api/environment/alerts       — Regime change alerts
GET  /api/environment/asset-classes — Asset class signals with scores and rationale
GET  /api/environment/deep-dive/{topic} — Expandable deep-dive (topic: 'energy', 'rates', 'shipping', etc.)

# Funnel
GET  /api/funnel                   — Full funnel state (all 6 stages with counts + overrides)
GET  /api/funnel/stage/2           — Asset class allocation (returns: asset_class_signals)
GET  /api/funnel/stage/3           — Sector & theme filter (returns: sector_rotation + worldview theses)
GET  /api/funnel/stage/4           — Technical gate (returns: stocks with pass/fail + reasons)
GET  /api/funnel/stage/5           — Conviction filter (returns: convergence_signals ranked)
GET  /api/funnel/stage/6           — Position sizing (returns: actionable positions)
# Note: Each stage returns different data schemas. Stage 2 returns asset class objects,
# Stages 3-6 return stock-level arrays with stage-specific fields.
GET  /api/funnel/filter            — Ad-hoc multi-factor filter (query params: module scores, sectors, etc.)
GET  /api/funnel/overrides         — User's active (non-expired) overrides
POST /api/funnel/override          — Add override {symbol, stage, action, reason}
DELETE /api/funnel/override/{symbol}/{stage} — Remove specific override

# Dossier (progressive loading — summary first, sections on demand)
GET  /api/dossier/{symbol}         — Summary: chart data + thesis + conviction level + trade setup
GET  /api/dossier/{symbol}/evidence — Module heatmap + top contributing modules with detail
GET  /api/dossier/{symbol}/risks   — Devil's advocate + conflicts + forensic + stress exposure
GET  /api/dossier/{symbol}/fundamentals — Key ratios vs sector median
GET  /api/dossier/{symbol}/catalysts — Upcoming events (earnings, M&A, regulatory, insider)

# Conviction Board
GET  /api/conviction-board         — Top actionable positions with sizing
GET  /api/conviction-board/blocked — Forensic-blocked positions

# Risk
GET  /api/risk/overview            — Portfolio exposure, concentration, correlation
GET  /api/risk/edge-decay          — Module IC trends (30d vs 90d)
GET  /api/risk/track-record        — Monthly returns + win rate

# Journal
GET  /api/journal/open             — Open positions with thesis + score deltas since entry
GET  /api/journal/closed           — Closed with outcome attribution
POST /api/journal/note             — Add journal entry {portfolio_id, symbol, content, entry_type}
GET  /api/journal/themes           — Active thematic narratives mapped to open positions

# Portfolio CRUD (for Journal manual management)
POST /api/portfolio                — Open new position {symbol, entry_price, shares, stop_loss, target_price}
PUT  /api/portfolio/{id}           — Update position (adjust stop_loss, target_price, notes)
POST /api/portfolio/{id}/close     — Close position {exit_price, exit_reason}

# Historical convergence (for Journal "what's changed" deltas)
GET  /api/convergence/{symbol}/history — Historical convergence scores {from_date, to_date}
```

**Existing `/api/asset/{symbol}` endpoint:** Retained for backwards compatibility. The new `/api/dossier/{symbol}` is a superset. The slide-over panel consumes the dossier endpoints. Old asset endpoint serves as fallback.

### Existing Endpoints Retained (consumed by new views)

All existing module-level endpoints (insider, pairs, convergence, patterns, etc.) are retained. The new aggregation endpoints compose them. No existing endpoints are deleted — they become the building blocks.

---

## 6. Component Architecture

### New Components

```
src/components/
  environment/
    EnvironmentView.tsx         — Main environment layout
    RegimeHeader.tsx            — Large regime indicator + score
    IndicatorStrip.tsx          — Liquidity/rates/credit/vol cards
    AssetClassBar.tsx           — Asset class signal strip
    LeadingIndicators.tsx       — Sparkline grid
    CrossCuttingIntel.tsx       — Auto-generated intelligence bullets
    RegimeAlerts.tsx            — Change alerts
    DeepDivePanel.tsx           — Expandable inline panel for energy/rates/indicators
    IndicatorHistoryChart.tsx   — Full history chart for individual indicators

  funnel/
    FunnelView.tsx              — Main funnel layout
    FunnelProgressBar.tsx       — Stage progress with counts
    StageSelector.tsx           — Stage navigation
    SectorStage.tsx             — Stage 3 content
    TechnicalGate.tsx           — Stage 4 content
    ConvictionFilter.tsx        — Stage 5 content (main table)
    ConvictionRow.tsx           — Expandable stock row
    EvidencePanel.tsx           — Expanded evidence (modules + bullets)
    RejectedPanel.tsx           — Right panel showing filtered-out stocks
    OverrideBadge.tsx           — Manual override indicator
    MiniChart.tsx               — Thumbnail chart for technical gate
    FilterPanel.tsx             — Ad-hoc multi-factor screening panel
    WatchlistPanel.tsx          — Watchlist tab in funnel progress bar

  conviction/
    ConvictionBoard.tsx         — Main conviction board layout
    PositionList.tsx            — Left panel ranked list
    Dossier.tsx                 — Right panel stock dossier
    DossierChart.tsx            — Candlestick with levels
    DossierThesis.tsx           — Auto-generated thesis narrative
    DossierEvidence.tsx         — Module heatmap + evidence bullets
    DossierRisks.tsx            — Devil's advocate + conflicts
    DossierFundamentals.tsx     — Key ratios grid
    DossierTradeSetup.tsx       — Entry/stop/target/sizing
    DossierCatalysts.tsx        — Upcoming events

  risk/
    RiskView.tsx                — Main risk layout
    ExposureOverview.tsx        — Portfolio exposure cards
    SectorExposureBar.tsx       — Stacked sector bar
    StressScenarios.tsx         — Scenario impact table
    SignalConflicts.tsx          — Active conflicts list
    EdgeDecayTable.tsx          — Module IC trends
    WeightTreemap.tsx           — Current weight visualization
    TrackRecord.tsx             — Monthly returns heatmap

  journal/
    JournalView.tsx             — Main journal layout
    OpenPositions.tsx           — Active trades with thesis
    PositionDetail.tsx          — Selected position deep view
    ThesisCapture.tsx           — Entry thesis display
    ChangeSinceEntry.tsx        — Delta from entry scores
    DecisionLog.tsx             — User annotations
    ClosedTrades.tsx            — Outcome attribution table
    ThemesPanel.tsx             — Thematic narratives mapped to positions

  shared/
    SlideOverPanel.tsx          — Reusable slide-over (for dossier anywhere)
    ModuleHeatstrip.tsx         — 29-cell module score strip
    Sparkline.tsx               — (existing, reuse)
    SignalBadge.tsx             — (existing, reuse)
    PriceChart.tsx              — (existing, enhance with levels)
    CommandPalette.tsx          — (existing, reuse)
    ErrorBoundary.tsx           — (existing, reuse)
```

### Deleted Components (replaced by new architecture)

```
HomeContent.tsx          → EnvironmentView + FunnelView
SynthesisContent.tsx     → FunnelView (Stage 5)
DiscoverContent.tsx      → FunnelView
PatternsContent.tsx      → FunnelView (Stage 4)
EnergyContent.tsx        → EnvironmentView + Dossier panels
ReportsContent.tsx       → Cut (funnel IS the report)
AlphaContent.tsx         → Risk (IC section) + Funnel (narratives)
PerformanceContent.tsx   → RiskView

All tab components dissolved into funnel evidence panels or environment sections.
```

### Routes (src/app/)

```
/                   → Redirect to /funnel
/environment        → EnvironmentView
/funnel             → FunnelView (default, Stage 5 selected)
/conviction         → ConvictionBoard
/risk               → RiskView
/journal            → JournalView
/login              → (kept as-is)
```

Asset detail route `/asset/[symbol]` removed. Replaced by `SlideOverPanel` triggered from any ticker click.

---

## 7. Multi-Asset Phasing

### Phase 1 (This Build)
- Funnel architecture with 903 equities
- 20 ETF proxies added to stock_universe for asset class signals: SPY, QQQ, IWM, TLT, IEF, SHY, GLD, SLV, USO, XLE, UUP, BITO, ETHE, COPX, WEAT, DBA, XLF, XLK, XLV, XLI
- Asset Class stage (Stage 2) shows regime-derived recommendations
- Environment view shows macro indicators for all asset classes via ETF proxies
- Data sources: All existing + CoinGecko (free tier) for crypto prices

### Phase 2 (Crypto)
- Add 20 crypto assets: BTC, ETH, SOL, AVAX, LINK, DOT, MATIC, UNI, AAVE, OP, ARB, DOGE, PEPE, INJ, TIA, SUI, APT, SEI, JUP, RENDER
- Data: CoinGecko API (prices, volume, market cap) + Nansen (on-chain: whale activity, DEX flows, staking) + Etherscan (gas, contract activity)
- On-chain analytics become a new convergence module for crypto assets
- Hyperliquid data (already exists) expands to cover more crypto pairs

### Phase 3 (FX + Bonds)
- Add 10 FX pairs: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD, EUR/GBP, EUR/JPY, GBP/JPY
- Add bond instruments: US 2Y, 5Y, 10Y, 30Y yields; Germany 10Y; Japan 10Y
- Data: Alpha Vantage (FX rates) + FRED (yields, term structure)
- Carry trade module + rate differential scoring

### Phase 4 (Commodities)
- Add individual commodities: Gold, Silver, Copper, Oil (WTI + Brent), Natural Gas, Wheat, Corn, Soybeans, Coffee, Lumber
- Data: Alpha Vantage/FMP (futures prices) + EIA (energy, expanded) + USDA (agriculture)
- Supply/demand balance scoring per commodity
- COT (Commitments of Traders) data for positioning

---

## 8. Design System

Retain existing light-mode design language (Apple-like, white cards, subtle shadows). Key adjustments:

**Information Hierarchy:**
- Level 1 (glanceable): Regime badge, funnel progress bar, conviction count
- Level 2 (scannable): Stock rows, module scores, key metrics
- Level 3 (drill-down): Expanded panels, dossier sections, chart details

**Color System:**
- Bullish/positive: `#059669` (emerald-600)
- Bearish/negative: `#e11d48` (rose-600)
- Neutral/caution: `#d97706` (amber-600)
- Information: `#2563eb` (blue-600)
- Background: `#f9fafb` (gray-50)
- Cards: `#ffffff` (white) with `shadow-sm`
- Muted/filtered: `opacity-50` on filtered-out items

**Typography:**
- Display/headers: Inter 600-700
- Data/numbers: JetBrains Mono
- Body: Inter 400

**Density:** Bloomberg-inspired. More data per pixel than typical dashboards, but with clear visual hierarchy so the eye knows where to look first.

---

## 9. Performance Requirements

- **Initial load:** < 2 seconds for Funnel view (most-used)
- **Stage transitions:** < 500ms (data pre-fetched)
- **Dossier slide-over:** < 800ms (lazy-loaded)
- **Environment view:** < 1.5 seconds
- **Data freshness:** All views show "Data as of HH:MM" timestamp

**Optimization strategy:**
- Funnel stages pre-fetch adjacent stages on load
- Dossier uses progressive loading: `/api/dossier/{symbol}` (summary) loads on hover (~2 queries, fast). Evidence, risks, fundamentals, catalysts load on-demand when their accordion sections are expanded. This prevents the full 10+ query cost from blocking the initial panel open.
- Environment data cached for 5 minutes (macro doesn't change fast)
- WebSocket for regime change alerts (future enhancement)

---

## 10. Migration Strategy

**Approach:** Build new views under `/v2/` route prefix alongside existing pages. Feature flag in `localStorage` (`dashboard_version: 'v1' | 'v2'`) controls which Sidebar navigation renders. Toggle via Settings or `?v=2` URL parameter. Once new views are validated, promote v2 to root and remove v1.

**Step 1:** Build new API endpoints (environment, funnel, dossier, journal CRUD) + new DB tables
**Step 2:** Build Funnel view — Stage 4 (Technical Gate) + Stage 5 (Conviction Filter) first
  - Note: During this step, Stages 4-5 operate on the FULL universe (no sector filtering yet). This is expected — funnel counts will change when Stages 1-3 are wired in. Display a "(unfiltered)" badge on the progress bar during this intermediate state.
**Step 3:** Build Funnel Stages 1-3 (Universe, Asset Class, Sector/Theme) + Stage 6
**Step 4:** Build Environment view
**Step 5:** Build Conviction Board + slide-over dossier panel
**Step 6:** Build Risk view
**Step 7:** Build Journal view
**Step 8:** Update Sidebar navigation (v2 flag controls which nav renders)
**Step 9:** Remove old pages — sub-steps:
  - 9a. Verify mapping: each old component → its new replacement (checklist below)
  - 9b. Remove old route directories (src/app/macro, src/app/patterns, etc.)
  - 9c. Remove old components (HomeContent.tsx, SynthesisContent.tsx, etc.)
  - 9d. Remove dead API endpoints (if any are no longer consumed)
  - 9e. Promote /v2/ routes to root (/ → /funnel, etc.)
**Step 10:** Multi-asset Phase 1 (ETF proxies + asset class signal generation in pipeline)

**Old → New Component Mapping (for Step 9a verification):**

| Old Component | New Replacement | Verified? |
|--------------|-----------------|-----------|
| HomeContent.tsx | EnvironmentView + FunnelView | [ ] |
| SynthesisContent.tsx | FunnelView (Stage 5) | [ ] |
| DiscoverContent.tsx | FunnelView (filter mode) | [ ] |
| PatternsContent.tsx | FunnelView (Stage 4) | [ ] |
| EnergyContent.tsx + tabs | EnvironmentView (deep-dive panels) | [ ] |
| ReportsContent.tsx | Removed (funnel IS the report) | [ ] |
| AlphaContent.tsx | RiskView (IC) + EnvironmentView (narratives) | [ ] |
| PerformanceContent.tsx | RiskView (track record + edge decay) | [ ] |
| AssetContent.tsx | SlideOverPanel + Dossier | [ ] |
| InsiderTab.tsx | Dossier evidence panel | [ ] |
| ConsensusBlindspotTab.tsx | Dossier evidence panel | [ ] |
| PairsTab.tsx | Dossier evidence panel | [ ] |
| EstimateMomentumTab.tsx | Dossier evidence panel | [ ] |
| MATab.tsx | Dossier evidence panel | [ ] |
| AltDataTab.tsx | Dossier evidence panel | [ ] |
| DisplacementTab.tsx | Dossier evidence panel | [ ] |
| RegulatoryTab.tsx | Dossier evidence panel | [ ] |
| AIExecTab.tsx | Dossier evidence panel | [ ] |
| PredictionsTab.tsx | EnvironmentView (cross-cutting) | [ ] |
| WorldviewTab.tsx | EnvironmentView + Funnel Stage 3 | [ ] |
| StressTestTab.tsx | RiskView (stress scenarios) | [ ] |
| SignalConflictsTab.tsx | RiskView (signal conflicts) | [ ] |
| ThesisTab.tsx | JournalView (themes sub-tab) | [ ] |
| WatchlistTab.tsx | FunnelView (watchlist tab) | [ ] |
| TradingIdeasTab.tsx | Removed (conviction board IS trading ideas) | [ ] |

Each step is independently deployable and testable.

---

## 11. Known Schema Issues to Resolve

**Module count:** The convergence engine docstring says "24 modules" but the actual code loads 29 (the 5 new Alt Alpha II modules — aar_rail, ship_tracking, patent_intel, ucc_filings, board_interlocks — were added recently). The convergence_engine.py docstring needs updating to say 29. All UI references (module heatstrip, evidence panels) should render 29 cells.

**worldview_signals table:** The CREATE TABLE in db.py has PRIMARY KEY (date, thesis) — thesis-level. But the pipeline upserts symbol-level rows (with `symbol` as a column, not a key). Stage 3 of the funnel needs thesis-level data ("which theses are active?") while the dossier needs symbol-level data ("how does this stock align with active theses?"). Resolution: keep the table as-is (thesis-level PK), and query for Stage 3 with `SELECT DISTINCT thesis, direction, confidence, affected_sectors FROM worldview_signals WHERE date = (SELECT MAX(date) FROM worldview_signals)`. For symbol-level dossier data, query with `WHERE symbol = ?`. Both work because the table contains rows at both granularities.

---

## 12. Success Criteria

The redesign is successful when:

1. **Morning scan takes < 5 minutes.** Open dashboard → Environment (10s) → Funnel shows today's picks (30s) → Review top 5 dossiers (4 min) → Done.

2. **Every view answers exactly one question:**
   - Environment: "What kind of market is this?"
   - Funnel: "What should I look at?"
   - Conviction: "What should I trade?"
   - Risk: "What could go wrong?"
   - Journal: "Am I improving?"

3. **Zero dead states.** No "No data available" messages. Every view has meaningful content even before the pipeline runs (show historical data, explain what will populate after pipeline).

4. **The system challenges you.** Devil's advocate is prominent. Signal conflicts are surfaced. Blocked positions are visible. The dashboard doesn't just confirm bias — it fights it.

5. **Track record is honest.** Every signal is tracked. Every module's accuracy is visible. Edge decay is monitored. The system earns trust through transparency.
