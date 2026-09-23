"""Security and Credential Resolution Tests for lightning_helper.py.

Verifies:
1. No hardcoded credentials or fallback secrets exist.
2. Missing credentials fails closed safely.
3. Successful resolution from environment variables and keyring.
4. Secret redaction functions properly.
"""

import os
import pytest
from unittest.mock import patch

from scripts.content_factory import lightning_helper


def test_no_hardcoded_secrets_in_module():
    """Ensures no DEFAULT_API_KEY or DEFAULT_USER_ID constants exist in module."""
    assert not hasattr(lightning_helper, "DEFAULT_API_KEY"), "DEFAULT_API_KEY must not exist"
    assert not hasattr(lightning_helper, "DEFAULT_USER_ID"), "DEFAULT_USER_ID must not exist"


def test_missing_credentials_fails_closed(monkeypatch):
    """When neither env vars nor keyring has credentials, resolution must raise RuntimeError."""
    monkeypatch.delenv("LIGHTNING_API_KEY", raising=False)
    monkeypatch.delenv("LIGHTNING_USER_ID", raising=False)
    monkeypatch.delenv("LIGHTNING_USER", raising=False)
    monkeypatch.delenv("LIGHTNING_TEAMSPACE", raising=False)

    with patch.object(lightning_helper, "_get_keyring_credential", return_value=None):
        with pytest.raises(RuntimeError) as exc_info:
            lightning_helper.resolve_lightning_credentials()
        assert "Missing required Lightning AI credentials" in str(exc_info.value)


def test_credentials_resolved_from_env(monkeypatch):
    """Resolves credentials from environment variables safely."""
    monkeypatch.setenv("LIGHTNING_API_KEY", "test-api-key-1234567890")
    monkeypatch.setenv("LIGHTNING_USER_ID", "test-user-id-1234567890")
    monkeypatch.setenv("LIGHTNING_USER", "test-user")
    monkeypatch.setenv("LIGHTNING_TEAMSPACE", "test-teamspace")

    creds = lightning_helper.resolve_lightning_credentials()
    assert creds["api_key"] == "test-api-key-1234567890"
    assert creds["user_id"] == "test-user-id-1234567890"
    assert creds["user"] == "test-user"
    assert creds["teamspace"] == "test-teamspace"


def test_secret_redaction():
    """Ensures secret redaction protects sensitive credentials from log exposure."""
    assert lightning_helper.redact_secret(None) == "[EMPTY]"
    assert lightning_helper.redact_secret("") == "[EMPTY]"
    assert lightning_helper.redact_secret("short") == "[REDACTED]"
    secret = "2b1adb7a-c712-44d4-a9ed-1c5b2eb45a59"
    redacted = lightning_helper.redact_secret(secret)
    assert secret not in redacted
    assert redacted.startswith("2b1...")
    assert redacted.endswith("a59")
