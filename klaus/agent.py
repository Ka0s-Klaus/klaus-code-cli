"""Loop del agente Klaus con tool calling multi-turn y context management."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.spinner import Spinner
from rich.syntax import Syntax

from .config import KlausConfig
from .context import context_usage_line, load_project_context, maybe_compact
from .mcp.client import MCPRegistry
from .provider.base import ProviderAdapter
from .pseudonymizer_config import PseudonymizerError, ensure_pseudonymizer
from .security import configure_security
from .tools import TOOL_HANDLERS, TOOL_SCHEMAS, configure_confirmations

if TYPE_CHECKING:
    from .hooks import HookRunner

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
    configure_security(config, cwd)

    # Cargar contexto del proyecto (CLAUDE.md / CLAUDE.md)
    ctx = load_project_context(cwd, max_tokens=config.context.max_Klaus_md_tokens)
    system_prompt = ctx.get("system_prompt")

    # --- Inicializar MCP ---
    mcp = MCPRegistry()
    active_schemas = list(TOOL_SCHEMAS)
    active_handlers: dict[str, Any] = dict(TOOL_HANDLERS)

    # --- Pseudonymizer: antes de cualquier petición al modelo (#55) ---
    try:
        await ensure_pseudonymizer(config, cwd)
    except PseudonymizerError as e:
        console.print(f"[red]🔒 {e}[/red]")
        return 1

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

    total_input_tokens: int = 0  # consumo acumulado (facturación)
    total_output_tokens: int = 0
    context_tokens: int = 0  # tamaño del contexto en la última petición

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
            context_tokens = usage["input_tokens"]
            console.print(
                context_usage_line(
                    context_tokens,
                    config.context.max_context_tokens,
                    total_input_tokens,
                    total_output_tokens,
                )
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
                result = await _dispatch_tool(
                    tc, config, cwd, active_handlers, schemas=active_schemas
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })

            messages.append({"role": "user", "content": tool_results})

            messages, dropped, threshold = maybe_compact(
                messages,
                context_tokens,
                config.context.max_context_tokens,
                enabled=config.context.auto_compact,
            )
            if dropped > 0:
                console.print(
                    f"[yellow]🗜️  Auto-compact: {dropped} mensajes eliminados "
                    f"(threshold: {threshold:,} tokens)[/yellow]"
                )

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
    hook_runner: HookRunner | None = None,
    session_id: str = "",
    schemas: list[dict[str, Any]] | None = None,
) -> Any:
    """Despacha una tool call: validación → hook PreToolUse → handler → hook PostToolUse.

    ``schemas`` son los schemas activos (built-in + MCP) contra los que se validan
    los parámetros requeridos; por defecto, los built-in.

    El handler se invoca **una sola vez** (#57).
    """
    from .hooks import HookRunner  # import local evita circular

    name = tool_call.get("name", "")
    args = tool_call.get("input", {})
    # `cwd` es reservado: lo inyecta Klaus, nunca el modelo. Si el modelo lo envía,
    # el fallback por TypeError se lo pasaría al handler y saldría del workspace (#56).
    if isinstance(args, dict) and "cwd" in args:
        args = {k: v for k, v in args.items() if k != "cwd"}

    _handlers = handlers if handlers is not None else TOOL_HANDLERS
    handler = _handlers.get(name)
    if not handler:
        return {"error": f"Tool desconocida: {name}"}

    _print_tool_call(name, args)

    # Validar parámetros requeridos antes de invocar el handler.
    # Devuelve un error accionable al modelo en lugar de una excepción Python
    # críptica que provoca bucles de reintentos hasta max_agent_turns.
    _schemas = schemas if schemas is not None else TOOL_SCHEMAS
    _schema = next((s for s in _schemas if s.get("name") == name), None)
    if _schema:
        _required = _schema.get("input_schema", {}).get("required", [])
        _missing = [p for p in _required if p not in args]
        if _missing:
            _params = ", ".join(f"'{p}'" for p in _missing)
            _example = ", ".join(f'{p}="<valor>"' for p in _required)
            return {
                "error": (
                    f"Parámetros requeridos faltantes en '{name}': {_params}. "
                    f"Llama la herramienta con: {name}({_example})"
                )
            }

    # Parámetros que el handler no acepta → error accionable, sin invocarlo
    _accepted, _accepts_any, _wants_cwd = _handler_params(handler)
    if not _accepts_any:
        _unknown = sorted(set(args) - _accepted)
        if _unknown:
            _valid = ", ".join(sorted(_accepted - {"cwd"})) or "(ninguno)"
            return {
                "error": (
                    f"Parámetros desconocidos en '{name}': {', '.join(_unknown)}. "
                    f"Parámetros válidos: {_valid}"
                )
            }

    # ── PreToolUse hook ──────────────────────────────────────────────────────
    runner = hook_runner or HookRunner(project_root=cwd)
    allowed = await runner.run_pre_tool(name, args, session_id=session_id)
    if not allowed:
        return {"error": f"Ejecución de {name} bloqueada por hook PreToolUse"}

    # Una única invocación. Antes, un TypeError lanzado *dentro* del handler
    # provocaba un segundo intento sin cwd: efectos duplicados en otro directorio.
    call_kwargs = {**args, "cwd": cwd} if _wants_cwd else dict(args)
    try:
        result = await handler(**call_kwargs)
    except Exception as e:
        result = {"error": f"Error ejecutando {name}: {e}"}
        await runner.run_post_tool_error(name, args, str(e), session_id=session_id)
        return result

    # ── PostToolUse hook ─────────────────────────────────────────────────────
    await runner.run_post_tool(name, args, result, session_id=session_id)

    return result


def _handler_params(handler: Any) -> tuple[set[str], bool, bool]:
    """(parámetros aceptados, acepta **kwargs, se le debe pasar cwd).

    Sigue ``__wrapped__`` (decoradores como ``guard_workspace``). Si la firma no se
    puede inspeccionar, se asume que acepta cualquier argumento salvo ``cwd``.
    """
    try:
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        return set(), True, False
    params = sig.parameters
    accepts_any = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
    named = {
        n
        for n, p in params.items()
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    return named, accepts_any, "cwd" in named or accepts_any


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
