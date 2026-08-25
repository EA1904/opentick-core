import os
import subprocess
import time

import duckdb

DOLT_PATH = r"C:\Program Files\Dolt\bin\dolt.exe"
from tvdata.config import LAKE_ROOT, WORKSPACE_ROOT

OPTIONS_REPO = os.path.join(WORKSPACE_ROOT, "raw", "dolt", "options")
LAKE_DIR = LAKE_ROOT


def run_fast_ingest():
    start_time = time.time()
    print("==================================================")
    print("STARTING FAST OPTION INGESTION PIPELINE (DUCKDB)")
    print("==================================================")

    # 1. Export tables from Dolt to Parquet
    vol_parquet = os.path.join(OPTIONS_REPO, "volatility_history.parquet")
    chain_parquet = os.path.join(OPTIONS_REPO, "option_chain.parquet")

    print("\n[Step 1/4] Exporting volatility_history from Dolt to Parquet...")
    if not os.path.exists(vol_parquet):
        cmd_vol = [
            DOLT_PATH,
            "table",
            "export",
            "-f",
            "volatility_history",
            vol_parquet,
        ]
        subprocess.run(cmd_vol, cwd=OPTIONS_REPO, check=True)
        print("Volatility history exported.")
    else:
        print("Volatility history parquet already exists.")

    print("\n[Step 2/4] Exporting option_chain from Dolt to Parquet...")
    if not os.path.exists(chain_parquet):
        cmd_chain = [DOLT_PATH, "table", "export", "-f", "option_chain", chain_parquet]
        subprocess.run(cmd_chain, cwd=OPTIONS_REPO, check=True)
        print("Option chain exported.")
    else:
        print("Option chain parquet already exists.")

    # 2. Process and save volatility history
    print("\n[Step 3/4] Processing volatility history...")
    con = duckdb.connect()

    dest_vol_dir = os.path.join(LAKE_DIR, "volatility")
    os.makedirs(dest_vol_dir, exist_ok=True)
    dest_vol_path = os.path.join(dest_vol_dir, "options_vol.parquet")

    # Pre-replace backslashes to avoid f-string syntax error in Python <= 3.11
    vol_parquet_db = vol_parquet.replace("\\", "/")
    dest_vol_path_db = dest_vol_path.replace("\\", "/")

    # Convert dates to timestamp, columns to lowercase
    query_vol = f"""
        COPY (
            SELECT date as timestamp, act_symbol as symbol, 
                   iv_current, iv_year_high, iv_year_low, hv_current
            FROM '{vol_parquet_db}'
        ) TO '{dest_vol_path_db}' (FORMAT PARQUET)
    """
    con.execute(query_vol)
    print("Volatility history processed and saved.")

    # 3. Partition option chain by symbol
    print("\n[Step 4/4] Partitioning option chain by symbol (DuckDB COPY)...")
    dest_options_dir = os.path.join(LAKE_DIR, "options")
    os.makedirs(dest_options_dir, exist_ok=True)

    chain_parquet_db = chain_parquet.replace("\\", "/")
    dest_options_dir_db = dest_options_dir.replace("\\", "/")

    query_chain = f"""
        COPY (
            SELECT act_symbol as symbol, date as timestamp, expiration, strike, call_put,
                   bid, ask, vol as implied_vol, delta, gamma, theta, vega, rho
            FROM '{chain_parquet_db}'
        ) TO '{dest_options_dir_db}' (FORMAT PARQUET, PARTITION_BY symbol, OVERWRITE_OR_IGNORE true)
    """
    con.execute(query_chain)
    print("Option chain partitioned and saved.")

    # Cleanup temp parquet files
    print("\nCleaning up temporary Parquet files...")
    if os.path.exists(vol_parquet):
        os.remove(vol_parquet)
    if os.path.exists(chain_parquet):
        os.remove(chain_parquet)

    con.close()
    duration = time.time() - start_time
    print("==================================================")
    print(f"FAST INGESTION COMPLETED IN {duration:.2f} SECONDS")
    print("==================================================")


if __name__ == "__main__":
    run_fast_ingest()
