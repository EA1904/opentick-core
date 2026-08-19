import os
import io
import subprocess
import pandas as pd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from tvdata.catalog import register_dataset, init_db
from tvdata.config import LAKE_ROOT

# Executable path
DOLT_PATH = r"C:\Program Files\Dolt\bin\dolt.exe"

def query_dolt(repo_path: str, query: str) -> pd.DataFrame:
    """Run a SQL query against a local cloned Dolt repo and return a pandas DataFrame."""
    if not os.path.exists(repo_path):
        raise FileNotFoundError(f"Dolt repository path does not exist: {repo_path}")
        
    cmd = [DOLT_PATH, "sql", "-q", query, "-r", "csv"]
    
    try:
        res = subprocess.run(cmd, cwd=repo_path, check=True, capture_output=True, text=True, encoding='utf-8')
        if not res.stdout.strip():
            return pd.DataFrame()
        return pd.read_csv(io.StringIO(res.stdout))
    except subprocess.CalledProcessError as e:
        print(f"Error executing SQL in {repo_path}: {e.stderr}")
        raise e

def ingest_dolt_rates(rates_repo_path: str):
    """
    Ingest US treasury rates into lake/macro/yield_curve.parquet.
    """
    print(f"Ingesting yield curve rates from Dolt: {rates_repo_path}")
    query = """
        SELECT date, 3_month, 2_year, 10_year, 30_year 
        FROM us_treasury
        ORDER BY date
    """
    df = query_dolt(rates_repo_path, query)
    if len(df) == 0:
        print("No rates data found.")
        return
        
    # Standardize columns
    df = df.rename(columns={
        'date': 'timestamp',
        '3_month': 't_bill_3m',
        '2_year': 't_note_2y',
        '10_year': 't_note_10y',
        '30_year': 't_bond_30y'
    })
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Calculate spread
    df['yield_spread_2_10'] = df['t_note_10y'] - df['t_note_2y']
    
    # Save as parquet
    dest_dir = os.path.join(LAKE_ROOT, "macro")
    os.makedirs(dest_dir, exist_ok=True)
    df.to_parquet(os.path.join(dest_dir, "yield_curve.parquet"), index=False)
    
    # Register in catalog
    init_db()
    register_dataset(
        symbol="US_YIELD_CURVE",
        timeframe="D1",
        asset_class="macro",
        start_date=df['timestamp'].min().strftime('%Y-%m-%d'),
        end_date=df['timestamp'].max().strftime('%Y-%m-%d'),
        rows_count=len(df),
        nulls_pct=0.0,
        quality_score=100.0,
        source="dolt_rates"
    )
    print("Successfully ingested rates into yield_curve.parquet.")

def ingest_dolt_corporate_actions(stocks_repo_path: str):
    """
    Ingest splits and dividends history into lake/corporate_actions.parquet.
    """
    print(f"Ingesting corporate actions (splits & dividends) from Dolt: {stocks_repo_path}")
    
    # 1. Fetch splits
    split_query = "SELECT act_symbol as symbol, ex_date as date, to_factor, for_factor FROM split"
    df_splits = query_dolt(stocks_repo_path, split_query)
    
    if len(df_splits) > 0:
        df_splits['action_type'] = "split"
        df_splits['split_factor'] = df_splits['to_factor'] / df_splits['for_factor']
        df_splits['dividend_amount'] = 0.0
        df_splits = df_splits.drop(columns=['to_factor', 'for_factor'])
    else:
        df_splits = pd.DataFrame(columns=['symbol', 'date', 'action_type', 'split_factor', 'dividend_amount'])
        
    # 2. Fetch dividends
    div_query = "SELECT act_symbol as symbol, ex_date as date, amount as dividend_amount FROM dividend"
    df_divs = query_dolt(stocks_repo_path, div_query)
    
    if len(df_divs) > 0:
        df_divs['action_type'] = "dividend"
        df_divs['split_factor'] = 1.0
    else:
        df_divs = pd.DataFrame(columns=['symbol', 'date', 'action_type', 'split_factor', 'dividend_amount'])
        
    # Combine both
    df_actions = pd.concat([df_splits, df_divs], ignore_index=True)
    if len(df_actions) == 0:
        print("No corporate actions found.")
        return
        
    df_actions['date'] = pd.to_datetime(df_actions['date'])
    df_actions = df_actions.sort_values(by=['symbol', 'date'])
    
    # Save as parquet
    dest_dir = LAKE_ROOT
    os.makedirs(dest_dir, exist_ok=True)
    df_actions.to_parquet(os.path.join(dest_dir, "corporate_actions.parquet"), index=False)
    
    print(f"Successfully ingested {len(df_actions)} corporate actions.")

