"""Supply Chain Intelligence — rail, shipping, and trucking proxy scores.

Aggregates freight-sector stock momentum vs SPY as a real-time proxy
for supply chain health.  Institutional-grade approach: freight stock
momentum IS a leading indicator for sector-level economic activity.

Data sources (all from existing price_data table):
  1. Rail stocks (CSX, NSC, UNP)  — weight 0.40
  2. Shipping stocks + BDI proxy  — weight 0.30
  3. Trucking stocks              — weight 0.30

Produces 0-100 supply_chain_score per symbol via sector mapping.
Weekly gate: skips if last run was <7 days ago.

Usage:
    python -m tools.supply_chain_intel
"""

import json
import logging
import time
from datetime import date, datetime, timedelta

from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

# ── Proxy Baskets ────────────────────────────────────────────────────

RAIL_STOCKS = ["CSX", "NSC", "UNP"]
SHIPPING_STOCKS = ["ZIM", "SBLK", "GOGL", "MATX"]
TRUCKING_STOCKS = ["ODFL", "XPO", "SAIA", "JBHT", "CHRW"]

# ── Sector Mapping ───────────────────────────────────────────────────

SUPPLY_CHAIN_SECTORS = {
    "mining":        ["FCX", "NEM", "SCCO", "CLF", "X", "AA"],
    "agriculture":   ["ADM", "BG", "DE", "MOS", "CF"],
    "energy":        ["XOM", "CVX", "COP", "OXY", "EOG"],
    "industrials":   ["CAT", "CMI", "HON", "GE", "ETN"],
    "retail_import": ["WMT", "TGT", "COST", "HD", "LOW"],
    "tech_hardware": ["AAPL", "DELL", "HPQ"],
    "shipping":      ["ZIM", "SBLK", "GOGL", "MATX"],
}

# Which transport modes matter most per sector (rail, shipping, trucking)
SECTOR_WEIGHTS = {
    "mining":        {"rail": 0.60, "shipping": 0.20, "trucking": 0.20},
    "agriculture":   {"rail": 0.50, "shipping": 0.30, "trucking": 0.20},
    "energy":        {"rail": 0.30, "shipping": 0.40, "trucking": 0.30},
    "industrials":   {"rail": 0.35, "shipping": 0.25, "trucking": 0.40},
    "retail_import": {"rail": 0.15, "shipping": 0.55, "trucking": 0.30},
    "tech_hardware": {"rail": 0.10, "shipping": 0.60, "trucking": 0.30},
    "shipping":      {"rail": 0.10, "shipping": 0.70, "trucking": 0.20},
}

# Default blend used for symbols not in any supply chain sector
DEFAULT_WEIGHTS = {"rail": 0.40, "shipping": 0.30, "trucking": 0.30}


# ── DB Setup ─────────────────────────────────────────────────────────

def _ensure_tables():
    """Create supply-chain-specific tables if they don't exist."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS supply_chain_raw (
            date TEXT,
            source TEXT,
            metric TEXT,
            value REAL,
            sector TEXT,
            details TEXT,
            PRIMARY KEY (date, source, metric)
        );
        CREATE TABLE IF NOT EXISTS supply_chain_scores (
            symbol TEXT,
            date TEXT,
            supply_chain_score REAL,
            rail_score REAL,
            shipping_score REAL,
            trucking_score REAL,
            details TEXT,
            PRIMARY KEY (symbol, date)
        );
    """)
    conn.commit()
    conn.close()


# ── Weekly Gate ──────────────────────────────────────────────────────

def _should_run() -> bool:
    """Return True if last run was >= 7 days ago (or never)."""
    rows = query(
        "SELECT MAX(date) as last_date FROM supply_chain_scores"
    )
    if not rows or rows[0]["last_date"] is None:
        return True
    last = datetime.strptime(rows[0]["last_date"], "%Y-%m-%d").date()
    return (date.today() - last).days >= 7


# ── Momentum Helper ─────────────────────────────────────────────────

def _get_returns(symbol: str, days: int = 20):
    """Return percentage change over *days* trading days for a symbol.

    Uses the two most recent closes separated by *days* rows.
    Returns None if insufficient data.
    """
    rows = query(
        """
        SELECT close FROM price_data
        WHERE symbol = ? AND close IS NOT NULL
        ORDER BY date DESC
        LIMIT ?
        """,
        [symbol, days + 1],
    )
    if len(rows) < days + 1:
        return None
    latest = rows[0]["close"]
    prior = rows[days]["close"]
    if prior is None or prior == 0:
        return None
    return (latest - prior) / prior * 100


def _compute_basket_momentum(symbols: list[str], days: int = 20) -> float | None:
    """Average return of a basket over *days* trading days."""
    returns = []
    for sym in symbols:
        r = _get_returns(sym, days)
        if r is not None:
            returns.append(r)
    return sum(returns) / len(returns) if returns else None


