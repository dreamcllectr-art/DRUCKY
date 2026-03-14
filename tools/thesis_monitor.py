"""Thesis Break Monitor — alerts when macro thesis state flips.

Compares today's active thesis set against historical thesis state.
When a thesis that was active N days ago is no longer active (or vice
versa), fires an alert. This prevents the "I forgot to check" failure
mode where a position was entered on a thesis that has since broken.

How it works:
  worldview_signals stores theses PER SYMBOL as JSON arrays in active_theses.
  We aggregate across all symbols to build a thesis-level snapshot:
    {thesis: {symbol_count, avg_score, top_symbols, regime}}
  Then diff against historical snapshots.

Alert Types:
  - THESIS_BROKEN: a thesis that was active N days ago has disappeared
  - THESIS_ACTIVATED: a new thesis has appeared
  - THESIS_WEAKENED: thesis still active but fewer symbols express it
  - THESIS_STRENGTHENED: thesis gaining more symbol expressions

Usage: python -m tools.thesis_monitor
"""

import json
import logging
from datetime import date, timedelta

from tools.db import init_db, get_conn, query, upsert_many

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────
THESIS_LOOKBACK_DAYS = [7, 14, 30]
THESIS_WEAKENED_THRESHOLD = 0.50  # <50% of original symbol count = weakened
THESIS_STRENGTHENED_THRESHOLD = 2.0  # 2x original count = strengthened


# ── DB Table ─────────────────────────────────────────────────────────

def _ensure_tables():
    """Create thesis monitoring tables if needed."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS thesis_snapshots (
            date TEXT,
            thesis TEXT,
            direction TEXT,
            confidence REAL,
            affected_sectors TEXT,
            PRIMARY KEY (date, thesis)
        );
        CREATE TABLE IF NOT EXISTS thesis_alerts (
            date TEXT,
            thesis TEXT,
            alert_type TEXT,
            severity TEXT,
            description TEXT,
            affected_symbols TEXT,
            lookback_days INTEGER,
            old_state TEXT,
            new_state TEXT,
            PRIMARY KEY (date, thesis, alert_type)
        );
    """)
    conn.commit()
    conn.close()


# ── Snapshot ─────────────────────────────────────────────────────────

def _build_thesis_snapshot(target_date: str = None) -> dict:
    """Build thesis-level snapshot from worldview_signals.

    Aggregates per-symbol active_theses JSON into thesis-level metrics.
    Returns: {thesis: {symbol_count, avg_score, regime, top_symbols}}
    """
    if target_date is None:
        target_date = date.today().isoformat()

    # Find closest date <= target
    date_row = query("""
        SELECT MAX(date) as d FROM worldview_signals WHERE date <= ?
    """, [target_date])
    if not date_row or not date_row[0]["d"]:
        return {}

    actual_date = date_row[0]["d"]

    rows = query("""
        SELECT symbol, active_theses, thesis_alignment_score, regime
        FROM worldview_signals
        WHERE date = ?
    """, [actual_date])

    if not rows:
        return {}

    # Aggregate by thesis
    thesis_data = {}
    regime = rows[0]["regime"] if rows else "neutral"

    for r in rows:
        theses_raw = r.get("active_theses", "[]")
        score = r.get("thesis_alignment_score", 0) or 0
        symbol = r["symbol"]

        try:
            theses = json.loads(theses_raw) if isinstance(theses_raw, str) else []
        except (json.JSONDecodeError, TypeError):
            theses = []

        for thesis in theses:
            if thesis not in thesis_data:
                thesis_data[thesis] = {
                    "symbol_count": 0,
                    "total_score": 0.0,
                    "top_symbols": [],
                    "regime": regime,
                    "date": actual_date,
                }
            thesis_data[thesis]["symbol_count"] += 1
            thesis_data[thesis]["total_score"] += score
            if len(thesis_data[thesis]["top_symbols"]) < 5:
                thesis_data[thesis]["top_symbols"].append(
                    {"symbol": symbol, "score": score})

    # Compute averages and sort top symbols
    for thesis, data in thesis_data.items():
        if data["symbol_count"] > 0:
            data["avg_score"] = round(
                data["total_score"] / data["symbol_count"], 1)
        else:
            data["avg_score"] = 0.0
        data["top_symbols"].sort(key=lambda x: -x["score"])
        del data["total_score"]  # Don't need this in the snapshot

    return thesis_data


