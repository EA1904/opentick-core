import os
import time

from tvdata import (
    ingest_dolt_corporate_actions,
    ingest_dolt_earnings,
    ingest_dolt_options,
    ingest_dolt_rates,
)

# Cloned repositories paths
from tvdata.config import WORKSPACE_ROOT

# Cloned repositories paths
RATES_REPO = os.path.join(WORKSPACE_ROOT, "raw", "dolt", "rates")
STOCKS_REPO = os.path.join(WORKSPACE_ROOT, "raw", "dolt", "stocks")
EARNINGS_REPO = os.path.join(WORKSPACE_ROOT, "raw", "dolt", "earnings")
OPTIONS_REPO = os.path.join(WORKSPACE_ROOT, "raw", "dolt", "options")


def main():
    start_time = time.time()
    print("==================================================")
    print("STARTING DOLT DATABASES INGESTION PIPELINE")
    print("==================================================")

    # 1. Ingest Rates
    if os.path.exists(RATES_REPO):
        ingest_dolt_rates(RATES_REPO)
    else:
        print(f"Skipping: Rates repository not found at {RATES_REPO}")

    # 2. Ingest Corporate Actions
    if os.path.exists(STOCKS_REPO):
        ingest_dolt_corporate_actions(STOCKS_REPO)
    else:
        print(f"Skipping: Stocks repository not found at {STOCKS_REPO}")

    # 3. Ingest Earnings (Financial Statements)
    if os.path.exists(EARNINGS_REPO):
        ingest_dolt_earnings(EARNINGS_REPO)
    else:
        print(f"Skipping: Earnings repository not found at {EARNINGS_REPO}")

    # 4. Ingest Options (if download is finished)
    if os.path.exists(OPTIONS_REPO) and os.path.exists(
        os.path.join(OPTIONS_REPO, ".dolt")
    ):
        # Check if the folder is locked/cloning by looking for lock or checking if we can query it
        try:
            ingest_dolt_options(OPTIONS_REPO)
        except Exception as e:
            print(
                f"Options repository is still lock-protected or cloning. Skipping options ingestion for now. Error: {e}"
            )
    else:
        print(
            "Options repository not yet fully cloned. Skipping options ingestion for now."
        )

    duration = time.time() - start_time
    print("==================================================")
    print(f"DOLT INGESTION PIPELINE FINISHED IN {duration:.2f} SECONDS")
    print("==================================================")


if __name__ == "__main__":
    main()
