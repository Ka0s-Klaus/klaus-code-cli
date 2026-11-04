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


# ── Perfiles de `klaus init` (#77) ──────────────────────────────────────────

import pytest  # noqa: E402
import yaml  # noqa: E402

from klaus.config import CONFIG_PROFILES, DEFAULT_CONFIG_YAML, config_yaml_for_profile  # noqa: E402


def _profile_config(profile: str) -> KlausConfig:
    return KlausConfig.model_validate(yaml.safe_load(config_yaml_for_profile(profile)))


def test_profile_dev_is_the_default_yaml():
    text = config_yaml_for_profile("dev")
    assert text.startswith("# Perfil: dev")
    assert yaml.safe_load(text) == yaml.safe_load(DEFAULT_CONFIG_YAML)


@pytest.mark.parametrize("profile", list(CONFIG_PROFILES))
def test_every_profile_is_a_valid_config(profile):
    # config_yaml_for_profile falla si una sustitución ya no encaja con el YAML por defecto
    _profile_config(profile)


def test_profile_cliente_matches_security_doc():
    cfg = _profile_config("cliente")
    assert cfg.security.outside_workspace == "deny"
    assert cfg.security.project_hooks == "never"
    assert cfg.pseudonymizer.required is True
    assert cfg.behavior.auto_approve_writes is False
    assert cfg.behavior.auto_approve_bash is False
    assert 'confirm: "always"' in config_yaml_for_profile("cliente")


def test_profile_ci_matches_security_doc():
    cfg = _profile_config("ci")
    assert cfg.security.outside_workspace == "deny"
    assert cfg.security.project_hooks == "trust"
    assert cfg.security.bash_allowlist == ["pytest", "ruff check", "mypy", "git status", "git diff"]
    assert cfg.pseudonymizer.required is False


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError, match="perfil desconocido"):
        config_yaml_for_profile("prod")


@pytest.mark.parametrize("profile", list(CONFIG_PROFILES))
def test_init_writes_profile(tmp_path, monkeypatch, profile):
    from typer.testing import CliRunner

    from klaus import cli

    cfg_path = tmp_path / ".klaus" / "config.yaml"
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg_path)
    result = CliRunner().invoke(cli.app, ["init", "--profile", profile])
    assert result.exit_code == 0, result.output
    assert cfg_path.read_text(encoding="utf-8") == config_yaml_for_profile(profile)


def test_init_default_profile_is_dev(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from klaus import cli

    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg_path)
    assert CliRunner().invoke(cli.app, ["init"]).exit_code == 0
    assert cfg_path.read_text(encoding="utf-8") == config_yaml_for_profile("dev")


def test_init_never_overwrites(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from klaus import cli

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("mío\n", encoding="utf-8")
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg_path)
    result = CliRunner().invoke(cli.app, ["init", "--profile", "cliente"])
    assert result.exit_code == 0
    assert cfg_path.read_text(encoding="utf-8") == "mío\n"
    assert "no se sobreescribe" in " ".join(result.output.split())  # rich parte líneas largas


def test_init_unknown_profile_exits_2(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from klaus import cli

    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg_path)
    result = CliRunner().invoke(cli.app, ["init", "--profile", "prod"])
    assert result.exit_code == 2
    assert not cfg_path.exists()
