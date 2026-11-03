"""Tests de nombres canónicos y compatibilidad con los anteriores (#58)."""

from __future__ import annotations

from pathlib import Path

import pytest

import klaus.compat as compat


@pytest.fixture(autouse=True)
def fresh_warnings() -> None:
    compat._warned.clear()


def _case_sensitive(tmp_path: Path) -> bool:
    (tmp_path / "CaseProbe").mkdir()
    return not (tmp_path / "caseprobe").exists()


# ── Variables de entorno ────────────────────────────────────────────────────


def test_klaus_env_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KLAUS_MODEL", "gpt-4o")
    assert compat.getenv("MODEL") == "gpt-4o"


def test_klaude_env_is_deprecated_alias(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("KLAUDE_MODEL", "legacy-model")
    assert compat.getenv("MODEL") == "legacy-model"
    assert compat.getenv("MODEL") == "legacy-model"
    err = capsys.readouterr().err
    assert err.count("KLAUDE_MODEL está obsoleta") == 1  # avisa una sola vez


def test_klaus_env_wins_over_klaude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KLAUS_PROXY_URL", "http://nuevo/v1")
    monkeypatch.setenv("KLAUDE_PROXY_URL", "http://viejo/v1")
    assert compat.getenv("PROXY_URL") == "http://nuevo/v1"


def test_load_config_uses_klaus_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import klaus.config as cm

    monkeypatch.setattr(cm, "CONFIG_PATH", tmp_path / "none.yaml")
    monkeypatch.setenv("KLAUS_PROXY_URL", "http://proxy:8080/v1")
    monkeypatch.setenv("KLAUDE_API_FORMAT", "openai")
    cfg = cm.load_config()
    assert cfg.provider.base_url == "http://proxy:8080/v1"
    assert cfg.provider.api_format == "openai"


def test_api_key_falls_back_to_klaude(monkeypatch: pytest.MonkeyPatch) -> None:
    from klaus.config import KlausConfig

    monkeypatch.setenv("KLAUDE_API_KEY", "sk-legacy")
    assert KlausConfig().api_key == "sk-legacy"
    monkeypatch.setenv("KLAUS_API_KEY", "sk-new")
    assert KlausConfig().api_key == "sk-new"


def test_custom_api_key_env_has_no_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from klaus.config import KlausConfig

    monkeypatch.setenv("KLAUDE_API_KEY", "sk-legacy")
    cfg = KlausConfig()
    cfg.provider.api_key_env = "MY_KEY"
    assert cfg.api_key is None


# ── Clave de config renombrada ──────────────────────────────────────────────


def test_legacy_config_key_accepted_with_warning(capsys: pytest.CaptureFixture[str]) -> None:
    from klaus.config import KlausConfig

    cfg = KlausConfig.model_validate({"context": {"max_Klaus_md_tokens": 1234}})
    assert cfg.context.max_klaus_md_tokens == 1234
    assert "max_Klaus_md_tokens está obsoleta" in capsys.readouterr().err


def test_new_config_key(capsys: pytest.CaptureFixture[str]) -> None:
    from klaus.config import KlausConfig

    cfg = KlausConfig.model_validate({"context": {"max_klaus_md_tokens": 99}})
    assert cfg.context.max_klaus_md_tokens == 99
    assert capsys.readouterr().err == ""


# ── Directorios ─────────────────────────────────────────────────────────────


def test_new_dir_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert compat.klaus_home() == tmp_path / ".klaus"


def test_legacy_dir_used_when_only_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not _case_sensitive(tmp_path):
        pytest.skip("FS sin distinción de mayúsculas: .Klaus y .klaus son el mismo directorio")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".Klaus").mkdir()
    assert compat.klaus_home() == tmp_path / ".Klaus"
    assert compat.expand_user_path("~/.klaus/sessions/") == tmp_path / ".Klaus" / "sessions"


def test_new_dir_preferred_when_both(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if not _case_sensitive(tmp_path):
        pytest.skip("FS sin distinción de mayúsculas")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    (tmp_path / ".Klaus").mkdir()
    (tmp_path / ".klaus").mkdir()
    assert compat.klaus_home() == tmp_path / ".klaus"


def test_warn_legacy_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if not _case_sensitive(tmp_path):
        pytest.skip("FS sin distinción de mayúsculas")
    home = tmp_path / "home"
    project = tmp_path / "project"
    (home / ".Klaus").mkdir(parents=True)
    (project / ".Klaus").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    compat.warn_legacy_dirs(project)
    err = capsys.readouterr().err
    assert "mv" in err and str(home / ".Klaus") in err and str(project / ".Klaus") in err


def test_expand_user_path_other_paths_untouched(tmp_path: Path) -> None:
    assert compat.expand_user_path(str(tmp_path / "x")) == tmp_path / "x"


# ── klaus init --scan genera el fichero que luego se carga ──────────────────


def test_scan_output_is_the_file_context_loads() -> None:
    """Antes, init --scan generaba CLAUS.md, pero el contexto solo carga KLAUS.md."""
    import inspect

    from klaus import cli, context

    src = inspect.getsource(cli._scan_and_generate)
    assert 'project_root / "KLAUS.md"' in src
    assert "KLAUS.md" in inspect.getsource(context.load_project_context)


def test_version_comes_from_package_metadata() -> None:
    import tomllib
    from importlib.metadata import version

    import klaus

    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert klaus.__version__ == pyproject["project"]["version"] == version("klaus-code-cli")
