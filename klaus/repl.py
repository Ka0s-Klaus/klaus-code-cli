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

from .agent import _dispatch_tool
from .config import KlausConfig
from .context import compact_messages, load_project_context
from .mcp.client import MCPRegistry
from .provider.base import ProviderAdapter
from .sessions import SessionLock, SessionManager, list_sessions
from .streaming import StreamRenderer
from .tools import TOOL_HANDLERS, TOOL_SCHEMAS, configure_confirmations

console = Console()

_PROMPT = "(Klaus) ❯ "

_SPECIAL_COMMANDS = {
    "/exit": "Salir del REPL",
    "/quit": "Salir del REPL",
    "/clear": "Limpiar el historial de conversación (nueva sesión con contexto en blanco)",
    "/help": "Mostrar este mensaje de ayuda",
    "/history": "Mostrar el historial de mensajes de la sesión actual",
    "/sessions": "Listar sesiones guardadas en disco",
    "/tokens": "Mostrar el conteo de tokens acumulados en la sesión actual",
    # Fase 1
    "/model [nombre]": "Ver o cambiar el modelo activo en esta sesión",
    # Fase 3
    "/todos": "Mostrar la lista de tareas de la sesión actual",
    # Fase 7 (custom): los comandos de ~/.Klaus/commands/ se añaden dinámicamente
    # Fase 8
    "/memory list": "Listar memorias persistentes en ~/.Klaus/memory/",
    "/memory add <nombre> <contenido>": "Crear o actualizar una memoria",
    # Fase 9
    "/checkpoint [nombre]": "Crear un checkpoint del estado actual de la conversación",
    "/checkpoints": "Listar checkpoints de la sesión actual",
}


