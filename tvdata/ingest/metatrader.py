import os
import re
import pandas as pd
import numpy as np
from tvdata.catalog import register_dataset, init_db
from tvdata.ingest.normalizer import rename_and_standardize
from tvdata.ingest.stocks import write_parquet_hive
from tvdata.quality import scan_nulls, compute_quality_score

def detect_delimiter(first_line: str) -> str:
    """Detect delimiter by counting frequencies of standard separators."""
    delims = {',': 0, '\t': 0, ';': 0}
    for d in delims:
        delims[d] = first_line.count(d)
    # Return the one with maximum count, fallback to tab (default MT5 export)
    best_delim = max(delims, key=delims.get)
    return best_delim if delims[best_delim] > 0 else '\t'

def parse_filename_metadata(filename: str):
    """
    Extract symbol and timeframe from MT5 typical export filenames.
    Examples:
        - "EURUSD1.csv" -> symbol "EURUSD", timeframe "1m" (1 minute)
        - "GBPUSD60.csv" -> symbol "GBPUSD", timeframe "1h" (60 minutes)
        - "USDJPY1440.csv" -> symbol "USDJPY", timeframe "D1" (1440 minutes)
        - "EURUSD_M1.csv" -> symbol "EURUSD", timeframe "1m"
        - "EURUSD_H1.csv" -> symbol "EURUSD", timeframe "1h"
        - "EURUSD_D1.csv" -> symbol "EURUSD", timeframe "D1"
    """
    base = os.path.splitext(filename)[0]
    
    # 1. Try underscore formats like EURUSD_M1, EURUSD_H1, EURUSD_D1
    match_underscore = re.match(r"^([A-Za-z0-9\-]+)_(M1|M5|M15|M30|H1|H4|D1|W1|MN1)$", base, re.IGNORECASE)
    if match_underscore:
        symbol = match_underscore.group(1)
        tf_raw = match_underscore.group(2).upper()
        tf_map = {
            'M1': '1m', 'M5': '5m', 'M15': '15m', 'M30': '30m',
            'H1': '1h', 'H4': '4h', 'D1': 'D1', 'W1': '1W', 'MN1': '1M'
        }
        return symbol, tf_map.get(tf_raw, '1m')
        
    # 2. Try minutes suffix like EURUSD1, EURUSD60, EURUSD1440
    match_digits = re.match(r"^([A-Za-z0-9\-]+?)(\d+)$", base)
    if match_digits:
        symbol = match_digits.group(1)
        minutes = int(match_digits.group(2))
        if minutes == 1: tf = '1m'
        elif minutes == 5: tf = '5m'
        elif minutes == 15: tf = '15m'
        elif minutes == 30: tf = '30m'
        elif minutes == 60: tf = '1h'
        elif minutes == 240: tf = '4h'
        elif minutes == 1440: tf = 'D1'
        elif minutes == 10080: tf = '1W'
        elif minutes == 43200: tf = '1M'
        else: tf = f"{minutes}m"
        return symbol, tf
        
    # Fallback
    return base, '1m'