def _take_and_persist_snapshot() -> dict:
    """Take today's snapshot and persist to thesis_snapshots table."""
    today = date.today().isoformat()
    snapshot = _build_thesis_snapshot(today)

    if snapshot:
        snap_rows = []
        for thesis, data in snapshot.items():
            snap_rows.append((
                today,
                thesis,
                "active",  # direction: active means thesis is firing
                data["avg_score"],  # confidence = avg alignment score
                json.dumps({
                    "symbol_count": data["symbol_count"],
                    "top_symbols": data["top_symbols"],
                    "regime": data["regime"],
                }),
            ))
        upsert_many(
            "thesis_snapshots",
            ["date", "thesis", "direction", "confidence", "affected_sectors"],
            snap_rows,
        )

    return snapshot


# ── Diff & Alert ─────────────────────────────────────────────────────

def _find_affected_stocks(thesis: str) -> list[str]:
    """Find current HIGH/NOTABLE stocks expressing this thesis."""
    rows = query("""
        SELECT ws.symbol
        FROM worldview_signals ws
        JOIN convergence_signals cs ON ws.symbol = cs.symbol
        WHERE ws.date = (SELECT MAX(date) FROM worldview_signals)
          AND cs.date = (SELECT MAX(date) FROM convergence_signals)
          AND cs.conviction_level IN ('HIGH', 'NOTABLE')
          AND ws.active_theses LIKE ?
        ORDER BY cs.convergence_score DESC
        LIMIT 20
    """, [f'%{thesis}%'])

    return [r["symbol"] for r in rows]


def _diff_snapshots(current: dict, historical: dict, lookback: int) -> list[dict]:
    """Compare current vs historical thesis snapshot and generate alerts."""
    alerts = []
    all_theses = set(list(current.keys()) + list(historical.keys()))

    for thesis in all_theses:
        curr = current.get(thesis)
        hist = historical.get(thesis)

        if hist and not curr:
            # THESIS BROKEN — was active, now gone
            affected = _find_affected_stocks(thesis)
            hist_count = hist.get("symbol_count", 0)
            hist_score = hist.get("avg_score", 0)
            severity = "CRITICAL" if hist_count >= 10 else "WARNING"
            alerts.append({
                "thesis": thesis,
                "alert_type": "THESIS_BROKEN",
                "severity": severity,
                "description": (
                    f"Thesis '{thesis}' was active {lookback}d ago "
                    f"({hist_count} symbols, avg_score={hist_score:.0f}) "
                    f"but is NO LONGER ACTIVE. Review positions."
                ),
                "affected_symbols": json.dumps(affected),
                "lookback_days": lookback,
                "old_state": json.dumps(hist),
                "new_state": "INACTIVE",
            })

        elif curr and not hist:
            # THESIS ACTIVATED — new thesis
            affected = _find_affected_stocks(thesis)
            curr_count = curr.get("symbol_count", 0)
            curr_score = curr.get("avg_score", 0)
            alerts.append({
                "thesis": thesis,
                "alert_type": "THESIS_ACTIVATED",
                "severity": "INFO",
                "description": (
                    f"NEW thesis '{thesis}' activated "
                    f"({curr_count} symbols, avg_score={curr_score:.0f}). "
                    f"Potential new opportunities."
                ),
                "affected_symbols": json.dumps(affected),
                "lookback_days": lookback,
                "old_state": "INACTIVE",
                "new_state": json.dumps(curr),
            })

        elif curr and hist:
            # Both active — check for weakening or strengthening
            old_count = hist.get("symbol_count", 1)
            new_count = curr.get("symbol_count", 0)
            old_score = hist.get("avg_score", 0)
            new_score = curr.get("avg_score", 0)

            ratio = new_count / old_count if old_count > 0 else 1.0

            if ratio <= THESIS_WEAKENED_THRESHOLD and old_count >= 5:
                affected = _find_affected_stocks(thesis)
                alerts.append({
                    "thesis": thesis,
                    "alert_type": "THESIS_WEAKENED",
                    "severity": "WARNING",
                    "description": (
                        f"Thesis '{thesis}' WEAKENING: "
                        f"{old_count} → {new_count} symbols "
                        f"(avg_score {old_score:.0f} → {new_score:.0f}) "
                        f"over {lookback}d. Thesis losing conviction."
                    ),
                    "affected_symbols": json.dumps(affected),
                    "lookback_days": lookback,
                    "old_state": json.dumps(hist),
                    "new_state": json.dumps(curr),
                })
            elif ratio >= THESIS_STRENGTHENED_THRESHOLD and new_count >= 10:
                affected = _find_affected_stocks(thesis)
                alerts.append({
                    "thesis": thesis,
                    "alert_type": "THESIS_STRENGTHENED",
                    "severity": "INFO",
                    "description": (
                        f"Thesis '{thesis}' STRENGTHENING: "
                        f"{old_count} → {new_count} symbols "
                        f"(avg_score {old_score:.0f} → {new_score:.0f}) "
                        f"over {lookback}d. More stocks aligning."
                    ),
                    "affected_symbols": json.dumps(affected),
                    "lookback_days": lookback,
                    "old_state": json.dumps(hist),
                    "new_state": json.dumps(curr),
                })

    return alerts


