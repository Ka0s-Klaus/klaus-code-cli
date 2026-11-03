"""Tool run_bash: ejecuta comandos shell con safety checks y confirmación.

Capas, en orden:
  1. Denylist de patrones peligrosos (siempre). **Best effort**: detecta errores
     y descuidos habituales, pero NO es una frontera de seguridad. Un comando
     ofuscado puede evadirla. Ver docs/security.md.
  2. ``security.bash_allowlist`` (si está definida y bash está auto-aprobado):
     lo que no encaje se confirma con el usuario, o se rechaza sin TTY.
  3. Confirmación interactiva (CONFIRM_BASH, desactivada por --allow-bash/--yolo).

run_bash no está confinado al workspace: un comando shell puede acceder a
cualquier ruta del usuario. Esa es la razón de que la confirmación sea la
barrera real.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax

console = Console()

# Límite de caracteres en stdout/stderr devueltos al modelo
OUTPUT_CHAR_LIMIT = 20_000

# Puesto en False por --allow-bash / --yolo
CONFIRM_BASH: bool = True

# Patrones peligrosos — se bloquean siempre, sin importar CONFIRM_BASH
_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-[a-z]*r[a-z]*\s+/(?:\s|$)", "rm -r / (borrado recursivo de raíz)"),
    (r"rm\s+-[a-z]*f[a-z]*\s+/(?:\s|$)", "rm -f / (borrado forzado de raíz)"),
    (r"rm\s+-rf\b", "rm -rf"),
    (r"rm\s+-fr\b", "rm -fr"),
    # rm recursivo + forzado con flags separados o largos: rm -r -f, rm --recursive --force
    (
        r"\brm\b(?=[^;&|\n]*\s(?:-[a-z]*r[a-z]*|--recursive)\b)"
        r"(?=[^;&|\n]*\s(?:-[a-z]*f[a-z]*|--force)\b)",
        "rm recursivo forzado (flags separados)",
    ),
    (r"\bfind\s+(?:/|~|\$HOME)\S*\s.*-delete\b", "find -delete sobre raíz/home"),
    (r"\bfind\s+(?:/|~|\$HOME)\S*\s.*-exec\s+rm\b", "find -exec rm sobre raíz/home"),
    (r">\s*/dev/(?:sd[a-z]|nvme\d|disk\d)", "sobreescritura de dispositivo de bloque"),
    (r"dd\s+.*of=/dev/(?:sd|nvme|disk|rdisk)", "dd a dispositivo de bloque"),
    (r"mkfs\b", "mkfs (formatear sistema de ficheros)"),
    (r":(\s*\)\s*){2,}\s*\|", "fork bomb"),
    (r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}", "fork bomb"),
    # Ejecución de contenido dinámico u ofuscado
    (r"\|\s*(?:sudo\s+)?(?:ba|z|da|k|fi)?sh\b(?!\S)", "pipe a un intérprete de shell"),
    (r"\$\([^)]*base64\s+(?:-d|-D|--decode)\b", "ejecución de contenido base64 (comando ofuscado)"),
    (r"\beval\s+[\"']?\$\(", "eval de sustitución de comando"),
    (r"(?:>|\btee\b).*(?:~|\$HOME|/Users/[^/\s]+|/home/[^/\s]+)/\.ssh/", "escritura en ~/.ssh"),
    (r"curl\s+.*\|\s*(bash|sh|zsh|fish)", "curl | shell (ejecución remota sin verificar)"),
    (r"wget\s+.*-O\s*-.*\|\s*(bash|sh|zsh|fish)", "wget | shell"),
    (r"sudo\s+su\b", "sudo su (escalada de privilegios total)"),
    (r"sudo\s+passwd\b", "sudo passwd"),
    (r"chmod\s+(?:-R\s+)?777\s+/", "chmod 777 / (permisos globales en raíz)"),
    (r"\$\(curl\b", "command substitution con curl"),
    (r"python[23]?\s+-c\s+['\"]import\s+os.*system", "python -c os.system (posible ejecución disfrazada)"),
]


def _check_dangerous(command: str) -> str | None:
    """Devuelve descripción del patrón peligroso detectado, o None si el comando es seguro."""
    for pattern, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return description
    return None


def _confirm_run(command: str) -> bool | str:
    """True/False según el usuario; str con el motivo si se rechaza sin preguntar."""
    from ..security import bash_allowed, bash_allowlist_active, is_interactive

    if not CONFIRM_BASH:
        if not bash_allowlist_active() or bash_allowed(command):
            return True
        # Auto-aprobado, pero fuera de la allowlist → requiere a un humano
        if not is_interactive():
            return (
                "Comando fuera de security.bash_allowlist en modo no interactivo. "
                "Solo se permiten comandos simples (sin ;, &&, |, $(...), redirecciones) "
                "que empiecen por un prefijo de la allowlist."
            )
        console.print("[yellow]⚠️  Comando fuera de security.bash_allowlist[/yellow]")
    return Confirm.ask("¿Ejecutar el comando anterior?", default=False)


async def run_bash(
    command: str,
    timeout: int = 30,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Ejecuta un comando shell con safety checks, confirmación y timeout."""
    # Safety check — antes de mostrar nada
    danger = _check_dangerous(command)
    if danger:
        console.print(
            Panel(
                f"[red bold]🚫 Comando bloqueado[/red bold]\n\n"
                f"[yellow]{command}[/yellow]\n\n"
                f"[red]Patrón peligroso detectado:[/red] {danger}",
                title="[red]run_bash — BLOQUEADO[/red]",
                border_style="red",
            )
        )
        return {
            "error": f"Comando bloqueado por patrón peligroso: {danger}",
            "command": command,
        }

    # Mostrar el comando completo antes de pedir confirmación
    console.print(
        Panel(
            Syntax(command, "bash", theme="monokai"),
            title=f"[cyan]⚙️  run_bash[/cyan] [dim](timeout: {timeout}s)[/dim]",
            border_style="cyan",
        )
    )

    decision = _confirm_run(command)
    if isinstance(decision, str):
        return {"error": decision, "command": command}
    if not decision:
        return {"status": "cancelled", "command": command}

    work_dir = str(cwd) if cwd else None

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return {
                "error": f"Timeout de {timeout}s alcanzado. Proceso terminado.",
                "command": command,
                "exit_code": -1,
            }
    except Exception as e:
        return {"error": f"Error al lanzar el proceso: {e}", "command": command}

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    exit_code = proc.returncode

    truncated = False
    if len(stdout) > OUTPUT_CHAR_LIMIT:
        stdout = stdout[:OUTPUT_CHAR_LIMIT] + f"\n... [TRUNCADO — {len(stdout):,} caracteres totales]"
        truncated = True
    if len(stderr) > OUTPUT_CHAR_LIMIT:
        stderr = stderr[:OUTPUT_CHAR_LIMIT] + f"\n... [TRUNCADO — {len(stderr):,} caracteres totales]"
        truncated = True

    # Mostrar output en consola
    if stdout.strip():
        console.print(
            Panel(
                stdout.rstrip(),
                title=f"[green]stdout[/green] [dim](exit {exit_code})[/dim]",
                border_style="green" if exit_code == 0 else "yellow",
            )
        )
    if stderr.strip():
        console.print(
            Panel(
                stderr.rstrip(),
                title="[red]stderr[/red]",
                border_style="red",
            )
        )

    result: dict[str, Any] = {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "command": command,
    }
    if truncated:
        result["truncated"] = True
    return result
