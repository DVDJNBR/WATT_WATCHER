"""
Key Vault Module — Story 1.1, Task 3

Retrieves secrets from Azure Key Vault using Managed Identity.
In local dev mode, falls back to environment variables.

Note: The RTE eCO2mix API is PUBLIC (no auth needed), but this
module is kept for future data sources requiring API keys.
"""

import logging
import os

logger = logging.getLogger(__name__)


class KeyVaultClient:
    """Retrieve secrets from Azure Key Vault or environment variables."""

    def __init__(self, vault_url: str | None = None):
        """
        Args:
            vault_url: Key Vault URI (e.g. https://gps-dev-kv.vault.azure.net/).
                      If None, uses KEY_VAULT_URL env var. Falls back to env-only mode.
        """
        self.vault_url = vault_url or os.environ.get("KEY_VAULT_URL")
        self._client = None

        if self.vault_url:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient

                credential = DefaultAzureCredential()
                self._client = SecretClient(
                    vault_url=self.vault_url, credential=credential
                )
                logger.info("KeyVaultClient connected: %s", self.vault_url)
            except Exception as e:
                logger.warning(
                    "KeyVault unavailable (%s), falling back to env vars", e
                )
        else:
            logger.info("KeyVaultClient in ENV-ONLY mode (no vault URL)")

    def get_secret(self, name: str, env_fallback: str | None = None) -> str | None:
        """
        Get a secret value. Tries Key Vault first, then environment variable.

        Args:
            name: Secret name in Key Vault.
            env_fallback: Environment variable name to check if KV unavailable.

        Returns:
            Secret value, or None if not found.
        """
        # Try Key Vault
        if self._client:
            try:
                secret = self._client.get_secret(name)
                logger.debug("Secret '%s' retrieved from Key Vault", name)
                return secret.value
            except Exception as e:
                logger.warning("Failed to get secret '%s' from KV: %s", name, e)

        # Fallback to environment variable
        env_key = env_fallback or name.upper().replace("-", "_")
        value = os.environ.get(env_key)
        if value:
            logger.debug("Secret '%s' retrieved from env var '%s'", name, env_key)
        return value