# ── Email Alert ──────────────────────────────────────────────────────

def _build_alert_email(alerts: list[dict]) -> str:
    """Build HTML email for thesis break alerts."""
    critical = [a for a in alerts if a["severity"] == "CRITICAL"]
    warning = [a for a in alerts if a["severity"] == "WARNING"]
    info = [a for a in alerts if a["severity"] == "INFO"]

    html = f"""
    <html><body style="font-family: -apple-system, sans-serif; background:#0E1117; color:#E0E0E0; padding:20px;">
    <h1 style="color:white;">Thesis Monitor Alert</h1>
    <p style="color:#888;">{date.today().strftime('%B %d, %Y')}</p>
    """

    if critical:
        html += '<div style="background:#2a1a1a; border-left:4px solid #FF1744; padding:16px; margin:12px 0; border-radius:4px;">'
        html += f'<h2 style="color:#FF1744; margin-top:0;">CRITICAL ({len(critical)})</h2>'
        for a in critical:
            symbols = json.loads(a["affected_symbols"]) if a["affected_symbols"] else []
            sym_str = ", ".join(symbols[:10]) if symbols else "none identified"
            html += f"""
            <div style="margin:12px 0; padding:8px; background:#1a1111; border-radius:4px;">
                <p style="color:#FF8A65; font-weight:600; margin:0;">{a['alert_type']}: {a['thesis']}</p>
                <p style="color:#CCC; margin:4px 0;">{a['description']}</p>
                <p style="color:#888; font-size:12px; margin:2px 0;">Affected: {sym_str}</p>
            </div>"""
        html += '</div>'

    if warning:
        html += '<div style="background:#2a2a1a; border-left:4px solid #FFD54F; padding:16px; margin:12px 0; border-radius:4px;">'
        html += f'<h2 style="color:#FFD54F; margin-top:0;">WARNING ({len(warning)})</h2>'
        for a in warning:
            html += f"""
            <div style="margin:8px 0;">
                <p style="color:#FFD54F; font-weight:600; margin:0;">{a['alert_type']}: {a['thesis']}</p>
                <p style="color:#CCC; margin:4px 0;">{a['description']}</p>
            </div>"""
        html += '</div>'

    if info:
        html += '<div style="background:#1a2a1a; border-left:4px solid #69F0AE; padding:16px; margin:12px 0; border-radius:4px;">'
        html += f'<h2 style="color:#69F0AE; margin-top:0;">THESIS CHANGES ({len(info)})</h2>'
        for a in info:
            html += f"""
            <div style="margin:8px 0;">
                <p style="color:#69F0AE; font-weight:600; margin:0;">{a['alert_type']}: {a['thesis']}</p>
                <p style="color:#CCC; margin:4px 0;">{a['description']}</p>
            </div>"""
        html += '</div>'

    html += "</body></html>"
    return html


