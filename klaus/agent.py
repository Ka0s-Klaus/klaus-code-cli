"""Loop del agente Klaus con tool calling multi-turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from .config import KlausConfig
from .context import load_project_context
from .provider.base import ProviderAdapter
from .tools import TOOL_HANDLERS, TOOL_SCHEMAS

console = Console()


async def run_agent_loop(
    prompt: str,
    adapter: ProviderAdapter,
    config: KlausConfig,
    project_root: Path | None = None,
) -> int:
    """
    Loop principal del agente.

    - Envía el prompt inicial con las tools disponibles.
    - Si el modelo llama tools, las ejecuta y devuelve los resultados.
    - Continúa hasta que stop_reason sea 'end_turn' o se agoten los turnos.
    - Devuelve exit code (0 = éxito, 1 = error).
    """
    cwd = project_root or Path.cwd()

    # Cargar contexto del proyecto (KLAUS.md / CLAUDE.md)
    ctx = load_project_context(cwd, max_tokens=config.context.max_klaus_md_tokens)
    system_prompt = ctx.get("system_prompt")

    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    max_turns = config.behavior.max_agent_turns

    for turn in range(max_turns):
        try:
            response = await adapter.send_message(
                messages=messages,
                tools=TOOL_SCHEMAS,
                system=system_prompt,
            )
        except Exception as e:
            console.print(f"[red]Error de red (turno {turn + 1}):[/red] {e}")
            return 1

        stop = adapter.stop_reason(response)
        text = adapter.extract_text(response)
        tool_calls = adapter.extract_tool_calls(response)

        # Mostrar texto parcial si lo hay
        if text:
            console.print(Markdown(text))

        # Turno final — no hay tool calls
        if stop == "end_turn" or not tool_calls:
            return 0

        # Hay tool calls — ejecutar y construir mensajes de respuesta
        if stop == "tool_use":
            # Añadir el mensaje del asistente (con tool_use blocks)
            messages.append({"role": "assistant", "content": response["content"]})

            # Ejecutar cada tool call y recopilar resultados
            tool_results: list[dict[str, Any]] = []
            for tc in tool_calls:
                result = await _dispatch_tool(tc, config, cwd)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

            messages.append({"role": "user", "content": tool_results})
            continue

        # stop_reason inesperado — terminar
        if stop == "max_tokens":
            console.print("[yellow]⚠️  Límite de tokens alcanzado[/yellow]")
        return 0

    console.print(f"[yellow]⚠️  Límite de {max_turns} turnos alcanzado[/yellow]")
    return 0


async def _dispatch_tool(
    tool_call: dict[str, Any],
    config: KlausConfig,
    cwd: Path,
) -> Any:
    """Despacha una tool call al handler correspondiente."""
    name = tool_call.get("name", "")
    args = tool_call.get("input", {})

    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return {"error": f"Tool desconocida: {name}"}

    # Mostrar qué tool se ejecuta
    _print_tool_call(name, args)

    try:
        # Pasar cwd a las tools que lo soporten
        result = await handler(**args, cwd=cwd)
    except TypeError:
        # Si el handler no acepta cwd (compatibilidad futura)
        result = await handler(**args)
    except Exception as e:
        result = {"error": f"Error ejecutando {name}: {e}"}

    return result


def _print_tool_call(name: str, args: dict[str, Any]) -> None:
    """Muestra la tool call de forma compacta en la consola."""
    args_str = json.dumps(args, ensure_ascii=False)
    console.print(
        Panel(
            Syntax(f"{name}({args_str})", "python", theme="monokai"),
            title="[dim]🔧 tool[/dim]",
            border_style="dim",
            padding=(0, 1),
        )
    )
