# Hyperliquid Weekend Gap Arbitrage

## Objective
Monitor Hyperliquid HIP-3 perp prices during weekends to predict Monday CME/equity opening gaps. Track accuracy over time.

## Research Backing
- **Source**: @0xmattegoat analysis of 35 HIP-3 instruments across 9 weekends
- **Key stats**: 100% directional accuracy (34/34 assets), R²=0.973, 14bps median error
- **Optimal signal**: 20:00 UTC Sunday (slope≈1.0, R²=0.73) — NOT 23:00 when CME opens
- **Book thinning**: LPs pull 66-84% of depth in last 3h before CME reopens
- **Metals overshoot**: Gold slope jumps from 1.09→1.61, Silver 1.88→2.04 after 20:00

## Pipeline Schedule
- **Saturday/Sunday every hour**: `collect_snapshots()` — fetch mids + L2 books for all instruments
- **Sunday 20:00+ UTC**: `generate_gap_signals()` — compare HL weekend return vs Friday close
- **Monday 16:00 UTC**: `backfill_actuals()` — fetch actual opens, compute accuracy

## Tool
`tools/hyperliquid_gap.py` — Run modes:
```bash
venv/bin/python tools/hyperliquid_gap.py --mode auto      # detect time, act accordingly
venv/bin/python tools/hyperliquid_gap.py --mode snapshot   # force snapshot
venv/bin/python tools/hyperliquid_gap.py --mode signal     # force gap signal generation
venv/bin/python tools/hyperliquid_gap.py --mode backfill   # force Monday backfill
```

## Hyperliquid API
- **Endpoint**: POST `https://api.hyperliquid.xyz/info`
- **All mids**: `{"type":"allMids","dex":"xyz"}` — returns all instruments for a deployer
- **L2 book**: `{"type":"l2Book","coin":"xyz:GOLD"}` — 20 levels per side
- **Deployers**: `{"type":"perpDexs"}` — lists all available deployers
- **No API key needed** — public read-only data
- **Rate limits**: ~10 req/s is safe

## Active Deployers (as of 2026-03-10)
| Deployer | Name | Instruments | Notable |
|----------|------|-------------|---------|
| xyz | XYZ | 51 | Main deployer: stocks, commodities, indices, FX |
| flx | Felix | 13 | Metals, oil, NVDA, TSLA |
| km | Kinetiq | 18 | US500/SPY, SMALL2000/IWM, single stocks |
| vntl | Ventuals | 13 | Sector ETFs (SEMIS, ENERGY, DEFENSE) |
| cash | dreamcash | 12 | Single stocks + metals |

## DB Tables
- `hl_price_snapshots` — hourly snapshots (hl_symbol, mid, bid, ask, spread, depth)
- `hl_gap_signals` — gap predictions + accuracy tracking
- `hl_deployer_spreads` — cross-deployer divergences

## API Endpoints
- `GET /api/hyperliquid/gaps` — latest gap predictions
- `GET /api/hyperliquid/snapshots/{ticker}` — price history for a ticker
- `GET /api/hyperliquid/deployer-spreads` — cross-deployer divergences
- `GET /api/hyperliquid/book-depth` — latest depth for all instruments
- `GET /api/hyperliquid/accuracy` — aggregate accuracy stats

## Key Quirks
1. **Deployer naming**: xyz, flx, km, vntl, cash (NOT kinetiq, felix, ventuals)
2. **L2 book format**: `levels[0]` = bids (descending), `levels[1]` = asks (ascending)
3. **Size field**: L2 `sz` is in asset units, multiply by `px` for USD
4. **Weekend definition**: CME closes Fri 5PM ET → reopens Sun 5PM ET (23:00 UTC)
5. **Book depth drops** significantly after 20:00 UTC Sunday — signal degrades
6. **Metals overshoot**: Gold/Silver prices exaggerate after 20:00 UTC — ignore late moves

## Alerts
- Email alert when |predicted gap| > 1%
- Email alert when cross-deployer spread > 100bps
- Uses existing SMTP config (SMTP_USER, SMTP_PASS, EMAIL_TO)

## Future Enhancements
- Funding rate tracking per instrument
- WebSocket streaming for real-time book updates
- Cross-deployer arbitrage execution via HL API
- Open interest analysis for positioning signals