def _momentum_to_score(basket_return: float | None,
                        spy_return: float | None) -> float:
    """Convert relative momentum (basket vs SPY) to a 0-100 score.

    Outperformance bands:
      > +5 pp  → 80-100
      > +2 pp  → 60-80
      -2 to +2 → 40-60  (neutral)
      < -2 pp  → 20-40
      < -5 pp  → 0-20
    """
    if basket_return is None or spy_return is None:
        return 50.0  # neutral fallback

    spread = basket_return - spy_return  # percentage-point spread

    if spread >= 5:
        return min(100.0, 80.0 + (spread - 5) * 4)
    elif spread >= 2:
        return 60.0 + (spread - 2) / 3 * 20
    elif spread >= -2:
        return 40.0 + (spread + 2) / 4 * 20
    elif spread >= -5:
        return 20.0 + (spread + 5) / 3 * 20
    else:
        return max(0.0, 20.0 + (spread + 5) * 4)


# ── Core Logic ───────────────────────────────────────────────────────

def _compute_transport_scores() -> dict[str, float]:
    """Compute rail, shipping, trucking scores (0-100) vs SPY."""
    spy_return = _get_returns("SPY", 20)
    print(f"  SPY 20-day return: {spy_return:+.2f}%" if spy_return is not None
          else "  SPY return: N/A (using neutral)")

    scores = {}
    for label, basket in [("rail", RAIL_STOCKS),
                           ("shipping", SHIPPING_STOCKS),
                           ("trucking", TRUCKING_STOCKS)]:
        basket_ret = _compute_basket_momentum(basket, 20)
        score = _momentum_to_score(basket_ret, spy_return)
        scores[label] = round(score, 1)
        print(f"  {label.capitalize():>10} basket return: "
              f"{basket_ret:+.2f}%  →  score {score:.0f}" if basket_ret is not None
              else f"  {label.capitalize():>10} basket return: N/A  →  score 50 (neutral)")

    return scores


def _build_symbol_scores(transport_scores: dict[str, float]) -> list[tuple]:
    """Map transport scores to individual symbols via sector weights."""
    today = date.today().isoformat()
    rows_out = []

    # Collect all mapped symbols
    assigned: set[str] = set()
    for sector, symbols in SUPPLY_CHAIN_SECTORS.items():
        w = SECTOR_WEIGHTS.get(sector, DEFAULT_WEIGHTS)
        sector_score = round(
            transport_scores["rail"] * w["rail"]
            + transport_scores["shipping"] * w["shipping"]
            + transport_scores["trucking"] * w["trucking"],
            1,
        )
        details = json.dumps({
            "sector": sector,
            "weights": w,
            "rail_score": transport_scores["rail"],
            "shipping_score": transport_scores["shipping"],
            "trucking_score": transport_scores["trucking"],
        })
        for sym in symbols:
            rows_out.append((
                sym, today, sector_score,
                transport_scores["rail"],
                transport_scores["shipping"],
                transport_scores["trucking"],
                details,
            ))
            assigned.add(sym)

    # For every other symbol in the universe, assign a blended neutral-ish score
    universe = query("SELECT symbol FROM stock_universe")
    blended = round(
        transport_scores["rail"] * DEFAULT_WEIGHTS["rail"]
        + transport_scores["shipping"] * DEFAULT_WEIGHTS["shipping"]
        + transport_scores["trucking"] * DEFAULT_WEIGHTS["trucking"],
        1,
    )
    details_default = json.dumps({
        "sector": "default",
        "weights": DEFAULT_WEIGHTS,
        "rail_score": transport_scores["rail"],
        "shipping_score": transport_scores["shipping"],
        "trucking_score": transport_scores["trucking"],
    })
    for row in universe:
        sym = row["symbol"]
        if sym not in assigned:
            rows_out.append((
                sym, today, blended,
                transport_scores["rail"],
                transport_scores["shipping"],
                transport_scores["trucking"],
                details_default,
            ))

    return rows_out


def _store_raw(transport_scores: dict[str, float]):
    """Persist raw transport metrics for audit trail."""
    today = date.today().isoformat()
    raw_rows = []
    for mode, score in transport_scores.items():
        raw_rows.append((
            today, mode, "momentum_vs_spy", score, "all",
            json.dumps({"lookback_days": 20}),
        ))
    upsert_many(
        "supply_chain_raw",
        ["date", "source", "metric", "value", "sector", "details"],
        raw_rows,
    )


# ── Entry Point ──────────────────────────────────────────────────────

def run():
    """Weekly supply chain intelligence run."""
    init_db()
    _ensure_tables()

    print("\n" + "=" * 60)
    print("  SUPPLY CHAIN INTELLIGENCE")
    print("=" * 60)

    if not _should_run():
        print("  Skipping — last run was < 7 days ago")
        print("=" * 60)
        return

    # 1. Compute transport mode scores
    transport_scores = _compute_transport_scores()

    # 2. Store raw metrics
    _store_raw(transport_scores)

    # 3. Map to per-symbol scores
    symbol_rows = _build_symbol_scores(transport_scores)
    print(f"\n  Scoring {len(symbol_rows)} symbols …")

    upsert_many(
        "supply_chain_scores",
        ["symbol", "date", "supply_chain_score",
         "rail_score", "shipping_score", "trucking_score", "details"],
        symbol_rows,
    )

    print(f"  Stored {len(symbol_rows)} supply chain scores")
    print("=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
