# Story 5.2: Alert Detector

Status: done

## Story

As a system,
I want to detect when production crosses consumption for a region,
so that alerts can be triggered at the right moment.

## Acceptance Criteria

1. `alert_detector.py` dans `functions/shared/alerting/`
2. Lit les données Gold les plus récentes depuis `FACT_ENERGY_FLOW` (production + consommation par région)
3. Détecte les croisements : `under_production` (prod < conso) et `over_production` (prod > conso)
4. Retourne liste de `{ region_code, alert_type, prod_mw, conso_mw }` pour les régions en déséquilibre
5. Gère les valeurs nulles (skip si consommation absente ou nulle)
6. Tests unitaires avec données mockées (SQLite in-memory)

## Tasks / Subtasks

- [x] Créer `functions/shared/alerting/alert_detector.py` (AC: 1, 2, 3, 4, 5)
  - [x] Fonction `detect(conn) -> list[dict]`
  - [x] SQL : récupérer le dernier horodatage, SUM(valeur_mw) par région, MAX(consommation_mw) par région
  - [x] Skip si consommation_mw est NULL ou ≤ 0
  - [x] `under_production` si prod_mw < conso_mw
  - [x] `over_production` si prod_mw > conso_mw
  - [x] Retourner `[{"region_code": str, "alert_type": str, "prod_mw": float, "conso_mw": float}]`
- [x] Écrire les tests dans `tests/test_alert_detector.py` (AC: 3, 4, 5, 6)
  - [x] Région sous-production → 1 alerte `under_production`
  - [x] Région sur-production → 1 alerte `over_production`
  - [x] Région à l'équilibre exact → aucune alerte
  - [x] consommation_mw NULL → skippée
  - [x] consommation_mw = 0 → skippée
  - [x] Plusieurs régions → alertes correctes par région
  - [x] Table vide → liste vide

## Dev Notes

### ⚠️ NE PAS MODIFIER `alert_engine.py` — deux systèmes distincts

`alert_engine.py` existe déjà dans `functions/shared/alerting/`. Il lit des fichiers Silver Parquet et produit des alertes OVERPRODUCTION/NEGATIVE_PRICE_RISK pour le dashboard (stockées dans `AlertStore`). **C'est un système différent.**

`alert_detector.py` lit Gold SQL, produit des alertes `under_production`/`over_production` pour les emails utilisateurs via story 5.3. Les deux coexistent, ne pas toucher à `alert_engine.py`.

### Schéma FACT_ENERGY_FLOW (Gold SQL)

```sql
FACT_ENERGY_FLOW
  id_region     → DIM_REGION.id_region  (code_insee, nom_region)
  id_date       → DIM_TIME.id_date      (horodatage DATETIME2)
  id_source     → DIM_SOURCE.id_source  (source_name)
  valeur_mw     DECIMAL — production pour cette source
  consommation_mw DECIMAL — même valeur pour toutes les sources d'une (région, timestamp)
```

Plusieurs lignes par (région, horodatage) — une par source. Il faut `SUM(valeur_mw)` pour la production totale et `MAX(consommation_mw)` pour la conso.

### Requête SQL recommandée

```sql
SELECT
    r.code_insee   AS region_code,
    SUM(f.valeur_mw)         AS prod_mw,
    MAX(f.consommation_mw)   AS conso_mw
FROM FACT_ENERGY_FLOW f
JOIN DIM_REGION r ON f.id_region = r.id_region
JOIN DIM_TIME t   ON f.id_date   = t.id_date
WHERE t.horodatage = (
    SELECT MAX(t2.horodatage)
    FROM FACT_ENERGY_FLOW f2
    JOIN DIM_TIME t2 ON f2.id_date = t2.id_date
)
GROUP BY r.code_insee
```

Filtrer ensuite en Python : skip si `conso_mw is None or conso_mw <= 0`.

### Implémentation de `detect()`

