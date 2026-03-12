# Story 5.3: Alert Timer Function

Status: done

## Story

As a system,
I want an hourly timer function that orchestrates detection and email sending with deduplication,
so that users receive timely and non-spammy alerts.

## Acceptance Criteria

1. Nouvelle Azure Function timer dans `function_app.py`, déclenchement horaire (`0 0 * * * *`)
2. Séquence : `detect(conn)` → pour chaque alerte → trouver abonnés (`ALERT_SUBSCRIPTION`) → check `ALERT_SENT_LOG` → si pas envoyé aujourd'hui → `send_alert()` → insérer dans `ALERT_SENT_LOG`
3. Déduplication : 1 seul email par utilisateur/région/type par jour calendaire
4. Si envoi email échoue → log erreur, ne pas insérer dans `ALERT_SENT_LOG` (retry au prochain cycle)
5. Logs : détection, envoi réussi, skip déduplication
6. La logique de dispatch est extraite dans `functions/shared/alerting/alert_dispatcher.py` (testabilité)
7. Tests unitaires couvrent : envoi normal, dédup, échec email, pas d'abonnés

## Tasks / Subtasks

- [x] Créer `functions/shared/alerting/alert_dispatcher.py` (AC: 2, 3, 4, 5, 6)
  - [x] Fonction `dispatch_alerts(conn, email_svc) -> dict` — séquence principale
  - [x] Requête abonnés : `SELECT u.id, u.email FROM ALERT_SUBSCRIPTION s JOIN USER_ACCOUNT u ON s.user_id = u.id WHERE s.region_code = ? AND s.alert_type = ? AND s.is_active = 1`
  - [x] Check dédup : `SELECT 1 FROM ALERT_SENT_LOG WHERE user_id = ? AND region_code = ? AND alert_type = ? AND sent_at >= ?` (avec début de journée UTC)
  - [x] Si pas déjà envoyé : appeler `email_svc.send_alert(email, region_code, alert_type, prod_mw, conso_mw)`
  - [x] Si envoi OK : insérer dans `ALERT_SENT_LOG`
  - [x] Si envoi échoue : log erreur, ne pas insérer (retry cycle suivant)
  - [x] Retourner `{"detected": int, "sent": int, "skipped_dedup": int, "errors": int}`
- [x] Ajouter le timer trigger dans `functions/function_app.py` (AC: 1)
  - [x] Import `dispatch_alerts` et `EmailService`
  - [x] `@app.timer_trigger(schedule="0 0 * * * *", arg_name="timer", run_on_startup=False)`
  - [x] Appeler `dispatch_alerts(conn, EmailService())`
  - [x] `conn = None` + try/finally pour fermeture connexion
- [x] Écrire les tests dans `tests/test_alert_dispatcher.py` (AC: 2, 3, 4, 5, 7)
  - [x] Envoi normal : 1 alerte, 1 abonné → 1 email envoyé, 1 log inséré
  - [x] Dédup : alerte déjà envoyée aujourd'hui → skip, pas de 2e email
  - [x] Échec email → log non inséré dans ALERT_SENT_LOG
  - [x] Aucun abonné pour une région → 0 email
  - [x] Plusieurs abonnés même alerte → N emails
  - [x] Compteurs retournés corrects

## Dev Notes

### Architecture : séparer dispatch de la Function App

La logique de dispatch va dans `alert_dispatcher.py` (testable sans Azure SDK). Le timer dans `function_app.py` est un thin wrapper :

```python
# function_app.py — thin wrapper
@app.timer_trigger(schedule="0 0 * * * *", arg_name="timer", run_on_startup=False)
def alert_dispatch_timer(timer: func.TimerRequest) -> None:
    """Hourly alert dispatch: detect → match subscribers → dedup → send."""
    job_id = str(uuid.uuid4())
    logger.info("[%s] Alert dispatch starting", job_id)
    conn = None
    try:
        conn = _get_db_connection()
        svc = EmailService()
        result = dispatch_alerts(conn, svc)
        logger.info(
            "[%s] Alert dispatch done: detected=%d sent=%d skipped=%d errors=%d",
            job_id, result["detected"], result["sent"], result["skipped_dedup"], result["errors"],
        )
    except Exception as exc:
        logger.error("[%s] Alert dispatch failed: %s", job_id, exc, exc_info=True)
    finally:
        if conn:
            conn.close()
```

### Logique `dispatch_alerts(conn, email_svc)`

