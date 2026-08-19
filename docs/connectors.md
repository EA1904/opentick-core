# OpenTick — Guide des Connecteurs

## yfinance (Yahoo Finance)

**Usage :** Stocks US, ETFs, Forex EOD, Indices

```python
from tvdata.ingest.yfinance_connector import ingest_yfinance

ingest_yfinance(
    symbols=["AAPL", "MSFT", "GOOGL"],
    start="2022-01-01",
    end="2024-12-31",
    timeframe="D1"
)
```

**Limites :** Gratuit, pas de clé requise. Rate limit ~2000 req/heure.

---

## Alpaca Markets

**Usage :** Stocks US intraday (M1, M5, M15, H1), Crypto

**Clé requise :** Compte gratuit sur [alpaca.markets](https://alpaca.markets/)

```env
ALPACA_API_KEY=votre_cle
ALPACA_SECRET_KEY=votre_secret
```

```python
from tvdata.ingest.alpaca_connector import ingest_alpaca

ingest_alpaca(
    symbol="AAPL",
    timeframe="15Min",
    start="2022-01-01"
)
```

---

## Binance

**Usage :** Crypto OHLCV (M1, M5, M15, H1, H4, D1)

**Clé requise :** Aucune pour les données historiques

```python
from tvdata.ingest.binance_connector import ingest_binance

ingest_binance(
    symbol="BTCUSDT",
    timeframe="1h",
    start="2021-01-01"
)
```

---

## FRED API

**Usage :** 845k+ séries macro-économiques (CPI, GDP, taux, chômage...)

**Clé requise :** Gratuite sur [fred.stlouisfed.org](https://fred.stlouisfed.org/api_key.html)

```env
FRED_API_KEY=votre_cle_fred
```

```python
from tvdata.ingest.fred_connector import ingest_fred

ingest_fred(series_ids=["CPIAUCSL", "FEDFUNDS", "UNRATE", "T10Y2Y", "GDP"])
```

**Séries prioritaires :**
| ID | Description |
|----|-------------|
| CPIAUCSL | CPI Inflation |
| FEDFUNDS | Federal Funds Rate |
| DGS10 | 10-Year Treasury Yield |
| T10Y2Y | Yield Curve Spread |
| UNRATE | Unemployment Rate |
| GDP | Gross Domestic Product |

---

## SEC EDGAR

**Usage :** Bilans, P&L, Cash Flow (10-K, 10-Q)

**Clé requise :** Aucune, juste un User-Agent

```env
SEC_USER_AGENT=OpenTick/1.0 contact@example.com
```

```python
from tvdata.ingest.sec_connector import ingest_sec_fundamentals

ingest_sec_fundamentals(symbol="AAPL")
```

---

## Update Automatique EOD

Pour mettre à jour tous les cours S&P 500 quotidiennement :

```python
from tvdata.ingest.update_all_stocks import update_all

update_all()  # Vérifie catalog.db et télécharge les jours manquants
```

Ou via le Data Explorer UI : bouton **"Actualiser la base (EOD)"** sur http://localhost:8001
