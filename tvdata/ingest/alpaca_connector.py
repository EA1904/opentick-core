import os
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from tvdata.catalog import register_dataset, init_db, recalculate_catalog_entry
from tvdata.ingest.normalizer import rename_and_standardize
from tvdata.ingest.stocks import write_parquet_hive
from tvdata.quality import scan_nulls, compute_quality_score

TIMEFRAME_MAP = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "1h": "1Hour",
    "D1": "1Day"
}

def ingest_alpaca(symbol: str,
                  timeframe: str,
                  start_date: str,
                  end_date: str,
                  asset_class: str = 'stocks') -> dict:
    """
    Fetch historical OHLCV data from Alpaca Market Data API (v2),
    normalize it, save to the Parquet data lake, and register it in catalog.db.
    """
    load_dotenv()
    
    api_key = os.getenv('APCA_API_KEY_ID')
    api_secret = os.getenv('APCA_API_SECRET_KEY')
    
    if not api_key or not api_secret:
        print("Warning: Alpaca API credentials not found in .env. Skipping ingestion.")
        return {}
        
    interval = TIMEFRAME_MAP.get(timeframe)
    if not interval:
        raise ValueError(f"Unsupported timeframe for Alpaca: {timeframe}")
        
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    
    # Alpaca Free Tier has a 2-year historical data limit
    now_utc = datetime.now(timezone.utc)
    limit_date = now_utc - timedelta(days=2 * 365)
    
    if start_dt.tzinfo is None:
        start_dt = start_dt.tz_localize(timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.tz_localize(timezone.utc)
        
    if start_dt < limit_date:
        print(f"Warning: Alpaca free tier is limited to last 2 years. Truncating start date from {start_date} to {limit_date.strftime('%Y-%m-%d')}")
        start_dt = limit_date
        
    if start_dt >= end_dt:
        print(f"No new dates to query for {symbol} ({timeframe}) after Alpaca limitation check.")
        return {}
        
    start_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    url = "https://data.alpaca.markets/v2/stocks/bars"
    headers = {
        "accept": "application/json",
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    params = {
        "symbols": symbol.upper(),
        "timeframe": interval,
        "start": start_iso,
        "end": end_iso,
        "limit": 10000,
        "feed": "iex",
        "sort": "asc"
    }
    
    all_bars = []
    next_page_token = None
    
    print(f"Downloading Alpaca data for {symbol} ({interval}) from {start_iso} to {end_iso}...")
    
    while True:
        if next_page_token:
            params['page_token'] = next_page_token
        else:
            params.pop('page_token', None)
            
        try:
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code != 200:
                print(f"Error calling Alpaca API: {r.status_code} - {r.text}")
                break
                
            res_json = r.json()
            bars_dict = res_json.get('bars', {})
            symbol_bars = bars_dict.get(symbol.upper(), [])
            
            if not symbol_bars:
                break
                
            all_bars.extend(symbol_bars)
            
            next_page_token = res_json.get('next_page_token')
            if not next_page_token:
                break
        except Exception as e:
            print(f"Exception fetching Alpaca data: {e}")
            break
            
    if not all_bars:
        print(f"No data retrieved from Alpaca for {symbol}")
        return {}
        
    # Convert list of bars to DataFrame
    df = pd.DataFrame(all_bars)
    
    # Rename Alpaca columns to match standard schema
    df = df.rename(columns={
        't': 'timestamp',
        'o': 'open',
        'h': 'high',
        'l': 'low',
        'c': 'close',
        'v': 'volume'
    })
    
    # Standardize data format
    standardized = rename_and_standardize(
        df=df,
        symbol=symbol.upper(),
        asset_class=asset_class,
        timeframe=timeframe,
        source="alpaca",
        source_tz="UTC"  # Alpaca works in UTC
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
        symbol=symbol.upper(),
        timeframe=timeframe,
        asset_class=asset_class,
        start_date=start_str,
        end_date=end_str,
        rows_count=len(standardized),
        nulls_pct=nulls_pct,
        quality_score=quality_score,
        source="alpaca"
    )
    recalculate_catalog_entry(
        symbol=symbol.upper(),
        timeframe=timeframe,
        asset_class=asset_class,
        source="alpaca"
    )
    
    print(f"Successfully ingested Alpaca data for {symbol} ({timeframe}). Rows: {len(standardized)}")
    return {
        'symbol': symbol.upper(),
        'timeframe': timeframe,
        'rows': len(standardized),
        'start_date': start_str,
        'end_date': end_str,
        'quality_score': quality_score
    }
