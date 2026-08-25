from datetime import datetime

import pandas as pd

from tvdata.catalog import get_all_datasets, recalculate_catalog_entry
from tvdata.ingest.binance_connector import ingest_binance
from tvdata.ingest.yfinance_connector import ingest_yfinance


def update_data_lake(symbols: list = None, asset_classes: list = None):
    """
    Scans the SQLite data catalog and incrementally updates datasets
    (optionally filtered by symbols or asset_classes) from their last end_date
    to today using external API connectors.
    """
    print("==================================================")
    print("STARTING INCREMENTAL DATA LAKE UPDATE")
    print("==================================================")

    datasets = get_all_datasets()
    if len(datasets) == 0:
        print(
            "No datasets registered in data_catalog yet. Please run initial ingestion first."
        )
        return

    # Apply filtering
    if symbols:
        symbols_upper = [s.upper() for s in symbols]
        datasets = datasets[datasets["symbol"].str.upper().isin(symbols_upper)]

    if asset_classes:
        asset_classes_lower = [a.lower() for a in asset_classes]
        datasets = datasets[
            datasets["asset_class"].str.lower().isin(asset_classes_lower)
        ]

    if len(datasets) == 0:
        print("No matching datasets found in catalog after filtering.")
        return

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"Current local time for update: {now_str}")

    count_success = 0
    count_skipped = 0

    for idx, row in datasets.iterrows():
        symbol = row["symbol"]
        timeframe = row["timeframe"]
        asset_class = row["asset_class"]
        end_date_str = row["end_date"]
        source = row["source"]

        # Macro data is updated on demand, not in standard market auto-update
        if asset_class == "macro" or source == "dolt_rates":
            count_skipped += 1
            continue

        try:
            end_dt = pd.to_datetime(end_date_str)

            # Compute start of update range with offset to avoid duplicates
            if timeframe == "D1":
                start_update = end_dt + pd.Timedelta(days=1)
                start_str = start_update.strftime("%Y-%m-%d")
                end_str = now.strftime("%Y-%m-%d")
            elif timeframe in ["1h", "4h"]:
                start_update = end_dt + pd.Timedelta(hours=1)
                start_str = start_update.strftime("%Y-%m-%d %H:%M:%S")
                end_str = now.strftime("%Y-%m-%d %H:%M:%S")
            elif timeframe in ["1m", "2m", "5m", "15m", "30m"]:
                start_update = end_dt + pd.Timedelta(minutes=1)
                start_str = start_update.strftime("%Y-%m-%d %H:%M:%S")
                end_str = now.strftime("%Y-%m-%d %H:%M:%S")
            else:
                start_update = end_dt + pd.Timedelta(seconds=1)
                start_str = start_update.strftime("%Y-%m-%d %H:%M:%S")
                end_str = now.strftime("%Y-%m-%d %H:%M:%S")

            # If last data point is in the future relative to system clock or today, skip
            if start_update >= now:
                print(
                    f"Skipping {symbol} ({timeframe}): already up-to-date (end_date: {end_date_str})"
                )
                count_skipped += 1
                continue

            print(f"\nUpdating {symbol} ({timeframe}) from {start_str} to {end_str}...")

            # Select appropriate connector
            res = {}
            if asset_class == "crypto":
                res = ingest_binance(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_str,
                    end_date=end_str,
                )
            else:
                # yfinance stocks or forex (forex symbols are converted to symbol=X by connector)
                source_tz = "UTC" if asset_class == "forex" else "America/New_York"
                res = ingest_yfinance(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_str,
                    end_date=end_str,
                    asset_class=asset_class,
                    source_tz=source_tz,
                )

            if res and res.get("rows", 0) > 0:
                # Consolidate catalog stats based on all written Parquet files
                recalculate_catalog_entry(
                    symbol=symbol,
                    timeframe=timeframe,
                    asset_class=asset_class,
                    source=source,
                )
                count_success += 1
            else:
                print(f"No new rows added for {symbol} ({timeframe}).")
                count_skipped += 1

        except Exception as e:
            print(f"Failed to update {symbol} ({timeframe}): {e}")
            count_skipped += 1

    print("\n==================================================")
    print(
        f"UPDATE PROCESS COMPLETE. {count_success} series updated, {count_skipped} skipped/up-to-date."
    )
    print("==================================================")


if __name__ == "__main__":
    update_data_lake()
