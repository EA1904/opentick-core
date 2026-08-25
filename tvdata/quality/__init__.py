import numpy as np
import pandas as pd


def scan_nulls(df: pd.DataFrame) -> dict:
    """
    Calculate the percentage of null values in each column of the DataFrame.
    Returns a dictionary of col_name -> null_percentage (0 to 100).
    """
    if len(df) == 0:
        return {col: 0.0 for col in df.columns}

    null_counts = df.isnull().sum()
    null_pct = (null_counts / len(df)) * 100
    return null_pct.to_dict()


def detect_gaps(df: pd.DataFrame, timeframe: str) -> list:
    """
    Identify significant gaps in the time-series.
    Returns a list of dictionaries with gap details:
    [{'start': timestamp, 'end': timestamp, 'duration_days': float}, ...]
    """
    if len(df) < 2 or "timestamp" not in df.columns:
        return []

    # Ensure timestamps are sorted and index is reset for clean positional indexing
    ts = df["timestamp"].sort_values().reset_index(drop=True)
    diffs = ts.diff()

    gaps = []

    if timeframe == "D1":
        # Daily: standard gap is > 4 days (covers weekend + holiday)
        threshold = pd.Timedelta(days=4)
        gap_indices = diffs[diffs > threshold].index

        for idx in gap_indices:
            end_time = ts.loc[idx]
            start_time = ts.loc[idx - 1]
            duration = (end_time - start_time).days
            gaps.append(
                {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "gap_size_days": duration,
                }
            )

    elif timeframe == "1m":
        # 1-minute: flag gaps of > 15 minutes during standard NYSE hours (14:30 - 21:00 UTC)
        # Gaps across days (overnight/weekends) are standard, so we filter them out.
        threshold = pd.Timedelta(minutes=15)

        # Sort and diff
        ts_sorted = ts.reset_index(drop=True)
        diffs_sorted = ts_sorted.diff()

        gap_indices = diffs_sorted[diffs_sorted > threshold].index

        for idx in gap_indices:
            start_time = ts_sorted.iloc[idx - 1]
            end_time = ts_sorted.iloc[idx]

            # Check if it's the same trading day (UTC time)
            if start_time.date() == end_time.date():
                duration_mins = (end_time - start_time).total_seconds() / 60.0
                gaps.append(
                    {
                        "start": start_time.isoformat(),
                        "end": end_time.isoformat(),
                        "gap_size_minutes": duration_mins,
                    }
                )

    return gaps


def compute_quality_score(df: pd.DataFrame, timeframe: str) -> float:
    """
    Compute a data quality score between 0 and 100.
    100 means perfect data, 0 means completely corrupted.
    Deductions:
      - Nulls in OHLCV columns (up to -50 points)
      - Detected time gaps (up to -50 points)
    """
    if len(df) == 0:
        return 0.0

    score = 100.0

    # 1. Nulls deduction (check open, high, low, close)
    null_pcts = scan_nulls(df)
    ohlc_cols = ["open", "high", "low", "close"]
    ohlc_null_avg = np.mean([null_pcts.get(col, 100.0) for col in ohlc_cols])

    # Subtract directly proportional to nulls (e.g. 10% nulls = -10 points, max -50)
    score -= min(50.0, ohlc_null_avg * 1.5)

    # 2. Gaps deduction
    gaps = detect_gaps(df, timeframe)
    # Deduct 5 points per gap, up to -50 points
    score -= min(50.0, len(gaps) * 5.0)

    return max(0.0, score)
