"""Modal deployment for Druckenmiller Alpha System.

Deploys:
  - FastAPI web endpoint (serves the dashboard API)
  - Daily pipeline cron job (runs after US market close Mon-Fri)

Usage:
  modal setup                          # one-time login
  modal deploy modal_app.py            # deploy/update (reads .env automatically)
  modal run modal_app.py::daily_pipeline   # run pipeline manually once
"""

import os
from pathlib import Path
import modal

app = modal.App("druckenmiller")

# Persistent volume — SQLite database lives here across deploys
volume = modal.Volume.from_name("druckenmiller-db", create_if_missing=True)
VOLUME_PATH = "/data"
DB_PATH = f"{VOLUME_PATH}/druckenmiller.db"

_project_dir = Path(__file__).parent

# Container image — Debian slim + all Python deps + tools/ source code
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir(_project_dir / "tools", remote_path="/root/tools")
)

# Secrets — read from local .env at deploy time (no manual secret creation needed)
_env_path = _project_dir / ".env"
secrets = [modal.Secret.from_dotenv(path=_env_path)]


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    secrets=secrets,
)
@modal.asgi_app()
def api():
    """FastAPI web endpoint — serves all /api/* routes."""
    os.environ.setdefault("DATABASE_PATH", DB_PATH)
    from tools.api import app as fastapi_app
    return fastapi_app


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    secrets=secrets,
    # Run daily at 11pm UTC (6pm ET) Mon-Fri, after US market close
    schedule=modal.Cron("0 23 * * 1-5"),
    timeout=3600,  # 1 hour max
)
def daily_pipeline():
    """Daily data pipeline — fetches prices, scores stocks, generates signals."""
    os.environ.setdefault("DATABASE_PATH", DB_PATH)
    from tools.daily_pipeline import main
    main()
    volume.commit()  # flush writes to persistent storage


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    secrets=secrets,
    # Run every hour during weekends (Saturday=6, Sunday=0)
    schedule=modal.Cron("0 * * * 0,6"),
    timeout=300,  # 5 min max — just API calls + DB writes
)
def hl_weekend_monitor():
    """Hyperliquid weekend price monitor — snapshots + gap signals at 20:00 UTC."""
    os.environ.setdefault("DATABASE_PATH", DB_PATH)
    try:
        from tools.hyperliquid_gap import run
        run(mode="auto")
        volume.commit()
    except ImportError:
        print("tools.hyperliquid_gap not yet implemented — skipping")


@app.function(
    image=image,
    volumes={VOLUME_PATH: volume},
    secrets=secrets,
    # Monday at 16:00 UTC (after US market open) — backfill actual opens
    schedule=modal.Cron("0 16 * * 1"),
    timeout=300,
)
def hl_monday_backfill():
    """Backfill actual opening prices for HL gap accuracy tracking."""
    os.environ.setdefault("DATABASE_PATH", DB_PATH)
    try:
        from tools.db import init_db
        from tools.hyperliquid_gap import backfill_actuals
        init_db()
        backfill_actuals()
        volume.commit()
    except ImportError:
        print("tools.hyperliquid_gap not yet implemented — skipping")
