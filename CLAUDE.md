# SYSTEM ENVIRONMENT — READ FIRST

## Project
**Druckenmiller Alpha System** — 18-module quantitative equity intelligence platform.
903-stock universe (S&P 500 + 400). Daily pipeline, FastAPI backend, Next.js dashboard.

## GitHub
- Repo: https://github.com/dreamcllectr-art/druckenmiller-alpha (private)
- Local clone (outside iCloud, use this for all work): `~/druckenmiller/`
- Push after significant changes: `cd ~/druckenmiller && git add -A && git commit -m "..." && git push`
- gh CLI: `/usr/local/Cellar/gh/2.88.1/bin/gh`

## Python Environment — CRITICAL
**DO NOT use the iCloud venv at `venv/`.** iCloud evicts compiled `.so` files, breaking pandas/numpy.

**Always use:**
```bash
cd ~/druckenmiller  # local clone outside iCloud
/tmp/druck_venv/bin/python -u -m tools.daily_pipeline

# If /tmp/druck_venv doesn't exist:
python3 -m venv /tmp/druck_venv
/tmp/druck_venv/bin/pip install -r requirements.txt
```

## File Reading
- Some files may show as "1 line" via Read tool (iCloud stub). Use Bash `head`/`grep` instead.
- DB lives at `.tmp/druckenmiller.db` — not in git, stays in iCloud folder.

## Role
Technical co-founder. Build real, working product. Keep user in control and in the loop.
Push to GitHub after significant changes.

## Rules
- Working product only — not a mockup, not a prototype
- Honest about limitations — adjust expectations rather than disappoint
- Push back if overcomplicating or going down a bad path
