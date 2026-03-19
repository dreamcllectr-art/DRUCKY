# Crowd Intelligence System — Handoff Document

**Date:** 2026-03-19
**Branch:** main
**Last commit:** 3c0e5e5 (feat: crowd_engine — full pipeline, report generation, DB write, confirmation gate)

---

## What We Are Building

An institutional-grade crowd intelligence system integrated into the Druckenmiller Alpha platform. It shows what retail, institutional, and smart money crowds are currently positioned in, using IC-weighted, decay-adjusted, regime-conditional scoring. See full spec at `docs/superpowers/specs/2026-03-19-crowd-intelligence-design.md`.

---

## Completed Tasks (6 of 12)

| # | Task | File | Commit |
|---|------|------|--------|
| 1 | DB Schema | `tools/db.py` | ed1bb66 |
| 2 | Signal dataclass | `tools/crowd_types.py` | 2ad6359 |
| 3 | Scoring engine math | `tools/crowd_engine.py` (partial) | fbdfac4 |
| 4 | Retail collector | `tools/crowd_retail.py` | bfb3c7d |
| 5 | Institutional collector | `tools/crowd_institutional.py` | c4dfa4f |
| 6 | Smart money collector | `tools/crowd_smart.py` | 431ce83 |
| 7 | Engine integration | `tools/crowd_engine.py` (complete) | 3c0e5e5 |

Task 7 spec review: PASSED. Code quality review: IN PROGRESS (may need minor fixes).

---

## Remaining Tasks (5 of 12)

### Task 8: Standalone CLI — `crowd_report.py`
Create `crowd_report.py` at project root with argparse:
- `--tickers AAPL NVDA` — specific tickers
- `--sector technology` — filter by sector
- `--mode full|divergence-only|conviction|sector|macro`
- `--regime risk_off` — override macro regime
- `--export json|csv|markdown`

Full code is in the plan at `docs/superpowers/plans/2026-03-19-crowd-intelligence.md` around line 1830.

### Task 9: Pipeline integration — `tools/daily_pipeline.py`
Add Phase 2.95 between macro_regime and insider_trading:
```python
# Phase 2.95: Crowd Intelligence
try:
    from tools.crowd_engine import run_crowd_intelligence
    crowd_results = run_crowd_intelligence(universe=list(universe_symbols), write_db=True)
    print(f"  Crowd intelligence: {len(crowd_results)} rows written")
except Exception as e:
    print(f"  Crowd intelligence FAILED: {e}")
```
Full plan code is around line 1960 in the plan file.

### Task 10: FastAPI endpoints — `tools/api_market_modules.py`
Append 5 routes:
- `GET /api/crowd-intelligence` — top conviction scores
- `GET /api/crowd-intelligence/macro` — macro-level row
- `GET /api/crowd-intelligence/sector` — all sector rows
- `GET /api/crowd-intelligence/divergences` — divergence signals (gate_passed=1)
- `GET /api/crowd-intelligence/{ticker}` — per-ticker detail

Full code is in the plan around line 2010.

### Task 11: Dashboard tab — `CrowdContent.tsx` + routing
- Create `dashboard/src/components/CrowdContent.tsx` — 4-panel layout (macro map, sector crowding, divergence alerts, conviction leaderboard)
- Create `dashboard/src/app/crowd/page.tsx`
- Modify `dashboard/src/app/layout.tsx` — add "Crowd" to sidebar

Full code is in the plan around line 2060.

### Task 12: Universal Claude skill
- Create `~/.claude/plugins/crowd-intelligence/SKILL.md`
- Copy `tools/crowd_*.py` into the skill folder
- The skill lets any project call crowd intelligence from Claude Code

Full code is in plan around line 2200.

---

## How to Resume

1. Open this repo in Claude Code
2. Say: "Continue the crowd intelligence implementation from HANDOFF.md. Task 7 is done, start with Task 8."
3. Use `superpowers:subagent-driven-development` — dispatch a fresh subagent per task, two-stage review after each (spec compliance first, then code quality)

### Key commands
```bash
# Python runtime (always use this)
/tmp/druck_venv/bin/python

# Run tests
/tmp/druck_venv/bin/python -m pytest tests/test_crowd_engine.py -v

# Smoke test the engine
/tmp/druck_venv/bin/python -c "
from tools.crowd_engine import run_crowd_intelligence, generate_report
results = run_crowd_intelligence(tickers=['AAPL','GME'], write_db=False)
print(generate_report(results))
"

# Push to GitHub
cd ~/druckenmiller && git add -A && git commit -m '...' && git push
```

### Files created so far
```
tools/crowd_types.py          # Signal dataclass
tools/crowd_retail.py         # Layer 1: Fear&Greed, AAII, Reddit, Google Trends
tools/crowd_institutional.py  # Layer 2: ETF flows, COT, FINRA, 13F, short interest, margin debt
tools/crowd_smart.py          # Layer 3: insider clusters, options skew, Polymarket
tools/crowd_engine.py         # Full engine: normalize, score, divergence, confirmation gate, report
tests/test_crowd_engine.py    # 20 unit tests — all passing
```

---

## Architecture Quick Reference

**Three-layer scoring:**
- Retail (contrarian): inverted via `1 - normalized`
- Institutional (trend-following): IC=0.05-0.07
- Smart money (leading): IC=0.06-0.08

**Conviction formula:**
```
raw = smart_w * smart + inst_w * inst + retail_penalty * (1 - retail)
alignment = 1 - std([smart, inst, 1-retail]) / 0.577
conviction = raw * alignment * 100  →  [0, 100]
```

**6 Divergence signals:** DISTRIBUTION, CONTRARIAN_BUY, HIDDEN_GEM, SHORT_SQUEEZE, CROWDED_FADE, STEALTH_ACCUM

**5 Macro regimes:** strong_risk_on, risk_on, neutral, risk_off, strong_risk_off

**Plan file:** `docs/superpowers/plans/2026-03-19-crowd-intelligence.md`
**Spec file:** `docs/superpowers/specs/2026-03-19-crowd-intelligence-design.md`
