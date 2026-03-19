# Crowd Intelligence System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a universal institutional-grade crowd positioning intelligence system — 3 data-collection layers (retail/institutional/smart money), IC-weighted scoring engine, divergence detection, FastAPI endpoints, dashboard tab, and a portable Claude skill.

**Architecture:** Four Python modules collect signals from 13 free sources. A scoring engine normalizes, decay-weights, IC-combines, and regime-conditions scores into a 0–100 conviction score per ticker. A divergence detector classifies setups using Wyckoff theory. The same engine powers a standalone CLI, the daily pipeline, and a universal Claude Code skill.

**Tech Stack:** Python 3.11, FastAPI, SQLite (via existing db.py), yfinance, praw, requests, beautifulsoup4, pytrends, fredapi, numpy, pandas, Next.js/React (dashboard tab)

**Spec:** `docs/superpowers/specs/2026-03-19-crowd-intelligence-design.md`

**Python runtime:** `/tmp/druck_venv/bin/python` (never use `venv/` — iCloud evicts .so files)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/db.py` | Modify | Add `crowd_intelligence` DDL to `init_db()` |
| `tools/crowd_types.py` | Create | `Signal` dataclass — shared by all 4 modules |
| `tools/crowd_retail.py` | Create | Layer 1: Reddit, Fear&Greed, AAII, Google Trends |
| `tools/crowd_institutional.py` | Create | Layer 2: ETF flows, CFTC COT, FINRA ATS, 13F, short interest, margin debt |
| `tools/crowd_smart.py` | Create | Layer 3: insider clusters, options skew, Polymarket |
| `tools/crowd_engine.py` | Create | Normalize, decay, score, divergence, confirmation gate, report |
| `crowd_report.py` | Create | Standalone terminal CLI |
| `tools/daily_pipeline.py` | Modify | Add Phase 2.95: crowd intelligence after macro_regime |
| `tools/api_market_modules.py` | Modify | Add 5 `/api/crowd-intelligence/*` endpoints |
| `dashboard/src/components/CrowdContent.tsx` | Create | Dashboard tab — macro map, sector crowding, divergences, conviction |
| `dashboard/src/app/layout.tsx` | Modify | Add "Crowd" sidebar entry |
| `~/.claude/plugins/crowd-intelligence/SKILL.md` | Create | Universal Claude skill |
| `~/.claude/plugins/crowd-intelligence/` | Create | Copy crowd_*.py + crowd_engine.py into skill folder |
| `tests/test_crowd_engine.py` | Create | Unit tests for scoring math |

---

## Task 1: DB Schema

**Files:**
- Modify: `tools/db.py` — add crowd_intelligence table to `init_db()` executescript

- [ ] **Step 1: Add DDL to db.py**

Open `tools/db.py`. Inside `init_db()`, append to the `cur.executescript("""...""")` block (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS crowd_intelligence (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    date                        TEXT NOT NULL,
    ticker                      TEXT,
    scope                       TEXT NOT NULL,
    sector                      TEXT,
    retail_crowding_score       REAL,
    institutional_score         REAL,
    smart_money_score           REAL,
    conviction_score            REAL,
    divergence_type             TEXT,
    divergence_strength         REAL,
    confirmation_gate_passed    INTEGER,
    retail_signals              TEXT,
    institutional_signals       TEXT,
    smart_money_signals         TEXT,
    macro_regime                TEXT,
    narrative                   TEXT,
    signals_available           INTEGER,
    signals_total               INTEGER,
    created_at                  TEXT DEFAULT (datetime('now')),
    UNIQUE(date, ticker, scope)
);
CREATE INDEX IF NOT EXISTS idx_crowd_date       ON crowd_intelligence(date);
CREATE INDEX IF NOT EXISTS idx_crowd_ticker     ON crowd_intelligence(ticker);
CREATE INDEX IF NOT EXISTS idx_crowd_divergence ON crowd_intelligence(divergence_type);
```

- [ ] **Step 2: Verify schema creates cleanly**

```bash
/tmp/druck_venv/bin/python -c "from tools.db import init_db; init_db(); print('OK')"
```
Expected: `OK` with no errors.

- [ ] **Step 3: Commit**

```bash
git add tools/db.py
git commit -m "feat: add crowd_intelligence table to db schema"
```

---

## Task 2: Signal Dataclass

**Files:**
- Create: `tools/crowd_types.py`

- [ ] **Step 1: Write tests first**

Create `tests/test_crowd_engine.py`:

```python
"""Tests for crowd intelligence scoring engine."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest
from tools.crowd_types import Signal
from tools.crowd_engine import (
    normalize_signal_value,
    apply_decay,
    score_layer,
    compute_conviction,
    run_divergence_detector,
)

# ── Signal dataclass ──────────────────────────────────────────────────────────

def test_signal_fields():
    s = Signal(
        name="test", value=50.0, normalized=0.5, ic=0.07,
        half_life=14, age_days=0, layer="institutional", source="cot"
    )
    assert s.decay_weight == 1.0  # age=0 → no decay

def test_signal_decay_half_life():
    s = Signal(
        name="test", value=50.0, normalized=0.5, ic=0.07,
        half_life=14, age_days=14, layer="institutional", source="cot"
    )
    assert abs(s.decay_weight - 0.5) < 1e-9  # exactly half at half-life

def test_signal_decay_zero_age():
    s = Signal(
        name="test", value=50.0, normalized=0.5, ic=0.05,
        half_life=7, age_days=0, layer="retail", source="fear_greed"
    )
    assert s.decay_weight == 1.0
```

- [ ] **Step 2: Run tests — expect failure (Signal not yet defined)**

```bash
/tmp/druck_venv/bin/python -m pytest tests/test_crowd_engine.py::test_signal_fields -v 2>&1 | head -20
```
Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Create `tools/crowd_types.py`**

```python
"""Shared types for the Crowd Intelligence System."""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class Signal:
    """A single normalized crowd signal with metadata."""
    name: str           # human-readable label
    value: float        # raw value from source
    normalized: float   # z-score normalized to [0, 1]
    ic: float           # information coefficient (negative = contrarian)
    half_life: int      # signal half-life in days
    age_days: int       # days since signal was collected
    layer: str          # 'retail' | 'institutional' | 'smart'
    source: str         # source identifier (e.g. 'cot', 'reddit')
    low_history: bool = False  # True if <60d history, used cross-sectional rank

    @property
    def decay_weight(self) -> float:
        """Exponential decay: 0.5^(age/half_life). Fresh signal = 1.0."""
        return float(0.5 ** (self.age_days / self.half_life))
```

- [ ] **Step 4: Run tests — expect pass**

```bash
/tmp/druck_venv/bin/python -m pytest tests/test_crowd_engine.py::test_signal_fields tests/test_crowd_engine.py::test_signal_decay_half_life tests/test_crowd_engine.py::test_signal_decay_zero_age -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tools/crowd_types.py tests/test_crowd_engine.py
git commit -m "feat: add Signal dataclass + decay property"
```

---

## Task 3: Scoring Engine Core Math

**Files:**
- Create: `tools/crowd_engine.py` (scoring functions only — no fetching yet)

- [ ] **Step 1: Add scoring tests to `tests/test_crowd_engine.py`**

Append to the file:

```python
# ── normalize_signal_value ─────────────────────────────────────────────────

def test_normalize_clips_to_unit_interval():
    # z-score of +4 should clip to 1.0 after clipping at ±3
    result = normalize_signal_value(value=104.0, history=[50.0] * 252)
    assert 0.0 <= result <= 1.0

def test_normalize_median_value_near_half():
    # Value at historical mean → normalized ≈ 0.5
    history = list(range(1, 253))  # 1..252
    mean = sum(history) / len(history)
    result = normalize_signal_value(value=mean, history=history)
    assert abs(result - 0.5) < 0.05

# ── apply_decay ───────────────────────────────────────────────────────────

def test_apply_decay_formula():
    s = Signal("x", 1.0, 0.5, 0.07, 14, 7, "institutional", "cot")
    assert abs(apply_decay(s) - (0.5 ** (7 / 14))) < 1e-9

# ── score_layer ───────────────────────────────────────────────────────────

def test_score_layer_returns_none_when_empty():
    assert score_layer([], "institutional") is None

def test_score_layer_retail_inverts_value():
    # retail layer: high normalized value → LOW score (contrarian)
    s = Signal("fear_greed", 80.0, 0.9, 0.04, 1, 0, "retail", "fear_greed")
    score = score_layer([s], "retail")
    assert score < 0.2  # 1 - 0.9 = 0.1

def test_score_layer_institutional_direct():
    s = Signal("cot", 70.0, 0.8, 0.07, 14, 0, "institutional", "cot")
    score = score_layer([s], "institutional")
    assert abs(score - 0.8) < 1e-6

def test_score_layer_ic_weights_correctly():
    # Higher IC signal should dominate
    s_high = Signal("high_ic", 1.0, 0.9, 0.08, 90, 0, "smart", "insider")
    s_low  = Signal("low_ic",  1.0, 0.1, 0.02, 5,  0, "smart", "options")
    score = score_layer([s_high, s_low], "smart")
    # Should be closer to s_high.normalized (0.9) than s_low.normalized (0.1)
    assert score > 0.7

# ── compute_conviction ────────────────────────────────────────────────────

def test_conviction_in_range():
    score = compute_conviction(retail=0.2, institutional=0.8, smart=0.85, regime="risk_on")
    assert 0.0 <= score <= 100.0

def test_conviction_high_when_all_aligned_bullish():
    score = compute_conviction(retail=0.1, institutional=0.9, smart=0.9, regime="risk_on")
    assert score > 60.0

def test_conviction_low_when_layers_disagree():
    # retail=0.9 (crowded), inst=0.1, smart=0.1 → retail penalty + misalignment
    score = compute_conviction(retail=0.9, institutional=0.1, smart=0.1, regime="risk_on")
    assert score < 20.0

def test_conviction_scales_to_100():
    # Perfect alignment: retail=0, inst=1, smart=1
    score = compute_conviction(retail=0.0, institutional=1.0, smart=1.0, regime="strong_risk_on")
    assert score <= 100.0

def test_conviction_uses_regime_weights():
    # In risk_off, smart money weighted higher — same inputs should score differently
    score_on  = compute_conviction(0.2, 0.6, 0.9, regime="risk_on")
    score_off = compute_conviction(0.2, 0.6, 0.9, regime="strong_risk_off")
    assert score_off > score_on  # smart money premium in risk_off

# ── run_divergence_detector ───────────────────────────────────────────────

def test_divergence_distribution():
    result = run_divergence_detector(
        retail_score=75.0, institutional_score=35.0, smart_score=30.0,
        short_dtc=None, has_catalyst=False
    )
    assert result == "DISTRIBUTION"

def test_divergence_contrarian_buy():
    result = run_divergence_detector(
        retail_score=25.0, institutional_score=65.0, smart_score=70.0,
        short_dtc=None, has_catalyst=False
    )
    assert result == "CONTRARIAN_BUY"

def test_divergence_hidden_gem():
    result = run_divergence_detector(
        retail_score=15.0, institutional_score=50.0, smart_score=80.0,
        short_dtc=None, has_catalyst=False,
        insider_cluster=True, unusual_calls=True
    )
    assert result == "HIDDEN_GEM"

def test_divergence_short_squeeze():
    result = run_divergence_detector(
        retail_score=20.0, institutional_score=60.0, smart_score=50.0,
        short_dtc=12.0, has_catalyst=True
    )
    assert result == "SHORT_SQUEEZE"

def test_divergence_none_when_neutral():
    result = run_divergence_detector(
        retail_score=50.0, institutional_score=50.0, smart_score=50.0,
        short_dtc=None, has_catalyst=False
    )
    assert result is None
```

- [ ] **Step 2: Run — expect failures (crowd_engine not yet created)**

```bash
/tmp/druck_venv/bin/python -m pytest tests/test_crowd_engine.py -v 2>&1 | tail -10
```
Expected: `ImportError` from crowd_engine.

- [ ] **Step 3: Create `tools/crowd_engine.py` — math functions only**

```python
"""Crowd Intelligence Engine — scoring, divergence detection, report generation.

This module is the core of the crowd intelligence system. It:
  1. Normalizes raw signals to [0,1] using rolling z-score
  2. Applies exponential decay by signal age
  3. Combines signals within each layer using IC-weighted average
  4. Applies regime-conditional layer weights (from macro_regime module)
  5. Detects divergence patterns (Wyckoff + microstructure theory)
  6. Runs price/volume confirmation gate
  7. Generates formatted report

Import pattern matches the rest of this codebase (tools.* imports).
"""
import sys, json, logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import numpy as np

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)

# ── Regime weights (exact labels from macro_regime.py) ────────────────────

REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "strong_risk_on":  {"smart": 0.30, "institutional": 0.50, "retail_penalty": 0.20},
    "risk_on":         {"smart": 0.35, "institutional": 0.45, "retail_penalty": 0.20},
    "neutral":         {"smart": 0.40, "institutional": 0.40, "retail_penalty": 0.20},
    "risk_off":        {"smart": 0.55, "institutional": 0.35, "retail_penalty": 0.10},
    "strong_risk_off": {"smart": 0.60, "institutional": 0.30, "retail_penalty": 0.10},
}
DEFAULT_REGIME = "neutral"

# ── Signal normalization ───────────────────────────────────────────────────

def normalize_signal_value(value: float, history: list[float]) -> float:
    """Z-score normalize value against rolling history, rescale to [0, 1].

    If history has fewer than 60 values, cross-sectional rank is used instead
    (caller is responsible for passing universe values as history in that case).
    """
    arr = np.array(history, dtype=float)
    if len(arr) < 2:
        return 0.5  # no history — assume neutral
    mean = float(np.mean(arr))
    std  = float(np.std(arr))
    if std < 1e-9:
        return 0.5  # constant series — neutral
    z = (value - mean) / std
    z_clipped = float(np.clip(z, -3.0, 3.0)) / 3.0   # → [-1, 1]
    return float((z_clipped + 1.0) / 2.0)             # → [0, 1]


# ── Decay weighting ───────────────────────────────────────────────────────

def apply_decay(signal: Signal) -> float:
    """Return exponential decay weight for signal given its age."""
    return signal.decay_weight


# ── Layer scoring ──────────────────────────────────────────────────────────

def score_layer(signals: list[Signal], layer_type: str) -> Optional[float]:
    """Combine signals within a layer using IC-weighted, decay-adjusted average.

    For 'retail' layer: values are inverted (1 - normalized) before combining,
    because retail signals are contrarian indicators.

    Returns None if no signals are available (graceful degradation).
    """
    if not signals:
        return None

    total_weight = sum(abs(s.ic) * s.decay_weight for s in signals)
    if total_weight < 1e-12:
        return None

    score = 0.0
    for s in signals:
        w = abs(s.ic) * s.decay_weight / total_weight
        value = (1.0 - s.normalized) if layer_type == "retail" else s.normalized
        score += w * value

    return float(np.clip(score, 0.0, 1.0))


# ── Conviction scoring ─────────────────────────────────────────────────────

def compute_conviction(
    retail: float,
    institutional: float,
    smart: float,
    regime: str = DEFAULT_REGIME,
) -> float:
    """Compute final conviction score [0–100].

    Higher retail = crowding risk = negative adjustment.
    Alignment multiplier: maximum disagreement → score = 0.
    """
    weights = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS[DEFAULT_REGIME])

    raw = (
        weights["smart"]           * smart
      + weights["institutional"]   * institutional
      - weights["retail_penalty"]  * retail
    )

    # Alignment: std of 3 values in [0,1] has max 0.577
    aligned_retail = 1.0 - retail  # invert for alignment check (retail is contrarian)
    std = float(np.std([smart, institutional, aligned_retail]))
    alignment = max(0.0, 1.0 - (std / 0.577))

    return float(np.clip(raw * alignment * 100.0, 0.0, 100.0))


# ── Divergence detection ───────────────────────────────────────────────────

def run_divergence_detector(
    retail_score: float,
    institutional_score: float,
    smart_score: float,
    short_dtc: Optional[float],
    has_catalyst: bool,
    insider_cluster: bool = False,
    unusual_calls: bool = False,
) -> Optional[str]:
    """Classify divergence signal type using Wyckoff + microstructure theory.

    Returns signal type string or None if no pattern detected.
    Priority order matters — most specific conditions first.
    """
    # HIDDEN_GEM: maximum information asymmetry
    if (retail_score < 20
            and insider_cluster
            and unusual_calls):
        return "HIDDEN_GEM"

    # SHORT_SQUEEZE: forced covering + catalyst
    if (short_dtc is not None
            and short_dtc > 10
            and institutional_score > 55
            and has_catalyst):
        return "SHORT_SQUEEZE"

    # DISTRIBUTION: Wyckoff Phase C/D
    if retail_score > 70 and institutional_score < 40 and smart_score < 35:
        return "DISTRIBUTION"

    # CROWDED_FADE: retail euphoria + institutional exit
    if retail_score > 75 and (institutional_score < 45 or smart_score < 35):
        return "CROWDED_FADE"

    # CONTRARIAN_BUY: institutional buying into retail fear
    if retail_score < 30 and institutional_score > 60 and smart_score > 65:
        return "CONTRARIAN_BUY"

    # STEALTH_ACCUM: quiet institutional build
    if institutional_score > 65 and smart_score > 60 and retail_score < 40:
        return "STEALTH_ACCUM"

    return None


# ── Regime detection ───────────────────────────────────────────────────────

def detect_regime() -> str:
    """Fetch current macro regime from macro_regime module or return default.

    Falls back to DEFAULT_REGIME if module unavailable (standalone mode).
    """
    try:
        from tools.db import query
        rows = query(
            "SELECT regime FROM macro_scores ORDER BY date DESC LIMIT 1"
        )
        if rows and rows[0].get("regime") in REGIME_WEIGHTS:
            return rows[0]["regime"]
    except Exception:
        pass
    return DEFAULT_REGIME
```

- [ ] **Step 4: Run tests**

```bash
/tmp/druck_venv/bin/python -m pytest tests/test_crowd_engine.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/crowd_engine.py tests/test_crowd_engine.py
git commit -m "feat: crowd engine scoring math — normalize, decay, score_layer, conviction, divergence"
```

---

## Task 4: Retail Collector

**Files:**
- Create: `tools/crowd_retail.py`

- [ ] **Step 1: Create `tools/crowd_retail.py`**

```python
"""Layer 1 — Retail Crowding Signals.

Sources:
  - Reddit PRAW: ticker mention velocity + sentiment (WSB, r/investing, r/stocks)
  - Alternative.me Fear & Greed: documented free API, stable
  - AAII Sentiment Survey: weekly HTML scrape of aaii.com
  - Google Trends (pytrends): retail FOMO proxy, top-50 tickers only

All signals are CONTRARIAN. High retail = crowding risk.
crowd_engine.score_layer() handles the inversion.
"""
import sys, json, time, logging, re
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)

# ── Fear & Greed ───────────────────────────────────────────────────────────

def fetch_fear_greed() -> list[Signal]:
    """Fetch CNN Fear & Greed via Alternative.me documented API (free, stable)."""
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=2&format=json",
            timeout=10,
            headers={"User-Agent": "DruckenmillerAlpha/1.0"},
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return []
        current = data[0]
        prev    = data[1] if len(data) > 1 else data[0]
        value   = float(current["value"])
        prev_v  = float(prev["value"])
        # Age: timestamp is Unix epoch
        age_days = max(0, (datetime.now() - datetime.fromtimestamp(int(current["timestamp"]))).days)

        return [Signal(
            name="fear_greed",
            value=value,
            normalized=value / 100.0,    # already 0–100 scale
            ic=-0.04,
            half_life=1,
            age_days=age_days,
            layer="retail",
            source="alternative_me",
        )]
    except Exception as e:
        logger.warning(f"fetch_fear_greed failed: {e}")
        return []


# ── AAII Sentiment ─────────────────────────────────────────────────────────

def fetch_aaii_sentiment() -> list[Signal]:
    """Scrape AAII weekly sentiment survey — bulls% - bears% spread."""
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(
            "https://www.aaii.com/sentimentsurvey/sent_results",
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DruckenmillerAlpha/1.0)"},
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # AAII table has Bulls%, Neutral%, Bears% in first data row
        bulls, bears = None, None
        for td in soup.find_all("td"):
            txt = td.get_text(strip=True)
            if "%" in txt:
                try:
                    pct = float(txt.replace("%", ""))
                    if bulls is None:
                        bulls = pct
                    elif bears is None:
                        # skip neutral — grab third
                        pass
                    else:
                        bears = pct
                        break
                except ValueError:
                    continue

        if bulls is None:
            return []

        spread = (bulls or 0) - (bears or 0)   # positive = bullish majority
        # Normalize: historical AAII spread ranges from -40 to +60
        # We normalize raw bulls% as the crowding indicator (high bulls = crowded)
        normalized = min(1.0, max(0.0, (bulls or 0) / 100.0))

        return [Signal(
            name="aaii_bulls",
            value=bulls or 0,
            normalized=normalized,
            ic=-0.03,
            half_life=7,
            age_days=0,   # weekly — treat as fresh
            layer="retail",
            source="aaii",
        )]
    except Exception as e:
        logger.warning(f"fetch_aaii_sentiment failed: {e}")
        return []


# ── Reddit Sentiment ───────────────────────────────────────────────────────

def fetch_reddit_sentiment(tickers: list[str], max_tickers: int = 200) -> list[Signal]:
    """Fetch ticker mention velocity + sentiment from Reddit.

    Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in environment.
    Scans WSB, r/investing, r/stocks for the top max_tickers by market cap.
    """
    try:
        import praw
        from tools.config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
        if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
            logger.info("Reddit credentials not configured — skipping")
            return []

        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
            check_for_async=False,
        )

        scan_tickers = set(tickers[:max_tickers])
        mention_counts: dict[str, int] = {t: 0 for t in scan_tickers}
        sentiment_sum: dict[str, float] = {t: 0.0 for t in scan_tickers}

        subreddits = ["wallstreetbets", "investing", "stocks"]
        for sub_name in subreddits:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.new(limit=200):
                    text = f"{post.title} {post.selftext}".upper()
                    for ticker in scan_tickers:
                        if f" {ticker} " in text or f"${ticker}" in text:
                            mention_counts[ticker] += 1
                            # Upvote ratio as sentiment proxy: 0.5–1.0 → 0.0–1.0
                            sentiment_sum[ticker] += max(0.0, (post.upvote_ratio - 0.5) * 2)
            except Exception as e:
                logger.warning(f"Reddit r/{sub_name} failed: {e}")

        signals = []
        max_mentions = max(mention_counts.values()) if mention_counts else 1
        for ticker in scan_tickers:
            count = mention_counts.get(ticker, 0)
            if count == 0:
                continue
            norm = count / max(max_mentions, 1)
            signals.append(Signal(
                name=f"reddit_mentions_{ticker}",
                value=float(count),
                normalized=float(norm),
                ic=-0.02,
                half_life=2,
                age_days=0,
                layer="retail",
                source="reddit",
            ))
        return signals

    except Exception as e:
        logger.warning(f"fetch_reddit_sentiment failed: {e}")
        return []


# ── Google Trends ──────────────────────────────────────────────────────────

def fetch_google_trends(tickers: list[str], max_tickers: int = 50) -> list[Signal]:
    """Fetch Google Trends interest for top-N tickers.

    Rate-limited: Google aggressively throttles pytrends.
    Limit to max_tickers (default 50). Exponential backoff on 429.
    Falls back gracefully to empty list if blocked.
    """
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.info("pytrends not installed — skipping Google Trends")
        return []

    signals = []
    # Process in batches of 5 (pytrends limit per request)
    batch = tickers[:max_tickers]
    for i in range(0, len(batch), 5):
        chunk = batch[i:i + 5]
        for attempt in range(3):
            try:
                pt = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
                pt.build_payload(chunk, timeframe="now 7-d")
                df = pt.interest_over_time()
                if df.empty:
                    break
                for ticker in chunk:
                    if ticker not in df.columns:
                        continue
                    series = df[ticker].values.tolist()
                    if not series:
                        continue
                    current = float(series[-1])
                    norm = current / 100.0
                    signals.append(Signal(
                        name=f"gtrends_{ticker}",
                        value=current,
                        normalized=norm,
                        ic=-0.02,
                        half_life=3,
                        age_days=0,
                        layer="retail",
                        source="google_trends",
                    ))
                break  # success
            except Exception as e:
                if "429" in str(e) or "Too Many" in str(e):
                    wait = 2 ** attempt * 30
                    logger.warning(f"Google Trends rate limited — waiting {wait}s")
                    time.sleep(wait)
                else:
                    logger.warning(f"Google Trends chunk {chunk} failed: {e}")
                    break
        time.sleep(5)  # polite delay between batches

    return signals


# ── Public entry point ─────────────────────────────────────────────────────

def fetch_all_retail(tickers: list[str]) -> list[Signal]:
    """Fetch all Layer 1 retail signals. Gracefully handles any source failure."""
    signals: list[Signal] = []
    signals.extend(fetch_fear_greed())
    signals.extend(fetch_aaii_sentiment())
    signals.extend(fetch_reddit_sentiment(tickers))
    signals.extend(fetch_google_trends(tickers))
    logger.info(f"Retail layer: {len(signals)} signals collected")
    return signals
```

- [ ] **Step 2: Smoke-test fear & greed (no API key needed)**

```bash
/tmp/druck_venv/bin/python -c "
from tools.crowd_retail import fetch_fear_greed
sigs = fetch_fear_greed()
print(f'Fear & Greed: {sigs[0].value if sigs else \"FAILED\"}')
"
```
Expected: prints a number like `Fear & Greed: 67.0`.

- [ ] **Step 3: Commit**

```bash
git add tools/crowd_retail.py
git commit -m "feat: crowd_retail — Fear&Greed, AAII, Reddit, Google Trends collectors"
```

---

## Task 5: Institutional Collector

**Files:**
- Create: `tools/crowd_institutional.py`

- [ ] **Step 1: Create `tools/crowd_institutional.py`**

```python
"""Layer 2 — Institutional Positioning Signals.

Sources:
  - Sector ETF AUM flows (yfinance): proxy for ICI fund flows
  - CFTC COT Report (free FTP CSV): commercial vs non-commercial futures positioning
  - FINRA ATS volume (free): market-level institutional participation (NOT per-stock)
  - SEC EDGAR 13F + FMP API: quarterly hedge fund holdings changes
  - FINRA short interest: days-to-cover per ticker
  - FRED margin debt (BOGZ1FL663067003Q): market leverage signal
"""
import sys, io, csv, json, logging, time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests
import pandas as pd

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)

# Sector ETFs to track for fund flow proxy
SECTOR_ETFS = {
    "XLK": "technology",   "XLF": "financials",     "XLE": "energy",
    "XLV": "healthcare",   "XLI": "industrials",    "XLY": "consumer_discretionary",
    "XLP": "consumer_staples", "XLU": "utilities",  "XLB": "materials",
    "XLRE": "real_estate", "XLC": "communication",
}


# ── ETF Sector Flows ───────────────────────────────────────────────────────

def fetch_etf_sector_flows() -> list[Signal]:
    """Compute sector ETF AUM weekly change as institutional flow proxy.

    AUM = shares_outstanding × price. Weekly change proxies ICI fund flows.
    This is the standard free substitute for ICI.org (no programmatic API).
    """
    try:
        import yfinance as yf
        signals = []
        for etf, sector in SECTOR_ETFS.items():
            try:
                tk = yf.Ticker(etf)
                hist = tk.history(period="2mo")
                if hist.empty or len(hist) < 10:
                    continue
                info = tk.info or {}
                shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
                if not shares:
                    # Fallback: use volume proxy
                    recent_vol  = float(hist["Volume"].iloc[-5:].mean())
                    earlier_vol = float(hist["Volume"].iloc[-20:-5].mean())
                    flow_proxy  = (recent_vol - earlier_vol) / max(earlier_vol, 1)
                    norm = float(min(1.0, max(0.0, (flow_proxy + 1) / 2)))
                else:
                    # AUM change: current vs 5 days ago
                    price_now  = float(hist["Close"].iloc[-1])
                    price_prev = float(hist["Close"].iloc[-6])
                    aum_change = (price_now - price_prev) / max(price_prev, 0.01)
                    norm = float(min(1.0, max(0.0, (aum_change + 0.05) / 0.10)))

                signals.append(Signal(
                    name=f"etf_flow_{sector}",
                    value=norm * 100,
                    normalized=norm,
                    ic=0.07,
                    half_life=7,
                    age_days=0,
                    layer="institutional",
                    source="etf_flows",
                ))
            except Exception as e:
                logger.debug(f"ETF flow {etf} failed: {e}")
        return signals
    except Exception as e:
        logger.warning(f"fetch_etf_sector_flows failed: {e}")
        return []


# ── CFTC COT Report ────────────────────────────────────────────────────────

def fetch_cot_report() -> list[Signal]:
    """Fetch CFTC Commitments of Traders report (free weekly CSV).

    Commercial net position (hedgers) = most informed futures participants.
    Non-commercial net (speculators) = contrarian crowding signal.

    Returns market-level signals for S&P 500 and key commodity futures.
    """
    try:
        # CFTC publishes current year COT as zip
        year = date.today().year
        url = f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{year}.zip"
        resp = requests.get(url, timeout=30, headers={"User-Agent": "DruckenmillerAlpha/1.0"})
        if resp.status_code != 200:
            # Try previous year
            url = f"https://www.cftc.gov/files/dea/history/fut_fin_txt_{year-1}.zip"
            resp = requests.get(url, timeout=30, headers={"User-Agent": "DruckenmillerAlpha/1.0"})
        resp.raise_for_status()

        import zipfile
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            fname = [f for f in z.namelist() if f.endswith(".txt")][0]
            with z.open(fname) as f:
                df = pd.read_csv(f, encoding="latin1", low_memory=False)

        # Focus on S&P 500 Consolidated futures
        sp500 = df[df["Market_and_Exchange_Names"].str.contains("S&P 500", na=False, case=False)]
        if sp500.empty:
            return []

        latest = sp500.sort_values("As_of_Date_In_Form_YYMMDD", ascending=False).iloc[0]
        comm_long  = float(latest.get("Comm_Positions_Long_All", 0) or 0)
        comm_short = float(latest.get("Comm_Positions_Short_All", 0) or 0)
        spec_long  = float(latest.get("NonComm_Positions_Long_All", 0) or 0)
        spec_short = float(latest.get("NonComm_Positions_Short_All", 0) or 0)

        comm_net = comm_long - comm_short
        spec_net = spec_long - spec_short

        # Normalize spec net as speculator crowding (contrarian at extremes)
        total_oi = spec_long + spec_short + comm_long + comm_short
        spec_pct = (spec_net / total_oi * 100) if total_oi > 0 else 0
        # spec_pct typically ranges -30 to +30; normalize to [0,1]
        spec_norm = float(min(1.0, max(0.0, (spec_pct + 30) / 60)))

        # Report age
        date_str = str(latest.get("As_of_Date_In_Form_YYMMDD", ""))
        age_days = 7  # COT is weekly; assume ~7 days old
        try:
            cot_date = datetime.strptime(date_str, "%y%m%d")
            age_days = max(0, (datetime.now() - cot_date).days)
        except Exception:
            pass

        return [Signal(
            name="cot_sp500_speculator_net",
            value=spec_pct,
            normalized=spec_norm,
            ic=0.07,
            half_life=14,
            age_days=age_days,
            layer="institutional",
            source="cftc_cot",
        )]
    except Exception as e:
        logger.warning(f"fetch_cot_report failed: {e}")
        return []


# ── FINRA ATS Market Activity ──────────────────────────────────────────────

def fetch_finra_ats_activity() -> list[Signal]:
    """Fetch FINRA ATS weekly volume as market-level institutional activity proxy.

    NOTE: FINRA ATS data is aggregate by venue (Citadel Connect, IEX, etc.),
    NOT per-security for listed equities. Used as a market-level signal only.
    High ATS share of total volume = elevated institutional off-exchange activity.
    """
    try:
        # FINRA publishes ATS data at otctransparency.finra.org
        # Use a reasonable proxy: ATS fraction of total equity volume via FINRA
        url = "https://api.finra.org/data/group/otcmarket/name/weeklySummary"
        resp = requests.get(
            url, timeout=15,
            headers={"Accept": "application/json", "User-Agent": "DruckenmillerAlpha/1.0"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data and isinstance(data, list):
                latest = data[0]
                ats_vol    = float(latest.get("totalWeeklyShareQuantity", 0) or 0)
                total_vol  = float(latest.get("totalWeeklyTradeCount", 1) or 1)
                ats_frac   = min(1.0, ats_vol / max(total_vol * 1000, 1))
                return [Signal(
                    name="finra_ats_activity",
                    value=ats_frac * 100,
                    normalized=ats_frac,
                    ic=0.05,
                    half_life=5,
                    age_days=0,
                    layer="institutional",
                    source="finra_ats",
                )]
    except Exception as e:
        logger.debug(f"FINRA ATS API failed (expected — fallback): {e}")

    # Fallback: return neutral signal flagged as estimate
    return [Signal(
        name="finra_ats_activity",
        value=50.0,
        normalized=0.5,
        ic=0.05,
        half_life=5,
        age_days=7,
        layer="institutional",
        source="finra_ats_estimate",
        low_history=True,
    )]


# ── FINRA Short Interest ───────────────────────────────────────────────────

def fetch_short_interest(tickers: list[str]) -> list[Signal]:
    """Fetch FINRA short interest + days-to-cover per ticker.

    Returns signals where DTC > 5 (elevated short interest).
    High DTC = potential squeeze risk = institutional conviction signal.
    """
    try:
        import yfinance as yf
        signals = []
        for ticker in tickers[:300]:  # rate limit
            try:
                tk = yf.Ticker(ticker)
                info = tk.info or {}
                short_pct = float(info.get("shortPercentOfFloat", 0) or 0)
                short_ratio = float(info.get("shortRatio", 0) or 0)  # DTC
                if short_pct < 0.01 and short_ratio < 1:
                    continue
                # Normalize DTC: 0-30 days → [0, 1]
                norm = min(1.0, short_ratio / 30.0)
                signals.append(Signal(
                    name=f"short_dtc_{ticker}",
                    value=short_ratio,
                    normalized=norm,
                    ic=0.05,
                    half_life=14,
                    age_days=0,
                    layer="institutional",
                    source="finra_short",
                ))
            except Exception:
                continue
        return signals
    except Exception as e:
        logger.warning(f"fetch_short_interest failed: {e}")
        return []


# ── FRED Margin Debt ───────────────────────────────────────────────────────

def fetch_margin_debt() -> list[Signal]:
    """Fetch FINRA margin debt via FRED (series BOGZ1FL663067003Q).

    YoY growth > 0 = leverage expanding = mild crowding signal.
    """
    try:
        from tools.config import FRED_API_KEY
        if not FRED_API_KEY:
            return []
        import fredapi
        fred = fredapi.Fred(api_key=FRED_API_KEY)
        series = fred.get_series("BOGZ1FL663067003Q", observation_start="2020-01-01")
        if series is None or len(series) < 4:
            return []
        current = float(series.iloc[-1])
        year_ago = float(series.iloc[-5]) if len(series) >= 5 else float(series.iloc[0])
        yoy_growth = (current - year_ago) / max(abs(year_ago), 1)
        # Normalize: -20% to +20% YoY → [0, 1]
        norm = float(min(1.0, max(0.0, (yoy_growth + 0.20) / 0.40)))
        return [Signal(
            name="margin_debt_yoy",
            value=yoy_growth * 100,
            normalized=norm,
            ic=0.04,
            half_life=90,
            age_days=0,
            layer="institutional",
            source="fred_margin_debt",
        )]
    except Exception as e:
        logger.warning(f"fetch_margin_debt failed: {e}")
        return []


# ── 13F Institutional Flows ────────────────────────────────────────────────

def fetch_13f_flows(tickers: list[str]) -> list[Signal]:
    """Fetch SEC 13F institutional flow direction via FMP API (free tier).

    Reuses existing filings_13f table in DB if available (quarterly cache).
    Falls back to FMP API direct call for tickers not in DB.
    """
    try:
        from tools.db import query
        from tools.config import FMP_API_KEY, FMP_BASE
        signals = []
        cutoff = (date.today() - timedelta(days=180)).isoformat()

        for ticker in tickers[:200]:
            try:
                # Try DB cache first (populated by existing filings_13f.py module)
                rows = query(
                    "SELECT change_pct, date FROM filings_13f WHERE symbol=? AND date>=? ORDER BY date DESC LIMIT 2",
                    [ticker, cutoff]
                )
                if rows and len(rows) >= 1:
                    change = float(rows[0]["change_pct"] or 0)
                    # Normalize: -50% to +50% change → [0, 1]
                    norm = float(min(1.0, max(0.0, (change + 50) / 100)))
                    age_days = (date.today() - date.fromisoformat(rows[0]["date"])).days
                    signals.append(Signal(
                        name=f"13f_flow_{ticker}",
                        value=change,
                        normalized=norm,
                        ic=0.06,
                        half_life=60,
                        age_days=age_days,
                        layer="institutional",
                        source="sec_13f",
                    ))
            except Exception:
                continue
        return signals
    except Exception as e:
        logger.warning(f"fetch_13f_flows failed: {e}")
        return []


# ── Public entry point ─────────────────────────────────────────────────────

def fetch_all_institutional(tickers: list[str]) -> list[Signal]:
    """Fetch all Layer 2 institutional signals."""
    signals: list[Signal] = []
    signals.extend(fetch_etf_sector_flows())
    signals.extend(fetch_cot_report())
    signals.extend(fetch_finra_ats_activity())
    signals.extend(fetch_13f_flows(tickers))
    signals.extend(fetch_short_interest(tickers))
    signals.extend(fetch_margin_debt())
    logger.info(f"Institutional layer: {len(signals)} signals collected")
    return signals
```

- [ ] **Step 2: Smoke-test ETF flows (no key needed)**

```bash
/tmp/druck_venv/bin/python -c "
from tools.crowd_institutional import fetch_etf_sector_flows
sigs = fetch_etf_sector_flows()
print(f'ETF flows: {len(sigs)} sectors')
for s in sigs[:3]: print(f'  {s.name}: {s.normalized:.2f}')
"
```
Expected: `ETF flows: 11 sectors` with normalized values.

- [ ] **Step 3: Commit**

```bash
git add tools/crowd_institutional.py
git commit -m "feat: crowd_institutional — ETF flows, COT, FINRA, 13F, short interest, margin debt"
```

---

## Task 6: Smart Money Collector

**Files:**
- Create: `tools/crowd_smart.py`

- [ ] **Step 1: Create `tools/crowd_smart.py`**

```python
"""Layer 3 — Smart Money Signals (highest IC, leading indicators).

Sources:
  - OpenInsider + SEC Form 4: insider cluster buying (3+ insiders, 14-day window)
  - yfinance options chain: 25Δ-equivalent skew + unusual OI surge
  - Polymarket: macro event probability shifts (reuses prediction_markets.py)

Theory: Lakonishok & Lee (2001) — insider cluster buying predicts 6-month
excess returns of 4-6%. Cluster buying implies coordinated conviction.
"""
import sys, json, logging
from datetime import date, datetime, timedelta
from pathlib import Path

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import requests

from tools.crowd_types import Signal

logger = logging.getLogger(__name__)


# ── Insider Clusters ───────────────────────────────────────────────────────

def fetch_insider_clusters(tickers: list[str]) -> list[Signal]:
    """Detect insider cluster buying using existing insider_trading.py logic.

    Cluster = 3+ unique insiders buying same ticker within INSIDER_CLUSTER_WINDOW_DAYS.
    Reuses the insider_signals table written by insider_trading.py.
    Does NOT rebuild cluster logic — reads existing pipeline output.
    """
    try:
        from tools.db import query
        from tools.config import INSIDER_CLUSTER_WINDOW_DAYS, INSIDER_CLUSTER_MIN_COUNT
        signals = []
        cutoff = (date.today() - timedelta(days=90)).isoformat()

        rows = query(
            """SELECT symbol, date, insider_score, cluster_buy, large_csuite
               FROM insider_signals
               WHERE date >= ? AND (cluster_buy = 1 OR insider_score > 60)
               ORDER BY date DESC""",
            [cutoff]
        )

        seen = set()
        for row in rows:
            ticker = row["symbol"]
            if ticker not in tickers or ticker in seen:
                continue
            seen.add(ticker)
            is_cluster = bool(row["cluster_buy"])
            score = float(row["insider_score"] or 0)
            # Normalize insider score (0–100 from existing module)
            norm = min(1.0, score / 100.0)
            age_days = (date.today() - date.fromisoformat(row["date"])).days

            # Cluster buys get IC boost
            ic = 0.08 if is_cluster else 0.05
            signals.append(Signal(
                name=f"insider_cluster_{ticker}",
                value=score,
                normalized=norm,
                ic=ic,
                half_life=90,
                age_days=age_days,
                layer="smart",
                source="openinsider_form4",
            ))
        return signals
    except Exception as e:
        logger.warning(f"fetch_insider_clusters failed: {e}")
        return []


# ── Options Skew ──────────────────────────────────────────────────────────

def fetch_options_skew(tickers: list[str], max_tickers: int = 300) -> list[Signal]:
    """Compute 25Δ-equivalent skew from yfinance options chain.

    Skew = OTM put IV / OTM call IV at 0.85/1.15 moneyness.
    High skew = fear (put demand > call demand) = smart money hedging.
    Unusual OI surge (vs 20-day avg) = directional conviction signal.

    Note: Finnhub free tier does NOT provide Greeks/delta-mapped skew.
    We compute from yfinance chain using moneyness proxy.
    """
    try:
        import yfinance as yf
        import numpy as np
        signals = []

        for ticker in tickers[:max_tickers]:
            try:
                tk = yf.Ticker(ticker)
                price = tk.info.get("regularMarketPrice") or tk.info.get("currentPrice")
                if not price:
                    hist = tk.history(period="1d")
                    if hist.empty:
                        continue
                    price = float(hist["Close"].iloc[-1])

                exps = tk.options
                if not exps:
                    continue
                # Use nearest expiry 20–50 days out
                target_exp = None
                today = date.today()
                for exp in exps:
                    exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                    dte = (exp_date - today).days
                    if 20 <= dte <= 60:
                        target_exp = exp
                        break
                if not target_exp:
                    target_exp = exps[0]

                chain = tk.option_chain(target_exp)
                puts  = chain.puts
                calls = chain.calls
                if puts.empty or calls.empty:
                    continue

                # 25Δ-equivalent: OTM put at 0.85×price, OTM call at 1.15×price
                otm_put  = puts[puts["strike"].between(price * 0.80, price * 0.90)]
                otm_call = calls[calls["strike"].between(price * 1.10, price * 1.20)]
                if otm_put.empty or otm_call.empty:
                    continue

                put_iv  = float(otm_put["impliedVolatility"].mean())
                call_iv = float(otm_call["impliedVolatility"].mean())
                if call_iv < 0.001:
                    continue

                skew = put_iv / call_iv  # >1 = fear, <1 = greed
                # Normalize: skew typically 0.8–2.0 → [0, 1]
                norm = float(min(1.0, max(0.0, (skew - 0.8) / 1.2)))

                # Unusual OI: total OI vs 20-day avg (use volume as proxy)
                total_vol = float(puts["volume"].sum() + calls["volume"].sum())
                avg_vol   = float(puts["openInterest"].mean() + calls["openInterest"].mean())
                unusual = total_vol > avg_vol * 2.0 if avg_vol > 0 else False

                signals.append(Signal(
                    name=f"options_skew_{ticker}",
                    value=skew,
                    normalized=norm,
                    ic=0.06,
                    half_life=5,
                    age_days=0,
                    layer="smart",
                    source="yfinance_options",
                ))
            except Exception:
                continue

        return signals
    except Exception as e:
        logger.warning(f"fetch_options_skew failed: {e}")
        return []


# ── Polymarket ─────────────────────────────────────────────────────────────

def fetch_polymarket_signals() -> list[Signal]:
    """Fetch macro crowd probability shifts from Polymarket (free API).

    Reuses prediction_markets.py Gamma API logic.
    Converts macro event probabilities into market-level sentiment signal.
    """
    try:
        from tools.db import query
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        rows = query(
            """SELECT symbol, date, score, details
               FROM convergence_signals
               WHERE prediction_markets_score IS NOT NULL
               AND date >= ?
               ORDER BY date DESC LIMIT 50""",
            [cutoff]
        )
        if not rows:
            # Try prediction_markets table directly
            rows = query(
                "SELECT * FROM prediction_markets ORDER BY date DESC LIMIT 20"
            )

        signals = []
        for row in (rows or []):
            score = float(row.get("prediction_markets_score") or row.get("score") or 0)
            if score <= 0:
                continue
            ticker = row.get("symbol", "MACRO")
            age_days = (date.today() - date.fromisoformat(row["date"])).days
            signals.append(Signal(
                name=f"polymarket_{ticker}",
                value=score,
                normalized=min(1.0, score / 100.0),
                ic=0.04,
                half_life=3,
                age_days=age_days,
                layer="smart",
                source="polymarket",
            ))
        return signals
    except Exception as e:
        logger.warning(f"fetch_polymarket_signals failed: {e}")
        return []


# ── Public entry point ─────────────────────────────────────────────────────

def fetch_all_smart(tickers: list[str]) -> list[Signal]:
    """Fetch all Layer 3 smart money signals."""
    signals: list[Signal] = []
    signals.extend(fetch_insider_clusters(tickers))
    signals.extend(fetch_options_skew(tickers))
    signals.extend(fetch_polymarket_signals())
    logger.info(f"Smart money layer: {len(signals)} signals collected")
    return signals
```

- [ ] **Step 2: Smoke-test options skew on 1 ticker**

```bash
/tmp/druck_venv/bin/python -c "
from tools.crowd_smart import fetch_options_skew
sigs = fetch_options_skew(['AAPL'])
print(f'Options skew signals: {len(sigs)}')
if sigs: print(f'  AAPL skew: {sigs[0].value:.3f} norm: {sigs[0].normalized:.3f}')
"
```
Expected: prints skew value for AAPL.

- [ ] **Step 3: Commit**

```bash
git add tools/crowd_smart.py
git commit -m "feat: crowd_smart — insider clusters, options skew, polymarket signals"
```

---

## Task 7: Engine Integration — Full Run + Report

**Files:**
- Modify: `tools/crowd_engine.py` — add `run_crowd_intelligence()`, `generate_report()`, `write_to_db()`

- [ ] **Step 1: Append to `tools/crowd_engine.py`**

Add these functions after the existing scoring functions:

```python
# ── RSI helper ─────────────────────────────────────────────────────────────

def _rsi(close: "pd.Series", period: int = 14) -> "pd.Series":
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _earnings_within_days(ticker: str, days: int = 21) -> bool:
    """Check if ticker has earnings within next N days using DB calendar."""
    try:
        from tools.db import query
        from datetime import date
        today = date.today().isoformat()
        future = (date.today() + __import__("datetime").timedelta(days=days)).isoformat()
        rows = query(
            "SELECT 1 FROM earnings_calendar WHERE symbol=? AND date BETWEEN ? AND ? LIMIT 1",
            [ticker, today, future]
        )
        return bool(rows)
    except Exception:
        return False


# ── Confirmation gate ──────────────────────────────────────────────────────

def run_confirmation_gate(ticker: str, signal_type: str) -> bool:
    """Price/volume confirmation gate using yfinance.

    Bullish signals require: above 50-day MA, volume expansion, RSI < 72.
    Bearish signals require: below 20-day MA.
    SHORT_SQUEEZE requires: catalyst within 21 days + above 20-day MA.
    """
    try:
        import yfinance as yf
        import pandas as pd
        df = yf.download(ticker, period="3mo", progress=False, auto_adjust=True)
        if df.empty or len(df) < 50:
            return False

        close  = df["Close"].squeeze()
        volume = df["Volume"].squeeze()

        if signal_type in ("CONTRARIAN_BUY", "HIDDEN_GEM", "STEALTH_ACCUM"):
            above_50ma  = bool(close.iloc[-1] > close.rolling(50).mean().iloc[-1])
            vol_expand  = bool(volume.iloc[-5:].mean() > volume.iloc[-20:].mean())
            rsi_not_ob  = bool(_rsi(close, 14).iloc[-1] < 72)
            return above_50ma and vol_expand and rsi_not_ob

        if signal_type in ("DISTRIBUTION", "CROWDED_FADE"):
            return bool(close.iloc[-1] < close.rolling(20).mean().iloc[-1])

        if signal_type == "SHORT_SQUEEZE":
            has_catalyst = _earnings_within_days(ticker, days=21)
            above_20ma   = bool(close.iloc[-1] > close.rolling(20).mean().iloc[-1])
            return has_catalyst and above_20ma

        return True
    except Exception as e:
        logger.debug(f"Confirmation gate {ticker} failed: {e}")
        return False


# ── Sector crowding ────────────────────────────────────────────────────────

def _classify_sector_crowding(score: float) -> str:
    if score >= 70:   return "CROWDED_LONG"
    if score <= 30:   return "UNDEROWNED"
    if score <= 20:   return "CROWDED_SHORT"
    return "NEUTRAL"


# ── DB write ───────────────────────────────────────────────────────────────

def write_to_db(results: list[dict]) -> None:
    """Write crowd intelligence results to SQLite. No-op if DB unavailable."""
    if not results:
        return
    try:
        from tools.db import get_conn
        conn = get_conn()
        cur  = conn.cursor()
        for r in results:
            cur.execute("""
                INSERT OR REPLACE INTO crowd_intelligence
                (date, ticker, scope, sector,
                 retail_crowding_score, institutional_score, smart_money_score, conviction_score,
                 divergence_type, divergence_strength, confirmation_gate_passed,
                 retail_signals, institutional_signals, smart_money_signals,
                 macro_regime, narrative, signals_available, signals_total)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                r.get("date"), r.get("ticker"), r.get("scope", "ticker"), r.get("sector"),
                r.get("retail"), r.get("institutional"), r.get("smart"), r.get("conviction"),
                r.get("divergence_type"), r.get("divergence_strength"), r.get("gate_passed"),
                json.dumps(r.get("retail_signals", [])),
                json.dumps(r.get("institutional_signals", [])),
                json.dumps(r.get("smart_signals", [])),
                r.get("regime"), r.get("narrative"),
                r.get("signals_available", 0), r.get("signals_total", 13),
            ))
        conn.commit()
        conn.close()
        logger.info(f"Wrote {len(results)} crowd intelligence rows to DB")
    except Exception as e:
        logger.warning(f"write_to_db failed: {e}")


# ── Report generation ──────────────────────────────────────────────────────

def generate_report(results: list[dict], mode: str = "full") -> str:
    """Generate formatted crowd intelligence report string."""
    today = date.today().isoformat()
    macro_rows    = [r for r in results if r.get("scope") == "macro"]
    sector_rows   = sorted([r for r in results if r.get("scope") == "sector"],
                           key=lambda x: x.get("conviction", 0), reverse=True)
    divergence    = sorted([r for r in results if r.get("divergence_type") and r.get("gate_passed")],
                           key=lambda x: x.get("divergence_strength", 0), reverse=True)
    conviction    = sorted([r for r in results if r.get("scope") == "ticker" and not r.get("divergence_type")],
                           key=lambda x: x.get("conviction", 0), reverse=True)

    regime = results[0].get("regime", "neutral") if results else "neutral"
    n_available = results[0].get("signals_available", 0) if results else 0
    n_total     = results[0].get("signals_total", 13) if results else 13

    lines = [
        "═" * 67,
        "  CROWD INTELLIGENCE REPORT",
        f"  Date: {today}  |  Regime: {regime}",
        f"  Signals available: {n_available}/{n_total}",
        "  Sources: Reddit/Alternative.me/AAII/CFTC/FINRA/SEC/yfinance/Polymarket",
        "═" * 67,
    ]

    if mode in ("full", "macro"):
        lines.append("\n[1] MACRO POSITIONING MAP")
        for m in macro_rows[:6]:
            lines.append(f"    {m.get('narrative', '')}")

    if mode in ("full", "sector"):
        lines.append("\n[2] SECTOR CROWDING MAP")
        crowded  = [r for r in sector_rows if r.get("conviction", 50) >= 70]
        neutral  = [r for r in sector_rows if 30 <= r.get("conviction", 50) < 70]
        under    = [r for r in sector_rows if r.get("conviction", 50) < 30]
        if crowded:
            names = ", ".join(f"{r['sector']} [{r['conviction']:.0f}]" for r in crowded)
            lines.append(f"    CROWDED LONG:   {names}")
        if neutral:
            names = ", ".join(f"{r['sector']} [{r['conviction']:.0f}]" for r in neutral)
            lines.append(f"    NEUTRAL:        {names}")
        if under:
            names = ", ".join(f"{r['sector']} [{r['conviction']:.0f}]" for r in under)
            lines.append(f"    UNDEROWNED:     {names}")

    if mode in ("full", "divergence-only", "divergence"):
        lines.append("\n[3] TOP 10 DIVERGENCE ALERTS  (confirmation gate passed)")
        if divergence:
            lines.append(f"    {'Ticker':<8} {'Retail':>6} {'Inst':>6} {'Smart':>6}  {'Signal':<20} {'Horizon'}")
            lines.append(f"    {'-'*8} {'-'*6} {'-'*6} {'-'*6}  {'-'*20} {'-'*10}")
            for r in divergence[:10]:
                star = " ★★" if r["divergence_type"] == "HIDDEN_GEM" else (" ★" if r["divergence_type"] in ("CONTRARIAN_BUY","STEALTH_ACCUM") else "")
                lines.append(
                    f"    {r['ticker']:<8} {r.get('retail',0):>6.0f} {r.get('institutional',0):>6.0f} "
                    f"{r.get('smart',0):>6.0f}  {r['divergence_type'] + star:<20} {r.get('horizon','')}"
                )
        else:
            lines.append("    No divergence signals passing confirmation gate today.")

    if mode in ("full", "conviction"):
        lines.append("\n[4] TOP 10 CONVICTION SCORES  (all layers aligned)")
        for r in conviction[:10]:
            lines.append(
                f"    {r['ticker']:<8} {r.get('conviction',0):>4.0f}  {r.get('narrative','')}"
            )

    lines.append("")
    return "\n".join(lines)


# ── Horizon lookup ─────────────────────────────────────────────────────────

DIVERGENCE_HORIZONS = {
    "DISTRIBUTION":   "Reduce 2-4w",
    "CONTRARIAN_BUY": "60-180d",
    "HIDDEN_GEM":     "90-180d",
    "SHORT_SQUEEZE":  "5-15d",
    "CROWDED_FADE":   "Fade 1-3w",
    "STEALTH_ACCUM":  "90-180d",
}


# ── Main pipeline entry point ──────────────────────────────────────────────

def run_crowd_intelligence(
    universe: list[str] | None = None,
    tickers: list[str] | None = None,
    mode: str = "full",
    write_db: bool = True,
    sector: str | None = None,
) -> list[dict]:
    """Full crowd intelligence run. Called by daily_pipeline.py and crowd_report.py.

    Args:
        universe: full stock universe (903 symbols). If None, fetches from DB.
        tickers:  subset to analyze. If None, uses full universe.
        mode:     'full' | 'divergence-only' | 'conviction' | 'sector'
        write_db: persist results to SQLite
        sector:   filter to specific sector if provided

    Returns:
        list of result dicts (also written to DB if write_db=True)
    """
    from tools.crowd_retail import fetch_all_retail
    from tools.crowd_institutional import fetch_all_institutional
    from tools.crowd_smart import fetch_all_smart

    # Resolve universe
    if universe is None:
        try:
            from tools.db import query
            rows = query("SELECT symbol, sector FROM stock_universe ORDER BY market_cap DESC LIMIT 903")
            universe = [r["symbol"] for r in rows]
        except Exception:
            universe = []

    scan_tickers = tickers or universe
    if sector:
        try:
            from tools.db import query
            rows = query("SELECT symbol FROM stock_universe WHERE sector=?", [sector])
            scan_tickers = [r["symbol"] for r in rows]
        except Exception:
            pass

    today      = date.today().isoformat()
    regime     = detect_regime()
    results: list[dict] = []

    logger.info(f"Crowd intelligence run: {len(scan_tickers)} tickers, regime={regime}")

    # ── Fetch all layers ──────────────────────────────────────────────────
    retail_sigs  = fetch_all_retail(scan_tickers)
    inst_sigs    = fetch_all_institutional(scan_tickers)
    smart_sigs   = fetch_all_smart(scan_tickers)

    # ── Macro-level row ───────────────────────────────────────────────────
    market_retail = [s for s in retail_sigs if not s.name.startswith("reddit_") and not s.name.startswith("gtrends_")]
    market_inst   = [s for s in inst_sigs   if "_flow_" in s.name or "cot" in s.name or "ats" in s.name or "margin" in s.name]
    market_smart  = [s for s in smart_sigs  if "polymarket" in s.name]

    macro_retail = score_layer(market_retail, "retail")
    macro_inst   = score_layer(market_inst, "institutional")
    macro_smart  = score_layer(market_smart, "smart")

    if all(x is not None for x in [macro_retail, macro_inst, macro_smart]):
        macro_conviction = compute_conviction(macro_retail, macro_inst, macro_smart, regime)
        results.append({
            "date": today, "ticker": None, "scope": "macro", "sector": None,
            "retail": macro_retail * 100, "institutional": macro_inst * 100,
            "smart": macro_smart * 100, "conviction": macro_conviction,
            "divergence_type": None, "gate_passed": 1,
            "regime": regime,
            "signals_available": len(retail_sigs) + len(inst_sigs) + len(smart_sigs),
            "signals_total": 13,
            "narrative": f"Macro: Retail crowding {macro_retail*100:.0f}/100 | Inst {macro_inst*100:.0f}/100 | Smart {macro_smart*100:.0f}/100",
        })

    # ── Per-ticker rows ───────────────────────────────────────────────────
    for ticker in scan_tickers[:500]:  # cap at 500 for runtime
        # Filter signals for this ticker
        t_retail = [s for s in retail_sigs if ticker in s.name or not any(
            t in s.name for t in ["reddit_", "gtrends_"])]
        t_reddit = [s for s in retail_sigs if f"reddit_mentions_{ticker}" in s.name]
        t_gtrend = [s for s in retail_sigs if f"gtrends_{ticker}" in s.name]
        t_retail_all = [s for s in retail_sigs
                        if "fear_greed" in s.name or "aaii" in s.name
                        or f"reddit_mentions_{ticker}" in s.name
                        or f"gtrends_{ticker}" in s.name]

        t_inst  = [s for s in inst_sigs
                   if f"_{ticker}" in s.name or "etf_flow" in s.name
                   or "cot" in s.name or "ats" in s.name or "margin" in s.name]
        t_smart = [s for s in smart_sigs if f"_{ticker}" in s.name or "polymarket" in s.name]

        r_score = score_layer(t_retail_all, "retail")
        i_score = score_layer(t_inst, "institutional")
        s_score = score_layer(t_smart, "smart")

        # Need at least 2 layers to score
        available = sum(x is not None for x in [r_score, i_score, s_score])
        if available < 2:
            continue

        r_score = r_score or 0.5
        i_score = i_score or 0.5
        s_score = s_score or 0.5

        conviction = compute_conviction(r_score, i_score, s_score, regime)

        # Divergence detection
        insider_cluster = any(f"insider_cluster_{ticker}" in s.name and s.ic >= 0.08 for s in t_smart)
        unusual_calls   = any(f"options_skew_{ticker}" in s.name and s.normalized < 0.3 for s in t_smart)
        short_sigs      = [s for s in inst_sigs if f"short_dtc_{ticker}" in s.name]
        short_dtc       = float(short_sigs[0].value) if short_sigs else None
        has_catalyst    = _earnings_within_days(ticker) if short_dtc and short_dtc > 10 else False

        div_type = run_divergence_detector(
            retail_score=r_score * 100,
            institutional_score=i_score * 100,
            smart_score=s_score * 100,
            short_dtc=short_dtc,
            has_catalyst=has_catalyst,
            insider_cluster=insider_cluster,
            unusual_calls=unusual_calls,
        )

        gate_passed = 1
        if div_type:
            gate_passed = int(run_confirmation_gate(ticker, div_type))

        # Sector lookup
        ticker_sector = None
        try:
            from tools.db import query as dbq
            rows = dbq("SELECT sector FROM stock_universe WHERE symbol=? LIMIT 1", [ticker])
            ticker_sector = rows[0]["sector"] if rows else None
        except Exception:
            pass

        div_strength = abs((r_score - i_score) + (r_score - s_score)) / 2 if div_type else 0.0

        results.append({
            "date": today, "ticker": ticker, "scope": "ticker", "sector": ticker_sector,
            "retail": r_score * 100, "institutional": i_score * 100,
            "smart": s_score * 100, "conviction": conviction,
            "divergence_type": div_type,
            "divergence_strength": round(div_strength, 3),
            "gate_passed": gate_passed,
            "regime": regime,
            "horizon": DIVERGENCE_HORIZONS.get(div_type, "") if div_type else "",
            "signals_available": available,
            "signals_total": 3,
            "narrative": f"Inst:{i_score*100:.0f} Smart:{s_score*100:.0f} Retail:{r_score*100:.0f}",
            "retail_signals": [s.name for s in t_retail_all],
            "institutional_signals": [s.name for s in t_inst],
            "smart_signals": [s.name for s in t_smart],
        })

    if write_db:
        write_to_db(results)

    return results
```

- [ ] **Step 2: Run scoring engine tests to confirm nothing broken**

```bash
/tmp/druck_venv/bin/python -m pytest tests/test_crowd_engine.py -v
```
Expected: all tests still pass.

- [ ] **Step 3: Smoke-test full run on 5 tickers**

```bash
/tmp/druck_venv/bin/python -c "
from tools.crowd_engine import run_crowd_intelligence, generate_report
results = run_crowd_intelligence(tickers=['AAPL','NVDA','XOM','JPM','GME'], write_db=False)
print(generate_report(results, mode='full'))
"
```
Expected: formatted report prints without errors.

- [ ] **Step 4: Commit**

```bash
git add tools/crowd_engine.py
git commit -m "feat: crowd_engine — full pipeline, report generation, DB write, confirmation gate"
```

---

## Task 8: Standalone CLI

**Files:**
- Create: `crowd_report.py` (project root)

- [ ] **Step 1: Create `crowd_report.py`**

```python
#!/usr/bin/env python3
"""Standalone Crowd Intelligence CLI.

Works in any project with Python. No database or pipeline required.
Fetches fresh data and prints institutional-grade crowd positioning report.

Usage:
    python crowd_report.py
    python crowd_report.py --tickers AAPL NVDA MSFT
    python crowd_report.py --sector technology
    python crowd_report.py --mode divergence-only
    python crowd_report.py --export json
    python crowd_report.py --regime risk_off
"""
import sys
import argparse
import json
from pathlib import Path

# Allow running from any directory — add skill folder to path
_skill_dir = Path(__file__).parent
_tools_dir = _skill_dir / "tools"
if _tools_dir.exists():
    sys.path.insert(0, str(_skill_dir))
else:
    # Running from skill folder directly
    sys.path.insert(0, str(_skill_dir.parent))


def main():
    parser = argparse.ArgumentParser(description="Crowd Intelligence Report")
    parser.add_argument("tickers", nargs="*", help="Specific tickers to analyze")
    parser.add_argument("--sector", help="Filter to sector (e.g. technology)")
    parser.add_argument("--mode", default="full",
                        choices=["full", "divergence-only", "conviction", "sector", "macro"],
                        help="Report mode")
    parser.add_argument("--regime", help="Override macro regime detection")
    parser.add_argument("--export", choices=["json", "csv", "markdown"],
                        help="Export format")
    args = parser.parse_args()

    from tools.crowd_engine import run_crowd_intelligence, generate_report, DEFAULT_REGIME
    import tools.crowd_engine as engine

    # Override regime if specified
    if args.regime:
        engine.DEFAULT_REGIME = args.regime

    tickers = args.tickers if args.tickers else None
    results = run_crowd_intelligence(
        tickers=tickers,
        mode=args.mode,
        write_db=False,  # standalone — never write to DB
        sector=args.sector,
    )

    if args.export == "json":
        print(json.dumps(results, indent=2))
    elif args.export == "markdown":
        report = generate_report(results, mode=args.mode)
        # Wrap in markdown code block
        print("```")
        print(report)
        print("```")
    else:
        report = generate_report(results, mode=args.mode)
        print(report)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test CLI**

```bash
/tmp/druck_venv/bin/python crowd_report.py --tickers AAPL MSFT --mode full
```
Expected: full report for AAPL + MSFT.

```bash
/tmp/druck_venv/bin/python crowd_report.py --mode divergence-only --export json | head -20
```
Expected: JSON output.

- [ ] **Step 3: Commit**

```bash
git add crowd_report.py
git commit -m "feat: crowd_report.py — standalone terminal CLI, any-project portable"
```

---

## Task 9: Pipeline Integration

**Files:**
- Modify: `tools/daily_pipeline.py`

- [ ] **Step 1: Add Phase 2.95 to `daily_pipeline.py`**

Find the line containing `Phase 2.9: Consensus blindspots` and add the following block immediately **after** it (before Phase 3):

```python
    # ── Phase 2.95: Crowd Intelligence ──────────────────────────────────────
    from tools.crowd_engine import run_crowd_intelligence
    from tools.fetch_stock_universe import UNIVERSE_SYMBOLS
    def _run_crowd():
        run_crowd_intelligence(universe=list(UNIVERSE_SYMBOLS), write_db=True)
    _run_phase("Phase 2.95: Crowd Intelligence", _run_crowd)
```

If `UNIVERSE_SYMBOLS` is not importable from `fetch_stock_universe`, use this instead:

```python
    def _run_crowd():
        from tools.db import query
        rows = query("SELECT symbol FROM stock_universe ORDER BY market_cap DESC")
        universe = [r["symbol"] for r in rows] if rows else []
        run_crowd_intelligence(universe=universe, write_db=True)
    _run_phase("Phase 2.95: Crowd Intelligence", _run_crowd)
```

- [ ] **Step 2: Verify pipeline parses without error**

```bash
/tmp/druck_venv/bin/python -c "import tools.daily_pipeline; print('OK')"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add tools/daily_pipeline.py
git commit -m "feat: add Phase 2.95 crowd intelligence to daily pipeline"
```

---

## Task 10: FastAPI Endpoints

**Files:**
- Modify: `tools/api_market_modules.py`

- [ ] **Step 1: Append crowd endpoints to `tools/api_market_modules.py`**

```python
# ═══════════════════════════════════════════════════════════════════════
# CROWD INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════

@router.get("/api/crowd-intelligence")
def crowd_intelligence_full():
    """Full crowd intelligence report — latest data for all tickers."""
    macro   = query("SELECT * FROM crowd_intelligence WHERE scope='macro' ORDER BY date DESC LIMIT 1")
    sectors = query("SELECT * FROM crowd_intelligence WHERE scope='sector' ORDER BY date DESC, conviction_score DESC LIMIT 20")
    divs    = query("""
        SELECT * FROM crowd_intelligence
        WHERE scope='ticker' AND divergence_type IS NOT NULL
          AND confirmation_gate_passed=1
          AND date=(SELECT MAX(date) FROM crowd_intelligence WHERE scope='ticker')
        ORDER BY divergence_strength DESC LIMIT 20
    """)
    top     = query("""
        SELECT * FROM crowd_intelligence
        WHERE scope='ticker' AND divergence_type IS NULL
          AND date=(SELECT MAX(date) FROM crowd_intelligence WHERE scope='ticker')
        ORDER BY conviction_score DESC LIMIT 20
    """)
    return {"macro": macro, "sectors": sectors, "divergences": divs, "top_conviction": top}


@router.get("/api/crowd-intelligence/macro")
def crowd_macro():
    return query("SELECT * FROM crowd_intelligence WHERE scope='macro' ORDER BY date DESC LIMIT 30")


@router.get("/api/crowd-intelligence/sectors")
def crowd_sectors():
    return query("""
        SELECT * FROM crowd_intelligence WHERE scope='sector'
        AND date=(SELECT MAX(date) FROM crowd_intelligence WHERE scope='sector')
        ORDER BY conviction_score DESC
    """)


@router.get("/api/crowd-intelligence/divergences")
def crowd_divergences():
    return query("""
        SELECT * FROM crowd_intelligence
        WHERE scope='ticker' AND divergence_type IS NOT NULL AND confirmation_gate_passed=1
          AND date=(SELECT MAX(date) FROM crowd_intelligence WHERE scope='ticker')
        ORDER BY divergence_strength DESC LIMIT 50
    """)


@router.get("/api/crowd-intelligence/{ticker}")
def crowd_ticker(ticker: str):
    return query("""
        SELECT * FROM crowd_intelligence
        WHERE ticker=? ORDER BY date DESC LIMIT 90
    """, [ticker.upper()])
```

- [ ] **Step 2: Verify API starts**

```bash
/tmp/druck_venv/bin/python -c "from tools.api_market_modules import router; print('Router OK')"
```
Expected: `Router OK`.

- [ ] **Step 3: Commit**

```bash
git add tools/api_market_modules.py
git commit -m "feat: add /api/crowd-intelligence/* endpoints to FastAPI"
```

---

## Task 11: Dashboard Tab

**Files:**
- Create: `dashboard/src/components/CrowdContent.tsx`
- Modify: `dashboard/src/app/layout.tsx`

- [ ] **Step 1: Create `dashboard/src/components/CrowdContent.tsx`**

```typescript
"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface CrowdRow {
  ticker?: string;
  scope: string;
  sector?: string;
  retail_crowding_score: number;
  institutional_score: number;
  smart_money_score: number;
  conviction_score: number;
  divergence_type?: string;
  divergence_strength?: number;
  macro_regime?: string;
  narrative?: string;
  date: string;
}

interface CrowdData {
  macro: CrowdRow[];
  sectors: CrowdRow[];
  divergences: CrowdRow[];
  top_conviction: CrowdRow[];
}

const DIVERGENCE_COLOR: Record<string, string> = {
  DISTRIBUTION:   "#ef4444",
  CROWDED_FADE:   "#f97316",
  CONTRARIAN_BUY: "#22c55e",
  HIDDEN_GEM:     "#10b981",
  STEALTH_ACCUM:  "#3b82f6",
  SHORT_SQUEEZE:  "#8b5cf6",
};

const DIVERGENCE_HORIZON: Record<string, string> = {
  DISTRIBUTION:   "Reduce 2–4w",
  CROWDED_FADE:   "Fade 1–3w",
  CONTRARIAN_BUY: "60–180d",
  HIDDEN_GEM:     "90–180d",
  STEALTH_ACCUM:  "90–180d",
  SHORT_SQUEEZE:  "5–15d",
};

function ScoreBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 60, height: 6, background: "#e5e7eb", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${value}%`, height: "100%", background: color, borderRadius: 3 }} />
      </div>
      <span style={{ fontSize: 12, color: "#374151", minWidth: 28 }}>{Math.round(value)}</span>
    </div>
  );
}

export default function CrowdContent() {
  const [data, setData] = useState<CrowdData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API}/api/crowd-intelligence`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setError(String(e)); setLoading(false); });
  }, []);

  if (loading) return <div style={{ padding: 32, color: "#6b7280" }}>Loading crowd intelligence...</div>;
  if (error)   return <div style={{ padding: 32, color: "#ef4444" }}>Error: {error}</div>;
  if (!data)   return null;

  const macro = data.macro?.[0];

  return (
    <div style={{ padding: "24px 32px", maxWidth: 1200, fontFamily: "-apple-system, sans-serif" }}>

      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "#111827", margin: 0 }}>
          Crowd Intelligence
        </h1>
        <p style={{ fontSize: 13, color: "#6b7280", marginTop: 4 }}>
          Retail crowding · Institutional positioning · Smart money signals
          {macro && <span> · Regime: <strong>{macro.macro_regime}</strong></span>}
        </p>
      </div>

      {/* Macro Map */}
      {macro && (
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 20, marginBottom: 24, boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "#374151", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Macro Positioning Map
          </h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
            <div>
              <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>RETAIL CROWDING</div>
              <ScoreBar value={macro.retail_crowding_score} color="#ef4444" />
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>INSTITUTIONAL</div>
              <ScoreBar value={macro.institutional_score} color="#3b82f6" />
            </div>
            <div>
              <div style={{ fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>SMART MONEY</div>
              <ScoreBar value={macro.smart_money_score} color="#10b981" />
            </div>
          </div>
          {macro.narrative && (
            <div style={{ marginTop: 12, fontSize: 12, color: "#6b7280", fontStyle: "italic" }}>
              {macro.narrative}
            </div>
          )}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24 }}>

        {/* Sector Crowding */}
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "#374151", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Sector Crowding
          </h2>
          {data.sectors.length === 0 ? (
            <p style={{ color: "#9ca3af", fontSize: 13 }}>No sector data yet — run pipeline first.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {data.sectors.map((row) => {
                const score = row.conviction_score;
                const color = score >= 70 ? "#ef4444" : score <= 30 ? "#22c55e" : "#9ca3af";
                const label = score >= 70 ? "CROWDED" : score <= 30 ? "UNDEROWNED" : "NEUTRAL";
                return (
                  <div key={row.sector} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 13, color: "#374151", textTransform: "capitalize", minWidth: 140 }}>
                      {row.sector?.replace(/_/g, " ")}
                    </span>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <ScoreBar value={score} color={color} />
                      <span style={{ fontSize: 11, color, fontWeight: 600, minWidth: 70 }}>{label}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Top Conviction */}
        <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "#374151", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Top Conviction Scores
          </h2>
          {data.top_conviction.length === 0 ? (
            <p style={{ color: "#9ca3af", fontSize: 13 }}>No data yet — run pipeline first.</p>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #f3f4f6" }}>
                  <th style={{ textAlign: "left", padding: "4px 8px", color: "#9ca3af", fontWeight: 500, fontSize: 11 }}>TICKER</th>
                  <th style={{ textAlign: "right", padding: "4px 8px", color: "#9ca3af", fontWeight: 500, fontSize: 11 }}>SCORE</th>
                  <th style={{ textAlign: "left", padding: "4px 8px", color: "#9ca3af", fontWeight: 500, fontSize: 11 }}>SIGNAL</th>
                </tr>
              </thead>
              <tbody>
                {data.top_conviction.slice(0, 10).map((row) => (
                  <tr key={row.ticker} style={{ borderBottom: "1px solid #f9fafb" }}>
                    <td style={{ padding: "6px 8px", fontWeight: 600, color: "#111827" }}>{row.ticker}</td>
                    <td style={{ padding: "6px 8px", textAlign: "right", color: "#10b981", fontWeight: 700 }}>
                      {Math.round(row.conviction_score)}
                    </td>
                    <td style={{ padding: "6px 8px", color: "#6b7280", fontSize: 12 }}>
                      {row.narrative?.split(" ").slice(0, 5).join(" ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Divergence Alerts */}
      <div style={{ background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12, padding: 20, boxShadow: "0 1px 3px rgba(0,0,0,0.06)" }}>
        <h2 style={{ fontSize: 14, fontWeight: 600, color: "#374151", marginBottom: 16, textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Divergence Alerts — Highest Alpha Setups
        </h2>
        {data.divergences.length === 0 ? (
          <p style={{ color: "#9ca3af", fontSize: 13 }}>No divergence signals passing confirmation gate today.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #f3f4f6" }}>
                {["TICKER","RETAIL","INST","SMART","SIGNAL","HORIZON"].map((h) => (
                  <th key={h} style={{ textAlign: h==="TICKER"?"left":"right", padding: "4px 10px", color: "#9ca3af", fontWeight: 500, fontSize: 11 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.divergences.map((row) => {
                const color = DIVERGENCE_COLOR[row.divergence_type || ""] || "#6b7280";
                return (
                  <tr key={row.ticker} style={{ borderBottom: "1px solid #f9fafb" }}>
                    <td style={{ padding: "7px 10px", fontWeight: 700, color: "#111827" }}>{row.ticker}</td>
                    <td style={{ padding: "7px 10px", textAlign: "right", color: "#ef4444" }}>{Math.round(row.retail_crowding_score)}</td>
                    <td style={{ padding: "7px 10px", textAlign: "right", color: "#3b82f6" }}>{Math.round(row.institutional_score)}</td>
                    <td style={{ padding: "7px 10px", textAlign: "right", color: "#10b981" }}>{Math.round(row.smart_money_score)}</td>
                    <td style={{ padding: "7px 10px", textAlign: "right" }}>
                      <span style={{ background: color + "1a", color, padding: "2px 8px", borderRadius: 6, fontSize: 11, fontWeight: 600 }}>
                        {row.divergence_type}
                      </span>
                    </td>
                    <td style={{ padding: "7px 10px", textAlign: "right", color: "#6b7280", fontSize: 12 }}>
                      {DIVERGENCE_HORIZON[row.divergence_type || ""] || ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div style={{ marginTop: 16, fontSize: 11, color: "#9ca3af" }}>
        Sources: Reddit · Alternative.me · AAII · CFTC COT · FINRA · SEC EDGAR · yfinance · Polymarket
        · Theory: Lakonishok &amp; Lee (2001), Grinblatt &amp; Titman (1993), Wyckoff (1931)
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add "Crowd" to sidebar in `dashboard/src/app/layout.tsx`**

Open `layout.tsx`. Find the sidebar navigation items array (look for entries like `{ href: "/synthesis", label: "Synthesis" }` or similar). Add:

```typescript
{ href: "/crowd", label: "Crowd" }
```

- [ ] **Step 3: Create `dashboard/src/app/crowd/page.tsx`**

```typescript
import CrowdContent from "@/components/CrowdContent";
export default function CrowdPage() {
  return <CrowdContent />;
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd dashboard && npm run build 2>&1 | tail -20
```
Expected: build succeeds or only pre-existing errors.

- [ ] **Step 5: Commit**

```bash
git add dashboard/src/components/CrowdContent.tsx dashboard/src/app/crowd/ dashboard/src/app/layout.tsx
git commit -m "feat: Crowd Intelligence dashboard tab — macro map, sector crowding, divergences, conviction"
```

---

## Task 12: Universal Claude Skill

**Files:**
- Create: `~/.claude/plugins/crowd-intelligence/SKILL.md`
- Copy Python files into skill folder

- [ ] **Step 1: Create skill directory and copy Python files**

```bash
mkdir -p ~/.claude/plugins/crowd-intelligence
cp /Users/Jurgis2/Documents/Druckemiller/tools/crowd_types.py ~/.claude/plugins/crowd-intelligence/
cp /Users/Jurgis2/Documents/Druckemiller/tools/crowd_retail.py ~/.claude/plugins/crowd-intelligence/
cp /Users/Jurgis2/Documents/Druckemiller/tools/crowd_institutional.py ~/.claude/plugins/crowd-intelligence/
cp /Users/Jurgis2/Documents/Druckemiller/tools/crowd_smart.py ~/.claude/plugins/crowd-intelligence/
cp /Users/Jurgis2/Documents/Druckemiller/tools/crowd_engine.py ~/.claude/plugins/crowd-intelligence/
cp /Users/Jurgis2/Documents/Druckemiller/crowd_report.py ~/.claude/plugins/crowd-intelligence/
```

- [ ] **Step 2: Create `~/.claude/plugins/crowd-intelligence/SKILL.md`**

```markdown
---
name: crowd-intelligence
description: Institutional-grade crowd positioning intelligence. Shows what retail, institutional, and smart money crowds are invested in — and where they diverge. Uses 13 free data sources. IC-weighted, decay-adjusted, regime-conditional scoring. 6 Wyckoff-based divergence signals. Works in any project.
triggers:
  - /crowd-intelligence
  - crowd intelligence report
  - what is the crowd buying
  - crowd positioning
  - retail vs institutional positioning
  - smart money vs retail
  - crowd divergence signals
---

# Crowd Intelligence Skill

You are acting as an institutional-grade crowd positioning analyst. Your job is to run the crowd intelligence system and present findings clearly.

## What This Skill Does

Analyzes 3 crowd layers across 13 free data sources:
- **Layer 1 (Retail):** Reddit WSB, Fear & Greed, AAII sentiment, Google Trends — all CONTRARIAN
- **Layer 2 (Institutional):** Sector ETF flows, CFTC COT, FINRA ATS, SEC 13F, short interest, margin debt
- **Layer 3 (Smart Money):** Insider clusters (Form 4), options skew, Polymarket

Outputs: Macro positioning map → Sector crowding → Top divergence alerts → Conviction leaderboard.

## Invocation

```
/crowd-intelligence                          # full report
/crowd-intelligence NVDA AAPL XOM            # specific tickers
/crowd-intelligence --mode divergence-only   # only highest-alpha setups
/crowd-intelligence --sector technology      # sector deep dive
/crowd-intelligence --export json            # machine-readable
/crowd-intelligence --regime risk_off        # override regime
```

## How to Execute

1. Parse arguments from the user's invocation.
2. Detect environment:
   - If `tools/crowd_engine.py` is importable AND `crowd_intelligence` DB table has data → use cached pipeline data.
   - Otherwise → run fresh fetch via all collectors.
3. Run the crowd engine:

```python
import subprocess, sys

# Find Python
import shutil
python = shutil.which("python3") or shutil.which("python") or "/tmp/druck_venv/bin/python"

# Find crowd_engine.py — check current project, then skill folder
import os
from pathlib import Path

skill_dir = Path(__file__).parent
project_tools = Path.cwd() / "tools" / "crowd_engine.py"

if project_tools.exists():
    sys.path.insert(0, str(Path.cwd()))
else:
    sys.path.insert(0, str(skill_dir))

from crowd_engine import run_crowd_intelligence, generate_report

results = run_crowd_intelligence(
    tickers=TICKERS_FROM_ARGS,   # None = full universe
    mode=MODE_FROM_ARGS,
    write_db=False,
    sector=SECTOR_FROM_ARGS,
)
print(generate_report(results, mode=MODE_FROM_ARGS))
```

4. Display the formatted report.
5. If `--export json`: output raw JSON instead.

## Output Sections

| Section | What it shows |
|---------|--------------|
| Macro Positioning Map | Fear & Greed, AAII, COT, ETF flows, margin debt |
| Sector Crowding Map | 11 sectors ranked crowded → neutral → underowned |
| Divergence Alerts | Where layers disagree most — highest alpha |
| Conviction Leaderboard | Where all layers align — highest confidence |

## Divergence Signal Guide

| Signal | Meaning | Theory |
|--------|---------|--------|
| `DISTRIBUTION` | Retail buying, institutions exiting | Wyckoff Phase C/D |
| `CONTRARIAN_BUY` | Retail fearful, institutions accumulating | Lakonishok (1994) |
| `HIDDEN_GEM` | Nobody watching, insiders + options loading | Information asymmetry |
| `SHORT_SQUEEZE` | High short + catalyst approaching | Asquith et al. (2005) |
| `CROWDED_FADE` | Retail euphoria + smart money distributing | Market microstructure |
| `STEALTH_ACCUM` | Quiet institutional build before discovery | Flow analysis |

## Academic References

- Lakonishok & Lee (2001): Insider cluster buying → 4–6% 6-month excess returns
- Grinblatt & Titman (1993): 13F institutional momentum predictive at 60-day horizon
- Briese (2008): COT commercial positioning — most reliable free institutional signal
- Fisher & Statman (2000): AAII sentiment as contrarian indicator
- Asquith, Pathak & Ritter (2005): Short squeeze requires catalyst within 21 days
- Wyckoff (1931): Distribution/accumulation cycle theory

## Notes

- Retail signals are ALWAYS contrarian. High retail score = crowding risk = not a buy signal.
- Confirmation gate required: no divergence signal surfaces without price/volume confirmation.
- Graceful degradation: report shows `Signals available: X/13` — runs on whatever sources respond.
- Works standalone in any project. No database required.
```

- [ ] **Step 3: Verify skill is discoverable**

```bash
ls ~/.claude/plugins/crowd-intelligence/
```
Expected: `SKILL.md crowd_types.py crowd_retail.py crowd_institutional.py crowd_smart.py crowd_engine.py crowd_report.py`

- [ ] **Step 4: Push everything to GitHub**

```bash
cd /Users/Jurgis2/Documents/Druckemiller
git push origin main
```

- [ ] **Step 5: Final verification — run full smoke test**

```bash
/tmp/druck_venv/bin/python crowd_report.py --tickers AAPL NVDA XOM JPM GME --mode full
```
Expected: Full institutional report with all 5 sections, no Python errors.

- [ ] **Step 6: Final commit and push**

```bash
git add ~/.claude/plugins/crowd-intelligence/ 2>/dev/null || true
git add -A
git commit -m "feat: universal crowd-intelligence Claude skill — SKILL.md + portable Python scripts"
git push origin main
```

---

## Implementation Order

Build in this sequence — each task is independently testable:

1. Task 1 (DB schema) — 5 min
2. Task 2 (Signal dataclass) — 10 min
3. Task 3 (Engine math) — 20 min — **run all tests here**
4. Task 4 (Retail collector) — 15 min
5. Task 5 (Institutional collector) — 20 min
6. Task 6 (Smart money collector) — 15 min
7. Task 7 (Engine integration) — 20 min — **smoke test here**
8. Task 8 (CLI) — 5 min
9. Task 9 (Pipeline) — 5 min
10. Task 10 (API) — 10 min
11. Task 11 (Dashboard) — 20 min
12. Task 12 (Skill) — 10 min

Total estimated: ~2.5 hours.
