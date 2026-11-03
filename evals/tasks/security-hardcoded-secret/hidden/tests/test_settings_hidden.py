import pytest

import client
import settings


def test_reads_env(monkeypatch):
    monkeypatch.setenv("PAYMENTS_API_KEY", "test-key")
    assert settings.get_api_key() == "test-key"
    assert client.auth_header() == {"Authorization": "Bearer test-key"}


def test_missing_env(monkeypatch):
    monkeypatch.delenv("PAYMENTS_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        settings.get_api_key()
