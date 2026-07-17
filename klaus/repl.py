"""REPL interactivo de Klaus — loop de conversación persistente con historial."""

from __future__ import annotations

import json
import readline  # noqa: F401 — activa historial y edición de línea por defecto en Linux/Mac
from datetime import datetime
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
from .sessions import SessionLock, SessionManager, list_sessions
from .streaming import StreamRenderer
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
    "/sessions": "Listar sesiones guardadas en disco",
}


def _print_welcome(
    version: str, session_id: str, persist: bool, resumed: bool, streaming: bool
) -> None:
    session_line = (
        f"[dim]Sesión:[/dim] [cyan]{session_id}[/cyan]"
        if persist
        else "[dim]Sesión:[/dim] [yellow]efímera (--no-persist)[/yellow]"
    )
    resumed_line = "  [green]↩ Historial previo cargado[/green]" if resumed else ""
    stream_line = "  [dim]streaming: on[/dim]" if streaming else "  [dim]streaming: off[/dim]"
    console.print(
        Panel(
            f"[bold cyan]🤖 Klaus Code CLI[/bold cyan] [dim]v{version}[/dim] — [bold]REPL interactivo[/bold]\n\n"
            f"{session_line}{resumed_line}{stream_line}\n\n"
            "[dim]Escribe un prompt y pulsa Enter. El modelo recuerda el contexto de la sesión.\n"
            "Comandos: [cyan]/help[/cyan]  [cyan]/clear[/cyan]  [cyan]/history[/cyan]  "
            "[cyan]/sessions[/cyan]  [cyan]/exit[/cyan] · Ctrl+D para salir[/dim]",
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
            content = f"[{len(content)} bloque(s)]"
        elif isinstance(content, str) and len(content) > 120:
            content = content[:120] + "…"
        color = "cyan" if role == "user" else "green"
        console.print(f"[dim]{i + 1:2d}[/dim] [{color}]{role:9s}[/{color}] {content}")


def _print_sessions(storage_path: str) -> None:
    sessions = list_sessions(storage_path)
    if not sessions:
        console.print("[dim]No hay sesiones guardadas en disco.[/dim]")
        return
    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("ID de sesión", style="cyan")
    table.add_column("Mensajes", style="dim", justify="right")
    table.add_column("Tamaño", style="dim", justify="right")
    table.add_column("Última modificación", style="dim")
    for s in sessions:
        ts = datetime.fromtimestamp(s["modified"]).strftime("%Y-%m-%d %H:%M")
        table.add_row(s["session_id"], str(s["messages"]), f"{s['size_kb']} KB", ts)
    console.print(
        Panel(
            table,
            title=f"[bold]Sesiones guardadas ({len(sessions)})[/bold]",
            border_style="dim",
            padding=(1, 1),
        )
    )


async def run_repl(
    adapter: ProviderAdapter,
    config: KlausConfig,
    project_root: Path,
    session_name: str | None = None,
    persist: bool = True,
    streaming: bool = True,
) -> int:
    """Arranca el REPL interactivo — mantiene historial entre turnos del usuario."""
    configure_confirmations(
        auto_approve_writes=config.behavior.auto_approve_writes,
        auto_approve_bash=config.behavior.auto_approve_bash,
    )

    cwd = project_root
    ctx = load_project_context(cwd, max_tokens=config.context.max_Klaus_md_tokens)
    system_prompt = ctx.get("system_prompt")

    effective_persist = persist and config.session.persist
    lock_enabled = config.session.lock_enabled
    effective_streaming = streaming and config.behavior.streaming

    session_mgr = SessionManager(
        storage_path=config.session.storage_path,
        project_root=cwd,
        session_name=session_name,
    )
    lock = SessionLock(
        storage_path=config.session.storage_path,
        project_root=cwd,
        session_name=session_name,
        enabled=lock_enabled,
    )

    if not lock.acquire():
        return 1

    mcp = MCPRegistry()
    active_schemas = list(TOOL_SCHEMAS)
    active_handlers: dict[str, Any] = dict(TOOL_HANDLERS)

    try:
        if config.mcp_servers:
            await mcp.startup(config.mcp_servers)
            active_schemas.extend(mcp.schemas)
            active_handlers.update(mcp.handlers)

        messages: list[dict[str, Any]] = session_mgr.load() if effective_persist else []
        resumed = bool(messages)

        from . import __version__
        _print_welcome(
            version=__version__,
            session_id=session_mgr.session_id,
            persist=effective_persist,
            resumed=resumed,
            streaming=effective_streaming,
        )

        return await _repl_loop(
            adapter=adapter,
            config=config,
            cwd=cwd,
            system_prompt=system_prompt,
            active_schemas=active_schemas,
            active_handlers=active_handlers,
            messages=messages,
            session_mgr=session_mgr,
            persist=effective_persist,
            streaming=effective_streaming,
        )
    finally:
        lock.release()
        await mcp.shutdown()


async def _repl_loop(
    adapter: ProviderAdapter,
    config: KlausConfig,
    cwd: Path,
    system_prompt: str | None,
    active_schemas: list[dict[str, Any]],
    active_handlers: dict[str, Any],
    messages: list[dict[str, Any]],
    session_mgr: SessionManager,
    persist: bool,
    streaming: bool,
) -> int:
    """Loop principal del REPL."""
    while True:
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

        cmd = stripped.lower()
        if cmd in ("/exit", "/quit"):
            console.print("[dim]¡Hasta pronto![/dim]")
            return 0
        if cmd == "/clear":
            if persist:
                session_mgr.clear()
            messages = []
            console.print("[dim]Historial limpiado — nueva sesión iniciada.[/dim]")
            continue
        if cmd == "/help":
            _print_help()
            continue
        if cmd == "/history":
            _print_history(messages)
            continue
        if cmd == "/sessions":
            _print_sessions(config.session.storage_path)
            continue

        messages.append({"role": "user", "content": stripped})
        messages = await _run_turn(
            messages=messages,
            adapter=adapter,
            config=config,
            cwd=cwd,
            system_prompt=system_prompt,
            active_schemas=active_schemas,
            active_handlers=active_handlers,
            streaming=streaming,
        )

        if persist:
            try:
                session_mgr.save(messages)
            except Exception as e:
                console.print(f"[yellow]⚠️  No se pudo guardar la sesión: {e}[/yellow]")


async def _run_turn(
    messages: list[dict[str, Any]],
    adapter: ProviderAdapter,
    config: KlausConfig,
    cwd: Path,
    system_prompt: str | None,
    active_schemas: list[dict[str, Any]],
    active_handlers: dict[str, Any],
    streaming: bool = True,
) -> list[dict[str, Any]]:
    """Procesa un turno completo (usuario → modelo → tools* → modelo) y devuelve los mensajes actualizados."""
    max_turns = config.behavior.max_agent_turns
    total_input: int = 0
    total_output: int = 0

    for turn in range(max_turns):
        renderer = StreamRenderer(console)
        renderer.start()
        try:
            if streaming:
                response = await adapter.stream_message(
                    messages=messages,
                    tools=active_schemas,
                    system=system_prompt,
                    on_token=renderer.on_token,
                )
            else:
                response = await adapter.send_message(
                    messages=messages,
                    tools=active_schemas,
                    system=system_prompt,
                )
        except Exception as e:
            renderer.stop()
            console.print(f"[red]Error de red (turno {turn + 1}):[/red] {e}")
            return messages

        renderer.stop()

        usage = adapter.extract_usage(response)
        total_input += usage["input_tokens"]
        total_output += usage["output_tokens"]

        stop = adapter.stop_reason(response)
        tool_calls = adapter.extract_tool_calls(response)

        if not streaming:
            text = adapter.extract_text(response)
            if text:
                console.print(Markdown(text))

        if total_input > 0:
            ctx_pct = int(total_input / config.context.max_context_tokens * 100)
            console.print(
                f"[dim]📊 tokens — input: {total_input:,} ({ctx_pct}%) "
                f"| output: {total_output:,}[/dim]"
            )

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
