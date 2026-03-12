---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-starter', 'step-04-decisions', 'step-05-patterns', 'step-06-structure', 'step-07-validation', 'step-08-complete']
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', '_bmad-output/planning-artifacts/prd-user-accounts-alerts.md', '_bmad-output/planning-artifacts/ux-design-specification.md', 'docs/api_exploration_report.md']
workflowType: 'architecture'
project_name: 'WATT_WATCHER'
user_name: 'David'
date: '2026-03-09'
---

# Architecture Decision Document

_Ce document se construit de manière collaborative, étape par étape. Les sections sont ajoutées au fil des décisions architecturales prises ensemble._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
23 FRs répartis en 5 domaines : auth (FR1-9), abonnements (FR10-13), détection & alertes (FR14-18), RGPD (FR19-21), testabilité ops (FR22-23). Densité élevée sur l'auth — 9 FRs couvrent un flow complet email/password avec confirmation, reset et suppression. La feature de détection (FR14-18) est le cœur métier : timer function autonome, comparaison prod/conso en temps réel, email transactionnel avec déduplication.

**Non-Functional Requirements:**
- Sécurité : bcrypt cost ≥ 12, JWT 24h, tokens confirmation/reset 1h usage unique
- Fiabilité : retry email si échec, déduplication résistante aux retries (contrainte SQL unique)
- Performance : auth < 2s, email < 1h post-détection
- RGPD : inactivité 12 mois → suppression automatique, avertissement J-30

**Scale & Complexity:**
- Primary domain : full-stack brownfield (Azure Functions Python + React)
- Complexity level : medium
- Estimated architectural components : 3 nouvelles tables SQL, 10 endpoints, 6 pages frontend, 1 timer function, 1 provider email tiers

### Technical Constraints & Dependencies

- **[BLOQUANT]** `consommation_mw` absent de l'API Gold → à exposer avant toute implémentation de la détection (FR14-16)
- Infrastructure Azure existante : Function App Python, Azure SQL, React SPA sur Azure Storage Static Website
- Provider email tiers requis (Resend recommandé — gratuit < 3k/mois)
- Pas de changement d'infrastructure cloud — ajout sur stack existante uniquement

### Cross-Cutting Concerns Identified

- **Authentification** : middleware JWT à appliquer sur tous les endpoints `/subscriptions` et `/auth/account` — pattern à définir une fois, réutiliser partout
- **Email transactionnel** : interface découplée provider → faciliter remplacement futur
- **Idempotence** : timer function peut tourner plusieurs fois — toute opération doit être idempotente (déduplication SQL, tokens usage unique)
- **RGPD** : suppression compte doit cascader sur ALERT_SUBSCRIPTION et ALERT_SENT_LOG — contraintes FK avec ON DELETE CASCADE

## Starter Template Evaluation

### Primary Technology Domain

**Full-stack brownfield** — ajout de feature sur infrastructure Azure existante. Pas de starter à initialiser.

### Stack Existante (fondation confirmée)

**Backend :** Python 3.11, Azure Functions v4, Polars, pyodbc (Azure SQL), auth actuelle par API Key statique (`X-Api-Key`)

**Frontend :** React 18 + Vite, CSS custom properties + glassmorphism, react-simple-maps, Recharts — déployé sur Azure Storage Static Website

**Base de données :** Azure SQL — tables Gold existantes : fact_production, dim_region, dim_source

**CI/CD :** GitHub Actions (`deploy.yml`) → Azure Functions + Azure Storage, semantic-release

**Infrastructure :** Terraform (`.cloud/`) pour provisioning Azure

### Décisions Architecturales Héritées

| Domaine | Décision existante | Impact nouvelle feature |
|---|---|---|
| Auth | API Key statique | À remplacer/compléter par JWT pour endpoints user |
| BDD | Azure SQL | Nouvelles tables USER_ACCOUNT, ALERT_SUBSCRIPTION, ALERT_SENT_LOG |
| Email | Aucun | Nouveau : provider tiers (Resend) |
| Sessions | Aucune (stateless) | Nouveau : JWT 24h |
| Frontend routing | SPA sans router | Nouveau : React Router pour /login, /register, etc. |

## Core Architectural Decisions

### Decision Priority Analysis

