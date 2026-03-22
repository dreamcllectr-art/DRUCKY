# DAS — Session Log
Running log of observations, decisions, and learnings for future LLM context.
Append new sessions at the top.

---

## Session: 2026-03-22 (Part 2) — Design Polish to 9.2/10

### What We Built / Fixed
- **NEUTRAL regime badge**: Fixed amber/orange fallback → slate-100/slate-600/slate-300 for true neutral regime. Also aligned pulse dot color to regime (slate-400 for NEUTRAL instead of macroScore-derived amber).
- **Gates waterfall bars**: Replaced linear scale (caused tiny dots for low-count gates 7-10) with log scale `Math.log1p(count) / Math.log1p(maxCount)` — all gates now render visible bars. Also bumped bar track from h-1.5 → h-2.
- **Verified all prior fixes**: StockPanel SVG close button, 9px labels, slate ENTRY color all confirmed correct. Portfolio 404 confirmed as non-issue (sidebar correctly routes to /v2/conviction).

### Key Technical Learnings

**Tailwind class purging:**
- Tailwind only includes classes it can statically detect at build time. If you add new classes (e.g. `bg-slate-400`) in conditional strings, they may not exist in the CSS bundle if unused elsewhere. Always verify computed styles via `window.getComputedStyle()` not just DOM className inspection.
- Chrome DevTools MCP screenshots can appear to cache old styles — use `evaluate_script` to inspect `window.getComputedStyle()` for ground truth.

**Log scale for waterfall charts:**
- When values span 3+ orders of magnitude (4 → 916), linear scale renders small values as invisible dots.
- `Math.log1p(x)` (log(1+x)) is safe for x=0 and compresses large ranges while keeping small values readable.
- Formula: `Math.max(6, (Math.log1p(count) / Math.log1p(maxCount)) * 100)` gives minimum 6% width on a 0-100% scale.

**Design semantic consistency:**
- Badge dot color and badge background color must both agree on the semantic meaning. E.g. a slate "NEUTRAL" badge with a red pulse dot is confusing — the dot should also be neutral (slate-400).

### Current Design Score: ~9.2/10
Remaining gaps (not worth addressing until data/UX requirements clearer):
- `h-[calc(100vh-88px)]` hardcoded height in PortfolioView and AlphaStack
- No keyboard navigation between sidebar pages (Tab key)
- Loading states: some pages still use plain text "Loading..." instead of skeleton shimmer

---

## Session: 2026-03-22 — Frontend Design Audit + Pipeline ETL Improvements

### What We Built / Fixed
- Switched font from Inter → Geist (via `geist` npm package from Vercel, not `next/font/google` which doesn't have it in v14.2)
- Replaced unicode icon characters (▣ ◆ ★ ⚠ ✎) in Sidebar with proper inline SVGs
- Fixed Sidebar section headers: 8px → 9px, better tracking, legible
- Sidebar active state: slim 2.5px left-accent bar with emerald bg highlight
- Added `Search...` kbd shortcut chip with magnifier SVG in sidebar
- Portfolio page: removed 📊 emoji from empty state → clean SVG illustration
- Portfolio "On Deck": replaced 3-equal-card grid with 2-col FatPitch cards + compact list rows for G8-9
- Added dot-grid background (radial-gradient dots) to replace flat gray-50
- Added `.hover-lift`, `.focus-ring` CSS utilities
- Improved scrollbar: thinner, transparent track, slate-200 thumb
- `digital_exhaust.py`: replaced `print()` → `logger.*`, added `_make_session()` with `urllib3.Retry` (3 retries, backoff, respects `Retry-After`), passed shared `requests.Session` to all fetch functions
- `api_v2_terminal.py`: replaced all `except Exception: pass` → `except Exception as e: logger.warning(...)` for observability
- `GatesView.tsx`: fixed 2 `text-white` bugs in light-mode app (gate name and symbol were invisible)
- `GatesView.tsx`: improved empty detail state with SVG icon + proper typography

### Key Technical Learnings

**Next.js fonts:**
- `next/font/google` does NOT include Geist in Next.js 14.2.x
- Use the `geist` npm package from Vercel: `npm install geist`
- Import as: `import { GeistSans } from 'geist/font/sans'` and `import { GeistMono } from 'geist/font/mono'`
- Apply as class on `<html>` tag: `className={GeistSans.variable + ' ' + GeistMono.variable}`
- Reference in CSS: `var(--font-geist-sans)` and `var(--font-geist-mono)`

**Python ETL:**
- Always use `requests.Session()` + `HTTPAdapter(max_retries=Retry(...))` for all external HTTP calls
- `Retry(respect_retry_after_header=True)` handles GitHub 429s correctly with the `Retry-After` header
- Never mix `print()` and `logger.*` in the same module — pick one; always use `logger.*` in production pipeline code
- `except Exception: pass` is an anti-pattern — always `except Exception as e: logger.warning(...)` minimum

**Design:**
- 3-equal-card horizontal grid is a classic AI design smell — avoid it
- Emoji in empty states is banned in production tools — use inline SVGs
- `text-white` can hide text in light-mode components — audit carefully when reviewing dark/light mode switching
- Dot-grid backgrounds (`radial-gradient(circle, #e2e8f0 1px, transparent 1px)`) add depth cheaply

### Current State (2026-03-22)
- Backend: FastAPI on port 8000 (start with `/tmp/druck_venv/bin/python -m uvicorn tools.api:app --port 8000`)
- Frontend: Next.js on port 3000 (start in `dashboard/` with `npm run dev`)
- DB: `.tmp/druckenmiller.db` (SQLite, ~30MB, not in git)
- 4 Fat Pitches currently passing Gate 10: EOG, PSX, DVN, MPC (all Energy)
- Pipeline last run: 2026-03-20

---
