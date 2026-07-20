"""Sistema de hooks de Klaus — Pre/PostToolUse, Stop, Notification.

Los hooks son scripts ejecutables almacenados en:
  - ~/.Klaus/hooks/<EventName>         (globales)
  - .Klaus/hooks/<EventName>           (proyecto)

Los hooks de proyecto tienen prioridad sobre los globales.

Protocolo:
  - El hook recibe un JSON por stdin.
  - Si el hook termina con exit code != 0, la acción asociada se bloquea (solo PreToolUse).
  - El hook puede escribir JSON a stdout para modificar el comportamiento (campo "decision").

Formato JSON de entrada para PreToolUse / PostToolUse:
  {
    "tool_name": "run_bash",
    "tool_input": { ... },
    "session_id": "abc123",
    "event": "PreToolUse"
  }

Para PostToolUse / PostToolUseError se añade "tool_result": { ... }.

Respuesta esperada del hook (stdout JSON opcional):
  {
    "decision": "block" | "approve" | ""   // solo PreToolUse
  }
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()

# Nombres canónicos de eventos
HookEvent = str  # "PreToolUse" | "PostToolUse" | "PostToolUseError" | "Stop" | "Notification"


class HookRunner:
    """Busca y ejecuta hooks para los eventos del ciclo de vida del agente."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._global_dir = Path.home() / ".Klaus" / "hooks"
        self._project_dir = (project_root / ".Klaus" / "hooks") if project_root else None

    def _find_hook(self, event: str, tool_name: str | None = None) -> Path | None:
        """Busca el script de hook más específico disponible.

        Orden de búsqueda (más específico primero):
          1. proyecto/{tool_name}.{event}
          2. proyecto/{event}
          3. global/{tool_name}.{event}
          4. global/{event}
        """
        candidates: list[Path] = []

        dirs: list[Path] = []
        if self._project_dir:
            dirs.append(self._project_dir)
        dirs.append(self._global_dir)

        for d in dirs:
            if not d.exists():
                continue
            if tool_name:
                for ext in ("", ".sh", ".py"):
                    candidates.append(d / f"{tool_name}.{event}{ext}")
            for ext in ("", ".sh", ".py"):
                candidates.append(d / f"{event}{ext}")

        for c in candidates:
            if c.exists() and os.access(c, os.X_OK):
                return c
        return None

    async def run_pre_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        session_id: str = "",
    ) -> bool:
        """Ejecuta el hook PreToolUse. Devuelve True si se permite ejecutar la tool."""
        hook = self._find_hook("PreToolUse", tool_name)
        if not hook:
            return True

        payload = {
            "event": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "session_id": session_id,
        }
        result = _run_hook_script(hook, payload)

        if result["exit_code"] != 0:
            console.print(
                f"[yellow]⚠️  Hook PreToolUse bloqueó la ejecución de {tool_name}[/yellow]"
            )
            if result["stdout"]:
                try:
                    out = json.loads(result["stdout"])
                    if out.get("reason"):
                        console.print(f"[dim]Razón: {out['reason']}[/dim]")
                except json.JSONDecodeError:
                    console.print(f"[dim]{result['stdout'][:200]}[/dim]")
            return False

        if result["stdout"]:
            try:
                out = json.loads(result["stdout"])
                if out.get("decision") == "block":
                    console.print(f"[yellow]⚠️  Hook bloqueó {tool_name}[/yellow]")
                    return False
            except json.JSONDecodeError:
                pass

        return True

    async def run_post_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_result: Any,
        session_id: str = "",
    ) -> None:
        """Ejecuta el hook PostToolUse (resultado informativo, no bloquea)."""
        hook = self._find_hook("PostToolUse", tool_name)
        if not hook:
            return

        payload = {
            "event": "PostToolUse",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_result": tool_result,
            "session_id": session_id,
        }
        _run_hook_script(hook, payload)

    async def run_post_tool_error(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        error: str,
        session_id: str = "",
    ) -> None:
        """Ejecuta el hook PostToolUseError cuando una tool falla."""
        hook = self._find_hook("PostToolUseError", tool_name)
        if not hook:
            return

        payload = {
            "event": "PostToolUseError",
            "tool_name": tool_name,
            "tool_input": tool_input,
            "error": error,
            "session_id": session_id,
        }
        _run_hook_script(hook, payload)

    async def run_stop(self, session_id: str = "", summary: str = "") -> None:
        """Ejecuta el hook Stop cuando el agente completa su tarea."""
        hook = self._find_hook("Stop")
        if not hook:
            return

        payload = {
            "event": "Stop",
            "session_id": session_id,
            "summary": summary,
        }
        _run_hook_script(hook, payload)

    async def run_notification(
        self,
        message: str,
        level: str = "info",
        session_id: str = "",
    ) -> None:
        """Ejecuta el hook Notification para alertas al usuario."""
        hook = self._find_hook("Notification")
        if not hook:
            return

        payload = {
            "event": "Notification",
            "message": message,
            "level": level,
            "session_id": session_id,
        }
        _run_hook_script(hook, payload)


def _run_hook_script(
    hook_path: Path,
    payload: dict[str, Any],
    timeout: int = 10,
) -> dict[str, Any]:
    """Ejecuta un hook script con el payload JSON en stdin. Captura stdout/stderr."""
    try:
        proc = subprocess.run(
            [str(hook_path)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        console.print(f"[yellow]⚠️  Hook {hook_path.name} excedió el timeout ({timeout}s)[/yellow]")
        return {"exit_code": 1, "stdout": "", "stderr": "timeout"}
    except Exception as e:
        console.print(f"[yellow]⚠️  Error ejecutando hook {hook_path.name}: {e}[/yellow]")
        return {"exit_code": 1, "stdout": "", "stderr": str(e)}
