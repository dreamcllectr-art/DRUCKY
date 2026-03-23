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

_project_dir = Path(__file__).parent

# Container image — Debian slim + all Python deps + tools/ source code
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
    .add_local_dir(_project_dir / "tools", remote_path="/root/tools")
)

# Secrets — read from local .env at deploy time (DATABASE_URL points to Neon)
_env_path = _project_dir / ".env"
secrets = [modal.Secret.from_dotenv(path=_env_path)]


@app.function(
    image=image,
    secrets=secrets,
)
@modal.asgi_app()
def api():
    """FastAPI web endpoint — serves all /api/* routes."""
    from tools.api import app as fastapi_app
    return fastapi_app


@app.function(
    image=image,
    secrets=secrets,
    # Run daily at 11pm UTC (6pm ET) Mon-Fri, after US market close
    schedule=modal.Cron("0 23 * * 1-5"),
    timeout=3600,  # 1 hour max
)
def daily_pipeline():
    """Daily data pipeline — fetches prices, scores stocks, generates signals."""
    from tools.daily_pipeline import main
    main()


