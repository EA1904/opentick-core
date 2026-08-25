# 📋 TradoVera — Implementation Plan Officiel

> Réplique complète de Tradovate en local/SaaS avec données 100% gratuites.
> Version : 1.0 | Date : Août 2026

---

## 🎯 Objectif

Construire **TradoVera** — une plateforme de trading analytique qui reproduit exactement l'expérience Tradovate :
- Interface modulaire (Charts, DOM, Watchlist, Order Entry)
- Paper trading / simulation complète
- Market Replay (rejouer des sessions historiques)
- Order Flow Tools (Volume Profile, VWAP, Delta)
- Trading Journal + Analytics avancés (exclusifs vs Tradovate)
- Backtesting Engine Python (exclusif vs Tradovate)
- 100% données gratuites, 100% local (Docker)

---

## 💾 Stratégie Données Gratuites — Le Cœur du Projet

### Sources par asset class

| Marché | Source | Type de données | Limite gratuite |
|--------|--------|-----------------|-----------------|
| **Crypto (live)** | **Binance WebSocket** | Tick + OHLCV temps réel | ✅ Illimité, sans compte |
| **Crypto (historique)** | **CCXT + Binance REST** | OHLCV 1m → 1M, plusieurs années | ✅ Illimité, sans compte |
| **Actions US** | **yfinance** | OHLCV 1m (60j) → 1D (max) | ✅ Gratuit, sans clé |
| **Futures (ES, NQ, CL)** | **yfinance** (`ES=F`, `NQ=F`) | OHLCV daily + intraday limité | ✅ Gratuit |
| **Forex** | **Dukascopy** (CSV bulk) | Tick data historique complet | ✅ Gratuit, téléchargement |
| **Forex (live simulé)** | **Frankfurter API** | Taux de change EOD | ✅ Gratuit, sans clé |
| **Indices** | **yfinance** (`^GSPC`, `^NDX`) | OHLCV complet | ✅ Gratuit |
| **Économique** | **FRED API** | Données macro (CPI, Fed Rate...) | ✅ Gratuit avec clé |

### Architecture Data Pipeline

```
Sources Gratuites
│
├── Binance WebSocket ──────────────────► Redis (cache temps réel)
│   (Crypto live, sans auth)                    │
│                                               ▼
├── CCXT + Binance REST ─────────────► PostgreSQL/TimescaleDB
│   (Crypto historique)                  (stockage OHLCV)
│                                               │
├── yfinance ────────────────────────►          │
│   (Stocks, Futures, Indices)                  │
│                                               ▼
├── Dukascopy CSV Import ───────────► FastAPI Data Service
│   (Forex tick data)                           │
│                                               ▼
└── Frankfurter API ──────────────────► Frontend (Next.js)
    (Forex EOD simulé live)              via WebSocket Gateway
```

### Couverture réelle avec données gratuites

| Asset | Historique | Temps réel | Qualité |
|-------|-----------|------------|---------|
| BTC, ETH, Altcoins | ✅ Illimité (Binance) | ✅ Tick live | 🟢 Excellent |
| Actions US (AAPL, TSLA...) | ✅ 5+ ans (1D) / 60j (1m) | ⚠️ 15min delay | 🟡 Bon |
| Futures ES/NQ/CL | ✅ 1-2 ans (1D) | ⚠️ 15min delay | 🟡 Acceptable |
| Forex (EUR/USD...) | ✅ Tick complet (Dukascopy) | ⚠️ EOD simulé | 🟡 Bon |
| Indices (S&P, Nasdaq) | ✅ Complet | ⚠️ 15min delay | 🟡 Bon |

> **Note** : Pour le paper trading et le backtesting, les données gratuites sont PARFAITES.
> Le 15min delay sur les actions ne pose aucun problème en mode simulation/analyse.

---

## 🏗️ Architecture Technique

### Stack complète

