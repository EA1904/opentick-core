import json
import os
import sqlite3
import time

from tvdata.config import DB_PATH, PROGRESS_FILE
from tvdata.ingest.yfinance_connector import ingest_yfinance


def write_progress(current, total, status, step_name="Importation"):
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
    print("IMPORTATION DES SYMBOLS S&P 500 MANQUANTS")
    print("==================================================")

    if not os.path.exists(DB_PATH):
        print(f"Catalog DB not found at: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Get symbols that are in historical_sp500_tickers but don't have active rows in data_catalog
        query = """
            SELECT symbol FROM historical_sp500_tickers
            WHERE symbol NOT IN (
                SELECT DISTINCT symbol FROM data_catalog 
                WHERE asset_class = 'stocks' AND rows_count > 0
            )
            ORDER BY symbol
        """
        rows = cursor.execute(query).fetchall()
        missing_symbols = [r[0] for r in rows]
    except Exception as e:
        print("Error fetching missing symbols:", e)
        return
    finally:
        conn.close()

    total = len(missing_symbols)
    print(f"Nombre total de symboles historiques S&P 500 manquants : {total}")

    if total == 0:
        print("Toutes les actions historiques sont déjà importées ! Rien à faire.")
        write_progress(
            100,
            100,
            "Toutes les actions historiques sont déjà importées !",
            "Importation",
        )
        return

    # We will fetch D1 daily data from 1996-01-02 to 2026-08-16
    start_date = "1996-01-02"
    end_date = "2026-08-16"

    success_count = 0
    failure_count = 0

    write_progress(0, total, "Démarrage de l'importation...", "Importation")

    for idx, sym in enumerate(missing_symbols, 1):
        status_msg = f"Ingestion de {sym} ({idx}/{total})..."
        print(f"\n[{idx}/{total}] {status_msg}")
        write_progress(idx - 1, total, status_msg, "Importation")

        try:
            # We call ingest_yfinance to handle download, save & catalog entry
            res = ingest_yfinance(
                symbol=sym,
                timeframe="D1",
                start_date=start_date,
                end_date=end_date,
                asset_class="stocks",
            )
            if res and res.get("rows", 0) > 0:
                success_count += 1
            else:
                failure_count += 1
        except Exception as e:
            print(f"Échec de l'ingestion pour {sym}: {e}")
            failure_count += 1

        # Tiny delay to avoid rate limiting
        time.sleep(0.2)

    write_progress(
        total,
        total,
        f"Importation terminée. Succès: {success_count}, Échecs: {failure_count}",
        "Importation",
    )

    print("\n==================================================")
    print("RÉSULTAT DE L'IMPORTATION:")
    print(f"Total à traiter : {total}")
    print(f"Importés avec succès : {success_count}")
    print(f"Échecs / Sans données : {failure_count}")
    print("==================================================")


if __name__ == "__main__":
    main()