def ingest_single_metatrader5_file(file_path: str,
                                   symbol: str = None,
                                   timeframe: str = None,
                                   asset_class: str = 'forex',
                                   source_tz: str = 'Europe/Athens') -> dict:
    """
    Ingests a single MetaTrader 5 CSV file.
    Standardizes timezone (typically EET) to UTC naive, structures columns,
    writes Parquet files and registers the dataset in catalog.db.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"MT5 CSV file not found: {file_path}")
        
    filename = os.path.basename(file_path)
    
    # Auto-detect symbol and timeframe if not provided
    detected_symbol, detected_timeframe = parse_filename_metadata(filename)
    if not symbol:
        symbol = detected_symbol
    if not timeframe:
        timeframe = detected_timeframe
        
    print(f"Ingesting MT5 file: {filename} (symbol={symbol}, timeframe={timeframe}, asset_class={asset_class}, tz={source_tz})")
    
    # 1. Read first line to detect delimiter and headers
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        first_line = f.readline()
        
    delim = detect_delimiter(first_line)
    
    # Check if first line contains header indicators (usually starting with '<')
    has_header = False
    if '<DATE>' in first_line.upper() or '<OPEN>' in first_line.upper():
        has_header = True
        
    # 2. Read the CSV file into a DataFrame
    if has_header:
        df = pd.read_csv(file_path, sep=delim)
    else:
        # Standard default column mappings for MT5 files without headers
        # Determine number of columns by reading the first line
        parts = [p.strip() for p in re.split(re.escape(delim), first_line.strip())]
        sample_cols = len(parts)
        
        # Check if column 0 contains combined date and time
        first_part = parts[0] if sample_cols > 0 else ""
        is_combined = ' ' in first_part or ('/' in first_part and ':' in first_part) or ('-' in first_part and ':' in first_part) or ('.' in first_part and ':' in first_part)
        
        if is_combined:
            # Commonly: Timestamp, Open, High, Low, Close, TickVol, Vol, Spread
            col_names = ['timestamp', 'open', 'high', 'low', 'close', 'tickvol', 'vol', 'spread']
        else:
            # Commonly: Date, Time, Open, High, Low, Close, TickVol, Vol, Spread
            col_names = ['date', 'time', 'open', 'high', 'low', 'close', 'tickvol', 'vol', 'spread']
            
        if sample_cols < len(col_names):
            col_names = col_names[:sample_cols]
            
        df = pd.read_csv(file_path, sep=delim, header=None, names=col_names)
        
    if len(df) == 0:
        print(f"Skipping empty file: {filename}")
        return {}
        
    # Normalize column name cases and strip brackets like '<' and '>'
    df.columns = [str(c).upper().replace('<', '').replace('>', '').strip() for c in df.columns]
    
    # 3. Handle combined or separate Date and Time columns
    # MT5 separate columns: DATE (e.g. "2023.10.25") and TIME (e.g. "10:00:00")
    if 'DATE' in df.columns and 'TIME' in df.columns:
        df['TIMESTAMP'] = df['DATE'].astype(str) + ' ' + df['TIME'].astype(str)
        df = df.drop(columns=['DATE', 'TIME'])
    elif 'DATE' in df.columns:
        # Date column might have time in it
        df = df.rename(columns={'DATE': 'TIMESTAMP'})
    elif 'TIME' in df.columns:
        df = df.rename(columns={'TIME': 'TIMESTAMP'})
        
    # Map other MT5 columns to standard names
    col_mapping = {
        'OPEN': 'open',
        'HIGH': 'high',
        'LOW': 'low',
        'CLOSE': 'close',
        'TICKVOL': 'volume',
        'VOL': 'volume_real',  # Keep real volume if needed, otherwise volume is tickvol
        'SPREAD': 'spread',
        'TIMESTAMP': 'timestamp'
    }
    
    # If VOL is present and volume has not been set by TICKVOL, map appropriately
    # In MT5 forex, TickVol is standard volume. In stocks/futures, Real Vol is standard.
    if 'VOL' in df.columns and 'TICKVOL' not in df.columns:
        col_mapping['VOL'] = 'volume'
        
    df = df.rename(columns=col_mapping)
    
    # Ensure lowercase headers match the standardization pipeline expectations
    df.columns = [c.lower() if c in col_mapping.values() else c for c in df.columns]
    
    # 4. Standardize via normalizer
    standardized = rename_and_standardize(
        df=df,
        symbol=symbol,
        asset_class=asset_class,
        timeframe=timeframe,
        source="metatrader5",
        source_tz=source_tz
    )
    
    # 5. Write to hive partition Parquet lake
    write_parquet_hive(standardized)
    
    # 6. Database catalog logging
    init_db()
    null_pcts = scan_nulls(standardized)
    nulls_pct = null_pcts.get('close', 0.0)
    quality_score = compute_quality_score(standardized, timeframe)
    
    min_ts = standardized['timestamp'].min()
    max_ts = standardized['timestamp'].max()
    start_date = min_ts.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(min_ts) else "N/A"
    end_date = max_ts.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(max_ts) else "N/A"
    
    register_dataset(
        symbol=symbol,
        timeframe=timeframe,
        asset_class=asset_class,
        start_date=start_date,
        end_date=end_date,
        rows_count=len(standardized),
        nulls_pct=nulls_pct,
        quality_score=quality_score,
        source="metatrader5"
    )
    
    print(f"Successfully ingested MT5 file to Parquet and registered. Symbol: {symbol}, Rows: {len(standardized)}")
    
    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'rows': len(standardized),
        'start_date': start_date,
        'end_date': end_date,
        'quality_score': quality_score
    }

def ingest_metatrader5(path: str,
                       symbol: str = None,
                       timeframe: str = None,
                       asset_class: str = 'forex',
                       source_tz: str = 'Europe/Athens'):
    """
    Ingest MT5 exported CSV file(s).
    If path is a directory, processes all CSV files inside it.
    If path is a single file, processes just that file.
    """
    if os.path.isdir(path):
        csv_files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.csv')]
        print(f"Found {len(csv_files)} MT5 CSV files in directory: {path}")
        results = []
        for file_path in csv_files:
            try:
                res = ingest_single_metatrader5_file(
                    file_path=file_path,
                    symbol=symbol,
                    timeframe=timeframe,
                    asset_class=asset_class,
                    source_tz=source_tz
                )
                if res:
                    results.append(res)
            except Exception as e:
                print(f"Error processing MT5 file {os.path.basename(file_path)}: {e}")
        print(f"Batch MT5 ingestion completed. Successfully processed {len(results)} files.")
    else:
        ingest_single_metatrader5_file(
            file_path=path,
            symbol=symbol,
            timeframe=timeframe,
            asset_class=asset_class,
            source_tz=source_tz
        )