```
┌─────────────────────────────────────────────────────┐
│                   FRONTEND (Next.js 14)              │
│  ┌─────────┐ ┌──────────┐ ┌────────┐ ┌──────────┐  │
│  │ Charts  │ │   DOM    │ │Journal │ │Backtest  │  │
│  │(LW Charts│ │(Ladder) │ │& Stats │ │ Results  │  │
│  └─────────┘ └──────────┘ └────────┘ └──────────┘  │
│         Zustand State | Tailwind CSS | Framer Motion │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP + WebSocket
┌──────────────────────▼──────────────────────────────┐
│               BACKEND (FastAPI Python)               │
│  ┌──────────┐ ┌────────┐ ┌──────────┐ ┌─────────┐  │
│  │Data Svc  │ │Sim Svc │ │Backtest  │ │Journal  │  │
│  │(yf+CCXT) │ │(Paper) │ │(Backtrdr)│ │  Svc    │  │
│  └──────────┘ └────────┘ └──────────┘ └─────────┘  │
└────────┬─────────────┬────────────────┬─────────────┘
         │             │                │
┌────────▼──┐  ┌───────▼──┐  ┌─────────▼──────┐
│PostgreSQL  │  │  Redis   │  │  Celery Worker │
│TimescaleDB │  │  Cache   │  │ (Backtests BG) │
└────────────┘  └──────────┘  └────────────────┘
```

### Technologies

| Couche | Technologie | Version |
|--------|-------------|---------|
| **Frontend Framework** | Next.js (App Router) | 14.x |
| **Charts Trading** | Lightweight Charts (TradingView) | 4.x |
| **UI Components** | shadcn/ui + Radix UI | latest |
| **Styling** | Tailwind CSS | 3.x |
| **Animations** | Framer Motion | 11.x |
| **State Management** | Zustand | 4.x |
| **Backend** | FastAPI (Python) | 0.110+ |
| **Data — Stocks/Futures** | yfinance | 0.2.x |
| **Data — Crypto** | CCXT + Binance WS | 4.x |
| **Backtesting Engine** | Backtrader | 1.9.x |
| **Base de données** | PostgreSQL + TimescaleDB | 16.x |
| **Cache** | Redis | 7.x |
| **Task Queue** | Celery | 5.x |
| **Conteneurs** | Docker + Docker Compose | latest |
| **Auth** | NextAuth.js + JWT | 5.x |

---

## 📦 Modules — Feature List Exacte (= Tradovate)

### MODULE 1 — Workspace & Navigation
- [ ] Layout modulaire (panels redimensionnables)
- [ ] Sidebar navigation
- [ ] Topbar (comptes, mode live/sim, notifications)
- [ ] Sauvegarde/chargement de workspaces nommés
- [ ] Thème dark (défaut) / light
- [ ] Multi-panels : Chart + DOM + Watchlist côte à côte

