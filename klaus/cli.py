"""Entrypoint principal del CLI."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table

from . import __version__
from .config import CONFIG_PATH, DEFAULT_CONFIG_YAML, KlausConfig, load_config
from .provider.base import ProviderAdapter

app = typer.Typer(
    name="Klaus",
    help="Klaus Code CLI — agente de codificación agnóstico de proveedor",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Gestión de configuración")
app.add_typer(config_app, name="config")

sessions_app = typer.Typer(help="Gestión de sesiones REPL guardadas")
app.add_typer(sessions_app, name="sessions")

console = Console()

# Ficheros clave que se leen para el contexto de --scan (por orden de relevancia)
_KEY_FILES = [
    "README.md",
    "README.rst",
    "pyproject.toml",
    "setup.py",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    ".github/workflows",
]
_KEY_FILE_CHAR_LIMIT = 2000  # máximo de chars por fichero clave
_TREE_DEPTH = 3


def _get_adapter(config: KlausConfig) -> ProviderAdapter:
    fmt = config.provider.api_format.lower()
    if fmt == "openai":
        from .provider.openai_fmt import OpenAIAdapter
        return OpenAIAdapter(config)
    from .provider.anthropic_fmt import AnthropicAdapter
    return AnthropicAdapter(config)


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Prompt para el agente"),
    model: str | None = typer.Option(None, "--model", "-m", help="Override de modelo"),
    base_url: str | None = typer.Option(None, "--base-url", help="Override de base URL"),
    project: str | None = typer.Option(None, "--project", help="Directorio del proyecto"),
    plan: bool = typer.Option(False, "--plan", help="Modo plan: propone un plan de acción antes de ejecutar"),
    allow_writes: bool = typer.Option(
        False, "--allow-writes",
        help="Auto-aprueba write_file, edit_file, delete_file sin confirmación interactiva",
    ),
    allow_bash: bool = typer.Option(
        False, "--allow-bash",
        help="Auto-aprueba run_bash sin confirmación interactiva (bloques de seguridad siguen activos)",
    ),
    yolo: bool = typer.Option(
        False, "--yolo",
        help="Modo sin confirmaciones: equivale a --allow-writes --allow-bash",
    ),
) -> None:
    """Ejecuta el agente con tool calling."""
    try:
        config = load_config(base_url_override=base_url, model_override=model)
    except Exception as e:
        console.print(f"[red]Error de configuración:[/red] {e}")
        raise typer.Exit(4)

    # Flags de modo (CLI tiene precedencia sobre config.yaml)
    if plan:
        config.behavior.plan_mode = True
    if yolo or allow_writes:
        config.behavior.auto_approve_writes = True
    if yolo or allow_bash:
        config.behavior.auto_approve_bash = True

    if yolo:
        from rich.panel import Panel as _Panel
        console.print(
            _Panel(
                "[yellow bold]⚡ YOLO MODE ACTIVADO[/yellow bold]\n\n"
                "[dim]write_file, edit_file, delete_file y run_bash se ejecutan sin confirmación.\n"
                "Los bloques de seguridad de run_bash siguen activos (rm -rf, curl|bash, etc.).[/dim]",
                title="[yellow]⚠️  Modo sin confirmaciones[/yellow]",
                border_style="yellow",
            )
        )

    project_root = Path(project).resolve() if project else Path.cwd()
    exit_code = asyncio.run(_run_async(prompt, config, project_root))
    raise typer.Exit(exit_code)


async def _run_async(prompt: str, config: KlausConfig, project_root: Path) -> int:
    from .agent import run_agent_loop

    adapter = _get_adapter(config)
    try:
        with Live(
            Spinner("dots", text="[dim]Pensando...[/dim]"),
            console=console,
            transient=True,
        ):
            pass

        return await run_agent_loop(
            prompt=prompt,
            adapter=adapter,
            config=config,
            project_root=project_root,
        )
    except Exception as e:
        console.print(f"[red]Error inesperado:[/red] {e}")
        return 1
    finally:
        await adapter.close()


@app.command()
def init(
    scan: bool = typer.Option(False, "--scan", help="Explora el proyecto y genera CLAUS.md"),
) -> None:
    """Crea ~/.Klaus/config.yaml con valores por defecto. Con --scan, genera CLAUS.md."""
    config_dir = Path.home() / ".Klaus"
    config_dir.mkdir(parents=True, exist_ok=True)

    if CONFIG_PATH.exists():
        console.print(f"[yellow]⚠️[/yellow]  {CONFIG_PATH} ya existe — no se sobreescribe")
        console.print("[dim]Usa `Klaus config show` para ver la configuración activa[/dim]")
    else:
        CONFIG_PATH.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
        console.print(f"[green]✅[/green]  Configuración creada en [bold]{CONFIG_PATH}[/bold]")
        console.print("[dim]Edita base_url para apuntar a tu proxy (default: http://localhost:8080/v1)[/dim]")

    if scan:
        try:
            config = load_config()
        except Exception as e:
            console.print(f"[red]Error cargando configuración:[/red] {e}")
            raise typer.Exit(4)

        asyncio.run(_scan_and_generate(Path.cwd(), config))


async def _scan_and_generate(project_root: Path, config: KlausConfig) -> None:
    """Escanea el proyecto y genera CLAUS.md mediante una llamada one-shot al LLM."""
    from .context import KlausIgnore

    console.print("[cyan]🔍  Analizando estructura del proyecto...[/cyan]")
    ignore = KlausIgnore(project_root)

    # Árbol de directorios (depth <= _TREE_DEPTH)
    tree_lines: list[str] = [str(project_root)]
    for dirpath, dirnames, filenames in os.walk(project_root):
        rel = Path(dirpath).relative_to(project_root)
        depth = len(rel.parts)
        if depth >= _TREE_DEPTH:
            dirnames.clear()
            continue
        dirnames[:] = sorted(
            d for d in dirnames
            if not ignore.is_ignored(Path(dirpath) / d)
        )
        indent = "  " * depth
        for d in dirnames:
            tree_lines.append(f"{indent}📁 {d}/")
        for fname in sorted(filenames):
            if not ignore.is_ignored(Path(dirpath) / fname):
                tree_lines.append(f"{indent}📄 {fname}")

    tree_str = "\n".join(tree_lines[:200])  # limitar a 200 líneas

    # Ficheros clave
    key_content_parts: list[str] = []
    for fname in _KEY_FILES:
        candidate = project_root / fname
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
                trimmed = text[:_KEY_FILE_CHAR_LIMIT]
                if len(text) > _KEY_FILE_CHAR_LIMIT:
                    trimmed += f"\n... [{len(text):,} chars totales, truncado]"
                key_content_parts.append(f"### {fname}\n```\n{trimmed}\n```")
            except OSError:
                pass

    key_content_str = "\n\n".join(key_content_parts) if key_content_parts else "(ninguno)"

    prompt = (
        "Eres un asistente de codificación experto. Analiza el siguiente proyecto y genera "
        "un fichero CLAUS.md conciso y útil que sirva como system prompt para un agente de codificación.\n\n"
        "El fichero debe:\n"
        "- Estar en castellano\n"
        "- Usar Markdown con emojis en los títulos\n"
        "- Tener máximo 500 palabras\n"
        "- Incluir: propósito del proyecto, stack tecnológico, convenciones de código, "
        "patrones importantes, cómo ejecutar tests, cómo arrancar el proyecto\n"
        "- Ser directo y útil para un agente IA que trabaja con el código\n\n"
        f"## Estructura del proyecto\n\n```\n{tree_str}\n```\n\n"
        f"## Ficheros clave\n\n{key_content_str}\n\n"
        "Genera solo el contenido del fichero CLAUS.md, sin explicaciones adicionales."
    )

    adapter = _get_adapter(config)
    console.print("[cyan]🤖  Generando CLAUS.md con el LLM...[/cyan]")
    try:
        response = await adapter.send_message(
            messages=[{"role": "user", "content": prompt}]
        )
        klausmd_content = adapter.extract_text(response)
    except Exception as e:
        console.print(f"[red]Error al llamar al LLM:[/red] {e}")
        return
    finally:
        await adapter.close()

    if not klausmd_content.strip():
        console.print("[red]El LLM devolvió respuesta vacía — CLAUS.md no generado[/red]")
        return

    target = project_root / "CLAUS.md"
    target.write_text(klausmd_content, encoding="utf-8")
    console.print(f"[green]✅  CLAUS.md generado en[/green] [bold]{target}[/bold]")
    console.print("[dim]Revisa y edita el fichero antes de usarlo como contexto[/dim]")



@app.command()
def repl(
    model: str | None = typer.Option(None, "--model", "-m", help="Override de modelo"),
    base_url: str | None = typer.Option(None, "--base-url", help="Override de base URL"),
    project: str | None = typer.Option(None, "--project", help="Directorio del proyecto"),
    session: str | None = typer.Option(
        None, "--session",
        help="Nombre de sesión personalizado (default: hash SHA1 del project_root). "
             "Útil para abrir sesiones paralelas en el mismo directorio.",
    ),
    no_persist: bool = typer.Option(
        False, "--no-persist",
        help="Desactiva el guardado de historial en disco para esta ejecución. "
             "La sesión es efímera y no se reanudará.",
    ),
    no_stream: bool = typer.Option(
        False, "--no-stream",
        help="Desactiva streaming de tokens. Muestra la respuesta completa de una vez.",
    ),
    allow_writes: bool = typer.Option(
        False, "--allow-writes",
        help="Auto-aprueba write_file, edit_file, delete_file sin confirmación interactiva",
    ),
    allow_bash: bool = typer.Option(
        False, "--allow-bash",
        help="Auto-aprueba run_bash sin confirmación interactiva (bloques de seguridad siguen activos)",
    ),
    yolo: bool = typer.Option(
        False, "--yolo",
        help="Modo sin confirmaciones: equivale a --allow-writes --allow-bash",
    ),
) -> None:
    """REPL interactivo — loop de conversación persistente con historial entre turnos."""
    try:
        config = load_config(base_url_override=base_url, model_override=model)
    except Exception as e:
        console.print(f"[red]Error de configuración:[/red] {e}")
        raise typer.Exit(4)

    if yolo or allow_writes:
        config.behavior.auto_approve_writes = True
    if yolo or allow_bash:
        config.behavior.auto_approve_bash = True

    if yolo:
        from rich.panel import Panel as _Panel
        console.print(
            _Panel(
                "[yellow bold]⚡ YOLO MODE ACTIVADO[/yellow bold]\n\n"
                "[dim]write_file, edit_file, delete_file y run_bash se ejecutan sin confirmación.\n"
                "Los bloques de seguridad de run_bash siguen activos (rm -rf, curl|bash, etc.).[/dim]",
                title="[yellow]⚠️  Modo sin confirmaciones[/yellow]",
                border_style="yellow",
            )
        )

    project_root = Path(project).resolve() if project else Path.cwd()
    exit_code = asyncio.run(
        _repl_async(
            config, project_root,
            session_name=session,
            persist=not no_persist,
            streaming=not no_stream,
            yolo=yolo,
        )
    )
    raise typer.Exit(exit_code)


async def _repl_async(
    config: KlausConfig,
    project_root: Path,
    session_name: str | None = None,
    persist: bool = True,
    streaming: bool = True,
    yolo: bool = False,
) -> int:
    from .repl import run_repl

    adapter = _get_adapter(config)
    try:
        return await run_repl(
            adapter=adapter,
            config=config,
            project_root=project_root,
            session_name=session_name,
            persist=persist,
            streaming=streaming,
            yolo=yolo,
        )
    except Exception as e:
        console.print(f"[red]Error inesperado:[/red] {e}")
        return 1
    finally:
        await adapter.close()


@config_app.command("show")
def config_show() -> None:
    """Muestra la configuración activa sin exponer la api_key."""
    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]Error de configuración:[/red] {e}")
        raise typer.Exit(4)

    import json
    data = config.model_dump()
    data["provider"]["api_key_value"] = "***" if config.api_key else "(no definida)"
    console.print_json(json.dumps(data, indent=2, ensure_ascii=False))


@app.callback(invoke_without_command=True)
def version_cb(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Muestra la versión"),
) -> None:
    if version:
        console.print(f"[bold]Klaus Code CLI[/bold] v{__version__}")
        raise typer.Exit()



@sessions_app.command("list")
def sessions_list() -> None:
    """Lista todas las sesiones guardadas en disco."""
    from .sessions import list_sessions as _list_sessions

    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]Error de configuración:[/red] {e}")
        raise typer.Exit(4)

    sessions = _list_sessions(config.session.storage_path)
    if not sessions:
        console.print("[dim]No hay sesiones guardadas.[/dim]")
        return

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("ID de sesión", style="cyan")
    table.add_column("Mensajes", style="dim", justify="right")
    table.add_column("Tamaño", style="dim", justify="right")
    table.add_column("Última modificación", style="dim")
    for s in sessions:
        ts = datetime.fromtimestamp(s["modified"]).strftime("%Y-%m-%d %H:%M")
        table.add_row(s["session_id"], str(s["messages"]), f"{s['size_kb']} KB", ts)

    from rich.panel import Panel as _Panel
    console.print(
        _Panel(
            table,
            title=f"[bold]Sesiones guardadas ({len(sessions)})[/bold]",
            border_style="dim",
            padding=(1, 1),
        )
    )


@sessions_app.command("show")
def sessions_show(
    session_id: str = typer.Argument(..., help="ID de la sesión"),
    raw: bool = typer.Option(False, "--raw", help="Muestra el JSON crudo sin formatear"),
) -> None:
    """Muestra el historial de mensajes de una sesión."""
    from .sessions import get_session

    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]Error de configuración:[/red] {e}")
        raise typer.Exit(4)

    messages = get_session(config.session.storage_path, session_id)
    if messages is None:
        console.print(f"[red]Sesión no encontrada:[/red] {session_id}")
        raise typer.Exit(1)

    if not messages:
        console.print("[dim]La sesión está vacía.[/dim]")
        return

    if raw:
        import json as _json
        console.print_json(_json.dumps(messages, ensure_ascii=False, indent=2))
        return

    for i, msg in enumerate(messages):
        role = msg.get("role", "?")
        content = msg.get("content", "")
        color = "cyan" if role == "user" else "green"
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "?")
                if btype == "tool_use":
                    name = block.get("name", "?")
                    console.print(f"[dim]{i + 1:2d}[/dim] [yellow]{role:9s}[/yellow] 🔧 {name}()")
                elif btype == "tool_result":
                    tid = block.get("tool_use_id", "?")[:8]
                    console.print(f"[dim]{i + 1:2d}[/dim] [dim]{role:9s}[/dim] 📤 result:{tid}…")
                elif btype == "text":
                    text = block.get("text", "")[:200]
                    console.print(f"[dim]{i + 1:2d}[/dim] [{color}]{role:9s}[/{color}] {text}")
        elif isinstance(content, str):
            truncated = content[:200] + ("…" if len(content) > 200 else "")
            console.print(f"[dim]{i + 1:2d}[/dim] [{color}]{role:9s}[/{color}] {truncated}")


@sessions_app.command("clear")
def sessions_clear(
    session_id: str | None = typer.Argument(
        None,
        help="ID de la sesión a borrar. Omitir junto con --all para borrar todas.",
    ),
    all_sessions: bool = typer.Option(
        False, "--all", help="Borra todas las sesiones guardadas en disco."
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Confirmar sin prompt interactivo."
    ),
) -> None:
    """Borra una sesión específica o todas las sesiones guardadas."""
    from rich.prompt import Confirm

    from .sessions import clear_all_sessions, delete_session

    if not session_id and not all_sessions:
        console.print("[red]Error:[/red] Especifica un <session_id> o usa --all")
        raise typer.Exit(1)

    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]Error de configuración:[/red] {e}")
        raise typer.Exit(4)

    if all_sessions:
        if not yes:
            confirmed = Confirm.ask(
                "[yellow]¿Borrar TODAS las sesiones guardadas?[/yellow]", default=False
            )
            if not confirmed:
                console.print("[dim]Cancelado.[/dim]")
                return
        count = clear_all_sessions(config.session.storage_path)
        console.print(f"[green]✅[/green]  {count} sesión(es) eliminada(s).")
        return

    if not yes:
        confirmed = Confirm.ask(
            f"[yellow]¿Borrar la sesión[/yellow] [cyan]{session_id}[/cyan]?", default=False
        )
        if not confirmed:
            console.print("[dim]Cancelado.[/dim]")
            return

    assert session_id is not None  # garantizado por guards previos
    deleted = delete_session(config.session.storage_path, session_id)
    if deleted:
        console.print(f"[green]✅[/green]  Sesión [cyan]{session_id}[/cyan] eliminada.")
    else:
        console.print(f"[red]Sesión no encontrada:[/red] {session_id}")
        raise typer.Exit(1)


def main() -> None:
    app()
