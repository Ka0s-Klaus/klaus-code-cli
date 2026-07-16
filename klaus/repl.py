"""REPL interactivo de Klaus — loop de conversación persistente con historial."""

from __future__ import annotations

import json
import readline  # noqa: F401 — activa historial y edición de línea por defecto en Linux/Mac
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .config import KlausConfig
from .context import compact_messages, load_project_context
from .mcp.client import MCPRegistry
from .provider.base import ProviderAdapter
from .tools import TOOL_HANDLERS, TOOL_SCHEMAS, configure_confirmations
from .agent import _dispatch_tool

console = Console()

_PROMPT = "(Klaus) ❯ "

_SPECIAL_COMMANDS = {
    "/exit": "Salir del REPL",
    "/quit": "Salir del REPL",
    "/clear": "Limpiar el historial de conversación (nueva sesión con contexto en blanco)",
    "/help": "Mostrar este mensaje de ayuda",
    "/history": "Mostrar el historial de mensajes de la sesión actual",
}


def _print_welcome(version: str) -> None:
    console.print(
        Panel(
            f"[bold cyan]🤖 Klaus Code CLI[/bold cyan] [dim]v{version}[/dim] — [bold]REPL interactivo[/bold]\n\n"
            "[dim]Escribe un prompt y pulsa Enter. El modelo recuerda el contexto de la sesión.\n"
            "Comandos: [cyan]/help[/cyan]  [cyan]/clear[/cyan]  [cyan]/history[/cyan]  [cyan]/exit[/cyan] "
            "· Ctrl+D para salir[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def _print_help() -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column(style="dim")
    for cmd, desc in _SPECIAL_COMMANDS.items():
        table.add_row(cmd, desc)
    console.print(
        Panel(
            table,
            title="[bold]Comandos del REPL[/bold]",
            border_style="dim",
            padding=(1, 1),
        )
    )


def _print_history(messages: list[dict[str, Any]]) -> None:
    if not messages:
        console.print("[dim]Historial vacío.[/dim]")
        return
    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, list):
            # tool_use blocks o tool_result
            content = f"[{len(content)} bloque(s)]"
        elif isinstance(content, str) and len(content) > 120:
            content = content[:120] + "…"
        color = "cyan" if role == "user" else "green"
        console.print(f"[dim]{i + 1:2d}[/dim] [{color}]{role:9s}[/{color}] {content}")


async def run_repl(
    adapter: ProviderAdapter,
    config: KlausConfig,
    project_root: Path,
) -> int:
    """Arranca el REPL interactivo — mantiene historial entre turnos del usuario."""
    configure_confirmations(
        auto_approve_writes=config.behavior.auto_approve_writes,
        auto_approve_bash=config.behavior.auto_approve_bash,
    )

    cwd = project_root
    ctx = load_project_context(cwd, max_tokens=config.context.max_Klaus_md_tokens)
    system_prompt = ctx.get("system_prompt")

    mcp = MCPRegistry()
    active_schemas = list(TOOL_SCHEMAS)
    active_handlers: dict[str, Any] = dict(TOOL_HANDLERS)

    try:
        if config.mcp_servers:
            await mcp.startup(config.mcp_servers)
            active_schemas.extend(mcp.schemas)
            active_handlers.update(mcp.handlers)

        from . import __version__
        _print_welcome(__version__)

        return await _repl_loop(
            adapter=adapter,
            config=config,
            cwd=cwd,
            system_prompt=system_prompt,
            active_schemas=active_schemas,
            active_handlers=active_handlers,
        )
    finally:
        await mcp.shutdown()


async def _repl_loop(
    adapter: ProviderAdapter,
    config: KlausConfig,
    cwd: Path,
    system_prompt: str | None,
    active_schemas: list[dict[str, Any]],
    active_handlers: dict[str, Any],
) -> int:
    """Loop principal del REPL."""
    messages: list[dict[str, Any]] = []

    while True:
        # Leer input del usuario
        try:
            user_input = input(_PROMPT)
        except EOFError:
            console.print("\n[dim]Saliendo...[/dim]")
            return 0
        except KeyboardInterrupt:
            console.print("")
            continue

        stripped = user_input.strip()
        if not stripped:
            continue

        # Comandos especiales
        cmd = stripped.lower()
        if cmd in ("/exit", "/quit"):
            console.print("[dim]¡Hasta pronto![/dim]")
            return 0
        if cmd == "/clear":
            messages = []
            console.print("[dim]Historial limpiado — nueva sesión iniciada.[/dim]")
            continue
        if cmd == "/help":
            _print_help()
            continue
        if cmd == "/history":
            _print_history(messages)
            continue

        # Append y procesar el turno
        messages.append({"role": "user", "content": stripped})
        messages = await _run_turn(
            messages=messages,
            adapter=adapter,
            config=config,
            cwd=cwd,
            system_prompt=system_prompt,
            active_schemas=active_schemas,
            active_handlers=active_handlers,
        )


async def _run_turn(
    messages: list[dict[str, Any]],
    adapter: ProviderAdapter,
    config: KlausConfig,
    cwd: Path,
    system_prompt: str | None,
    active_schemas: list[dict[str, Any]],
    active_handlers: dict[str, Any],
) -> list[dict[str, Any]]:
    """Procesa un turno completo (usuario → modelo → tools* → modelo) y devuelve los mensajes actualizados."""
    max_turns = config.behavior.max_agent_turns
    total_input: int = 0
    total_output: int = 0

    for turn in range(max_turns):
        try:
            response = await adapter.send_message(
                messages=messages,
                tools=active_schemas,
                system=system_prompt,
            )
        except Exception as e:
            console.print(f"[red]Error de red (turno {turn + 1}):[/red] {e}")
            return messages

        usage = adapter.extract_usage(response)
        total_input += usage["input_tokens"]
        total_output += usage["output_tokens"]

        if usage["input_tokens"] > 0:
            ctx_pct = int(total_input / config.context.max_context_tokens * 100)
            console.print(
                f"[dim]📊 tokens — input: {total_input:,} ({ctx_pct}%) "
                f"| output: {total_output:,}[/dim]"
            )

        stop = adapter.stop_reason(response)
        text = adapter.extract_text(response)
        tool_calls = adapter.extract_tool_calls(response)

        if text:
            console.print(Markdown(text))

        if stop == "end_turn" or not tool_calls:
            if response.get("content"):
                messages.append({"role": "assistant", "content": response["content"]})
            return messages

        if stop == "tool_use":
            messages.append({"role": "assistant", "content": response["content"]})

            tool_results: list[dict[str, Any]] = []
            for tc in tool_calls:
                result = await _dispatch_tool(tc, config, cwd, active_handlers)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
            messages.append({"role": "user", "content": tool_results})

            if config.context.auto_compact:
                threshold = int(config.context.max_context_tokens * 0.8)
                if total_input >= threshold:
                    messages, dropped = compact_messages(messages, keep_last=6)
                    if dropped > 0:
                        console.print(
                            f"[yellow]🗜️  Auto-compact: {dropped} mensajes eliminados "
                            f"(threshold: {threshold:,} tokens)[/yellow]"
                        )
                        total_input = 0
            continue

        if stop == "max_tokens":
            console.print("[yellow]⚠️  Límite de tokens alcanzado en este turno[/yellow]")
        return messages

    console.print(
        f"[yellow]⚠️  Límite de {max_turns} turnos alcanzado para este input[/yellow]"
    )
    return messages