### MODULE 2 — Charts (= Tradovate Charts)
**Types de charts :**
- [ ] Candlestick (défaut)
- [ ] OHLC bars
- [ ] Line on Close
- [ ] Heiken-Ashi
- [ ] Renko (basé sur l'amplitude)
- [ ] Volume bars (basé sur le volume)

**Timeframes :**
- [ ] Secondes (1s, 5s, 15s, 30s)
- [ ] Minutes (1m, 3m, 5m, 15m, 30m)
- [ ] Heures (1H, 2H, 4H)
- [ ] Jours / Semaines / Mois (1D, 1W, 1M)
- [ ] Tick charts (N ticks par bougie)

**Indicateurs built-in (20+) :**
- [ ] Moyennes mobiles : SMA, EMA, WMA, VWMA
- [ ] MACD
- [ ] RSI
- [ ] Stochastique
- [ ] Bollinger Bands
- [ ] ATR (Average True Range)
- [ ] Volume
- [ ] VWAP + VWAP bands
- [ ] **Volume Profile** (distribution volume par prix)
- [ ] Fibonacci Retracement
- [ ] Ichimoku Cloud
- [ ] Pivot Points
- [ ] OBV (On Balance Volume)
- [ ] CCI
- [ ] Williams %R
- [ ] ADX

**Drawing Tools :**
- [ ] Ligne de tendance
- [ ] Ligne horizontale / verticale
- [ ] Rectangle / Zone
- [ ] Fibonacci (retracement + extension)
- [ ] Flèches et annotations
- [ ] Canaux (Channel)

**Fonctionnalités chart :**
- [ ] Zoom / Pan / Crosshair
- [ ] Snap to OHLC
- [ ] Synchronisation avec DOM (même symbole/timeframe)
- [ ] Multi-chart layout (1, 2, 4 charts simultanés)
- [ ] Overlay des trades sur le chart (positions, SL, TP)
- [ ] Chart Trading mode (clic droit pour placer ordre)
- [ ] Alertes directement depuis le chart

### MODULE 3 — DOM / SuperDOM (= Tradovate SuperDOM)
- [ ] Ladder de prix (bid/ask levels)
- [ ] Taille bid/ask par niveau de prix
- [ ] Placement d'ordre 1-clic depuis le DOM
- [ ] Modification d'ordre (drag sur le ladder)
- [ ] Annulation d'ordre (clic)
- [ ] P&L simulé en temps réel par ligne de prix
- [ ] Histogramme de volume intégré dans le DOM
- [ ] Pulling / Stacking detection
- [ ] Synchronisation avec chart actif
- [ ] Affichage indicateurs sur le DOM

### MODULE 4 — Order Entry & Gestion de Positions (= Tradovate Order Entry)
**Types d'ordres :**
- [ ] Market Order
- [ ] Limit Order
- [ ] Stop Order
- [ ] Stop-Limit Order
- [ ] Trailing Stop

**ATM Strategies (Bracket Orders) :**
- [ ] Configuration Stop Loss + Take Profit automatiques
- [ ] OCO (One-Cancels-Other)
- [ ] Sauvegarde des ATM strategies nommées
- [ ] Application en 1 clic

**Gestion de positions :**
- [ ] Flatten (fermer position + annuler ordres)
- [ ] Reverse (inverser position)
- [ ] Close at Market
- [ ] Cancel All Orders
- [ ] P&L en temps réel par position

### MODULE 5 — Market Replay (= Tradovate Market Replay)
- [ ] Sélection de la date et session à rejouer
- [ ] Lecture tick par tick / barre par barre
- [ ] Contrôles : Play, Pause, Stop, Vitesse (1x, 2x, 5x, 10x)
- [ ] Barre de progression temporelle
- [ ] Placement d'ordres simulés pendant le replay
- [ ] P&L en temps réel pendant le replay
- [ ] DOM animé pendant le replay
- [ ] Journal auto des trades passés pendant le replay

### MODULE 6 — Watchlist / Market Analyzer (= Tradovate Watchlist)
- [ ] Liste multi-symboles avec quotes en temps réel
- [ ] Colonnes : Last, Bid, Ask, Volume, Change%, High, Low
- [ ] Ajout/suppression de symboles
- [ ] Groupes de watchlist (Crypto, Stocks, Futures...)
- [ ] Tri par colonne
- [ ] Alertes depuis la watchlist
- [ ] Double-clic → ouvre le chart du symbole

### MODULE 7 — Risk Management (= Tradovate Risk Settings)
- [ ] Daily Loss Limit (arrêt auto si perte > X$)
- [ ] Daily Profit Target Lock (arrêt si profit > X$)
- [ ] Max Position Size (limite taille des ordres)
- [ ] Weekly Loss Limit
- [ ] Verrou de paramètres (Lock Settings pour la session)
- [ ] Alertes visuelles / sonores quand seuil approché
- [ ] Log des événements de risk management

### MODULE 8 — Account & Positions Panel
- [ ] Vue des positions ouvertes (symbole, taille, prix moyen, P&L)
- [ ] Ordres en attente (working orders)
- [ ] Historique des trades de la session
- [ ] Balance du compte simulé
- [ ] Margin utilisé / disponible
- [ ] P&L du jour (réalisé + non-réalisé)
- [ ] Graphique equity intraday

### MODULE 9 — Trading Journal (🏆 EXCLUSIF vs Tradovate)
- [ ] Ajout manuel de trades (symbole, direction, prix, taille, date)
- [ ] Import automatique depuis MetaTrader 4/5 (CSV/HTML)
- [ ] Import CSV générique (colonnes mappables)
- [ ] Tags par trade (setup, erreur, émotionnel...)
- [ ] Notes texte + screenshots par trade
- [ ] Rating du trade (1-5 étoiles)
- [ ] Calendrier heatmap P&L par jour
- [ ] Filtres avancés (symbole, setup, résultat, date)
- [ ] Revue de trade avec chart overlay
- [ ] Export journal (CSV, PDF)

### MODULE 10 — Analytics Dashboard (🏆 EXCLUSIF vs Tradovate)
**Métriques globales :**
- [ ] Win Rate (global + par symbole + par setup)
- [ ] Profit Factor
- [ ] Average Win / Average Loss
- [ ] Risk/Reward Ratio
- [ ] Sharpe Ratio
- [ ] Sortino Ratio
- [ ] Max Drawdown ($ et %)
- [ ] Longest Drawdown Period
- [ ] Consecutive Wins / Losses

**Graphiques analytiques :**
- [ ] Equity Curve (courbe de capital)
- [ ] Drawdown Chart
- [ ] Histogramme distribution des P&L
- [ ] Heatmap par heure/jour de semaine
- [ ] Performance par symbole (bar chart)
- [ ] Performance par setup
- [ ] Scatter plot (durée vs P&L)

**Rapports :**
- [ ] Rapport hebdomadaire auto-généré
- [ ] Rapport mensuel
- [ ] Export PDF complet

### MODULE 11 — Backtesting Engine (🏆 EXCLUSIF vs Tradovate)
**Configuration :**
- [ ] Sélection stratégie (fichier Python)
- [ ] Période de backtest (dates début/fin)
- [ ] Capital initial
- [ ] Frais de commission
- [ ] Slippage
- [ ] Sélection symbole + timeframe

**Exécution :**
- [ ] Run en background (Celery)
- [ ] Barre de progression temps réel
- [ ] Annulation possible

**Résultats :**
- [ ] Equity curve interactive
- [ ] Drawdown chart
- [ ] Liste complète des trades exécutés
- [ ] Toutes les métriques (Sharpe, Win Rate, etc.)
- [ ] Comparaison de plusieurs backtests (A/B)
- [ ] Export CSV/PDF

### MODULE 12 — Strategy Builder (🏆 EXCLUSIF vs Tradovate)
- [ ] Éditeur de code Python (Monaco Editor)
- [ ] Templates prêts à l'emploi (Moving Average Cross, RSI, etc.)
- [ ] Validation syntaxique en temps réel
- [ ] Documentation des APIs disponibles
- [ ] Bibliothèque de stratégies sauvegardées
- [ ] Partage de stratégies (fichier .py)

---

## 📅 Plan de Développement — 6 Sprints

### **SPRINT 0 — Infrastructure & Setup** ⏱️ `5-7 jours`
```
Objectif : Avoir une app qui tourne dans Docker, avec DB et API fonctionnels.
```
- [ ] Initialisation Next.js 14 (App Router)
- [ ] Initialisation FastAPI backend
- [ ] Docker Compose : PostgreSQL + TimescaleDB + Redis + FastAPI + Next.js
- [ ] Migrations Alembic (tables : users, symbols, ohlcv, trades, journals)
- [ ] Pipeline data de base : yfinance → PostgreSQL
- [ ] WebSocket gateway (FastAPI → Next.js)
- [ ] Authentification JWT (single user local)
- [ ] Design System : couleurs, typo (Inter), tokens Tailwind
- [ ] Layout de base : sidebar + topbar + zone de modules

**Livrables** : App Docker qui tourne, data BTC/AAPL stockée en DB

---

### **SPRINT 1 — Charts + Watchlist + Workspace** ⏱️ `10-12 jours`
```
Objectif : Interface chart professionnelle = cœur de Tradovate.
```
- [ ] Intégration Lightweight Charts (TradingView library)
- [ ] Chart candlestick interactif (zoom, pan, crosshair)
- [ ] Multi-timeframe (secondes → mois)
- [ ] Chart types : Candlestick, OHLC, Line, Heiken-Ashi
- [ ] Indicateurs : SMA, EMA, MACD, RSI, Bollinger, Volume, VWAP
- [ ] Drawing tools : lignes, rectangles, Fibonacci
- [ ] Multi-chart layout (1/2/4 panels)
- [ ] Watchlist avec quotes (crypto = live, stocks = 15min delay)
- [ ] Binance WebSocket intégré (prix crypto temps réel)
- [ ] Chart Trading mode (order entry depuis chart)
- [ ] Synchronisation chart ↔ symbole actif

**Livrables** : Charts professionnels, watchlist live crypto, multi-layout

---

### **SPRINT 2 — DOM + Order Entry + Paper Trading** ⏱️ `10-12 jours`
```
Objectif : Simuler exactement l'expérience d'exécution de Tradovate.
```
- [ ] SuperDOM : ladder bid/ask simulé
- [ ] DOM génération depuis OHLCV (simulation order book)
- [ ] Placement ordres depuis DOM (Market, Limit, Stop)
- [ ] Panel d'ordre (Market, Limit, Stop-Limit, Trailing Stop)
- [ ] ATM Strategies (Bracket : SL + TP auto)
- [ ] OCO orders
- [ ] Position panel (positions ouvertes, P&L simulé)
- [ ] Working orders panel
- [ ] Actions : Flatten, Reverse, Cancel All
- [ ] Compte simulé (balance, margin, equity)
- [ ] Risk Management : Daily Loss Limit, Profit Target Lock, Max Size

**Livrables** : Paper trading complet, DOM simulé, risk management actif

---

### **SPRINT 3 — Market Replay + Order Flow** ⏱️ `10-14 jours`
```
Objectif : Market Replay (feature premium de Tradovate) + Volume Profile.
```
**Market Replay :**
- [ ] Sélection date + session
- [ ] Reconstruction des données tick-by-tick depuis OHLCV
- [ ] Moteur de replay (play/pause/vitesse)
- [ ] Chart animé pendant le replay
- [ ] DOM animé pendant le replay
- [ ] Paper trading pendant le replay
- [ ] Sauvegarde session replay

**Order Flow Tools :**
- [ ] Volume Profile (distribution volume par prix)
- [ ] VWAP avec bandes (1, 2, 3 std dev)
- [ ] Delta / CVD (Cumulative Volume Delta)
- [ ] Footprint chart (simplifié : bid/ask par bougie)

**Chart types avancés :**
- [ ] Renko charts
- [ ] Tick charts
- [ ] Range bars

**Livrables** : Market Replay fonctionnel, Volume Profile, Footprint basique

---

### **SPRINT 4 — Journal + Analytics** ⏱️ `10-12 jours`
```
Objectif : Notre différenciation majeure vs Tradovate.
```
**Trading Journal :**
- [ ] Interface saisie manuelle de trades
- [ ] Import MT4/MT5 (parser CSV/HTML)
- [ ] Import CSV générique avec mapping de colonnes
- [ ] Tags, notes, rating par trade
- [ ] Calendrier heatmap P&L
- [ ] Revue de trade avec chart overlay
- [ ] Export CSV / PDF

**Analytics Dashboard :**
- [ ] Equity Curve interactive
- [ ] Drawdown Chart
- [ ] Win Rate, Profit Factor, Sharpe Ratio...
- [ ] Heatmap (heure/jour de la semaine)
- [ ] Performance par symbole / setup
- [ ] Rapport auto (hebdo / mensuel)
- [ ] Comparaison périodes

**Livrables** : Journal complet, analytics pro, rapport PDF

---

### **SPRINT 5 — Backtesting + Strategy Builder** ⏱️ `12-14 jours`
```
Objectif : Feature unique — tester des stratégies sur données historiques.
```
**Strategy Builder :**
- [ ] Monaco Editor (Python) intégré
- [ ] Templates de base (MA Cross, RSI Overbought...)
- [ ] Validation et lint en temps réel
- [ ] Bibliothèque de stratégies

**Backtesting Engine :**
- [ ] Intégration Backtrader
- [ ] Configuration : dates, capital, frais, slippage, symbole, TF
- [ ] Run en background (Celery)
- [ ] Progression temps réel (WebSocket)
- [ ] Rapport complet (equity curve, trades, métriques)
- [ ] Comparaison multi-backtests
- [ ] Export résultats (CSV, PDF)

**Livrables** : Backtesting fonctionnel bout en bout

---

### **SPRINT 6 — Polish, Tests & Déploiement** ⏱️ `5-7 jours`
```
Objectif : Stabiliser, optimiser, et livrer une version production.
```
- [ ] Tests backend (pytest, couverture > 70%)
- [ ] Tests E2E frontend (Playwright : chart, journal, backtest)
- [ ] Optimisations performance (lazy loading, pagination, cache)
- [ ] Notifications in-app (alertes prix, risk events)
- [ ] Documentation utilisateur (README + guide)
- [ ] Docker Compose final (one-command install)
- [ ] Variables d'environnement propres (.env)
- [ ] Préparation SaaS (Vercel + Railway config)

**Livrables** : App stable, Docker installable en 1 commande

---

## ⏱️ Estimation Totale

| Sprint | Description | Durée |
|--------|-------------|-------|
| Sprint 0 | Infrastructure | 5-7 jours |
| Sprint 1 | Charts + Watchlist | 10-12 jours |
| Sprint 2 | DOM + Paper Trading | 10-12 jours |
| Sprint 3 | Market Replay + Order Flow | 10-14 jours |
| Sprint 4 | Journal + Analytics | 10-12 jours |
| Sprint 5 | Backtesting + Strategy | 12-14 jours |
| Sprint 6 | Polish + Deploy | 5-7 jours |
| **TOTAL** | **Développement assisté AI** | **~62-78 jours** |
| **MVP (Sprint 0→2)** | Charts + DOM + Paper Trading | **~25-31 jours** |

---

## 🗂️ Structure des Fichiers du Projet

```
tradovera/
├── frontend/                    # Next.js 14
│   ├── app/
│   │   ├── (auth)/             # Login / Register
│   │   ├── (dashboard)/
│   │   │   ├── chart/          # Module Charts
│   │   │   ├── dom/            # SuperDOM
│   │   │   ├── replay/         # Market Replay
│   │   │   ├── journal/        # Trading Journal
│   │   │   ├── analytics/      # Analytics Dashboard
│   │   │   ├── backtest/       # Backtesting
│   │   │   └── settings/       # Settings
│   │   └── layout.tsx
│   ├── components/
│   │   ├── charts/             # Chart components
│   │   ├── dom/                # DOM components
│   │   ├── journal/            # Journal components
│   │   ├── analytics/          # Analytics charts
│   │   └── ui/                 # Base UI (shadcn)
│   ├── lib/
│   │   ├── stores/             # Zustand stores
│   │   ├── hooks/              # Custom hooks
│   │   └── websocket.ts        # WS client
│   └── public/
│
├── backend/                     # FastAPI Python
│   ├── app/
│   │   ├── api/
│   │   │   ├── data.py         # OHLCV endpoints
│   │   │   ├── simulation.py   # Paper trading
│   │   │   ├── replay.py       # Market replay
│   │   │   ├── journal.py      # Journal CRUD
│   │   │   ├── analytics.py    # Métriques
│   │   │   └── backtest.py     # Backtesting
│   │   ├── services/
│   │   │   ├── data_service.py # yfinance + CCXT
│   │   │   ├── binance_ws.py   # WebSocket Binance
│   │   │   ├── sim_engine.py   # Simulation engine
│   │   │   └── replay_engine.py
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   └── tasks/              # Celery tasks
│   ├── strategies/             # Stratégies Python user
│   ├── alembic/                # Migrations DB
│   └── requirements.txt
│
├── docker-compose.yml           # One-command deploy
├── .env.example
└── README.md
```

---

## 🐳 Installation (1 commande)

```bash
git clone https://github.com/you/tradovera
cd tradovera
cp .env.example .env
docker-compose up -d
# → http://localhost:3000
```

**C'est tout.** Aucune configuration nécessaire, tout tourne en local.

---

## 📊 Récapitulatif Features vs Tradovate

| Feature | Tradovate | TradoVera |
|---------|-----------|-----------|
| Charts interactifs | ✅ | ✅ |
| Heiken-Ashi + Renko | ✅ | ✅ |
| Tick / Volume bars | ✅ | ✅ |
| 20+ indicateurs | ✅ | ✅ |
| Volume Profile | ✅ | ✅ |
| VWAP | ✅ | ✅ |
| Drawing tools | ✅ | ✅ |
| SuperDOM / Ladder | ✅ | ✅ (simulé) |
| Order Entry complet | ✅ | ✅ (simulé) |
| ATM / Bracket Orders | ✅ | ✅ |
| Paper Trading | ✅ | ✅ |
| Market Replay | ✅ | ✅ |
| Footprint Charts | ✅ | ✅ (basique) |
| CVD / Delta | ✅ | ✅ |
| Watchlist live | ✅ | ✅ (crypto live) |
| Risk Management | ✅ | ✅ |
| Multi-workspace layouts | ✅ | ✅ |
| **Trading Journal** | ❌ | 🏆 ✅ |
| **Analytics avancés** | ⚠️ basique | 🏆 ✅ complet |
| **Backtesting Engine** | ❌ | 🏆 ✅ |
| **Strategy Builder Python** | ❌ | 🏆 ✅ |
| **Import MT4/MT5** | ❌ | 🏆 ✅ |
| **Données gratuites** | ❌ (abonnement) | 🏆 ✅ $0 |

**Résultat : TradoVera = Tradovate + Journal + Backtesting + Analytics — à $0/mois**

