import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from tvdata.catalog import register_dataset, init_db, recalculate_catalog_entry
from tvdata.ingest.normalizer import rename_and_standardize
from tvdata.ingest.stocks import write_parquet_hive
from tvdata.quality import scan_nulls, compute_quality_score

TIMEFRAME_MAP = {
    '1m': '1m',
    '2m': '2m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
    '4h': '1h',  # Fetch 1h, user can resample
    'D1': '1d',
    '1W': '1wk',
    '1M': '1mo'
}

def fetch_yfinance(symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch OHLCV data from yfinance for a symbol, timeframe, and date range.
    Handles yfinance specific time limits for intraday data.
    """
    interval = TIMEFRAME_MAP.get(timeframe)
    if not interval:
        raise ValueError(f"Unsupported timeframe for yfinance: {timeframe}")
        
    start_dt = pd.to_datetime(start)
    end_dt = pd.to_datetime(end)
    today = datetime.now()
    
    # yfinance limitations for intraday data
    if timeframe == '1m':
        limit_date = today - timedelta(days=29)
        if start_dt < limit_date:
            print(f"Warning: 1m data for yfinance is limited to last 30 days. Truncating start date from {start} to {limit_date.strftime('%Y-%m-%d')}")
            start_dt = limit_date
    elif timeframe in ['2m', '5m', '15m', '30m', '1h', '4h']:
        limit_date = today - timedelta(days=59)
        if start_dt < limit_date:
            print(f"Warning: Intraday data ({timeframe}) for yfinance is limited to last 60 days. Truncating start date from {start} to {limit_date.strftime('%Y-%m-%d')}")
            start_dt = limit_date
            
    if start_dt >= end_dt:
        print(f"No new dates to query for {symbol} ({timeframe}) after yfinance limitation check.")
        return pd.DataFrame()
        
    start_str = start_dt.strftime('%Y-%m-%d')
    end_str = end_dt.strftime('%Y-%m-%d')
    
    # Download data
    print(f"Downloading yfinance data for {symbol} ({interval}) from {start_str} to {end_str}...")
    df = yf.download(
        tickers=symbol,
        start=start_str,
        end=end_str,
        interval=interval,
        progress=False,
        auto_adjust=False
    )
    
    if len(df) == 0:
        return pd.DataFrame()
        
    df = df.reset_index()
    
    # Flatten MultiIndex columns if present (common in yfinance >= 0.2)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    return df

def ingest_yfinance(symbol: str,
                    timeframe: str,
                    start_date: str,
                    end_date: str,
                    asset_class: str = 'stocks',
                    source_tz: str = 'America/New_York') -> dict:
    """
    Fetch data from yfinance, normalize it, save to the Parquet lake, and register in catalog.db.
    """
    # yfinance specific symbol mapping for Forex
    yf_symbol = symbol
    if asset_class == 'forex':
        if not symbol.endswith('=X'):
            yf_symbol = f"{symbol}=X"
        # Forex timezone is UTC
        source_tz = 'UTC'
    elif symbol.startswith('^'):
        asset_class = 'indices'
        
    df = fetch_yfinance(yf_symbol, timeframe, start_date, end_date)
    if len(df) == 0:
        print(f"No data retrieved from yfinance for {symbol}")
        return {}
        
    # Standardize DataFrame
    standardized = rename_and_standardize(
        df=df,
        symbol=symbol,  # Use normalized standard symbol (without =X)
        asset_class=asset_class,
        timeframe=timeframe,
        source="yfinance",
        source_tz=source_tz
    )
    
    # Write to Parquet lake
    write_parquet_hive(standardized)
    
    # Register dataset in SQLite catalog
    init_db()
    null_pcts = scan_nulls(standardized)
    nulls_pct = null_pcts.get('close', 0.0)
    quality_score = compute_quality_score(standardized, timeframe)
    
    min_ts = standardized['timestamp'].min()
    max_ts = standardized['timestamp'].max()
    start_str = min_ts.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(min_ts) else "N/A"
    end_str = max_ts.strftime('%Y-%m-%d %H:%M:%S') if pd.notnull(max_ts) else "N/A"
    
    register_dataset(
        symbol=symbol,
        timeframe=timeframe,
        asset_class=asset_class,
        start_date=start_str,
        end_date=end_str,
        rows_count=len(standardized),
        nulls_pct=nulls_pct,
        quality_score=quality_score,
        source="yfinance"
    )
    recalculate_catalog_entry(
        symbol=symbol,
        timeframe=timeframe,
        asset_class=asset_class,
        source="yfinance"
    )
    
    print(f"Successfully ingested yfinance data for {symbol} ({timeframe}). Rows: {len(standardized)}")
    return {
        'symbol': symbol,
        'timeframe': timeframe,
        'rows': len(standardized),
        'start_date': start_str,
        'end_date': end_str,
        'quality_score': quality_score
    }
