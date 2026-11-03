"""Fixtures comunes para la suite pytest de Klaus Code CLI."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_confirmations():
    """Desactiva todos los prompts de confirmación durante los tests."""
    import klaus.tools.bash as bm
    import klaus.tools.write as wm

    orig_write = wm.CONFIRM_WRITES
    orig_bash = bm.CONFIRM_BASH
    orig_approve = wm._APPROVE_ALL

    wm.CONFIRM_WRITES = False
    bm.CONFIRM_BASH = False
    wm._APPROVE_ALL = False

    yield

    wm.CONFIRM_WRITES = orig_write
    bm.CONFIRM_BASH = orig_bash
    wm._APPROVE_ALL = orig_approve


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Aísla los tests de variables KLAUDE_* presentes en el entorno del desarrollador."""
    for var in ("KLAUDE_PROXY_URL", "KLAUDE_MODEL", "KLAUDE_API_FORMAT", "KLAUDE_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def reset_pseudonymizer_cache():
    """Cada test parte sin literales registrados (caché de proceso de pseudonymizer_config)."""
    import klaus.pseudonymizer_config as pc

    pc._configured.clear()
    yield
    pc._configured.clear()
