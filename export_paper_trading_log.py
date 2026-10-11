#!/usr/bin/env python3
"""
Export paper trading log from Eventra PostgreSQL database.
Run this script to generate a CSV file for hackathon submission.
"""

import os
import csv
from datetime import datetime
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("Installing psycopg2...")
    os.system("pip install psycopg2-binary")
    import psycopg2
    from psycopg2.extras import RealDictCursor


def export_trading_log():
    """Export all trades with decision and event context."""

    # Get database URL from environment or prompt
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        print("\n" + "=" * 60)
        print("DATABASE_URL not found in environment variables.")
        print("=" * 60)
        print("\nPlease enter your PostgreSQL connection URL:")
        print(
            "(You can find this in Render dashboard → PostgreSQL → Internal Database URL)"
        )
        print("\nFormat: postgres://username:password@hostname:5432/database\n")
        database_url = input("DATABASE_URL: ").strip()

        if not database_url:
            print("\nError: No database URL provided.")
            return False

    print(f"\nConnecting to database...")

    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        print("Connected successfully!\n")

        # Query to get comprehensive trading log
        query = """
        SELECT 
            t.timestamp as trade_timestamp,
            t.decision_id,
            t.symbol,
            t.side,
            t.quantity,
            t.price,
            t.notional,
            t.fee,
            t.slippage,
            e.title as event_title,
            e.source as event_source,
            e.category as event_category,
            e.importance as event_importance,
            d.llm_provider,
            d.status as decision_status,
            d.created_at as decision_timestamp,
            r.status as risk_status,
            r.checks as risk_checks
        FROM trades t
        LEFT JOIN decisions d ON t.decision_id = d.id
        LEFT JOIN events e ON d.event_id = e.id
        LEFT JOIN risk_decisions r ON d.id = r.decision_id
        ORDER BY t.timestamp DESC
        """

        print("Fetching trading data...")
        cursor.execute(query)
        trades = cursor.fetchall()

        if not trades:
            print("\nNo trades found in database.")
            print("The paper trading log is still accumulating.")
            print("Check back after the agent has processed some events.\n")

            # Still export empty structure for reference
            output_file = "paper_trading_log_empty.csv"
            with open(output_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "decision_id",
                        "symbol",
                        "side",
                        "quantity",
                        "price",
                        "notional",
                        "fee",
                        "slippage",
                        "event_title",
                        "event_source",
                        "event_category",
                        "event_importance",
                        "llm_provider",
                        "decision_status",
                        "decision_timestamp",
                        "risk_status",
                        "risk_checks",
                    ]
                )
            print(f"Created empty template: {output_file}")
            return True

        print(f"Found {len(trades)} trades.\n")

        # Export to CSV
        output_file = (
            f"paper_trading_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        with open(output_file, "w", newline="") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(
                [
                    "timestamp",
                    "decision_id",
                    "symbol",
                    "side",
                    "quantity",
                    "price",
                    "notional",
                    "fee",
                    "slippage",
                    "event_title",
                    "event_source",
                    "event_category",
                    "event_importance",
                    "llm_provider",
                    "decision_status",
                    "decision_timestamp",
                    "risk_status",
                    "risk_checks",
                ]
            )

            # Data rows
            for trade in trades:
                writer.writerow(
                    [
                        trade["trade_timestamp"],
                        trade["decision_id"],
                        trade["symbol"],
                        trade["side"],
                        trade["quantity"],
                        trade["price"],
                        trade["notional"],
                        trade["fee"],
                        trade["slippage"],
                        trade["event_title"][:100]
                        if trade["event_title"]
                        else "",  # Truncate long titles
                        trade["event_source"],
                        trade["event_category"],
                        trade["event_importance"],
                        trade["llm_provider"],
                        trade["decision_status"],
                        trade["decision_timestamp"],
                        trade["risk_status"],
                        str(trade["risk_checks"]) if trade["risk_checks"] else "",
                    ]
                )

        print(f"✓ Exported {len(trades)} trades to: {output_file}")
        print(f"✓ File size: {os.path.getsize(output_file)} bytes\n")

        # Also export summary statistics
        print("=" * 60)
        print("SUMMARY STATISTICS")
        print("=" * 60)

        # Total trades
        cursor.execute("SELECT COUNT(*) as count FROM trades")
        total_trades = cursor.fetchone()["count"]
        print(f"Total trades: {total_trades}")

        # Date range
        cursor.execute("""
            SELECT 
                MIN(timestamp) as first_trade,
                MAX(timestamp) as last_trade
            FROM trades
        """)
        date_range = cursor.fetchone()
        if date_range["first_trade"]:
            print(f"First trade: {date_range['first_trade']}")
            print(f"Last trade: {date_range['last_trade']}")

            # Calculate days
            days = (date_range["last_trade"] - date_range["first_trade"]).days
            print(f"Trading period: {days} days")

        # Buy vs Sell
        cursor.execute("""
            SELECT side, COUNT(*) as count 
            FROM trades 
            GROUP BY side
        """)
        sides = cursor.fetchall()
        for side in sides:
            print(f"{side['side'].upper()} trades: {side['count']}")

        # Unique symbols
        cursor.execute("SELECT COUNT(DISTINCT symbol) as count FROM trades")
        symbols = cursor.fetchone()["count"]
        print(f"Unique symbols traded: {symbols}")

        # Total volume
        cursor.execute("SELECT SUM(notional) as total FROM trades")
        volume = cursor.fetchone()["total"]
        if volume:
            print(f"Total volume: ${volume:,.2f}")

        # Total fees
        cursor.execute("SELECT SUM(fee) as total FROM trades")
        fees = cursor.fetchone()["total"]
        if fees:
            print(f"Total fees paid: ${fees:,.2f}")

        print("=" * 60)
        print(f"\n✓ Upload '{output_file}' to GitHub or Google Drive")
        print("✓ Paste the link in your hackathon submission form\n")

        cursor.close()
        conn.close()

        return True

    except psycopg2.Error as e:
        print(f"\n✗ Database error: {e}")
        print("\nTroubleshooting:")
        print("1. Check that DATABASE_URL is correct")
        print("2. Verify the database is running on Render")
        print("3. Make sure your IP is allowed (if using IP whitelist)")
        return False
    except Exception as e:
        print(f"\n✗ Error: {e}")
        return False


def export_portfolio_history():
    """Export portfolio equity curve."""

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return

    try:
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        query = """
        SELECT 
            timestamp,
            value as portfolio_value,
            cash,
            gross_exposure
        FROM equity_points
        ORDER BY timestamp ASC
        """

        cursor.execute(query)
        points = cursor.fetchall()

        if points:
            output_file = (
                f"portfolio_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )

            with open(output_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["timestamp", "portfolio_value", "cash", "gross_exposure"]
                )

                for point in points:
                    writer.writerow(
                        [
                            point["timestamp"],
                            point["portfolio_value"],
                            point["cash"],
                            point["gross_exposure"],
                        ]
                    )

            print(f"✓ Exported {len(points)} equity points to: {output_file}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Could not export portfolio history: {e}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("EVENTRA PAPER TRADING LOG EXPORTER")
    print("=" * 60)

    success = export_trading_log()

    if success:
        export_portfolio_history()
        print("\n" + "=" * 60)
        print("EXPORT COMPLETE")
        print("=" * 60)
    else:
        print("\nExport failed. Please check the error message above.")
