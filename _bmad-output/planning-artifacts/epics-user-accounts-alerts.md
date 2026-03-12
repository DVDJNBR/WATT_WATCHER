# Epics & Stories — User Accounts & Alert Subscriptions

**Feature:** User Accounts & Alert Subscriptions
**PRD:** prd-user-accounts-alerts.md
**Architecture:** architecture.md
**Date:** 2026-03-09

---

## Epic 1: Foundation — Database & API Prerequisites

**Goal:** Créer les tables SQL nécessaires et exposer `consommation_mw` dans l'API Gold. Prérequis bloquant pour toutes les autres epics.

### Story 1.1: SQL Migrations

As a developer, I want the three new SQL tables created in Azure SQL, so that user accounts, subscriptions, and alert logs can be persisted.

**Acceptance Criteria:**
- Migration `001_create_user_account.sql` crée la table `USER_ACCOUNT` avec toutes les colonnes (id, email, password_hash, is_confirmed, confirmation_token, reset_token, reset_token_expires, last_activity, created_at)
- Migration `002_create_alert_subscription.sql` crée `ALERT_SUBSCRIPTION` (id, user_id FK, region_code, alert_type, is_active, created_at) avec ON DELETE CASCADE
- Migration `003_create_alert_sent_log.sql` crée `ALERT_SENT_LOG` (id, user_id FK, region_code, alert_type, sent_at) avec contrainte UNIQUE sur (user_id, region_code, alert_type, DATE(sent_at)) et ON DELETE CASCADE
- Les scripts sont idempotents (`IF NOT EXISTS`)
- Les scripts sont dans `functions/migrations/` et numérotés

### Story 1.2: Expose consommation_mw in Production API

As a developer, I want `consommation_mw` exposed in the `/v1/production/regional` endpoint, so that the alert detector can compare production vs consumption.

**Acceptance Criteria:**
- La colonne `consommation_mw` est lue depuis `FACT_ENERGY_FLOW` dans `production_service.py`
- Le champ `consommation_mw` apparaît dans la réponse JSON de `/v1/production/regional`
- Les tests existants passent toujours
- La valeur peut être nulle (données RTE parfois absentes)

---

## Epic 2: Authentication Backend

**Goal:** Implémenter tous les endpoints d'authentification côté Azure Functions Python, avec JWT middleware réutilisable.

### Story 2.1: JWT Middleware

As a developer, I want a reusable `@require_jwt` decorator for Azure Functions, so that protected endpoints can validate tokens consistently.

