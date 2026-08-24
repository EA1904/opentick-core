<div align="center">

<img src="https://img.shields.io/badge/OpenTick-Financial%20Data%20Lake-00D4AA?style=for-the-badge&logo=databricks&logoColor=white" alt="OpenTick"/>

# 🗄️ OpenTick — Financial Data Lake

**Your single source of truth for all trading data.**  
Self-hosted, portable, 100% free — deployed with a single `docker compose up`.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![DuckDB](https://img.shields.io/badge/DuckDB-0.10+-FFC832?style=flat-square&logo=duckdb&logoColor=black)](https://duckdb.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=flat-square&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

</div>

---

## 🤔 Why OpenTick?

As quants and data scientists, we were spending **more time cleaning and managing data infrastructure than building models**.

- **Free APIs** (Yahoo Finance) hit rate limits, have missing data, and break unpredictably
- **Professional terminals** (Bloomberg, Refinitiv) cost $20k+/year and restrict automation
- **Scattered sources** — price data here, fundamentals there, macro elsewhere — hours of wrangling before any analysis

**OpenTick solves this**: centralises 500+ time series (Prices, Fundamentals, Macro, Options) into a Parquet data lake with sub-second DuckDB queries, eliminating 90% of data wrangling before any backtest or model run.

---

## ✨ What is OpenTick?

OpenTick is a **full-stack financial data platform** designed for quants, data scientists, and algorithmic traders. It aggregates, normalises, and exposes 500+ US equities (S&P 500), Forex, Crypto, and macro time series in a **high-performance Parquet Data Lake**.

### 🔑 Key Features

| Feature | Detail |
|---|---|
| 📊 **Parquet Data Lake** | Hive partitioning `asset_class / timeframe / symbol` — sub-second DuckDB queries |
| 🌐 **Data Explorer UI** | Interactive web interface with real-time charts, symbol search, financial data, and CSV export |
| 🔌 **5 Connectors** | Yahoo Finance, Alpaca Markets, Binance, FRED API, SEC EDGAR |
| 🤖 **Auto-Updater** | Daily incremental End-of-Day price update — runs automatically |
| 🐳 **1-Click Docker** | Entire stack in a single `docker compose up --build` |
| 📦 **Python SDK** | `from tvdata import get_ohlcv, get_macro, get_fundamentals` |
| 🧮 **SQL Console** | DuckDB SQL directly on your Parquet lake from the browser |
| 📤 **Flexible Export** | CSV/ZIP export with custom date range, timeframe, and data type selection |

---

## 🖥️ Live Demo — NVDA (NVIDIA Corporation)

> All screenshots below are taken directly from a live, locally-running instance of OpenTick.

### Interactive Candlestick Chart — Full History 2022 → 2026

The Data Explorer loads any S&P 500 symbol with **split/dividend-adjusted prices**, interactive zoom, and volume bars. Here, NVDA's AI-driven rally from ~$12 to $225 is captured in full — **from AI boom to market leadership**.

![NVDA Full History Chart — OpenTick Data Explorer](Screens/1.png)

---

### Zoom on Recent Price Action — 2026

Drill into any period with the interactive chart. Daily Open/High/Low/Close candles with volume for NVDA's most recent trading sessions.

![NVDA 2026 Zoom — Daily Candlestick](Screens/3.png)

---

### Financial Data — Revenue, EPS, FCF (2013 → 2026)

The **Financial Data** tab exposes all quarterly and annual earnings pulled from SEC EDGAR and Bloomberg. Metrics include Revenue, Net Income, EPS, Cash, Operating Cash Flow, and Free Cash Flow — color-coded green for profit, red for loss.

![NVDA Financial Data Table](Screens/2.png)

Full financial history scrolled — watch NVIDIA's Revenue explode from **$4.28B (2013)** to **$215.94B (2026 Annual)** and Free Cash Flow reaching **$96.68B**:

![NVDA Financial Data — Full History 2013→2026](Screens/4.png)

---

### OHLCV Data Table — 2,926 Daily Bars with Metadata Sidebar

The **OHLCV Data (Table)** tab exposes raw price data rows up to the latest available date (**2026-08-21**). The sidebar shows:
- Company metadata: Sector **Technology**, Industry **Semiconductors**, Market Cap **$3.30T**
- Exchange: **US**
- Full **Business Summary** from yfinance (NVIDIA Corporation operates as a data center scale AI infrastructure company...)

![NVDA OHLCV Table + Metadata Sidebar](Screens/5.png)

---

### SQL Console — DuckDB Queries Directly on the Lake

Query your entire Parquet data lake with **raw DuckDB SQL** straight from the browser. No server, no ORM — direct columnar queries in milliseconds.

```sql
SELECT timestamp, open, high, low, close, volume
FROM ohlcv
WHERE symbol = 'AAPL' AND timeframe = 'D1'
ORDER BY timestamp DESC LIMIT 5;
```

![DuckDB SQL Console — OpenTick](Screens/6.png)

Pre-built query examples included: **OHLCV AAPL Daily**, **Top Tech by Market Cap**, **Bloomberg Volatility AAPL**, **Bloomberg Multiples AAPL**.

---

### Export Configuration — Granular Multi-Format Export

Click **Export to CSV** from any symbol view to open the Export Configuration modal. Fully configurable:

**Price Series Export:**
- Custom date range (e.g. 2015-01-02 → 2026-08-21 for NVDA)
- Format: **Single Consolidated CSV** or **Separate CSV files in ZIP**
- Timeframes: **15 Minutes**, **1 Hour**, **4 Hours**, **Daily (D1)**

![Export Configuration — Price Series](Screens/7.png)

**Fundamentals & Derivatives Export:**
- Financial statements: **Income Statement** (Revenue, EPS), **Balance Sheet** (Assets, Debt), **Cash Flow Statement** (FCF, Operating CF)
- **Option Volatility** — Historical HV / Implied IV from options
- **Corporate Actions** — Historical dividends and splits

![Export Configuration — Financials & Derivatives](Screens/8.png)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                       OpenTick Stack                             │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Frontend    │  │   Backend    │  │    Data Explorer     │  │
│  │  Next.js 14  │  │  FastAPI     │  │  FastAPI + HTML/JS   │  │
│  │  :3000       │  │  :8000       │  │  :8001               │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         └─────────────────┼──────────────────────┘              │
│                           │                                      │
│              ┌────────────▼─────────────┐                        │
│              │    tvdata Python SDK     │                        │
│              │  get_ohlcv()  sql()      │                        │
│              └──────────┬───────────────┘                        │
│                         │                                        │
│         ┌───────────────┼───────────────┐                        │
│         ▼               ▼               ▼                        │
│   ┌──────────┐   ┌──────────┐   ┌─────────────┐                 │
│   │  Parquet │   │  DuckDB  │   │   SQLite    │                 │
│   │  lake/   │   │ (Queries)│   │ catalog.db  │                 │
│   └──────────┘   └──────────┘   └─────────────┘                 │
│         ▲                                                        │
│   ┌─────┴────────────────────────────────────────┐               │
│   │  yfinance │ Alpaca │ Binance │ FRED │ SEC   │               │
│   └───────────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology | Role |
|--------|-------------|------|
| Storage | **Apache Parquet** | Columnar, 80% compression vs CSV |
| Queries | **DuckDB** | SQL on Parquet, zero server |
| Catalogue | **SQLite** | Lightweight, portable metadata |
| Relational DB | **TimescaleDB / PostgreSQL** | Time series + users |
| Cache | **Redis** | Sessions, WebSocket, queues |
| API | **FastAPI** | REST + WebSocket, JWT Auth |
| UI | **Next.js 14** | Trading Dashboard |
| Data Explorer | **FastAPI + HTML/JS** | Data Lake Visualisation |

---

## 📊 Data Coverage

| Asset Class | Timeframes | Symbols | Coverage | Source |
|-------------|-----------|----------|------------|--------|
| **US Stocks** | D1, 1H, 15m, 1m | 530 / 1,057 S&P 500 | 2015 → Today | Yahoo Finance + Alpaca |
| **Forex** | D1, H1, M15 | EUR, GBP, JPY... | 2018 → | Alpaca + MT4 CSV |
| **Crypto** | D1, H1, M15 | BTC, ETH, BNB... | 2018 → | Binance |
| **Macro** | Variable | 845k+ series | 1950 → | FRED API |
| **Fundamentals** | Quarterly/Annual | 500+ companies | 2013 → | SEC EDGAR + Bloomberg |
| **Options** | EOD | SPY, QQQ, ETFs | 2019 → | DoltHub |

> **530 symbols locally imported** out of 1,057 total S&P 500 tickers tracked. Each symbol contains OHLCV bars across multiple timeframes stored as Parquet partitions.

---

## 🚀 Quick Start (Docker — Recommended)

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows, macOS, Linux)
- Git

