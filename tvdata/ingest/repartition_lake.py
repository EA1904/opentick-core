import os
import shutil
import sqlite3
import pandas as pd
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from tvdata.config import DB_PATH, LAKE_ROOT as CONFIG_LAKE_ROOT
LAKE_ROOT = os.path.join(CONFIG_LAKE_ROOT, "ohlcv")

def main():
    print("==================================================")
    print("MIGRATION & PRUNING DU DATA LAKE PARQUET")
    print("==================================================")
    
    if not os.path.exists(LAKE_ROOT):
        print("Le dossier lake/ohlcv n'existe pas. Rien à migrer.")
        return
        
    # 1. Charger la liste des 1057 tickers historiques du S&P 500
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        rows = cursor.execute("SELECT symbol FROM historical_sp500_tickers").fetchall()
        sp500_tickers = {r[0].upper() for r in rows}
    except Exception as e:
        print("Erreur de lecture de la table historical_sp500_tickers. Avez-vous exécuté l'ingestion de la liste ?", e)
        return
    finally:
        conn.close()
        
    print(f"Nombre de tickers de référence S&P 500 chargés : {len(sp500_tickers)}")
    
    # 2. Utiliser DuckDB pour lire toutes les données existantes dans l'ancien format
    # et les réécrire partitionnées par symbol.
    temp_lake = os.path.join(CONFIG_LAKE_ROOT, "ohlcv_temp")
    os.makedirs(temp_lake, exist_ok=True)
    
    db_conn = duckdb.connect(database=':memory:')
    
    print("\nÉtape 1 : Lecture et filtrage des données existantes...")
    # On scanne récursivement tous les Parquet existants
    old_pattern = os.path.join(LAKE_ROOT, "**", "*.parquet").replace(os.sep, '/')
    
    try:
        # Lire les données existantes en gardant les colonnes de partition hive existantes
        df_all = db_conn.execute(f"SELECT * FROM parquet_scan('{old_pattern}', hive_partitioning=true)").df()
        print(f"Total des lignes chargées en mémoire : {len(df_all)}")
        
        if len(df_all) == 0:
            print("Aucune donnée trouvée dans le lac actuel.")
            return
            
        # 3. Filtrer : garder toutes les classes d'actifs autres que 'stocks',
        # et pour 'stocks' ne garder que les symboles de la liste S&P 500.
        print("\nÉtape 2 : Filtrage de l'univers S&P 500...")
        df_all['symbol'] = df_all['symbol'].str.upper()
        
        # Filtre
        mask = (df_all['asset_class'] != 'stocks') | (df_all['symbol'].isin(sp500_tickers))
        df_filtered = df_all[mask].copy()
        
        pruned_rows = len(df_all) - len(df_filtered)
        print(f"Lignes après filtrage : {len(df_filtered)}")
        print(f"Lignes supprimées (hors S&P 500) : {pruned_rows}")
        
        # S'assurer des types pour le partitionnement Hive
        df_filtered['asset_class'] = df_filtered['asset_class'].astype(str)
        df_filtered['timeframe'] = df_filtered['timeframe'].astype(str)
        df_filtered['symbol'] = df_filtered['symbol'].astype(str)
        df_filtered['year'] = df_filtered['year'].astype('int32')
        
        # 4. Écrire dans le répertoire temporaire partitionné par symbole
        print("\nÉtape 3 : Écriture du nouveau lac partitionné par symbole...")
        table = pa.Table.from_pandas(df_filtered, preserve_index=False)
        
        pq.write_to_dataset(
            table,
            root_path=temp_lake,
            partition_cols=['asset_class', 'timeframe', 'symbol', 'year'],
            compression='snappy',
            use_dictionary=True,
            row_group_size=100_000
        )
        print("Écriture terminée avec succès.")
        
        # 5. Remplacer l'ancien lac par le nouveau
        print("\nÉtape 4 : Remplacement de l'ancien lac par la nouvelle structure...")
        db_conn.close() # Libérer les verrous DuckDB
        
        # Supprimer l'ancien lac
        shutil.rmtree(LAKE_ROOT)
        # Renommer le temporaire
        os.rename(temp_lake, LAKE_ROOT)
        print("Remplacement effectué.")
        
        # 6. Nettoyer et ré-indexer le catalogue SQLite
        print("\nÉtape 5 : Mise à jour du catalogue SQLite...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Supprimer les stocks du catalogue qui ne sont pas dans le S&P 500 historique
        cursor.execute("""
            DELETE FROM data_catalog 
            WHERE asset_class = 'stocks' 
              AND symbol NOT IN (SELECT symbol FROM historical_sp500_tickers)
        """)
        conn.commit()
        
        # Mettre à jour le statut des lignes pour les symboles conservés
        # (Certains symboles peuvent avoir eu une réduction de lignes si des doublons ont été retirés)
        print("Recalcul des statistiques de lignes pour le catalogue...")
        db_conn = duckdb.connect(database=':memory:')
        new_pattern = os.path.join(LAKE_ROOT, "**", "*.parquet").replace(os.sep, '/')
        
        catalog_rows = db_conn.execute(f"""
            SELECT symbol, timeframe, asset_class, MIN(timestamp) as start_date, MAX(timestamp) as end_date, COUNT(*) as rows_count
            FROM parquet_scan('{new_pattern}', hive_partitioning=true)
            GROUP BY symbol, timeframe, asset_class
        """).fetchall()
        
        for row in catalog_rows:
            sym, tf, ac, s_date, e_date, count = row
            # Convert datetime to string
            s_date_str = str(s_date)[:10]
            e_date_str = str(e_date)[:10]
            
            cursor.execute("""
                UPDATE data_catalog 
                SET start_date = ?, end_date = ?, rows_count = ?
                WHERE symbol = ? AND timeframe = ? AND asset_class = ?
            """, (s_date_str, e_date_str, count, sym, tf, ac))
            
        conn.commit()
        conn.close()
        db_conn.close()
        
        print("\nMIGRATION TERMINÉE AVEC SUCCÈS ! Le lac est propre, optimisé et conforme.")
        
    except Exception as e:
        print("Erreur critique durant la migration :", e)
        # Nettoyage temp en cas d'échec
        if os.path.exists(temp_lake):
            shutil.rmtree(temp_lake)

if __name__ == "__main__":
    main()
