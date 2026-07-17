"""Fixtures comunes para la suite pytest de Klaus Code CLI."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_confirmations():
    """Desactiva todos los prompts de confirmación durante los tests."""
    import klaus.tools.write as wm
    import klaus.tools.bash as bm

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
