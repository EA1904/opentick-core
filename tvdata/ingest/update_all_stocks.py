import os
import sqlite3
import time
import json
from datetime import datetime, timedelta
from tvdata.ingest.yfinance_connector import ingest_yfinance

from tvdata.config import DB_PATH, PROGRESS_FILE

def write_progress(current, total, status, step_name="Actualisation"):
    data = {
        "current": current,
        "total": total,
        "percent": int((current / total) * 100) if total > 0 else 0,
        "status": status,
        "step_name": step_name,
        "active": current < total
    }
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print("Error writing progress:", e)

def main():
    print("==================================================")
    print("ACTUALISATION DES COURS DE TOUTES LES ACTIONS (2022-2026)")
    print("==================================================")
    
    if not os.path.exists(DB_PATH):
        print(f"Catalog DB not found at: {DB_PATH}")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Get all stocks and their end dates
        query = """
            SELECT symbol, end_date 
            FROM data_catalog 
            WHERE asset_class = 'stocks' AND timeframe = 'D1' AND rows_count > 0
            ORDER BY symbol
        """
        rows = cursor.execute(query).fetchall()
        stocks = [(r[0], r[1]) for r in rows]
    except Exception as e:
        print("Error fetching stock end dates:", e)
        return
    finally:
        conn.close()
        
    total = len(stocks)
    print(f"Nombre de symboles à vérifier : {total}")
    
    today_dt = datetime.now()
    today_str = today_dt.strftime("%Y-%m-%d")
    
    success_count = 0
    skipped_count = 0
    failure_count = 0
    
    write_progress(0, total, "Démarrage de l'actualisation...", "Actualisation")
    
    for idx, (sym, last_date) in enumerate(stocks, 1):
        status_msg = f"Vérification / Actualisation de {sym} ({idx}/{total})..."
        print(f"\n[{idx}/{total}] {status_msg}")
        write_progress(idx - 1, total, status_msg, "Actualisation")
        
        try:
            # Parse last date
            if last_date.strip() == "" or last_date == "N/A":
                # Fallback start date if not catalogued
                start_date = "2022-01-01"
            else:
                last_dt = datetime.strptime(last_date[:10], "%Y-%m-%d")
                # Start from the next day
                start_dt = last_dt + timedelta(days=1)
                start_date = start_dt.strftime("%Y-%m-%d")
                
            # If the next day is already today or in the future, skip
            if start_dt >= today_dt:
                print(f"[{idx}/{total}] {sym} est déjà à jour (dernière date: {last_date[:10]}).")
                skipped_count += 1
                continue
                
            res = ingest_yfinance(
                symbol=sym,
                timeframe="D1",
                start_date=start_date,
                end_date=today_str,
                asset_class="stocks"
            )
            if res and res.get('rows', 0) > 0:
                success_count += 1
            else:
                skipped_count += 1
        except Exception as e:
            print(f"Échec de l'actualisation pour {sym}: {e}")
            failure_count += 1
            
        time.sleep(0.2)
        
    write_progress(total, total, f"Actualisation terminée. Succès: {success_count}, Ignorés: {skipped_count}, Échecs: {failure_count}", "Actualisation")
    
    print("\n==================================================")
    print("RÉSULTAT DE L'ACTUALISATION:")
    print(f"Total vérifié : {total}")
    print(f"Actualisés avec succès : {success_count}")
    print(f"Déjà à jour / Sans nouvelles données : {skipped_count}")
    print(f"Échecs : {failure_count}")
    print("==================================================")

if __name__ == "__main__":
    main()
