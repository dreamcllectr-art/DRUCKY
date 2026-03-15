#!/bin/bash
# Druckenmiller Alpha System - One-command setup
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Druckenmiller Alpha System Setup ==="

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate and install
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env template..."
    cp .env.template .env
    echo ">>> IMPORTANT: Edit .env and add your FRED_API_KEY <<<"
fi

# Create data directory
mkdir -p .tmp/logs

# Install Node.js dashboard
if [ -d "dashboard" ] && [ -f "dashboard/package.json" ]; then
    echo "Installing dashboard dependencies..."
    cd dashboard
    npm install -q 2>/dev/null || echo "Node.js not found. Install Node: brew install node, then run 'cd dashboard && npm install'"
    cd ..
fi

echo ""
echo "=== Setup Complete ==="
echo "1. Edit .env with your API keys (FRED_API_KEY required)"
echo "2. Activate Python: source venv/bin/activate"
echo "3. Run daily scan: python -m tools.daily_pipeline"
echo "4. Start API server: uvicorn tools.api:app --reload --port 8000"
echo "5. Start dashboard: cd dashboard && npm run dev"
echo "6. Open: http://localhost:3000"
