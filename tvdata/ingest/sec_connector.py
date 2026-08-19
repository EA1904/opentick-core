import os
import json
import urllib.request
import pandas as pd
import numpy as np
from tvdata.ingest.fred_connector import load_env
from tvdata.config import LAKE_ROOT

def fetch_sec_json(url: str, user_agent: str) -> dict:
    """Fetch JSON from SEC EDGAR API with mandatory User-Agent, handles gzip decompression."""
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': user_agent,
            'Accept-Encoding': 'gzip, deflate'
        }
    )
    
    try:
        import requests
        res = requests.get(url, headers={'User-Agent': user_agent}, timeout=10)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 403:
            print(f"SEC API returned 403 Forbidden for URL: {url}. Please configure a-valid User-Agent.")
            return {}
        else:
            print(f"SEC API error {res.status_code} for URL: {url}")
            return {}
    except ImportError:
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                import gzip
                if response.info().get('Content-Encoding') == 'gzip':
                    data = gzip.decompress(response.read())
                else:
                    data = response.read()
                return json.loads(data.decode('utf-8'))
        except Exception as e:
            print(f"urllib error fetching from SEC: {e}")
            return {}

def get_cik_for_ticker(ticker: str, user_agent: str) -> str:
    """Get SEC 10-digit CIK for a ticker symbol."""
    ticker = ticker.upper()
    url = "https://www.sec.gov/files/company_tickers.json"
    data = fetch_sec_json(url, user_agent)
    if not data:
        return None
        
    for key, val in data.items():
        if val['ticker'] == ticker:
            return str(val['cik_str']).zfill(10)
    return None

def extract_fact(facts: dict, taxonomy: str, keys: list, form_types=['10-Q', '10-K']) -> dict:
    """Extract dict of {end_date: value} from SEC facts taxonomy check list."""
    tax_data = facts.get(taxonomy, {})
    for key in keys:
        if key in tax_data:
            unit_data = tax_data[key].get('units', {})
            for unit in unit_data:
                reports = unit_data[unit]
                # Filter to standard forms
                filtered = [r for r in reports if r.get('form') in form_types]
                if filtered:
                    # Return latest entries by end date to handle duplicate restatements
                    result = {}
                    for r in sorted(filtered, key=lambda x: x.get('end')):
                        result[r['end']] = r['val']
                    return result
    return {}

