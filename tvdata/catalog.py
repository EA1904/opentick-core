import sqlite3
import os
from datetime import datetime
import pandas as pd

from tvdata.config import DB_PATH as DEFAULT_DB_PATH, LAKE_ROOT

def get_conn(db_path: str = DEFAULT_DB_PATH):
    """Get connection to the SQLite catalog database. Creates parent dirs if needed."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: str = DEFAULT_DB_PATH):
    """Initialize database tables if they do not exist."""
    conn = get_conn(db_path)
    cursor = conn.cursor()
    
    # 1. Symbols Metadata Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS symbols_metadata (
        symbol TEXT PRIMARY KEY,
        exchange TEXT,
        shortname TEXT,
        longname TEXT,
        sector TEXT,
        industry TEXT,
        marketcap REAL,
        weight REAL,
        summary TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Ingested Data Catalog Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS data_catalog (
        symbol TEXT,
        timeframe TEXT,
        asset_class TEXT,
        start_date TEXT,
        end_date TEXT,
        rows_count INTEGER,
        nulls_pct REAL,
        quality_score REAL,
        source TEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, timeframe)
    )
    """)
    
    conn.commit()
    conn.close()

def register_metadata(symbol: str, 
                      exchange: str = None, 
                      shortname: str = None, 
                      longname: str = None,
                      sector: str = None, 
                      industry: str = None, 
                      marketcap: float = None, 
                      weight: float = None, 
                      summary: str = None,
                      db_path: str = DEFAULT_DB_PATH):
    """Insert or replace symbol metadata in symbols_metadata table."""
    conn = get_conn(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    INSERT OR REPLACE INTO symbols_metadata 
    (symbol, exchange, shortname, longname, sector, industry, marketcap, weight, summary, last_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol, exchange, shortname, longname, sector, industry, marketcap, weight, summary, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

def register_dataset(symbol: str, 
                     timeframe: str, 
                     asset_class: str, 
                     start_date: str, 
                     end_date: str, 
                     rows_count: int, 
                     nulls_pct: float, 
                     quality_score: float, 
                     source: str,
                     db_path: str = DEFAULT_DB_PATH):
    """Insert or replace dataset info in data_catalog table."""
    conn = get_conn(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    INSERT OR REPLACE INTO data_catalog 
    (symbol, timeframe, asset_class, start_date, end_date, rows_count, nulls_pct, quality_score, source, last_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (symbol, timeframe, asset_class, start_date, end_date, rows_count, nulls_pct, quality_score, source, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

def get_metadata(symbol: str, db_path: str = DEFAULT_DB_PATH) -> dict:
    """Fetch metadata for a symbol as a dictionary."""
    conn = get_conn(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM symbols_metadata WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_datasets(db_path: str = DEFAULT_DB_PATH) -> pd.DataFrame:
    """Fetch all dataset catalog records as a pandas DataFrame."""
    conn = get_conn(db_path)
    df = pd.read_sql_query("SELECT * FROM data_catalog", conn)
    conn.close()
    return df

def recalculate_catalog_entry(symbol: str, 
                              timeframe: str, 
                              asset_class: str, 
                              source: str,
                              db_path: str = DEFAULT_DB_PATH):
    """
    Scan Parquet lake using DuckDB to compute actual start_date, end_date, rows_count,
    and nulls_pct, and update catalog.db.
    """
    import duckdb
    
    lake_root = os.path.join(LAKE_ROOT, "ohlcv")
    pattern = f"{lake_root}/asset_class={asset_class}/timeframe={timeframe}/symbol={symbol.upper()}/**/*.parquet"
    pattern_db = pattern.replace('\\', '/')
    
    con = duckdb.connect()
    try:
        # Check if files exist
        query_check = f"SELECT count(*) as count FROM glob('{pattern_db}')"
        files_count = con.execute(query_check).fetchone()[0]
        if files_count == 0:
            print(f"No files found for {symbol} in data lake to recalculate.")
            return
            
        query = f"SELECT min(timestamp) as start_date, max(timestamp) as end_date, count_star() as rows_count, sum(case when close is null then 1 else 0 end) as nulls_count FROM parquet_scan('{pattern_db}', hive_partitioning=true)"
        res = con.execute(query).df()
        if len(res) == 0 or res.iloc[0]['rows_count'] == 0:
            return
            
        row = res.iloc[0]
        start_date = row['start_date']
        end_date = row['end_date']
        rows_count = int(row['rows_count'])
        nulls_count = int(row['nulls_count']) if pd.notnull(row['nulls_count']) else 0
        nulls_pct = (nulls_count / rows_count) * 100.0 if rows_count > 0 else 0.0
        
        # Re-compute simple quality score
        from tvdata.quality import compute_quality_score
        # Fetch data to compute quality score or use a simpler placeholder
        quality_score = max(0.0, 100.0 - (nulls_pct * 2.0))
        
        start_str = start_date.strftime('%Y-%m-%d %H:%M:%S') if timeframe != 'D1' else start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d %H:%M:%S') if timeframe != 'D1' else end_date.strftime('%Y-%m-%d')
        
        register_dataset(
            symbol=symbol,
            timeframe=timeframe,
            asset_class=asset_class,
            start_date=start_str,
            end_date=end_str,
            rows_count=rows_count,
            nulls_pct=nulls_pct,
            quality_score=quality_score,
            source=source,
            db_path=db_path
        )
        print(f"Consolidated catalog stats for {symbol} ({timeframe}): {start_str} to {end_str}, Rows: {rows_count}")
    except Exception as e:
        print(f"Error recalculating catalog stats for {symbol} ({timeframe}): {e}")
    finally:
        con.close()

