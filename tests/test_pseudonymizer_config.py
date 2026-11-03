"""Tests para klaus.pseudonymizer_config — regresiones de #55.

Cubre: heurística de modelo local, espera antes de la primera petición,
modo required, caché por proceso y los cuatro caminos que hablan con el
modelo (run, repl, /model, spawn_agent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

import klaus.pseudonymizer_config as pc
from klaus.config import KlausConfig
from klaus.pseudonymizer_config import (
    PseudonymizerError,
    collect_sensitive_literals,
    config_endpoint,
    configure_pseudonymizer,
    ensure_pseudonymizer,
    is_local_model,
)

DEFAULT_LOCAL = KlausConfig().pseudonymizer.local_models


# ── Fake del proxy ──────────────────────────────────────────────────────────


class FakeProxy:
    """Sustituye httpx.AsyncClient dentro del módulo y registra los POST."""

    def __init__(self, status: int = 200, exc: Exception | None = None) -> None:
        self.status = status
        self.exc = exc
        self.calls: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.exc:
            raise self.exc
        self.calls.append({"url": str(request.url), "json": json.loads(request.content)})
        return httpx.Response(self.status, json={"literals": 3, "paths": 2})


@pytest.fixture
def proxy(monkeypatch: pytest.MonkeyPatch) -> FakeProxy:
    fake = FakeProxy()
    real_client = httpx.AsyncClient

    def factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(fake.handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(pc.httpx, "AsyncClient", factory)
    return fake


def make_config(model: str, **pseudo: Any) -> KlausConfig:
    cfg = KlausConfig()
    cfg.provider.model = model
    cfg.provider.base_url = "http://proxy.test:8080/v1"
    for key, value in pseudo.items():
        setattr(cfg.pseudonymizer, key, value)
    return cfg


# ── is_local_model ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "model",
    [
        "openai/gpt-4o",  # LiteLLM: antes se trataba como local por contener "/"
        "anthropic/claude-sonnet-4-5",
        "azure/gpt-4o",
        "claude-haiku-4-5-20251001",
        "gpt-4o",
        "bedrock/anthropic.claude-3",
    ],
)
def test_external_models_are_not_local(model: str) -> None:
    assert is_local_model(model, DEFAULT_LOCAL) is False


@pytest.mark.parametrize("model", ["kdev:latest", "KDEV", "ollama/llama3", "ollama_chat/qwen2.5"])
def test_declared_local_models(model: str) -> None:
    assert is_local_model(model, DEFAULT_LOCAL) is True


def test_local_models_configurable() -> None:
    assert is_local_model("vllm/my-model", ["vllm/*"]) is True
    assert is_local_model("vllm/my-model", []) is False


def test_empty_model_is_not_local() -> None:
    assert is_local_model(None, DEFAULT_LOCAL) is False
    assert is_local_model("", DEFAULT_LOCAL) is False


# ── helpers ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://h:8080/v1", "http://h:8080/pseudonymizer/config"),
        ("http://h:8080/v1/", "http://h:8080/pseudonymizer/config"),
        ("http://h:8080", "http://h:8080/pseudonymizer/config"),
    ],
)
def test_config_endpoint(base_url: str, expected: str) -> None:
    assert config_endpoint(base_url) == expected


def test_collect_literals_includes_project_home_user(tmp_path: Path) -> None:
    literals = collect_sensitive_literals(tmp_path)
    assert literals[0] == str(tmp_path.resolve())
    assert str(Path.home().resolve()) in literals
    assert len(literals) == len(set(literals))


# ── configure_pseudonymizer ─────────────────────────────────────────────────


async def test_configure_posts_literals(proxy: FakeProxy) -> None:
    ok = await configure_pseudonymizer("http://proxy.test:8080/v1", ["/secret/path"])
    assert ok is True
    assert proxy.calls == [
        {"url": "http://proxy.test:8080/pseudonymizer/config", "json": {"literals": ["/secret/path"]}}
    ]


async def test_configure_http_error_returns_false(proxy: FakeProxy) -> None:
    proxy.status = 500
    assert await configure_pseudonymizer("http://proxy.test:8080/v1", ["x"]) is False


async def test_configure_connect_error_returns_false(proxy: FakeProxy) -> None:
    proxy.exc = httpx.ConnectError("refused")
    assert await configure_pseudonymizer("http://proxy.test:8080/v1", ["x"]) is False


async def test_configure_is_bounded_by_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un proxy que acepta y no responde no debe colgar Klaus (motivo de b1a9e63)."""
    import asyncio

    class HangingClient:
        def __init__(self, *a: Any, **k: Any) -> None: ...
        async def __aenter__(self) -> HangingClient:
            return self
        async def __aexit__(self, *a: Any) -> None: ...
        async def post(self, *a: Any, **k: Any) -> None:
            await asyncio.sleep(10)

    monkeypatch.setattr(pc.httpx, "AsyncClient", HangingClient)
    loop = asyncio.get_running_loop()
    start = loop.time()
    ok = await configure_pseudonymizer("http://proxy.test:8080/v1", ["x"], timeout_seconds=0.1)
    assert ok is False
    assert loop.time() - start < 1


