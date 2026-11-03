"""Regresiones del bucle del agente (#57).

Cubre: invocación única de tools, validación contra schemas activos (MCP),
parámetros desconocidos, tamaño de contexto vs consumo acumulado, compactación
sin tool_result huérfanos y coherencia de DEFAULT_CONFIG_YAML.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import pytest

from klaus.agent import _dispatch_tool
from klaus.config import KlausConfig

# ── _dispatch_tool: una sola invocación ─────────────────────────────────────


async def test_handler_raising_typeerror_runs_once(tmp_path: Path) -> None:
    """Antes: TypeError interno → segundo intento sin cwd (efectos duplicados)."""
    calls: list[Path | None] = []

    async def flaky(path: str, cwd: Path | None = None) -> dict[str, Any]:
        calls.append(cwd)
        raise TypeError("bug interno del handler")

    tc = {"name": "flaky", "id": "t", "input": {"path": "x"}}
    result = await _dispatch_tool(tc, KlausConfig(), tmp_path, {"flaky": flaky}, schemas=[])
    assert calls == [tmp_path]
    assert "bug interno" in result["error"]


async def test_side_effect_not_duplicated(tmp_path: Path) -> None:
    log = tmp_path / "log.txt"

    async def append_then_fail(line: str, cwd: Path | None = None) -> dict[str, Any]:
        with log.open("a") as f:
            f.write(line + "\n")
        raise TypeError("fallo tras el efecto")

    tc = {"name": "append", "id": "t", "input": {"line": "hola"}}
    await _dispatch_tool(tc, KlausConfig(), tmp_path, {"append": append_then_fail}, schemas=[])
    assert log.read_text() == "hola\n"


async def test_handler_without_cwd_does_not_receive_it(tmp_path: Path) -> None:
    received: dict[str, Any] = {}

    async def no_cwd(query: str) -> dict[str, Any]:
        received["query"] = query
        return {"ok": True}

    tc = {"name": "no_cwd", "id": "t", "input": {"query": "q"}}
    result = await _dispatch_tool(tc, KlausConfig(), tmp_path, {"no_cwd": no_cwd}, schemas=[])
    assert result == {"ok": True}
    assert received == {"query": "q"}


async def test_kwargs_handler_receives_cwd(tmp_path: Path) -> None:
    """Los handlers MCP aceptan **kwargs: se les pasa cwd (lo descartan ellos)."""
    received: dict[str, Any] = {}

    async def mcp_like(**kwargs: Any) -> dict[str, Any]:
        received.update(kwargs)
        return {}

    tc = {"name": "mcp_x", "id": "t", "input": {"a": 1}}
    await _dispatch_tool(tc, KlausConfig(), tmp_path, {"mcp_x": mcp_like}, schemas=[])
    assert received == {"a": 1, "cwd": tmp_path}


async def test_decorated_handler_signature_is_followed(tmp_path: Path) -> None:
    """guard_workspace y similares usan functools.wraps: se respeta la firma original."""

    def deco(fn: Any) -> Any:
        @functools.wraps(fn)
        async def wrapper(*a: Any, **k: Any) -> Any:
            return await fn(*a, **k)

        return wrapper

    @deco
    async def wrapped(path: str, cwd: Path | None = None) -> dict[str, Any]:
        return {"cwd": cwd}

    tc = {"name": "w", "id": "t", "input": {"path": "x"}}
    result = await _dispatch_tool(tc, KlausConfig(), tmp_path, {"w": wrapped}, schemas=[])
    assert result == {"cwd": tmp_path}


async def test_unknown_parameter_returns_actionable_error(tmp_path: Path) -> None:
    called = False

    async def tool(path: str, cwd: Path | None = None) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    tc = {"name": "tool", "id": "t", "input": {"path": "x", "pathh": "y"}}
    result = await _dispatch_tool(tc, KlausConfig(), tmp_path, {"tool": tool}, schemas=[])
    assert not called
    assert "pathh" in result["error"]
    assert "path" in result["error"]
    assert "cwd" not in result["error"].split("válidos:")[1]


async def test_builtin_tool_still_works(tmp_path: Path) -> None:
    from klaus.security import configure_security

    configure_security(KlausConfig(), tmp_path)
    (tmp_path / "a.txt").write_text("hola\n")
    tc = {"name": "read_file", "id": "t", "input": {"path": "a.txt"}}
    result = await _dispatch_tool(tc, KlausConfig(), tmp_path)
    assert "hola" in result["content"]


# ── Validación contra schemas activos (MCP) ─────────────────────────────────


async def test_required_params_validated_for_mcp_schema(tmp_path: Path) -> None:
    called = False

    async def mcp_handler(**kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    schema = {
        "name": "mcp_github_create_issue",
        "input_schema": {"type": "object", "required": ["title", "repo"]},
    }
    tc = {"name": "mcp_github_create_issue", "id": "t", "input": {"title": "x"}}
    result = await _dispatch_tool(
        tc, KlausConfig(), tmp_path, {"mcp_github_create_issue": mcp_handler}, schemas=[schema]
    )
    assert not called
    assert "'repo'" in result["error"]


# ── Tamaño de contexto vs consumo ───────────────────────────────────────────


def test_maybe_compact_uses_current_context_size() -> None:
    from klaus.context import maybe_compact

    msgs = [{"role": "user", "content": str(i)} for i in range(20)]
    same, dropped, threshold = maybe_compact(msgs, 70_000, 100_000)
    assert dropped == 0 and same is msgs and threshold == 80_000
    _, dropped, _ = maybe_compact(msgs, 85_000, 100_000)
    assert dropped > 0
    _, dropped, _ = maybe_compact(msgs, 85_000, 100_000, enabled=False)
    assert dropped == 0


class _Adapter:
    """Pide una tool en cada turno hasta `turns`, con un contexto creciente."""

    def __init__(self, contexts: list[int]) -> None:
        self.contexts = contexts
        self.turn = 0
        self.history_sizes: list[int] = []

    async def send_message(self, messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        self.history_sizes.append(len(messages))
        ctx = self.contexts[min(self.turn, len(self.contexts) - 1)]
        self.turn += 1
        if self.turn <= len(self.contexts):
            content = [{"type": "tool_use", "id": f"t{self.turn}", "name": "list_directory",
                        "input": {}}]
            stop = "tool_use"
        else:
            content = [{"type": "text", "text": "fin"}]
            stop = "end_turn"
        return {"content": content, "stop_reason": stop, "usage": {"input_tokens": ctx}}

    def extract_usage(self, r: dict[str, Any]) -> dict[str, int]:
        return {"input_tokens": r["usage"]["input_tokens"], "output_tokens": 10}

    def stop_reason(self, r: dict[str, Any]) -> str:
        return str(r["stop_reason"])

    def extract_text(self, r: dict[str, Any]) -> str:
        return "".join(b.get("text", "") for b in r["content"] if b["type"] == "text")

    def extract_tool_calls(self, r: dict[str, Any]) -> list[dict[str, Any]]:
        return [b for b in r["content"] if b["type"] == "tool_use"]


async def test_no_premature_compaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """6 turnos de ~30 % de contexto: la suma (180 %) compactaba; el tamaño real no."""
    from klaus.agent import run_agent_loop

    async def no_proxy(*a: Any, **k: Any) -> bool:
        return True

    monkeypatch.setattr("klaus.agent.ensure_pseudonymizer", no_proxy)
    cfg = KlausConfig()
    cfg.context.max_context_tokens = 100_000
    adapter = _Adapter([30_000] * 6)
    await run_agent_loop("tarea", adapter, cfg, tmp_path)  # type: ignore[arg-type]
    # El historial crece de 2 en 2 sin recortes
    assert adapter.history_sizes == [1, 3, 5, 7, 9, 11, 13]


async def test_compaction_when_context_really_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from klaus.agent import run_agent_loop

    async def no_proxy(*a: Any, **k: Any) -> bool:
        return True

    monkeypatch.setattr("klaus.agent.ensure_pseudonymizer", no_proxy)
    cfg = KlausConfig()
    cfg.context.max_context_tokens = 100_000
    adapter = _Adapter([10_000, 20_000, 40_000, 60_000, 90_000, 95_000])
    await run_agent_loop("tarea", adapter, cfg, tmp_path)  # type: ignore[arg-type]
    assert max(adapter.history_sizes) < 13  # hubo compactación
    assert adapter.history_sizes[-1] <= 1 + 1 + 6  # primero + marcador + keep_last


# ── compact_messages: sin tool_result huérfanos ─────────────────────────────


def _tool_use(i: int) -> dict[str, Any]:
    return {"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": "x",
                                              "input": {}}]}


def _tool_result(i: int) -> dict[str, Any]:
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"t{i}",
                                         "content": "ok"}]}


def _assert_no_orphans(messages: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for m in messages:
        for b in m["content"] if isinstance(m["content"], list) else []:
            if b.get("type") == "tool_use":
                seen.add(b["id"])
            if b.get("type") == "tool_result":
                assert b["tool_use_id"] in seen, f"tool_result huérfano: {b['tool_use_id']}"


def test_compact_drops_orphan_tool_result_at_tail_start() -> None:
    """Historial con longitud par (p. ej. REPL tras un turno de texto): la cola empezaba
    por un tool_result cuyo tool_use se había recortado → error 400 de la API."""
    from klaus.context import compact_messages

    msgs: list[dict[str, Any]] = [{"role": "user", "content": "inicio"}]
    msgs += [{"role": "assistant", "content": "texto"}]
    for i in range(5):
        msgs += [_tool_use(i), _tool_result(i)]
    # longitud 12 → la cola de 6 empezaría por _tool_result(2)
    compacted, dropped = compact_messages(msgs, keep_last=7)
    _assert_no_orphans(compacted)
    assert dropped == len(msgs) - len(compacted) + 1  # +1: marcador añadido


def test_compact_keeps_valid_tail_untouched() -> None:
    from klaus.context import compact_messages

    msgs: list[dict[str, Any]] = [{"role": "user", "content": "inicio"}]
    for i in range(5):
        msgs += [_tool_use(i), _tool_result(i)]
    compacted, _ = compact_messages(msgs, keep_last=6)
    assert compacted[2:] == msgs[-6:]
    _assert_no_orphans(compacted)


# ── DEFAULT_CONFIG_YAML ─────────────────────────────────────────────────────


def test_default_config_yaml_matches_model_everywhere() -> None:
    """`klaus init` escribe exactamente los defaults del modelo (antes timeout 120 vs 600)."""
    import yaml

    from klaus.config import DEFAULT_CONFIG_YAML

    data = yaml.safe_load(DEFAULT_CONFIG_YAML)
    expected = KlausConfig().model_dump()
    expected.pop("mcp_servers")  # comentado como ejemplo en el YAML
    assert data == expected
