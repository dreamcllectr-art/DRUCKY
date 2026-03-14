# Daily Scan Workflow

## Objective
Run the full analysis pipeline daily after US market close to identify new trading signals.

## Schedule
- **When**: 5:00 PM ET (after market close + 30 min for data settlement)
- **Duration**: ~10-15 minutes for full universe scan

## Manual Run
```bash
cd Druckemiller
source venv/bin/activate
python -m tools.daily_pipeline
```

## Automated Run (macOS launchd)

Create `~/Library/LaunchAgents/com.druckenmiller.scan.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.druckenmiller.scan</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Druckemiller" && source venv/bin/activate && python -m tools.daily_pipeline</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>17</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/druckenmiller_scan.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/druckenmiller_scan_err.log</string>
</dict>
</plist>
```

Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.druckenmiller.scan.plist
```

## Pipeline Steps
1. Fetch stock universe (S&P 500 + S&P 400)
2. Fetch prices for stocks, crypto, commodities
3. Fetch macro indicators from FRED
4. Fetch stock fundamentals
5. Compute market breadth
6. Compute macro regime score
7. Compute technical scores
8. Compute fundamental scores
9. Generate composite signals
10. Size positions
11. Check watchlist alerts
12. Send email summary

## Logs
Scan logs are saved to `.tmp/logs/scan_YYYYMMDD.log`

## Troubleshooting
- **yfinance rate limit**: If you see "Too Many Requests", the fetch_prices step includes delays. May need to increase sleep times in `tools/fetch_prices.py`.
- **FRED API error**: Check that FRED_API_KEY is valid in `.env`
- **No signals generated**: Ensure price data exists (run fetch_prices first)
