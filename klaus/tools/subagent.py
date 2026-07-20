"""Tool spawn_agent — sub-agente aislado para delegar subtareas.

El sub-agente tiene su propio historial y contexto, aislado del agente padre.
El resultado (último texto generado) se devuelve al padre como string.

Limitaciones de seguridad:
  - Máximo de profundidad configurable (max_agent_depth en BehaviorConfig).
  - Los sub-agentes NO heredan hooks del padre.
  - Los sub-agentes NO guardan sesión en disco.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

console = Console()

# Profundidad actual de anidamiento (thread-local vía contextvars)
import contextvars

_current_depth: contextvars.ContextVar[int] = contextvars.ContextVar("agent_depth", default=0)


async def spawn_agent(
    prompt: str,
    model: str | None = None,
    max_turns: int | None = None,
    tools: list[str] | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Lanza un sub-agente aislado con el prompt dado.

    Args:
        prompt: Tarea a ejecutar por el sub-agente.
        model: Override de modelo (usa el modelo del padre si None).
        max_turns: Override de max_agent_turns (usa el default si None).
        tools: Lista de nombres de tools disponibles para el sub-agente
               (None = todas las tools built-in).
        cwd: Directorio de trabajo (hereda el del padre si None).

    Returns:
        Dict con "result" (texto de respuesta) y metadatos de ejecución.
    """
    # Import aquí para evitar importaciones circulares
    from ..config import KlausConfig, load_config

    depth = _current_depth.get()
    config = load_config()
    max_depth = getattr(config.behavior, "max_agent_depth", 3)

    if depth >= max_depth:
        return {
            "error": (
                f"Límite de profundidad de sub-agentes alcanzado ({max_depth}). "
                "No se puede crear un sub-agente desde este contexto."
            )
        }

    console.print(
        Panel(
            f"[cyan]🤖 Lanzando sub-agente[/cyan] (profundidad {depth + 1}/{max_depth})\n"
            f"[dim]{prompt[:120]}{'…' if len(prompt) > 120 else ''}[/dim]",
            border_style="cyan",
            padding=(0, 1),
        )
    )

    # Construir config para el sub-agente
    sub_config = load_config(model_override=model)
    if max_turns is not None:
        sub_config.behavior.max_agent_turns = max_turns
    sub_config.behavior.auto_approve_writes = True
    sub_config.behavior.auto_approve_bash = True
    sub_config.session.persist = False  # sub-agentes no guardan sesión

    # Filtrar tools si se especificó lista
    sub_schemas = None
    sub_handlers = None
    if tools is not None:
        from ..tools import TOOL_HANDLERS, TOOL_SCHEMAS

        sub_schemas = [s for s in TOOL_SCHEMAS if s["name"] in tools]
        sub_handlers = {k: v for k, v in TOOL_HANDLERS.items() if k in tools}

    # Capturar resultado del sub-agente
    collected_text: list[str] = []

    try:
        token = _current_depth.set(depth + 1)
        result = await _run_subagent(
            prompt=prompt,
            config=sub_config,
            cwd=cwd or Path.cwd(),
            collected_text=collected_text,
            sub_schemas=sub_schemas,
            sub_handlers=sub_handlers,
        )
    finally:
        _current_depth.reset(token)

    output = "\n".join(collected_text).strip()
    console.print(f"[dim]✅ Sub-agente completado (exit: {result})[/dim]")

    return {
        "result": output,
        "exit_code": result,
        "depth": depth + 1,
        "chars": len(output),
    }


async def _run_subagent(
    prompt: str,
    config: "KlausConfig",
    cwd: Path,
    collected_text: list[str],
    sub_schemas: list[dict[str, Any]] | None,
    sub_handlers: dict[str, Any] | None,
) -> int:
    """Ejecuta el loop del sub-agente capturando el output de texto."""
    import json

    from ..context import load_project_context
    from ..provider.base import ProviderAdapter
    from ..tools import TOOL_HANDLERS, TOOL_SCHEMAS, configure_confirmations

    configure_confirmations(auto_approve_writes=True, auto_approve_bash=True)

    ctx = load_project_context(cwd, max_tokens=config.context.max_Klaus_md_tokens)
    system_prompt = ctx.get("system_prompt")

    active_schemas = sub_schemas if sub_schemas is not None else list(TOOL_SCHEMAS)
    active_handlers: dict[str, Any] = sub_handlers if sub_handlers is not None else dict(TOOL_HANDLERS)

    # Obtener adapter
    fmt = config.provider.api_format.lower()
    if fmt == "openai":
        from ..provider.openai_fmt import OpenAIAdapter

        adapter: ProviderAdapter = OpenAIAdapter(config)
    else:
        from ..provider.anthropic_fmt import AnthropicAdapter

        adapter = AnthropicAdapter(config)

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    max_turns = config.behavior.max_agent_turns

    try:
        for turn in range(max_turns):
            try:
                response = await adapter.send_message(
                    messages=messages,
                    tools=active_schemas,
                    system=system_prompt,
                )
            except Exception as e:
                console.print(f"[red]Sub-agente — error de red: {e}[/red]")
                return 1

            stop = adapter.stop_reason(response)
            text = adapter.extract_text(response)
            tool_calls = adapter.extract_tool_calls(response)

            if text:
                collected_text.append(text)

            if stop == "end_turn" or not tool_calls:
                return 0

            if stop == "tool_use":
                messages.append({"role": "assistant", "content": response["content"]})
                tool_results: list[dict[str, Any]] = []
                for tc in tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("input", {})
                    handler = active_handlers.get(name)
                    if not handler:
                        res: Any = {"error": f"Tool desconocida: {name}"}
                    else:
                        try:
                            res = await handler(**args, cwd=cwd)
                        except TypeError:
                            res = await handler(**args)
                        except Exception as exc:
                            res = {"error": str(exc)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": json.dumps(res, ensure_ascii=False),
                    })
                messages.append({"role": "user", "content": tool_results})
                continue

            return 0
    finally:
        await adapter.close()

    return 0