# ── ensure_pseudonymizer ────────────────────────────────────────────────────


async def test_ensure_configures_litellm_external_model(proxy: FakeProxy, tmp_path: Path) -> None:
    """Regresión principal de #55: 'openai/gpt-4o' debe configurarse."""
    assert await ensure_pseudonymizer(make_config("openai/gpt-4o"), tmp_path) is True
    assert len(proxy.calls) == 1
    assert str(tmp_path.resolve()) in proxy.calls[0]["json"]["literals"]


async def test_ensure_skips_local_model(proxy: FakeProxy, tmp_path: Path) -> None:
    assert await ensure_pseudonymizer(make_config("ollama/llama3"), tmp_path) is True
    assert proxy.calls == []


async def test_ensure_disabled(proxy: FakeProxy, tmp_path: Path) -> None:
    assert await ensure_pseudonymizer(make_config("gpt-4o", enabled=False), tmp_path) is False
    assert proxy.calls == []


async def test_ensure_caches_success(proxy: FakeProxy, tmp_path: Path) -> None:
    cfg = make_config("gpt-4o")
    await ensure_pseudonymizer(cfg, tmp_path)
    await ensure_pseudonymizer(cfg, tmp_path)
    assert len(proxy.calls) == 1


async def test_ensure_does_not_cache_failure(proxy: FakeProxy, tmp_path: Path) -> None:
    proxy.status = 503
    cfg = make_config("gpt-4o")
    assert await ensure_pseudonymizer(cfg, tmp_path) is False
    proxy.status = 200
    assert await ensure_pseudonymizer(cfg, tmp_path) is True
    assert len(proxy.calls) == 2


async def test_ensure_required_raises_on_failure(proxy: FakeProxy, tmp_path: Path) -> None:
    proxy.exc = httpx.ConnectError("refused")
    with pytest.raises(PseudonymizerError):
        await ensure_pseudonymizer(make_config("gpt-4o", required=True), tmp_path)


async def test_ensure_required_ok_with_local_model(proxy: FakeProxy, tmp_path: Path) -> None:
    proxy.exc = httpx.ConnectError("refused")
    assert await ensure_pseudonymizer(make_config("kdev:latest", required=True), tmp_path) is True


# ── Caminos que hablan con el modelo ────────────────────────────────────────


class RecordingAdapter:
    """Adapter mínimo que registra si el proxy ya estaba configurado en la 1.ª petición."""

    def __init__(self, proxy: FakeProxy) -> None:
        self.proxy = proxy
        self.calls_before_first_request: int | None = None

    def _response(self) -> dict[str, Any]:
        if self.calls_before_first_request is None:
            self.calls_before_first_request = len(self.proxy.calls)
        return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}

    async def send_message(self, **_: Any) -> dict[str, Any]:
        return self._response()

    async def stream_message(self, **_: Any) -> dict[str, Any]:
        return self._response()

    def extract_usage(self, _: dict[str, Any]) -> dict[str, int]:
        return {"input_tokens": 0, "output_tokens": 0}

    def stop_reason(self, r: dict[str, Any]) -> str:
        return str(r["stop_reason"])

    def extract_text(self, r: dict[str, Any]) -> str:
        return str(r["content"][0]["text"])

    def extract_tool_calls(self, _: dict[str, Any]) -> list[dict[str, Any]]:
        return []


async def test_run_configures_before_first_request(proxy: FakeProxy, tmp_path: Path) -> None:
    """`klaus run`: configuración esperada antes de la 1.ª petición (antes era fire-and-forget)."""
    from klaus.agent import run_agent_loop

    adapter = RecordingAdapter(proxy)
    code = await run_agent_loop("hola", adapter, make_config("openai/gpt-4o"), tmp_path)  # type: ignore[arg-type]
    assert code == 0
    assert adapter.calls_before_first_request == 1


async def test_run_aborts_when_required_fails(proxy: FakeProxy, tmp_path: Path) -> None:
    from klaus.agent import run_agent_loop

    proxy.status = 500
    adapter = RecordingAdapter(proxy)
    cfg = make_config("gpt-4o", required=True)
    code = await run_agent_loop("hola", adapter, cfg, tmp_path)  # type: ignore[arg-type]
    assert code == 1
    assert adapter.calls_before_first_request is None  # nunca se habló con el modelo


