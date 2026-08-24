import pandas as pd
import numpy as np

def to_utc_naive(series: pd.Series, source_tz: str) -> pd.Series:
    """
    Convert a timezone-aware or naive datetime series into a naive UTC datetime series.
    - If the series is tz-naive, localize it to source_tz, convert to UTC, and strip timezone.
    - If the series is tz-aware, convert it directly to UTC and strip timezone.
    """
    # Ensure datetime format
    dt_series = pd.to_datetime(series, errors='raise')
    
    if dt_series.dt.tz is None:
        # Naive series: localize, convert to UTC, strip tz
        return dt_series.dt.tz_localize(source_tz).dt.tz_convert('UTC').dt.tz_localize(None)
    else:
        # Aware series: convert to UTC, strip tz
        return dt_series.dt.tz_convert('UTC').dt.tz_localize(None)

def rename_and_standardize(df: pd.DataFrame, 
                           symbol: str, 
                           asset_class: str, 
                           timeframe: str, 
                           source: str, 
                           source_tz: str = 'UTC') -> pd.DataFrame:
    """
    Renames columns to target schema, cleans rows, and adds metadata columns.
    
    Target schema columns:
      - timestamp (datetime64[ns], UTC naive)
      - symbol (string)
      - asset_class (string)
      - timeframe (string)
      - open (float64)
      - high (float64)
      - low (float64)
      - close (float64)
      - volume (float64)
      - adj_close (float64)
      - adj_factor (float64)
      - source (string)
      - year (int32)
    """
    df = df.copy()
    
    # 1. Column renaming mapping (case insensitive matching)
    col_mapping = {}
    for col in df.columns:
        col_lower = str(col).lower()
        if col_lower in ['date', 'datetime', 'timestamp', 'observation_date']:
            col_mapping[col] = 'timestamp'
        elif col_lower == 'open':
            col_mapping[col] = 'open'
        elif col_lower == 'high':
            col_mapping[col] = 'high'
        elif col_lower == 'low':
            col_mapping[col] = 'low'
        elif col_lower == 'close':
            col_mapping[col] = 'close'
        elif col_lower == 'volume':
            col_mapping[col] = 'volume'
        elif col_lower in ['adj close', 'adj_close']:
            col_mapping[col] = 'adj_close'
        elif col_lower == 'symbol':
            col_mapping[col] = 'symbol'
            
    # If no timestamp column mapped yet, check for empty or Unnamed index columns
    if 'timestamp' not in col_mapping.values():
        for col in df.columns:
            col_lower = str(col).lower()
            if 'unnamed' in col_lower or col_lower.strip() == '':
                col_mapping[col] = 'timestamp'
                break
                
    df = df.rename(columns=col_mapping)
    
    # Check if we have timestamp
    if 'timestamp' not in df.columns:
        raise ValueError(f"Could not find timestamp/date column in source dataframe. Columns: {list(df.columns)}")
        
    # 2. Normalize Timestamp to naive UTC
    df['timestamp'] = to_utc_naive(df['timestamp'], source_tz)
    
    # 3. Clean null values in price fields
    # If open/high/low/close are all null, discard the row.
    core_cols = ['open', 'high', 'low', 'close']
    # Filter to exist in df
    available_core = [c for c in core_cols if c in df.columns]
    if available_core:
        df = df.dropna(subset=available_core, how='all')
        
    # 4. Fill missing columns with defaults if not present
    if 'open' not in df.columns: df['open'] = np.nan
    if 'high' not in df.columns: df['high'] = np.nan
    if 'low' not in df.columns: df['low'] = np.nan
    if 'close' not in df.columns: df['close'] = np.nan
    if 'volume' not in df.columns: df['volume'] = 0.0
    if 'adj_close' not in df.columns: df['adj_close'] = df['close']
    
    # Ensure float/numeric types
    for c in ['open', 'high', 'low', 'close', 'volume', 'adj_close']:
        df[c] = pd.to_numeric(df[c], errors='coerce').astype('float64')
        
    # 5. Compute adj_factor: adj_close / close
    # Avoid division by zero
    close_zero_or_nan = (df['close'] == 0) | df['close'].isna()
    df['adj_factor'] = np.where(close_zero_or_nan, 1.0, df['adj_close'] / df['close'])
    df['adj_factor'] = df['adj_factor'].astype('float64')
    
    # 6. Add metadata columns
    if 'symbol' not in df.columns:
        df['symbol'] = str(symbol)
    else:
        df['symbol'] = df['symbol'].astype(str)
        
    df['asset_class'] = str(asset_class)
    df['timeframe'] = str(timeframe)
    df['source'] = str(source)
    
    # 7. Add year column (int32) for partitioning
    df['year'] = df['timestamp'].dt.year.astype('int32')
    
    # Reorder columns to standard schema
    standard_cols = [
        'timestamp', 'symbol', 'asset_class', 'timeframe', 
        'open', 'high', 'low', 'close', 'volume', 
        'adj_close', 'adj_factor', 'source', 'year'
    ]
    
    # Keep extra columns if any, but ensure standard cols are first and standard
    extra_cols = [c for c in df.columns if c not in standard_cols]
    df = df[standard_cols + extra_cols]
    
    return df
