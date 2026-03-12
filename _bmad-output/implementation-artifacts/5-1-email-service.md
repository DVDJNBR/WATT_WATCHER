# Story 5.1: Email Service — send_alert

Status: done

## Story

As a developer,
I want `EmailService.send_alert()` implemented,
so that the alert timer function can notify subscribed users when their region crosses the production/consumption threshold.

## Acceptance Criteria

1. `EmailService` dans `functions/shared/api/email_service.py` expose une méthode `send_alert(to_email, region_code, alert_type, prod_mw, conso_mw)`
2. Mode mock (`EMAIL_MOCK=true`) : log au lieu d'envoyer, ne pas appeler Resend API
3. Mode production : appel `POST https://api.resend.com/emails` avec sujet et corps HTML appropriés
4. `alert_type` doit être `"under_production"` ou `"over_production"` — corps email différencié selon le type
5. Tests unitaires mock mode dans `tests/test_email_service.py`

## Tasks / Subtasks

- [x] Ajouter `send_alert()` dans `functions/shared/api/email_service.py` (AC: 1, 2, 3, 4)
  - [x] Signature : `def send_alert(self, to_email: str, region_code: str, alert_type: str, prod_mw: float, conso_mw: float) -> None`
  - [x] Mock mode : `logger.info("EMAIL_MOCK send_alert: to=%s region=%s alert_type=%s prod_mw=%s conso_mw=%s", ...)`
  - [x] Production mode : POST Resend API — même pattern que `send_confirmation`/`send_reset`
  - [x] Sujet email : distinguer `under_production` vs `over_production`
  - [x] Corps HTML : inclure `region_code`, `prod_mw`, `conso_mw` pour que l'utilisateur sache pourquoi il est alerté
  - [x] Mettre à jour le docstring module (Story 5.1)
- [x] Ajouter `TestSendAlertMockMode` dans `tests/test_email_service.py` (AC: 2, 5)
  - [x] Mock logs au lieu d'envoyer
  - [x] Mock ne fait pas appel à requests
  - [x] `under_production` : log mentionne le type
  - [x] `over_production` : log mentionne le type

## Dev Notes

### Contexte critique : `email_service.py` existe déjà

`email_service.py` a été créé en story 2.2 et étendu en story 2.4. Il contient déjà :
- `send_confirmation(to_email, token)` — confirmé et testé
- `send_reset(to_email, token)` — confirmé et testé
- Pattern Resend API complet (key vault + env fallback, mock mode, requests.post)
- Classe `EmailService` avec `self._mock`, `self._base_url`, `self._from_address`

**Story 5.1 = ajouter UNIQUEMENT `send_alert()` — ne pas modifier ce qui existe.**

### Pattern à reproduire (`send_reset` comme modèle)

```python
def send_alert(self, to_email: str, region_code: str, alert_type: str, prod_mw: float, conso_mw: float) -> None:
    """
    Send alert email when production crosses consumption threshold.

    Args:
        to_email: Recipient email address.
        region_code: Region code (e.g., "FR", "FR-IDF").
        alert_type: "under_production" or "over_production".
        prod_mw: Current production in MW.
        conso_mw: Current consumption in MW.
    """
    if alert_type == "under_production":
        subject = f"[WATT WATCHER] Alerte sous-production — {region_code}"
        detail = f"La production ({prod_mw:.0f} MW) est inférieure à la consommation ({conso_mw:.0f} MW)."
    else:
        subject = f"[WATT WATCHER] Alerte sur-production — {region_code}"
        detail = f"La production ({prod_mw:.0f} MW) est supérieure à la consommation ({conso_mw:.0f} MW)."

    if self._mock:
        logger.info(
            "EMAIL_MOCK send_alert: to=%s region_code=%s alert_type=%s prod_mw=%s conso_mw=%s",
            to_email, region_code, alert_type, prod_mw, conso_mw,
        )
        return

    api_key = _load_resend_api_key()
    payload = {
        "from": self._from_address,
        "to": [to_email],
        "subject": subject,
        "html": (
            f"<p>Alerte de production détectée pour la région <strong>{region_code}</strong>.</p>"
            f"<p>{detail}</p>"
            f"<p>Connectez-vous sur WATT WATCHER pour suivre l'évolution.</p>"
        ),
    }
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=10,
    )
    if not resp.ok:
        logger.error("Resend API error %d: %s", resp.status_code, resp.text)
        raise RuntimeError(f"Email send failed (status={resp.status_code})")
    logger.info("Alert email sent to %s (region=%s, type=%s)", to_email, region_code, alert_type)
```

