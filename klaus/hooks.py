"""Sistema de hooks de Klaus — Pre/PostToolUse, Stop, Notification.

Los hooks son scripts ejecutables almacenados en:
  - ~/.Klaus/hooks/<EventName>         (globales)
  - .Klaus/hooks/<EventName>           (proyecto)

Los hooks de proyecto tienen prioridad sobre los globales.

Seguridad (#56): los hooks de proyecto son código del repositorio, que puede ser de
un tercero. Solo se ejecutan si el usuario confía en ellos (ver
``klaus.security.project_hooks_trusted``); los globales son del usuario y se
ejecutan siempre.

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

import asyncio
import json
import os
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

    def _project_dir_has_hooks(self) -> bool:
        d = self._project_dir
        return bool(d and d.is_dir() and any(p.is_file() for p in d.iterdir()))

    def _project_trusted(self) -> bool:
        from .security import project_hooks_trusted

        assert self._project_dir is not None
        return project_hooks_trusted(self._project_dir)

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
        if self._project_dir and self._project_dir_has_hooks() and self._project_trusted():
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
        result = await _run_hook_script(hook, payload)

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
        await _run_hook_script(hook, payload)

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
        await _run_hook_script(hook, payload)

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
        await _run_hook_script(hook, payload)

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
        await _run_hook_script(hook, payload)


async def _run_hook_script(
    hook_path: Path,
    payload: dict[str, Any],
    timeout: int = 10,
) -> dict[str, Any]:
    """Ejecuta un hook con el payload JSON en stdin, sin bloquear el event loop."""
    try:
        proc = await asyncio.create_subprocess_exec(
            str(hook_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        console.print(f"[yellow]⚠️  Error ejecutando hook {hook_path.name}: {e}[/yellow]")
        return {"exit_code": 1, "stdout": "", "stderr": str(e)}

    data = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    try:
        out, err = await asyncio.wait_for(proc.communicate(data), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        console.print(f"[yellow]⚠️  Hook {hook_path.name} excedió el timeout ({timeout}s)[/yellow]")
        return {"exit_code": 1, "stdout": "", "stderr": "timeout"}

    return {
        "exit_code": proc.returncode if proc.returncode is not None else 1,
        "stdout": out.decode("utf-8", errors="replace").strip(),
        "stderr": err.decode("utf-8", errors="replace").strip(),
    }