def ingest_dolt_earnings(earnings_repo_path: str):
    """
    Ingest financial statements from Dolt earnings database.
    Writes one Parquet file per ticker in lake/financials/quarterly/{symbol}.parquet.
    """
    print(f"Ingesting financials from Dolt: {earnings_repo_path}")
    
    # Correct columns for Dolt earnings tables
    query = """
        SELECT i.act_symbol as symbol, i.date as report_date, i.period as fiscal_period,
               i.sales as revenue, i.net_income, i.diluted_net_eps as eps,
               a.total_assets, l.total_liabilities, e.total_equity as equity,
               a.cash_and_equivalents as cash, l.long_term_debt as total_debt,
               c.net_change_in_cash_and_equivalents as net_change_cash,
               c.net_cash_from_operating_activities as operating_cf,
               c.property_and_equipment as capex
        FROM income_statement i
        LEFT JOIN balance_sheet_assets a ON i.act_symbol = a.act_symbol AND i.date = a.date AND i.period = a.period
        LEFT JOIN balance_sheet_liabilities l ON i.act_symbol = l.act_symbol AND i.date = l.date AND i.period = l.period
        LEFT JOIN balance_sheet_equity e ON i.act_symbol = e.act_symbol AND i.date = e.date AND i.period = e.period
        LEFT JOIN cash_flow_statement c ON i.act_symbol = c.act_symbol AND i.date = c.date AND i.period = c.period
    """
    
    df = query_dolt(earnings_repo_path, query)
    if len(df) == 0:
        print("No earnings statement data found.")
        return
        
    df['report_date'] = pd.to_datetime(df['report_date'])
    
    # Calculate Free Cash Flow (FCF = operating_cf - capex)
    # capex is usually positive in statements but could be negative, so we do standard subtraction
    df['free_cash_flow'] = df['operating_cf'] - df['capex'].abs().fillna(0.0)
    
    # Add consensus estimates and surprises from eps_history
    print("Enriching with eps history and consensus estimates...")
    est_query = """
        SELECT act_symbol as symbol, period_end_date as report_date, 
               estimate as eps_estimate, reported as actual_eps
        FROM eps_history
    """
    df_est = query_dolt(earnings_repo_path, est_query)
    
    if len(df_est) > 0:
        df_est['report_date'] = pd.to_datetime(df_est['report_date'])
        df_est['eps_surprise'] = df_est['actual_eps'] - df_est['eps_estimate']
        # Join estimates
        df = df.merge(df_est, on=['symbol', 'report_date'], how='left')
    else:
        df['eps_estimate'] = np.nan
        df['actual_eps'] = np.nan
        df['eps_surprise'] = np.nan
        
    # Write quarterly parquets
    dest_dir = os.path.join(LAKE_ROOT, "financials", "quarterly")
    os.makedirs(dest_dir, exist_ok=True)
    
    count = 0
    for symbol, group in df.groupby('symbol'):
        group_path = os.path.join(dest_dir, f"{symbol}.parquet")
        group = group.sort_values(by='report_date')
        group.to_parquet(group_path, index=False)
        count += 1
        
    print(f"Successfully ingested quarterly financials for {count} symbols.")

def ingest_dolt_options(options_repo_path: str):
    """
    Ingest option chain and volatility history from Dolt options database.
    Option chain is written per ticker in lake/options/{symbol}.parquet.
    Volatility history is written to lake/volatility/options_vol.parquet.
    """
    print(f"Ingesting options data from Dolt: {options_repo_path}")
    
    # 1. Ingest volatility history
    print("Ingesting volatility history...")
    vol_query = "SELECT * FROM volatility_history"
    df_vol = query_dolt(options_repo_path, vol_query)
    
    if len(df_vol) > 0:
        df_vol = df_vol.rename(columns={
            'date': 'timestamp',
            'act_symbol': 'symbol'
        })
        df_vol['timestamp'] = pd.to_datetime(df_vol['timestamp'])
        
        dest_dir = os.path.join(LAKE_ROOT, "volatility")
        os.makedirs(dest_dir, exist_ok=True)
        df_vol.to_parquet(os.path.join(dest_dir, "options_vol.parquet"), index=False)
        print("Successfully ingested volatility history.")
    else:
        print("No volatility history data found.")
        
    # 2. Ingest option chain
    print("Ingesting option chain ticker-by-ticker...")
    dest_dir = os.path.join(LAKE_ROOT, "options")
    os.makedirs(dest_dir, exist_ok=True)
    
    # Get distinct symbols first
    try:
        symbols_df = query_dolt(options_repo_path, "SELECT DISTINCT act_symbol FROM option_chain")
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return
        
    if len(symbols_df) == 0:
        print("No symbols found in option_chain.")
        return
        
    symbols = symbols_df['act_symbol'].dropna().unique()
    print(f"Found {len(symbols)} symbols in options database: {list(symbols)}")
    
    count = 0
    for symbol in symbols:
        print(f"Processing options for symbol: {symbol}...")
        try:
            symbol_query = f"SELECT * FROM option_chain WHERE act_symbol = '{symbol}'"
            df_symbol = query_dolt(options_repo_path, symbol_query)
            
            if len(df_symbol) > 0:
                df_symbol = df_symbol.rename(columns={
                    'date': 'timestamp',
                    'act_symbol': 'symbol'
                })
                df_symbol['timestamp'] = pd.to_datetime(df_symbol['timestamp'])
                
                group_path = os.path.join(dest_dir, f"{symbol}.parquet")
                df_symbol = df_symbol.sort_values(by=['timestamp', 'expiration', 'strike'])
                df_symbol.to_parquet(group_path, index=False)
                count += 1
                print(f"Successfully saved {symbol} options ({len(df_symbol):,} rows).")
            else:
                print(f"No option chain data found for symbol: {symbol}")
        except Exception as e:
            print(f"Error processing options for symbol {symbol}: {e}")
            
    print(f"Successfully ingested option chains for {count} symbols.")

