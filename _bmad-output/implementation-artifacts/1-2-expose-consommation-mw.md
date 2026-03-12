# Story 1.2: Expose consommation_mw in Production API

Status: done

## Story

As a developer,
I want `consommation_mw` exposed in the `/v1/production/regional` endpoint,
so that the alert detector can compare production vs consumption.

## Acceptance Criteria

1. La colonne `consommation_mw` est lue depuis `FACT_ENERGY_FLOW` dans `production_service.py` (SELECT `f.consommation_mw`)
2. Le champ `consommation_mw` apparaît dans chaque enregistrement de la réponse JSON de `/v1/production/regional`, au niveau région/timestamp (pas par source)
3. Les tests existants (266 passant) continuent de passer — aucune régression
4. La valeur peut être nulle (`null` en JSON si NULL en base) — le serializer existant `_to_json_safe` gère déjà les None

## Tasks / Subtasks

- [x] Synchroniser le schéma SQLite avec SQL Server (AC: 3)
  - [x] Ajouter `consommation_mw REAL NULL` dans `FACT_ENERGY_FLOW` du schéma SQLite dans `dim_loader.py` (bloc `if not is_sql_server` ~ligne 58-68)
- [x] Modifier `build_production_query` dans `production_service.py` (AC: 1)
  - [x] Ajouter `f.consommation_mw` au SELECT (les deux branches : SQLite et SQL Server)
- [x] Modifier `_aggregate_rows` dans `production_service.py` (AC: 2)
  - [x] Extraire `consommation_mw` depuis la première ligne du groupe (comme `facteur_charge`) et l'inclure dans le dict agrégé
