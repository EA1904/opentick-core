import os
import duckdb
import pandas as pd
from tvdata.catalog import get_all_datasets
from tvdata.config import DB_PATH, LAKE_ROOT, LAKE_PATTERN

import threading

_db_lock = threading.Lock()
_CONN = None
_last_scan_pattern = None

def get_duckdb_conn():
    """Returns a thread-safe global DuckDB connection."""
    global _CONN
    if _CONN is None:
        _CONN = duckdb.connect(database=':memory:')
    return _CONN

def sql(query: str) -> pd.DataFrame:
    """
    Execute a raw SQL query using DuckDB.
    You can query the 'ohlcv' table directly:
    e.g. sql("SELECT * FROM ohlcv WHERE symbol='AAPL'")
    """
    global _last_scan_pattern
    
    # Optimize Parquet scan path to avoid scanning the entire database lake (6000+ folders)
    # when timeframe/symbol are specified in the query.
    import re
    import sqlite3
    
    timeframe_match = re.search(r"timeframe\s*=\s*'([^']+)'", query, re.IGNORECASE)
    symbol_match = re.search(r"symbol\s*(?:=\s*'([^']+)'|IN\s*\(\s*'([^']+)'\s*\))", query, re.IGNORECASE)
    
    tf = timeframe_match.group(1) if timeframe_match else None
    sym = None
    if symbol_match:
        sym = symbol_match.group(1) or symbol_match.group(2)
    
    scan_pattern = LAKE_PATTERN
    
    test_dir = os.path.join(LAKE_ROOT, "ohlcv")
    if os.path.exists(test_dir) and any(os.scandir(test_dir)):
        if tf:
            asset_class = None
            db_path = DB_PATH
            if sym and os.path.exists(db_path):
                try:
                    with sqlite3.connect(db_path) as db_conn:
                        cursor = db_conn.cursor()
                        cursor.execute("SELECT asset_class FROM data_catalog WHERE symbol = ? LIMIT 1", (sym.upper(),))
                        row = cursor.fetchone()
                        if row:
                            asset_class = row[0]
                except Exception:
                    pass
            
            if asset_class:
                if sym:
                    scan_pattern = os.path.join(LAKE_ROOT, "ohlcv", f"asset_class={asset_class}", f"timeframe={tf}", f"symbol={sym.upper()}", "**", "*.parquet").replace(os.sep, '/')
                else:
                    scan_pattern = os.path.join(LAKE_ROOT, "ohlcv", f"asset_class={asset_class}", f"timeframe={tf}", "**", "*.parquet").replace(os.sep, '/')
            else:
                if sym:
                    scan_pattern = os.path.join(LAKE_ROOT, "ohlcv", "*", f"timeframe={tf}", f"symbol={sym.upper()}", "**", "*.parquet").replace(os.sep, '/')
                else:
                    scan_pattern = os.path.join(LAKE_ROOT, "ohlcv", "*", f"timeframe={tf}", "**", "*.parquet").replace(os.sep, '/')
                
    with _db_lock:
        conn = get_duckdb_conn()
        if scan_pattern != _last_scan_pattern:
            if os.path.exists(test_dir) and any(os.scandir(test_dir)):
                conn.execute(f"CREATE OR REPLACE VIEW ohlcv AS SELECT * FROM parquet_scan('{scan_pattern}', hive_partitioning=true)")
            else:
                # Create an empty dummy view so queries don't crash immediately if empty
                conn.execute("""
                CREATE OR REPLACE VIEW ohlcv AS 
                SELECT 
                    CAST(NULL AS TIMESTAMP) as timestamp, 
                    CAST(NULL AS VARCHAR) as symbol, 
                    CAST(NULL AS VARCHAR) as asset_class, 
                    CAST(NULL AS VARCHAR) as timeframe,
                    CAST(NULL AS DOUBLE) as open, 
                    CAST(NULL AS DOUBLE) as high, 
                    CAST(NULL AS DOUBLE) as low, 
                    CAST(NULL AS DOUBLE) as close, 
                    CAST(NULL AS DOUBLE) as volume,
                    CAST(NULL AS DOUBLE) as adj_close, 
                    CAST(NULL AS DOUBLE) as adj_factor, 
                    CAST(NULL AS VARCHAR) as source, 
                    CAST(NULL AS INTEGER) as year
                WHERE 1=0
                """)
            _last_scan_pattern = scan_pattern
            
        res = conn.execute(query).df()
    return res