def _repl_config(model: str, tmp_path: Path, **pseudo: Any) -> KlausConfig:
    cfg = make_config(model, **pseudo)
    cfg.session.storage_path = str(tmp_path / "sessions")
    cfg.session.persist = False
    cfg.session.lock_enabled = False
    return cfg


def _feed_inputs(monkeypatch: pytest.MonkeyPatch, inputs: list[str]) -> None:
    import builtins

    it = iter(inputs)

    def fake_input(*_: Any, **__: Any) -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(builtins, "input", fake_input)
    import klaus.repl as repl_mod

    if hasattr(repl_mod, "Prompt"):
        monkeypatch.setattr(repl_mod.Prompt, "ask", staticmethod(fake_input))


async def test_repl_configures_on_start(
    proxy: FakeProxy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`klaus repl`: antes nunca se configuraba."""
    from klaus.repl import run_repl

    _feed_inputs(monkeypatch, ["hola", "/exit"])
    adapter = RecordingAdapter(proxy)
    cfg = _repl_config("anthropic/claude-sonnet-4-5", tmp_path)
    await run_repl(adapter, cfg, tmp_path, persist=False, streaming=False)  # type: ignore[arg-type]
    assert adapter.calls_before_first_request == 1


async def test_repl_model_switch_local_to_external(
    proxy: FakeProxy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/model`: empezar en local y cambiar a externo debe configurar el proxy."""
    from klaus.repl import run_repl

    _feed_inputs(monkeypatch, ["/model openai/gpt-4o", "hola", "/exit"])
    adapter = RecordingAdapter(proxy)
    cfg = _repl_config("kdev:latest", tmp_path)
    await run_repl(adapter, cfg, tmp_path, persist=False, streaming=False)  # type: ignore[arg-type]
    assert len(proxy.calls) == 1
    assert adapter.calls_before_first_request == 1
    assert cfg.provider.model == "openai/gpt-4o"


async def test_repl_model_switch_reverts_when_required_fails(
    proxy: FakeProxy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from klaus.repl import run_repl

    proxy.status = 500
    _feed_inputs(monkeypatch, ["/model gpt-4o", "/exit"])
    cfg = _repl_config("kdev:latest", tmp_path, required=True)
    await run_repl(RecordingAdapter(proxy), cfg, tmp_path, persist=False, streaming=False)  # type: ignore[arg-type]
    assert cfg.provider.model == "kdev:latest"


async def test_spawn_agent_required_failure_returns_error(
    proxy: FakeProxy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`spawn_agent(model=...)` no pasa por run_agent_loop: debe configurar por su cuenta."""
    import klaus.config as cm
    from klaus.tools.subagent import spawn_agent

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        "provider:\n  base_url: http://proxy.test:8080/v1\n"
        "pseudonymizer:\n  required: true\n"
    )
    monkeypatch.setattr(cm, "CONFIG_PATH", cfg_file)
    monkeypatch.chdir(tmp_path)  # workspace = tmp_path (#56)
    proxy.status = 500

    result = await spawn_agent("tarea", model="openai/gpt-4o", cwd=tmp_path)
    assert "error" in result
    assert "pseudonymizer" in result["error"]


def test_default_config_yaml_matches_model() -> None:
    """El YAML de `klaus init` documenta exactamente los defaults del modelo."""
    import yaml

    from klaus.config import DEFAULT_CONFIG_YAML

    assert yaml.safe_load(DEFAULT_CONFIG_YAML)["pseudonymizer"] == KlausConfig().pseudonymizer.model_dump()


# ── Proveedor directo (sin proxy) ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("base_url", "direct"),
    [
        ("https://api.anthropic.com", True),
        ("https://api.openai.com/v1", True),
        ("https://mi-recurso.openai.azure.com/openai", True),
        ("http://localhost:8080/v1", False),
        ("http://klaude-proxy.interno:8080/v1", False),
        ("https://api.anthropic.com.evil.test/v1", False),
    ],
)
def test_is_direct_provider(base_url: str, direct: bool) -> None:
    assert pc.is_direct_provider(base_url) is direct


async def test_direct_provider_never_receives_literals(proxy: FakeProxy, tmp_path: Path) -> None:
    """Sin proxy, los literales sensibles no deben enviarse al proveedor."""
    cfg = make_config("claude-sonnet-4-5")
    cfg.provider.base_url = "https://api.anthropic.com"
    assert await ensure_pseudonymizer(cfg, tmp_path) is False
    assert proxy.calls == []


async def test_direct_provider_required_raises(proxy: FakeProxy, tmp_path: Path) -> None:
    cfg = make_config("gpt-4o", required=True)
    cfg.provider.base_url = "https://api.openai.com/v1"
    with pytest.raises(PseudonymizerError, match="sin klaude-proxy"):
        await ensure_pseudonymizer(cfg, tmp_path)
    assert proxy.calls == []
