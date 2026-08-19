# OpenTick — Architecture Technique

## Vue d'ensemble

OpenTick repose sur 4 principes fondamentaux :

1. **UTC Strict** — Tous les timestamps sont normalisés en UTC naïf à l'ingestion
2. **Hive Partitioning** — Le lake Parquet est partitionné par `asset_class/timeframe/symbol`
3. **Asof Joins** — Les données fondamentales (rapports trimestriels) sont jointes aux cours via `pd.merge_asof` backward
4. **Séparation Code/Données** — Le code (`opentick-core/`) et les données (`opentick-data/`) sont indépendants

## Data Lake Structure

```
lake/
├── ohlcv/
│   ├── asset_class=stocks/
│   │   ├── timeframe=D1/
│   │   │   ├── symbol=AAPL/
│   │   │   │   └── data.parquet
│   │   │   └── symbol=MSFT/
│   │   └── timeframe=M15/
│   ├── asset_class=forex/
│   ├── asset_class=crypto/
│   └── asset_class=macro/
├── financials/quarterly/
├── volatility/
├── bloomberg/
└── options/
```

## Décisions Critiques

### 1. UTC Normalization
```python
def to_utc_naive(series, source_tz):
    if series.dt.tz is None:
        return series.dt.tz_localize(source_tz).dt.tz_convert('UTC').dt.tz_localize(None)
    return series.dt.tz_convert('UTC').dt.tz_localize(None)
```

### 2. DuckDB Hive Partitioning
```python
# Narrow scan to specific symbol partition — sub-10ms per query
path = f"lake/ohlcv/asset_class=stocks/timeframe=D1/symbol={symbol}/**/*.parquet"
df = duckdb.sql(f"SELECT * FROM parquet_scan('{path}') ORDER BY timestamp").df()
```

### 3. Asof Join pour les données fondamentales
```python
# Financials are published on weekends — exact date join drops them all
# Use merge_asof backward to carry forward the latest available report
df_financials = df_financials.sort_values("date").ffill()
result = pd.merge_asof(
    df_ohlcv.sort_values("date"),
    df_financials.sort_values("date"),
    on="date", direction="backward"
)
```

### 4. Séparation Code/Données via OPENTICK_DATA_ROOT
```python
# tvdata/config.py
DATA_ROOT = os.environ.get("OPENTICK_DATA_ROOT", WORKSPACE_ROOT)
LAKE_ROOT = os.path.join(DATA_ROOT, "lake")
DB_PATH   = os.path.join(DATA_ROOT, "catalog.db")
```

## Catalogue SQLite (`catalog.db`)

Tables principales :
- `data_catalog` — Métadonnées par série (symbol, timeframe, start/end date, rows_count, quality_score)
- `symbols_metadata` — Informations entreprises (sector, industry, marketcap, longname...)
- `historical_sp500_tickers` — Constituants historiques S&P 500

## Qualité des Données

Chaque série dispose d'un `quality_score` (0-100) calculé sur :
- % de valeurs nulles (`nulls_pct`)
- Continuité des dates (gaps détectés)
- Cohérence OHLCV (high >= low, close dans [low, high])
