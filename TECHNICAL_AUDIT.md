# Audit Technique & Axes d'Amélioration : `opentick-core`

Ce document présente une analyse technique détaillée du dépôt **opentick-core**, identifiant les points de faiblesse actuels, les axes d'optimisation prioritaires ainsi que le degré d'urgence associé pour chaque chantier.

---

## 1. Tableau Synthétique d'Évaluation

| Axe / Chantier | Faiblesse Constatée | Impact Technique | Degré d'Urgence |
| :--- | :--- | :--- | :---: |
| **Pipeline CI/CD** | Absence de validation automatique des tests et du build Docker. | Risque de régressions non détectées lors des pushs. | **Élevé** |
| **Résilience d'Ingestion** | Absence de gestion explicite des rate-limits API et des déconnexions. | Risque de perte de ticks ou d'interruption silencieuse du pipeline. | **Élevé** |
| **Architecture des Tests** | Tests sous forme de scripts à la racine (`test_*.py`) au lieu d'une suite standard. | Couverture difficile à automatiser, absence d'isolation (mocks). | **Moyen** |
| **Optimisation du Data Lake** | Risque d'engorgement lié à la création de multiples "petits fichiers" lors des mises à jour incrémentales. | Ralentissement des requêtes sur `data_explorer.py` (problème des small files). | **Moyen** |
| **Observabilité & Alerting** | Pas de système d'alertes en cas de coupure de flux live. | Absence de visibilité en temps réel sur l'état de santé des workers. | **Faible à Moyen** |

---

## 2. Analyse Détaillée des Axes d'Amélioration

### A. Industrialisation de l'Ingestion & Tolérance aux Pannes (Urgence : Élevée)
* **Constat :** Les APIs financières de courtage et de flux de marché (Alpaca, FRED, etc.) appliquent des limitations strictes sur le nombre de requêtes par minute et peuvent couper les sockets de manière intermittente.
* **Recommandations :**
  - Mettre en place un mécanisme de retry avec **backoff exponentiel** (via `tenacity` ou `backoff`).
  - Utiliser une file d'attente tampon (buffer mémoire ou queue légère) pour absorber les pics de volatilité sans surcharger la couche de stockage.
  - Implémenter un système de réconciliation pour combler automatiquement les trous de données (gaps) après une reconnexion.

---

### B. Mise en Place d'un Pipeline CI/CD GitHub Actions (Urgence : Élevée)
* **Constat :** Le dépôt ne dispose pas encore de répertoire `.github/workflows/`. Tout contrôle repose sur une exécution manuelle.
* **Recommandations :**
  - Créer un workflow `.github/workflows/ci.yml` exécutant à chaque PR / push :
    1. **Linting & Formatage** : `ruff check .` et `ruff format --check .`
    2. **Tests Unitaires & Intégration** : `pytest tests/`
    3. **Vérification du Build Docker** : `docker compose build`

---

### C. Standardisation de la Suite de Tests (Urgence : Moyenne)
* **Constat :** Les fichiers `test_alpaca_m15.py` et `test_pipeline.py` sont positionnés à la racine du projet comme des scripts autonomes.
* **Recommandations :**
  - Structurer un répertoire dédié `tests/` :
    ```text
    tests/
    ├── conftest.py
    ├── test_alpaca_ingestion.py
    ├── test_pipeline_flow.py
    └── test_storage_engine.py
    ```
  - Introduire des fixtures `pytest` et des mocks pour simuler les réponses API d'Alpaca afin de garantir des tests reproductibles hors ligne et sans consommation de quotas.

---

### D. Optimisation Avancée du Data Lake & Compaction (Urgence : Moyenne)
* **Constat :** Bien que l'architecture actuelle repose déjà sur Parquet, DuckDB et un Hive-partitioning performant, les mises à jour incrémentales (daily updates) génèrent de multiples petits fichiers Parquet par partition (le problème du "small files problem").
* **Recommandations :**
  - Implémenter un script de **compaction** régulier (via DuckDB) pour fusionner les petits fichiers Parquet incrémentaux en de plus gros fichiers (optimisation des row groups).
  - Affiner l'algorithme de compression (passer explicitement à ZSTD avec un niveau de compression adapté) pour réduire encore l'empreinte disque.

---

## 3. Matrice de Décision : Priorisation selon l'Objectif

```text
[ Objectif : Showcase / Portfolio ]
   └── 1. Déplacer les tests dans /tests avec pytest (1h)
   └── 2. Ajouter GitHub Actions CI (30 min)
   └── Résultat : Image de code production-ready impeccable.

[ Objectif : Système de Trading / Ingestion Live 24/7 ]
   └── 1. Sécuriser les retries et la résilience WebSocket
   └── 2. Script de compaction des petits fichiers Parquet
   └── 3. Configurer un monitoring basique des flux
```