### 1. Clone the repository

```bash
git clone https://github.com/your-username/opentick.git
cd opentick
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your API keys (see section below)
```

### 3. Launch the full stack

```bash
docker compose up --build
```

> ⏱️ First launch may take 3–5 minutes to build Docker images.

### 4. Access the interfaces

| Service | URL | Description |
|---------|-----|-------------|
| 🖥️ **Data Explorer** | http://localhost:8001 | Data Lake Visualisation |
| ⚡ **API Backend** | http://localhost:8000 | OpenTick REST API |
| 🎨 **Frontend App** | http://localhost:3000 | Trading Dashboard |
| 📖 **API Docs** | http://localhost:8000/docs | Swagger / OpenAPI |

---

## ⚙️ API Keys Configuration

| Variable | Where to get it | Required for |
|----------|---------|-------------|
| `FRED_API_KEY` | [fred.stlouisfed.org](https://fred.stlouisfed.org/api_key.html) | Macro data (free) |
| `SEC_USER_AGENT` | Format: `"AppName/1.0 email@example.com"` | SEC EDGAR (free) |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | [alpaca.markets](https://alpaca.markets/) | Intraday stocks (free) |

> **Note:** Yahoo Finance and Binance require no API key.

---

## 📁 Project Structure

```
opentick/
│
├── 📄 docker-compose.yml       ← Full stack (DB, Redis, Backend, Frontend, Explorer)
├── 📄 .env.example             ← Environment variables template
├── 📄 requirements.txt         ← Python Data Layer dependencies
├── 🖥️ data_explorer.py         ← Data Explorer (FastAPI + UI on :8001)
├── 📋 catalog.db               ← SQLite catalogue (series metadata)
│
├── 🐍 tvdata/                  ← Python SDK (Data Lake)
│   ├── __init__.py             → get_ohlcv, get_macro, get_fundamentals, sql()
│   ├── config.py               → WORKSPACE_ROOT, LAKE_ROOT, DB_PATH (portable)
│   ├── get.py                  → Parquet read helpers via DuckDB
│   ├── catalog.py              → Catalogue management + stats recalculation
│   └── ingest/
│       ├── yfinance_connector.py    → Stocks EOD via Yahoo Finance
│       ├── alpaca_connector.py      → Stocks/Crypto Intraday via Alpaca
│       ├── binance_connector.py     → Crypto via Binance REST
│       ├── fred_connector.py        → Macro via FRED API (845k series)
│       ├── sec_connector.py         → Fundamentals via SEC EDGAR (XBRL)
│       ├── dolt_connector.py        → Options, Earnings via DoltHub
│       ├── ingest_bloomberg.py      → Bloomberg fundamentals CSV
│       ├── update_all_stocks.py     → Incremental S&P 500 update
│       └── updater.py               → Scheduled EOD auto-updater
│
├── 🗄️ lake/                    ← Parquet Data Lake (generated locally, not versioned)
│   └── ohlcv/
│       ├── asset_class=stocks/timeframe=D1/symbol=NVDA/...parquet
│       ├── asset_class=forex/timeframe=H1/...parquet
│       └── asset_class=crypto/timeframe=D1/...parquet
│
├── ⚡ backend/                 ← OpenTick REST API (FastAPI on :8000)
│   ├── Dockerfile
│   └── app/
│       ├── main.py
│       └── api/               → REST + WebSocket routes
│
└── 🎨 frontend/               ← Trading Dashboard (Next.js 14 on :3000)
    ├── Dockerfile
    └── app/
```

---

## 🐍 Python SDK — Usage

```python
from tvdata import get_ohlcv, get_macro, get_fundamentals

# ─── OHLCV Stocks ────────────────────────────────────────────────
df = get_ohlcv("NVDA", "D1")                     # Daily, adjusted prices
df = get_ohlcv("NVDA", "D1", adjusted=False)     # Raw prices (backtests)
df = get_ohlcv("EURUSD", "H1")                   # Forex intraday
df = get_ohlcv(["NVDA", "MSFT", "GOOGL"], "D1") # Multi-symbol

# ─── Macro FRED ──────────────────────────────────────────────────
cpi    = get_macro("CPIAUCSL")   # CPI Inflation
rates  = get_macro("FEDFUNDS")   # Fed Funds Rate
spread = get_macro("T10Y2Y")     # 10Y-2Y Yield Curve

# ─── DuckDB SQL Direct ──────────────────────────────────────────
from tvdata import sql
df = sql("""
    SELECT symbol, COUNT(*) as bars, MIN(timestamp) as start
    FROM ohlcv WHERE asset_class = 'stocks' AND timeframe = 'D1'
    GROUP BY symbol ORDER BY bars DESC LIMIT 10
""")
```

### Backtesting & ML Integration

```python
# Backtrader
import backtrader as bt
cerebro = bt.Cerebro()
cerebro.adddata(bt.feeds.PandasData(dataname=get_ohlcv("NVDA", "D1")))
cerebro.run()

# QuantStats — Full performance report
import quantstats as qs
returns = get_ohlcv("SPY", "D1")["close"].pct_change().dropna()
qs.reports.html(returns, benchmark="SPY", output="report.html")

# PyPortfolioOpt — Markowitz portfolio optimisation
from pypfopt import EfficientFrontier, expected_returns, risk_models
prices = get_ohlcv(["NVDA", "MSFT", "GOOGL", "AMZN"], "D1").pivot(
    index="timestamp", columns="symbol", values="adj_close"
)
mu = expected_returns.mean_historical_return(prices)
S  = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
weights = EfficientFrontier(mu, S).max_sharpe()
```

---

## 📡 Data Ingestion

### Via the Data Explorer (recommended)

From **http://localhost:8001**, click **"Refresh Database (EOD)"** to trigger the incremental update in the background.

### Manual scripts

```bash
# S&P 500 Stocks — Yahoo Finance
python tvdata/ingest/yfinance_connector.py --symbol NVDA --start 2015-01-01

# Intraday M15 — Alpaca
python tvdata/ingest/alpaca_connector.py --symbol NVDA --timeframe 15Min

# Crypto — Binance
python tvdata/ingest/binance_connector.py --symbol BTCUSDT --timeframe 1h

# Macro — FRED
python tvdata/ingest/fred_connector.py --series CPIAUCSL FEDFUNDS UNRATE
```

---

## 🔧 Manual Setup (Without Docker)

```bash
# 1. Python environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # Linux / macOS

# 2. Dependencies
pip install -r requirements.txt

# 3. Environment variables
cp .env.example .env

# 4. Launch the Data Explorer only
uvicorn data_explorer:app --host 0.0.0.0 --port 8001 --reload

# 5. Initial ingestion
python tvdata/ingest/yfinance_connector.py
python tvdata/ingest/ingest_bloomberg.py

# 6. Daily update
python tvdata/ingest/update_all_stocks.py
```

---

## 🧪 Tests

```bash
python test_pipeline.py      # End-to-end pipeline
python test_alpaca_m15.py    # Alpaca M15 intraday
pytest                       # Full test suite
```

---

## 📌 Important Notes

> **⚠️ Important:** The **Data Lake** (`lake/`) and `catalog.db` are generated locally and **not versioned** on Git. They are rebuilt via the ingestion scripts.

> **ℹ️ Note:** Bloomberg fundamental data requires the `Bloomberg/` folder with the corresponding CSV files at the project root.

> **💡 Tip:** On a fresh machine, full S&P 500 ingestion (530 symbols) takes approximately **30–60 minutes** depending on connection speed.

---

## 🤝 Contributing

Contributions are welcome!

1. **Fork** the repository
2. Create your branch: `git checkout -b feat/my-feature`
3. Commit: `git commit -m 'feat: add my feature'`
4. Push: `git push origin feat/my-feature`
5. Open a **Pull Request**

---

## 📄 License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file.

---

<div align="center">

**OpenTick Data Lake — Self-hosted, portable, 100% free.**

*Built with ❤️ for algorithmic traders and data scientists.*

</div>
