import os
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from tvdata.catalog import register_metadata, register_dataset, init_db
from tvdata.ingest.normalizer import rename_and_standardize
from tvdata.quality import scan_nulls, compute_quality_score

from tvdata.config import LAKE_ROOT as CONFIG_LAKE_ROOT
LAKE_ROOT = os.path.join(CONFIG_LAKE_ROOT, "ohlcv")

def write_parquet_hive(df: pd.DataFrame, root_path: str = LAKE_ROOT):
    """
    Write standard DataFrame to Hive-partitioned Parquet files:
    Partition columns: asset_class, timeframe, year
    """
    if len(df) == 0:
        return
        
    # Ensure year, timeframe, asset_class, symbol are of correct types
    df['year'] = df['year'].astype('int32')
    df['timeframe'] = df['timeframe'].astype(str)
    df['asset_class'] = df['asset_class'].astype(str)
    df['symbol'] = df['symbol'].astype(str)
    
    table = pa.Table.from_pandas(df, preserve_index=False)
    
    os.makedirs(root_path, exist_ok=True)
    
    pq.write_to_dataset(
        table,
        root_path=root_path,
        partition_cols=['asset_class', 'timeframe', 'symbol', 'year'],
        compression='snappy',
        use_dictionary=True,
        row_group_size=100_000
    )

def ingest_companies(csv_path: str):
    """
    Ingest metadata from sp500_companies.csv into SQLite catalog.
    """
    print(f"Ingesting companies metadata from: {csv_path}")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Source file not found: {csv_path}")
        
    # Initialize DB in case it isn't
    init_db()
    
    df = pd.read_csv(csv_path)
    
    # Standardize empty values
    df = df.replace({np.nan: None})
    
    count = 0
    for _, row in df.iterrows():
        symbol = str(row['Symbol']).strip()
        register_metadata(
            symbol=symbol,
            exchange=row.get('Exchange'),
            shortname=row.get('Shortname'),
            longname=row.get('Longname'),
            sector=row.get('Sector'),
            industry=row.get('Industry'),
            marketcap=row.get('Marketcap'),
            weight=row.get('Weight'),
            summary=row.get('Longbusinesssummary')
        )
        count += 1
        
    print(f"Successfully registered metadata for {count} companies.")

def ingest_sp500_bulk(csv_path: str, chunk_size: int = 200_000):
    """
    Ingest the bulk sp500_stocks.csv file using chunks.
    Maintains memory efficiency while tracking symbol stats for catalog.
    """
    print(f"Ingesting SP500 stocks historical daily data from: {csv_path}")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Source file not found: {csv_path}")
        
    # Dictionary to collect stats for the catalog
    # symbol -> {start_date, end_date, rows, null_close}
    stats = {}
    
    chunk_idx = 0
    for chunk in pd.read_csv(csv_path, chunksize=chunk_size):
        chunk_idx += 1
        print(f"Processing chunk {chunk_idx}...")
        
        # Remove completely null rows in core price columns
        # yfinance bulk exports sometimes have full empty rows for delisted or non-trading days
        chunk = chunk.dropna(subset=['Open', 'High', 'Low', 'Close'], how='all')
        if len(chunk) == 0:
            continue
            
        # Standardize using normalizer
        standardized = rename_and_standardize(
            df=chunk,
            symbol="", # ignored since Symbol is in columns
            asset_class="stocks",
            timeframe="D1",
            source="kaggle_sp500_stocks",
            source_tz="America/New_York" # yfinance daily standard is NYSE tz
        )
        
        # Write partition Parquet
        write_parquet_hive(standardized)
        
        # Accumulate stats per symbol
        for symbol, group in standardized.groupby('symbol'):
            min_ts = group['timestamp'].min()
            max_ts = group['timestamp'].max()
            rows = len(group)
            nulls = group['close'].isnull().sum()
            
            if symbol not in stats:
                stats[symbol] = {
                    'start': min_ts,
                    'end': max_ts,
                    'rows': rows,
                    'nulls': nulls
                }
            else:
                s = stats[symbol]
                if min_ts < s['start']: s['start'] = min_ts
                if max_ts > s['end']: s['end'] = max_ts
                s['rows'] += rows
                s['nulls'] += nulls

    # Register all datasets in catalog
    print("Registering datasets in catalog database...")
    for symbol, s in stats.items():
        nulls_pct = (s['nulls'] / s['rows']) * 100.0 if s['rows'] > 0 else 0.0
        # Simple quality score (100 - nulls_pct)
        # Gaps can be computed later or set to a placeholder for bulk imports
        quality_score = max(0.0, 100.0 - (nulls_pct * 2.0))
        
        register_dataset(
            symbol=symbol,
            timeframe="D1",
            asset_class="stocks",
            start_date=s['start'].strftime('%Y-%m-%d'),
            end_date=s['end'].strftime('%Y-%m-%d'),
            rows_count=s['rows'],
            nulls_pct=nulls_pct,
            quality_score=quality_score,
            source="kaggle_sp500_stocks"
        )
        
    print(f"Finished bulk ingestion. {len(stats)} symbols catalogued.")