```python
from typing import Any

def detect(conn: Any) -> list[dict]:
    """
    Detect production/consumption crossings at the latest Gold timestamp.

    Args:
        conn: DB connection (pyodbc or sqlite3).

    Returns:
        List of dicts: [{"region_code": str, "alert_type": str, "prod_mw": float, "conso_mw": float}]
        Only regions with imbalance are returned (prod != conso, conso > 0).
    """
    import sqlite3 as _sqlite3
    is_sqlite = isinstance(conn, _sqlite3.Connection)

    if is_sqlite:
        sql = """
            SELECT r.code_insee AS region_code,
                   SUM(f.valeur_mw) AS prod_mw,
                   MAX(f.consommation_mw) AS conso_mw
            FROM FACT_ENERGY_FLOW f
            JOIN DIM_REGION r ON f.id_region = r.id_region
            JOIN DIM_TIME t ON f.id_date = t.id_date
            WHERE t.horodatage = (
                SELECT MAX(t2.horodatage)
                FROM FACT_ENERGY_FLOW f2
                JOIN DIM_TIME t2 ON f2.id_date = t2.id_date
            )
            GROUP BY r.code_insee
        """
    else:
        sql = """
            SELECT r.code_insee AS region_code,
                   SUM(f.valeur_mw) AS prod_mw,
                   MAX(f.consommation_mw) AS conso_mw
            FROM FACT_ENERGY_FLOW f
            JOIN DIM_REGION r ON f.id_region = r.id_region
            JOIN DIM_TIME t ON f.id_date = t.id_date
            WHERE t.horodatage = (
                SELECT MAX(t2.horodatage)
                FROM FACT_ENERGY_FLOW f2
                JOIN DIM_TIME t2 ON f2.id_date = t2.id_date
            )
            GROUP BY r.code_insee
        """

    cursor = conn.cursor()
    cursor.execute(sql)
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    alerts = []
    for row in rows:
        r = dict(zip(cols, row))
        conso = r.get("conso_mw")
        prod = r.get("prod_mw")
        region_code = r.get("region_code")

        if conso is None or conso <= 0:
            continue
        if prod is None:
            continue

        if prod < conso:
            alerts.append({
                "region_code": region_code,
                "alert_type": "under_production",
                "prod_mw": float(prod),
                "conso_mw": float(conso),
            })
        elif prod > conso:
            alerts.append({
                "region_code": region_code,
                "alert_type": "over_production",
                "prod_mw": float(prod),
                "conso_mw": float(conso),
            })
        # prod == conso → no alert

    logger.info("AlertDetector: %d alert(s) detected", len(alerts))
    return alerts
```

### Pattern de test (SQLite in-memory)

```python
import sqlite3

def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE DIM_REGION (
            id_region INTEGER PRIMARY KEY,
            code_insee TEXT NOT NULL,
            nom_region TEXT
        );
        CREATE TABLE DIM_TIME (
            id_date INTEGER PRIMARY KEY,
            horodatage TEXT NOT NULL
        );
        CREATE TABLE DIM_SOURCE (
            id_source INTEGER PRIMARY KEY,
            source_name TEXT NOT NULL
        );
        CREATE TABLE FACT_ENERGY_FLOW (
            id INTEGER PRIMARY KEY,
            id_region INTEGER,
            id_date INTEGER,
            id_source INTEGER,
            valeur_mw REAL,
            consommation_mw REAL
        );
    """)
    # Insérer sources de base
    conn.execute("INSERT INTO DIM_SOURCE VALUES (1, 'nucleaire')")
    conn.execute("INSERT INTO DIM_SOURCE VALUES (2, 'eolien')")
    conn.execute("INSERT INTO DIM_TIME VALUES (1, '2026-03-11T12:00:00')")
    conn.commit()
    return conn

def _add_region(conn, id_region, code_insee):
    conn.execute("INSERT INTO DIM_REGION VALUES (?, ?, ?)", (id_region, code_insee, code_insee))

def _add_fact(conn, id_region, id_date, id_source, valeur_mw, consommation_mw):
    conn.execute(
        "INSERT INTO FACT_ENERGY_FLOW (id_region, id_date, id_source, valeur_mw, consommation_mw) VALUES (?, ?, ?, ?, ?)",
        (id_region, id_date, id_source, valeur_mw, consommation_mw)
    )
    conn.commit()
```

### Note : SQL identique pour SQLite et SQL Server

La requête utilise `MAX(t2.horodatage)` en sous-requête corrélée, compatible SQLite et SQL Server. Pas besoin de branche `is_sqlite` pour la requête — on peut unifier. Garder la branche is_sqlite si des différences de syntaxe apparaissent, sinon une seule requête suffit.

### Références

- `functions/shared/alerting/alert_engine.py` — NE PAS MODIFIER, système distinct
- `functions/shared/api/email_service.py` — `send_alert(to_email, region_code, alert_type, prod_mw, conso_mw)` prêt
- `functions/shared/api/production_service.py` — patron SQL Gold avec JOIN DIM_REGION/DIM_TIME
- `functions/migrations/003_create_alert_sent_log.sql` — ALERT_SENT_LOG (déduplication story 5.3)
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 5.2` — ACs source

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

N/A — 12/12 tests passed on first run.

### Completion Notes List

- Requête SQL unifiée SQLite/SQL Server (`MAX(horodatage)` en sous-requête corrélée).
- `detect()` retourne seulement les régions en déséquilibre — prod==conso → pas d'alerte.
- Test `test_only_latest_timestamp_used` vérifie que les anciennes données ne génèrent pas d'alertes.

### Code Review Fixes (CR)

- **M1 fixed**: Suppression de `import sqlite3 as _sqlite3` (dead code).
- **L1 fixed**: Test `test_null_prod_mw_skipped` ajouté — couvre le cas `SUM(valeur_mw)=NULL`.

### File List

- `functions/shared/alerting/alert_detector.py` (new)
- `tests/test_alert_detector.py` (new, 12 tests)