def _print_welcome(
    version: str,
    session_id: str,
    persist: bool,
    resumed: bool,
    streaming: bool,
    yolo: bool = False,
    model: str = "",
) -> None:
    session_line = (
        f"[dim]Sesión:[/dim] [cyan]{session_id}[/cyan]"
        if persist
        else "[dim]Sesión:[/dim] [yellow]efímera (--no-persist)[/yellow]"
    )
    resumed_line = "  [green]↩ Historial previo cargado[/green]" if resumed else ""
    stream_line = "  [dim]streaming: on[/dim]" if streaming else "  [dim]streaming: off[/dim]"
    yolo_line = "  [yellow bold]⚡ YOLO MODE[/yellow bold] [dim](sin confirmaciones interactivas)[/dim]" if yolo else ""
    model_line = f"  [dim]modelo: {model}[/dim]" if model else ""
    console.print(
        Panel(
            f"[bold cyan]🤖 Klaus Code CLI[/bold cyan] [dim]v{version}[/dim] — [bold]REPL interactivo[/bold]\n\n"
            f"{session_line}{resumed_line}{stream_line}{yolo_line}{model_line}\n\n"
            "[dim]Escribe un prompt y pulsa Enter. El modelo recuerda el contexto de la sesión.\n"
            "Comandos: [cyan]/help[/cyan]  [cyan]/clear[/cyan]  [cyan]/history[/cyan]  "
            "[cyan]/sessions[/cyan]  [cyan]/exit[/cyan] · Ctrl+D para salir[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def _print_help(custom_commands: dict[str, str] | None = None) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column(style="dim")
    for cmd, desc in _SPECIAL_COMMANDS.items():
        table.add_row(cmd, desc)
    if custom_commands:
        table.add_row("[bold]── Custom ──[/bold]", "")
        for slash_cmd, prompt_tmpl in sorted(custom_commands.items()):
            preview = prompt_tmpl[:60] + "…" if len(prompt_tmpl) > 60 else prompt_tmpl
            table.add_row(slash_cmd, preview)
    console.print(
        Panel(
            table,
            title="[bold]Comandos del REPL[/bold]",
            border_style="dim",
            padding=(1, 1),
        )
    )


def _load_custom_commands(cwd: Path) -> dict[str, str]:
    """Carga comandos slash personalizados de ~/.Klaus/commands/ y .Klaus/commands/.

    Cada fichero .md es un comando: el nombre del fichero (sin extensión, con / prefijo)
    es el comando, y el contenido es el prompt. $ARGUMENTS se reemplaza con los args del usuario.
    """
    commands: dict[str, str] = {}
    search_dirs = [
        Path.home() / ".Klaus" / "commands",
        cwd / ".Klaus" / "commands",
    ]
    for commands_dir in search_dirs:
        if not commands_dir.is_dir():
            continue
        for md_file in sorted(commands_dir.glob("*.md")):
            try:
                content = md_file.read_text(encoding="utf-8").strip()
                if content:
                    slash_name = f"/{md_file.stem.lower()}"
                    commands[slash_name] = content
            except OSError:
                pass
    return commands


def _remove_memory(name: str) -> None:
    """Elimina una memoria de ~/.Klaus/memory/ y su entrada del índice MEMORY.md."""
    memory_dir = Path.home() / ".Klaus" / "memory"
    mem_file = memory_dir / f"{name}.md"

    if not mem_file.exists():
        console.print(f"[red]Memoria no encontrada:[/red] [cyan]{name}[/cyan]")
        return

    try:
        mem_file.unlink()
        console.print(f"[green]✅ Memoria eliminada:[/green] [cyan]{name}[/cyan]")

        index_path = memory_dir / "MEMORY.md"
        if index_path.exists():
            lines = index_path.read_text(encoding="utf-8").splitlines(keepends=True)
            new_lines = [l for l in lines if name not in l]
            index_path.write_text("".join(new_lines), encoding="utf-8")
    except OSError as e:
        console.print(f"[red]Error eliminando memoria: {e}[/red]")


def _print_checkpoints(storage_path: str, session_id: str) -> None:
    """Muestra los checkpoints de la sesión en una tabla Rich."""
    from .sessions import list_checkpoints

    checkpoints = list_checkpoints(storage_path, session_id)
    if not checkpoints:
        console.print("[dim]💾 No hay checkpoints para esta sesión.[/dim]")
        return

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("ID / Nombre", style="cyan")
    table.add_column("Mensajes", style="dim", justify="right")
    table.add_column("Creado", style="dim")
    table.add_column("Tamaño", style="dim", justify="right")

    for cp in checkpoints:
        ts = datetime.fromtimestamp(cp["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        table.add_row(
            cp["name"],
            str(cp["messages"]),
            ts,
            f"{cp['size_kb']} KB",
        )

    console.print(
        Panel(
            table,
            title=f"[bold]💾 Checkpoints de sesión ({len(checkpoints)})[/bold]",
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
    initial_messages: list[dict[str, Any]] | None = None,
    persist: bool = True,
    streaming: bool = True,
    yolo: bool = False,
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

        # Prioridad: initial_messages (--restore checkpoint) > sesión en disco > vacío
        if initial_messages is not None:
            messages = initial_messages
        elif effective_persist:
            messages = session_mgr.load()
        else:
            messages = []
        resumed = bool(messages)

        # ── Cargar custom slash commands (Fase 7) ─────────────────────────────
        custom_commands = _load_custom_commands(cwd)

        from . import __version__
        _print_welcome(
            version=__version__,
            session_id=session_mgr.session_id,
            persist=effective_persist,
            resumed=resumed,
            streaming=effective_streaming,
            yolo=yolo,
            model=config.provider.model,
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
            custom_commands=custom_commands,
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
    custom_commands: dict[str, str] | None = None,
) -> int:
    """Loop principal del REPL."""
    from .sessions import list_checkpoints, save_checkpoint
    from .tools.memory import print_memory_list
    from .tools.todo import get_todos_for_display

    session_input_tokens: int = 0
    session_output_tokens: int = 0
    _custom_cmds = custom_commands or {}

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
        cmd_parts = stripped.split(None, 1)  # split en max 2 partes para args

        # ── Comandos básicos ──────────────────────────────────────────────────
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
            _print_help(_custom_cmds)
            continue

        if cmd == "/history":
            _print_history(messages)
            continue

        if cmd == "/tokens":
            total = session_input_tokens + session_output_tokens
            console.print(
                Panel(
                    f"[cyan]Input:[/cyan]  {session_input_tokens:,} tokens\n"
                    f"[green]Output:[/green] {session_output_tokens:,} tokens\n"
                    f"[bold]Total:[/bold]   {total:,} tokens",
                    title="[bold]📊 Tokens de sesión[/bold]",
                    border_style="dim",
                    padding=(0, 2),
                )
            )
            continue

        if cmd == "/sessions":
            _print_sessions(config.session.storage_path)
            continue

        # ── Fase 1: /model ─────────────────────────────────────────────────────
        if cmd == "/model" or cmd.startswith("/model "):
            args = stripped[len("/model"):].strip()
            if args:
                config.provider.model = args
                console.print(f"[green]✅ Modelo cambiado a:[/green] [cyan]{args}[/cyan]")
                console.print("[dim]El cambio aplica al siguiente turno de conversación.[/dim]")
            else:
                console.print(
                    Panel(
                        f"[cyan]Modelo activo:[/cyan] [bold]{config.provider.model}[/bold]\n"
                        "[dim]Usa /model <nombre> para cambiar, e.g. /model claude-opus-4-8[/dim]",
                        title="[bold]🤖 Modelo[/bold]",
                        border_style="dim",
                        padding=(0, 1),
                    )
                )
            continue

        # ── Fase 3: /todos ────────────────────────────────────────────────────
        if cmd == "/todos":
            todos = get_todos_for_display()
            if not todos:
                console.print("[dim]📋 No hay tareas en la sesión actual.[/dim]")
            else:
                from .tools.todo import _print_todos
                _print_todos(todos)
            continue

        # ── Fase 8: /memory ───────────────────────────────────────────────────
        if cmd == "/memory" or cmd.startswith("/memory "):
            args = stripped[len("/memory"):].strip()
            subcmd = args.split(None, 1)[0].lower() if args else "list"

            if subcmd == "list" or not args:
                print_memory_list()
            elif subcmd == "add":
                rest = args[len("add"):].strip()
                if not rest:
                    console.print("[red]Uso: /memory add <nombre> <contenido>[/red]")
                else:
                    parts2 = rest.split(None, 1)
                    mem_name = parts2[0]
                    mem_content = parts2[1] if len(parts2) > 1 else ""
                    if not mem_content:
                        console.print("[red]Uso: /memory add <nombre> <contenido>[/red]")
                    else:
                        from .tools.memory import memory_write as _mwrite
                        result = await _mwrite(name=mem_name, content=mem_content)
                        if result.get("error"):
                            console.print(f"[red]{result['error']}[/red]")
            elif subcmd == "remove":
                rest = args[len("remove"):].strip()
                if not rest:
                    console.print("[red]Uso: /memory remove <nombre>[/red]")
                else:
                    _remove_memory(rest)
            else:
                console.print(f"[red]Subcomando desconocido: {subcmd}. Usa list|add|remove[/red]")
            continue

        # ── Fase 9: /checkpoint y /checkpoints ───────────────────────────────
        if cmd == "/checkpoint" or cmd.startswith("/checkpoint "):
            cp_name = stripped[len("/checkpoint"):].strip() or None
            try:
                cp = save_checkpoint(
                    config.session.storage_path,
                    session_mgr.session_id,
                    messages,
                    name=cp_name,
                )
                console.print(
                    f"[green]💾 Checkpoint creado:[/green] [cyan]{cp['checkpoint_id']}[/cyan] "
                    f"[dim]({cp['messages']} mensajes)[/dim]"
                )
            except Exception as e:
                console.print(f"[red]Error creando checkpoint: {e}[/red]")
            continue

        if cmd in ("/checkpoints", "/checkpoints list"):
            _print_checkpoints(config.session.storage_path, session_mgr.session_id)
            continue

        # ── Fase 7: Custom slash commands ─────────────────────────────────────
        if stripped.startswith("/") and not stripped.startswith("//"):
            slash_name = cmd_parts[0].lower()
            if slash_name in _custom_cmds:
                arguments = cmd_parts[1] if len(cmd_parts) > 1 else ""
                prompt_text = _custom_cmds[slash_name].replace("$ARGUMENTS", arguments)
                console.print(
                    f"[dim]⚡ Ejecutando comando personalizado: {slash_name}[/dim]"
                )
                messages.append({"role": "user", "content": prompt_text})
                messages, turn_in, turn_out = await _run_turn(
                    messages=messages,
                    adapter=adapter,
                    config=config,
                    cwd=cwd,
                    system_prompt=system_prompt,
                    active_schemas=active_schemas,
                    active_handlers=active_handlers,
                    streaming=streaming,
                )
                session_input_tokens += turn_in
                session_output_tokens += turn_out
                if persist:
                    try:
                        session_mgr.save(messages)
                    except Exception as e:
                        console.print(f"[yellow]⚠️  No se pudo guardar la sesión: {e}[/yellow]")
                continue
            elif slash_name not in {k.split()[0] for k in _SPECIAL_COMMANDS}:
                console.print(
                    f"[yellow]Comando desconocido: {slash_name}[/yellow] "
                    "[dim]— usa /help para ver los disponibles[/dim]"
                )
                continue

        # ── Input normal → agente ─────────────────────────────────────────────
        messages.append({"role": "user", "content": stripped})
        messages, turn_in, turn_out = await _run_turn(
            messages=messages,
            adapter=adapter,
            config=config,
            cwd=cwd,
            system_prompt=system_prompt,
            active_schemas=active_schemas,
            active_handlers=active_handlers,
            streaming=streaming,
        )
        session_input_tokens += turn_in
        session_output_tokens += turn_out

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
) -> tuple[list[dict[str, Any]], int, int]:
    """Procesa un turno (usuario → modelo → tools* → modelo). Devuelve (mensajes, tokens_input, tokens_output)."""
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
                    on_thinking=renderer.on_thinking,
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
            return messages, total_input, total_output

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
            return messages, total_input, total_output

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
        return messages, total_input, total_output

    console.print(
        f"[yellow]⚠️  Límite de {max_turns} turnos alcanzado para este input[/yellow]"
    )
    return messages, total_input, total_output
