"""Confirmación de tools MCP (#61).

Unitarios con una sesión falsa + integración con un servidor MCP real por stdio.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import klaus.security as sec
from klaus.config import MCPServerConfig
from klaus.mcp.client import MCPRegistry, _tool_read_only, needs_confirmation


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        return SimpleNamespace(content=[SimpleNamespace(text="ok")])


def make_registry(**server_cfg: Any) -> tuple[MCPRegistry, FakeSession, MCPServerConfig]:
    reg = MCPRegistry()
    session = FakeSession()
    reg._sessions["srv"] = session
    server = MCPServerConfig(name="srv", command=["x"], **server_cfg)
    return reg, session, server


def interactive(monkeypatch: pytest.MonkeyPatch, answer: bool) -> list[str]:
    asked: list[str] = []

    def fake_ask(q: str) -> bool:
        asked.append(q)
        return answer

    monkeypatch.setattr(sec, "is_interactive", lambda: True)
    monkeypatch.setattr(sec, "ask", fake_ask)
    return asked


@pytest.fixture(autouse=True)
def confirmations_on() -> None:
    """Estado por defecto del producto: escrituras con confirmación."""
    from klaus.tools import configure_confirmations

    configure_confirmations(auto_approve_writes=False, auto_approve_bash=False)


# ── readOnlyHint ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("annotations", "expected"),
    [
        (None, False),
        (SimpleNamespace(read_only_hint=True), True),  # mcp 2.x
        (SimpleNamespace(readOnlyHint=True), True),  # mcp 1.x
        (SimpleNamespace(read_only_hint=False), False),
        (SimpleNamespace(read_only_hint=None), False),
    ],
)
def test_tool_read_only(annotations: Any, expected: bool) -> None:
    assert _tool_read_only(SimpleNamespace(annotations=annotations)) is expected


# ── Política ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("confirm", "trust_ro", "read_only", "writes_auto", "expected"),
    [
        ("auto", True, False, False, (True, False)),  # efecto + confirmaciones activas → pregunta
        ("auto", True, True, False, (False, False)),  # solo lectura de confianza → no
        ("auto", False, True, False, (True, False)),  # no confiar en el hint → pregunta
        ("auto", True, False, True, (False, False)),  # --allow-writes/--yolo → no
        ("always", True, True, True, (True, True)),  # siempre, incluso YOLO y solo lectura
        ("never", True, False, False, (False, False)),
    ],
)
def test_needs_confirmation_matrix(
    confirm: str, trust_ro: bool, read_only: bool, writes_auto: bool, expected: tuple[bool, bool]
) -> None:
    from klaus.tools import configure_confirmations

    configure_confirmations(auto_approve_writes=writes_auto)
    server = MCPServerConfig.model_validate(
        {"name": "s", "command": ["x"], "confirm": confirm, "trust_read_only": trust_ro}
    )
    assert needs_confirmation(server, read_only) == expected


# ── Handler ─────────────────────────────────────────────────────────────────


async def test_side_effect_tool_denied_without_tty() -> None:
    """Antes de #61: se ejecutaba sin confirmación."""
    reg, session, server = make_registry()
    handler = reg._make_handler("srv", "delete_repo", server=server, read_only=False)
    result = await handler(name="prod")
    assert session.calls == []
    assert "requiere confirmación" in result["error"]


async def test_side_effect_tool_asks_and_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = interactive(monkeypatch, answer=True)
    reg, session, server = make_registry()
    result = await reg._make_handler("srv", "create_issue", server=server)(title="x")
    assert result == {"result": "ok"}
    assert session.calls == [("create_issue", {"title": "x"})]
    assert len(asked) == 1


async def test_side_effect_tool_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    interactive(monkeypatch, answer=False)
    reg, session, server = make_registry()
    result = await reg._make_handler("srv", "create_issue", server=server)(title="x")
    assert result["status"] == "cancelled"
    assert session.calls == []


