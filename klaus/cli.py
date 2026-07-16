"""Entrypoint principal del CLI."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

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
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override de modelo"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Override de base URL"),
    project: Optional[str] = typer.Option(None, "--project", help="Directorio del proyecto"),
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

    if not config.api_key:
        console.print(
            f"[red]Error:[/red] Variable de entorno [bold]{config.provider.api_key_env}[/bold] no definida.\n"
            f"Ejecuta: [dim]export {config.provider.api_key_env}=tu-api-key[/dim]"
        )
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

        if not config.api_key:
            console.print(
                f"[red]Error:[/red] Variable de entorno [bold]{config.provider.api_key_env}[/bold] "
                "no definida — necesaria para --scan."
            )
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
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override de modelo"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="Override de base URL"),
    project: Optional[str] = typer.Option(None, "--project", help="Directorio del proyecto"),
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

    if not config.api_key:
        console.print(
            f"[red]Error:[/red] Variable de entorno [bold]{config.provider.api_key_env}[/bold] no definida.\n"
            f"Ejecuta: [dim]export {config.provider.api_key_env}=tu-api-key[/dim]"
        )
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
    exit_code = asyncio.run(_repl_async(config, project_root))
    raise typer.Exit(exit_code)


async def _repl_async(config: KlausConfig, project_root: Path) -> int:
    from .repl import run_repl

    adapter = _get_adapter(config)
    try:
        return await run_repl(
            adapter=adapter,
            config=config,
            project_root=project_root,
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


def main() -> None:
    app()
