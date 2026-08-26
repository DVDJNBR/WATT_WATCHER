"""
Email Service — Story 2.2 (send_confirmation) + Story 2.4 (send_reset) + Story 5.1 (send_alert).

In mock mode (EMAIL_MOCK=true), logs instead of sending — used in tests and local dev.
Resend API key loaded from Key Vault (RESEND_API_KEY) or env var fallback.
"""

import logging
import os
from typing import Optional

import requests  # already in requirements.txt

logger = logging.getLogger(__name__)

_resend_api_key: Optional[str] = None


def _load_resend_api_key() -> str:
    global _resend_api_key
    if _resend_api_key is not None:
        return _resend_api_key

    key_vault_url = os.environ.get("KEY_VAULT_URL")
    if key_vault_url:
        try:
            from shared.keyvault import KeyVaultClient
            kv = KeyVaultClient(vault_url=key_vault_url)
            value = kv.get_secret("RESEND_API_KEY")
            if value:
                _resend_api_key = value
                logger.info("Resend API key loaded from Key Vault")
                return _resend_api_key
        except Exception as exc:
            logger.warning("Could not load RESEND_API_KEY from Key Vault: %s", exc)

    value = os.environ.get("RESEND_API_KEY", "")
    if not value:
        raise EnvironmentError("RESEND_API_KEY not configured (Key Vault: RESEND_API_KEY or env: RESEND_API_KEY)")

    _resend_api_key = value
    logger.info("Resend API key loaded from environment variable")
    return _resend_api_key


def reset_resend_api_key() -> None:
    """Clear cached key — used in tests."""
    global _resend_api_key
    _resend_api_key = None


class EmailService:
    """
    Transactional email service backed by Resend.

    Activate mock mode via EMAIL_MOCK=true (logs instead of sending).
    """

    def __init__(self):
        self._mock = os.environ.get("EMAIL_MOCK", "").lower() == "true"
        self._base_url = os.environ.get("APP_BASE_URL", "https://watt-watcher.fr")
        self._from_address = "WATT WATCHER <noreply@watt-watcher.fr>"

    def send_confirmation(self, to_email: str, token: str) -> None:
        """
        Send account confirmation email with token link.

        Args:
            to_email: Recipient email address.
            token: UUID v4 confirmation token.
        """
        confirm_url = f"{self._base_url}/confirm?token={token}"

        if self._mock:
            logger.info(
                "EMAIL_MOCK send_confirmation: to=%s confirm_url=%s",
                to_email,
                confirm_url,
            )
            return

        api_key = _load_resend_api_key()
        payload = {
            "from": self._from_address,
            "to": [to_email],
            "subject": "Confirmez votre compte WATT WATCHER",
            "html": (
                f"<p>Bienvenue sur WATT WATCHER !</p>"
                f"<p><a href='{confirm_url}'>Confirmer mon compte</a></p>"
                f"<p>Ce lien expire dans 1 heure.</p>"
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
        logger.info("Confirmation email sent to %s", to_email)

    def send_reset(self, to_email: str, token: str) -> None:
        """
        Send password reset email with token link.

        Args:
            to_email: Recipient email address.
            token: UUID v4 reset token.
        """
        reset_url = f"{self._base_url}/reset-password?token={token}"

        if self._mock:
            logger.info(
                "EMAIL_MOCK send_reset: to=%s reset_url=%s",
                to_email,
                reset_url,
            )
            return

        api_key = _load_resend_api_key()
        payload = {
            "from": self._from_address,
            "to": [to_email],
            "subject": "Réinitialisation de votre mot de passe WATT WATCHER",
            "html": (
                f"<p>Vous avez demandé la réinitialisation de votre mot de passe.</p>"
                f"<p><a href='{reset_url}'>Réinitialiser mon mot de passe</a></p>"
                f"<p>Ce lien expire dans 1 heure. Si vous n'avez pas fait cette demande, ignorez cet email.</p>"
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
        logger.info("Reset email sent to %s", to_email)

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
        elif alert_type == "over_production":
            subject = f"[WATT WATCHER] Alerte sur-production — {region_code}"
            detail = f"La production ({prod_mw:.0f} MW) est supérieure à la consommation ({conso_mw:.0f} MW)."
        else:
            raise ValueError(f"Invalid alert_type '{alert_type}'. Must be 'under_production' or 'over_production'.")

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

    def send_inactivity_warning(self, to_email: str) -> None:
        """
        Send RGPD inactivity warning email (30-day notice before account deletion).

        Args:
            to_email: Recipient email address.
        """
        subject = "[WATT WATCHER] Votre compte sera supprimé dans 30 jours"
        if self._mock:
            logger.info("EMAIL_MOCK send_inactivity_warning: to=%s", to_email)
            return

        api_key = _load_resend_api_key()
        payload = {
            "from": self._from_address,
            "to": [to_email],
            "subject": subject,
            "html": (
                "<p>Votre compte WATT WATCHER est inactif depuis 11 mois.</p>"
                "<p>Conformément à notre politique RGPD, les comptes inactifs depuis 12 mois "
                "sont automatiquement supprimés.</p>"
                "<p><strong>Pour conserver votre compte, connectez-vous avant 30 jours.</strong></p>"
                "<p>Si vous ne souhaitez pas conserver votre compte, aucune action n'est requise.</p>"
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
        logger.info("Inactivity warning email sent to %s", to_email)
