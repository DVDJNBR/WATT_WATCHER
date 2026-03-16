"""
Tests for EmailService — Story 2.2 CR fix (M2) + Story 2.4 (send_reset).

Covers: mock mode, missing API key, cached key reset, send_reset mock mode.
Does NOT test the live Resend API call (requires real key + network).
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from shared.api.email_service import EmailService, reset_resend_api_key, _load_resend_api_key


@pytest.fixture(autouse=True)
def reset_key_cache():
    """Clear module-level API key cache before/after each test."""
    reset_resend_api_key()
    yield
    reset_resend_api_key()


class TestEmailServiceMockMode:

    def test_mock_mode_logs_instead_of_sending(self, monkeypatch, caplog):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        import logging
        svc = EmailService()
        with caplog.at_level(logging.INFO, logger="shared.api.email_service"):
            svc.send_confirmation("user@test.com", "test-token-123")
        assert "EMAIL_MOCK" in caplog.text
        assert "user@test.com" in caplog.text

    def test_mock_mode_does_not_call_requests(self, monkeypatch):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        svc = EmailService()
        with patch("shared.api.email_service.requests") as mock_requests:
            svc.send_confirmation("user@test.com", "test-token-123")
            mock_requests.post.assert_not_called()

    def test_mock_mode_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("EMAIL_MOCK", "TRUE")
        svc = EmailService()
        with patch("shared.api.email_service.requests") as mock_requests:
            svc.send_confirmation("user@test.com", "test-token-123")
            mock_requests.post.assert_not_called()

    def test_non_mock_mode_is_default(self, monkeypatch):
        monkeypatch.delenv("EMAIL_MOCK", raising=False)
        svc = EmailService()
        assert svc._mock is False


class TestLoadResendApiKey:

    def test_missing_key_raises_environment_error(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        monkeypatch.delenv("KEY_VAULT_URL", raising=False)
        with pytest.raises(EnvironmentError, match="RESEND_API_KEY"):
            _load_resend_api_key()

    def test_env_var_key_loaded(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "test-api-key-123")
        monkeypatch.delenv("KEY_VAULT_URL", raising=False)
        key = _load_resend_api_key()
        assert key == "test-api-key-123"

    def test_key_cached_after_first_load(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "cached-key")
        monkeypatch.delenv("KEY_VAULT_URL", raising=False)
        key1 = _load_resend_api_key()
        # Change env — cached value should still be returned
        monkeypatch.setenv("RESEND_API_KEY", "new-key")
        key2 = _load_resend_api_key()
        assert key1 == key2 == "cached-key"

    def test_reset_clears_cache(self, monkeypatch):
        monkeypatch.setenv("RESEND_API_KEY", "first-key")
        monkeypatch.delenv("KEY_VAULT_URL", raising=False)
        _load_resend_api_key()
        reset_resend_api_key()
        monkeypatch.setenv("RESEND_API_KEY", "second-key")
        key = _load_resend_api_key()
        assert key == "second-key"


class TestSendResetMockMode:

    def test_send_reset_mock_logs_instead_of_sending(self, monkeypatch, caplog):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        import logging
        svc = EmailService()
        with caplog.at_level(logging.INFO, logger="shared.api.email_service"):
            svc.send_reset("user@test.com", "reset-token-abc")
        assert "EMAIL_MOCK" in caplog.text
        assert "user@test.com" in caplog.text

    def test_send_reset_mock_does_not_call_requests(self, monkeypatch):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        svc = EmailService()
        with patch("shared.api.email_service.requests") as mock_requests:
            svc.send_reset("user@test.com", "reset-token-abc")
            mock_requests.post.assert_not_called()


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

    def test_send_alert_mock_includes_region_and_values(self, monkeypatch, caplog):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        import logging
        svc = EmailService()
        with caplog.at_level(logging.INFO, logger="shared.api.email_service"):
            svc.send_alert("alert@test.com", "PACA", "under_production", 1200.5, 1500.0)
        assert "PACA" in caplog.text
        assert "1200.5" in caplog.text

    def test_send_alert_invalid_type_raises(self, monkeypatch):
        monkeypatch.setenv("EMAIL_MOCK", "true")
        svc = EmailService()
        with pytest.raises(ValueError, match="invalid_type"):
            svc.send_alert("user@test.com", "FR", "invalid_type", 5000.0, 6000.0)
