import os
import sqlite3
import time
from datetime import datetime, timedelta

import pandas as pd

from tvdata.ingest.alpaca_connector import ingest_alpaca


def run_alpaca_bulk(timeframe: str = "15m"):
    """
    Query all symbols from catalog.db (symbols_metadata),
    determine the last end_date for each, and ingest new data from Alpaca.
    """
    from tvdata.config import DB_PATH

    db_path = DB_PATH
    if not os.path.exists(db_path):
        print("Database catalog.db not found. Please run initial ingestion first.")
        return

    conn = sqlite3.connect(db_path)
    try:
        symbols_df = pd.read_sql_query("SELECT symbol FROM symbols_metadata", conn)
    except Exception as e:
        print(f"Error reading symbols: {e}")
        conn.close()
        return

    symbols = symbols_df["symbol"].tolist()
    if not symbols:
        print("No symbols found in symbols_metadata.")
        conn.close()
        return

    # Fetch existing catalog end_dates for timeframe to do incremental updates
    try:
        catalog_df = pd.read_sql_query(
            f"SELECT symbol, end_date FROM data_catalog WHERE timeframe = '{timeframe}'",
            conn,
        )
        existing_ends = dict(zip(catalog_df["symbol"], catalog_df["end_date"]))
    except Exception:
        existing_ends = {}

    conn.close()

    print(
        f"Starting bulk Alpaca ingestion for {len(symbols)} stocks (timeframe: {timeframe})..."
    )

    now = datetime.now()
    two_years_ago = now - timedelta(days=2 * 365)
    default_start = two_years_ago.strftime("%Y-%m-%d")
    end_date_str = now.strftime("%Y-%m-%d")

    success_count = 0
    fail_count = 0

    for idx, symbol in enumerate(symbols):
        # Determine start date
        if symbol in existing_ends:
            last_end = pd.to_datetime(existing_ends[symbol])
            start_date_str = (last_end + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            start_date_str = default_start

        print(
            f"[{idx + 1}/{len(symbols)}] Ingesting {symbol} from {start_date_str} to {end_date_str}..."
        )

        try:
            res = ingest_alpaca(symbol, timeframe, start_date_str, end_date_str)
            if res and res.get("rows", 0) > 0:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"Error ingesting {symbol}: {e}")
            fail_count += 1

        # Respect rate limits (Alpaca free tier is 200 API calls per minute or similar)
        time.sleep(0.3)

    print("==================================================")
    print("BULK INGESTION PROCESS COMPLETE")
    print(f"Successfully updated: {success_count} series")
    print(f"Failed or skipped: {fail_count} series")
    print("==================================================")


if __name__ == "__main__":
    run_alpaca_bulk()
