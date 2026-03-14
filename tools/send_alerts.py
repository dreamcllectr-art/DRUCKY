"""Email alert sender via Gmail SMTP."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from tools.config import SMTP_USER, SMTP_PASS, EMAIL_TO
from tools.db import query_df


def build_daily_summary():
    """Build HTML email with daily scan summary."""
    # Get macro regime
    macro = query_df("SELECT * FROM macro_scores ORDER BY date DESC LIMIT 1")
    regime = macro.iloc[0]["regime"] if not macro.empty else "unknown"
    macro_score = float(macro.iloc[0]["total_score"]) if not macro.empty else 0

    # Get top signals
    buys = query_df("""
        SELECT s.* FROM signals s
        INNER JOIN (SELECT symbol, MAX(date) as max_date FROM signals GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.max_date
        WHERE s.signal IN ('STRONG BUY', 'BUY')
        ORDER BY s.composite_score DESC
        LIMIT 20
    """)

    sells = query_df("""
        SELECT s.* FROM signals s
        INNER JOIN (SELECT symbol, MAX(date) as max_date FROM signals GROUP BY symbol) m
        ON s.symbol = m.symbol AND s.date = m.max_date
        WHERE s.signal IN ('STRONG SELL', 'SELL')
        ORDER BY s.composite_score ASC
        LIMIT 10
    """)

    # Build HTML
    regime_colors = {
        "strong_risk_on": "#00C853", "risk_on": "#69F0AE",
        "neutral": "#FFD54F", "risk_off": "#FF8A65", "strong_risk_off": "#FF1744",
    }
    r_color = regime_colors.get(regime, "#FFD54F")

    html = f"""
    <html><body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; background:#0E1117; color:#E0E0E0; padding:20px;">
    <h1 style="color:white;">Druckenmiller Alpha - Daily Scan</h1>
    <p style="color:#888;">{datetime.now().strftime('%B %d, %Y')}</p>

    <div style="background:#1e2130; padding:16px; border-radius:8px; margin:16px 0;">
        <h2 style="color:white; margin-top:0;">Macro Regime:
            <span style="color:{r_color};">{regime.replace('_', ' ').upper()} ({macro_score:+.0f})</span>
        </h2>
    </div>
    """

    if not buys.empty:
        html += '<h2 style="color:#00C853;">Top Buy Signals</h2>'
        html += '<table style="width:100%; border-collapse:collapse; color:#E0E0E0;">'
        html += '<tr style="border-bottom:1px solid #333;"><th>Symbol</th><th>Signal</th><th>Score</th><th>Entry</th><th>Stop</th><th>Target</th><th>R:R</th></tr>'
        for _, row in buys.iterrows():
            sig_color = "#00C853" if row["signal"] == "STRONG BUY" else "#69F0AE"
            html += f"""
            <tr style="border-bottom:1px solid #1e2130;">
                <td style="padding:8px;"><b>{row['symbol']}</b></td>
                <td style="color:{sig_color};">{row['signal']}</td>
                <td>{row['composite_score']:.1f}</td>
                <td>${row['entry_price']:,.2f}</td>
                <td>${row['stop_loss']:,.2f}</td>
                <td>${row['target_price']:,.2f}</td>
                <td>{row['rr_ratio']:.1f}</td>
            </tr>"""
        html += '</table>'

    if not sells.empty:
        html += '<h2 style="color:#FF1744;">Top Sell Signals</h2>'
        html += '<table style="width:100%; border-collapse:collapse; color:#E0E0E0;">'
        html += '<tr style="border-bottom:1px solid #333;"><th>Symbol</th><th>Signal</th><th>Score</th></tr>'
        for _, row in sells.iterrows():
            html += f"""
            <tr style="border-bottom:1px solid #1e2130;">
                <td style="padding:8px;"><b>{row['symbol']}</b></td>
                <td style="color:#FF1744;">{row['signal']}</td>
                <td>{row['composite_score']:.1f}</td>
            </tr>"""
        html += '</table>'

    html += """
    <p style="color:#666; margin-top:20px; font-size:12px;">
        Launch dashboard for full analysis: <code>streamlit run dashboard/app.py</code>
    </p>
    </body></html>
    """
    return html


def send_alert_email(triggered_alerts=None):
    """Send email with daily summary and/or triggered alerts."""
    if not SMTP_USER or not SMTP_PASS or not EMAIL_TO:
        print("  Email not configured. Set SMTP_USER, SMTP_PASS, EMAIL_TO in .env")
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = f"Druckenmiller Alpha - {datetime.now().strftime('%b %d')} Scan"

    html = build_daily_summary()

    # Add triggered alerts if any
    if triggered_alerts:
        html = html.replace("</body>", "")
        html += '<h2 style="color:#FFD54F;">Watchlist Alerts Triggered</h2>'
        for alert in triggered_alerts:
            html += f'<p><b>{alert["symbol"]}</b>: {" | ".join(alert["alerts"])}</p>'
            if alert.get("notes"):
                html += f'<p style="color:#888;">Notes: {alert["notes"]}</p>'
        html += "</body></html>"

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print("  Email alert sent successfully.")
    except Exception as e:
        print(f"  Email send failed: {e}")


def run():
    """Send daily summary email."""
    send_alert_email()


if __name__ == "__main__":
    run()
