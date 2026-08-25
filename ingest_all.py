import os
import time

from tvdata import (
    ingest_archive_1d,
    ingest_archive_1m,
    ingest_companies,
    ingest_sp500_bulk,
)

# Standard workspace paths
from tvdata.config import WORKSPACE_ROOT

COMPANIES_CSV = os.path.join(
    WORKSPACE_ROOT, "Kaggle_Data", "SP500 DATA", "sp500_companies.csv"
)
STOCKS_CSV = os.path.join(
    WORKSPACE_ROOT, "Kaggle_Data", "SP500 DATA", "sp500_stocks.csv"
)
ARCHIVE_1D = os.path.join(WORKSPACE_ROOT, "Kaggle_Data", "archive (4)", "data", "1d")
ARCHIVE_1M = os.path.join(WORKSPACE_ROOT, "Kaggle_Data", "archive (4)", "data", "1m")


def run_ingestion():
    start_time = time.time()
    print("==================================================")
    print("STARTING FULL STOCK DATASET INGESTION PIPELINE")
    print("==================================================")

    # 1. Ingest companies metadata
    print("\n[Step 1/4] Ingesting SP500 metadata...")
    if os.path.exists(COMPANIES_CSV):
        ingest_companies(COMPANIES_CSV)
    else:
        print(f"Skipping: Companies metadata not found at {COMPANIES_CSV}")

    # 2. Ingest bulk historical daily stocks (sp500_stocks.csv)
    print("\n[Step 2/4] Ingesting SP500 bulk daily stock history (1.89M rows)...")
    if os.path.exists(STOCKS_CSV):
        ingest_sp500_bulk(STOCKS_CSV, chunk_size=300000)
    else:
        print(f"Skipping: Bulk stocks CSV not found at {STOCKS_CSV}")

    # 3. Ingest archive 1D
    print("\n[Step 3/4] Ingesting archive D1 stock files...")
    if os.path.exists(ARCHIVE_1D):
        ingest_archive_1d(ARCHIVE_1D)
    else:
        print(f"Skipping: Archive 1d folder not found at {ARCHIVE_1D}")

    # 4. Ingest archive 1M
    print("\n[Step 4/4] Ingesting archive 1m stock files...")
    if os.path.exists(ARCHIVE_1M):
        ingest_archive_1m(ARCHIVE_1M)
    else:
        print(f"Skipping: Archive 1m folder not found at {ARCHIVE_1M}")

    duration = time.time() - start_time
    print("==================================================")
    print(f"FULL INGESTION COMPLETED IN {duration:.2f} SECONDS")
    print("==================================================")


if __name__ == "__main__":
    run_ingestion()
