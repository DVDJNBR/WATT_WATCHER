# Intégration des prix de marché ENTSO-E — Rapport (branche `FT/PRICES`)

## 1. Pourquoi

Le dashboard affiche un indicateur "Excédent export" calibré sur le ratio
production/consommation national (seuil 40%, cf. `ProdConsChart.jsx`). Ce
seuil avait été choisi en croisant, **manuellement et une seule fois**, les
données RTE 2025 avec les prix négatifs réels du marché EPEX/ENTSO-E — un
calcul ponctuel, pas reproductible, et qui ne peut pas s'améliorer avec le
temps. Cette intégration rend cette donnée de prix **native au pipeline** :
collectée en continu, stockée, documentée, et purgée automatiquement — pour
qu'un futur recalibrage (ou un vrai indicateur de probabilité) parte d'une
vraie table plutôt que d'un export CSV jetable.

**Portée volontairement limitée** : cette itération couvre la collecte, le
nettoyage, le stockage et la rétention. L'exposition (API, dashboard,
visualisations) est explicitement laissée pour une étape suivante, une fois
les autres explications du site retravaillées.

## 2. Ce qui a été ajouté

### 2.1 Client API — `functions/shared/entsoe_client.py`

- Interroge `https://web-api.tp.entsoe.eu/api`, `documentType=A44` (prix
  day-ahead), domaine `10YFR-RTE------C` — **la France est une zone de
  marché unique** (pas de découpage régional côté ENTSO-E ni EPEX), donc
  aucune donnée par région n'existe ni n'existera par ce biais.
- Parse le XML lui-même (`xml.etree.ElementTree`, stdlib — aucune dépendance
  ajoutée) plutôt que de faire confiance à une extraction approximative :
  chaque `Point` (position N dans une `Period`) est converti en timestamp
  exact via `period_start + resolution × (N-1)`.
- Gère les deux résolutions rencontrées dans les données réelles :
  **PT60M (horaire) jusqu'au 30/09/2025**, puis **PT15M (15 min) depuis le
  01/10/2025** — un changement de marché européen généralisé (SDAC MTU
  transition, cf. § 4). `DIM_TIME` supporte déjà le 15 min, aucune migration
  de schéma nécessaire pour ce changement de granularité.