**Acceptance Criteria:**
- Décorateur `@require_jwt` dans `functions/shared/api/auth.py` (remplace l'ancien middleware API Key pour les nouveaux endpoints)
- Vérifie `Authorization: Bearer <token>` header
- Retourne 401 si token absent ou invalide
- Retourne le payload décodé (`user_id`, `email`) accessible dans la fonction
- Utilise PyJWT avec algorithme HS256
- Secret JWT lu depuis Azure Key Vault (clé `JWT_SECRET`)
- Tests unitaires couvrent: token valide, token expiré, token absent, token malformé

### Story 2.2: Register & Email Confirmation Endpoints

As a new user, I want to register with email and password and confirm my account via email, so that I can access the platform.

**Acceptance Criteria:**
- `POST /v1/auth/register` : crée compte avec bcrypt cost=12, envoie email de confirmation, retourne 201
- `POST /v1/auth/confirm` : active le compte via token UUID v4, invalide le token après usage, retourne 200
- `POST /v1/auth/resend-confirmation` : renvoie l'email si compte non confirmé, retourne 200
- Email non confirmé → login impossible (retourne 403 avec message explicite)
- Token confirmation expire après 1h
- Email déjà existant → 409 Conflict
- Validation format email côté serveur

### Story 2.3: Login & Logout Endpoints

As a confirmed user, I want to login with email/password and logout, so that I can access protected features and end my session.

**Acceptance Criteria:**
- `POST /v1/auth/login` : vérifie bcrypt hash, retourne JWT 24h + `{ user_id, email, token }`
- `POST /v1/auth/logout` : endpoint symbolique (JWT stateless), retourne 200
- Mauvais mot de passe → 401 (message générique, pas de leak d'info)
- Compte non confirmé → 403

### Story 2.4: Reset Password Endpoints

As a user who forgot their password, I want to reset it via email link, so that I can regain access to my account.

**Acceptance Criteria:**
- `POST /v1/auth/reset-password/request` : envoie email avec token reset si email existe (toujours 200, même si email inconnu — pas de leak)
- `POST /v1/auth/reset-password/confirm` : nouveau mot de passe via token, invalide le token, retourne 200
- Token reset expire après 1h, usage unique
- Nouveau mot de passe hashé bcrypt cost=12

### Story 2.5: Delete Account Endpoint

As a connected user, I want to delete my account permanently, so that my data is removed (RGPD).

**Acceptance Criteria:**
- `DELETE /v1/auth/account` : protégé par `@require_jwt`
- Supprime `USER_ACCOUNT` → cascade sur `ALERT_SUBSCRIPTION` et `ALERT_SENT_LOG`
- Retourne 204 No Content
- Test: vérifier que les tables liées sont bien vidées

---

## Epic 3: Authentication Frontend

**Goal:** Intégrer React Router v6, AuthContext, et toutes les pages d'authentification dans le frontend React existant.

### Story 3.1: React Router & AuthContext Setup

As a developer, I want React Router v6 and AuthContext integrated in the app, so that navigation and auth state work consistently across all pages.

**Acceptance Criteria:**
- `react-router-dom` v6 installé
- `App.jsx` wrappé avec `<BrowserRouter>` et `<AuthProvider>`
- `AuthContext.jsx` dans `frontend/src/contexts/` expose `{ user, token, login(token, user), logout() }`
- Token stocké/lu depuis `localStorage` clé `watt_watcher_token`
- Routes publiques et protégées définies (`ProtectedRoute` component)
- La page dashboard existante (`/`) reste accessible sans auth
- `services/auth.js` (MSAL Azure AD) remplacé par implémentation JWT simple
- Variables `VITE_AZURE_AD_*` retirées du `.env`

### Story 3.2: Login & Register Pages

As a visitor, I want to register and login via dedicated pages, so that I can create and access my account.

**Acceptance Criteria:**
- `RegisterPage.jsx` : formulaire email + password + confirm password, appelle `POST /v1/auth/register`, affiche message "Vérifiez votre email"
- `LoginPage.jsx` : formulaire email + password, appelle `POST /v1/auth/login`, stocke token dans AuthContext, redirige vers `/`
- Lien "Mot de passe oublié ?" sur LoginPage → `/reset-password`
- Lien "Pas de compte ? S'inscrire" sur LoginPage → `/register`
- Gestion erreurs : affichage inline sous le champ concerné
- Style cohérent avec le design system existant (glassmorphism, dark mode)

### Story 3.3: Confirm & Reset Password Pages

As a user, I want to confirm my email and reset my password via dedicated pages, so that account setup and recovery work end-to-end.

**Acceptance Criteria:**
- `ConfirmPage.jsx` : lit `?token=` depuis URL, appelle `POST /v1/auth/confirm`, affiche succès ou erreur
- `ResetPasswordPage.jsx` : mode "demande" (formulaire email) et mode "nouveau MDP" (si `?token=` présent)
- Succès confirmation → lien vers `/login`
- Succès reset → lien vers `/login`

### Story 3.4: Settings Page

As a connected user, I want a settings page to delete my account, so that I can exercise my RGPD rights.

**Acceptance Criteria:**
- `SettingsPage.jsx` accessible via `/settings`, protégée (redirect `/login` si non connecté)
- Bouton "Supprimer mon compte" avec confirmation dialog
- Appelle `DELETE /v1/auth/account`, puis `logout()` et redirect `/`
- Lien vers Settings visible dans le header quand connecté

---

## Epic 4: Alert Subscriptions

**Goal:** Permettre à un utilisateur connecté de gérer ses abonnements aux alertes par région.

### Story 4.1: Subscriptions API

As a connected user, I want to manage my alert subscriptions via API, so that my preferences are persisted.

**Acceptance Criteria:**
- `GET /v1/subscriptions` : retourne les abonnements actifs de l'utilisateur connecté
- `PUT /v1/subscriptions` : met à jour les abonnements (remplace la liste complète)
- Les deux endpoints protégés par `@require_jwt`
- Format : `[{ region_code, alert_type, is_active }]`
- `subscription_service.py` dans `functions/shared/api/`

### Story 4.2: Subscriptions Page

As a connected user, I want a visual subscriptions page with the France map, so that I can easily select regions and alert types.

**Acceptance Criteria:**
- `SubscriptionsPage.jsx` accessible via `/subscriptions`, protégée
- Réutilise le composant `FranceMap` existant pour la sélection des régions
- Clic sur région → panel latéral avec toggles "Sous-production" et "Sur-production"
- Bouton Sauvegarder → appelle `PUT /v1/subscriptions`
- Feedback visuel (succès/erreur) après sauvegarde
- Lien vers Subscriptions visible dans le header quand connecté

---

## Epic 5: Alert Detection & Email

**Goal:** Implémenter la détection automatique des croisements prod/conso et l'envoi d'emails d'alerte via Resend.

### Story 5.1: Email Service (Resend)

As a developer, I want a decoupled EmailService using Resend, so that transactional emails can be sent and easily replaced.

**Acceptance Criteria:**
- `email_service.py` dans `functions/shared/api/` avec classe `EmailService`
- Méthodes : `send_confirmation(email, token)`, `send_reset(email, token)`, `send_alert(email, region, alert_type, prod_mw, conso_mw)`
- Clé API Resend dans Azure Key Vault (clé `RESEND_API_KEY`)
- Mode mock/test activable via env var `EMAIL_MOCK=true` (log au lieu d'envoyer)
- Tests unitaires avec mock

### Story 5.2: Alert Detector

As a system, I want to detect when production crosses consumption for a region, so that alerts can be triggered at the right moment.

**Acceptance Criteria:**
- `alert_detector.py` dans `functions/shared/alerting/`
- Lit les données Gold les plus récentes depuis `FACT_ENERGY_FLOW` (production + consommation par région)
- Détecte les croisements : `under_production` (prod < conso) et `over_production` (prod > conso)
- Retourne liste de `{ region_code, alert_type, prod_mw, conso_mw }` pour les régions en déséquilibre
- Gère les valeurs nulles (skip si consommation absente)
- Tests unitaires avec données mockées

### Story 5.3: Alert Timer Function

As a system, I want an hourly timer function that orchestrates detection and email sending with deduplication, so that users receive timely and non-spammy alerts.

**Acceptance Criteria:**
- Nouvelle Azure Function timer dans `function_app.py`, déclenchement horaire (`0 0 * * * *`)
- Séquence : `AlertDetector.detect()` → pour chaque alerte → check `ALERT_SENT_LOG` → si pas envoyé aujourd'hui → `EmailService.send_alert()` → insérer dans `ALERT_SENT_LOG`
- Déduplication : contrainte UNIQUE SQL sur `(user_id, region_code, alert_type, DATE(sent_at))`
- Si envoi email échoue → log erreur, ne pas insérer dans `ALERT_SENT_LOG` (retry au prochain cycle)
- Logs : détection, envoi réussi, skip déduplication

---

## Epic 6: RGPD & Operational Testing

**Goal:** Implémenter la suppression automatique RGPD des comptes inactifs et le script de test d'injection.

### Story 6.1: RGPD Inactivity Cleanup

As a system, I want inactive accounts to be automatically deleted after 12 months with a 30-day warning email, so that RGPD compliance is maintained.

**Acceptance Criteria:**
- `last_activity` mis à jour à chaque login et modification d'abonnement
- Timer function quotidienne (ou ajout au timer existant) : détecte comptes inactifs depuis 11 mois → envoie email avertissement
- Détecte comptes inactifs depuis 12 mois → suppression (cascade FK)
- Log de chaque suppression

### Story 6.2: Test Injection Script

As an admin, I want a script to inject fake production/consumption data that triggers alerts, so that I can validate the alert pipeline without waiting for real events.

**Acceptance Criteria:**
- Script `functions/scripts/inject_test_data.py`
- Mode inject : insère des données Gold simulant une sous-production ou sur-production dans une région cible
- Mode restore : remet les données réelles (ou supprime les données injectées)
- Documentation d'utilisation dans le script
- Utilisable en local et via invocation Azure