```python
from datetime import datetime, timezone
from shared.alerting.alert_detector import detect
from shared.api.email_service import EmailService
import logging

logger = logging.getLogger(__name__)

def dispatch_alerts(conn, email_svc) -> dict:
    alerts = detect(conn)
    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")

    sent = skipped = errors = 0
    cursor = conn.cursor()

    for alert in alerts:
        region_code = alert["region_code"]
        alert_type = alert["alert_type"]
        prod_mw = alert["prod_mw"]
        conso_mw = alert["conso_mw"]

        # Find all active subscribers for this region+type
        cursor.execute(
            "SELECT u.id, u.email "
            "FROM ALERT_SUBSCRIPTION s "
            "JOIN USER_ACCOUNT u ON s.user_id = u.id "
            "WHERE s.region_code = ? AND s.alert_type = ? AND s.is_active = 1",
            (region_code, alert_type),
        )
        subscribers = cursor.fetchall()

        for user_id, email in subscribers:
            # Dedup check: already sent today?
            cursor.execute(
                "SELECT 1 FROM ALERT_SENT_LOG "
                "WHERE user_id = ? AND region_code = ? AND alert_type = ? AND sent_at >= ?",
                (user_id, region_code, alert_type, today_start),
            )
            if cursor.fetchone():
                logger.info("AlertDispatcher: skip dedup user=%d region=%s type=%s", user_id, region_code, alert_type)
                skipped += 1
                continue

            # Send email
            try:
                email_svc.send_alert(email, region_code, alert_type, prod_mw, conso_mw)
            except Exception as exc:
                logger.error("AlertDispatcher: email failed user=%d region=%s: %s", user_id, region_code, exc)
                errors += 1
                continue  # Don't insert log — retry next cycle

            # Log successful send
            cursor.execute(
                "INSERT INTO ALERT_SENT_LOG (user_id, region_code, alert_type) VALUES (?, ?, ?)",
                (user_id, region_code, alert_type),
            )
            conn.commit()
            logger.info("AlertDispatcher: sent user=%d region=%s type=%s", user_id, region_code, alert_type)
            sent += 1

    return {"detected": len(alerts), "sent": sent, "skipped_dedup": skipped, "errors": errors}
```

### Déduplication : `sent_at >= today_start`

On utilise `today_start = datetime.now(timezone.utc).strftime("%Y-%m-%d")` (ex. `'2026-03-11'`).
- SQLite : `sent_at TEXT` stocké par `datetime('now')` au format `'YYYY-MM-DD HH:MM:SS'` — la comparaison `>= '2026-03-11'` fonctionne par ordre lexicographique ✓
- SQL Server : `sent_at DATETIME2` cast implicite de `'2026-03-11'` → `2026-03-11 00:00:00` ✓
- Format avec `T` (ex. `'2026-03-11T00:00:00'`) évité : SQLite stocke avec espace, pas `T`, ce qui causerait un échec silencieux de la déduplication (`' ' < 'T'` en ASCII).

### Pattern de test (SQLite in-memory)

```python
def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE USER_ACCOUNT (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            is_confirmed INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE ALERT_SUBSCRIPTION (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            region_code TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE ALERT_SENT_LOG (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            region_code TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            sent_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        -- Gold tables needed for detect()
        CREATE TABLE DIM_REGION (id_region INTEGER PRIMARY KEY, code_insee TEXT NOT NULL, nom_region TEXT);
        CREATE TABLE DIM_TIME (id_date INTEGER PRIMARY KEY, horodatage TEXT NOT NULL);
        CREATE TABLE DIM_SOURCE (id_source INTEGER PRIMARY KEY, source_name TEXT NOT NULL);
        CREATE TABLE FACT_ENERGY_FLOW (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_region INTEGER, id_date INTEGER, id_source INTEGER,
            valeur_mw REAL, consommation_mw REAL
        );
    """)
    conn.commit()
    return conn
```

Pour mocker `EmailService`, utiliser `unittest.mock.MagicMock()` :
```python
from unittest.mock import MagicMock
mock_svc = MagicMock()
result = dispatch_alerts(conn, mock_svc)
mock_svc.send_alert.assert_called_once_with("user@test.com", "FR", "under_production", 4000.0, 6000.0)
```

Pour simuler un échec email :
```python
mock_svc.send_alert.side_effect = RuntimeError("Resend API error")
```

### Imports à ajouter dans `function_app.py`

```python
from shared.alerting.alert_dispatcher import dispatch_alerts
```

`EmailService` est déjà importé.

### Références

- `functions/shared/alerting/alert_detector.py` — `detect(conn)` → prêt story 5.2
- `functions/shared/api/email_service.py` — `send_alert(email, region_code, alert_type, prod_mw, conso_mw)` → prêt story 5.1
- `functions/function_app.py` — pattern timer `rte_ingestion` à reproduire (ligne ~95)
- `functions/migrations/003_create_alert_sent_log.sql` — schéma ALERT_SENT_LOG
- `_bmad-output/planning-artifacts/architecture.md` — idempotence timer : vérifier ALERT_SENT_LOG avant envoi
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 5.3` — ACs source

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

### File List

- `functions/shared/alerting/alert_dispatcher.py` — new: `dispatch_alerts(conn, email_svc) -> dict`
- `functions/function_app.py` — modified: import `dispatch_alerts`, added `alert_dispatch_timer` timer trigger
- `tests/test_alert_dispatcher.py` — new: 9 unit tests covering all ACs
