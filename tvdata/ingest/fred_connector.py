import os
from datetime import datetime

import pandas as pd
from fredapi import Fred

from tvdata.catalog import init_db, register_dataset
from tvdata.config import LAKE_ROOT, WORKSPACE_ROOT


def load_env():
    """Load environment variables from .env file in the workspace root."""
    env_path = os.path.join(WORKSPACE_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")


def ingest_fred_series(
    series_id: str,
    symbol: str = None,
    start_date: str = "1950-01-01",
    end_date: str = None,
) -> dict:
    """
    Fetch a macroeconomic series from FRED and save it as Parquet in the lake.
    """
    load_env()
    api_key = os.environ.get("FRED_API_KEY") or os.environ.get("fred_api_key")

    if not api_key or api_key == "your_fred_api_key_here":
        # Raise descriptive error or print warning if key is placeholder
        print(
            f"Warning: Valid FRED_API_KEY not found in environment. Skipping FRED series {series_id}."
        )
        return {}

    if not symbol:
        symbol = series_id

    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    print(
        f"Ingesting FRED series: {series_id} (symbol={symbol}) from {start_date} to {end_date}..."
    )

    try:
        fred = Fred(api_key=api_key)
        series = fred.get_series(
            series_id, observation_start=start_date, observation_end=end_date
        )

        if series is None or len(series) == 0:
            print(f"No data returned from FRED for series: {series_id}")
            return {}

        df = pd.DataFrame(series).reset_index()
        df.columns = ["timestamp", "value"]

        # Ensure correct types
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")

        # Add metadata columns matching target schema structure
        df["symbol"] = symbol
        df["asset_class"] = "macro"
        df["timeframe"] = "D1"
        df["source"] = "fred"

        # Drop rows where value is null (FRED sometimes returns nulls for recent dates)
        df = df.dropna(subset=["value"])

        # Create output directory
        dest_dir = os.path.join(LAKE_ROOT, "macro")
        os.makedirs(dest_dir, exist_ok=True)

        dest_path = os.path.join(dest_dir, f"{symbol.lower()}.parquet")
        df.to_parquet(dest_path, index=False)

        # Register in catalog
        init_db()
        min_ts = df["timestamp"].min()
        max_ts = df["timestamp"].max()
        start_str = min_ts.strftime("%Y-%m-%d") if pd.notnull(min_ts) else "N/A"
        end_str = max_ts.strftime("%Y-%m-%d") if pd.notnull(max_ts) else "N/A"

        # For macroeconomic data, we consider it high quality if no nulls are present
        nulls_pct = (
            (df["value"].isnull().sum() / len(df)) * 100.0 if len(df) > 0 else 0.0
        )
        quality_score = 100.0 - nulls_pct

        register_dataset(
            symbol=symbol,
            timeframe="D1",
            asset_class="macro",
            start_date=start_str,
            end_date=end_str,
            rows_count=len(df),
            nulls_pct=nulls_pct,
            quality_score=quality_score,
            source="fred",
        )

        print(
            f"Successfully ingested FRED series {series_id} into {symbol.lower()}.parquet. Rows: {len(df)}"
        )
        return {
            "symbol": symbol,
            "timeframe": "D1",
            "rows": len(df),
            "start_date": start_str,
            "end_date": end_str,
            "quality_score": quality_score,
        }

    except Exception as e:
        print(f"Error fetching series {series_id} from FRED: {e}")
        return {}
