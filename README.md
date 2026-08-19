<div align="center">

<img src="https://img.shields.io/badge/OpenTick-Core-10b981?style=for-the-badge&logo=databricks&logoColor=white" alt="OpenTick"/>

# OpenTick Core — Financial Data Lake & Quant SDK

**Open-source financial data infrastructure for quants and algo traders.**
Self-hosted, free, deployable in one command.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![DuckDB](https://img.shields.io/badge/DuckDB-0.10+-FFC832?style=flat-square&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-10b981.svg?style=flat-square)](LICENSE)

</div>

---

## What is OpenTick?

OpenTick is an open-source **financial data lake** built for quantitative researchers and algorithmic traders.
It aggregates, normalizes, and exposes **500+ time series** — US stocks (S&P 500), Forex, Crypto, and macro data — into a high-performance Parquet lake with a built-in interactive Data Explorer UI.

### Key Features

| Feature | Details |
|---------|---------|
| Parquet Data Lake | Hive partitioning `asset_class / timeframe / symbol` — DuckDB sub-second queries |
| Data Explorer UI | Interactive web app with real-time charts, symbol search, CSV export |
| 5 Connectors | Yahoo Finance, Alpaca Markets, Binance, FRED API, SEC EDGAR |
| Auto-updater | Daily incremental EOD update, runs automatically |
| Docker 1-click | `docker compose -f docker-compose.core.yml up --build` |
| Python SDK | `from tvdata import get_ohlcv, get_macro, get_fundamentals` |

---

## Architecture

```
+--------------------------------------------+
|              OpenTick Core                 |
|                                            |
|  +----------------------------------+      |
|  |      Data Explorer UI :8001      |      |
|  |   FastAPI + Lightweight Charts   |      |
|  +----------------+-----------------+      |
|                   |                        |
|  +----------------v-----------------+      |
|       tvdata Python SDK                    |
|   get_ohlcv()  get_macro()  sql()          |
|  +----------------+-----------------+      |
|                   |                        |
|  +--------+  +----------+  +----------+   |
|  | Parquet|  |  DuckDB  |  |  SQLite  |   |
|  |  lake/ |  | (Queries)|  |catalog.db|   |
|  +--------+  +----------+  +----------+   |
|         ^                                 |
|  +------+----------------------------------+
|  | yfinance | Alpaca | Binance | FRED | SEC|
|  +------------------------------------------+
+--------------------------------------------+
```

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Git

### 1. Clone

```bash
git clone https://github.com/your-username/opentick-core.git
cd opentick-core
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set OPENTICK_DATA_ROOT to your data folder path
```

### 3. Run

```bash
docker compose -f docker-compose.core.yml up --build
```

### 4. Open

| Service | URL |
|---------|-----|
| Data Explorer | http://localhost:8001 |
| API Docs | http://localhost:8001/docs |

---

## Python SDK

```python
from tvdata import get_ohlcv, get_macro

# OHLCV — Stocks, Forex, Crypto
df = get_ohlcv("AAPL", "D1")                      # Daily adjusted
df = get_ohlcv("AAPL", "D1", adjusted=False)       # Raw prices (backtesting)
df = get_ohlcv("EURUSD", "H1")                     # Forex intraday
df = get_ohlcv(["AAPL", "MSFT", "GOOGL"], "D1")    # Multi-symbol

# Macro — FRED
cpi    = get_macro("CPIAUCSL")    # CPI Inflation
rates  = get_macro("FEDFUNDS")    # Fed Funds Rate
spread = get_macro("T10Y2Y")      # Yield Curve 10Y-2Y

# Direct DuckDB SQL
from tvdata import sql
df = sql("""
    SELECT symbol, COUNT(*) as bars
    FROM ohlcv WHERE asset_class = 'stocks' AND timeframe = 'D1'
    GROUP BY symbol ORDER BY bars DESC LIMIT 10
""")
```

### Backtesting / ML Integration

```python
# Backtrader
import backtrader as bt
cerebro = bt.Cerebro()
cerebro.adddata(bt.feeds.PandasData(dataname=get_ohlcv("AAPL", "D1")))
cerebro.run()

# QuantStats — Full performance report
import quantstats as qs
returns = get_ohlcv("SPY", "D1")["close"].pct_change().dropna()
qs.reports.html(returns, benchmark="SPY", output="report.html")

# PyPortfolioOpt — Portfolio optimization
from pypfopt import EfficientFrontier, expected_returns, risk_models
prices = get_ohlcv(["AAPL", "MSFT", "GOOGL"], "D1").pivot(
    index="timestamp", columns="symbol", values="adj_close"
)
weights = EfficientFrontier(
    expected_returns.mean_historical_return(prices),
    risk_models.CovarianceShrinkage(prices).ledoit_wolf()
).max_sharpe()
```

---

## Data Coverage

| Asset Class | Timeframes | Symbols | Coverage |
|-------------|-----------|---------|----------|
| US Stocks | D1, M15 | 503 S&P 500 | 2022 → Today |
| Forex | D1, H1, M15 | EUR, GBP, JPY... | 2018 → |
| Crypto | D1, H1, M15 | BTC, ETH, BNB... | 2018 → |
| Macro | Variable | 845k+ series | 1950 → |
| Fundamentals | Quarterly | 500+ companies | 2016 → |

---

## Manual Setup (No Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your OPENTICK_DATA_ROOT
uvicorn data_explorer:app --host 0.0.0.0 --port 8001 --reload
```

---

## Ingestion

```bash
# Daily EOD update — all S&P 500 stocks
python tvdata/ingest/update_all_stocks.py

# Single symbol
python tvdata/ingest/yfinance_connector.py --symbol AAPL --start 2022-01-01

# Crypto via Binance
python tvdata/ingest/binance_connector.py --symbol BTCUSDT --timeframe 1h

# Macro via FRED
python tvdata/ingest/fred_connector.py --series CPIAUCSL FEDFUNDS UNRATE
```

---

## Disclaimer

> **For research and educational purposes only.**
> OpenTick is a data infrastructure tool. It does not constitute financial advice.
> Always verify data accuracy before making investment decisions.

---

## Contributing

1. Fork the repository
2. Create your branch: `git checkout -b feat/my-feature`
3. Commit: `git commit -m 'feat: add my feature'`
4. Push: `git push origin feat/my-feature`
5. Open a **Pull Request**

---

## License

MIT — See [LICENSE](LICENSE).

---

<div align="center">

**OpenTick Core — Open-source. Self-hosted. Free.**

*Built for quantitative researchers and algorithmic traders.*

</div>
