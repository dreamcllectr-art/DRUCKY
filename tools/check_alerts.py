"""Check watchlist alert rules against current data."""

from tools.db import init_db, query_df, query


def run():
    """Evaluate all alert rules and return triggered alerts."""
    init_db()
    print("Checking alert rules...")

    watchlist = query_df("SELECT * FROM watchlist")
    if watchlist.empty:
        print("  No watchlist items.")
        return []

    triggered = []

    for _, item in watchlist.iterrows():
        symbol = item["symbol"]
        alerts = []

        # Check technical score alert
        if item["alert_tech_above"] is not None:
            tech = query_df("""
                SELECT total_score FROM technical_scores
                WHERE symbol = ? ORDER BY date DESC LIMIT 1
            """, [symbol])
            if not tech.empty:
                score = float(tech.iloc[0]["total_score"])
                threshold = float(item["alert_tech_above"])
                if score >= threshold:
                    alerts.append(f"Technical score {score:.0f} >= {threshold:.0f}")

        # Check price alerts
        price = query_df("""
            SELECT close FROM price_data WHERE symbol = ?
            ORDER BY date DESC LIMIT 1
        """, [symbol])

        if not price.empty:
            current = float(price.iloc[0]["close"])

            if item["alert_price_above"] is not None:
                threshold = float(item["alert_price_above"])
                if current >= threshold:
                    alerts.append(f"Price ${current:,.2f} >= ${threshold:,.2f}")

            if item["alert_price_below"] is not None:
                threshold = float(item["alert_price_below"])
                if current <= threshold:
                    alerts.append(f"Price ${current:,.2f} <= ${threshold:,.2f}")

        if alerts:
            triggered.append({
                "symbol": symbol,
                "alerts": alerts,
                "notes": item.get("notes", ""),
            })

    if triggered:
        print(f"\n  TRIGGERED ALERTS ({len(triggered)}):")
        for t in triggered:
            print(f"    {t['symbol']}: {' | '.join(t['alerts'])}")
            if t["notes"]:
                print(f"      Notes: {t['notes']}")

        # Send email if configured
        try:
            from tools.send_alerts import send_alert_email
            send_alert_email(triggered)
        except Exception as e:
            print(f"  Email alert failed: {e}")
    else:
        print("  No alerts triggered.")

    return triggered


if __name__ == "__main__":
    run()
