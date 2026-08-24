import os
import time
import ccxt
import pandas as pd
from datetime import datetime
from tvdata.catalog import register_dataset, init_db
from tvdata.ingest.normalizer import rename_and_standardize
from tvdata.ingest.stocks import write_parquet_hive
from tvdata.quality import scan_nulls, compute_quality_score

CCXT_TIMEFRAME_MAP = {
    '1m': '1m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
    '4h': '4h',
    'D1': '1d',
    '1W': '1w',
    '1M': '1M'
}

def standardize_crypto_symbol(symbol: str) -> str:
    """Map BTCUSDT or BTC-USDT to CCXT standard BTC/USDT."""
    symbol = symbol.replace('-', '/')
    if '/' in symbol:
        return symbol
    # Insert slash before standard quote currencies
    for quote in ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH']:
        if symbol.endswith(quote):
            base = symbol[:-len(quote)]
            return f"{base}/{quote}"
    return symbol

def fetch_binance(symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    """
    Fetch historical bars from Binance using CCXT with automatic pagination loop.
    """
    interval = CCXT_TIMEFRAME_MAP.get(timeframe)
    if not interval:
        raise ValueError(f"Unsupported timeframe for CCXT/Binance: {timeframe}")
        
    ccxt_symbol = standardize_crypto_symbol(symbol)
    
    exchange = ccxt.binance({
        'enableRateLimit': True
    })
    
    # Convert dates to milliseconds timestamps
    start_ms = int(pd.to_datetime(start).timestamp() * 1000)
    end_ms = int(pd.to_datetime(end).timestamp() * 1000)
    
    print(f"Downloading Binance data for {ccxt_symbol} ({interval}) from {start} to {end}...")
    
    all_ohlcv = []
    since = start_ms
    
    # Loop for pagination
    while since < end_ms:
        try:
            ohlcv = exchange.fetch_ohlcv(
                symbol=ccxt_symbol,
                timeframe=interval,
                since=since,
                limit=1000
            )
            if not ohlcv:
                break
                
            all_ohlcv.extend(ohlcv)
            
            # Check the last timestamp returned
            last_ts = ohlcv[-1][0]
            if last_ts == since:
                # Avoid infinite loop if exchange keeps returning the same bar
                break
                
            since = last_ts + 1
            
            # Respect rate limit
            time.sleep(exchange.rateLimit / 1000.0)
            
        except Exception as e:
            print(f"Error fetching from Binance for {ccxt_symbol}: {e}")
            break
            
    if not all_ohlcv:
        return pd.DataFrame()
        
    # Convert to DataFrame
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Filter to end date range just in case
    df = df[df['timestamp'] <= pd.to_datetime(end)]
    
    return df

def ingest_binance(symbol: str,
                   timeframe: str,
                   start_date: str,
                   end_date: str) -> dict:
    """
    Fetch crypto data from Binance, normalize, write to data lake and catalog.
    """
    # Force clean crypto symbol representation (e.g. BTCUSDT without slash for standard storage symbol)
    storage_symbol = symbol.replace('/', '').replace('-', '').upper()
    
    df = fetch_binance(symbol, timeframe, start_date, end_date)
    if len(df) == 0:
        print(f"No data retrieved from Binance for {symbol}")
        return {}
        
    # Standardize
    standardized = rename_and_standardize(
        df=df,
        symbol=storage_symbol,
        asset_class="crypto",
        timeframe=timeframe,
        source="binance",
        source_tz="UTC"  # CCXT uses UTC epoch ms
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
        symbol=storage_symbol,
        timeframe=timeframe,
        asset_class="crypto",
        start_date=start_str,
        end_date=end_str,
        rows_count=len(standardized),
        nulls_pct=nulls_pct,
        quality_score=quality_score,
        source="binance"
    )
    
    print(f"Successfully ingested Binance data for {storage_symbol} ({timeframe}). Rows: {len(standardized)}")
    return {
        'symbol': storage_symbol,
        'timeframe': timeframe,
        'rows': len(standardized),
        'start_date': start_str,
        'end_date': end_str,
        'quality_score': quality_score
    }