- [x] Mettre à jour les tests dans `test_api_endpoints.py` (AC: 2, 3, 4)
  - [x] Fixture `db` : insérer `consommation_mw` sur certains enregistrements (et NULL sur d'autres pour tester les deux cas)
  - [x] Ajouter un test vérifiant que `consommation_mw` apparaît dans la réponse JSON
  - [x] Ajouter un test vérifiant qu'une valeur NULL est sérialisée en `null` JSON (pas de crash)
- [x] Vérifier que tous les tests existants passent (AC: 3)

## Dev Notes

### ⚠️ PIÈGE CRITIQUE — Schéma SQLite désynchronisé

**Le schéma SQLite de `dim_loader.py` n'a PAS `consommation_mw`.** Les deux schémas divergent :

```python
# dim_loader.py ~ligne 58 — schéma SQLite (INCOMPLET)
CREATE TABLE IF NOT EXISTS FACT_ENERGY_FLOW (
    ...
    valeur_mw REAL NOT NULL,
    facteur_charge REAL,
    temperature_moyenne REAL,
    prix_mwh REAL,
    -- ⚠️ consommation_mw ABSENT ICI
    UNIQUE(id_date, id_region, id_source)
)

# dim_loader.py ligne 105-119 — schéma SQL Server (COMPLET)
CREATE TABLE FACT_ENERGY_FLOW (
    ...
    consommation_mw     DECIMAL(10,2)   NULL,  ← présent ici
)
```

**Impact :** Les tests `test_api_endpoints.py` utilisent `DimLoader(conn).ensure_schema()` sur SQLite. Si on ajoute `f.consommation_mw` au SELECT sans corriger le schéma SQLite, les tests lèveront `OperationalError: no such column: f.consommation_mw`.

**Fix requis AVANT toute modification de `production_service.py`** : ajouter `consommation_mw REAL NULL` au schéma SQLite dans `dim_loader.py`.

### Architecture du SELECT existant

`build_production_query` retourne actuellement (les deux branches) :
```sql
SELECT [TOP(?)]
    r.code_insee,
    r.nom_region,
    t.horodatage,
    s.source_name,
    f.valeur_mw,
    f.facteur_charge
FROM FACT_ENERGY_FLOW f
JOIN DIM_REGION r ...
JOIN DIM_TIME t ...
JOIN DIM_SOURCE s ...
```

Ajouter `f.consommation_mw` **dans les deux branches** (SQLite LIMIT et SQL Server TOP).

### Architecture de `_aggregate_rows`

`_aggregate_rows` reçoit des colonnes `(code_insee, nom_region, horodatage, source_name, valeur_mw, facteur_charge)` et agrège par `(code_insee, horodatage)`. La colonne `facteur_charge` est prise de la **première ligne** du groupe (c'est une donnée région/temps, pas par source). `consommation_mw` suit le **même pattern** :

```python
# Actuel
aggregated[key] = {
    "code_insee": r["code_insee"],
    "region":     r["nom_region"],
    "timestamp":  ts,
    "sources":    {},
    "facteur_charge": _to_json_safe(r["facteur_charge"]),
}

# Après modification — ajouter consommation_mw au même niveau
aggregated[key] = {
    ...
    "facteur_charge":   _to_json_safe(r["facteur_charge"]),
    "consommation_mw":  _to_json_safe(r["consommation_mw"]),  # ← ajouter
}
```

### `_to_json_safe` gère déjà les NULL

```python
def _to_json_safe(value):
    if value is None:
        return None   # ← None → null JSON automatiquement
    ...
```

Pas de code supplémentaire pour gérer les NULL.

### `consommation_mw` en contexte projet

- Colonne dans SQL Server : `DECIMAL(10,2) NULL` (`dim_loader.py:117`)
- Alimentée par le pipeline : `rte_silver.py:37` mappe `"consommation"` → `"consommation_mw"`
- Utilisée par l'alert engine : `alert_engine.py:77-88` — lit déjà la colonne depuis le DataFrame Gold
- **Dans la fixture SQLite**, valeur typique : `consommation REAL NULL` (peut être 0.0 ou NULL)

### Tests à modifier : `test_api_endpoints.py`

**Fixture `db` (ligne 71-81)** — ajouter `consommation_mw` aux inserts :
```python
# Avant
cursor.execute(
    """INSERT INTO FACT_ENERGY_FLOW
       (id_date, id_region, id_source, valeur_mw, facteur_charge)
       VALUES (?, ?, 2, ?, ?)""",
    (id_date, id_region, mw, round(mw / 5000, 4)),
)

# Après — ajouter consommation_mw (valeur non-nulle pour certains, NULL pour d'autres)
cursor.execute(
    """INSERT INTO FACT_ENERGY_FLOW
       (id_date, id_region, id_source, valeur_mw, facteur_charge, consommation_mw)
       VALUES (?, ?, 2, ?, ?, ?)""",
    (id_date, id_region, mw, round(mw / 5000, 4), mw * 1.1 if id_region == 1 else None),
)
```
→ Région 1 (id_region=1) aura `consommation_mw` non-nulle, région 2 aura `null` — couvre les deux cas.

**Nouveaux tests à ajouter** dans `TestProductionService` :
```python
def test_query_production_includes_consommation_mw(self, db):
    result = query_production(db, request_id="cons-test")
    record = result["data"][0]
    assert "consommation_mw" in record

def test_query_production_consommation_null_serializable(self, db):
    """NULL consommation_mw must serialize to null JSON, not crash."""
    import json
    result = query_production(db, region_code="84")  # region 2 → NULL consommation
    serialized = json.dumps(result)
    reparsed = json.loads(serialized)
    record = reparsed["data"][0]
    assert "consommation_mw" in record
    assert record["consommation_mw"] is None
```

**Test d'intégration à mettre à jour** dans `TestHTTPIntegration.test_production_200_json_structure` :
```python
for rec in body["data"]:
    assert "code_insee" in rec
    assert "region" in rec
    assert "timestamp" in rec
    assert "sources" in rec
    assert "consommation_mw" in rec  # ← ajouter
```

### Pattern de test établi dans 1.1

- Utiliser `.venv/bin/python -m pytest` (Python 3.11), pas `python3.8`
- SQLite in-memory pour les tests unitaires — valide la logique sans Azure SQL
- `_to_json_safe` déjà testé dans `test_aggregate_rows_datetime_serializable`

### Ordre des modifications

1. `functions/shared/gold/dim_loader.py` — schéma SQLite (ajouter colonne)
2. `functions/shared/api/production_service.py` — SELECT + `_aggregate_rows`
3. `tests/test_api_endpoints.py` — fixture + nouveaux tests + mise à jour assertion d'intégration

### Project Structure Notes

- Fichiers modifiés : 3 fichiers existants, aucun nouveau fichier
- Conventions : `snake_case` pour le champ JSON (`consommation_mw`) — cohérent avec `facteur_charge`, `valeur_mw`
- Le schéma SQLite dans `dim_loader.py` doit rester synchronisé avec SQL Server (c'est un bug préexistant à corriger ici)

### References

- [Source: functions/shared/gold/dim_loader.py:58-69] — schéma SQLite incomplet (sans consommation_mw)
- [Source: functions/shared/gold/dim_loader.py:105-119] — schéma SQL Server avec `consommation_mw DECIMAL(10,2) NULL`
- [Source: functions/shared/api/production_service.py:72-108] — `build_production_query` branches SQLite/SQL Server
- [Source: functions/shared/api/production_service.py:129-155] — `_aggregate_rows` pattern facteur_charge
- [Source: tests/test_api_endpoints.py:53-82] — fixture `db` avec DimLoader
- [Source: _bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 1.2] — ACs
- [Source: _bmad-output/planning-artifacts/architecture.md#Data Architecture] — contexte consommation_mw

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Schéma SQLite `FACT_ENERGY_FLOW` synchronisé avec SQL Server : ajout de `consommation_mw REAL NULL` dans `dim_loader.py`
- `build_production_query` : `f.consommation_mw` ajouté dans les deux branches (SQLite LIMIT et SQL Server TOP)
- `_aggregate_rows` : `consommation_mw` ajouté au niveau région/timestamp (même pattern que `facteur_charge`)
- 2 tests existants (`test_aggregate_rows_pivot`, `test_aggregate_rows_datetime_serializable`) mis à jour pour inclure la nouvelle colonne
- 3 nouveaux tests : présence du champ, valeur non-nulle région 1, valeur NULL région 2 sérialisée en `null` JSON
- Assertion d'intégration `test_production_200_json_structure` mise à jour avec `consommation_mw`
- 269/269 tests passent, 0 régression
- Code review : tests unitaires `build_production_query` renforcés (assert `consommation_mw` dans SQL) ; `test_aggregate_rows_datetime_serializable` complété (assert `consommation_mw == 500.0`) ; magic number retiré (`expected = round(450.0 * 1.1, 2)`) ; docstring `_aggregate_rows` mise à jour

### File List

- `functions/shared/gold/dim_loader.py`
- `functions/shared/api/production_service.py`
- `tests/test_api_endpoints.py`
