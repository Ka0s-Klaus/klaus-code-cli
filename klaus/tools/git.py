"""Tools git: git_status, git_diff, git_commit.

git_status y git_diff son de solo lectura — no piden confirmación.
git_commit muestra el diff y pide confirmación antes de ejecutar.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

OUTPUT_CHAR_LIMIT = 20_000


async def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Ejecuta un subcomando git y devuelve (exit_code, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd),
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    assert proc.returncode is not None
    return proc.returncode, stdout, stderr


async def git_status(
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Devuelve el estado del repositorio git (rama actual + ficheros modificados)."""
    work_dir = cwd or Path.cwd()

    exit_code, stdout, stderr = await _run_git(["status", "--porcelain", "-b"], work_dir)
    if exit_code != 0:
        return {"error": stderr.strip() or "git status falló", "exit_code": exit_code}

    lines = stdout.splitlines()
    branch_line = lines[0] if lines else ""
    # ## main...origin/main  →  extraer rama local
    branch = branch_line.lstrip("# ").split("...")[0] if branch_line.startswith("##") else branch_line

    entries: list[dict[str, str]] = []
    for line in lines[1:]:
        if len(line) >= 3:
            xy = line[:2]
            path = line[3:]
            entries.append({"status": xy.strip(), "path": path})

    if entries or branch:
        console.print(
            Panel(
                stdout.rstrip() or "(árbol limpio)",
                title=f"[blue]git status[/blue] [dim]{branch}[/dim]",
                border_style="blue",
            )
        )

    return {
        "branch": branch,
        "entries": entries,
        "raw": stdout,
    }


async def git_diff(
    staged: bool = False,
    path: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Muestra el diff del repositorio (staged o unstaged)."""
    work_dir = cwd or Path.cwd()

    args = ["diff"]
    if staged:
        args.append("--staged")
    if path:
        args += ["--", path]

    exit_code, stdout, stderr = await _run_git(args, work_dir)
    if exit_code != 0:
        return {"error": stderr.strip() or "git diff falló", "exit_code": exit_code}

    truncated = False
    if len(stdout) > OUTPUT_CHAR_LIMIT:
        stdout = stdout[:OUTPUT_CHAR_LIMIT] + "\n... [TRUNCADO — más contenido omitido]"
        truncated = True

    title_suffix = " --staged" if staged else ""
    title_path = f" {path}" if path else ""
    console.print(
        Panel(
            Syntax(stdout.rstrip() or "(sin cambios)", "diff", theme="monokai"),
            title=f"[blue]git diff{title_suffix}{title_path}[/blue]",
            border_style="blue",
        )
    )

    result: dict[str, Any] = {"diff": stdout, "staged": staged}
    if path:
        result["path"] = path
    if truncated:
        result["truncated"] = True
    return result


async def git_commit(
    message: str,
    paths: list[str] | None = None,
    add_all: bool = False,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Hace git add + git commit con confirmación previa.

    - paths: lista de ficheros a añadir. Si None y add_all=False, solo hace commit de lo staged.
    - add_all: equivalente a git add -A (todos los cambios).
    """
    from rich.prompt import Confirm

    from .write import CONFIRM_WRITES

    work_dir = cwd or Path.cwd()

    # Calcular qué se va a commitear — mostrar diff staged primero
    if paths or add_all:
        # Simular el add para mostrar el diff resultante
        _, diff_out, _ = await _run_git(["diff", "--stat"] + (["--"] + paths if paths else []), work_dir)
        if add_all:
            _, diff_out, _ = await _run_git(["diff", "--stat"], work_dir)
    else:
        _, diff_out, _ = await _run_git(["diff", "--staged", "--stat"], work_dir)

    console.print(
        Panel(
            Syntax(diff_out.rstrip() or "(nada staged aún — se verá tras git add)", "diff", theme="monokai"),
            title=f"[yellow]git commit[/yellow] [dim]\"{message}\"[/dim]",
            border_style="yellow",
        )
    )

    if CONFIRM_WRITES and not Confirm.ask("¿Hacer commit con el mensaje anterior?", default=False):
        return {"status": "cancelled"}

    # git add
    if add_all:
        ec, _, err = await _run_git(["add", "-A"], work_dir)
        if ec != 0:
            return {"error": f"git add -A falló: {err.strip()}", "exit_code": ec}
    elif paths:
        for p in paths:
            ec, _, err = await _run_git(["add", "--", p], work_dir)
            if ec != 0:
                return {"error": f"git add {p} falló: {err.strip()}", "exit_code": ec}

    # git commit
    ec, stdout, stderr = await _run_git(["commit", "-m", message], work_dir)
    if ec != 0:
        return {"error": stderr.strip() or stdout.strip() or "git commit falló", "exit_code": ec}

    console.print(
        Panel(
            stdout.rstrip(),
            title="[green]✅ git commit[/green]",
            border_style="green",
        )
    )
    return {
        "status": "ok",
        "message": message,
        "output": stdout,
    }
