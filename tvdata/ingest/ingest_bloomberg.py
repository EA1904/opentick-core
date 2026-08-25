import json
import os
import shutil
import sqlite3

import duckdb
import numpy as np
import pandas as pd

from tvdata.catalog import init_db, register_dataset
from tvdata.config import BLOOMBERG_DIR, DB_PATH, LAKE_ROOT, PROGRESS_FILE
from tvdata.ingest.stocks import write_parquet_hive


def write_progress(current, total, status, step_name="Bloomberg"):
    data = {
        "current": current,
        "total": total,
        "percent": int((current / total) * 100) if total > 0 else 0,
        "status": status,
        "step_name": step_name,
        "active": current < total,
    }
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print("Error writing progress:", e)


def main():
    print("==================================================")
    print("INGESTION DE LA BASE DE DONNÉES BLOOMBERG")
    print("==================================================")

    init_db()

    # 1. Ingestion des Métadonnées statiques
    meta_path = os.path.join(BLOOMBERG_DIR, "processed", "sp500_static_metadata.csv")
    if os.path.exists(meta_path):
        print("Importation des métadonnées Bloomberg...")
        write_progress(0, 100, "Importation des métadonnées statiques...", "Bloomberg")
        df_meta = pd.read_csv(meta_path)

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            for _, row in df_meta.iterrows():
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO symbols_metadata (symbol, longname, sector, industry, marketcap, exchange)
                    VALUES (?, ?, ?, ?, ?, 'US')
                """,
                    (
                        row["Symbol"].strip(),
                        row["Longname"],
                        row["Sector"],
                        row["Industry"],
                        row["Marketcap"],
                    ),
                )
            conn.commit()
            print(f"Métadonnées importées pour {len(df_meta)} symboles.")
        except Exception as e:
            print("Erreur import métadonnées:", e)
        finally:
            conn.close()
    else:
        print("Fichier métadonnées non trouvé.")

    # 2. Ingestion des Fondamentaux Mensuels Bloomberg
    funds_path = os.path.join(
        BLOOMBERG_DIR, "processed", "sp500_fundamentals_monthly.csv"
    )
    if os.path.exists(funds_path):
        print("Importation des fondamentaux mensuels...")
        write_progress(5, 100, "Importation des fondamentaux mensuels...", "Bloomberg")
        df_funds = pd.read_csv(funds_path)

        # Clean ticker
        df_funds["symbol"] = (
            df_funds["Ticker"].str.replace(" US Equity", "", regex=False).str.strip()
        )
        df_funds["DATE"] = pd.to_datetime(df_funds["DATE"])

        # Save to Parquet
        out_funds_dir = os.path.join(LAKE_ROOT, "bloomberg")
        os.makedirs(out_funds_dir, exist_ok=True)
        df_funds.to_parquet(
            os.path.join(out_funds_dir, "fundamentals.parquet"), compression="snappy"
        )
        print("Fondamentaux mensuels enregistrés.")
    else:
        print("Fichier fondamentaux non trouvé.")

    # 3. Ingestion de la Volatilité Daily Bloomberg
    vol_path = os.path.join(
        BLOOMBERG_DIR, "processed", "sp500_price_volatility_daily.csv"
    )
    if os.path.exists(vol_path):
        print("Importation de la volatilité daily Bloomberg...")
        write_progress(10, 100, "Importation de la volatilité daily...", "Bloomberg")
        df_vol = pd.read_csv(vol_path)

        # Clean ticker
        df_vol["symbol"] = (
            df_vol["Ticker"].str.replace(" US Equity", "", regex=False).str.strip()
        )
        df_vol["DATE"] = pd.to_datetime(df_vol["DATE"])

        # Save to Parquet
        out_vol_dir = os.path.join(LAKE_ROOT, "bloomberg")
        df_vol.to_parquet(
            os.path.join(out_vol_dir, "volatility.parquet"), compression="snappy"
        )
        print("Volatilité daily enregistrée.")
    else:
        print("Fichier volatilité non trouvé.")

    # 4. Ingestion des prix daily et fusion
    prices_path = os.path.join(BLOOMBERG_DIR, "golden", "prices_daily.csv")
    if not os.path.exists(prices_path):
        print("Fichier des prix daily Bloomberg introuvable.")
        write_progress(
            100,
            100,
            "Erreur: Fichier des prix daily Bloomberg introuvable.",
            "Bloomberg",
        )
        return

    print(
        "Chargement des prix daily Bloomberg (ceci peut prendre quelques secondes)..."
    )
    write_progress(15, 100, "Chargement des prix daily Bloomberg...", "Bloomberg")

    df_prices = pd.read_csv(prices_path)
    df_prices["Date"] = pd.to_datetime(df_prices["Date"])
    df_prices["Ticker"] = df_prices["Ticker"].str.strip()

    # Calculate adj_factor
    df_prices["adj_factor"] = np.where(
        df_prices["Close"] > 0, df_prices["Adj_Close"] / df_prices["Close"], 1.0
    )

    unique_tickers = df_prices["Ticker"].unique()
    total_tickers = len(unique_tickers)
    print(f"Total tickers Bloomberg à traiter : {total_tickers}")

    db_conn = duckdb.connect(database=":memory:")

    for idx, sym in enumerate(unique_tickers, 1):
        status_msg = f"Fusion Bloomberg pour {sym} ({idx}/{total_tickers})..."
        if idx % 10 == 0 or idx == total_tickers:
            print(status_msg)
            write_progress(
                15 + int((idx / total_tickers) * 80), 100, status_msg, "Bloomberg"
            )

        # Get Bloomberg data for this symbol
        bloom_sym_df = df_prices[df_prices["Ticker"] == sym].copy()

        # Map columns to standard format
        bloom_sym_df = bloom_sym_df.rename(
            columns={
                "Date": "timestamp",
                "Ticker": "symbol",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )

        bloom_sym_df["asset_class"] = "stocks"
        bloom_sym_df["timeframe"] = "D1"
        bloom_sym_df["year"] = bloom_sym_df["timestamp"].dt.year.astype("int32")

        # Reorder columns
        cols = [
            "timestamp",
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "adj_factor",
            "year",
            "asset_class",
            "timeframe",
        ]
        bloom_sym_df = bloom_sym_df[cols]

        # Load existing data from lake
        symbol_folder = os.path.join(
            LAKE_ROOT, "ohlcv", "asset_class=stocks", "timeframe=D1", f"symbol={sym}"
        )
        existing_df = pd.DataFrame()
        if os.path.exists(symbol_folder):
            try:
                existing_df = db_conn.execute(
                    f"SELECT * FROM parquet_scan('{symbol_folder.replace(os.sep, '/')}/*.parquet')"
                ).df()
            except Exception as e:
                print(f"Warning reading existing parquet for {sym}: {e}")

        bloomberg_min = bloom_sym_df["timestamp"].min()
        bloomberg_max = bloom_sym_df["timestamp"].max()

        if len(existing_df) > 0:
            existing_df["timestamp"] = pd.to_datetime(existing_df["timestamp"])
            # Filter out the overlap range to prefer Bloomberg data
            outside_range = existing_df[
                (existing_df["timestamp"] < bloomberg_min)
                | (existing_df["timestamp"] > bloomberg_max)
            ]
            merged_df = pd.concat([outside_range, bloom_sym_df], ignore_index=True)
        else:
            merged_df = bloom_sym_df

        # Sort and deduplicate
        merged_df = (
            merged_df.sort_values("timestamp")
            .drop_duplicates(subset=["timestamp"], keep="last")
            .reset_index(drop=True)
        )

        # Clear existing symbol files to avoid duplicate partitions or stale data
        if os.path.exists(symbol_folder):
            try:
                shutil.rmtree(symbol_folder)
            except Exception as e:
                print(f"Error removing old folder for {sym}: {e}")

        # Write merged data back
        write_parquet_hive(merged_df)

        # Register in SQLite catalog
        min_ts = merged_df["timestamp"].min()
        max_ts = merged_df["timestamp"].max()
        start_str = min_ts.strftime("%Y-%m-%d")
        end_str = max_ts.strftime("%Y-%m-%d")

        register_dataset(
            symbol=sym,
            timeframe="D1",
            asset_class="stocks",
            start_date=start_str,
            end_date=end_str,
            rows_count=len(merged_df),
            nulls_pct=0.0,
            quality_score=100.0,
            source="bloomberg_merged",
        )

    write_progress(
        100,
        100,
        f"Ingestion Bloomberg terminée avec succès. {total_tickers} symboles traités.",
        "Bloomberg",
    )
    print("Ingestion Bloomberg terminée avec succès !")


if __name__ == "__main__":
    main()
