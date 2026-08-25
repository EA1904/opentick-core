"""
TradoVera Python SDK
--------------------
Un SDK léger et robuste pour permettre aux quants, data scientists et développeurs
d'interroger directement le Data Lake Parquet et la base de données SQLite catalog.db
en Python en une seule ligne de code pour le backtesting et la modélisation.
"""

import os
import sqlite3

import duckdb
import pandas as pd

from tvdata.config import DB_PATH, LAKE_ROOT
from tvdata.get import get_ohlcv as sdk_get_ohlcv
from tvdata.get import sql as sdk_sql


def get_ohlcv(
    symbol: str,
    timeframe: str = "D1",
    start: str = None,
    end: str = None,
    adjusted: bool = True,
) -> pd.DataFrame:
    """
    Récupère l'historique des prix OHLCV sous forme de DataFrame Pandas.
    Gère automatiquement les ajustements de splits et de dividendes si adjusted=True.
    """
    return sdk_get_ohlcv(
        symbol, timeframe=timeframe, start=start, end=end, adjusted=adjusted
    )


def sql_query(query: str) -> pd.DataFrame:
    """
    Exécute une requête SQL personnalisée via le moteur ultra-rapide DuckDB
    directement sur l'ensemble du Data Lake Parquet.
    """
    return sdk_sql(query)


def get_metadata(symbol: str = None) -> pd.DataFrame:
    """
    Récupère les informations descriptives des entreprises (Secteur, Industrie, MarketCap, etc.)
    depuis la base de données SQLite catalog.db.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Database de catalogue introuvable à l'emplacement : {DB_PATH}"
        )

    conn = sqlite3.connect(DB_PATH)
    try:
        if symbol:
            query = "SELECT * FROM symbols_metadata WHERE symbol = ?"
            df = pd.read_sql_query(query, conn, params=(symbol.upper(),))
        else:
            query = "SELECT * FROM symbols_metadata"
            df = pd.read_sql_query(query, conn)
        return df
    finally:
        conn.close()


def get_consolidated_dataset(
    symbol: str, start_date: str = None, end_date: str = None, adjusted: bool = True
) -> pd.DataFrame:
    """
    Génère un dataset daily unique consolidé (LEFT JOIN) associant :
      - Les prix quotidiens ajustés (OHLCV)
      - Les métadonnées de l'entreprise (Nom, Secteur, Capitalisation)
      - La volatilité réalisée Bloomberg (Realized_Vol_30D)
      - Les fondamentaux mensuels Bloomberg (PE Ratio, Price to Book, Beta, Sales)
      - Les rapports trimestriels Financials (Revenus, Net Income, EPS, Cash, FCF)

    Les dates sans publication mensuelle ou trimestrielle contiennent des valeurs NaN (Option brute).
    """
    symbol = symbol.upper()

    # 1. Fetch base OHLCV (Daily)
    df_ohlcv = get_ohlcv(
        symbol, timeframe="D1", start=start_date, end=end_date, adjusted=adjusted
    )
    if len(df_ohlcv) == 0:
        return pd.DataFrame()

    # Standardize index dates
    df_ohlcv["date_str"] = pd.to_datetime(df_ohlcv["timestamp"]).dt.strftime("%Y-%m-%d")

    # 2. Add static metadata
    meta_df = get_metadata(symbol)
    if not meta_df.empty:
        df_ohlcv["company_name"] = meta_df.iloc[0]["longname"]
        df_ohlcv["sector"] = meta_df.iloc[0]["sector"]
        df_ohlcv["industry"] = meta_df.iloc[0]["industry"]
        df_ohlcv["market_cap"] = meta_df.iloc[0]["marketcap"]
    else:
        df_ohlcv["company_name"] = ""
        df_ohlcv["sector"] = ""
        df_ohlcv["industry"] = ""
        df_ohlcv["market_cap"] = None

    # 3. DuckDB join
    db = duckdb.connect(database=":memory:")
    db.register("df_base", df_ohlcv)

    select_cols = [
        "df_base.date_str as date",
        "df_base.symbol",
        "df_base.company_name",
        "df_base.sector",
        "df_base.industry",
        "df_base.market_cap",
        "df_base.open",
        "df_base.high",
        "df_base.low",
        "df_base.close",
        "df_base.volume",
        "df_base.adj_factor",
    ]

    # Volatility join
    vol_path = os.path.join(LAKE_ROOT, "bloomberg", "volatility.parquet")
    vol_clause = ""
    if os.path.exists(vol_path):
        vol_clause = f"LEFT JOIN parquet_scan('{vol_path.replace(os.sep, '/')}') v ON df_base.date_str = strftime(v.DATE, '%Y-%m-%d') AND v.symbol = '{symbol}'"
        select_cols.append("v.Realized_Vol_30D as realized_vol_30d")

    # Fundamentals join
    funds_path = os.path.join(LAKE_ROOT, "bloomberg", "fundamentals.parquet")
    funds_clause = ""
    if os.path.exists(funds_path):
        funds_clause = f"LEFT JOIN parquet_scan('{funds_path.replace(os.sep, '/')}') f ON df_base.date_str = strftime(f.DATE, '%Y-%m-%d') AND f.symbol = '{symbol}'"
        select_cols.extend(
            [
                "f.Implied_Vol as implied_vol",
                "f.PE_Ratio as pe_ratio",
                "f.Price_to_Book as price_to_book",
                "f.Beta_Raw as beta_raw",
                "f.Sales as sales",
                "f.Beta_Adj as beta_adj",
            ]
        )

    # Financials join
    fin_path = os.path.join(LAKE_ROOT, "financials", "quarterly", f"{symbol}.parquet")
    fin_clause = ""
    if os.path.exists(fin_path):
        fin_clause = f"LEFT JOIN parquet_scan('{fin_path.replace(os.sep, '/')}') fi ON df_base.date_str = strftime(fi.report_date, '%Y-%m-%d')"
        select_cols.extend(
            ["fi.revenue", "fi.net_income", "fi.eps", "fi.cash", "fi.free_cash_flow"]
        )

    query = f"""
        SELECT 
            {", ".join(select_cols)}
        FROM df_base
        {vol_clause}
        {funds_clause}
        {fin_clause}
        ORDER BY df_base.date_str ASC
    """

    df_res = db.execute(query).df()
    db.close()
    return df_res
