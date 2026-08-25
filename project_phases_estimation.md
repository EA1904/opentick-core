# 📅 TradoVera — Phases & Estimations de Temps

> Cette feuille de route détaille l'effort nécessaire pour construire l'ensemble de la plateforme TradoVera,
> de la base de données autonome (Data Layer) jusqu'à l'application visuelle (Platform App).

---

## 📊 Tableau Synthétique des Phases

Le projet complet est divisé en **2 grands chantiers** (le **Data Layer** pour 35% du projet et la **Platform App** pour 65%).

| Phase | Chantier | Description & Livrables | Temps Estimé | % du Projet | Statut |
|---|---|---|---|---|---|
| **Phase 1** | Data Layer | Fondations Parquet + DuckDB + Catalogue SQLite | 2 jours | **5%** | **Fait ✅** |
| **Phase 2** | Data Layer | Ingestion des données locales (Kaggle Stocks & Forex MT5) | 3 jours | **10%** | **En cours ⏳** |
| **Phase 3** | Data Layer | Connecteurs Dolt (Earnings, Options, Taux, Splits) | 4 jours | **10%** | **En cours ⏳** |
| **Phase 4** | Data Layer | APIs de Query (yfinance, Binance, FRED API, SEC) & Auto-update | 3 jours | **10%** | Pas commencé |
| **Phase 5** | Platform App | Backend FastAPI (gestion comptes, journal de trading, paper trading engine) | 5 jours | **15%** | Pas commencé |
| **Phase 6** | Platform App | Frontend UI (Dashboard principal, DOM Trading, Carnet d'ordres) | 7 jours | **20%** | Pas commencé |
| **Phase 7** | Platform App | Graphiques Interactifs (Candlestick Charts, indicateurs techniques TA-Lib) | 5 jours | **15%** | Pas commencé |
| **Phase 8** | Platform App | Journal de Trading Avancé & Dashboard Analytics (QuantStats integration) | 5 jours | **15%** | Pas commencé |

**Total estimé : 34 jours de développement actif (soit environ 5 à 7 semaines de travail).**

---

## 🔍 Détail de chaque Phase

---

### 📂 BLOC A — TRADOVERA DATA LAYER (35% du Projet)

Ce bloc permet d'avoir accès à toute la donnée financière (passée et présente), nettoyée, rapide à interroger, de manière totalement autonome (utilisable dans des notebooks Jupyter, pour entraîner des IA, ou par l'application TradoVera).

#### Phase 1 : Fondations SQL/Parquet (5%)
* **Livrables** : Module `normalizer.py`, `catalog.py`, `quality.py` et intégration DuckDB.
* **Temps** : 2 jours (Terminé).

#### Phase 2 : Ingestion Historique Local (10%)
* **Livrables** : Import des 17 millions de lignes Kaggle (D1, 1m). Parseur flexible pour les exports de fichiers CSV de **MetaTrader 5**.
* **Temps** : 3 jours (Pratiquement terminé pour les stocks, reste l'import des CSV MT5).

#### Phase 3 : Données Dolt Premium (10%)
* **Livrables** : Extraction et structuration des taux d'intérêt, des dividendes/splits, des options chains et des états financiers (earnings) depuis Dolt.
* **Temps** : 4 jours (En cours de traitement final).

#### Phase 4 : Connecteurs Extérieurs & Auto-update (10%)
* **Livrables** :
  * Intégration de **FRED API** (données macro) et **SEC EDGAR** (données comptables live).
  * Intégration de **Binance / CCXT** (crypto daily et intraday).
  * Système de mise à jour quotidien automatique pour combler le vide entre 2024 et aujourd'hui.
* **Temps** : 3 jours (Non commencé).

---

### 📂 BLOC B — TRADOVERA PLATFORM APP (65% du Projet)

C'est l'interface visuelle inspirée de Tradovate. Elle utilise les données du Data Layer pour afficher des graphiques interactifs, simuler des ordres (paper trading), gérer un carnet d'ordres (DOM) et journaliser tes trades automatiquement.

#### Phase 5 : Moteur de Paper Trading & Backend (15%)
* **Livrables** :
  * Serveur FastAPI gérant l'authentification et les sessions de trading.
  * Moteur de simulation d'ordres (Market, Limit, Stop, OCO) avec gestion du slippage et exécution sur le flux de prix.
  * Base de données PostgreSQL/SQLite pour stocker l'historique des transactions.
* **Temps** : 5 jours (Non commencé).

#### Phase 6 : Interface Graphique DOM & Carnet d'ordres (20%)
* **Livrables** :
  * Interface React/Next.js moderne avec fenêtres déplaçables (grid system).
  * Carnet d'ordres vertical (DOM) interactif pour placer des ordres d'achat/vente en un clic (exactement comme Tradovate).
  * Dashboard de performance en temps réel (Solde, PnL ouvert/fermé, Marge).
* **Temps** : 7 jours (Non commencé).

#### Phase 7 : Modules Graphiques Interactifs (15%)
* **Livrables** :
  * Graphiques en chandeliers (Candlesticks) fluides avec zoom et indicateurs superposés (Moyennes mobiles, Bandes de Bollinger, RSI...).
  * Liaison directe avec TA-Lib pour calculer les indicateurs à la volée.
* **Temps** : 5 jours (Non commencé).

#### Phase 8 : Journal de Trading & Analytics (15%)
* **Livrables** :
  * Journalisation automatique de chaque trade exécuté dans le Paper Trading.
  * Page d'analyse de performance avancée (Intégration de **QuantStats** pour générer des rapports de Sharpe, Max Drawdown, et courbe de capital).
  * Interface pour ajouter des notes, captures d'écran, et tags sur chaque trade (psychologie, setup, erreur...).
* **Temps** : 5 jours (Non commencé).