def ingest_archive_1d(folder_path: str):
    """
    Ingest daily CSV files from archive (4)/data/1d/ folder.
    Processes each ticker individually, detects forex pairs, normalizes, and writes parquet.
    """
    print(f"Ingesting daily historical files from: {folder_path}")
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")
        
    csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    print(f"Found {len(csv_files)} CSV files to process.")
    
    count = 0
    for filename in csv_files:
        file_path = os.path.join(folder_path, filename)
        
        # Skip empty/tiny header-only files (typically ~69,350 bytes)
        if os.path.getsize(file_path) < 75_000:
            continue
            
        raw_symbol = os.path.splitext(filename)[0]
        
        # Detect forex pairs (ending with -X)
        if raw_symbol.endswith('-X'):
            symbol = raw_symbol.replace('-X', '')
            asset_class = "forex"
            source_tz = "UTC"
        else:
            symbol = raw_symbol
            asset_class = "stocks"
            source_tz = "America/New_York"
            
        try:
            df = pd.read_csv(file_path)
            if len(df) == 0:
                continue
                
            # Standardize
            standardized = rename_and_standardize(
                df=df,
                symbol=symbol,
                asset_class=asset_class,
                timeframe="D1",
                source="kaggle_archive4_1d",
                source_tz=source_tz
            )
            
            # Write parquet
            write_parquet_hive(standardized)
            
            # Catalog quality check
            null_pcts = scan_nulls(standardized)
            nulls_pct = null_pcts.get('close', 0.0)
            quality_score = compute_quality_score(standardized, "D1")
            
            min_ts = standardized['timestamp'].min()
            max_ts = standardized['timestamp'].max()
            start_date = min_ts.strftime('%Y-%m-%d') if pd.notnull(min_ts) else "N/A"
            end_date = max_ts.strftime('%Y-%m-%d') if pd.notnull(max_ts) else "N/A"
            
            register_dataset(
                symbol=symbol,
                timeframe="D1",
                asset_class=asset_class,
                start_date=start_date,
                end_date=end_date,
                rows_count=len(standardized),
                nulls_pct=nulls_pct,
                quality_score=quality_score,
                source="kaggle_archive4_1d"
            )
            count += 1
            if count % 100 == 0:
                print(f"Processed {count} daily files...")
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            
    print(f"Ingested {count} daily tickers from archive.")

def ingest_archive_1m(folder_path: str):
    """
    Ingest 1-minute resolution CSV files from archive (4)/data/1m/ folder.
    Processes each ticker individually, detects forex pairs, normalizes, and writes parquet.
    """
    print(f"Ingesting 1-minute historical files from: {folder_path}")
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Folder not found: {folder_path}")
        
    csv_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    print(f"Found {len(csv_files)} CSV files to process.")
    
    count = 0
    for filename in csv_files:
        file_path = os.path.join(folder_path, filename)
        
        # 1-minute files can be smaller, but header-only files are still around 69k
        if os.path.getsize(file_path) < 75_000:
            continue
            
        raw_symbol = os.path.splitext(filename)[0]
        
        # Detect forex pairs (ending with -X)
        if raw_symbol.endswith('-X'):
            symbol = raw_symbol.replace('-X', '')
            asset_class = "forex"
            source_tz = "UTC"
        else:
            symbol = raw_symbol
            asset_class = "stocks"
            source_tz = "America/New_York"
            
        try:
            df = pd.read_csv(file_path)
            if len(df) == 0:
                continue
                
            # Standardize
            standardized = rename_and_standardize(
                df=df,
                symbol=symbol,
                asset_class=asset_class,
                timeframe="1m",
                source="kaggle_archive4_1m",
                source_tz=source_tz
            )
            
            # Write parquet
            write_parquet_hive(standardized)
            
            # Catalog quality check
            null_pcts = scan_nulls(standardized)
            nulls_pct = null_pcts.get('close', 0.0)
            quality_score = compute_quality_score(standardized, "1m")
            
            min_ts = standardized['timestamp'].min()
            max_ts = standardized['timestamp'].max()
            start_date = min_ts.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(min_ts) else "N/A"
            end_date = max_ts.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(max_ts) else "N/A"
            
            register_dataset(
                symbol=symbol,
                timeframe="1m",
                asset_class=asset_class,
                start_date=start_date,
                end_date=end_date,
                rows_count=len(standardized),
                nulls_pct=nulls_pct,
                quality_score=quality_score,
                source="kaggle_archive4_1m"
            )
            count += 1
            if count % 100 == 0:
                print(f"Processed {count} 1-minute files...")
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            
    print(f"Ingested {count} 1-minute tickers from archive.")


