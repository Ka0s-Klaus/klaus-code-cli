"""Tests para klaus.config — KlausConfig y load_config."""

from __future__ import annotations

from klaus.config import KlausConfig, load_config


def test_default_config():
    cfg = KlausConfig()
    assert cfg.provider.api_format == "anthropic"
    assert cfg.provider.max_tokens == 4096
    assert cfg.behavior.auto_approve_writes is False
    assert cfg.behavior.streaming is True
    assert cfg.session.persist is True


def test_config_api_key_from_env(monkeypatch):
    monkeypatch.setenv("KLAUS_API_KEY", "test-key-123")
    cfg = KlausConfig()
    assert cfg.api_key == "test-key-123"


def test_load_config_no_file(tmp_path, monkeypatch):
    import klaus.config as cm
    monkeypatch.setattr(cm, "CONFIG_PATH", tmp_path / "nonexistent.yaml")
    cfg = load_config()
    assert isinstance(cfg, KlausConfig)
    assert cfg.provider.api_format == "anthropic"


def test_load_config_env_override(monkeypatch, tmp_path):
    import klaus.config as cm
    monkeypatch.setattr(cm, "CONFIG_PATH", tmp_path / "nonexistent.yaml")
    monkeypatch.setenv("KLAUS_MODEL", "gpt-4o")
    cfg = load_config()
    assert cfg.provider.model == "gpt-4o"


def test_load_config_cli_override(monkeypatch, tmp_path):
    import klaus.config as cm
    monkeypatch.setattr(cm, "CONFIG_PATH", tmp_path / "nonexistent.yaml")
    cfg = load_config(model_override="claude-opus-4-8")
    assert cfg.provider.model == "claude-opus-4-8"


def test_load_config_from_file(tmp_path, monkeypatch):
    import klaus.config as cm
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("provider:\n  max_tokens: 8192\n")
    monkeypatch.setattr(cm, "CONFIG_PATH", cfg_file)
    cfg = load_config()
    assert cfg.provider.max_tokens == 8192
