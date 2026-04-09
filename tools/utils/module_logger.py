"""Structured error logging for pipeline modules.

Replaces silent `except: pass` blocks system-wide.

Usage:
    from tools.utils.module_logger import log_module_error

    try:
        result = fetch_something()
    except Exception as e:
        log_module_error(module="stocktwits", phase="fetch", exc=e)
        return None
"""

import logging
import traceback
from datetime import date, datetime

from tools.db import get_conn, query

logger = logging.getLogger(__name__)


def init_module_health_table() -> None:
    """Create module_health table if it doesn't exist. Called once at pipeline start."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS module_health (
                run_date  TEXT NOT NULL,
                module    TEXT NOT NULL,
                phase     TEXT NOT NULL,
                severity  TEXT NOT NULL DEFAULT 'WARNING',
                error_msg TEXT,
                ts        TEXT NOT NULL,
                PRIMARY KEY (run_date, module, phase, ts)
            )
        """)


def log_module_error(module: str, phase: str, exc: Exception,
                     severity: str = "WARNING") -> None:
    """Log a module error to `module_health` table and Python logger.

    Args:
        module:   Module name, e.g. "stocktwits", "alpha_vantage".
        phase:    Pipeline phase, e.g. "fetch", "score", "write".
        exc:      The caught exception.
        severity: "WARNING" (recoverable) or "CRITICAL" (data absent).
    """
    run_date = date.today().isoformat()
    ts = datetime.utcnow().isoformat(timespec="seconds")
    msg = f"{type(exc).__name__}: {exc}"

    # Log to Python logger so it shows in terminal / Modal logs
    log_fn = logger.critical if severity == "CRITICAL" else logger.warning
    log_fn(f"[{module}:{phase}] {msg}")

    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO module_health "
                "(run_date, module, phase, severity, error_msg, ts) VALUES (?,?,?,?,?,?)",
                (run_date, module, phase, severity, msg[:500], ts),
            )
    except Exception as db_exc:
        # Never let logging itself crash the pipeline
        logger.debug(f"module_health write failed: {db_exc}")


def get_module_health(run_date: str | None = None) -> dict:
    """Return a summary of module errors for a given run date.

    Returns:
        {
          "total": int,
          "critical": int,
          "warnings": int,
          "modules": [{"module": str, "phase": str, "severity": str, "error_msg": str}, ...]
        }
    """
    if run_date is None:
        run_date = date.today().isoformat()

    rows = query(
        "SELECT module, phase, severity, error_msg FROM module_health WHERE run_date=? ORDER BY severity DESC, module",
        [run_date],
    )
    return {
        "total": len(rows),
        "critical": sum(1 for r in rows if r["severity"] == "CRITICAL"),
        "warnings": sum(1 for r in rows if r["severity"] == "WARNING"),
        "modules": [dict(r) for r in rows],
    }