# ── Main ─────────────────────────────────────────────────────────────

def run():
    """Run thesis monitoring — compare current vs historical thesis state."""
    init_db()
    _ensure_tables()
    today = date.today().isoformat()

    print("\n" + "=" * 60)
    print("  THESIS BREAK MONITOR")
    print("=" * 60)

    # Take current snapshot (aggregated from worldview_signals)
    current = _take_and_persist_snapshot()
    print(f"  Active theses today: {len(current)}")
    for thesis, data in current.items():
        top = ", ".join(s["symbol"] for s in data.get("top_symbols", [])[:3])
        print(f"    {thesis}: {data['symbol_count']} symbols, "
              f"avg_score={data['avg_score']:.0f} (top: {top})")

    # Compare against historical snapshots
    all_alerts = []
    for lookback in THESIS_LOOKBACK_DAYS:
        target = (date.today() - timedelta(days=lookback)).isoformat()
        historical = _build_thesis_snapshot(target)
        if not historical:
            print(f"  No historical data for {lookback}d lookback — skipping")
            continue

        alerts = _diff_snapshots(current, historical, lookback)
        all_alerts.extend(alerts)
        print(f"  {lookback}d comparison: {len(alerts)} alerts")

    # Deduplicate (same thesis + alert_type, keep shortest lookback)
    seen = set()
    deduped = []
    for a in sorted(all_alerts, key=lambda x: x["lookback_days"]):
        key = (a["thesis"], a["alert_type"])
        if key not in seen:
            seen.add(key)
            deduped.append(a)

    all_alerts = deduped

    # Persist alerts
    if all_alerts:
        alert_rows = [
            (today, a["thesis"], a["alert_type"], a["severity"],
             a["description"], a["affected_symbols"], a["lookback_days"],
             a["old_state"], a["new_state"])
            for a in all_alerts
        ]
        upsert_many(
            "thesis_alerts",
            ["date", "thesis", "alert_type", "severity", "description",
             "affected_symbols", "lookback_days", "old_state", "new_state"],
            alert_rows,
        )

    # Print summary
    critical = sum(1 for a in all_alerts if a["severity"] == "CRITICAL")
    warning = sum(1 for a in all_alerts if a["severity"] == "WARNING")
    info = sum(1 for a in all_alerts if a["severity"] == "INFO")

    print(f"\n  Total alerts: {len(all_alerts)}")
    print(f"  CRITICAL: {critical} | WARNING: {warning} | INFO: {info}")

    if critical > 0:
        print("\n  *** CRITICAL THESIS BREAKS ***")
        for a in all_alerts:
            if a["severity"] == "CRITICAL":
                symbols = json.loads(a["affected_symbols"]) if a["affected_symbols"] else []
                sym_str = ", ".join(symbols[:5])
                print(f"    {a['alert_type']}: {a['thesis']}")
                print(f"      {a['description']}")
                if sym_str:
                    print(f"      Affected: {sym_str}")

    # Send email for critical alerts
    if critical > 0:
        try:
            from tools.config import SMTP_USER, SMTP_PASS, EMAIL_TO
            if SMTP_USER and SMTP_PASS and EMAIL_TO:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                email_html = _build_alert_email(all_alerts)
                msg = MIMEMultipart("alternative")
                msg["From"] = SMTP_USER
                msg["To"] = EMAIL_TO
                msg["Subject"] = (
                    f"THESIS ALERT: {critical} critical break(s) "
                    f"— {date.today().strftime('%b %d')}"
                )
                msg.attach(MIMEText(email_html, "html"))
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(SMTP_USER, SMTP_PASS)
                    server.send_message(msg)
                print("  Thesis alert email sent.")
        except Exception as e:
            print(f"  Email alert failed: {e}")

    print("=" * 60)
    return all_alerts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    run()