### Pattern de test à suivre (existant dans test_email_service.py)

```python
class TestSendAlertMockMode:

    def test_send_alert_mock_logs_instead_of_sending(self, monkeypatch, caplog):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        import logging
        svc = EmailService()
        with caplog.at_level(logging.INFO, logger="shared.api.email_service"):
            svc.send_alert("user@test.com", "FR", "under_production", 5000.0, 6000.0)
        assert "EMAIL_MOCK" in caplog.text
        assert "user@test.com" in caplog.text
        assert "under_production" in caplog.text

    def test_send_alert_mock_does_not_call_requests(self, monkeypatch):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        svc = EmailService()
        with patch("shared.api.email_service.requests") as mock_requests:
            svc.send_alert("user@test.com", "FR", "under_production", 5000.0, 6000.0)
            mock_requests.post.assert_not_called()

    def test_send_alert_over_production_mock(self, monkeypatch, caplog):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        import logging
        svc = EmailService()
        with caplog.at_level(logging.INFO, logger="shared.api.email_service"):
            svc.send_alert("user@test.com", "FR-IDF", "over_production", 8000.0, 6000.0)
        assert "over_production" in caplog.text
        assert "FR-IDF" in caplog.text
```

### Fichiers à modifier

| Fichier | Action |
|---|---|
| `functions/shared/api/email_service.py` | Ajouter `send_alert()` + mettre à jour docstring module |
| `tests/test_email_service.py` | Ajouter `TestSendAlertMockMode` (3-4 tests) |

**Ne pas modifier** : `function_app.py` (la méthode sera appelée par story 5.3 — timer function).

### Sujet email recommandé

- `under_production` → `"[WATT WATCHER] Alerte sous-production — {region_code}"`
- `over_production` → `"[WATT WATCHER] Alerte sur-production — {region_code}"`

### Note sur prod_mw / conso_mw

Ces valeurs peuvent être des floats ou des entiers. Utiliser `:.0f` dans le format string pour des valeurs lisibles (ex. "5 000 MW").

### Références

- `functions/shared/api/email_service.py` — fichier à modifier, patron `send_reset` à copier
- `tests/test_email_service.py` — patron `TestSendResetMockMode` à reproduire
- `_bmad-output/planning-artifacts/epics-user-accounts-alerts.md#Story 5.1` — ACs source
- `_bmad-output/planning-artifacts/architecture.md` — `email_service.py` = interface découplée provider

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

N/A — 14/14 tests passed on first run.

### Completion Notes List

- `send_alert()` ajouté selon le patron `send_reset` existant.
- Sujet email différencié : sous-production vs sur-production.
- 4 tests mock ajoutés : logs, no-requests, over_production, region+values.

### Code Review Fixes (CR)

- **M1 fixed**: `else` remplacé par `elif / else: raise ValueError(...)` — `alert_type` invalide lève maintenant une erreur explicite au lieu de silencieusement envoyer un email "sur-production".
- Test `test_send_alert_invalid_type_raises` ajouté.

### File List

- `functions/shared/api/email_service.py` (send_alert + docstring mis à jour)
- `tests/test_email_service.py` (TestSendAlertMockMode — 4 tests)
