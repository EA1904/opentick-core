import os
import sqlite3
from datetime import datetime

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from tvdata.config import DB_PATH
from tvdata.config import LAKE_ROOT as CONFIG_LAKE_ROOT

LAKE_ROOT = os.path.join(CONFIG_LAKE_ROOT, "ohlcv")


def resample_symbol_data(symbol: str):
    """
    Load 1m data for a symbol and resample it to 15m, 1h, and 4h timeframes.
    Writes resampled data to Parquet partitions and registers in catalog.db.
    """
    symbol = symbol.upper()
    print(f"\n--- Resampling intraday timeframes for: {symbol} ---")

    # 1. Fetch 1m data from parquet lake using DuckDB
    # Since it is partitioned by symbol, we scan exactly that folder
    pattern_1m = os.path.join(
        LAKE_ROOT,
        "asset_class=stocks",
        "timeframe=1m",
        f"symbol={symbol}",
        "**",
        "*.parquet",
    )
    pattern_1m = pattern_1m.replace(os.sep, "/")

    if not os.path.exists(os.path.dirname(pattern_1m.replace("/**/*.parquet", ""))):
        print(f"No local 1m data directory found for {symbol}.")
        return

    db_conn = duckdb.connect(database=":memory:")
    try:
        df_1m = db_conn.execute(
            f"SELECT * FROM parquet_scan('{pattern_1m}', hive_partitioning=true)"
        ).df()
    except Exception as e:
        print(f"Error reading 1m parquet for {symbol}: {e}")
        return
    finally:
        db_conn.close()

    if len(df_1m) == 0:
        print(f"No 1m data rows found for {symbol}.")
        return

    print(f"Loaded {len(df_1m)} rows of 1m data.")

    # Set index as timestamp for pandas resampling
    df_1m["timestamp"] = pd.to_datetime(df_1m["timestamp"])
    df_1m = df_1m.sort_values("timestamp").set_index("timestamp")

    # We define the target timeframes and their pandas resample frequencies
    timeframes = {"15m": "15Min", "1h": "60Min", "4h": "240Min"}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for tf, freq in timeframes.items():
        print(f"  Generating {tf} timeframe...")

        # Resample logic
        # We aggregate Open (first), High (max), Low (min), Close (last), Volume (sum)
        # For metadata fields like symbol, asset_class, source, etc. we take the first value
        resampled = df_1m.resample(freq).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
                "adj_close": "last",
                "adj_factor": "first",
                "source": "first",
                "asset_class": "first",
            }
        )

        # Drop rows where there was no trading activity (resulting in NaN prices)
        resampled = resampled.dropna(subset=["open", "close"])

        if len(resampled) == 0:
            print(f"  No {tf} bars generated (empty output).")
            continue

        # Reset index to bring timestamp back as column
        resampled = resampled.reset_index()

        # Add required partitioning columns
        resampled["timeframe"] = tf
        resampled["symbol"] = symbol
        resampled["year"] = resampled["timestamp"].dt.year.astype("int32")

        # Convert types to standard
        resampled["open"] = resampled["open"].astype(float)
        resampled["high"] = resampled["high"].astype(float)
        resampled["low"] = resampled["low"].astype(float)
        resampled["close"] = resampled["close"].astype(float)
        resampled["volume"] = resampled["volume"].astype(float)
        resampled["adj_close"] = resampled["adj_close"].astype(float)
        resampled["adj_factor"] = resampled["adj_factor"].astype(float)
        resampled["source"] = resampled["source"].astype(str)
        resampled["asset_class"] = resampled["asset_class"].astype(str)
        resampled["timeframe"] = resampled["timeframe"].astype(str)
        resampled["symbol"] = resampled["symbol"].astype(str)

        # Write to Parquet lake
        out_root = LAKE_ROOT
        table = pa.Table.from_pandas(resampled, preserve_index=False)

        # Clean any old parquet files for this symbol/timeframe to avoid duplication
        tf_dir = os.path.join(
            LAKE_ROOT, "asset_class=stocks", f"timeframe={tf}", f"symbol={symbol}"
        )
        if os.path.exists(tf_dir):
            shutil.rmtree(tf_dir)

        pq.write_to_dataset(
            table,
            root_path=out_root,
            partition_cols=["asset_class", "timeframe", "symbol", "year"],
            compression="snappy",
            use_dictionary=True,
            row_group_size=100_000,
        )

        # Calculate stats for the catalog
        min_date = resampled["timestamp"].min().strftime("%Y-%m-%d")
        max_date = resampled["timestamp"].max().strftime("%Y-%m-%d")
        rows_count = len(resampled)

        # Simple quality check
        nulls = resampled["close"].isnull().sum()
        nulls_pct = (nulls / rows_count) * 100.0 if rows_count > 0 else 0.0
        quality_score = max(0.0, 100.0 - (nulls_pct * 2.0))

        # Register/Update in catalog.db
        cursor.execute(
            """
            INSERT OR REPLACE INTO data_catalog (
                symbol, timeframe, asset_class, start_date, end_date, rows_count, nulls_pct, quality_score, source, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                symbol,
                tf,
                "stocks",
                min_date,
                max_date,
                rows_count,
                nulls_pct,
                quality_score,
                resampled["source"].iloc[0] or "resampled_1m",
                datetime.now().isoformat(),
            ),
        )

        print(f"  Saved {rows_count} rows. Registered {tf} in SQLite catalog.")

    conn.commit()
    conn.close()


def resample_all_symbols():
    """Run resampling for all symbols that have 1m data in catalog."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Get all stock symbols that have active 1m data
        rows = cursor.execute("""
            SELECT DISTINCT symbol 
            FROM data_catalog 
            WHERE asset_class = 'stocks' 
              AND timeframe = '1m' 
              AND rows_count > 0
        """).fetchall()
        symbols = [r[0] for r in rows]
    except Exception as e:
        print("Error fetching symbols list:", e)
        return
    finally:
        conn.close()

    print(f"Found {len(symbols)} S&P 500 stocks with local 1m data to resample.")

    # We can process them in batch
    for sym in symbols:
        try:
            resample_symbol_data(sym)
        except Exception as e:
            print(f"Failed to resample {sym}: {e}")


if __name__ == "__main__":
    import shutil

    resample_all_symbols()
