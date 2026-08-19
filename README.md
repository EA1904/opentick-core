<div align="center">

<img src="https://img.shields.io/badge/OpenTick-Core-10b981?style=for-the-badge&logo=databricks&logoColor=white" alt="OpenTick Core"/>

# OpenTick Core — Financial Data Lake & Quant SDK

**Infrastructure de données financières open-source pour quants et traders algorithmiques.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![DuckDB](https://img.shields.io/badge/DuckDB-0.10+-FFC832?style=flat-square&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-10b981.svg?style=flat-square)](LICENSE)

</div>

---

## Qu'est-ce qu'OpenTick ?

OpenTick est un **Data Lake financier self-hosted** conçu pour centraliser, normaliser et exposer
des milliers de séries temporelles financières dans un seul environnement cohérent.

Contrairement aux solutions cloud coûteuses, OpenTick tourne **entièrement en local**, sans
dépendance à un service tiers, et donne un accès **sub-seconde** à toutes les données via DuckDB.

---

## Ce que contient le Data Lake

| Asset Class | Couverture | Timeframes | Symboles |
|-------------|-----------|------------|---------|
| **US Stocks** | 2022 → Aujourd'hui | D1, M15 | 503 S&P 500 complets |
| **Forex** | 2018 → Aujourd'hui | D1, H1, M15 | Majors & Crosses |
| **Crypto** | 2018 → Aujourd'hui | D1, H1, M15 | BTC, ETH, BNB... |
| **Macro FRED** | 1950 → Aujourd'hui | Variable | 845k+ séries |
| **Fondamentaux** | 2016 → Aujourd'hui | Trimestriel | 500+ sociétés |
| **Options** | 2019 → Aujourd'hui | EOD | SPY, QQQ, ETFs |
| **Volatilité** | 2022 → Aujourd'hui | D1 | Realized + Implied |

> **Total : 500+ symboles × 1000+ jours × plusieurs timeframes = plusieurs dizaines de Go de données.**

---

## SDK Python — Ce que vous pouvez faire

```python
from tvdata import get_ohlcv, get_macro, get_fundamentals, sql

# Stocks, Forex, Crypto — une ligne
aapl  = get_ohlcv("AAPL", "D1")           # Daily S&P 500
eurusd = get_ohlcv("EURUSD", "H1")        # Forex intraday
btc   = get_ohlcv("BTCUSDT", "D1")        # Crypto

# Multi-symboles — portefeuilles entiers
sp500 = get_ohlcv(["AAPL","MSFT","GOOGL","NVDA","META"], "D1")

# Données macro FRED — 845k séries disponibles
cpi    = get_macro("CPIAUCSL")   # Inflation CPI
rates  = get_macro("FEDFUNDS")   # Fed Funds Rate
spread = get_macro("T10Y2Y")     # Courbe des taux

# Fondamentaux — PE, P/B, EPS, Revenue, FCF...
funds = get_fundamentals("AAPL")

# SQL direct sur le Data Lake via DuckDB
df = sql("""
    SELECT symbol, timeframe, COUNT(*) as bars,
           MIN(timestamp) as debut, MAX(timestamp) as fin,
           AVG(volume) as vol_moyen
    FROM ohlcv
    WHERE asset_class = 'stocks' AND timeframe = 'D1'
    GROUP BY symbol, timeframe
    ORDER BY bars DESC
    LIMIT 20
""")
```

---

## Data Explorer — Interface Visuelle

Un Data Explorer interactif est intégré, accessible sur `http://localhost:8001` :

- **Recherche dynamique** de symboles (ex: tapez "Apple" → `AAPL - Apple Inc.`)
- **Graphiques OHLCV interactifs** (TradingView Lightweight Charts)
- **Onglet Catalogue** — vue d'ensemble de toutes les séries (dates, qualité, nombre de barres)
- **Onglet SQL** — requêtes DuckDB directes sur le Data Lake
- **Export CSV** consolidé (OHLCV + fondamentaux forward-fillés)
- **Actualisation EOD** automatique en arrière-plan

---

## Intégration avec l'écosystème Quant

```python
# Backtrader — backtesting
import backtrader as bt
cerebro = bt.Cerebro()
cerebro.adddata(bt.feeds.PandasData(dataname=get_ohlcv("SPY", "D1")))
cerebro.run()

# QuantStats — rapport de performance complet
import quantstats as qs
returns = get_ohlcv("SPY", "D1")["close"].pct_change().dropna()
qs.reports.html(returns, benchmark="SPY", output="report.html")

# PyPortfolioOpt — optimisation de portefeuille Markowitz
from pypfopt import EfficientFrontier, expected_returns, risk_models
prices = get_ohlcv(["AAPL","MSFT","GOOGL","NVDA"], "D1").pivot(
    index="timestamp", columns="symbol", values="adj_close"
)
weights = EfficientFrontier(
    expected_returns.mean_historical_return(prices),
    risk_models.CovarianceShrinkage(prices).ledoit_wolf()
).max_sharpe()

# Scikit-learn / ML — features prêtes à l'emploi
from tvdata import sql
features = sql("""
    SELECT symbol, timestamp, close, volume,
           realized_vol_30d, implied_vol, pe_ratio, beta_adj,
           (close - LAG(close,20) OVER (PARTITION BY symbol ORDER BY timestamp))
           / LAG(close,20) OVER (PARTITION BY symbol ORDER BY timestamp) as momentum_20d
    FROM ohlcv_consolidated
    WHERE asset_class = 'stocks' AND timeframe = 'D1'
""")
```

---

## Architecture Technique

```
+----------------------------------------------------------+
|                   OpenTick Stack                         |
|                                                          |
|  +------------------+    +---------------------------+   |
|  |   Data Explorer  |    |    tvdata Python SDK      |   |
|  |  FastAPI + UI    |    |  get_ohlcv()  sql()       |   |
|  |  :8001           |    |  get_macro()  get_fund()  |   |
|  +--------+---------+    +-------------+-------------+   |
|           |                            |                  |
|           +----------------------------+                  |
|                          |                               |
|         +----------------v-----------------+             |
|         |         Apache Parquet           |             |
|         |    lake/ (Hive partitioning)     |             |
|         | asset_class / timeframe / symbol |             |
|         +----+----------+----------+-------+             |
|              |          |          |                     |
|           DuckDB    SQLite      Catalog                  |
|          (Queries)  (catalog.db) (metadata)              |
|                                                          |
|  +-------------------------------------------------------+|
|  | Yahoo Finance | Alpaca | Binance | FRED | SEC | Dolt  ||
|  +-------------------------------------------------------+|
+----------------------------------------------------------+
```

| Couche | Technologie | Choix Technique |
|--------|-------------|-----------------|
| Stockage | **Apache Parquet** | Columnar, compression 80% vs CSV |
| Requêtes | **DuckDB** | SQL analytique in-process, zéro serveur |
| Partitionnement | **Hive** | `asset_class/timeframe/symbol` — scan ciblé |
| Catalogue | **SQLite** | Métadonnées légères et portables |
| Timestamps | **UTC strict** | Tous les sources normalisées en UTC naïf |
| Joins fondamentaux | **merge_asof** | Forward-fill pour données trimestrielles |
| API | **FastAPI** | REST + WebSocket, Auth JWT |

---

## Connecteurs Disponibles

| Connecteur | Source | Données | Clé requise |
|------------|--------|---------|-------------|
| `yfinance_connector` | Yahoo Finance | OHLCV Stocks/ETF/Indices EOD | ❌ Gratuit |
| `alpaca_connector` | Alpaca Markets | Stocks/Crypto intraday | ✅ Gratuit |
| `binance_connector` | Binance REST | Crypto OHLCV toutes résolutions | ❌ Gratuit |
| `fred_connector` | FRED API | 845k+ séries macro | ✅ Gratuit |
| `sec_connector` | SEC EDGAR XBRL | Bilans, P&L, Cash Flow | ❌ Gratuit |
| `dolt_connector` | DoltHub | Options, Earnings | ❌ Gratuit |
| `metatrader` | MT4/MT5 | Forex/CFD historiques | ✅ Broker |
| `ingest_bloomberg` | Bloomberg Terminal | Fondamentaux propriétaires | ✅ Payant |

---

## Qualité des Données

Chaque série du catalogue dispose d'un **quality score** (0-100) calculé automatiquement :

- % de valeurs nulles par colonne
- Détection des gaps et discontinuités
- Cohérence OHLCV (high ≥ low, close ∈ [low, high])
- Couverture temporelle vs calendrier boursier

```python
from tvdata import sql

# Voir la qualité de toutes les séries
quality = sql("""
    SELECT symbol, timeframe, rows_count, quality_score,
           start_date, end_date
    FROM data_catalog
    WHERE quality_score < 90
    ORDER BY quality_score ASC
""")
```

---

## Obtenir Accès au Data Lake Complet

> Ce repository contient le **code source** (SDK + Data Explorer).
> Le Data Lake complet (~22 Go de données historiques) est distribué séparément.

**Pour obtenir l'environnement complet avec les données :**

📧 **Contactez-moi** via [GitHub Issues](https://github.com/EA1904/opentick-core/issues)
ou directement sur mon profil GitHub **[@EA1904](https://github.com/EA1904)**.

---

## Contribuer

Les contributions au SDK et aux connecteurs sont les bienvenues :

1. Fork le repo
2. Créez votre branche : `git checkout -b feat/ma-contribution`
3. Committez : `git commit -m 'feat: description'`
4. Pushez : `git push origin feat/ma-contribution`
5. Ouvrez une Pull Request

---

## Disclaimer

> Ce projet est fourni à des fins de **recherche et d'éducation uniquement**.
> OpenTick est une infrastructure de données. Il ne constitue pas un conseil financier.
> Vérifiez toujours l'exactitude des données avant toute décision d'investissement.

---

## Licence

MIT — Voir [LICENSE](LICENSE).

---

<div align="center">

**OpenTick Core — Open-source. Self-hosted. Libre.**

*Construit pour les quants, data scientists et traders algorithmiques.*

**[@EA1904](https://github.com/EA1904)**

</div>
