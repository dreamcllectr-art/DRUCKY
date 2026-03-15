"""Thesis Break Monitor — alerts when macro thesis state flips.
Compares today's active thesis set against historical snapshots.
Alert types: THESIS_BROKEN, THESIS_ACTIVATED, THESIS_WEAKENED, THESIS_STRENGTHENED."""
import json, logging
from datetime import date, timedelta
from tools.db import init_db, get_conn, query, upsert_many
logger = logging.getLogger(__name__)
THESIS_LOOKBACK_DAYS = [7, 14, 30]
THESIS_WEAKENED_THRESHOLD, THESIS_STRENGTHENED_THRESHOLD = 0.50, 2.0

def _ensure_tables():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS thesis_snapshots (date TEXT, thesis TEXT, direction TEXT,
            confidence REAL, affected_sectors TEXT, PRIMARY KEY (date, thesis));
        CREATE TABLE IF NOT EXISTS thesis_alerts (date TEXT, thesis TEXT, alert_type TEXT, severity TEXT,
            description TEXT, affected_symbols TEXT, lookback_days INTEGER, old_state TEXT, new_state TEXT,
            PRIMARY KEY (date, thesis, alert_type));""")
    conn.commit(); conn.close()

def _build_thesis_snapshot(target_date=None):
    if target_date is None: target_date = date.today().isoformat()
    date_row = query("SELECT MAX(date) as d FROM worldview_signals WHERE date <= ?", [target_date])
    if not date_row or not date_row[0]["d"]: return {}
    rows = query("SELECT symbol, active_theses, thesis_alignment_score, regime FROM worldview_signals WHERE date = ?", [date_row[0]["d"]])
    if not rows: return {}
    thesis_data, regime = {}, rows[0]["regime"] if rows else "neutral"
    for r in rows:
        score = r.get("thesis_alignment_score", 0) or 0
        try: theses = json.loads(r.get("active_theses", "[]")) if isinstance(r.get("active_theses"), str) else []
        except (json.JSONDecodeError, TypeError): theses = []
        for thesis in theses:
            if thesis not in thesis_data:
                thesis_data[thesis] = {"symbol_count": 0, "total_score": 0.0, "top_symbols": [], "regime": regime, "date": date_row[0]["d"]}
            thesis_data[thesis]["symbol_count"] += 1
            thesis_data[thesis]["total_score"] += score
            if len(thesis_data[thesis]["top_symbols"]) < 5:
                thesis_data[thesis]["top_symbols"].append({"symbol": r["symbol"], "score": score})
    for data in thesis_data.values():
        data["avg_score"] = round(data["total_score"] / data["symbol_count"], 1) if data["symbol_count"] > 0 else 0.0
        data["top_symbols"].sort(key=lambda x: -x["score"])
        del data["total_score"]
    return thesis_data

def _take_and_persist_snapshot():
    today = date.today().isoformat()
    snapshot = _build_thesis_snapshot(today)
    if snapshot:
        upsert_many("thesis_snapshots", ["date", "thesis", "direction", "confidence", "affected_sectors"],
            [(today, thesis, "active", d["avg_score"], json.dumps({"symbol_count": d["symbol_count"], "top_symbols": d["top_symbols"], "regime": d["regime"]})) for thesis, d in snapshot.items()])
    return snapshot

def _find_affected_stocks(thesis):
    rows = query("""SELECT ws.symbol FROM worldview_signals ws JOIN convergence_signals cs ON ws.symbol = cs.symbol
        WHERE ws.date = (SELECT MAX(date) FROM worldview_signals) AND cs.date = (SELECT MAX(date) FROM convergence_signals)
        AND cs.conviction_level IN ('HIGH', 'NOTABLE') AND ws.active_theses LIKE ? ORDER BY cs.convergence_score DESC LIMIT 20""", [f'%{thesis}%'])
    return [r["symbol"] for r in rows]

def _diff_snapshots(current, historical, lookback):
    alerts = []
    for thesis in set(list(current.keys()) + list(historical.keys())):
        curr, hist = current.get(thesis), historical.get(thesis)
        if hist and not curr:
            affected = _find_affected_stocks(thesis)
            sev = "CRITICAL" if hist.get("symbol_count", 0) >= 10 else "WARNING"
            alerts.append({"thesis": thesis, "alert_type": "THESIS_BROKEN", "severity": sev,
                "description": f"Thesis '{thesis}' was active {lookback}d ago ({hist.get('symbol_count',0)} symbols, avg_score={hist.get('avg_score',0):.0f}) but is NO LONGER ACTIVE.",
                "affected_symbols": json.dumps(affected), "lookback_days": lookback, "old_state": json.dumps(hist), "new_state": "INACTIVE"})
        elif curr and not hist:
            affected = _find_affected_stocks(thesis)
            alerts.append({"thesis": thesis, "alert_type": "THESIS_ACTIVATED", "severity": "INFO",
                "description": f"NEW thesis '{thesis}' activated ({curr.get('symbol_count',0)} symbols, avg_score={curr.get('avg_score',0):.0f}).",
                "affected_symbols": json.dumps(affected), "lookback_days": lookback, "old_state": "INACTIVE", "new_state": json.dumps(curr)})
        elif curr and hist:
            oc, nc = hist.get("symbol_count", 1), curr.get("symbol_count", 0)
            os, ns = hist.get("avg_score", 0), curr.get("avg_score", 0)
            ratio = nc / oc if oc > 0 else 1.0
            if ratio <= THESIS_WEAKENED_THRESHOLD and oc >= 5:
                alerts.append({"thesis": thesis, "alert_type": "THESIS_WEAKENED", "severity": "WARNING",
                    "description": f"Thesis '{thesis}' WEAKENING: {oc} -> {nc} symbols (avg {os:.0f} -> {ns:.0f}) over {lookback}d.",
                    "affected_symbols": json.dumps(_find_affected_stocks(thesis)), "lookback_days": lookback, "old_state": json.dumps(hist), "new_state": json.dumps(curr)})
            elif ratio >= THESIS_STRENGTHENED_THRESHOLD and nc >= 10:
                alerts.append({"thesis": thesis, "alert_type": "THESIS_STRENGTHENED", "severity": "INFO",
                    "description": f"Thesis '{thesis}' STRENGTHENING: {oc} -> {nc} symbols (avg {os:.0f} -> {ns:.0f}) over {lookback}d.",
                    "affected_symbols": json.dumps(_find_affected_stocks(thesis)), "lookback_days": lookback, "old_state": json.dumps(hist), "new_state": json.dumps(curr)})
    return alerts

def _build_alert_email(alerts):
    critical = [a for a in alerts if a["severity"] == "CRITICAL"]
    warning = [a for a in alerts if a["severity"] == "WARNING"]
    info = [a for a in alerts if a["severity"] == "INFO"]
    html = f'<html><body style="font-family:-apple-system,sans-serif;background:#0E1117;color:#E0E0E0;padding:20px;">'
    html += f'<h1 style="color:white;">Thesis Monitor Alert</h1><p style="color:#888;">{date.today().strftime("%B %d, %Y")}</p>'
    for items, color, bg, title in [(critical, "#FF1744", "#2a1a1a", "CRITICAL"), (warning, "#FFD54F", "#2a2a1a", "WARNING"), (info, "#69F0AE", "#1a2a1a", "CHANGES")]:
        if not items: continue
        html += f'<div style="background:{bg};border-left:4px solid {color};padding:16px;margin:12px 0;border-radius:4px;"><h2 style="color:{color};margin-top:0;">{title} ({len(items)})</h2>'
        for a in items:
            symbols = json.loads(a["affected_symbols"]) if a["affected_symbols"] else []
            html += f'<div style="margin:8px 0;"><p style="color:{color};font-weight:600;margin:0;">{a["alert_type"]}: {a["thesis"]}</p><p style="color:#CCC;margin:4px 0;">{a["description"]}</p>'
            if symbols and title == "CRITICAL": html += f'<p style="color:#888;font-size:12px;">Affected: {", ".join(symbols[:10])}</p>'
            html += '</div>'
        html += '</div>'
    html += '</body></html>'
    return html

def run():
    init_db(); _ensure_tables(); today = date.today().isoformat()
    print("\n" + "=" * 60 + "\n  THESIS BREAK MONITOR\n" + "=" * 60)
    current = _take_and_persist_snapshot()
    print(f"  Active theses today: {len(current)}")
    for thesis, data in current.items():
        top = ", ".join(s["symbol"] for s in data.get("top_symbols", [])[:3])
        print(f"    {thesis}: {data['symbol_count']} symbols, avg_score={data['avg_score']:.0f} (top: {top})")
    all_alerts = []
    for lookback in THESIS_LOOKBACK_DAYS:
        target = (date.today() - timedelta(days=lookback)).isoformat()
        historical = _build_thesis_snapshot(target)
        if not historical: print(f"  No historical data for {lookback}d lookback"); continue
        alerts = _diff_snapshots(current, historical, lookback)
        all_alerts.extend(alerts)
        print(f"  {lookback}d comparison: {len(alerts)} alerts")
    seen, deduped = set(), []
    for a in sorted(all_alerts, key=lambda x: x["lookback_days"]):
        key = (a["thesis"], a["alert_type"])
        if key not in seen: seen.add(key); deduped.append(a)
    all_alerts = deduped
    if all_alerts:
        upsert_many("thesis_alerts", ["date", "thesis", "alert_type", "severity", "description", "affected_symbols", "lookback_days", "old_state", "new_state"],
            [(today, a["thesis"], a["alert_type"], a["severity"], a["description"], a["affected_symbols"], a["lookback_days"], a["old_state"], a["new_state"]) for a in all_alerts])
    crit = sum(1 for a in all_alerts if a["severity"] == "CRITICAL")
    warn = sum(1 for a in all_alerts if a["severity"] == "WARNING")
    inf = sum(1 for a in all_alerts if a["severity"] == "INFO")
    print(f"\n  Total alerts: {len(all_alerts)} | CRITICAL: {crit} | WARNING: {warn} | INFO: {inf}")
    if crit > 0:
        print("\n  *** CRITICAL THESIS BREAKS ***")
        for a in all_alerts:
            if a["severity"] == "CRITICAL":
                syms = json.loads(a["affected_symbols"]) if a["affected_symbols"] else []
                print(f"    {a['alert_type']}: {a['thesis']}\n      {a['description']}")
                if syms: print(f"      Affected: {', '.join(syms[:5])}")
    if crit > 0:
        try:
            from tools.config import SMTP_USER, SMTP_PASS, EMAIL_TO
            if SMTP_USER and SMTP_PASS and EMAIL_TO:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart
                msg = MIMEMultipart("alternative")
                msg["From"], msg["To"] = SMTP_USER, EMAIL_TO
                msg["Subject"] = f"THESIS ALERT: {crit} critical break(s) — {date.today().strftime('%b %d')}"
                msg.attach(MIMEText(_build_alert_email(all_alerts), "html"))
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(SMTP_USER, SMTP_PASS); server.send_message(msg)
                print("  Thesis alert email sent.")
        except Exception as e: print(f"  Email alert failed: {e}")
    print("=" * 60)
    return all_alerts

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO); init_db(); run()