- Distingue une vraie erreur HTTP d'une requête **rejetée mais renvoyée en
  200** (`Acknowledgement_MarketDocument` — ENTSO-E répond ainsi quand la
  plage demandée n'a rien à publier) : la raison exacte est remontée au lieu
  de silencieusement renvoyer une liste vide.

### 2.2 Nettoyage — `functions/shared/transformations/price_silver.py`

Normalisation minimale (c'est déjà une série numérique propre en sortie du
client) : suppression des lignes sans prix, dédoublonnage par timestamp
(garde la valeur la plus récente — les fenêtres de fetch se chevauchent
volontairement, cf. § 2.3), tri chronologique.

### 2.3 Ingestion — `functions/function_app.py`, Stage 7

Ajouté comme 7ᵉ étape non-bloquante de `run_full_pipeline()`, au même rythme
que le reste (toutes les 15 min) :

- Fenêtre de récupération : **26h de lookback** à chaque exécution (marge
  au-delà d'un jour civil pour absorber les décalages horaires/publication),
  avec `ON CONFLICT(id_date) DO UPDATE` — refetcher un créneau déjà en base
  ne fait que le rafraîchir, jamais de doublon.
- Si `ENTSOE_API_TOKEN` n'est pas configuré : l'étape est **silencieusement
  ignorée** (`status: skipped`), le reste du pipeline n'est jamais affecté —
  ce point n'était initialement pas requis mais correspond exactement au
  problème réel qu'on avait sur `MAINTENANCE_SCRAPING_URL` (jamais branché
  dans Terraform, échec quotidien découvert bien après coup) : pour ne pas
  reproduire ce trou, le token est bien déclaré dans `.cloud/variables.tf` /
  `main.tf` cette fois (§ 2.5).

### 2.4 Table Gold — `FACT_MARKET_PRICE`

Ajoutée dans `functions/shared/gold/dim_loader.py` (`DimLoader.ensure_schema()`
— **c'est la vraie source de vérité du schéma en production**, SQLite et
PostgreSQL) et documentée dans `.cloud/sql/init_schema.sql` :

| Colonne | Type | Description |
|---|---|---|
| `id_fact` | BIGSERIAL / INTEGER AUTOINCREMENT | PK |
| `id_date` | INT, FK unique → `DIM_TIME(id_date)` | Un seul prix par créneau — France = zone unique |
| `price_eur_mwh` | NUMERIC(10,2) | Prix day-ahead, EUR/MWh (peut être négatif) |
| `retrieved_at` | TIMESTAMPTZ | Horodatage d'ingestion (traçabilité) |

Volontairement **pas de FK vers `DIM_REGION`** — l'ajouter suggérerait à
tort qu'un découpage régional du prix existe ou existera.

> **Dette documentaire préexistante, non introduite ici** : `init_schema.sql`
> date d'avant la migration Supabase et ne documentait déjà pas
> `fact_meteo`/`fact_capacity`/`fact_maintenance` (créées uniquement à
> l'exécution par `dim_loader.py`). `FACT_MARKET_PRICE` est documentée à sa
> place dans ce fichier ; les trois autres restent à rattraper dans un futur
> passage, hors périmètre de cette branche.

### 2.5 Rétention — `functions/shared/price_retention.py`

Nouveau timer quotidien `price_retention_timer` (02h15 UTC — décalé des deux
autres jobs quotidiens à 01h00 et 06h00) qui purge `FACT_MARKET_PRICE` au-delà
de `PRICE_RETENTION_DAYS` (**7 jours par défaut**, configurable).

- Supprime uniquement dans `FACT_MARKET_PRICE`, **jamais dans `DIM_TIME`**
  (partagée avec `FACT_ENERGY_FLOW` et les autres tables de faits — la
  supprimer casserait leurs clés étrangères). Vérifié explicitement par
  test (`test_does_not_touch_dim_time`).
- Cette table n'est pas pensée comme un historique : c'est un **cache
  vivant** pour le dashboard/la calibration en temps quasi réel. ENTSO-E
  reste la source durable pour toute analyse historique — c'est d'ailleurs
  exactement la méthode utilisée pour calibrer le seuil actuel (§ 4).
- Pourquoi 7 jours et pas 30 : le seul usage prévu à ce stade est un signal
  "récent" pour le dashboard, pas un stockage d'archive. Trivial à changer
  (`PRICE_RETENTION_DAYS=30` dans `terraform.tfvars`) si un usage futur en a
  besoin — aucune migration de schéma requise.

### 2.6 Terraform — `.cloud/variables.tf`, `main.tf`, `terraform.tfvars.example`

- `entsoe_api_token` (sensible, défaut `""` — l'ingestion reste "skip" tant
  qu'il n'est pas renseigné, aucun `terraform apply` existant ne casse).
- `price_retention_days` (défaut `7`).
- Les deux injectées dans `app_settings` du Function App
  (`ENTSOE_API_TOKEN`, `PRICE_RETENTION_DAYS`).

### 2.7 Tests

20 nouveaux tests (191 → 211, tous verts) :

- `tests/test_entsoe_client.py` (10) — résolution horaire et 15 min,
  positions/timestamps exacts, prix négatifs, document d'erreur
  (`Acknowledgement_MarketDocument`), erreurs HTTP, XML malformé, résolution
  inconnue (non-fatale), paramètres de requête exacts.
- `tests/test_price_silver.py` (5) — normalisation, valeurs nulles,
  dédoublonnage, tri.
- `tests/test_price_retention.py` (5) — purge sélective, non-atteinte à
  `DIM_TIME`, cas "rien à purger", lecture de `PRICE_RETENTION_DAYS` via
  l'environnement, valeur par défaut.

## 3. Comment l'activer

1. Compte ENTSO-E (gratuit) : [transparency.entsoe.eu](https://transparency.entsoe.eu/),
   puis email à `transparency@entsoe.eu`, objet `RESTful API access`, corps =
   l'adresse d'inscription. Réponse sous ~3 jours ouvrés, aucune justification
   demandée.
2. Renseigner `entsoe_api_token` dans `terraform.tfvars`, `terraform apply`.
3. Rien d'autre — le prochain run du pipeline (≤15 min) commence à écrire
   dans `FACT_MARKET_PRICE`.

## 4. Contexte : comment le seuil de 40% a été calibré (pour référence)

Ce calcul a été fait manuellement, hors pipeline, avant que cette intégration
n'existe — documenté ici pour qu'il soit reproductible une fois
`FACT_MARKET_PRICE` alimentée en continu.

- **Distribution du ratio national** (année 2025 complète, données RTE
  consolidées) : la production dépasse la consommation de +5% ou plus **98%
  du temps** — la France est structurellement exportatrice (92 TWh nets en
  2025). Un seuil à 5% ne "s'éteint" donc jamais. À 40%, le seuil se
  déclenche ~8% du temps sur l'année — proche des ~9% d'heures à prix
  négatif observées sur EPEX au S1 2026.
- **Croisement jour par jour avec les vrais prix ENTSO-E 2025** (63 jours à
  prix négatif identifiés) :

  | Seuil | Jours déclenchés / an | Précision (prix nég. sachant seuil dépassé) | Rappel (seuil dépassé sachant prix nég.) |
  |---|---|---|---|
  | 5% (ancien) | 100% | 17% | 100% |
  | 20% | 91% | 19% | 100% |
  | 30% | 71% | 24% | 97% |
  | **40% (actuel)** | **45%** | **31%** | **81%** |
  | 50% | 11% | 36% | 22% |

  **40% reste le meilleur compromis simple testé**, mais aucun seuil ne rend
  ce signal fiable au sens strict — c'est un indicateur bruité (bon rappel,
  précision modeste), pas un détecteur. Documenté explicitement sur la page
  "À propos" du site (`OriginPage.jsx`).
- **Limite structurelle, qui ne changera pas avec plus de données** : la
  vraie décision de curtailment se prend au niveau du **poste source**
  (~2300 points, RTE) — une granularité qu'aucune donnée publique
  (eco2mix, `data.rte-france.com`, ENTSO-E) n'expose, avec ou sans compte.
  Le national reste le seul niveau où un prix réel existe (France = zone de
  marché unique), donc le seul niveau qu'on peut honnêtement valider.
- **Méthode d'extraction 2025** : liste des jours à prix négatif obtenue via
  extraction relayée par LLM (`WebFetch`) du XML ENTSO-E, pas un parseur
  exact — fiable au niveau jour/tendance, pas garantie à la minute près
  (notamment autour du changement de résolution du 1ᵉʳ octobre 2025). Le
  client ajouté dans cette branche (§ 2.1) élimine ce risque pour toute
  donnée collectée à partir de maintenant : le calcul position→timestamp est
  fait en code, pas relayé par un modèle.

## 5. Prochaines étapes (hors périmètre de cette branche)

- Retravailler les explications du site (pipeline, architecture) — en cours,
  séparément.
- Une fois `FACT_MARKET_PRICE` alimentée depuis un moment : recalculer la
  précision/rappel du seuil 40% sur données natives au pipeline plutôt que
  sur l'extraction manuelle 2025, et envisager une vraie probabilité par
  requête SQL directe (`FACT_MARKET_PRICE` JOIN sur le ratio national) au
  lieu d'un seuil fixe.
- Rattraper la dette documentaire sur `init_schema.sql` (§ 2.4) si ce fichier
  doit rester une référence à jour.
