import os
import shutil
import pandas as pd
from tvdata import (
    get_ohlcv, sql, catalog,
    ingest_companies, ingest_sp500_bulk,
    ingest_archive_1d, ingest_archive_1m
)
from tvdata.catalog import DEFAULT_DB_PATH
from tvdata.ingest.stocks import LAKE_ROOT
from tvdata.config import WORKSPACE_ROOT

# Setup paths
COMPANIES_CSV = os.path.join(WORKSPACE_ROOT, "Kaggle_Data", "SP500 DATA", "sp500_companies.csv")
STOCKS_CSV = os.path.join(WORKSPACE_ROOT, "Kaggle_Data", "SP500 DATA", "sp500_stocks.csv")
ARCHIVE_1D = os.path.join(WORKSPACE_ROOT, "Kaggle_Data", "archive (4)", "data", "1d")
ARCHIVE_1M = os.path.join(WORKSPACE_ROOT, "Kaggle_Data", "archive (4)", "data", "1m")

def clean_database():
    """Reset DB and Lake for a clean test run."""
    print("Cleaning database and data lake...")
    if os.path.exists(DEFAULT_DB_PATH):
        os.remove(DEFAULT_DB_PATH)
    if os.path.exists(LAKE_ROOT):
        shutil.rmtree(LAKE_ROOT)
    print("Cleaned successfully.")

def run_test():
    clean_database()
    
    # 1. Ingest companies metadata
    print("\n--- TEST 1: Ingesting companies metadata ---")
    if os.path.exists(COMPANIES_CSV):
        ingest_companies(COMPANIES_CSV)
    else:
        print(f"Skipping: Metadata CSV not found at {COMPANIES_CSV}")
        
    # 2. Ingest SP500 stocks (we will ingest a small chunk size of 100k to test bulk)
    print("\n--- TEST 2: Ingesting SP500 stocks daily ---")
    if os.path.exists(STOCKS_CSV):
        # We limit the CSV reading to first 200,000 rows to keep it fast during test
        # Let's temporarily copy first 200k rows to a temp file and ingest that
        temp_csv = os.path.join(WORKSPACE_ROOT, "temp_stocks_test.csv")
        print(f"Creating temp test CSV from first 200,000 lines...")
        try:
            # Read first 200k lines (includes header)
            df_temp = pd.read_csv(STOCKS_CSV, nrows=200000)
            df_temp.to_csv(temp_csv, index=False)
            ingest_sp500_bulk(temp_csv, chunk_size=100000)
        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)
    else:
        print(f"Skipping: SP500 stocks CSV not found at {STOCKS_CSV}")
        
    # 3. Ingest a subset of archive (4) 1d files
    # Instead of all files, we copy 5 files to a temporary folder to test the speed and correctness
    print("\n--- TEST 3: Ingesting archive (4) D1 subset ---")
    if os.path.exists(ARCHIVE_1D):
        temp_dir_1d = os.path.join(WORKSPACE_ROOT, "temp_1d_test")
        os.makedirs(temp_dir_1d, exist_ok=True)
        # Select 5 non-empty CSV files
        count = 0
        for f in os.listdir(ARCHIVE_1D):
            src_f = os.path.join(ARCHIVE_1D, f)
            if f.endswith('.csv') and os.path.getsize(src_f) > 80_000:
                shutil.copy(src_f, os.path.join(temp_dir_1d, f))
                count += 1
                if count >= 5:
                    break
        try:
            ingest_archive_1d(temp_dir_1d)
        finally:
            if os.path.exists(temp_dir_1d):
                shutil.rmtree(temp_dir_1d)
    else:
        print(f"Skipping: Archive 1d folder not found at {ARCHIVE_1D}")

    # 4. Ingest a subset of archive (4) 1m files
    print("\n--- TEST 4: Ingesting archive (4) 1m subset ---")
    if os.path.exists(ARCHIVE_1M):
        temp_dir_1m = os.path.join(WORKSPACE_ROOT, "temp_1m_test")
        os.makedirs(temp_dir_1m, exist_ok=True)
        count = 0
        for f in os.listdir(ARCHIVE_1M):
            src_f = os.path.join(ARCHIVE_1M, f)
            if f.endswith('.csv') and os.path.getsize(src_f) > 80_000:
                shutil.copy(src_f, os.path.join(temp_dir_1m, f))
                count += 1
                if count >= 5:
                    break
        try:
            ingest_archive_1m(temp_dir_1m)
        finally:
            if os.path.exists(temp_dir_1m):
                shutil.rmtree(temp_dir_1m)
    else:
        print(f"Skipping: Archive 1m folder not found at {ARCHIVE_1M}")

    # 5. Verify data retrieval
    print("\n--- TEST 5: Verifying Query APIs ---")
    
    # Check catalog
    print("\nCatalog records:")
    df_cat = catalog()
    if len(df_cat) > 0:
        print(df_cat.head(10))
    else:
        print("No catalog records found!")
        
    # Query AAPL or another ticker from the catalog
    if len(df_cat) > 0:
        test_symbol = df_cat.iloc[0]['symbol']
        test_tf = df_cat.iloc[0]['timeframe']
        print(f"\nQuerying OHLCV for {test_symbol} ({test_tf}) adjusted:")
        df_ohlcv = get_ohlcv(test_symbol, test_tf)
        print(df_ohlcv.head(5))
        
        print(f"\nQuerying OHLCV for {test_symbol} ({test_tf}) raw:")
        df_raw = get_ohlcv(test_symbol, test_tf, adjusted=False)
        print(df_raw.head(5))
        
        # Test DuckDB SQL
        print("\nTesting SQL query direct on Parquet:")
        df_sql = sql(f"SELECT symbol, timeframe, COUNT(*), MIN(timestamp), MAX(timestamp) FROM ohlcv WHERE symbol = '{test_symbol}' GROUP BY symbol, timeframe")
        print(df_sql)
        
if __name__ == '__main__':
    run_test()