async def test_read_only_tool_runs_without_asking(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = interactive(monkeypatch, answer=False)
    reg, session, server = make_registry()
    await reg._make_handler("srv", "list_issues", server=server, read_only=True)()
    assert len(session.calls) == 1
    assert asked == []


async def test_always_asks_even_in_yolo(monkeypatch: pytest.MonkeyPatch) -> None:
    from klaus.tools import configure_confirmations

    configure_confirmations(auto_approve_writes=True, auto_approve_bash=True)
    asked = interactive(monkeypatch, answer=False)
    reg, session, server = make_registry(confirm="always")
    await reg._make_handler("srv", "list", server=server, read_only=True)()
    assert len(asked) == 1
    assert session.calls == []


async def test_yolo_auto_approves_in_auto_mode() -> None:
    from klaus.tools import configure_confirmations

    configure_confirmations(auto_approve_writes=True)
    reg, session, server = make_registry()
    await reg._make_handler("srv", "create_issue", server=server)(title="x")
    assert len(session.calls) == 1


async def test_never_runs_without_tty() -> None:
    reg, session, server = make_registry(confirm="never")
    await reg._make_handler("srv", "create_issue", server=server)(title="x")
    assert len(session.calls) == 1


async def test_cwd_never_forwarded_to_server(monkeypatch: pytest.MonkeyPatch) -> None:
    reg, session, server = make_registry(confirm="never")
    await reg._make_handler("srv", "t", server=server)(a=1, cwd="/etc")
    assert session.calls == [("t", {"a": 1})]


# ── Integración: servidor MCP real por stdio ────────────────────────────────

FAKE_SERVER = Path(__file__).parent / "fixtures" / "mcp_fake_server.py"


async def _start(tmp_path: Path, **cfg: Any) -> tuple[MCPRegistry, Path]:
    pytest.importorskip("mcp.server.mcpserver")
    log = tmp_path / "log.txt"
    server = MCPServerConfig(
        name="fake",
        command=[sys.executable, str(FAKE_SERVER)],
        env={"FAKE_MCP_LOG": str(log)},
        **cfg,
    )
    reg = MCPRegistry()
    await reg.startup([server])
    if "fake" not in reg._sessions:
        pytest.skip("No se pudo arrancar el servidor MCP de prueba")
    return reg, log


async def test_integration_read_only_hint_and_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reg, log = await _start(tmp_path)
    try:
        descriptions = {s["name"]: s["description"] for s in reg.schemas}
        assert "solo lectura" in descriptions["mcp_fake_lookup"]
        assert "solo lectura" not in descriptions["mcp_fake_write_record"]

        # Solo lectura: se ejecuta sin TTY
        ro = await reg.handlers["mcp_fake_lookup"](key="k")
        assert ro == {"result": "valor-de-k"}

        # Con efectos: sin TTY se deniega y el servidor no escribe nada
        denied = await reg.handlers["mcp_fake_write_record"](text="hola")
        assert "requiere confirmación" in denied["error"]
        assert not log.exists()

        # Con efectos y el usuario aprueba
        interactive(monkeypatch, answer=True)
        ok = await reg.handlers["mcp_fake_write_record"](text="hola")
        assert ok == {"result": "ok"}
        assert log.read_text() == "hola\n"
    finally:
        await reg.shutdown()


async def test_integration_dispatch_path(tmp_path: Path) -> None:
    """Por _dispatch_tool (camino real del agente): validación MCP + confirmación."""
    from klaus.agent import _dispatch_tool
    from klaus.config import KlausConfig

    reg, log = await _start(tmp_path)
    try:
        missing = await _dispatch_tool(
            {"name": "mcp_fake_write_record", "id": "t", "input": {}},
            KlausConfig(), tmp_path, reg.handlers, schemas=reg.schemas,
        )
        assert "'text'" in missing["error"]

        denied = await _dispatch_tool(
            {"name": "mcp_fake_write_record", "id": "t", "input": {"text": "x"}},
            KlausConfig(), tmp_path, reg.handlers, schemas=reg.schemas,
        )
        assert "requiere confirmación" in denied["error"]
        assert not log.exists()
    finally:
        await reg.shutdown()
