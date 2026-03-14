# Setup Guide

## Quick Start

```bash
cd Druckemiller
chmod +x setup.sh
./setup.sh
```

## Manual Setup

### 1. Python Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. API Keys
Copy `.env.template` to `.env` and fill in:

- **FRED_API_KEY**: Get free at https://fred.stlouisfed.org/docs/api/api_key.html
- **SMTP_USER / SMTP_PASS**: Gmail address + App Password (for email alerts)
  - Go to Google Account > Security > 2-Step Verification > App passwords
  - Generate a new app password for "Mail"
- **EMAIL_TO**: Where to receive daily scan emails
- **PORTFOLIO_VALUE**: Your portfolio size for position sizing (default: 50000)

### 3. First Run
```bash
source venv/bin/activate
python -m tools.daily_pipeline
```

This will:
1. Fetch ~1050 asset prices (10-15 min first run)
2. Pull macro indicators from FRED
3. Compute all scores
4. Generate signals
5. Send email alert (if configured)

### 4. Install Dashboard (Node.js)
```bash
brew install node    # If not installed
cd dashboard
npm install
cd ..
```

### 5. Launch System
You need two terminal tabs:

**Tab 1 - API Server:**
```bash
source venv/bin/activate
uvicorn tools.api:app --reload --port 8000
```

**Tab 2 - Dashboard:**
```bash
cd dashboard
npm run dev
```

Opens at http://localhost:3000

### 5. Daily Automation (Optional)
See `workflows/daily_scan.md` for setting up automatic daily scans.
