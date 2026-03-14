# Google Slides Intelligence Deck — Workflow

## Objective
Generate professional investment presentations from the Druckenmiller Alpha System data, delivered as Google Slides decks.

## Prerequisites
- `credentials.json` in project root (Google Cloud OAuth Desktop credentials)
- Google Slides API + Google Drive API enabled on the Cloud project
- `token.json` auto-created on first run (browser OAuth)

## One-Time Setup
```bash
python -m tools.google_slides --setup
```
This will:
1. Prompt browser OAuth (first time only)
2. Create a test presentation to verify API access
3. Save `token.json` for future runs

## Usage

### Full Intelligence Deck
```bash
python -m tools.google_slides --topic energy
python -m tools.google_slides --topic "AI power"
python -m tools.google_slides --topic semiconductors
```

### Skip Gemini (placeholder text, faster for testing)
```bash
python -m tools.google_slides --topic energy --skip-gemini
```

## What Gets Generated

| Slide | Content |
|-------|---------|
| 1. Title | System branding, macro regime badge, date |
| 2. Executive Summary | Gemini-generated narrative + key metrics sidebar |
| 3. Macro Context | Regime sub-scores with bar charts + Polymarket predictions |
| 4. Sector Deep-Dive | Gemini analysis of the specific sector/theme |
| 5-7. Conviction Ranking | Heatmap table: symbol, convergence, tech, fund, SM, pairs, signal |
| 8. Pairs & Relative Value | Active pairs signals with z-scores |
| 9. Smart Money & Insider | 13F positioning + insider trading clusters |
| 10. Risk Matrix | Gemini-generated risk assessment |
| 11. Closing | System capabilities + disclaimer |

## Design System
- Dark professional theme (#0E1117 background)
- Inter font family + JetBrains Mono for numbers
- Color-coded scores: green (≥70), light green (≥50), amber (≥40), orange (≥25), red (<25)
- 16:9 widescreen format

## Data Sources
Pulls from DB tables populated by the daily pipeline:
- `convergence_results` — stock scores
- `macro_regime` — regime classification
- `prediction_market_signals` — Polymarket
- `pair_signals` — cointegration pairs
- `smart_money_scores` + `insider_signals`
- `intelligence_reports` — cached Gemini narratives

## Troubleshooting

### Token expired
Delete `token.json` and re-run `--setup`.

### API quota
Google Slides API has generous free limits (300 requests/min). Batch updates keep us well under.

### Missing data
If DB tables are empty, run the daily pipeline first:
```bash
python -m tools.daily_pipeline
```
