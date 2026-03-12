---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', '_bmad-output/implementation-artifacts/5-2-over-production-negative-price-alerts.md', '_bmad-output/planning-artifacts/ux-design-specification.md']
workflowType: 'prd'
documentCounts:
  briefCount: 0
  researchCount: 0
  brainstormingCount: 0
  projectDocsCount: 3
classification:
  projectType: 'fullstack_feature'
  domain: 'energy_monitoring'
  complexity: 'medium'
  projectContext: 'brownfield'
---

# Product Requirements Document - WATT WATCHER : User Accounts & Alert Subscriptions

**Author:** David
**Date:** 2026-03-09

## Executive Summary

**User Accounts & Alert Subscriptions** est une feature ajoutée à Watt Watcher qui transforme la plateforme d'un outil de consultation passif en un système de veille énergétique proactif. Elle cible principalement les gestionnaires de parcs énergétiques qui ont besoin d'être notifiés automatiquement quand leur région bascule en situation de déséquilibre (sous-production ou sur-production), sans avoir à surveiller activement le dashboard.

Tout utilisateur disposant du lien de l'application peut créer un compte (email + mot de passe, confirmation par mail). Une fois inscrit, il configure ses abonnements : il sélectionne une ou plusieurs régions françaises et choisit les types d'événements à surveiller. Le système envoie un email par région et par type d'événement, au maximum une fois par jour, dès qu'un déséquilibre commence.

### Proposition de Valeur

L'alerte est déclenchée par un **événement métier réel** — le croisement entre production et consommation régionale — et non par un seuil arbitraire en MW. Pour un gestionnaire de parc éolien breton, recevoir un mail "la Bretagne est passée en sous-production" est directement actionnable. L'email embarque les données clés (région, type d'événement, valeurs production/consommation) pour permettre une décision sans ouvrir le dashboard.

Feature full-stack brownfield (Azure Functions Python + React) de complexité medium. Dépendance critique : vérifier l'exposition de `consommation` dans l'API Gold avant démarrage.

## Success Criteria

### User Success
- Un utilisateur s'inscrit, confirme son email, configure ses abonnements en moins de 5 minutes
- Quand un croisement production/consommation se produit sur une région abonnée, l'utilisateur reçoit un email avec les données clés (région, type d'événement, valeurs) sans avoir à ouvrir le dashboard

### Business Success
- Projet étudiant — le succès c'est la démo : le jury voit un email d'alerte arriver en live ou via scénario de test contrôlé

### Technical Success
- Email envoyé dans l'heure suivant le déclenchement de l'alerte
- Max 1 email/jour/région/type pour éviter le spam
- Testabilité : un script d'injection de données erronées permet de forcer le déclenchement d'une alerte, vérifier la réception email, puis restaurer les données réelles

### Measurable Outcomes
- ✅ Inscription + confirmation email : fonctionne end-to-end
- ✅ Abonnement multi-régions : configurable par l'utilisateur
- ✅ Alerte sous-production (prod < conso) : email envoyé < 1h
- ✅ Alerte sur-production (prod > conso) : email envoyé < 1h
- ✅ Déduplication : pas de doublon sur la même journée

## Product Scope