**Critical (bloquent l'implémentation) :**
- Exposer `consommation_mw` dans l'API Gold avant FR14-16
- JWT middleware pattern défini avant tout endpoint auth

**Important (structurent l'architecture) :**
- PyJWT pour les tokens, localStorage pour le stockage frontend
- React Router v6 pour le routing SPA
- Context API pour l'état auth

**Différé (post-MVP) :**
- Migration vers httpOnly cookies pour la sécurité token en production
- Alembic pour les migrations SQL si le projet scale

### Data Architecture

- **Nouvelles tables** : USER_ACCOUNT, ALERT_SUBSCRIPTION, ALERT_SENT_LOG — Azure SQL existant
- **Migrations** : scripts SQL versionnés dans `functions/migrations/` — exécution manuelle ou CI
- **FK + cascade** : `USER_ACCOUNT` → cascade DELETE sur ALERT_SUBSCRIPTION et ALERT_SENT_LOG (RGPD)
- **Déduplication** : contrainte UNIQUE sur `(user_id, region_code, alert_type, DATE(sent_at))` dans ALERT_SENT_LOG
- **Dépendance bloquante** : colonne `consommation_mw` à exposer dans l'endpoint `/v1/production/regional` avant implémentation de la détection

### Authentication & Security

- **JWT library** : PyJWT (Python backend) — HS256, expiration 24h
- **Token storage** : localStorage (frontend) — acceptable pour prototype étudiant, à migrer vers httpOnly cookie en production
- **Tokens confirmation/reset** : UUID v4, usage unique, expiration 1h, invalidés en BDD après utilisation
- **Password hashing** : bcrypt, cost factor ≥ 12
- **Coexistence auth** : endpoints existants (`/v1/production/*`) conservent l'API Key statique — nouveaux endpoints (`/v1/auth/*`, `/v1/subscriptions`) utilisent JWT — pas de breaking change

### API & Communication Patterns

- **Pattern** : REST (cohérent avec l'existant)
- **Middleware JWT** : décorateur Python réutilisable sur chaque Azure Function nécessitant auth
- **Email provider** : Resend — interface Python découplée (classe `EmailService`) pour faciliter le remplacement futur
- **Error handling** : format JSON uniforme `{ "error": "...", "request_id": "..." }` — cohérent avec les endpoints existants

### Frontend Architecture

- **Router** : React Router v6 — routes publiques (`/`, `/login`, `/register`, `/confirm`, `/reset-password`) et routes protégées (`/subscriptions`, `/settings`)
- **Auth state** : Context API (`AuthContext`) — fournit `user`, `token`, `login()`, `logout()` à toute l'app
- **Forms** : React state natif — pas de librairie (formulaires simples)
- **Composants réutilisés** : `FranceMap` existant réutilisé sur la page `/subscriptions` pour la sélection des régions

### Infrastructure & Deployment

- **Aucune nouvelle infrastructure Azure** — tout s'ajoute sur la stack existante
- **Secrets** : clé API Resend stockée dans Azure Key Vault (pattern existant)
- **Timer function** : nouvelle Azure Function à déclenchement horaire (cron `0 0 * * * *`) — s'ajoute dans `function_app.py`
- **CI/CD** : pipeline GitHub Actions existant inchangé

### Decision Impact Analysis

**Séquence d'implémentation recommandée :**
1. Migrations SQL (tables USER_ACCOUNT, ALERT_SUBSCRIPTION, ALERT_SENT_LOG)
2. Exposer `consommation_mw` dans l'API Gold (déblocage FR14-16)
3. Endpoints auth backend (register → confirm → login → logout → reset → delete)
4. Middleware JWT Python
5. Frontend : React Router + AuthContext + pages auth
6. Page abonnements (réutilise FranceMap)
7. Timer function détection + EmailService + envoi alertes

**Dépendances critiques :**
- Timer function dépend de `consommation_mw` dans l'API ET des tables SQL ET d'EmailService
- Page `/subscriptions` dépend du JWT middleware ET de React Router

## Implementation Patterns & Consistency Rules

### Naming Patterns

**Base de données — SCREAMING_SNAKE_CASE** (cohérent avec `FACT_ENERGY_FLOW`, `DIM_REGION`, `DIM_TIME`, `DIM_SOURCE` existants) :
- Tables : `USER_ACCOUNT`, `ALERT_SUBSCRIPTION`, `ALERT_SENT_LOG`
- Colonnes : `snake_case` — ex. `user_id`, `region_code`, `sent_at`
- FK : `{table_singulier}_id` — ex. `user_id` dans ALERT_SUBSCRIPTION
- Index : `IX_{TABLE}_{colonne}` — ex. `IX_USER_ACCOUNT_email`

**API endpoints — kebab-case, versionnés :**
- Pattern : `/api/v1/{ressource}/{action_optionnelle}`
- Exemples : `/v1/auth/register`, `/v1/auth/reset-password/request`, `/v1/subscriptions`
- Query params : `snake_case` — ex. `region_code`, `start_date`
- Headers : `X-Api-Key` (endpoints existants), `Authorization: Bearer {token}` (nouveaux endpoints)

**Code Python :** `snake_case` fonctions/variables, `PascalCase` classes, `snake_case.py` fichiers

**Code JS/JSX :** `PascalCase.jsx` composants, `use{Nom}.js` hooks, `camelCase.js` services

### Format Patterns

**Réponse API succès :** `{ "data": [...], "total_records": 42, "request_id": "uuid" }`

**Réponse API erreur :** `{ "error": "message lisible", "request_id": "uuid" }`

**Dates :** ISO 8601 UTC partout — `"2026-03-09T14:30:00Z"` — jamais de timestamp Unix

**JSON fields :** toujours `snake_case` côté API

### Process Patterns

**Gestion d'erreurs backend :** HTTP 400/401/403/404/500 — toujours `request_id` dans la réponse — logger l'erreur complète côté serveur, message générique côté client pour les 500

**Loading states frontend :** prop `loading` booléenne (pattern existant `FranceMap`) + skeleton placeholder `<div className="skeleton">`

**Auth flow frontend :** token JWT dans `localStorage` clé `watt_watcher_token` — `AuthContext` expose `{ user, token, login(), logout() }` — redirect `/login` si non authentifié

**Idempotence timer function :** vérifier `ALERT_SENT_LOG` avant tout envoi — logger détection, envoi réussi, skip déduplication

### Enforcement

Tout agent IA DOIT :
- Nommer les tables SQL en `SCREAMING_SNAKE_CASE`
- Retourner `request_id` dans toutes les réponses API
- Utiliser `AuthContext` pour l'état auth (pas de gestion locale du token)
- Vérifier la déduplication avant tout envoi d'email d'alerte

## Project Structure & Boundaries

### Nouveaux fichiers à créer

```
functions/
├── function_app.py                        [MODIFY] +routes auth, +timer function horaire
├── shared/
│   ├── api/
│   │   ├── auth.py                        [MODIFY] remplacer API Key par décorateur @require_jwt
│   │   ├── auth_service.py                [NEW] logique register/login/confirm/reset/delete
│   │   ├── subscription_service.py        [NEW] GET+PUT /v1/subscriptions
│   │   ├── production_service.py          [MODIFY] exposer consommation_mw
│   │   └── email_service.py               [NEW] interface EmailService (Resend)
│   └── alerting/
│       └── alert_detector.py              [NEW] détection croisement prod/conso
└── migrations/                            [NEW] scripts SQL versionnés
    ├── 001_create_user_account.sql
    ├── 002_create_alert_subscription.sql
    └── 003_create_alert_sent_log.sql

frontend/src/
├── App.jsx                                [MODIFY] +React Router, +AuthContext provider
├── contexts/
│   └── AuthContext.jsx                    [NEW] { user, token, login(), logout() }
├── pages/                                 [NEW]
│   ├── LoginPage.jsx
│   ├── RegisterPage.jsx
│   ├── ConfirmPage.jsx
│   ├── ResetPasswordPage.jsx
│   ├── SubscriptionsPage.jsx              réutilise FranceMap existant
│   └── SettingsPage.jsx
└── services/
    └── auth.js                            [REPLACE] Azure AD MSAL → JWT localStorage
```

### Architectural Boundaries

| Boundary | Règle |
|---|---|
| `shared/api/auth.py` | Décorateur `@require_jwt` — middleware réutilisable, pas de logique métier |
| `shared/api/auth_service.py` | Toute la logique auth — register, confirm, login, reset, delete |
| `shared/api/email_service.py` | Interface `EmailService` — Resend en prod, mock en test |
| `shared/alerting/alert_detector.py` | Détection croisement prod/conso — indépendant d'`alert_engine.py` |
| `AuthContext.jsx` | Source de vérité unique du state auth — pas de lecture directe de localStorage ailleurs |
| `migrations/` | Scripts SQL idempotents (`IF NOT EXISTS`), ordonnés numériquement |

### Note de migration

`services/auth.js` (Azure AD MSAL.js) est **remplacé** par l'implémentation JWT email/password. Les variables `VITE_AZURE_AD_*` deviennent caduques.

## Architecture Validation

### Couverture des FRs

| Catégorie | FRs | Support architectural |
|---|---|---|
| Auth | FR1-9 | `auth_service.py` + `@require_jwt` + pages auth + `AuthContext` |
| Abonnements | FR10-13 | `subscription_service.py` + `SubscriptionsPage.jsx` + `ALERT_SUBSCRIPTION` |
| Détection alertes | FR14-16 | `alert_detector.py` + timer horaire + `consommation_mw` exposé |
| Déduplication | FR17 | Contrainte UNIQUE SQL sur `ALERT_SENT_LOG` |
| Contenu email | FR18 | `email_service.py` + templates Resend |
| RGPD | FR19-21 | `last_activity` + cascade FK + timer RGPD |
| Testabilité | FR22-23 | `functions/scripts/inject_test_data.py` |

NFRs : bcrypt ✅ · JWT 24h ✅ · email < 1h (timer horaire) ✅ · déduplication idempotente ✅ · HTTPS (Azure) ✅

### Gaps & Risques

| Priorité | Gap | Résolution |
|---|---|---|
| 🔴 Critique | `consommation_mw` absent de l'API Gold | Story de prerequis — première à implémenter |
| 🟡 Important | Script injection test données (FR22-23) | `functions/scripts/inject_test_data.py` |
| 🟢 Mineur | Variables `VITE_AZURE_AD_*` à nettoyer | Lors du remplacement de `auth.js` |

### Statut : PRÊT POUR IMPLÉMENTATION

**Première priorité :** migrations SQL + exposition `consommation_mw` dans l'API Gold