def ingest_sec_financials(symbol: str) -> dict:
    """
    Fetch quarterly financials from SEC EDGAR API, merge with existing Dolt financials,
    and save back to lake/financials/quarterly/{symbol}.parquet.
    """
    load_env()
    user_agent = os.environ.get('SEC_USER_AGENT')
    if not user_agent or "admin@tradovera.local" in user_agent and os.environ.get('FRED_API_KEY') == "your_fred_api_key_here":
        # Check if user agent is default placeholder
        user_agent = "TradoVeraDataLayer/1.0 admin@tradovera.local"
        
    cik = get_cik_for_ticker(symbol, user_agent)
    if not cik:
        print(f"Could not map ticker {symbol} to a CIK. Skipping SEC ingestion.")
        return {}
        
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    print(f"Fetching SEC facts for {symbol} (CIK: {cik})...")
    facts_raw = fetch_sec_json(url, user_agent)
    if not facts_raw or 'facts' not in facts_raw:
        print(f"No company facts found for {symbol}.")
        return {}
        
    facts = facts_raw['facts']
    
    # Check us-gaap and fallback to dei
    taxonomy = 'us-gaap'
    if 'us-gaap' not in facts:
        if 'dei' in facts:
            taxonomy = 'dei'
        else:
            print(f"No us-gaap or dei taxonomy found for {symbol}.")
            return {}
            
    # Extract keys
    rev_data = extract_fact(facts, taxonomy, ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet', 'SalesRevenueGoodsNet'])
    ni_data = extract_fact(facts, taxonomy, ['NetIncomeLoss'])
    eps_data = extract_fact(facts, taxonomy, ['EarningsPerShareDiluted'])
    assets_data = extract_fact(facts, taxonomy, ['Assets'])
    liab_data = extract_fact(facts, taxonomy, ['Liabilities'])
    eq_data = extract_fact(facts, taxonomy, ['StockholdersEquity'])
    cash_data = extract_fact(facts, taxonomy, ['CashAndCashEquivalentsAtCarryingValue'])
    debt_data = extract_fact(facts, taxonomy, ['LongTermDebtNoncurrent', 'LongTermDebt'])
    ocf_data = extract_fact(facts, taxonomy, ['NetCashProvidedByUsedInOperatingActivities'])
    capex_data = extract_fact(facts, taxonomy, ['PaymentsToAcquirePropertyPlantAndEquipment'])
    
    # Combine dates
    dates = set()
    for f in [rev_data, ni_data, eps_data, assets_data, liab_data, eq_data, cash_data, debt_data, ocf_data, capex_data]:
        dates.update(f.keys())
        
    if not dates:
        print(f"No financial report dates extracted for {symbol}.")
        return {}
        
    # Build list of rows
    rows = []
    for d in sorted(dates):
        rows.append({
            'symbol': symbol.upper(),
            'report_date': d,
            'fiscal_period': 'Q' if '-Q' in d else 'FY',  # Placeholder: parse from date if needed
            'revenue': rev_data.get(d),
            'net_income': ni_data.get(d),
            'eps': eps_data.get(d),
            'total_assets': assets_data.get(d),
            'total_liabilities': liab_data.get(d),
            'equity': eq_data.get(d),
            'cash': cash_data.get(d),
            'total_debt': debt_data.get(d),
            'operating_cf': ocf_data.get(d),
            'capex': capex_data.get(d)
        })
        
    df_new = pd.DataFrame(rows)
    df_new['report_date'] = pd.to_datetime(df_new['report_date'])
    
    # Convert numerical columns
    num_cols = ['revenue', 'net_income', 'eps', 'total_assets', 'total_liabilities', 'equity', 'cash', 'total_debt', 'operating_cf', 'capex']
    for col in num_cols:
        df_new[col] = pd.to_numeric(df_new[col], errors='coerce').astype('float64')
        
    df_new['free_cash_flow'] = df_new['operating_cf'] - df_new['capex'].abs().fillna(0.0)
    
    # Fill estimates with NaN to conform to the schema
    for col in ['eps_estimate', 'actual_eps', 'eps_surprise']:
        df_new[col] = np.nan
        
    # Sort and filter empty rows
    df_new = df_new.dropna(subset=['revenue', 'net_income', 'total_assets'], how='all')
    
    # Target file
    dest_dir = os.path.join(LAKE_ROOT, "financials", "quarterly")
    os.makedirs(dest_dir, exist_ok=True)
    dest_file = os.path.join(dest_dir, f"{symbol.upper()}.parquet")
    
    # Merge if exists
    if os.path.exists(dest_file):
        try:
            df_exist = pd.read_parquet(dest_file)
            df_exist['report_date'] = pd.to_datetime(df_exist['report_date'])
            # Combined
            df_combined = pd.concat([df_exist, df_new], ignore_index=True)
            # Remove duplicate report dates, keeping the latest one
            df_combined = df_combined.drop_duplicates(subset=['report_date'], keep='last')
            df_combined = df_combined.sort_values(by='report_date')
            df_combined.to_parquet(dest_file, index=False)
            print(f"Successfully merged SEC financials for {symbol}. Total rows: {len(df_combined)}")
            return {'symbol': symbol, 'rows': len(df_combined), 'status': 'merged'}
        except Exception as e:
            print(f"Error merging with existing financials for {symbol}: {e}. Writing new file.")
            
    df_new.to_parquet(dest_file, index=False)
    print(f"Successfully wrote SEC financials for {symbol}. Rows: {len(df_new)}")
    return {'symbol': symbol, 'rows': len(df_new), 'status': 'written'}
