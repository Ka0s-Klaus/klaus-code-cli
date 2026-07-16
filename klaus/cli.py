"""Entrypoint principal del CLI."""

from __future__ import annotations

import asyncio
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
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Directorio del proyecto"),
) -> None:
    """Ejecuta el agente con tool calling en modo no interactivo."""
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
            # Primer ping para mostrar spinner — el loop lo gestiona internamente
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
    scan: bool = typer.Option(False, "--scan", help="Explora el proyecto y genera KLAUS.md"),
) -> None:
    """Crea ~/.Klaus/config.yaml con valores por defecto."""
    config_dir = Path.home() / ".Klaus"
    config_dir.mkdir(parents=True, exist_ok=True)

    if CONFIG_PATH.exists():
        console.print(f"[yellow]⚠️[/yellow]  {CONFIG_PATH} ya existe — no se sobreescribe")
        console.print("[dim]Usa `Klaus config show` para ver la configuración activa[/dim]")
        return

    CONFIG_PATH.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    console.print(f"[green]✅[/green]  Configuración creada en [bold]{CONFIG_PATH}[/bold]")
    console.print("[dim]Edita base_url para apuntar a tu proxy (default: http://localhost:8080/v1)[/dim]")

    if scan:
        console.print("[yellow]--scan aún no implementado (Fase 5)[/yellow]")


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
