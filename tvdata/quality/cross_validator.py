import numpy as np
import pandas as pd

from tvdata.get import get_ohlcv


def cross_validate(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    source1: str = "alpaca",
    source2: str = "yfinance",
) -> dict:
    """
    Compare OHLCV data for a symbol between two sources in the Parquet lake.
    Computes absolute percentage differences and a reliability score.
    """
    print("\n==================================================")
    print(f"CROSS-SOURCE VALIDATION: {symbol} ({timeframe})")
    print(f"Comparing {source1} vs {source2}")
    print(f"Period: {start_date} to {end_date}")
    print("==================================================")

    # Load raw data from the lake
    df = get_ohlcv(
        symbol, timeframe=timeframe, start=start_date, end=end_date, adjusted=False
    )
    if len(df) == 0:
        print("No data found in the lake for the specified query.")
        return {"reliability_score": 0.0, "rows_compared": 0}

    df_s1 = df[df["source"].str.lower() == source1.lower()].copy()
    df_s2 = df[df["source"].str.lower() == source2.lower()].copy()

    if len(df_s1) == 0:
        print(f"No data found in the lake for source: {source1}")
        return {"reliability_score": 0.0, "rows_compared": 0}
    if len(df_s2) == 0:
        print(f"No data found in the lake for source: {source2}")
        return {"reliability_score": 0.0, "rows_compared": 0}

    print(f"Loaded {len(df_s1)} rows for {source1} and {len(df_s2)} rows for {source2}")

    # Merge on timestamp
    merged = pd.merge(
        df_s1, df_s2, on="timestamp", suffixes=(f"_{source1}", f"_{source2}")
    )

    if len(merged) == 0:
        print("No overlapping timestamps found between the two sources.")
        return {"reliability_score": 0.0, "rows_compared": 0}

    print(f"Compared {len(merged)} overlapping rows.")

    # Calculate differences for close price
    close_s1 = merged[f"close_{source1}"]
    close_s2 = merged[f"close_{source2}"]

    # Avoid division by zero
    diff_pct = (abs(close_s1 - close_s2) / np.maximum(close_s1, 1e-8)) * 100.0

    mean_diff = float(diff_pct.mean())
    max_diff = float(diff_pct.max())
    std_diff = float(diff_pct.std()) if len(diff_pct) > 1 else 0.0

    # Compute a reliability score (100 is perfect, deduct 10 points per 1% mean difference)
    reliability_score = max(0.0, 100.0 - (mean_diff * 10.0))

    print(f"Mean Difference: {mean_diff:.4f}%")
    print(f"Max Difference : {max_diff:.4f}%")
    print(f"Standard Dev   : {std_diff:.4f}%")
    print(f"Reliability Score: {reliability_score:.2f}/100")

    # Flag discrepancies > 1%
    significant_diffs = merged[diff_pct > 1.0]
    if len(significant_diffs) > 0:
        print(
            f"Warning: Found {len(significant_diffs)} rows with >1% price difference."
        )
        print(
            significant_diffs[
                ["timestamp", f"close_{source1}", f"close_{source2}"]
            ].head()
        )

    print("==================================================")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "source1_rows": len(df_s1),
        "source2_rows": len(df_s2),
        "rows_compared": len(merged),
        "mean_difference_pct": mean_diff,
        "max_difference_pct": max_diff,
        "std_difference_pct": std_diff,
        "reliability_score": reliability_score,
    }