def get_ohlcv(symbol, 
              timeframe: str = 'D1', 
              start: str = None, 
              end: str = None, 
              adjusted: bool = True) -> pd.DataFrame:
    """
    Query the Parquet Data Lake for the specified symbol(s) and timeframe.
    
    Parameters:
      - symbol: string (e.g. "AAPL") or list of strings
      - timeframe: "D1", "1m", etc.
      - start: start date string (e.g. "2020-01-01")
      - end: end date string (e.g. "2024-12-31")
      - adjusted: 
        - True: returns split/dividend adjusted prices (ohlc are multiplied by adj_factor)
        - False: returns raw/unadjusted prices
        - 'factor': returns raw prices + adj_factor column explicitly
    """
    # Standardize symbol input to list of strings
    if isinstance(symbol, str):
        symbols = [symbol]
    else:
        symbols = list(symbol)
        
    symbol_list_str = ", ".join([f"'{s}'" for s in symbols])
    
    # We must determine the scan pattern exactly like sql() does, to align perfectly
    tf = timeframe
    sym = symbols[0] if len(symbols) == 1 else None
    scan_pattern = LAKE_PATTERN
    
    test_dir = os.path.join(LAKE_ROOT, "ohlcv")
    if os.path.exists(test_dir) and any(os.scandir(test_dir)):
        asset_class = None
        db_path = DB_PATH
        if sym and os.path.exists(db_path):
            import sqlite3
            try:
                with sqlite3.connect(db_path) as db_conn:
                    cursor = db_conn.cursor()
                    cursor.execute("SELECT asset_class FROM data_catalog WHERE symbol = ? LIMIT 1", (sym.upper(),))
                    row = cursor.fetchone()
                    if row:
                        asset_class = row[0]
            except Exception:
                pass
        
        if asset_class:
            if sym:
                scan_pattern = os.path.join(LAKE_ROOT, "ohlcv", f"asset_class={asset_class}", f"timeframe={tf}", f"symbol={sym.upper()}", "**", "*.parquet").replace(os.sep, '/')
            else:
                scan_pattern = os.path.join(LAKE_ROOT, "ohlcv", f"asset_class={asset_class}", f"timeframe={tf}", "**", "*.parquet").replace(os.sep, '/')
        else:
            if sym:
                scan_pattern = os.path.join(LAKE_ROOT, "ohlcv", "*", f"timeframe={tf}", f"symbol={sym.upper()}", "**", "*.parquet").replace(os.sep, '/')
            else:
                scan_pattern = os.path.join(LAKE_ROOT, "ohlcv", "*", f"timeframe={tf}", "**", "*.parquet").replace(os.sep, '/')
                
    global _last_scan_pattern
    
    with _db_lock:
        conn = get_duckdb_conn()
        if scan_pattern != _last_scan_pattern:
            if os.path.exists(test_dir) and any(os.scandir(test_dir)):
                conn.execute(f"CREATE OR REPLACE VIEW ohlcv AS SELECT * FROM parquet_scan('{scan_pattern}', hive_partitioning=true)")
            else:
                # Dummy empty view
                conn.execute("""
                CREATE OR REPLACE VIEW ohlcv AS 
                SELECT 
                    CAST(NULL AS TIMESTAMP) as timestamp, 
                    CAST(NULL AS VARCHAR) as symbol, 
                    CAST(NULL AS VARCHAR) as asset_class, 
                    CAST(NULL AS VARCHAR) as timeframe,
                    CAST(NULL AS DOUBLE) as open, 
                    CAST(NULL AS DOUBLE) as high, 
                    CAST(NULL AS DOUBLE) as low, 
                    CAST(NULL AS DOUBLE) as close, 
                    CAST(NULL AS DOUBLE) as volume,
                    CAST(NULL AS DOUBLE) as adj_close, 
                    CAST(NULL AS DOUBLE) as adj_factor, 
                    CAST(NULL AS VARCHAR) as source, 
                    CAST(NULL AS INTEGER) as year
                WHERE 1=0
                """)
            _last_scan_pattern = scan_pattern
            
        # Inspect columns in the created view
        try:
            columns_info = conn.execute("PRAGMA table_info('ohlcv')").fetchall()
            available_cols = {col[1].lower() for col in columns_info}
        except Exception:
            available_cols = set()
            
    # Build query clauses
    where_clauses = [
        f"timeframe = '{timeframe}'",
        f"symbol IN ({symbol_list_str})"
    ]
    if start:
        where_clauses.append(f"timestamp >= '{start}'")
    if end:
        where_clauses.append(f"timestamp <= '{end}'")
    where_str = " AND ".join(where_clauses)
    
    select_items = ["timestamp", "symbol"]
    if "asset_class" in available_cols:
        select_items.append("asset_class")
    else:
        select_items.append("CAST(NULL AS VARCHAR) as asset_class")
        
    if "timeframe" in available_cols:
        select_items.append("timeframe")
    else:
        select_items.append("CAST(NULL AS VARCHAR) as timeframe")
        
    for col in ["open", "high", "low", "close", "volume"]:
        if col in available_cols:
            select_items.append(col)
        else:
            select_items.append(f"CAST(NULL AS DOUBLE) as {col}")
            
    if "adj_close" in available_cols:
        select_items.append("adj_close")
    elif "close" in available_cols and "adj_factor" in available_cols:
        select_items.append("close * adj_factor as adj_close")
    elif "close" in available_cols:
        select_items.append("close as adj_close")
    else:
        select_items.append("CAST(NULL AS DOUBLE) as adj_close")
        
    if "adj_factor" in available_cols:
        select_items.append("adj_factor")
    else:
        select_items.append("1.0 as adj_factor")
        
    if "source" in available_cols:
        select_items.append("source")
    else:
        select_items.append("CAST(NULL AS VARCHAR) as source")
        
    select_str = ", ".join(select_items)
    
    query = f"""
        SELECT {select_str}
        FROM ohlcv
        WHERE {where_str}
        ORDER BY symbol, timestamp ASC
    """
    
    df = sql(query)
    
    if len(df) == 0:
        return df
        
    # Deduplicate by symbol and timestamp to handle duplicate rows from multi-source overlap
    df = df.drop_duplicates(subset=['symbol', 'timestamp'])
        
    # Adjust prices if requested
    if adjusted is True:
        # Standardize OHLC using the adj_factor
        # open_adjusted = open * adj_factor, etc.
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col] * df['adj_factor']
            
        # Drop raw columns
        if 'adj_factor' in df.columns:
            df = df.drop(columns=['adj_factor'])
        
    elif adjusted is False:
        # Drop adj_close and adj_factor to return raw values
        for col in ['adj_close', 'adj_factor']:
            if col in df.columns:
                df = df.drop(columns=[col])
        
    return df

def catalog() -> pd.DataFrame:
    """Return a DataFrame summarizing all datasets stored in the database."""
    return get_all_datasets()
