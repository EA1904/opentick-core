<div align="center">

<img src="https://img.shields.io/badge/OpenTick-Core-10b981?style=for-the-badge&logo=databricks&logoColor=white" alt="OpenTick Core"/>

# OpenTick Core — Financial Data Lake & Quant SDK

**Self-hosted, sub-millisecond financial data infrastructure for quantitative researchers and algorithmic traders.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![DuckDB](https://img.shields.io/badge/DuckDB-0.10+-FFC832?style=flat-square&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-10b981.svg?style=flat-square)](LICENSE)

</div>

---

## ⚡ What is OpenTick?

OpenTick is a **high-performance, local-first financial data lake** designed to consolidate, clean, and query massive historical market datasets without the overhead of cloud databases. 

By pairing **Apache Parquet (Hive partitioned)** with **DuckDB**, OpenTick delivers sub-millisecond query performance directly on raw files, making it the perfect backplane for backtesting, machine learning, and quantitative research.

---

## 🖥️ Interactive Data Explorer — Feature Walkthrough

The platform includes a built-in visual sandbox running on `http://localhost:8001` that allows you to inspect the health, coverage, and contents of your local data lake.

### 📈 1. High-Fidelity Interactive Charts
Visualize price action using official **TradingView-style interactive charts** featuring real-time candle metrics and volume overlays. Hovering over candles updates the metadata panel and header metrics instantly.

<p align="center">
  <img src="docs/assets/data_explorer_aapl.png" width="100%" style="border-radius: 12px; border: 1px solid #1e293b;" alt="Interactive TradingView Chart View"/>
</p>

### 🔍 2. Dynamic Real-Time Symbol Search
A custom search combobox filters through thousands of symbols in real time, matching tickers and company names instantly (`AAPL - Apple Inc.`, `MSFT - Microsoft Corp.`) for a seamless UX.

<p align="center">
  <img src="docs/assets/data_explorer_home.png" width="100%" style="border-radius: 12px; border: 1px solid #1e293b;" alt="Symbol Search Dashboard View"/>
</p>

### 💻 3. Embedded SQL Console (Powered by DuckDB)
Query the entire data lake with standard SQL. DuckDB reads directly from compressed Parquet files, allowing you to run analytical queries, filters, and aggregations with sub-millisecond execution times.

<p align="center">
  <img src="docs/assets/data_explorer_sql.png" width="100%" style="border-radius: 12px; border: 1px solid #1e293b;" alt="SQL Console View"/>
</p>

### 📊 4. Dataset Catalog & Quality Assurance
Inspect coverage dates, row counts, and auto-calculated **Quality Scores** (evaluating missing bars, null values, and OHLCV logical consistency) to ensure your data is production-ready.

<p align="center">
  <img src="docs/assets/data_explorer_catalog.png" width="100%" style="border-radius: 12px; border: 1px solid #1e293b;" alt="Data Catalog View"/>
</p>

---

## 🐍 Python Quant SDK

Read and query data directly in Python without running any database servers.

```python
from tvdata import get_ohlcv, get_macro, get_fundamentals, sql

# ─── Load OHLCV Data (Stocks, Forex, Crypto) ─────────────────────
# Returns clean Pandas DataFrames instantly
aapl_daily  = get_ohlcv("AAPL", "D1")     # Daily adjusted
aapl_1h     = get_ohlcv("AAPL", "1h")     # Hourly intraday
aapl_15m    = get_ohlcv("AAPL", "15m")    # 15-minute bars
btc_daily   = get_ohlcv("BTCUSDT", "D1")  # Crypto

# ─── Portfolio Loading ──────────────────────────────────────────
# Load multiple symbols simultaneously
portfolio = get_ohlcv(["AAPL", "MSFT", "GOOGL", "NVDA"], "D1")

# ─── Macroeconomic Series (FRED) ───────────────────────────────
cpi   = get_macro("CPIAUCSL")  # Consumer Price Index
rates = get_macro("FEDFUNDS")  # Effective Federal Funds Rate

# ─── Fundamental Metrics ────────────────────────────────────────
# EPS, PE Ratio, Revenue, Free Cash Flow, Debt/Equity, etc.
fundamentals = get_fundamentals("AAPL")

# ─── Direct High-Performance SQL ──────────────────────────────
# Leverage DuckDB for lightning-fast analysis
top_symbols = sql("""
    SELECT symbol, timeframe, COUNT(*) as bars,
           MIN(timestamp) as start_date, MAX(timestamp) as end_date
    FROM ohlcv
    WHERE asset_class = 'stocks' AND timeframe = 'D1'
    GROUP BY symbol, timeframe
    ORDER BY bars DESC
    LIMIT 10
""")
```

---

## ⚙️ Quant Ecosystem Integration

OpenTick interfaces natively with standard Python backtesting, optimization, and ML frameworks.

```python
# ─── Backtrader (Backtesting) ──────────────────────────────────
import backtrader as bt
cerebro = bt.Cerebro()
cerebro.adddata(bt.feeds.PandasData(dataname=get_ohlcv("SPY", "D1")))
cerebro.run()

# ─── QuantStats (Performance & Risk Analytics) ──────────────────
import quantstats as qs
returns = get_ohlcv("SPY", "D1")["close"].pct_change().dropna()
qs.reports.html(returns, benchmark="SPY", output="report.html")

# ─── PyPortfolioOpt (Portfolio Optimization) ───────────────────
from pypfopt import EfficientFrontier, expected_returns, risk_models
prices = get_ohlcv(["AAPL", "MSFT", "GOOGL", "NVDA"], "D1").pivot(
    index="timestamp", columns="symbol", values="adj_close"
)
mu = expected_returns.mean_historical_return(prices)
S  = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
weights = EfficientFrontier(mu, S).max_sharpe()

# ─── ML Feature Engineering ─────────────────────────────────────
# Calculate momentum, rolling volatility, and fundamentals on the fly
features = sql("""
    SELECT symbol, timestamp, close, volume,
           realized_vol_30d, implied_vol, pe_ratio, beta_adj,
           (close - LAG(close, 20) OVER (PARTITION BY symbol ORDER BY timestamp))
           / LAG(close, 20) OVER (PARTITION BY symbol ORDER BY timestamp) as momentum_20d
    FROM ohlcv_consolidated
    WHERE asset_class = 'stocks' AND timeframe = 'D1'
""")
```

---

## 📊 Data Coverage & Sources

OpenTick aggregates data from standard APIs and highly reliable, institutional-grade vendors. 

| Asset Class | Coverage | Timeframes | Source / Provider |
|-------------|-----------|------------|-------------------|
| **US Stocks** | 2022 → Today | D1, H1, 4H, M15, M1 | Public APIs & Licensed Market Feeds |
| **Forex** | 2018 → Today | D1, H1, M15 | Institutional Liquidity Providers |
| **Crypto** | 2018 → Today | D1, H1, M15 | Major Public Exchanges |
| **Macro Data** | 1950 → Today | Monthly / Qtr | FRED — Federal Reserve Bank (Public Domain) |
| **Corporate Filings** | 2016 → Today | Quarterly | SEC EDGAR XBRL (Public Domain) |
| **Fundamentals** | 2016 → Today | Quarterly | Selected Reliable Third-Party Providers |
| **Options** | 2019 → Today | EOD | Options Clearing Houses & End-of-Day Feeds |

---

## 🏗️ Technical Architecture

OpenTick stores data in columnar Parquet files on disk and runs queries in-process, bypassing the latency of client-server databases.

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
+----------------------------------------------------------+
```

- **Apache Parquet**: Columnar storage with Snappy compression (~80% space saving vs CSV).
- **DuckDB**: Fast, serverless analytical engine designed for SQL queries on columnar data.
- **Hive Partitioning**: `asset_class/timeframe/symbol` structure guarantees sub-10ms query execution times by pruning irrelevant directories before scanning.
- **SQLite Catalog**: Light, local registry storing data indices, symbol profiles, and data quality metrics.
- **Strict UTC Normalization**: Ingestion connectors enforce timezone normalization to ensure exact cross-asset timing alignment.

---

## 🔌 Available Connectors

Included out-of-the-box in the SDK:
- `alpaca_connector` — Intraday stock prices (requires free API key).
- `binance_connector` — Crypto OHLCV (no key required).
- `fred_connector` — Macroeconomic time series (requires free FRED API key).
- `sec_connector` — SEC EDGAR fundamentals parser.
- `dolt_connector` — Option chains and earnings datasets.
- `metatrader` — Institutional Forex history from MT4/MT5.
- `update_all_stocks` — Automatic daily EOD indexing script.

---

## 🤝 Contact & Collaboration

This repository contains the **core source code** (SDK, connectors, and Data Explorer UI). The historical dataset (~22 GB of pre-built Parquet files) is distributed separately.

### Get in Touch:
- 🗄️ **Get Data Lake Access**: Open an [Issue on GitHub](https://github.com/EA1904/opentick-core/issues) to request the historical data archive.
- 🤝 **Collaborate**: If you are a quantitative researcher, analyst, or developer looking to integrate OpenTick into your pipeline, reach out via my [GitHub Profile](https://github.com/EA1904).
- 🐛 **Contribute**: Feel free to submit a Pull Request or open an issue for connector upgrades and bug fixes.

---

## Disclaimer

> **For research and educational purposes only.** 
> OpenTick is a data infrastructure tool and does not constitute financial advice. Always verify data independently before risking capital. Data is fetched in compliance with API terms of service.

---

## License

MIT — See [LICENSE](LICENSE).

<div align="center">

**OpenTick Core — Open-Source. Local-First. Free.**

*Designed with ❤️ for quant researchers and system traders.*

**[@EA1904](https://github.com/EA1904)**

</div>