### MVP
- Auth email/mot de passe + confirmation par mail
- Page de gestion des abonnements (sélection régions + type d'alerte)
- Détection croisement prod/conso + envoi email
- Déduplication 1/jour/région/type
- Script de test d'injection

### Growth (Post-MVP)
- Résumé hebdomadaire par email
- Préférences horaires (ne pas recevoir la nuit)
- Dashboard "mes alertes" dans l'app

### Vision
- Canaux additionnels (SMS, push, webhook)
- Seuils personnalisés en complément du croisement prod/conso

## User Journeys

### Journey 1 — Sophie, gestionnaire de parc éolien en Bretagne *(primary user, success path)*

Sophie gère un parc éolien de 12 turbines en Ille-et-Vilaine. Son problème quotidien : elle doit checker manuellement plusieurs outils pour savoir si sa région produit à sa juste valeur. Un collègue lui envoie le lien de Watt Watcher.

**Inscription** → Elle ouvre l'app, clique "Créer un compte", entre son email pro + mot de passe. Un mail de confirmation arrive dans la minute — elle clique le lien, son compte est activé.

**Configuration** → Elle accède à "Mes abonnements", voit la carte France, coche "Bretagne". Elle active les deux types d'alertes : sous-production et sur-production. Sauvegarde.

**Moment de valeur** → Trois jours plus tard, 9h14 : elle reçoit un email "⚡ Bretagne — Sous-production détectée". Le mail affiche : production 412 MW vs consommation 680 MW, déficit de 268 MW. Elle appelle son responsable de réseau immédiatement. Pas besoin d'ouvrir le dashboard.

**Nouvelle réalité** → Sophie consulte le dashboard en profondeur une fois par semaine, mais est alertée au bon moment chaque jour si nécessaire.

### Journey 2 — Marc, curieux sans compte *(primary user, edge case)*

Marc a eu le lien par un ami. Il s'inscrit, entre son email perso... mais il ne confirme jamais le mail de confirmation (parti dans ses spams).

**Blocage** → Il essaie de se connecter : message "Confirmez votre email avant de vous connecter". Il clique "Renvoyer l'email de confirmation". Cette fois il le retrouve, clique le lien. Compte activé.

**Frustration évitée** → Le re-send est disponible immédiatement depuis la page de connexion, pas de dead-end.

### Journey 3 — David, admin/ops *(secondary user)*

David a déployé l'app. Un jour, les alertes ne partent plus — panne du service email.

**Investigation** → Il vérifie les logs Azure Functions, voit les erreurs SMTP. Il corrige la config du provider email. Il lance le script d'injection de données test, un email d'alerte arrive dans les 10 minutes. Tout est reparti.

**Contrôle** → David peut forcer le déclenchement d'une alerte à tout moment via le script de test pour valider le end-to-end sans attendre un vrai événement de croisement.

### Journey Requirements Summary

| Journey | Capabilities requises |
|---|---|
| Sophie inscription | Auth email/password, confirmation mail, session |
| Sophie abonnements | Page abonnements, sélection régions, types d'alerte |
| Sophie alerte | Détection croisement prod/conso, email formaté, déduplication |
| Marc edge case | Renvoi email confirmation, message d'erreur clair |
| David ops | Script test injection, logs, config email provider |

## Domain-Specific Requirements

### Compliance & Réglementaire (RGPD)
- Seule donnée personnelle stockée : email + mot de passe hashé (bcrypt)
- Droit à la suppression : bouton "Supprimer mon compte" accessible depuis les settings utilisateur
- Rétention automatique : colonne `last_activity` mise à jour à chaque connexion ou modification d'abonnement — suppression automatique après 12 mois d'inactivité
- Avertissement pré-suppression : email envoyé 30 jours avant la suppression automatique, permettant à l'utilisateur de se reconnecter pour conserver son compte
- Données RTE (production/consommation) : données publiques open data, hors scope RGPD

### Contraintes Techniques
- Mots de passe : hashage bcrypt obligatoire, jamais stockés en clair
- Email transactionnel : configuration SPF/DKIM pour la délivrabilité
- Reset password : flow complet inclus en MVP (lien temporaire par email, expiration 1h)
- Sessions : token JWT ou équivalent, expiration configurable

## Full-Stack Feature Specific Requirements

### Architecture Considerations

Feature ajoutée sur l'infrastructure Azure existante :
- **Backend** : nouvelles Azure Functions (Python) dans le `function_app.py` existant
- **Base de données** : nouvelles tables dans l'Azure SQL existant (pas de nouvelle BDD)
- **Frontend** : nouvelles pages React dans l'app Watt Watcher existante
- **Email** : provider tiers dédié (ex. Resend ou SendGrid) — SMTP direct déconseillé

### Nouveaux Endpoints API

| Méthode | Route | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Inscription email + password |
| POST | `/api/v1/auth/confirm` | Confirmation email (token) |
| POST | `/api/v1/auth/resend-confirmation` | Renvoi email de confirmation |
| POST | `/api/v1/auth/login` | Connexion → JWT |
| POST | `/api/v1/auth/logout` | Révocation token |
| POST | `/api/v1/auth/reset-password/request` | Demande reset password |
| POST | `/api/v1/auth/reset-password/confirm` | Nouveau password via token |
| DELETE | `/api/v1/auth/account` | Suppression compte (RGPD) |
| GET | `/api/v1/subscriptions` | Lister ses abonnements |
| PUT | `/api/v1/subscriptions` | Mettre à jour ses abonnements |

### Modèle de Données (nouvelles tables SQL)

```sql
-- Comptes utilisateurs
USER_ACCOUNT (id, email, password_hash, is_confirmed,
              confirmation_token, reset_token, reset_token_expires,
              last_activity, created_at)

-- Abonnements aux alertes
ALERT_SUBSCRIPTION (id, user_id, region_code, alert_type,
                    is_active, created_at)
-- alert_type: 'under_production' | 'over_production'

-- Historique des alertes envoyées (déduplication)
ALERT_SENT_LOG (id, user_id, region_code, alert_type, sent_at)
-- Contrainte unique: (user_id, region_code, alert_type, date)
```

### Authentification
- JWT stateless, expiration 24h
- Tokens de confirmation/reset : UUID v4, expiration 1h
- Middleware d'auth sur tous les endpoints `/subscriptions` et `/auth/account`

### Nouvelles Pages Frontend

| Page | Route | Description |
|---|---|---|
| Inscription | `/register` | Formulaire email + password |
| Connexion | `/login` | Formulaire login |
| Confirmation | `/confirm?token=...` | Landing confirmation email |
| Reset password | `/reset-password` | Demande + formulaire nouveau MDP |
| Mes abonnements | `/subscriptions` | Carte régions + toggles alertes |
| Paramètres | `/settings` | Supprimer son compte |

### Email Transactionnel (templates)
1. **Confirmation d'inscription** — lien valable 1h
2. **Reset password** — lien valable 1h
3. **Alerte sous-production** — région, prod vs conso, lien dashboard
4. **Alerte sur-production** — région, prod vs conso, lien dashboard
5. **Avertissement suppression compte** — inactif depuis 11 mois, 30 jours restants

### Timer Function (nouvelle)
Tâche planifiée (toutes les heures) : détecte les croisements prod/conso sur les 4 dernières heures → vérifie les abonnements actifs → vérifie la déduplication → envoie les emails

## Project Scoping & Phased Development

### MVP Strategy
**Approche :** Problem-solving MVP — le minimum pour qu'un gestionnaire reçoive son premier email d'alerte pertinent.
**Ressources :** Solo dev, stack Azure existante, 1 provider email tiers (Resend recommandé — gratuit jusqu'à 3k emails/mois).

### MVP Feature Set (Phase 1)
**Journeys couverts :** Sophie inscription → config abonnements → réception alerte · Marc edge case (resend confirmation)

**Must-Have :**
- Auth complète : register, confirm, login, logout, reset password, delete account
- Page abonnements : sélection régions + type d'alerte (sous/sur production)
- Timer Function : détection croisement prod/conso + envoi email + déduplication 1/jour
- 5 templates email : confirmation, reset, alerte sous-prod, alerte sur-prod, avertissement suppression
- Script de test injection de données pour déclencher une alerte à la demande

### Phase 2 — Growth
- Résumé hebdomadaire email
- Préférences horaires (ne pas déranger la nuit)
- Vue "historique de mes alertes" dans l'app

### Phase 3 — Expansion
- Canaux additionnels (SMS, push, webhook)
- Seuils personnalisés en complément du croisement prod/conso

### Risques & Mitigations
- **Technique :** Dépendance `consommation` dans l'API Gold → vérifier avant de démarrer
- **Email :** Délivrabilité → utiliser Resend (gratuit jusqu'à 3k emails/mois)
- **Scope :** Feature dense → livrer en 3 sprints distincts : auth, abonnements, alertes

## Functional Requirements

### Gestion des Comptes Utilisateurs

- **FR1 :** Un visiteur peut créer un compte avec email et mot de passe
- **FR2 :** Le système envoie un email de confirmation à l'inscription
- **FR3 :** Un utilisateur non confirmé peut demander le renvoi de l'email de confirmation
- **FR4 :** Un utilisateur peut confirmer son compte via un lien tokenisé reçu par email
- **FR5 :** Un utilisateur confirmé peut se connecter avec email et mot de passe
- **FR6 :** Un utilisateur connecté peut se déconnecter
- **FR7 :** Un utilisateur peut demander la réinitialisation de son mot de passe
- **FR8 :** Un utilisateur peut définir un nouveau mot de passe via un lien tokenisé reçu par email
- **FR9 :** Un utilisateur connecté peut supprimer définitivement son compte

### Gestion des Abonnements aux Alertes

- **FR10 :** Un utilisateur connecté peut consulter la liste de ses abonnements actifs
- **FR11 :** Un utilisateur connecté peut s'abonner aux alertes d'une ou plusieurs régions françaises
- **FR12 :** Un utilisateur connecté peut choisir le type d'alerte par région : sous-production, sur-production, ou les deux
- **FR13 :** Un utilisateur connecté peut modifier ou désactiver ses abonnements existants

### Détection & Envoi des Alertes

- **FR14 :** Le système détecte périodiquement les croisements entre production et consommation régionale
- **FR15 :** Le système envoie un email d'alerte "sous-production" lorsque la production régionale passe sous la consommation
- **FR16 :** Le système envoie un email d'alerte "sur-production" lorsque la production régionale dépasse la consommation
- **FR17 :** Le système n'envoie pas plus d'un email par utilisateur, par région et par type d'alerte dans une même journée
- **FR18 :** L'email d'alerte contient : nom de la région, type d'événement, valeur de production, valeur de consommation, lien vers le dashboard

### Conformité RGPD

- **FR19 :** Le système supprime automatiquement les comptes inactifs depuis 12 mois
- **FR20 :** Le système envoie un email d'avertissement 30 jours avant la suppression automatique d'un compte
- **FR21 :** La reconnexion ou toute modification d'abonnement réinitialise le compteur d'inactivité

### Testabilité & Opérations

- **FR22 :** Un administrateur peut injecter des données de test pour forcer le déclenchement d'une alerte
- **FR23 :** Un administrateur peut restaurer les données réelles après une injection de test

## Non-Functional Requirements

### Sécurité
- Mots de passe hashés bcrypt (coût ≥ 12 — ~400ms/hash, résistant au brute-force)
- Tokens JWT signés, expiration 24h
- Tokens de confirmation/reset : usage unique, expiration 1h, invalidés après utilisation
- Toutes les communications en HTTPS
- Données personnelles limitées au strict minimum (email + hash uniquement)

### Performance
- Réponse des endpoints auth < 2 secondes
- Email d'alerte envoyé dans l'heure suivant la détection du croisement prod/conso
- Page abonnements chargée < 3 secondes

### Fiabilité
- Si l'envoi d'un email échoue, le système retry au cycle suivant (pas de perte silencieuse)
- La déduplication résiste aux retries : un email déjà envoyé aujourd'hui ne sera jamais re-envoyé même si la timer function tourne plusieurs fois

### Scalabilité
- Projet étudiant : pas de contrainte de montée en charge — l'infra Azure serverless absorbe nativement les variations
- Le modèle de données supporte N utilisateurs × M régions sans changement de schéma

### Intégration
- Provider email tiers (Resend ou équivalent) : implémentation découplée via interface pour faciliter le changement de provider
- API Gold existante : la feature de détection dépend de la disponibilité de `consommation` dans les données Gold
