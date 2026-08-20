import os
import sqlite3
import pandas as pd
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from tvdata.get import get_ohlcv
from tvdata.ingest.alpaca_connector import ingest_alpaca
from tvdata.ingest.yfinance_connector import ingest_yfinance
from tvdata.ingest.fred_connector import ingest_fred_series

import asyncio
import subprocess
import sys

app = FastAPI(title="OpenTick — Data Explorer")

async def run_auto_update_loop():
    # Delay first run by 10 seconds to allow smooth server start
    await asyncio.sleep(10)
    while True:
        print("[Auto-Updater] Lancement de l'actualisation automatique en arrière-plan...")
        try:
            subprocess.Popen([sys.executable, "-m", "tvdata.ingest.update_all_stocks"])
        except Exception as e:
            print(f"[Auto-Updater] Erreur lors du lancement de l'actualisation : {e}")
        
        # Attendre 24 heures avant la prochaine actualisation
        await asyncio.sleep(86400)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(run_auto_update_loop())

from tvdata.config import DB_PATH, LAKE_ROOT, PROGRESS_FILE

class IngestRequest(BaseModel):
    symbol: str
    timeframe: str
    source: str
    start_date: str
    end_date: str
    asset_class: str = "stocks"

class SQLRequest(BaseModel):
    query: str

def get_db_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/symbols")
def get_symbols():
    """Fetch all registered symbols and their metadata from catalog.db."""
    if not os.path.exists(DB_PATH):
        return []
    
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        # Fetch S&P 500 constituents catalog entries merged with symbol metadata
        query = """
            SELECT 
                c.symbol, c.timeframe, c.asset_class, c.start_date, c.end_date, c.rows_count, 
                c.quality_score, c.source, c.nulls_pct,
                m.exchange, m.shortname, m.longname, m.sector, m.industry, m.marketcap, m.weight, m.summary
            FROM data_catalog c
            LEFT JOIN symbols_metadata m ON c.symbol = m.symbol
            WHERE c.asset_class != 'stocks' OR c.symbol IN (SELECT symbol FROM historical_sp500_tickers)
        """
        df = pd.read_sql_query(query, conn)
        df = df.replace({np.nan: None})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return []
    finally:
        conn.close()

@app.get("/api/stats")
def get_stats_endpoint():
    """Fetch global statistics for the S&P 500 catalog."""
    if not os.path.exists(DB_PATH):
        return {"total": 0, "imported": 0, "missing": 0}
        
    conn = get_db_conn()
    cursor = conn.cursor()
    try:
        total = cursor.execute("SELECT COUNT(*) FROM historical_sp500_tickers").fetchone()[0]
        imported = cursor.execute("""
            SELECT COUNT(DISTINCT symbol) 
            FROM data_catalog 
            WHERE asset_class = 'stocks' 
              AND symbol IN (SELECT symbol FROM historical_sp500_tickers)
              AND rows_count > 0
        """).fetchone()[0]
        
        missing = total - imported
        return {
            "total": total,
            "imported": imported,
            "missing": missing
        }
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return {"total": 0, "imported": 0, "missing": 0}
    finally:
        conn.close()

