# API Exploration Report — Story 0.1

**Date:** 2026-02-25
**Script:** `scripts/explore_rte_api.py`

---

## 1. API Discovery

| Property           | Value                                                             |
| ------------------ | ----------------------------------------------------------------- |
| **Provider**       | Opendatasoft (ODRE)                                               |
| **Base URL**       | `https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets` |
| **Auth**           | ⚠️ **PUBLIC — aucune authentification requise**                   |
| **Protocol**       | REST / JSON                                                       |
| **Query language** | ODSQL (where, order_by, select, group_by)                         |
| **Rate limit**     | 50,000 calls/month (estimated)                                    |

### Datasets

| Dataset ID                  | Type                | Records | Usage                   |
| --------------------------- | ------------------- | ------- | ----------------------- |
| `eco2mix-regional-tr`       | Temps réel régional | ~485K   | **Primary** — Story 1.1 |
| `eco2mix-national-tr`       | Temps réel national | ~40K    | Référence               |
| `eco2mix-regional-cons-def` | Consolidé régional  | ~2.5M   | Historique              |

---

## 2. Regional Real-Time Fields (eco2mix-regional-tr)

### Identifiers

| Field               | Type          | Sample                        |
| ------------------- | ------------- | ----------------------------- |
| `code_insee_region` | str           | `"75"`                        |
| `libelle_region`    | str           | `"Nouvelle-Aquitaine"`        |
| `nature`            | str           | `"Données temps réel"`        |
| `date`              | str           | `"2025-02-20"`                |
| `heure`             | str           | `"10:30"`                     |
| `date_heure`        | str (ISO8601) | `"2025-02-20T09:30:00+00:00"` |

### Production (MW)

| Field                 | Type    | Sample | In CONCEPTION?       |
| --------------------- | ------- | ------ | -------------------- |
| `consommation`        | int     | 5032   | ✅                   |
| `thermique`           | int     | 103    | ❌ (was `fioul+gaz`) |
| `nucleaire`           | int     | 5800   | ✅                   |
| `eolien`              | int     | 576    | ✅                   |
| `solaire`             | int     | 2006   | ✅                   |
| `hydraulique`         | int     | 682    | ✅                   |
| `pompage`             | str/int | 0      | ✅                   |
| `bioenergies`         | int     | 29     | ✅                   |
| `ech_physiques`       | int     | -4166  | ❌ (new)             |
| `stockage_batterie`   | str/int | 0      | ❌ (new)             |
| `destockage_batterie` | str/int | 0      | ❌ (new)             |

### Taux (% — BONUS, not in CONCEPTION)

| Field          | Type  | Meaning                                                          |
| -------------- | ----- | ---------------------------------------------------------------- |
| `tco_{source}` | float | Taux de couverture (% de la consommation)                        |
| `tch_{source}` | float | Taux de charge (% de la capacité installée) = **facteur_charge** |

Sources avec tco/tch: thermique, nucleaire, eolien, solaire, hydraulique, bioenergies.

### Artifact fields

| Field       | Notes                          |
| ----------- | ------------------------------ |
| `column_68` | Always null — artifact, ignore |

---

## 3. Regions Discovered (12)

| Code INSEE | Région                     |
| ---------- | -------------------------- |
| 11         | Île-de-France              |
| 24         | Centre-Val de Loire        |
| 27         | Bourgogne-Franche-Comté    |
| 28         | Normandie                  |
| 32         | Hauts-de-France            |
| 44         | Grand Est                  |
| 52         | Pays de la Loire           |
| 53         | Bretagne                   |
| 75         | Nouvelle-Aquitaine         |
| 76         | Occitanie                  |
| 84         | Auvergne-Rhône-Alpes       |
| 93         | Provence-Alpes-Côte d'Azur |

---

## 4. Schema Decisions

| Decision                                              | Rationale                                                                                 |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `thermique` au lieu de `fioul`/`gaz`                  | L'API régionale fournit `thermique` (agrégé). `fioul`/`charbon`/`gaz` sont national only. |
| Ajout `taux_couverture`/`taux_charge` dans FACT       | L'API fournit ces métriques — inutile de les recalculer.                                  |
| Ajout `consommation_mw`, `ech_physiques_mw` dans FACT | Valeurs clés pour alertes surproduction (Story 5.2).                                      |
| `prix_mwh` = NULL                                     | Source EPEX SPOT hors scope MVP.                                                          |
| `temperature_moyenne` = NULL                          | Source ERA5, future (Story 2.2).                                                          |
| Auth = none                                           | L'API Opendatasoft est publique. Simplifie Story 1.1.                                     |
| `pompage` type incohérent (str/int)                   | Nettoyage nécessaire en Silver (Story 3.1).                                               |

---

## 5. Deliverables

| File                                              | Status         |
| ------------------------------------------------- | -------------- |
| `scripts/explore_rte_api.py`                      | ✅             |
| `tests/fixtures/rte_eco2mix_regional_sample.json` | ✅             |
| `tests/fixtures/rte_eco2mix_national_sample.json` | ✅             |
| `infra/sql/init_schema.sql`                       | ✅             |
| `infra/sql/seed_dimensions.sql`                   | ✅             |
| `docs/api_exploration_report.md`                  | ✅ (this file) |
