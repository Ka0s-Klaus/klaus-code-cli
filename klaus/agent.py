"""Loop del agente Klaus con tool calling multi-turn y context management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.spinner import Spinner
from rich.syntax import Syntax

from .config import KlausConfig
from .context import compact_messages, load_project_context
from .mcp.client import MCPRegistry
from .provider.base import ProviderAdapter
from .tools import TOOL_HANDLERS, TOOL_SCHEMAS, configure_confirmations

console = Console()

_PLAN_MODE_SYSTEM = (
    "\n\n---\n"
    "MODO PLAN ACTIVADO: Analiza la solicitud y presenta un plan detallado numerado "
    "de las acciones que realizarías — qué herramientas usarías, en qué orden y con "
    "qué argumentos específicos. NO ejecutes ninguna herramienta todavía. "
    "Sé concreto y conciso. El usuario confirmará el plan antes de que lo ejecutes."
)


async def run_agent_loop(
    prompt: str,
    adapter: ProviderAdapter,
    config: KlausConfig,
    project_root: Path | None = None,
) -> int:
    """Loop principal del agente.

    - Inicializa servidores MCP configurados (si hay).
    - Si plan_mode está activo: genera plan → pide confirmación → ejecuta.
    - Envía el prompt inicial con las tools disponibles (built-in + MCP).
    - Si el modelo llama tools, las ejecuta y devuelve los resultados.
    - Continúa hasta que stop_reason sea 'end_turn' o se agoten los turnos.
    - Gestiona el contexto: tracking de tokens y auto-compact cuando se aproxima el límite.
    - Devuelve exit code (0 = éxito, 1 = error).
    """
    cwd = project_root or Path.cwd()

    # Aplicar modo no interactivo si está configurado
    configure_confirmations(
        auto_approve_writes=config.behavior.auto_approve_writes,
        auto_approve_bash=config.behavior.auto_approve_bash,
    )

    # Cargar contexto del proyecto (CLAUDE.md / CLAUDE.md)
    ctx = load_project_context(cwd, max_tokens=config.context.max_Klaus_md_tokens)
    system_prompt = ctx.get("system_prompt")

    # --- Inicializar MCP ---
    mcp = MCPRegistry()
    active_schemas = list(TOOL_SCHEMAS)
    active_handlers: dict[str, Any] = dict(TOOL_HANDLERS)

    try:
        if config.mcp_servers:
            await mcp.startup(config.mcp_servers)
            active_schemas.extend(mcp.schemas)
            active_handlers.update(mcp.handlers)

        return await _agent_loop(
            prompt=prompt,
            adapter=adapter,
            config=config,
            cwd=cwd,
            system_prompt=system_prompt,
            active_schemas=active_schemas,
            active_handlers=active_handlers,
        )
    finally:
        await mcp.shutdown()


async def _agent_loop(
    prompt: str,
    adapter: ProviderAdapter,
    config: KlausConfig,
    cwd: Path,
    system_prompt: str | None,
    active_schemas: list[dict[str, Any]],
    active_handlers: dict[str, Any],
) -> int:
    """Loop interno del agente (desacoplado del lifecycle MCP)."""
    messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
    max_turns = config.behavior.max_agent_turns

    total_input_tokens: int = 0
    total_output_tokens: int = 0

    # --- Fase de planificación (opcional) ---
    if config.behavior.plan_mode:
        plan_exit = await _run_plan_phase(
            messages=messages,
            adapter=adapter,
            system_prompt=system_prompt,
        )
        if plan_exit is None:
            return 0
        messages = plan_exit

    for turn in range(max_turns):
        try:
            with Live(
                Spinner("dots", "[dim] Pensando...[/dim]"),
                console=console,
                transient=True,
            ):
                response = await adapter.send_message(
                    messages=messages,
                    tools=active_schemas,
                    system=system_prompt,
                )
        except Exception as e:
            console.print(f"[red]Error de red (turno {turn + 1}):[/red] {e}")
            return 1

        # Tracking de tokens reales
        usage = adapter.extract_usage(response)
        total_input_tokens += usage["input_tokens"]
        total_output_tokens += usage["output_tokens"]

        if usage["input_tokens"] > 0:
            ctx_pct = int(total_input_tokens / config.context.max_context_tokens * 100)
            console.print(
                f"[dim]📊 tokens — input: {total_input_tokens:,} ({ctx_pct}%) "
                f"| output: {total_output_tokens:,}[/dim]"
            )

        stop = adapter.stop_reason(response)
        text = adapter.extract_text(response)
        tool_calls = adapter.extract_tool_calls(response)

        if text:
            console.print(Markdown(text))

        if stop == "end_turn" or not tool_calls:
            return 0

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
                if total_input_tokens >= threshold:
                    messages, dropped = compact_messages(messages, keep_last=6)
                    if dropped > 0:
                        console.print(
                            f"[yellow]🗜️  Auto-compact: {dropped} mensajes eliminados "
                            f"(threshold: {threshold:,} tokens)[/yellow]"
                        )
                        total_input_tokens = 0

            continue

        if stop == "max_tokens":
            console.print("[yellow]⚠️  Límite de tokens alcanzado[/yellow]")
        return 0

    console.print(f"[yellow]⚠️  Límite de {max_turns} turnos alcanzado[/yellow]")
    return 0


async def _run_plan_phase(
    messages: list[dict[str, Any]],
    adapter: ProviderAdapter,
    system_prompt: str | None,
) -> list[dict[str, Any]] | None:
    """Genera un plan de acción y pide confirmación al usuario.

    Devuelve la lista de mensajes enriquecida con el plan si el usuario confirma,
    o None si cancela.
    """
    plan_system = (system_prompt or "") + _PLAN_MODE_SYSTEM

    console.print("[cyan]🗺️  Modo plan activado — generando plan de acción...[/cyan]")
    try:
        response = await adapter.send_message(
            messages=messages,
            system=plan_system,
            # Sin tools: fuerza respuesta solo texto
        )
    except Exception as e:
        console.print(f"[red]Error generando plan:[/red] {e}")
        return None

    plan_text = adapter.extract_text(response)
    if plan_text:
        console.print(
            Panel(
                Markdown(plan_text),
                title="[cyan]📋 Plan propuesto[/cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
    else:
        console.print("[yellow]El modelo no generó un plan — ejecutando directamente.[/yellow]")
        return messages

    if not Confirm.ask("\n¿Ejecutar este plan?", default=False):
        console.print("[yellow]Plan cancelado — sin cambios en el proyecto.[/yellow]")
        return None

    return [
        *messages,
        {"role": "assistant", "content": plan_text},
        {"role": "user", "content": "Plan confirmado. Ejecuta el plan paso a paso."},
    ]


async def _dispatch_tool(
    tool_call: dict[str, Any],
    config: KlausConfig,
    cwd: Path,
    handlers: dict[str, Any] | None = None,
    hook_runner: "HookRunner | None" = None,
    session_id: str = "",
) -> Any:
    """Despacha una tool call al handler correspondiente, con hooks opcionales."""
    from .hooks import HookRunner  # import local evita circular

    name = tool_call.get("name", "")
    args = tool_call.get("input", {})

    _handlers = handlers if handlers is not None else TOOL_HANDLERS
    handler = _handlers.get(name)
    if not handler:
        return {"error": f"Tool desconocida: {name}"}

    _print_tool_call(name, args)

    # ── PreToolUse hook ──────────────────────────────────────────────────────
    runner = hook_runner or HookRunner(project_root=cwd)
    allowed = await runner.run_pre_tool(name, args, session_id=session_id)
    if not allowed:
        return {"error": f"Ejecución de {name} bloqueada por hook PreToolUse"}

    try:
        result = await handler(**args, cwd=cwd)
    except TypeError:
        try:
            result = await handler(**args)
        except Exception as e:
            result = {"error": f"Error ejecutando {name}: {e}"}
            await runner.run_post_tool_error(name, args, str(e), session_id=session_id)
            return result
    except Exception as e:
        result = {"error": f"Error ejecutando {name}: {e}"}
        await runner.run_post_tool_error(name, args, str(e), session_id=session_id)
        return result

    # ── PostToolUse hook ─────────────────────────────────────────────────────
    await runner.run_post_tool(name, args, result, session_id=session_id)

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