@app.get("/api/ohlcv")
def get_ohlcv_endpoint(symbol: str, timeframe: str, adjusted: bool = True, start_date: str = None, end_date: str = None):
    """Fetch OHLCV data from the Parquet lake and format for TradingView Lightweight Charts."""
    try:
        df = get_ohlcv(symbol, timeframe=timeframe, adjusted=adjusted)
        if len(df) == 0:
            return []
        
        # Sort by timestamp ascending
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Filter by date range if provided
        if start_date:
            df = df[df['timestamp'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['timestamp'] <= pd.to_datetime(end_date)]

        if len(df) == 0:
            return []

        # Deduplicate: keep last entry per timestamp to avoid LightweightCharts errors
        df = df.drop_duplicates(subset=['timestamp'], keep='last')
            
        records = []
        is_daily = (timeframe in ['D1', '1W', '1M'])
        
        for _, row in df.iterrows():
            if is_daily:
                # LightweightCharts requires "YYYY-MM-DD" string for daily series
                time_val = pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d')
            else:
                # For intraday: unix timestamp in seconds
                time_val = int(pd.to_datetime(row['timestamp']).timestamp())
            
            records.append({
                'time': time_val,
                'open': float(row['open']) if pd.notnull(row['open']) else None,
                'high': float(row['high']) if pd.notnull(row['high']) else None,
                'low': float(row['low']) if pd.notnull(row['low']) else None,
                'close': float(row['close']) if pd.notnull(row['close']) else None,
                'value': float(row['volume']) if pd.notnull(row['volume']) else 0.0
            })
            
        # Filter out invalid rows (must have open and close prices)
        records = [r for r in records if r['open'] is not None and r['close'] is not None]
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/financials/{symbol}")
def get_financials_endpoint(symbol: str):
    """Fetch quarterly financials from Parquet lake for a symbol."""
    path = os.path.join(LAKE_ROOT, "financials", "quarterly", f"{symbol.upper()}.parquet")
    if not os.path.exists(path):
        return []
        
    try:
        df = pd.read_parquet(path)
        # Format dates
        df['report_date'] = df['report_date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error loading financials: {e}")
        return []

@app.get("/api/macro/{symbol}")
def get_macro_endpoint(symbol: str, start_date: str = None, end_date: str = None):
    """Fetch macroeconomic line series from Parquet lake."""
    path = os.path.join(LAKE_ROOT, "macro", f"{symbol.lower()}.parquet")
    if not os.path.exists(path):
        path = os.path.join(LAKE_ROOT, "macro", f"{symbol.upper()}.parquet")
        if not os.path.exists(path):
            if symbol.upper() == "US_YIELD_CURVE":
                path = os.path.join(LAKE_ROOT, "macro", "yield_curve.parquet")
            else:
                return []
                
    try:
        df = pd.read_parquet(path)
        
        # Filter by date range if provided
        if start_date:
            df = df[df['timestamp'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['timestamp'] <= pd.to_datetime(end_date)]

        if len(df) == 0:
            return []

        if 'value' in df.columns:
            df = df.rename(columns={'value': 'val'})
        elif 't_note_10y' in df.columns:
            df['val'] = df['t_note_10y']
            
        records = []
        for _, row in df.iterrows():
            ts = int(row['timestamp'].timestamp())
            records.append({
                'time': ts,
                'value': float(row['val']) if pd.notnull(row['val']) else 0.0
            })
        return sorted(records, key=lambda x: x['time'])
    except Exception as e:
        print(f"Error loading macro series: {e}")
        return []

@app.post("/api/ingest")
def run_ingest(req: IngestRequest):
    """Trigger stock/forex ingestion on the fly via Alpaca or yfinance connectors."""
    symbol = req.symbol.upper()
    timeframe = req.timeframe
    source = req.source.lower()
    start_date = req.start_date
    end_date = req.end_date
    asset_class = req.asset_class
    
    print(f"Ingesting: {symbol} ({timeframe}) from {source} [{start_date} -> {end_date}]")
    
    try:
        if source == "alpaca":
            res = ingest_alpaca(symbol, timeframe, start_date, end_date, asset_class)
        elif source == "yfinance":
            res = ingest_yfinance(symbol, timeframe, start_date, end_date, asset_class)
        elif source == "fred":
            api_key = os.environ.get('FRED_API_KEY') or os.environ.get('fred_api_key')
            if not api_key or api_key == "your_fred_api_key_here":
                raise HTTPException(status_code=400, detail="Clé FRED_API_KEY absente ou invalide dans le fichier .env. Veuillez configurer votre clé API FRED.")
            res = ingest_fred_series(symbol, symbol, start_date, end_date)
        else:
            raise HTTPException(status_code=400, detail="Source invalide. Les sources supportées sont 'alpaca', 'yfinance' et 'fred'")
            
        if not res or res.get('rows', 0) == 0:
            raise HTTPException(status_code=400, detail=f"Aucune donnée retournée par la source {source}. Vérifiez le symbole et les dates.")
            
        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import subprocess
import sys

@app.post("/api/ingest/missing")
def trigger_ingest_missing():
    """Start ingestion script for missing S&P 500 stocks in background."""
    try:
        subprocess.Popen([sys.executable, "-m", "tvdata.ingest.ingest_missing_sp500"])
        return {"status": "started", "message": "Importation des symboles manquants démarrée en arrière-plan."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ingest/update_all")
def trigger_update_all():
    """Start update script for all local stocks in background."""
    try:
        subprocess.Popen([sys.executable, "-m", "tvdata.ingest.update_all_stocks"])
        return {"status": "started", "message": "Actualisation de toutes les actions démarrée en arrière-plan."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

import re

@app.post("/api/sql")
def execute_sql_query(req: SQLRequest):
    """Execute arbitrary SQL query against the DuckDB data lake."""
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="La requête ne peut pas être vide.")
    
    # Read-only security check (since this is a local app)
    forbidden = ["insert", "update", "delete", "drop", "create table", "alter", "vacuum", "copy"]
    query_lower = query.lower()
    for word in forbidden:
        if re.search(r"\b" + word + r"\b", query_lower):
            raise HTTPException(status_code=400, detail=f"La commande '{word}' n'est pas autorisée. Seules les requêtes de lecture (SELECT) sont acceptées.")
            
    try:
        from tvdata.get import sql as run_sql
        df = run_sql(query)
        # Handle nan/none conversions
        df = df.replace({np.nan: None})
        
        # Convert timestamp/datetime columns to string representation
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')
                
        # Limit rows returned to prevent browser freeze on huge tables
        max_rows = 500
        truncated = False
        total_count = len(df)
        if total_count > max_rows:
            df = df.head(max_rows)
            truncated = True
            
        return {
            "columns": list(df.columns),
            "rows": df.to_dict(orient='records'),
            "truncated": truncated,
            "total_rows": total_count,
            "max_rows": max_rows
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

import duckdb

@app.get("/api/datasets_status/{symbol}")
def get_datasets_status(symbol: str):
    symbol = symbol.upper()
    status = {
        "ohlcv": [],
        "financials": {
            "income": False,
            "balance": False,
            "cashflow": False
        },
        "volatility": False,
        "options": False,
        "corporate_actions": False,
        "macro": [],
        "bloomberg_fundamentals": False,
        "bloomberg_volatility": False
    }
    
    # 1. OHLCV timeframes & Macro list
    conn = get_db_conn()
    try:
        rows = conn.execute("SELECT DISTINCT timeframe FROM data_catalog WHERE symbol = ?", (symbol,)).fetchall()
        status["ohlcv"] = sorted(list(set([r["timeframe"] for r in rows])))
        
        macro_rows = conn.execute("SELECT DISTINCT symbol FROM data_catalog WHERE asset_class = 'macro'").fetchall()
        status["macro"] = [r["symbol"] for r in macro_rows]
    except Exception as e:
        print(f"Error checking catalog for status: {e}")
    finally:
        conn.close()
        
    # 2. Financials
    fin_path = os.path.join(LAKE_ROOT, "financials", "quarterly", f"{symbol}.parquet")
    if os.path.exists(fin_path):
        status["financials"]["income"] = True
        status["financials"]["balance"] = True
        status["financials"]["cashflow"] = True
        
    # 3. Volatility
    vol_path = os.path.join(LAKE_ROOT, "volatility", "options_vol.parquet")
    if os.path.exists(vol_path):
        try:
            db_conn = duckdb.connect(database=':memory:')
            res = db_conn.execute(f"SELECT COUNT(*) FROM parquet_scan('{vol_path.replace(os.sep, '/')}') WHERE symbol = '{symbol}'").fetchone()
            if res and res[0] > 0:
                status["volatility"] = True
        except Exception as e:
            print(f"Error checking volatility status: {e}")
            
    # 4. Options
    opt_path = os.path.join(LAKE_ROOT, "options", f"{symbol}.parquet")
    if os.path.exists(opt_path):
        status["options"] = True
        
    # 5. Corporate Actions
    corp_path = os.path.join(LAKE_ROOT, "corporate_actions.parquet")
    if os.path.exists(corp_path):
        try:
            db_conn = duckdb.connect(database=':memory:')
            res = db_conn.execute(f"SELECT COUNT(*) FROM parquet_scan('{corp_path.replace(os.sep, '/')}') WHERE symbol = '{symbol}'").fetchone()
            if res and res[0] > 0:
                status["corporate_actions"] = True
        except Exception as e:
            print(f"Error checking corporate actions status: {e}")
            
    # 6. Bloomberg Fundamentals & Volatility
    funds_path = os.path.join(LAKE_ROOT, "bloomberg", "fundamentals.parquet")
    if os.path.exists(funds_path):
        try:
            db_conn = duckdb.connect(database=':memory:')
            res = db_conn.execute(f"SELECT COUNT(*) FROM parquet_scan('{funds_path.replace(os.sep, '/')}') WHERE symbol = '{symbol}'").fetchone()
            if res and res[0] > 0:
                status["bloomberg_fundamentals"] = True
        except Exception as e:
            print(f"Error checking bloomberg fundamentals status: {e}")
            
    vol_bb_path = os.path.join(LAKE_ROOT, "bloomberg", "volatility.parquet")
    if os.path.exists(vol_bb_path):
        try:
            db_conn = duckdb.connect(database=':memory:')
            res = db_conn.execute(f"SELECT COUNT(*) FROM parquet_scan('{vol_bb_path.replace(os.sep, '/')}') WHERE symbol = '{symbol}'").fetchone()
            if res and res[0] > 0:
                status["bloomberg_volatility"] = True
        except Exception as e:
            print(f"Error checking bloomberg volatility status: {e}")
            
    return status

@app.get("/api/export/volatility/{symbol}")
def export_volatility(symbol: str):
    symbol = symbol.upper()
    vol_path = os.path.join(LAKE_ROOT, "volatility", "options_vol.parquet")
    if not os.path.exists(vol_path):
        raise HTTPException(status_code=404, detail="Volatility file not found")
    try:
        db_conn = duckdb.connect(database=':memory:')
        df = db_conn.execute(f"SELECT * FROM parquet_scan('{vol_path.replace(os.sep, '/')}') WHERE symbol = '{symbol}' ORDER BY timestamp ASC").df()
        df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        return df.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/options/{symbol}")
def export_options(symbol: str):
    symbol = symbol.upper()
    opt_path = os.path.join(LAKE_ROOT, "options", f"{symbol}.parquet")
    if not os.path.exists(opt_path):
        raise HTTPException(status_code=404, detail="Options file not found")
    try:
        df = pd.read_parquet(opt_path)
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d')
        df['expiration'] = pd.to_datetime(df['expiration']).dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        return df.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/corporate_actions/{symbol}")
def export_corporate_actions(symbol: str):
    symbol = symbol.upper()
    corp_path = os.path.join(LAKE_ROOT, "corporate_actions.parquet")
    if not os.path.exists(corp_path):
        raise HTTPException(status_code=404, detail="Corporate actions file not found")
    try:
        db_conn = duckdb.connect(database=':memory:')
        df = db_conn.execute(f"SELECT * FROM parquet_scan('{corp_path.replace(os.sep, '/')}') WHERE symbol = '{symbol}' ORDER BY date ASC").df()
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        return df.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/financials/income/{symbol}")
def export_financials_income(symbol: str, start_date: str = None, end_date: str = None):
    symbol = symbol.upper()
    path = os.path.join(LAKE_ROOT, "financials", "quarterly", f"{symbol}.parquet")
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_parquet(path)
        
        # Filter by date range if provided
        if start_date:
            df = df[df['report_date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['report_date'] <= pd.to_datetime(end_date)]
            
        if len(df) == 0:
            return []
            
        df['report_date'] = df['report_date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        cols = ['report_date', 'fiscal_period', 'symbol', 'revenue', 'net_income', 'eps', 'eps_estimate', 'actual_eps', 'eps_surprise']
        existing_cols = [c for c in cols if c in df.columns]
        return df[existing_cols].to_dict(orient='records')
    except Exception as e:
        print(f"Error: {e}")
        return []

@app.get("/api/export/financials/balance/{symbol}")
def export_financials_balance(symbol: str, start_date: str = None, end_date: str = None):
    symbol = symbol.upper()
    path = os.path.join(LAKE_ROOT, "financials", "quarterly", f"{symbol}.parquet")
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_parquet(path)
        
        # Filter by date range if provided
        if start_date:
            df = df[df['report_date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['report_date'] <= pd.to_datetime(end_date)]
            
        if len(df) == 0:
            return []
            
        df['report_date'] = df['report_date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        cols = ['report_date', 'fiscal_period', 'symbol', 'total_assets', 'total_liabilities', 'equity', 'cash', 'total_debt']
        existing_cols = [c for c in cols if c in df.columns]
        return df[existing_cols].to_dict(orient='records')
    except Exception as e:
        print(f"Error: {e}")
        return []

@app.get("/api/export/financials/cashflow/{symbol}")
def export_financials_cashflow(symbol: str, start_date: str = None, end_date: str = None):
    symbol = symbol.upper()
    path = os.path.join(LAKE_ROOT, "financials", "quarterly", f"{symbol}.parquet")
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_parquet(path)
        
        # Filter by date range if provided
        if start_date:
            df = df[df['report_date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['report_date'] <= pd.to_datetime(end_date)]
            
        if len(df) == 0:
            return []
            
        df['report_date'] = df['report_date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        cols = ['report_date', 'fiscal_period', 'symbol', 'net_change_cash', 'operating_cf', 'capex', 'free_cash_flow']
        existing_cols = [c for c in cols if c in df.columns]
        return df[existing_cols].to_dict(orient='records')
    except Exception as e:
        print(f"Error: {e}")
        return []

@app.get("/api/export/bloomberg/volatility/{symbol}")
def export_bloomberg_volatility(symbol: str, start_date: str = None, end_date: str = None):
    symbol = symbol.upper()
    vol_path = os.path.join(LAKE_ROOT, "bloomberg", "volatility.parquet")
    if not os.path.exists(vol_path):
        return []
    try:
        db_conn = duckdb.connect(database=':memory:')
        query = f"SELECT DATE as date, Realized_Vol_30D as realized_vol_30d FROM parquet_scan('{vol_path.replace(os.sep, '/')}') WHERE symbol = '{symbol}'"
        if start_date:
            query += f" AND DATE >= '{start_date}'"
        if end_date:
            query += f" AND DATE <= '{end_date}'"
        query += " ORDER BY DATE ASC"
        df = db_conn.execute(query).df()
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error: {e}")
        return []

@app.get("/api/export/bloomberg/fundamentals/{symbol}")
def export_bloomberg_fundamentals(symbol: str, start_date: str = None, end_date: str = None):
    symbol = symbol.upper()
    funds_path = os.path.join(LAKE_ROOT, "bloomberg", "fundamentals.parquet")
    if not os.path.exists(funds_path):
        return []
    try:
        db_conn = duckdb.connect(database=':memory:')
        query = f"SELECT DATE as date, Implied_Vol as implied_vol, PE_Ratio as pe_ratio, Price_to_Book as price_to_book, Beta_Raw as beta_raw, Sales as sales, Beta_Adj as beta_adj FROM parquet_scan('{funds_path.replace(os.sep, '/')}') WHERE symbol = '{symbol}'"
        if start_date:
            query += f" AND DATE >= '{start_date}'"
        if end_date:
            query += f" AND DATE <= '{end_date}'"
        query += " ORDER BY DATE ASC"
        df = db_conn.execute(query).df()
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        df = df.replace({np.nan: None})
        return df.to_dict(orient='records')
    except Exception as e:
        print(f"Error: {e}")
        return []
@app.get("/api/export/consolidated/{symbol}")
def get_consolidated_export(symbol: str, timeframe: str = "D1", adjusted: bool = True, start_date: str = None, end_date: str = None,
                            include_volatility: bool = True, include_fundamentals: bool = True, include_financials: bool = True):
    symbol = symbol.upper()
    try:
        df_ohlcv = get_ohlcv(symbol, timeframe=timeframe, adjusted=adjusted)
        if len(df_ohlcv) == 0:
            raise HTTPException(status_code=404, detail=f"Aucune donnée OHLCV trouvée pour le symbole {symbol}")
            
        df_ohlcv['date_str'] = pd.to_datetime(df_ohlcv['timestamp']).dt.strftime('%Y-%m-%d')
        # Do not filter df_ohlcv here to allow ffill from historical data before start_date.
            
        metadata = {"longname": "", "sector": "", "industry": "", "marketcap": None}
        conn = get_db_conn()
        try:
            row = conn.execute("SELECT longname, sector, industry, marketcap FROM symbols_metadata WHERE symbol = ?", (symbol,)).fetchone()
            if row:
                metadata = dict(row)
        except Exception as e:
            print(f"Error fetching metadata for consolidated export: {e}")
        finally:
            conn.close()
            
        df_ohlcv['symbol'] = symbol
        df_ohlcv['company_name'] = metadata['longname']
        df_ohlcv['sector'] = metadata['sector']
        df_ohlcv['industry'] = metadata['industry']
        df_ohlcv['market_cap'] = metadata['marketcap']
        
        # Ensure timestamp is datetime for pd.merge_asof
        df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['timestamp'])
        df_res = df_ohlcv.sort_values('timestamp').copy()
        
        # 1. Bloomberg Volatility
        vol_path = os.path.join(LAKE_ROOT, "bloomberg", "volatility.parquet")
        if include_volatility and os.path.exists(vol_path):
            try:
                df_vol = pd.read_parquet(vol_path)
                df_vol = df_vol[df_vol['symbol'] == symbol].copy()
                if len(df_vol) > 0:
                    df_vol['timestamp'] = pd.to_datetime(df_vol['DATE'])
                    df_vol = df_vol.sort_values('timestamp')
                    df_vol = df_vol.rename(columns={'Realized_Vol_30D': 'realized_vol_30d'})
                    df_vol = df_vol[['timestamp', 'symbol', 'realized_vol_30d']]
                    
                    df_vol['realized_vol_30d'] = df_vol['realized_vol_30d'].ffill()
                    
                    df_res = pd.merge_asof(
                        df_res, 
                        df_vol, 
                        on='timestamp', 
                        by='symbol', 
                        direction='backward'
                    )
            except Exception as e:
                print(f"Error merging volatility in consolidated export: {e}")
                
        # 2. Bloomberg Fundamentals
        funds_path = os.path.join(LAKE_ROOT, "bloomberg", "fundamentals.parquet")
        if include_fundamentals and os.path.exists(funds_path):
            try:
                df_funds = pd.read_parquet(funds_path)
                df_funds = df_funds[df_funds['symbol'] == symbol].copy()
                if len(df_funds) > 0:
                    df_funds['timestamp'] = pd.to_datetime(df_funds['DATE'])
                    df_funds = df_funds.sort_values('timestamp')
                    df_funds = df_funds.rename(columns={
                        'Implied_Vol': 'implied_vol',
                        'PE_Ratio': 'pe_ratio',
                        'Price_to_Book': 'price_to_book',
                        'Beta_Raw': 'beta_raw',
                        'Sales': 'sales',
                        'Beta_Adj': 'beta_adj'
                    })
                    
                    fund_cols = ['implied_vol', 'pe_ratio', 'price_to_book', 'beta_raw', 'sales', 'beta_adj']
                    df_funds[fund_cols] = df_funds[fund_cols].ffill()
                    
                    df_funds = df_funds[['timestamp', 'symbol'] + fund_cols]
                    
                    df_res = pd.merge_asof(
                        df_res, 
                        df_funds, 
                        on='timestamp', 
                        by='symbol', 
                        direction='backward'
                    )
            except Exception as e:
                print(f"Error merging fundamentals in consolidated export: {e}")
                
        # 3. Financials quarterly
        fin_path = os.path.join(LAKE_ROOT, "financials", "quarterly", f"{symbol}.parquet")
        if include_financials and os.path.exists(fin_path):
            try:
                df_fin = pd.read_parquet(fin_path)
                if len(df_fin) > 0:
                    df_fin['timestamp'] = pd.to_datetime(df_fin['report_date'])
                    df_fin = df_fin.sort_values('timestamp')
                    
                    fin_cols = ['revenue', 'net_income', 'eps', 'cash', 'free_cash_flow']
                    df_fin[fin_cols] = df_fin[fin_cols].ffill()
                    
                    df_fin = df_fin[['timestamp', 'symbol'] + fin_cols]
                    
                    df_res = pd.merge_asof(
                        df_res, 
                        df_fin, 
                        on='timestamp', 
                        by='symbol', 
                        direction='backward'
                    )
            except Exception as e:
                print(f"Error merging financials in consolidated export: {e}")
                
        # Rename date column and select/format returned fields
        df_res['date'] = df_res['date_str']
        
        cols_to_return = [
            'date', 'symbol', 'company_name', 'sector', 'industry', 'market_cap', 
            'open', 'high', 'low', 'close', 'volume'
        ]
        
        joined_cols = [
            'realized_vol_30d', 'implied_vol', 'pe_ratio', 'price_to_book', 
            'beta_raw', 'sales', 'beta_adj', 'revenue', 'net_income', 'eps', 'cash', 'free_cash_flow'
        ]
        
        for col in joined_cols:
            if col in df_res.columns:
                cols_to_return.append(col)
                
        df_final = df_res[cols_to_return].copy()
        
        # Filter by start_date and end_date AFTER joining and forward-filling
        if start_date:
            df_final = df_final[df_final['date'] >= start_date]
        if end_date:
            df_final = df_final[df_final['date'] <= end_date]
            
        if len(df_final) == 0:
            return []
            
        df_final = df_final.replace({np.nan: None})
        return df_final.to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ingest/progress")
def get_ingest_progress():
    progress_file = PROGRESS_FILE
    if not os.path.exists(progress_file):
        return {"active": False, "percent": 0, "status": "Aucune tâche en cours", "step_name": ""}
    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return {"active": False, "percent": 0, "status": f"Erreur de lecture: {str(e)}", "step_name": ""}

@app.post("/api/ingest/bloomberg")
def trigger_ingest_bloomberg():
    """Start Bloomberg ingestion script in background."""
    try:
        subprocess.Popen([sys.executable, "-m", "tvdata.ingest.ingest_bloomberg"])
        return {"status": "started", "message": "Importation des données Bloomberg démarrée en arrière-plan."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def index(response: Response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    html_content = """
    <!DOCTYPE html>
    <html lang="fr" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>OpenTick — Data Explorer</title>
        <!-- Tailwind CSS CDN -->
        <script src="https://cdn.tailwindcss.com"></script>
        <!-- Inter Font -->
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <!-- TradingView Lightweight Charts CDN -->
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <!-- JSZip CDN -->
        <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
        <style>
            body {
                font-family: 'Inter', sans-serif;
            }
            /* Glassmorphism scrollbar */
            ::-webkit-scrollbar {
                width: 6px;
                height: 6px;
            }
            ::-webkit-scrollbar-track {
                background: #0f172a;
            }
            ::-webkit-scrollbar-thumb {
                background: #334155;
                border-radius: 4px;
            }
            ::-webkit-scrollbar-thumb:hover {
                background: #475569;
            }
        </style>
        <script>
            tailwind.config = {
                darkMode: 'class',
                theme: {
                    extend: {
                        colors: {
                            slate: {
                                950: '#020617',
                                900: '#0f172a',
                                800: '#1e293b',
                            }
                        }
                    }
                }
            }
        </script>
    </head>
    <body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased">
        <!-- Top Header -->
        <header class="border-b border-slate-800 bg-slate-950/70 backdrop-blur-lg sticky top-0 z-50 px-6 py-4 flex items-center justify-between shadow-md shadow-slate-950/50">
            <div class="flex items-center space-x-3">
                <div class="w-10 h-10 rounded-xl bg-slate-950 border border-emerald-500/40 flex items-center justify-center shadow-lg shadow-emerald-500/20 transition-all duration-500 hover:border-emerald-400 hover:shadow-emerald-500/30">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" class="transform hover:scale-110 transition-transform duration-300">
                        <!-- Candlestick left -->
                        <rect x="5" y="9" width="3" height="8" rx="0.5" fill="#10b981"/>
                        <line x1="6.5" y1="6" x2="6.5" y2="9" stroke="#10b981" stroke-width="1.5" stroke-linecap="round"/>
                        <line x1="6.5" y1="17" x2="6.5" y2="20" stroke="#10b981" stroke-width="1.5" stroke-linecap="round"/>
                        <!-- Candlestick right -->
                        <rect x="11" y="6" width="3" height="9" rx="0.5" fill="#10b981"/>
                        <line x1="12.5" y1="3" x2="12.5" y2="6" stroke="#10b981" stroke-width="1.5" stroke-linecap="round"/>
                        <line x1="12.5" y1="15" x2="12.5" y2="18" stroke="#10b981" stroke-width="1.5" stroke-linecap="round"/>
                        <!-- Upward arrow -->
                        <polyline points="4,18 9,13 14,15 20,7" stroke="#34d399" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                        <polyline points="17,6 20,7 19,10" stroke="#34d399" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
                    </svg>
                </div>
                <div>
                    <h1 class="text-xl font-extrabold tracking-tight text-white"><span class="text-white">Open</span><span class="text-emerald-400 drop-shadow-[0_0_8px_rgba(16,185,129,0.3)]">Tick</span></h1>
                    <p class="text-[10px] uppercase font-semibold tracking-wider text-slate-500">Financial Data Lake</p>
                </div>
            </div>
            <div class="flex items-center space-x-4">
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-inner">
                    <span class="w-2 h-2 mr-2 rounded-full bg-emerald-400 animate-ping"></span>
                    Data Lake Connected
                </span>
                <span class="text-xs font-mono text-slate-500 bg-slate-900 border border-slate-800/80 px-2.5 py-1 rounded-lg">localhost:8001</span>
            </div>
        </header>

        <!-- Main Body -->
        <main class="flex-1 flex overflow-hidden">

            <!-- Left Panel / Controls -->
            <section class="w-80 border-r border-slate-800/80 bg-slate-950/45 backdrop-blur-md flex flex-col p-6 space-y-6 overflow-y-auto">
                <div>
                    <h2 class="text-[11px] font-bold uppercase tracking-widest text-slate-500 mb-4">Configuration</h2>
                    
                    <div class="space-y-4">
                        <!-- Asset Class -->
                        <div>
                            <label class="block text-[11px] font-medium text-slate-400 mb-1.5">Asset Class</label>
                            <select id="asset-class" onchange="onAssetClassChange()" class="w-full bg-slate-900/60 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20 transition-all duration-200">
                                <option value="stocks">Stocks (US Equities)</option>
                                <option value="forex">Forex (Currencies)</option>
                                <option value="crypto">Crypto (Cryptocurrencies)</option>
                                <option value="macro">Macro & FRED (Economy)</option>
                            </select>
                        </div>

                        <!-- Symbol -->
                        <div class="relative">
                            <label class="block text-[11px] font-medium text-slate-400 mb-1.5">Symbol</label>
                            <div class="relative flex items-center">
                                <div id="active-symbol-logo-container" class="absolute left-2.5 flex items-center justify-center hidden"></div>
                                <input type="text" id="symbol-search" placeholder="Search symbol..." onclick="toggleSymbolDropdown(true)" oninput="filterSymbols()" class="w-full bg-slate-900/60 border border-slate-800 rounded-lg pl-3 pr-8 py-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20 transition-all duration-200 cursor-pointer">
                                <div class="absolute inset-y-0 right-0 flex items-center pr-2.5 pointer-events-none text-slate-500">
                                    <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                                    </svg>
                                </div>
                            </div>
                            <div id="symbol-dropdown" class="absolute z-50 left-0 right-0 mt-1.5 max-h-64 overflow-y-auto bg-slate-900/95 border border-slate-800 rounded-lg shadow-2xl backdrop-blur-lg hidden">
                                <!-- Options loaded dynamically -->
                            </div>
                            <input type="hidden" id="symbol" value="">
                        </div>

                        <!-- Timeframe -->
                        <div id="timeframe-container">
                            <label class="block text-[11px] font-medium text-slate-400 mb-1.5">Timeframe</label>
                            <select id="timeframe" onchange="loadChartData()" class="w-full bg-slate-900/60 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20 transition-all duration-200">
                                <!-- Loaded dynamically based on catalog -->
                            </select>
                        </div>

                        <!-- Price adjustments -->
                        <div class="flex items-center space-x-2.5 pt-1" id="adjustment-container">
                            <input type="checkbox" id="adjusted-prices" onchange="loadChartData()" checked class="rounded border-slate-800 text-emerald-500 bg-slate-900 focus:ring-emerald-500/30 focus:ring-offset-slate-950">
                            <label for="adjusted-prices" class="text-xs text-slate-400 select-none cursor-pointer hover:text-slate-300">Apply price adjustments (splits/div)</label>
                        </div>
                    </div>
                </div>

                <!-- Database Statistics -->
                <div class="border-t border-slate-900 pt-6 space-y-3 text-xs">
                    <h2 class="text-[11px] font-bold uppercase tracking-widest text-slate-500">S&P 500 Statistics</h2>
                    <div class="bg-slate-950/60 p-4 rounded-xl border border-slate-900 space-y-2.5 shadow-md shadow-slate-950/20">
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">Total Index Tickers</span>
                            <span id="stats-total" class="font-bold text-slate-200 font-mono">-</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">Locally Imported</span>
                            <span id="stats-imported" class="font-bold text-emerald-400 font-mono">-</span>
                        </div>
                        <div class="flex justify-between items-center">
                            <span class="text-slate-400">Not Imported</span>
                            <span id="stats-missing" class="font-bold text-rose-400 font-mono">-</span>
                        </div>
                        <div class="flex justify-between items-center border-t border-slate-800/50 pt-2 text-[10px]">
                            <span class="text-slate-500">Last Sync</span>
                            <span id="sync-status-time" class="text-slate-400 font-semibold font-mono">Waiting...</span>
                        </div>
                        <div class="pt-2">
                            <button id="update-all-btn" onclick="triggerUpdateAll()" class="w-full bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold py-2 px-3 rounded-lg transition-all duration-300 shadow-md shadow-emerald-500/10 hover:shadow-emerald-500/20 hover:scale-[1.02] active:scale-[0.98] text-xs flex items-center justify-center space-x-1.5">
                                <span>Refresh Database (EOD)</span>
                            </button>
                        </div>
                        
                        <!-- Progress Tracking Section -->
                        <div id="ingest-progress-container" class="border-t border-slate-800/50 pt-2.5 mt-2 hidden space-y-2">
                            <div class="flex justify-between text-[10px]">
                                <span id="progress-step-name" class="font-semibold text-slate-400">Refreshing</span>
                                <span id="progress-percent" class="font-bold text-emerald-400">0%</span>
                            </div>
                            <div class="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                                <div id="progress-bar-fill" class="bg-gradient-to-r from-emerald-500 to-teal-400 h-1.5 rounded-full transition-all duration-300 w-0"></div>
                            </div>
                            <div id="progress-status" class="text-[9px] text-slate-500 truncate">Verifying AAPL...</div>
                        </div>
                    </div>
                </div>

                <!-- Live Ingestion Form -->
                <div class="border-t border-slate-900 pt-6 space-y-4 text-xs">
                    <h2 class="text-[11px] font-bold uppercase tracking-widest text-slate-500">Import / Update</h2>
                    <div class="bg-slate-950/60 p-4 rounded-xl border border-slate-900 space-y-3.5 shadow-md shadow-slate-950/20">
                        <div>
                            <label class="block text-[10px] font-medium text-slate-400 mb-1">API Source</label>
                            <select id="ingest-source" class="w-full bg-slate-900/60 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-300 focus:outline-none focus:border-emerald-500/50 transition-all duration-200">
                                <option value="alpaca">Alpaca Markets (M15+)</option>
                                <option value="yfinance">Yahoo Finance</option>
                                <option value="fred">FRED API (Macro)</option>
                            </select>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <label class="block text-[10px] font-medium text-slate-400 mb-1">Start Date</label>
                                <input type="date" id="ingest-start" class="w-full bg-slate-900/60 border border-slate-800 rounded-lg px-2 py-1 text-slate-300 focus:outline-none focus:border-emerald-500/50 transition-all duration-200">
                            </div>
                            <div>
                                <label class="block text-[10px] font-medium text-slate-400 mb-1">End Date</label>
                                <input type="date" id="ingest-end" class="w-full bg-slate-900/60 border border-slate-800 rounded-lg px-2 py-1 text-slate-300 focus:outline-none focus:border-emerald-500/50 transition-all duration-200">
                            </div>
                        </div>
                        <button id="ingest-btn" onclick="triggerIngestion()" class="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold py-2 rounded-lg transition-all duration-300 shadow-md shadow-blue-500/10 hover:shadow-blue-500/20 hover:scale-[1.02] active:scale-[0.98]">
                            <span id="ingest-btn-text">Start Ingestion</span>
                        </button>
                        <div id="ingest-status" class="text-[10px] text-center font-medium mt-1 hidden"></div>
                    </div>
                </div>

                <!-- Metadata details -->
                <div id="metadata-panel" class="border-t border-slate-900 pt-6 flex-1 flex flex-col space-y-4 text-xs">
                    <h2 class="text-[11px] font-bold uppercase tracking-widest text-slate-500">Metadata</h2>
                    <div class="bg-slate-950/60 p-4 rounded-xl border border-slate-900 space-y-3 shadow-md shadow-slate-950/20">
                        <div>
                            <div class="text-slate-500 text-[10px]">Long Name</div>
                            <div id="meta-longname" class="font-semibold text-slate-200">-</div>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <div class="text-slate-500 text-[10px]">Sector</div>
                                <div id="meta-sector" class="font-semibold text-slate-200">-</div>
                            </div>
                            <div>
                                <div class="text-slate-500 text-[10px]">Industry</div>
                                <div id="meta-industry" class="font-semibold text-slate-200">-</div>
                            </div>
                        </div>
                        <div class="grid grid-cols-2 gap-2">
                            <div>
                                <div class="text-slate-500 text-[10px]">Market Cap</div>
                                <div id="meta-marketcap" class="font-semibold text-slate-200">-</div>
                            </div>
                            <div>
                                <div class="text-slate-500 text-[10px]">Index Weight</div>
                                <div id="meta-weight" class="font-semibold text-slate-200">-</div>
                            </div>
                        </div>
                        <div>
                            <div class="text-slate-500 text-[10px]">Exchange</div>
                            <div id="meta-exchange" class="font-semibold text-slate-200">-</div>
                        </div>
                    </div>
                    <div class="flex-1 flex flex-col overflow-hidden">
                        <div class="text-slate-500 text-[10px] mb-1.5 font-medium">Business Summary</div>
                        <div id="meta-summary" class="bg-slate-950/60 p-4 rounded-xl border border-slate-900 overflow-y-auto text-slate-400 leading-relaxed max-h-48 shadow-inner">
                            No business summary available.
                        </div>
                    </div>
                </div>
            </section>

            <!-- Right Panel / Main Area -->
            <section class="flex-1 flex flex-col bg-slate-950 overflow-hidden">
                <!-- Top chart panel -->
                <div class="h-[460px] p-6 relative flex flex-col min-h-0 bg-gradient-to-b from-slate-900/20 to-slate-950">
                    <div id="chart-legend-wrapper" class="absolute top-8 left-8 z-10 bg-slate-950/85 border border-slate-800/80 px-4 py-2 rounded-xl backdrop-blur-lg flex items-center space-x-4 shadow-2xl shadow-slate-950/60 pointer-events-none text-xs select-none">
                        <div id="chart-symbol-logo" class="flex items-center justify-center"></div>
                        <div id="chart-symbol-label" class="text-sm font-bold text-white">-</div>
                        <div id="chart-price-label" class="text-sm font-semibold text-emerald-400 font-mono">-</div>
                        <div id="chart-ohlcv-legend" class="text-[11px] text-slate-400 font-mono hidden space-x-3">
                            <!-- Loaded dynamically on hover -->
                        </div>
                    </div>
                    <div class="absolute top-8 right-8 z-10 flex space-x-2">
                        <button onclick="downloadCSV()" class="bg-slate-900/90 hover:bg-slate-800 border border-slate-800 px-4 py-2 rounded-xl text-xs font-semibold text-emerald-400 hover:text-emerald-300 flex items-center space-x-2 transition-all duration-300 hover:scale-[1.02] shadow-xl shadow-slate-950/50">
                            <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                            <span>Export to CSV</span>
                        </button>
                    </div>
                    <div id="chart-container" class="w-full flex-1 rounded-2xl overflow-hidden border border-slate-800/80 bg-slate-950/80 shadow-2xl shadow-slate-950/40">
                        <!-- Chart renders here -->
                    </div>
                </div>

                <!-- Bottom Tabbed Area -->
                <div class="flex-1 border-t border-slate-900 bg-slate-950/30 flex flex-col overflow-hidden">
                    <div class="border-b border-slate-900 px-6 py-2 flex items-center justify-between bg-slate-950/50">
                        <div class="flex items-center space-x-6">
                            <button id="tab-financials-btn" onclick="switchTab('financials')" class="text-sm font-semibold border-b-2 border-emerald-500 text-emerald-400 pb-3 pt-3 focus:outline-none transition-colors duration-200">Financial Data</button>
                            <button id="tab-table-btn" onclick="switchTab('table')" class="text-sm font-semibold text-slate-400 hover:text-slate-200 pb-3 pt-3 focus:outline-none transition-colors duration-200">OHLCV Data (Table)</button>
                            <button id="tab-catalog-btn" onclick="switchTab('catalog')" class="text-sm font-semibold text-slate-400 hover:text-slate-200 pb-3 pt-3 focus:outline-none transition-colors duration-200">Dataset Catalog Info</button>
                            <button id="tab-sql-btn" onclick="switchTab('sql')" class="text-sm font-semibold text-slate-400 hover:text-slate-200 pb-3 pt-3 focus:outline-none transition-colors duration-200">SQL Console (DuckDB)</button>
                        </div>
                        <div id="table-row-count" class="text-xs text-slate-500 font-mono"></div>
                    </div>
                    
                    <div class="flex-1 p-6 overflow-auto">
                        <!-- Financials Table Tab -->
                        <div id="tab-financials" class="block w-full">
                            <div class="overflow-x-auto">
                                <table class="w-full text-left border-collapse text-xs">
                                    <thead>
                                        <tr class="border-b border-slate-800 text-slate-400 font-semibold">
                                            <th class="py-2 px-3">Report Date</th>
                                            <th class="py-2 px-3">Period</th>
                                            <th class="py-2 px-3 text-right">Revenue ($)</th>
                                            <th class="py-2 px-3 text-right">Net Income ($)</th>
                                            <th class="py-2 px-3 text-right">EPS ($)</th>
                                            <th class="py-2 px-3 text-right">Cash ($)</th>
                                            <th class="py-2 px-3 text-right">Op. Cash Flow ($)</th>
                                            <th class="py-2 px-3 text-right">Free Cash Flow ($)</th>
                                        </tr>
                                    </thead>
                                    <tbody id="financials-tbody" class="divide-y divide-slate-800/40 text-slate-300">
                                        <!-- Loaded dynamically -->
                                    </tbody>
                                </table>
                                <div id="financials-empty" class="text-center py-8 text-slate-500 text-sm hidden">
                                    No financial data available for this symbol.
                                </div>
                            </div>
                        </div>

                        <!-- Raw OHLCV Table Tab -->
                        <div id="tab-table" class="hidden w-full">
                            <div class="overflow-x-auto">
                                <table class="w-full text-left border-collapse text-xs">
                                    <thead>
                                        <tr class="border-b border-slate-800 text-slate-400 font-semibold">
                                            <th class="py-2 px-3">Date / Timestamp (UTC)</th>
                                            <th class="py-2 px-3 text-right">Open</th>
                                            <th class="py-2 px-3 text-right">High</th>
                                            <th class="py-2 px-3 text-right">Low</th>
                                            <th class="py-2 px-3 text-right">Close</th>
                                            <th class="py-2 px-3 text-right">Volume</th>
                                        </tr>
                                    </thead>
                                    <tbody id="table-tbody" class="divide-y divide-slate-800/40 text-slate-300">
                                        <!-- Loaded dynamically -->
                                    </tbody>
                                </table>
                                <div id="table-empty" class="text-center py-8 text-slate-500 text-sm">
                                    No market data loaded in this tab.
                                </div>
                            </div>
                        </div>

                        <!-- Catalog Details Tab -->
                        <div id="tab-catalog" class="hidden">
                            <div class="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
                                <div>
                                    <div class="text-slate-500 text-xs">Available Period</div>
                                    <div id="cat-range" class="font-semibold text-slate-200 mt-1">-</div>
                                </div>
                                <div>
                                    <div class="text-slate-500 text-xs">Number of Rows</div>
                                    <div id="cat-rows" class="font-semibold text-slate-200 mt-1">-</div>
                                </div>
                                <div>
                                    <div class="text-slate-500 text-xs">Nulls Rate (Price)</div>
                                    <div id="cat-nulls" class="font-semibold text-slate-200 mt-1">-</div>
                                </div>
                                <div>
                                    <div class="text-slate-500 text-xs">Quality Score</div>
                                    <div id="cat-quality" class="font-semibold mt-1">-</div>
                                </div>
                            </div>
                        </div>

                        <!-- SQL Console Tab -->
                        <div id="tab-sql" class="hidden w-full flex flex-col space-y-4 h-full">
                            <div class="flex space-x-4 items-stretch">
                                <div class="flex-1">
                                    <textarea id="sql-query-input" rows="3" class="w-full bg-slate-950 text-slate-200 border border-slate-800 rounded-lg p-3 font-mono text-xs focus:outline-none focus:border-blue-500" placeholder="Enter your SQL query here...">SELECT timestamp, open, high, low, close, volume FROM ohlcv WHERE symbol = 'AAPL' AND timeframe = 'D1' ORDER BY timestamp DESC LIMIT 5;</textarea>
                                </div>
                                <div class="flex flex-col justify-between">
                                    <button onclick="runSqlQuery()" class="bg-blue-600 hover:bg-blue-500 text-white font-semibold px-4 py-2 rounded-lg text-xs transition h-10 flex items-center justify-center space-x-1 shadow-md shadow-blue-500/20">
                                        <span>Execute SQL</span>
                                    </button>
                                    <div class="text-[10px] text-slate-500 max-w-[150px] leading-tight">
                                        Available tables: <br>
                                        <code class="text-blue-400 font-mono">ohlcv</code> (OHLCV data)<br>
                                        <code class="text-blue-400 font-mono">parquet_scan('path')</code>
                                    </div>
                                </div>
                            </div>
                            
                            <!-- Exemples de requêtes SQL rapides -->
                            <div class="flex flex-wrap gap-2 text-[10px] text-slate-400 pb-2">
                                <span class="self-center font-medium mr-1">Examples:</span>
                                <button onclick="prefillSQL('SELECT timestamp, open, high, low, close, volume FROM ohlcv WHERE symbol = \\'AAPL\\' AND timeframe = \\'D1\\' ORDER BY timestamp DESC LIMIT 10;')" class="bg-slate-850 hover:bg-slate-800 text-slate-300 px-2.5 py-1 rounded border border-slate-800 hover:border-slate-700 transition">OHLCV AAPL Daily</button>
                                <button onclick="prefillSQL('SELECT symbol, sector, industry, marketcap FROM symbols_metadata WHERE sector = \\'Technology\\' ORDER BY marketcap DESC LIMIT 5;')" class="bg-slate-850 hover:bg-slate-800 text-slate-300 px-2.5 py-1 rounded border border-slate-800 hover:border-slate-700 transition">Top Tech by Market Cap</button>
                                <button onclick="prefillSQL('SELECT symbol, DATE as date, Realized_Vol_30D as volatility FROM parquet_scan(\\'c:/Users/DELL/Desktop/Tradovera/lake/bloomberg/volatility.parquet\\') WHERE symbol = \\'AAPL\\' ORDER BY DATE DESC LIMIT 5;')" class="bg-slate-855 hover:bg-slate-800 text-amber-400 px-2.5 py-1 rounded border border-amber-900/30 hover:border-amber-700/50 transition">Bloomberg Volatility AAPL</button>
                                <button onclick="prefillSQL('SELECT symbol, DATE as date, PE_Ratio as pe, Price_to_Book as pb FROM parquet_scan(\\'c:/Users/DELL/Desktop/Tradovera/lake/bloomberg/fundamentals.parquet\\') WHERE symbol = \\'AAPL\\' ORDER BY DATE DESC LIMIT 5;')" class="bg-slate-855 hover:bg-slate-800 text-amber-400 px-2.5 py-1 rounded border border-amber-900/30 hover:border-amber-700/50 transition">Bloomberg Multiples AAPL</button>
                            </div>
                            
                            <div class="flex-1 overflow-auto border border-slate-800 rounded-lg bg-slate-950 min-h-0 relative">
                                <div id="sql-empty-state" class="absolute inset-0 flex items-center justify-center text-slate-500 text-xs">
                                    Click Execute to run SQL query on the data lake.
                                </div>
                                <div id="sql-loading-state" class="absolute inset-0 flex items-center justify-center text-slate-400 text-xs hidden space-x-2">
                                    <svg class="animate-spin h-4 w-4 text-blue-500" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                    <span>Running query on DuckDB...</span>
                                </div>
                                <div id="sql-result-container" class="hidden p-3 w-full">
                                    <div class="flex justify-between items-center text-[10px] text-slate-500 mb-2 border-b border-slate-900 pb-2">
                                        <span id="sql-result-info"></span>
                                        <button onclick="downloadSQLResultCSV()" class="text-blue-400 hover:text-blue-300 font-semibold flex items-center space-x-1">
                                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                                            <span>Export Result (CSV)</span>
                                        </button>
                                    </div>
                                    <div class="overflow-x-auto w-full">
                                        <table class="w-full text-left border-collapse text-[10px]" id="sql-table">
                                            <thead id="sql-table-thead" class="text-slate-400 border-b border-slate-800 font-semibold">
                                                <!-- Loaded dynamically -->
                                            </thead>
                                            <tbody id="sql-table-tbody" class="divide-y divide-slate-900/60 text-slate-300">
                                                <!-- Loaded dynamically -->
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    </div>
                </div>
            </section>

        </main>

        <!-- Export Modal -->
        <div id="export-modal" class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 backdrop-blur-md hidden transition duration-300">
            <div class="bg-[#080c16] border border-slate-800/80 rounded-2xl w-full max-w-xl p-6 shadow-2xl relative">
                <!-- Close Button -->
                <button onclick="closeExportModal()" class="absolute top-5 right-5 text-slate-400 hover:text-white transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
                
                <h3 class="text-lg font-bold text-white mb-0.5">Export Configuration</h3>
                <p class="text-xs text-slate-400 mb-5">Exporting data for <span id="export-symbol-title" class="font-extrabold text-blue-400">-</span></p>
                
                <!-- Date range selection -->
                <div class="bg-[#050810]/60 p-4 rounded-xl border border-slate-900 mb-4 space-y-3 shadow-inner">
                    <div class="text-[10px] font-bold uppercase tracking-wider text-slate-500">Export Period</div>
                    <div class="grid grid-cols-2 gap-4 text-xs">
                        <div>
                            <label class="block text-slate-400 mb-1.5 font-medium">Start Date</label>
                            <input type="date" id="export-start-date" class="w-full bg-[#070b15] border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 transition duration-150">
                        </div>
                        <div>
                            <label class="block text-slate-400 mb-1.5 font-medium">End Date</label>
                            <input type="date" id="export-end-date" class="w-full bg-[#070b15] border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-blue-500 transition duration-150">
                        </div>
                    </div>
                </div>

                <!-- Export Format Selection -->
                <div class="bg-[#050810]/60 p-4 rounded-xl border border-slate-900 mb-4 space-y-3 shadow-inner">
                    <div class="text-[10px] font-bold uppercase tracking-wider text-slate-500">Export Format</div>
                    <div class="flex items-center space-x-6 text-xs pl-1">
                        <label class="flex items-center space-x-2 text-slate-300 cursor-pointer select-none">
                            <input type="radio" name="export-format" value="consolidated" checked class="w-4 h-4 border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                            <span class="font-medium">Single Consolidated File (CSV)</span>
                        </label>
                        <label class="flex items-center space-x-2 text-slate-300 cursor-pointer select-none">
                            <input type="radio" name="export-format" value="separate" class="w-4 h-4 border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                            <span class="font-medium">Separate CSV Files (ZIP)</span>
                        </label>
                    </div>
                </div>

                <!-- Checkboxes Container -->
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-6 max-h-[280px] overflow-y-auto pr-1 text-xs" id="export-checkboxes-container">
                    <!-- Loaded dynamically -->
                </div>
                
                <div class="flex space-x-3 pt-4 border-t border-slate-900">
                    <button onclick="closeExportModal()" class="flex-1 bg-slate-900/60 hover:bg-slate-800/80 border border-slate-800 text-slate-300 font-bold py-2.5 rounded-lg text-xs transition duration-150 active:scale-[0.98]">
                        Cancel
                    </button>
                    <button id="modal-export-btn" onclick="executeExport()" class="flex-1 bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-lg text-xs transition duration-150 flex items-center justify-center space-x-1.5 active:scale-[0.98] shadow-lg shadow-blue-500/25">
                        <span id="modal-export-btn-text">Export</span>
                    </button>
                </div>
            </div>
        </div>

        <script>
            let allSymbols = [];
            let activeTab = 'financials';
            let chart = null;
            let candleSeries = null;
            let volumeSeries = null;
            let areaSeries = null;
            let currentData = []; // Holds currently loaded series data

            // Dynamic Brand & Crypto Logo definitions (similar to TradingView)
            function getSymbolLogoHtml(symbol, name = '', assetClass = 'stocks') {
                symbol = symbol.toUpperCase().trim();
                const stockDomains = {
                    'AAPL': 'apple.com',
                    'MSFT': 'microsoft.com',
                    'GOOGL': 'google.com',
                    'GOOG': 'google.com',
                    'NVDA': 'nvidia.com',
                    'AMZN': 'amazon.com',
                    'TSLA': 'tesla.com',
                    'META': 'meta.com',
                    'NFLX': 'netflix.com',
                    'AMD': 'amd.com',
                    'INTC': 'intel.com',
                    'QCOM': 'qualcomm.com',
                    'PYPL': 'paypal.com',
                    'COIN': 'coinbase.com',
                    'DIS': 'disney.com',
                    'NKE': 'nike.com',
                    'SBUX': 'starbucks.com'
                };
                
                const cryptoLogos = {
                    'BTC': 'https://assets.coingecko.com/coins/images/1/small/bitcoin.png',
                    'ETH': 'https://assets.coingecko.com/coins/images/279/small/ethereum.png',
                    'BNB': 'https://assets.coingecko.com/coins/images/825/small/binance-coin-logo.png',
                    'SOL': 'https://assets.coingecko.com/coins/images/4128/small/solana.png',
                    'XRP': 'https://assets.coingecko.com/coins/images/44/small/xrp-symbol-white-128.png',
                    'ADA': 'https://assets.coingecko.com/coins/images/975/small/cardano.png'
                };
                
                const forexFlags = {
                    'EUR': 'https://flagcdn.com/w40/eu.png',
                    'USD': 'https://flagcdn.com/w40/us.png',
                    'GBP': 'https://flagcdn.com/w40/gb.png',
                    'JPY': 'https://flagcdn.com/w40/jp.png',
                    'CHF': 'https://flagcdn.com/w40/ch.png',
                    'CAD': 'https://flagcdn.com/w40/ca.png',
                    'AUD': 'https://flagcdn.com/w40/au.png'
                };

                if (assetClass === 'crypto' && cryptoLogos[symbol]) {
                    return `<img src="${cryptoLogos[symbol]}" class="w-5 h-5 rounded-full object-cover bg-slate-800 border border-slate-700/50" alt="${symbol}">`;
                }

                if (assetClass === 'forex') {
                    const baseCurr = symbol.substring(0, 3);
                    if (forexFlags[baseCurr]) {
                        return `<img src="${forexFlags[baseCurr]}" class="w-5 h-3.5 rounded object-cover border border-slate-700/50 shadow-inner" alt="${symbol}">`;
                    }
                }

                if (assetClass === 'stocks') {
                    const domain = stockDomains[symbol];
                    if (domain) {
                        return `<img src="https://logo.clearbit.com/${domain}" class="w-5 h-5 rounded-full object-contain bg-white border border-slate-700/30 p-0.5" onerror="this.outerHTML=getLetterAvatarHtml('${symbol}')" alt="${symbol}">`;
                    }
                }

                return getLetterAvatarHtml(symbol);
            }

            function getLetterAvatarHtml(symbol) {
                let hash = 0;
                for (let i = 0; i < symbol.length; i++) {
                    hash = symbol.charCodeAt(i) + ((hash << 5) - hash);
                }
                const hue = Math.abs(hash % 360);
                const bg = `linear-gradient(135deg, hsl(${hue}, 85%, 35%), hsl(${(hue + 60) % 360}, 85%, 20%))`;
                const initials = symbol.substring(0, 2);
                return `<div class="w-5 h-5 rounded-full flex items-center justify-center text-[8px] font-bold text-white tracking-wider border border-white/10 shadow-lg" style="background: ${bg};">${initials}</div>`;
            }

            // Load symbol dataset metadata on startup
            window.addEventListener('DOMContentLoaded', async () => {
                console.log("DOMContentLoaded: Starting client-side initialization...");
                const today = new Date();
                const twoYearsAgo = new Date();
                twoYearsAgo.setFullYear(today.getFullYear() - 2);
                
                document.getElementById('ingest-start').value = twoYearsAgo.toISOString().substring(0, 10);
                document.getElementById('ingest-end').value = today.toISOString().substring(0, 10);

                try {
                    console.log("DOMContentLoaded: Initializing chart...");
                    initChart();
                } catch (e) {
                    console.error("DOMContentLoaded: Failed to initialize chart:", e);
                }

                try {
                    console.log("DOMContentLoaded: Fetching symbols list...");
                    await refreshSymbolsList();
                } catch (e) {
                    console.error("DOMContentLoaded: Failed to load symbols:", e);
                }

                try {
                    console.log("DOMContentLoaded: Fetching stats...");
                    await loadStats();
                } catch (e) {
                    console.error("DOMContentLoaded: Failed to load stats:", e);
                }

                // Start polling in case an ingestion script is already running in background
                pollIngestProgress();
            });

            async function refreshSymbolsList() {
                const response = await fetch('/api/symbols');
                allSymbols = await response.json();
                console.log("refreshSymbolsList: Symbols loaded from catalog. Count:", allSymbols.length);
                onAssetClassChange();
            }

            async function loadStats() {
                try {
                    const response = await fetch('/api/stats');
                    const stats = await response.json();
                    document.getElementById('stats-total').innerText = stats.total;
                    document.getElementById('stats-imported').innerText = stats.imported;
                    document.getElementById('stats-missing').innerText = stats.missing;
                } catch (e) {
                    console.error("Error loading stats:", e);
                }
            }

            let isPollingProgress = false;

            async function pollIngestProgress() {
                try {
                    const response = await fetch('/api/ingest/progress');
                    const progress = await response.json();
                    
                    const container = document.getElementById('ingest-progress-container');
                    const barFill = document.getElementById('progress-bar-fill');
                    const percentText = document.getElementById('progress-percent');
                    const stepText = document.getElementById('progress-step-name');
                    const statusText = document.getElementById('progress-status');
                    
                    const btnBloomberg = document.getElementById('import-bloomberg-btn');
                    const btnMissing = document.getElementById('import-missing-btn');
                    const btnUpdateAll = document.getElementById('update-all-btn');
                    
                    const syncTimeEl = document.getElementById('sync-status-time');
                    if (progress.active) {
                        isPollingProgress = true;
                        container.classList.remove('hidden');
                        stepText.innerText = progress.step_name;
                        percentText.innerText = progress.percent + '%';
                        barFill.style.width = progress.percent + '%';
                        statusText.innerText = progress.status;
                        
                        if (syncTimeEl) {
                            syncTimeEl.innerText = "Sync en cours...";
                            syncTimeEl.className = "text-blue-400 animate-pulse font-medium";
                        }
                        
                        if (btnBloomberg) btnBloomberg.disabled = true;
                        if (btnMissing) btnMissing.disabled = true;
                        if (btnUpdateAll) btnUpdateAll.disabled = true;
                        
                        setTimeout(pollIngestProgress, 2000);
                    } else {
                        if (syncTimeEl) {
                            if (progress.status && progress.status.includes("terminée")) {
                                syncTimeEl.innerText = "À jour (Terminé)";
                                syncTimeEl.className = "text-emerald-400 font-medium";
                            } else {
                                syncTimeEl.innerText = "En veille";
                                syncTimeEl.className = "text-slate-400 font-medium";
                            }
                        }
                        
                        if (isPollingProgress) {
                            // Just finished
                            percentText.innerText = '100%';
                            barFill.style.width = '100%';
                            statusText.innerText = progress.status || 'Opération terminée !';
                            
                            await loadStats();
                            await refreshSymbolsList();
                            
                            setTimeout(() => {
                                container.classList.add('hidden');
                                if (btnBloomberg) { btnBloomberg.disabled = false; btnBloomberg.innerText = "Importer Base Bloomberg"; }
                                if (btnMissing) { btnMissing.disabled = false; btnMissing.innerText = "Importer les manquants"; }
                                if (btnUpdateAll) { btnUpdateAll.disabled = false; btnUpdateAll.innerText = "Actualiser tout (2022-2026)"; }
                                isPollingProgress = false;
                            }, 5000);
                        } else {
                            container.classList.add('hidden');
                            if (btnBloomberg) btnBloomberg.disabled = false;
                            if (btnMissing) btnMissing.disabled = false;
                            if (btnUpdateAll) btnUpdateAll.disabled = false;
                        }
                    }
                } catch (e) {
                    console.error("Error polling progress:", e);
                    setTimeout(pollIngestProgress, 5000);
                }
            }

            async function triggerImportBloomberg() {
                const btn = document.getElementById('import-bloomberg-btn');
                btn.disabled = true;
                btn.innerText = "Lancement...";
                try {
                    const response = await fetch('/api/ingest/bloomberg', { method: 'POST' });
                    const res = await response.json();
                    alert(res.message);
                    pollIngestProgress();
                } catch(e) {
                    alert("Erreur lors du lancement : " + e.message);
                    btn.disabled = false;
                    btn.innerText = "Importer Base Bloomberg";
                }
            }

            async function triggerImportMissing() {
                const btn = document.getElementById('import-missing-btn');
                btn.disabled = true;
                btn.innerText = "Lancement...";
                try {
                    const response = await fetch('/api/ingest/missing', { method: 'POST' });
                    const res = await response.json();
                    alert(res.message);
                    pollIngestProgress();
                } catch(e) {
                    alert("Erreur lors du lancement : " + e.message);
                    btn.disabled = false;
                    btn.innerText = "Importer les manquants";
                }
            }

            async function triggerUpdateAll() {
                const btn = document.getElementById('update-all-btn');
                btn.disabled = true;
                btn.innerText = "Lancement...";
                try {
                    const response = await fetch('/api/ingest/update_all', { method: 'POST' });
                    const res = await response.json();
                    alert(res.message);
                    pollIngestProgress();
                } catch(e) {
                    alert("Erreur lors du lancement : " + e.message);
                    btn.disabled = false;
                    btn.innerText = "Actualiser tout (2022-2026)";
                }
            }

            function initChart() {
                const container = document.getElementById('chart-container');
                
                if (typeof LightweightCharts === 'undefined') {
                    console.error("TradingView Lightweight Charts library is not loaded.");
                    container.innerHTML = `
                        <div class="flex flex-col items-center justify-center h-full text-slate-400 p-6 text-center space-y-2">
                            <svg class="w-12 h-12 text-rose-500/80" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                            <div class="font-semibold text-slate-200">Mode Hors-ligne / Erreur CDN</div>
                            <div class="text-xs">Impossible de charger la bibliothèque de graphiques TradingView (Lightweight Charts). La visualisation graphique est désactivée, mais vous pouvez toujours explorer les tableaux de données et lancer les imports.</div>
                        </div>
                    `;
                    return;
                }
                
                chart = LightweightCharts.createChart(container, {
                    layout: {
                        background: { color: '#060813' },
                        textColor: '#64748b',
                        fontSize: 11,
                        fontFamily: "'Inter', sans-serif",
                    },
                    grid: {
                        vertLines: { color: 'rgba(148, 163, 184, 0.04)', style: 2 }, // dotted
                        horzLines: { color: 'rgba(148, 163, 184, 0.04)', style: 2 }, // dotted
                    },
                    crosshair: {
                        mode: LightweightCharts.CrosshairMode.Normal,
                        vertLine: {
                            color: 'rgba(148, 163, 184, 0.25)',
                            width: 1,
                            style: 3, // dashed
                            labelBackgroundColor: '#0f172a',
                        },
                        horzLine: {
                            color: 'rgba(148, 163, 184, 0.25)',
                            width: 1,
                            style: 3, // dashed
                            labelBackgroundColor: '#0f172a',
                        },
                    },
                    rightPriceScale: {
                        borderColor: 'rgba(148, 163, 184, 0.08)',
                        textColor: '#64748b',
                    },
                    timeScale: {
                        borderColor: 'rgba(148, 163, 184, 0.08)',
                        textColor: '#64748b',
                        timeVisible: true,
                        secondsVisible: false,
                    },
                });

                // Add series with premium colors
                candleSeries = chart.addCandlestickSeries({
                    upColor: '#10b981',
                    downColor: '#f43f5e',
                    borderVisible: true,
                    borderColor: '#10b981',
                    borderUpColor: '#10b981',
                    borderDownColor: '#f43f5e',
                    wickUpColor: '#10b981',
                    wickDownColor: '#f43f5e',
                });

                volumeSeries = chart.addHistogramSeries({
                    color: 'rgba(16, 185, 129, 0.25)',
                    priceFormat: {
                        type: 'volume',
                    },
                    priceScaleId: '', // overlay
                });
                
                volumeSeries.priceScale().applyOptions({
                    scaleMargins: {
                        top: 0.82, // volume at bottom
                        bottom: 0,
                    },
                });

                areaSeries = chart.addAreaSeries({
                    topColor: 'rgba(16, 185, 129, 0.22)',
                    bottomColor: 'rgba(16, 185, 129, 0.0)',
                    lineColor: '#10b981',
                    lineWidth: 2,
                });

                // Subscribe to crosshair move to display premium real-time legend values
                chart.subscribeCrosshairMove(param => {
                    const ohlcvLegend = document.getElementById('chart-ohlcv-legend');
                    const priceLabel = document.getElementById('chart-price-label');
                    
                    if (!param.time || !param.point || param.point.x < 0 || param.point.y < 0) {
                        // Reset to last bar when cursor leaves
                        updateLegendWithLastBar();
                    } else {
                        const candleData = param.seriesData.get(candleSeries);
                        const volumeData = param.seriesData.get(volumeSeries);
                        const areaData = param.seriesData.get(areaSeries);
                        
                        let dateStr = "";
                        if (typeof param.time === 'string') {
                            dateStr = param.time;
                        } else if (typeof param.time === 'object' && param.time !== null) {
                            dateStr = `${param.time.year}-${String(param.time.month).padStart(2,'0')}-${String(param.time.day).padStart(2,'0')}`;
                        } else {
                            // timestamp
                            const date = new Date(param.time * 1000);
                            dateStr = date.toISOString().split('T')[0];
                        }

                        if (candleData) {
                            ohlcvLegend.classList.remove('hidden');
                            ohlcvLegend.classList.add('flex');
                            priceLabel.classList.add('hidden');
                            
                            const isUp = candleData.close >= candleData.open;
                            const colorClass = isUp ? 'text-emerald-400' : 'text-rose-400';
                            
                            const o = candleData.open.toFixed(4);
                            const h = candleData.high.toFixed(4);
                            const l = candleData.low.toFixed(4);
                            const c = candleData.close.toFixed(4);
                            const v = volumeData ? volumeData.value.toLocaleString() : '-';
                            
                            ohlcvLegend.innerHTML = `
                                <span>D: <strong class="text-slate-200">${dateStr}</strong></span>
                                <span>O: <strong class="${colorClass}">${o}</strong></span>
                                <span>H: <strong class="${colorClass}">${h}</strong></span>
                                <span>L: <strong class="${colorClass}">${l}</strong></span>
                                <span>C: <strong class="${colorClass}">${c}</strong></span>
                                <span>V: <strong class="text-slate-200">${v}</strong></span>
                            `;
                        } else if (areaData) {
                            ohlcvLegend.classList.remove('hidden');
                            ohlcvLegend.classList.add('flex');
                            priceLabel.classList.add('hidden');
                            
                            const val = areaData.value.toFixed(4);
                            ohlcvLegend.innerHTML = `
                                <span>D: <strong class="text-slate-200">${dateStr}</strong></span>
                                <span>Valeur: <strong class="text-emerald-400">${val}</strong></span>
                            `;
                        } else {
                            updateLegendWithLastBar();
                        }
                    }
                });

                function updateLegendWithLastBar() {
                    const ohlcvLegend = document.getElementById('chart-ohlcv-legend');
                    const priceLabel = document.getElementById('chart-price-label');
                    ohlcvLegend.classList.add('hidden');
                    ohlcvLegend.classList.remove('flex');
                    priceLabel.classList.remove('hidden');
                }

                // Resize handler
                const resizeObserver = new ResizeObserver(entries => {
                    if (entries.length === 0 || entries[0].target !== container) { return; }
                    const newRect = entries[0].contentRect;
                    chart.resize(newRect.width, newRect.height);
                });
                resizeObserver.observe(container);
            }

            let currentAssetClassSymbols = [];

            function onAssetClassChange() {
                const assetClass = document.getElementById('asset-class').value;
                
                // Get unique symbols for this asset class
                const filtered = allSymbols.filter(s => s.asset_class === assetClass);
                
                // Remove duplicates by symbol name
                const uniqueSymbols = [];
                const seen = new Set();
                for (const item of filtered) {
                    if (!seen.has(item.symbol)) {
                        seen.add(item.symbol);
                        uniqueSymbols.push(item);
                    }
                }
                
                // Sort symbols
                uniqueSymbols.sort((a, b) => a.symbol.localeCompare(b.symbol));
                
                currentAssetClassSymbols = uniqueSymbols.map(item => {
                    const symUpper = item.symbol.toUpperCase();
                    const name = item.longname || item.shortname || '';
                    return {
                        symbol: symUpper,
                        label: symUpper + (name ? ` - ${name}` : '')
                    };
                });
                
                // Select first symbol by default
                if (currentAssetClassSymbols.length > 0) {
                    selectSymbol(currentAssetClassSymbols[0].symbol, currentAssetClassSymbols[0].label, false);
                } else {
                    selectSymbol('', '', false);
                }

                // Timeframe and adjustments visibility
                const tfContainer = document.getElementById('timeframe-container');
                const adjContainer = document.getElementById('adjustment-container');
                
                if (assetClass === 'macro') {
                    tfContainer.classList.add('hidden');
                    adjContainer.classList.add('hidden');
                } else {
                    tfContainer.classList.remove('hidden');
                    adjContainer.classList.remove('hidden');
                }

                // Render options
                renderSymbolOptions(currentAssetClassSymbols);
                
                // Trigger update
                onSymbolChange();
            }

            function selectSymbol(symbol, label, triggerChange = true) {
                document.getElementById('symbol').value = symbol;
                const assetClass = document.getElementById('asset-class').value;
                const cleanLabel = label || symbol;
                document.getElementById('symbol-search').value = cleanLabel;

                // Update active logo in search bar
                const logoContainer = document.getElementById('active-symbol-logo-container');
                const searchInput = document.getElementById('symbol-search');
                const chartLogo = document.getElementById('chart-symbol-logo');

                if (logoContainer && searchInput) {
                    logoContainer.innerHTML = getSymbolLogoHtml(symbol, cleanLabel, assetClass);
                    logoContainer.classList.remove('hidden');
                    searchInput.style.paddingLeft = '2.25rem';
                }

                if (chartLogo) {
                    chartLogo.innerHTML = getSymbolLogoHtml(symbol, cleanLabel, assetClass);
                }

                if (triggerChange) {
                    onSymbolChange();
                }
            }

            function renderSymbolOptions(items) {
                const dropdown = document.getElementById('symbol-dropdown');
                dropdown.innerHTML = '';
                
                if (items.length === 0) {
                    dropdown.innerHTML = '<div class="px-3 py-2 text-xs text-slate-500">No symbol found</div>';
                    return;
                }
                
                const selectedVal = document.getElementById('symbol').value;
                const assetClass = document.getElementById('asset-class').value;
                
                items.forEach(item => {
                    const isSelected = item.symbol === selectedVal;
                    const div = document.createElement('div');
                    div.className = `flex items-center space-x-2.5 px-3 py-2 text-xs cursor-pointer select-none hover:bg-blue-600 hover:text-white transition duration-100 ${isSelected ? 'bg-blue-600/35 text-blue-300 font-semibold' : 'text-slate-300'}`;
                    
                    const logoHtml = getSymbolLogoHtml(item.symbol, item.label, assetClass);
                    div.innerHTML = `
                        <div class="flex-shrink-0 flex items-center justify-center">${logoHtml}</div>
                        <span class="truncate font-medium">${item.label}</span>
                    `;
                    
                    div.onclick = () => {
                        selectSymbol(item.symbol, item.label, true);
                        toggleSymbolDropdown(false);
                    };
                    dropdown.appendChild(div);
                });
            }

            function filterSymbols() {
                const text = document.getElementById('symbol-search').value.toLowerCase().trim();
                
                if (text === '') {
                    renderSymbolOptions(currentAssetClassSymbols);
                    return;
                }
                
                const matches = currentAssetClassSymbols.filter(item => 
                    item.symbol.toLowerCase().includes(text) || 
                    item.label.toLowerCase().includes(text)
                );
                
                renderSymbolOptions(matches);
            }

            function toggleSymbolDropdown(show) {
                const dropdown = document.getElementById('symbol-dropdown');
                const logoContainer = document.getElementById('active-symbol-logo-container');
                const searchInput = document.getElementById('symbol-search');

                if (show) {
                    dropdown.classList.remove('hidden');
                    renderSymbolOptions(currentAssetClassSymbols);
                    
                    if (logoContainer && searchInput) {
                        logoContainer.classList.add('hidden');
                        searchInput.style.paddingLeft = '0.75rem';
                        searchInput.select();
                    }
                } else {
                    setTimeout(() => {
                        dropdown.classList.add('hidden');
                        const selectedVal = document.getElementById('symbol').value;
                        const match = currentAssetClassSymbols.find(item => item.symbol === selectedVal);
                        if (match) {
                            searchInput.value = match.label;
                            if (logoContainer && searchInput) {
                                logoContainer.innerHTML = getSymbolLogoHtml(match.symbol, match.label, document.getElementById('asset-class').value);
                                logoContainer.classList.remove('hidden');
                                searchInput.style.paddingLeft = '2.25rem';
                            }
                        }
                    }, 200);
                }
            }

            // Hide dropdown when clicking outside
            document.addEventListener('click', (e) => {
                const searchInput = document.getElementById('symbol-search');
                const dropdown = document.getElementById('symbol-dropdown');
                if (searchInput && dropdown) {
                    if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
                        dropdown.classList.add('hidden');
                    }
                }
            });

            function onSymbolChange() {
                const symbol = document.getElementById('symbol').value;
                if (!symbol) return;
                
                const assetClass = document.getElementById('asset-class').value;
                
                // Populate timeframe dropdown dynamically based on catalog entries
                const symbolEntries = allSymbols.filter(s => s.symbol === symbol && s.asset_class === assetClass);
                const timeframeDropdown = document.getElementById('timeframe');
                const previousTimeframeVal = timeframeDropdown.value;
                timeframeDropdown.innerHTML = '';
                
                if (assetClass !== 'macro') {
                    const timeframes = symbolEntries.map(s => s.timeframe);
                    const uniqueTfs = new Set(timeframes);
                    
                    const defaultTfs = ['D1', '1h', '15m', '5m', '1m'];
                    defaultTfs.forEach(tf => {
                        const opt = document.createElement('option');
                        opt.value = tf;
                        const label = tf === 'D1' ? 'Daily (D1)' : tf === '1h' ? '1 Heure (1h)' : tf === '15m' ? '15 Minutes (15m)' : tf === '5m' ? '5 Minutes (5m)' : '1 Minute (1m)';
                        const status = uniqueTfs.has(tf) ? ' (Local)' : ' (Non importé)';
                        opt.innerText = label + status;
                        timeframeDropdown.appendChild(opt);
                    });
                    
                    if (previousTimeframeVal && defaultTfs.includes(previousTimeframeVal)) {
                        timeframeDropdown.value = previousTimeframeVal;
                    }
                }
                
                // Update headers, meta, financials
                document.getElementById('chart-symbol-label').innerText = symbol;
                const chartLogo = document.getElementById('chart-symbol-logo');
                if (chartLogo) {
                    chartLogo.innerHTML = getSymbolLogoHtml(symbol, symbol, assetClass);
                }
                document.getElementById('chart-price-label').innerText = "";
                
                const meta = allSymbols.find(s => s.symbol === symbol && s.asset_class === assetClass) || {};
                
                document.getElementById('meta-longname').innerText = meta.longname || meta.shortname || symbol;
                document.getElementById('meta-sector').innerText = meta.sector || 'N/A';
                document.getElementById('meta-industry').innerText = meta.industry || 'N/A';
                document.getElementById('meta-marketcap').innerText = meta.marketcap ? formatLargeNumber(meta.marketcap) : 'N/A';
                document.getElementById('meta-weight').innerText = meta.weight ? `${(meta.weight * 100).toFixed(4)}%` : 'N/A';
                document.getElementById('meta-exchange').innerText = meta.exchange || 'N/A';
                document.getElementById('meta-summary').innerText = meta.summary || "Pas de description commerciale disponible.";
                
                document.getElementById('cat-range').innerText = `${meta.start_date || 'N/A'} au ${meta.end_date || 'N/A'}`;
                document.getElementById('cat-rows').innerText = meta.rows_count ? Number(meta.rows_count).toLocaleString() : 'N/A';
                document.getElementById('cat-nulls').innerText = meta.nulls_pct !== undefined && meta.nulls_pct !== null ? `${Number(meta.nulls_pct).toFixed(2)}%` : 'N/A';
                
                const qualityEl = document.getElementById('cat-quality');
                if (meta.quality_score !== undefined && meta.quality_score !== null) {
                    const score = Number(meta.quality_score);
                    qualityEl.innerText = `${score.toFixed(1)}/100`;
                    qualityEl.className = "font-semibold mt-1 " + (score >= 90 ? "text-emerald-400" : score >= 70 ? "text-amber-400" : "text-rose-500");
                } else {
                    qualityEl.innerText = 'N/A';
                    qualityEl.className = "font-semibold text-slate-200 mt-1";
                }

                loadFinancials(symbol);
                loadChartData();
            }

            async function loadChartData() {
                const assetClass = document.getElementById('asset-class').value;
                const symbol = document.getElementById('symbol').value;
                if (!symbol) return;
                
                if (typeof LightweightCharts === 'undefined') {
                    document.getElementById('chart-price-label').innerText = "(Mode Tableau Uniquement)";
                    currentData = [];
                    try {
                        if (assetClass === 'macro') {
                            const res = await fetch(`/api/macro/${symbol}`);
                            const data = await res.json();
                            currentData = data;
                            populateRawTable(data, true);
                        } else {
                            const timeframe = document.getElementById('timeframe').value;
                            if (!timeframe) return;
                            const adjusted = document.getElementById('adjusted-prices').checked;
                            const res = await fetch(`/api/ohlcv?symbol=${symbol}&timeframe=${timeframe}&adjusted=${adjusted}`);
                            const data = await res.json();
                            currentData = data;
                            populateRawTable(data, false);
                        }
                    } catch (e) {
                        console.error("Failed to load table data:", e);
                    }
                    return;
                }
                
                candleSeries.setData([]);
                volumeSeries.setData([]);
                areaSeries.setData([]);
                currentData = [];

                try {
                    if (assetClass === 'macro') {
                        const res = await fetch(`/api/macro/${symbol}`);
                        const data = await res.json();
                        currentData = data;
                        
                        areaSeries.setData(data);
                        
                        candleSeries.applyOptions({ visible: false });
                        volumeSeries.applyOptions({ visible: false });
                        areaSeries.applyOptions({ visible: true });
                        
                        if (data.length > 0) {
                            const last = data[data.length - 1];
                            document.getElementById('chart-price-label').innerText = last.value.toFixed(2);
                            chart.timeScale().fitContent();
                        }
                        populateRawTable(data, true);
                    } else {
                        const timeframe = document.getElementById('timeframe').value;
                        if (!timeframe) return;
                        
                        const adjusted = document.getElementById('adjusted-prices').checked;
                        
                        const res = await fetch(`/api/ohlcv?symbol=${symbol}&timeframe=${timeframe}&adjusted=${adjusted}`);
                        const data = await res.json();
                        currentData = data;
                        
                        if (data.length === 0) {
                            document.getElementById('chart-price-label').innerText = "Non importé localement - Utilisez le formulaire ci-dessous";
                            candleSeries.setData([]);
                            volumeSeries.setData([]);
                            areaSeries.setData([]);
                            populateRawTable([], false);
                            return;
                        }
                        
                        const candles = data.map(r => ({
                            time: r.time,
                            open: r.open,
                            high: r.high,
                            low: r.low,
                            close: r.close
                        }));
                        
                        const volumes = data.map(r => ({
                            time: r.time,
                            value: r.value,
                            color: r.close >= r.open ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'
                        }));
                        
                        candleSeries.setData(candles);
                        volumeSeries.setData(volumes);
                        
                        candleSeries.applyOptions({ visible: true });
                        volumeSeries.applyOptions({ visible: true });
                        areaSeries.applyOptions({ visible: false });
                        
                        const last = data[data.length - 1];
                        document.getElementById('chart-price-label').innerText = last.close.toFixed(4) + ` (Vol: ${last.value.toLocaleString()})`;
                        
                        chart.timeScale().fitContent();
                        populateRawTable(data, false);
                    }
                } catch(e) {
                    console.error("Error loading chart data:", e);
                }
            }

            function populateRawTable(data, isMacro) {
                const tbody = document.getElementById('table-tbody');
                const emptyMsg = document.getElementById('table-empty');
                const rowCountEl = document.getElementById('table-row-count');
                
                tbody.innerHTML = '';
                
                if (data.length === 0) {
                    emptyMsg.classList.remove('hidden');
                    rowCountEl.classList.add('hidden');
                    return;
                }
                
                emptyMsg.classList.add('hidden');
                rowCountEl.classList.remove('hidden');
                
                // Show last 100 rows
                const slicedData = data.slice(-100).reverse();
                rowCountEl.innerText = `Affichage des ${slicedData.length} dernières lignes (sur ${data.length})`;
                
                slicedData.forEach(r => {
                    const tr = document.createElement('tr');
                    tr.className = "hover:bg-slate-800/20";
                    
                    // time can be a 'YYYY-MM-DD' string (D1) or a unix seconds integer (intraday)
                    let dateStr;
                    if (typeof r.time === 'string') {
                        dateStr = r.time; // D1: already formatted
                    } else {
                        dateStr = new Date(r.time * 1000).toISOString().replace('T', ' ').substring(0, 19) + ' UTC';
                    }
                    
                    if (isMacro) {
                        tr.innerHTML = `
                            <td class="py-2 px-3 font-medium">${dateStr}</td>
                            <td class="py-2 px-3 text-right" colspan="4">${r.value.toFixed(4)}</td>
                            <td class="py-2 px-3 text-right text-slate-500">-</td>
                        `;
                    } else {
                        tr.innerHTML = `
                            <td class="py-2 px-3 font-medium">${dateStr}</td>
                            <td class="py-2 px-3 text-right">${r.open.toFixed(4)}</td>
                            <td class="py-2 px-3 text-right text-emerald-400">${r.high.toFixed(4)}</td>
                            <td class="py-2 px-3 text-right text-rose-400">${r.low.toFixed(4)}</td>
                            <td class="py-2 px-3 text-right font-semibold">${r.close.toFixed(4)}</td>
                            <td class="py-2 px-3 text-right text-slate-400">${r.value.toLocaleString()}</td>
                        `;
                    }
                    tbody.appendChild(tr);
                });
            }

            async function triggerIngestion() {
                const symbol = document.getElementById('symbol').value;
                const timeframe = document.getElementById('timeframe').value;
                const source = document.getElementById('ingest-source').value;
                const start_date = document.getElementById('ingest-start').value;
                const end_date = document.getElementById('ingest-end').value;
                const assetClass = document.getElementById('asset-class').value;
                
                if (!symbol || !timeframe || !start_date || !end_date) {
                    alert("Tous les champs (Symbole, Timeframe, Dates) sont requis pour l'import.");
                    return;
                }
                
                const btn = document.getElementById('ingest-btn');
                const btnText = document.getElementById('ingest-btn-text');
                const statusEl = document.getElementById('ingest-status');
                
                btn.disabled = true;
                btn.classList.add('bg-blue-800');
                btnText.innerText = "Synchronisation en cours...";
                
                statusEl.classList.remove('hidden', 'text-emerald-400', 'text-rose-400');
                statusEl.classList.add('text-slate-400');
                statusEl.innerText = "Connexion aux APIs et écriture Parquet...";
                
                try {
                    const response = await fetch('/api/ingest', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            symbol: symbol,
                            timeframe: timeframe,
                            source: source,
                            start_date: start_date,
                            end_date: end_date,
                            asset_class: assetClass
                        })
                    });
                    
                    const resJson = await response.json();
                    
                    if (response.status === 200) {
                        statusEl.classList.remove('text-slate-400');
                        statusEl.classList.add('text-emerald-400');
                        statusEl.innerText = `Succès ! +${resJson.rows} lignes importées.`;
                        
                        // Refresh elements
                        await refreshSymbolsList();
                        await loadStats();
                        // Select the current symbol and timeframe again
                        document.getElementById('symbol').value = symbol;
                        onSymbolChange();
                    } else {
                        statusEl.classList.remove('text-slate-400');
                        statusEl.classList.add('text-rose-400');
                        statusEl.innerText = `Erreur: ${resJson.detail || 'Erreur inconnue'}`;
                    }
                } catch (e) {
                    statusEl.classList.remove('text-slate-400');
                    statusEl.classList.add('text-rose-400');
                    statusEl.innerText = `Erreur réseau: ${e.message}`;
                } finally {
                    btn.disabled = false;
                    btn.classList.remove('bg-blue-800');
                    btnText.innerText = "Lancer l'Import";
                }
            }

            async function downloadCSV() {
                const symbol = document.getElementById('symbol').value;
                if (!symbol) {
                    alert("Veuillez sélectionner un symbole d'abord.");
                    return;
                }
                const assetClass = document.getElementById('asset-class').value;
                
                // Show modal & loading state
                document.getElementById('export-symbol-title').innerText = symbol;
                
                // Initialize date inputs based on catalog info
                const activeTF = document.getElementById('timeframe') ? document.getElementById('timeframe').value : 'D1';
                const activeSymInfo = allSymbols.find(s => s.symbol.toUpperCase() === symbol.toUpperCase() && s.timeframe === activeTF);
                if (activeSymInfo && activeSymInfo.start_date) {
                    document.getElementById('export-start-date').value = activeSymInfo.start_date.substring(0, 10);
                } else {
                    document.getElementById('export-start-date').value = '1996-01-02';
                }
                if (activeSymInfo && activeSymInfo.end_date) {
                    document.getElementById('export-end-date').value = activeSymInfo.end_date.substring(0, 10);
                } else {
                    document.getElementById('export-end-date').value = '2026-08-16';
                }

                const container = document.getElementById('export-checkboxes-container');
                container.innerHTML = `
                    <div class="flex items-center justify-center py-6 text-slate-400 space-x-2 text-xs">
                        <svg class="animate-spin h-4 w-4 text-blue-500" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                        <span>Analyse des données disponibles...</span>
                    </div>
                `;
                document.getElementById('export-modal').classList.remove('hidden');
                
                try {
                    const response = await fetch(`/api/datasets_status/${symbol}`);
                    const status = await response.json();
                    
                    let html = '';
                    
                    if (assetClass === 'macro') {
                        status.macro.forEach(m => {
                            const isDefault = (symbol === m);
                            html += `
                                <label class="flex items-center space-x-3 p-3 rounded-lg bg-slate-950 border border-slate-800 hover:border-slate-700 transition cursor-pointer select-none col-span-1 sm:col-span-2">
                                    <input type="checkbox" name="export-item" value="macro_${m}" ${isDefault ? 'checked' : ''} class="rounded border-slate-700 text-blue-600 bg-slate-900 focus:ring-blue-500">
                                    <div>
                                        <div class="text-xs font-semibold text-slate-200">${m}</div>
                                        <div class="text-[10px] text-slate-500">Série macroéconomique historique</div>
                                    </div>
                                </label>
                            `;
                        });
                    } else {
                        // 1. OHLCV timeframes grouped under subheader
                        if (status.ohlcv && status.ohlcv.length > 0) {
                            html += `<div class="col-span-1 sm:col-span-2 text-[10px] font-bold uppercase tracking-wider text-slate-500 mt-2 mb-1.5">PRICE SERIES (OHLCV)</div>`;
                            status.ohlcv.forEach(tf => {
                                const tfLabel = tf === 'D1' ? 'Daily (D1)' 
                                              : tf === '4h' ? '4 Hours (4h)' 
                                              : tf === '1h' ? '1 Hour (1h)' 
                                              : tf === '15m' ? '15 Minutes (15m)' 
                                              : tf === '5m' ? '5 Minutes (5m)' 
                                              : tf === '1m' ? '1 Minute (1m)' 
                                              : tf === '1W' ? 'Weekly (1W)' 
                                              : tf === '1M' ? 'Monthly (1M)' 
                                              : tf;
                                const isDefault = (tf === (document.getElementById('timeframe') ? document.getElementById('timeframe').value : 'D1'));
                                html += `
                                    <label class="flex items-center space-x-3.5 p-3.5 rounded-lg bg-[#070b15] border border-slate-900/60 hover:border-slate-800 transition cursor-pointer select-none col-span-1 shadow-md shadow-slate-950/20">
                                        <input type="checkbox" name="export-item" value="ohlcv_${tf}" ${isDefault ? 'checked' : ''} class="w-4 h-4 rounded border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                                        <div>
                                            <div class="text-xs font-bold text-slate-200">${tfLabel}</div>
                                            <div class="text-[10px] text-slate-500 font-medium">Prices & Volumes</div>
                                        </div>
                                    </label>
                                `;
                            });
                        }
                        
                        // 2. Financials
                        if (status.financials.income || status.financials.balance || status.financials.cashflow) {
                            html += `
                                <div class="p-4 rounded-xl bg-[#050810]/60 border border-slate-900 space-y-3 col-span-1 sm:col-span-2 mt-2 shadow-inner">
                                    <div class="text-[10px] font-bold uppercase tracking-wider text-slate-500 border-b border-slate-900 pb-1.5">Financial Data (Statements)</div>
                                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pl-1">
                            `;
                            if (status.financials.income) {
                                html += `
                                    <label class="flex items-center space-x-2.5 text-xs text-slate-300 cursor-pointer select-none">
                                        <input type="checkbox" name="export-item" value="fin_income" class="w-4 h-4 rounded border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                                        <span class="font-medium">Income Statement (Revenue, EPS...)</span>
                                    </label>
                                `;
                            }
                            if (status.financials.balance) {
                                html += `
                                    <label class="flex items-center space-x-2.5 text-xs text-slate-300 cursor-pointer select-none">
                                        <input type="checkbox" name="export-item" value="fin_balance" class="w-4 h-4 rounded border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                                        <span class="font-medium">Balance Sheet (Assets, Debt...)</span>
                                    </label>
                                `;
                            }
                            if (status.financials.cashflow) {
                                html += `
                                    <label class="flex items-center space-x-2.5 text-xs text-slate-300 cursor-pointer select-none">
                                        <input type="checkbox" name="export-item" value="fin_cashflow" class="w-4 h-4 rounded border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                                        <span class="font-medium">Cash Flow Statement (FCF, Operating CF...)</span>
                                    </label>
                                `;
                            }
                            html += `
                                    </div>
                                </div>
                            `;
                        }

                        // 3. Volatility, Options & Corporate Actions
                        if (status.volatility || status.options || status.corporate_actions) {
                            html += `<div class="col-span-1 sm:col-span-2 text-[10px] font-bold uppercase tracking-wider text-slate-500 mt-4 mb-1.5">VOLATILITY & DERIVATIVES</div>`;
                            
                            if (status.volatility) {
                                html += `
                                    <label class="flex items-center space-x-3.5 p-3.5 rounded-lg bg-[#070b15] border border-slate-900/60 hover:border-slate-800 transition cursor-pointer select-none col-span-1 shadow-md shadow-slate-950/20">
                                        <input type="checkbox" name="export-item" value="volatility" class="w-4 h-4 rounded border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                                        <div>
                                            <div class="text-xs font-bold text-slate-200">Option Volatility</div>
                                            <div class="text-[10px] text-slate-500 font-medium">Historical HV / IV from options</div>
                                        </div>
                                    </label>
                                `;
                            }
                            if (status.options) {
                                html += `
                                    <label class="flex items-center space-x-3.5 p-3.5 rounded-lg bg-[#070b15] border border-slate-900/60 hover:border-slate-800 transition cursor-pointer select-none col-span-1 shadow-md shadow-slate-950/20">
                                        <input type="checkbox" name="export-item" value="options" class="w-4 h-4 rounded border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                                        <div>
                                            <div class="text-xs font-bold text-slate-200">Option Chain</div>
                                            <div class="text-[10px] text-slate-500 font-medium">Historical Greeks & prices</div>
                                        </div>
                                    </label>
                                `;
                            }
                            if (status.corporate_actions) {
                                html += `
                                    <label class="flex items-center space-x-3.5 p-3.5 rounded-lg bg-[#070b15] border border-slate-900/60 hover:border-slate-800 transition cursor-pointer select-none col-span-1 sm:col-span-2 shadow-md shadow-slate-950/20">
                                        <input type="checkbox" name="export-item" value="corporate_actions" class="w-4 h-4 rounded border-slate-800 text-blue-600 bg-slate-950 focus:ring-blue-500/20">
                                        <div>
                                            <div class="text-xs font-bold text-slate-200">Corporate Actions</div>
                                            <div class="text-[10px] text-slate-500 font-medium">Historical dividends and splits</div>
                                        </div>
                                    </label>
                                `;
                            }
                        }

                        // 4. Bloomberg Golden Data
                        if (status.bloomberg_fundamentals || status.bloomberg_volatility) {
                            html += `<div class="col-span-1 sm:col-span-2 text-[10px] font-bold uppercase tracking-wider text-amber-500 mt-4 mb-1.5">BLOOMBERG GOLDEN DATA</div>`;
                            
                            if (status.bloomberg_fundamentals) {
                                html += `
                                    <label class="flex items-center space-x-3.5 p-3.5 rounded-lg bg-[#070b15] border border-amber-950/20 hover:border-amber-900/40 transition cursor-pointer select-none col-span-1 sm:col-span-2 shadow-md shadow-slate-950/20">
                                        <input type="checkbox" name="export-item" value="bb_fundamentals" class="w-4 h-4 rounded border-amber-800/40 text-amber-600 bg-[#070b15] focus:ring-amber-500/20">
                                        <div>
                                            <div class="text-xs font-bold text-amber-400 font-medium">Monthly Fundamentals (Bloomberg)</div>
                                            <div class="text-[10px] text-slate-500 font-medium">PE Multiples, Price-to-Book, Raw/Adj Beta, Sales</div>
                                        </div>
                                    </label>
                                `;
                            }
                            if (status.bloomberg_volatility) {
                                html += `
                                    <label class="flex items-center space-x-3.5 p-3.5 rounded-lg bg-[#070b15] border border-amber-950/20 hover:border-amber-900/40 transition cursor-pointer select-none col-span-1 sm:col-span-2 shadow-md shadow-slate-950/20">
                                        <input type="checkbox" name="export-item" value="bb_volatility" class="w-4 h-4 rounded border-amber-800/40 text-amber-600 bg-[#070b15] focus:ring-amber-500/20">
                                        <div>
                                            <div class="text-xs font-bold text-amber-400 font-medium">Realized Volatility 30D (Bloomberg)</div>
                                            <div class="text-[10px] text-slate-500 font-medium">Bloomberg daily historical series</div>
                                        </div>
                                    </label>
                                `;
                            }
                        }
                    }
                    
                    if (html === '') {
                        container.innerHTML = `
                            <div class="text-center py-6 text-slate-500 text-xs col-span-1 sm:col-span-2">
                                Aucune donnée disponible à l'export pour ce symbole.
                            </div>
                        `;
                        document.getElementById('modal-export-btn').disabled = true;
                    } else {
                        container.innerHTML = html;
                        document.getElementById('modal-export-btn').disabled = false;
                    }
                    
                } catch (e) {
                    console.error("Error analyzing datasets:", e);
                    container.innerHTML = `
                        <div class="text-center py-6 text-rose-400 text-xs col-span-1 sm:col-span-2">
                            Erreur lors de l'analyse des jeux de données : ${e.message}
                        </div>
                    `;
                    document.getElementById('modal-export-btn').disabled = true;
                }
            }
            
            function closeExportModal() {
                document.getElementById('export-modal').classList.add('hidden');
            }

             async function executeExport() {
                const checkboxes = document.querySelectorAll('input[name="export-item"]:checked');
                if (checkboxes.length === 0) {
                    alert("Veuillez cocher au moins une donnée à exporter.");
                    return;
                }
                
                const symbol = document.getElementById('export-symbol-title').innerText;
                const assetClass = document.getElementById('asset-class').value;
                const btn = document.getElementById('modal-export-btn');
                
                const startDate = document.getElementById('export-start-date').value;
                const endDate = document.getElementById('export-end-date').value;
                
                btn.disabled = true;
                btn.classList.add('bg-blue-800');
                btn.innerText = "Génération...";
                
                const formatEl = document.querySelector('input[name="export-format"]:checked');
                const exportFormat = formatEl ? formatEl.value : 'separate';
                
                if (exportFormat === 'consolidated') {
                    let includeVolatility = false;
                    let includeFundamentals = false;
                    let includeFinancials = false;
                    
                    checkboxes.forEach(cb => {
                        const val = cb.value;
                        if (val === 'bb_volatility') includeVolatility = true;
                        if (val === 'bb_fundamentals') includeFundamentals = true;
                        if (val === 'fin_income' || val === 'fin_balance' || val === 'fin_cashflow') includeFinancials = true;
                    });
                    
                    try {
                        const adjusted = document.getElementById('adjusted-prices').checked;
                        const res = await fetch(`/api/export/consolidated/${symbol}?timeframe=D1&adjusted=${adjusted}&start_date=${startDate}&end_date=${endDate}&include_volatility=${includeVolatility}&include_fundamentals=${includeFundamentals}&include_financials=${includeFinancials}`);
                        
                        if (res.status !== 200) {
                            const err = await res.json();
                            throw new Error(err.detail || "Erreur serveur");
                        }
                        
                        const data = await res.json();
                        if (data.length === 0) {
                            alert("Aucune donnée trouvée pour cette période.");
                            return;
                        }
                        
                        const headers = Object.keys(data[0]);
                        const rows = [headers.join(',')];
                        
                        data.forEach(r => {
                            const rowValues = headers.map(h => {
                                const val = r[h];
                                if (val === null || val === undefined) {
                                    return '';
                                }
                                if (typeof val === 'string' && val.includes(',')) {
                                    return `"${val}"`;
                                }
                                return val;
                            });
                            rows.push(rowValues.join(','));
                        });
                        
                        const csvContent = rows.join('\\r\\n');
                        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                        const url = URL.createObjectURL(blob);
                        const link = document.createElement("a");
                        link.setAttribute("href", url);
                        link.setAttribute("download", `${symbol}_consolidated_daily.csv`);
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                        
                        closeExportModal();
                    } catch (e) {
                        console.error("Export failed:", e);
                        alert("Erreur lors de la génération de l'export : " + e.message);
                    } finally {
                        btn.disabled = false;
                        btn.classList.remove('bg-blue-800');
                        btn.innerText = "Exporter";
                    }
                    return;
                }
                
                try {
                    const zip = new JSZip();
                    const exportTasks = [];
                    
                    checkboxes.forEach(cb => {
                        const val = cb.value;
                        
                        if (val.startsWith('ohlcv_')) {
                            const tf = val.replace('ohlcv_', '');
                            exportTasks.push((async () => {
                                const adjusted = document.getElementById('adjusted-prices').checked;
                                const res = await fetch(`/api/ohlcv?symbol=${symbol}&timeframe=${tf}&adjusted=${adjusted}&start_date=${startDate}&end_date=${endDate}`);
                                const data = await res.json();
                                
                                const rows = ['timestamp,open,high,low,close,volume'];
                                data.forEach(r => {
                                    const dateStr = typeof r.time === 'string' ? r.time : new Date(r.time * 1000).toISOString().replace('T', ' ').substring(0, 19);
                                    rows.push(`${dateStr},${r.open},${r.high},${r.low},${r.close},${r.value}`);
                                });
                                zip.file(`${symbol}_OHLCV_${tf}.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val.startsWith('macro_')) {
                            const mSym = val.replace('macro_', '');
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/macro/${mSym}?start_date=${startDate}&end_date=${endDate}`);
                                const data = await res.json();
                                
                                const rows = ['timestamp,value'];
                                data.forEach(r => {
                                    const dateStr = typeof r.time === 'string' ? r.time : new Date(r.time * 1000).toISOString().replace('T', ' ').substring(0, 19);
                                    rows.push(`${dateStr},${r.value}`);
                                });
                                zip.file(`${mSym}_macro.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val === 'fin_income') {
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/export/financials/income/${symbol}?start_date=${startDate}&end_date=${endDate}`);
                                const data = await res.json();
                                
                                const rows = ['report_date,fiscal_period,symbol,revenue,net_income,eps,eps_estimate,actual_eps,eps_surprise'];
                                data.forEach(r => {
                                    rows.push(`${r.report_date || ''},${r.fiscal_period || ''},${r.symbol || ''},${r.revenue || ''},${r.net_income || ''},${r.eps !== null && r.eps !== undefined ? r.eps : ''},${r.eps_estimate !== null && r.eps_estimate !== undefined ? r.eps_estimate : ''},${r.actual_eps !== null && r.actual_eps !== undefined ? r.actual_eps : ''},${r.eps_surprise !== null && r.eps_surprise !== undefined ? r.eps_surprise : ''}`);
                                });
                                zip.file(`${symbol}_compte_de_resultat.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val === 'fin_balance') {
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/export/financials/balance/${symbol}?start_date=${startDate}&end_date=${endDate}`);
                                const data = await res.json();
                                
                                const rows = ['report_date,fiscal_period,symbol,total_assets,total_liabilities,equity,cash,total_debt'];
                                data.forEach(r => {
                                    rows.push(`${r.report_date || ''},${r.fiscal_period || ''},${r.symbol || ''},${r.total_assets || ''},${r.total_liabilities || ''},${r.equity || ''},${r.cash || ''},${r.total_debt || ''}`);
                                });
                                zip.file(`${symbol}_bilan_comptable.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val === 'fin_cashflow') {
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/export/financials/cashflow/${symbol}?start_date=${startDate}&end_date=${endDate}`);
                                const data = await res.json();
                                
                                const rows = ['report_date,fiscal_period,symbol,net_change_cash,operating_cf,capex,free_cash_flow'];
                                data.forEach(r => {
                                    rows.push(`${r.report_date || ''},${r.fiscal_period || ''},${r.symbol || ''},${r.net_change_cash || ''},${r.operating_cf || ''},${r.capex || ''},${r.free_cash_flow || ''}`);
                                });
                                zip.file(`${symbol}_flux_de_tresorerie.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val === 'volatility') {
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/export/volatility/${symbol}`);
                                const data = await res.json();
                                
                                const rows = ['timestamp,symbol,hv_current,hv_week_ago,hv_month_ago,hv_year_high,hv_year_high_date,hv_year_low,hv_year_low_date,iv_current,iv_week_ago,iv_month_ago,iv_year_high,iv_year_high_date,iv_year_low,iv_year_low_date'];
                                data.forEach(r => {
                                    rows.push(`${r.timestamp || ''},${r.symbol || ''},${r.hv_current || ''},${r.hv_week_ago || ''},${r.hv_month_ago || ''},${r.hv_year_high || ''},${r.hv_year_high_date || ''},${r.hv_year_low || ''},${r.hv_year_low_date || ''},${r.iv_current || ''},${r.iv_week_ago || ''},${r.iv_month_ago || ''},${r.iv_year_high || ''},${r.iv_year_high_date || ''},${r.iv_year_low || ''},${r.iv_year_low_date || ''}`);
                                });
                                zip.file(`${symbol}_volatility.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val === 'options') {
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/export/options/${symbol}`);
                                const data = await res.json();
                                
                                const rows = ['timestamp,symbol,expiration,strike,call_put,bid,ask,vol,delta,gamma,theta,vega,rho'];
                                data.forEach(r => {
                                    rows.push(`${r.timestamp || ''},${r.symbol || ''},${r.expiration || ''},${r.strike || ''},${r.call_put || ''},${r.bid || ''},${r.ask || ''},${r.vol || ''},${r.delta || ''},${r.gamma || ''},${r.theta || ''},${r.vega || ''},${r.rho || ''}`);
                                });
                                zip.file(`${symbol}_options_chain.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val === 'corporate_actions') {
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/export/corporate_actions/${symbol}`);
                                const data = await res.json();
                                
                                const rows = ['symbol,date,action_type,split_factor,dividend_amount'];
                                data.forEach(r => {
                                    rows.push(`${r.symbol || ''},${r.date || ''},${r.action_type || ''},${r.split_factor || ''},${r.dividend_amount || ''}`);
                                });
                                zip.file(`${symbol}_corporate_actions.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val === 'bb_fundamentals') {
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/export/bloomberg/fundamentals/${symbol}?start_date=${startDate}&end_date=${endDate}`);
                                const data = await res.json();
                                
                                const rows = ['date,implied_vol,pe_ratio,price_to_book,beta_raw,sales,beta_adj'];
                                data.forEach(r => {
                                    rows.push(`${r.date || ''},${r.implied_vol !== null && r.implied_vol !== undefined ? r.implied_vol : ''},${r.pe_ratio !== null && r.pe_ratio !== undefined ? r.pe_ratio : ''},${r.price_to_book !== null && r.price_to_book !== undefined ? r.price_to_book : ''},${r.beta_raw !== null && r.beta_raw !== undefined ? r.beta_raw : ''},${r.sales !== null && r.sales !== undefined ? r.sales : ''},${r.beta_adj !== null && r.beta_adj !== undefined ? r.beta_adj : ''}`);
                                });
                                zip.file(`${symbol}_bloomberg_fundamentals_monthly.csv`, rows.join('\\r\\n'));
                            })());
                        }
                        else if (val === 'bb_volatility') {
                            exportTasks.push((async () => {
                                const res = await fetch(`/api/export/bloomberg/volatility/${symbol}?start_date=${startDate}&end_date=${endDate}`);
                                const data = await res.json();
                                
                                const rows = ['date,realized_vol_30d'];
                                data.forEach(r => {
                                    rows.push(`${r.date || ''},${r.realized_vol_30d !== null && r.realized_vol_30d !== undefined ? r.realized_vol_30d : ''}`);
                                });
                                zip.file(`${symbol}_bloomberg_volatility_daily.csv`, rows.join('\\r\\n'));
                            })());
                        }
                    });
                    
                    await Promise.all(exportTasks);
                    
                    const fileNames = Object.keys(zip.files);
                    if (fileNames.length === 1) {
                        const fileName = fileNames[0];
                        const csvContent = await zip.files[fileName].async('string');
                        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                        const url = URL.createObjectURL(blob);
                        const link = document.createElement("a");
                        link.setAttribute("href", url);
                        link.setAttribute("download", fileName);
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    } else {
                        const content = await zip.generateAsync({ type: 'blob' });
                        const url = URL.createObjectURL(content);
                        const link = document.createElement("a");
                        link.setAttribute("href", url);
                        link.setAttribute("download", `${symbol}_full_export.zip`);
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    }
                    
                    closeExportModal();
                } catch (e) {
                    console.error("Export failed:", e);
                    alert("Erreur lors de la génération de l'export : " + e.message);
                } finally {
                    btn.disabled = false;
                    btn.classList.remove('bg-blue-800');
                    btn.innerText = "Exporter";
                }
            }

            async function loadFinancials(symbol) {
                const tbody = document.getElementById('financials-tbody');
                const emptyMsg = document.getElementById('financials-empty');
                tbody.innerHTML = '';
                
                try {
                    const res = await fetch(`/api/financials/${symbol}`);
                    const data = await res.json();
                    
                    if (data.length === 0) {
                        emptyMsg.classList.remove('hidden');
                        return;
                    }
                    
                    emptyMsg.classList.add('hidden');
                    
                    data.forEach(row => {
                        const tr = document.createElement('tr');
                        tr.className = "hover:bg-slate-800/20";
                        
                        tr.innerHTML = `
                            <td class="py-2 px-3 font-medium">${row.report_date}</td>
                            <td class="py-2 px-3 text-slate-400">${row.fiscal_period || 'N/A'}</td>
                            <td class="py-2 px-3 text-right">${row.revenue ? formatLargeNumber(row.revenue) : '-'}</td>
                            <td class="py-2 px-3 text-right ${row.net_income >= 0 ? 'text-emerald-400' : 'text-rose-400'}">${row.net_income ? formatLargeNumber(row.net_income) : '-'}</td>
                            <td class="py-2 px-3 text-right">${row.eps !== null ? row.eps.toFixed(2) : '-'}</td>
                            <td class="py-2 px-3 text-right">${row.cash ? formatLargeNumber(row.cash) : '-'}</td>
                            <td class="py-2 px-3 text-right">${row.operating_cf ? formatLargeNumber(row.operating_cf) : '-'}</td>
                            <td class="py-2 px-3 text-right font-semibold ${row.free_cash_flow >= 0 ? 'text-emerald-400' : 'text-rose-400'}">${row.free_cash_flow ? formatLargeNumber(row.free_cash_flow) : '-'}</td>
                        `;
                        tbody.appendChild(tr);
                    });
                } catch (e) {
                    console.error("Error loading financials:", e);
                    emptyMsg.classList.remove('hidden');
                }
            }

            function switchTab(tabId) {
                activeTab = tabId;
                
                const finBtn = document.getElementById('tab-financials-btn');
                const tabBtn = document.getElementById('tab-table-btn');
                const catBtn = document.getElementById('tab-catalog-btn');
                const sqlBtn = document.getElementById('tab-sql-btn');
                
                const finTab = document.getElementById('tab-financials');
                const tabTab = document.getElementById('tab-table');
                const catTab = document.getElementById('tab-catalog');
                const sqlTab = document.getElementById('tab-sql');
                
                const rowCountEl = document.getElementById('table-row-count');
                
                // Hide all tabs
                finTab.classList.add('hidden');
                tabTab.classList.add('hidden');
                catTab.classList.add('hidden');
                sqlTab.classList.add('hidden');
                rowCountEl.classList.add('hidden');
                
                finBtn.className = "text-sm font-medium text-slate-400 hover:text-slate-200 pb-2 pt-2 focus:outline-none";
                tabBtn.className = "text-sm font-medium text-slate-400 hover:text-slate-200 pb-2 pt-2 focus:outline-none";
                catBtn.className = "text-sm font-medium text-slate-400 hover:text-slate-200 pb-2 pt-2 focus:outline-none";
                sqlBtn.className = "text-sm font-medium text-slate-400 hover:text-slate-200 pb-2 pt-2 focus:outline-none";
                
                if (tabId === 'financials') {
                    finBtn.className = "text-sm font-medium border-b-2 border-blue-500 text-blue-500 pb-2 pt-2 focus:outline-none";
                    finTab.classList.remove('hidden');
                } else if (tabId === 'table') {
                    tabBtn.className = "text-sm font-medium border-b-2 border-blue-500 text-blue-500 pb-2 pt-2 focus:outline-none";
                    tabTab.classList.remove('hidden');
                    if (currentData.length > 0) rowCountEl.classList.remove('hidden');
                } else if (tabId === 'catalog') {
                    catBtn.className = "text-sm font-medium border-b-2 border-blue-500 text-blue-500 pb-2 pt-2 focus:outline-none";
                    catTab.classList.remove('hidden');
                } else if (tabId === 'sql') {
                    sqlBtn.className = "text-sm font-medium border-b-2 border-blue-500 text-blue-500 pb-2 pt-2 focus:outline-none";
                    sqlTab.classList.remove('hidden');
                }
            }

            function prefillSQL(query) {
                document.getElementById('sql-query-input').value = query.trim();
            }

            let sqlLastResult = null;

            async function runSqlQuery() {
                const query = document.getElementById('sql-query-input').value.trim();
                if (!query) {
                    alert("Veuillez saisir une requête SQL d'abord.");
                    return;
                }
                
                const emptyState = document.getElementById('sql-empty-state');
                const loadingState = document.getElementById('sql-loading-state');
                const resultContainer = document.getElementById('sql-result-container');
                const resultInfo = document.getElementById('sql-result-info');
                const thead = document.getElementById('sql-table-thead');
                const tbody = document.getElementById('sql-table-tbody');
                
                emptyState.classList.add('hidden');
                resultContainer.classList.add('hidden');
                loadingState.classList.remove('hidden');
                
                thead.innerHTML = '';
                tbody.innerHTML = '';
                sqlLastResult = null;
                
                const startTime = performance.now();
                
                try {
                    const res = await fetch('/api/sql', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ query: query })
                    });
                    
                    const data = await res.json();
                    
                    if (res.status !== 200) {
                        alert("Erreur SQL : " + (data.detail || "Erreur inconnue"));
                        emptyState.classList.remove('hidden');
                        loadingState.classList.add('hidden');
                        return;
                    }
                    
                    sqlLastResult = data;
                    const duration = ((performance.now() - startTime) / 1000).toFixed(3);
                    
                    let infoText = `${data.total_rows} lignes trouvées en ${duration}s.`;
                    if (data.truncated) {
                        infoText += ` (Affichage limité aux ${data.max_rows} premières lignes)`;
                    }
                    resultInfo.innerText = infoText;
                    
                    // Render headers
                    const trHead = document.createElement('tr');
                    trHead.className = "border-b border-slate-800 text-slate-400 font-semibold";
                    data.columns.forEach(col => {
                        const th = document.createElement('th');
                        th.className = "py-2 px-3";
                        th.innerText = col;
                        trHead.appendChild(th);
                    });
                    thead.appendChild(trHead);
                    
                    // Render body rows
                    if (data.rows.length === 0) {
                        const tr = document.createElement('tr');
                        const td = document.createElement('td');
                        td.className = "py-4 text-center text-slate-500 text-xs";
                        td.colSpan = data.columns.length || 1;
                        td.innerText = "Aucun résultat trouvé pour cette requête.";
                        tr.appendChild(td);
                        tbody.appendChild(tr);
                    } else {
                        data.rows.forEach(row => {
                            const tr = document.createElement('tr');
                            tr.className = "hover:bg-slate-800/20";
                            data.columns.forEach(col => {
                                const td = document.createElement('td');
                                td.className = "py-1.5 px-3 truncate max-w-[200px]";
                                td.innerText = row[col] !== null ? row[col] : 'NULL';
                                tr.appendChild(td);
                            });
                            tbody.appendChild(tr);
                        });
                    }
                    
                    loadingState.classList.add('hidden');
                    resultContainer.classList.remove('hidden');
                } catch (e) {
                    console.error("SQL query execution failed:", e);
                    alert("Erreur réseau ou d'exécution : " + e.message);
                    emptyState.classList.remove('hidden');
                    loadingState.classList.add('hidden');
                }
            }

            function downloadSQLResultCSV() {
                if (!sqlLastResult || !sqlLastResult.rows || sqlLastResult.rows.length === 0) {
                    alert("Aucun résultat à exporter.");
                    return;
                }
                const cols = sqlLastResult.columns;
                const rows = [cols.join(',')];
                
                sqlLastResult.rows.forEach(r => {
                    const rowVals = cols.map(c => {
                        let val = r[c];
                        if (val === null) return '';
                        val = String(val);
                        if (val.includes(',') || val.includes('"') || val.includes('\\n')) {
                            val = '"' + val.replace(/"/g, '""') + '"';
                        }
                        return val;
                    });
                    rows.push(rowVals.join(','));
                });
                
                const csvContent = rows.join('\\r\\n');
                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.setAttribute("href", url);
                link.setAttribute("download", `sql_query_result.csv`);
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }

            function formatLargeNumber(num) {
                if (Math.abs(num) >= 1.0e+12) {
                    return (num / 1.0e+12).toFixed(2) + " T";
                }
                if (Math.abs(num) >= 1.0e+9) {
                    return (num / 1.0e+9).toFixed(2) + " B";
                }
                if (Math.abs(num) >= 1.0e+6) {
                    return (num / 1.0e+6).toFixed(2) + " M";
                }
                if (Math.abs(num) >= 1.0e+3) {
                    return (num / 1.0e+3).toFixed(1) + " k";
                }
                return Number(num).toLocaleString();
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    print("Démarrage du OpenTick Data Explorer sur le port 8001...")
    uvicorn.run(app, host="127.0.0.1", port=8001)
