"""Tools de escritura: write_file, edit_file, delete_file.

Todas las operaciones muestran una preview/diff antes de ejecutar
y piden confirmación interactiva al usuario.

Desactivar confirmación globalmente (modo --yolo futuro):
    import Klaus.tools.write as wt; wt.CONFIRM_WRITES = False
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax

console = Console()

# Puesto en False por el futuro modo --yolo / --allow-writes
CONFIRM_WRITES: bool = True


def _resolve(path: str, cwd: Path | None) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (cwd or Path.cwd()) / p
    return p.resolve()


def _unified_diff(old_lines: list[str], new_lines: list[str], fromfile: str, tofile: str) -> str:
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    )
    return "\n".join(diff)


def _show_diff(diff_text: str, title: str) -> None:
    if not diff_text.strip():
        console.print("[dim]Sin cambios.[/dim]")
        return
    console.print(
        Panel(
            Syntax(diff_text, "diff", theme="monokai"),
            title=title,
            border_style="yellow",
        )
    )


def _confirm(prompt: str) -> bool:
    if not CONFIRM_WRITES:
        return True
    return Confirm.ask(prompt, default=False)


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


async def write_file(
    path: str,
    content: str,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Crea o sobreescribe un fichero con confirmación y diff/preview."""
    target = _resolve(path, cwd)

    if target.exists() and not target.is_file():
        return {"error": f"La ruta existe y no es un fichero: {path}"}

    if target.exists():
        old_text = target.read_text(encoding="utf-8", errors="replace")
        old_lines = old_text.splitlines(keepends=True)
        new_lines = content.splitlines(keepends=True)
        diff = _unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}")
        _show_diff(diff, f"[yellow]✏️  write_file → {path}[/yellow]")
        if not diff.strip():
            return {"status": "no_changes", "path": str(target)}
    else:
        # Fichero nuevo — mostrar el contenido completo
        preview_lines = content.splitlines()
        preview = "\n".join(f"+{ln}" for ln in preview_lines[:80])
        if len(preview_lines) > 80:
            preview += f"\n... (+{len(preview_lines) - 80} líneas más)"
        console.print(
            Panel(
                Syntax(preview, "diff", theme="monokai"),
                title=f"[green]➕ write_file → {path} (nuevo)[/green]",
                border_style="green",
            )
        )

    if not _confirm(f"¿Escribir '{path}'?"):
        return {"status": "cancelled", "path": str(target)}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    action = "updated" if target.exists() else "created"
    return {
        "status": "ok",
        "action": action,
        "path": str(target),
        "bytes_written": len(content.encode("utf-8")),
    }


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------


async def edit_file(
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Edita un fichero reemplazando old_string por new_string, con diff y confirmación."""
    target = _resolve(path, cwd)

    if not target.exists():
        return {"error": f"Fichero no encontrado: {path}"}
    if not target.is_file():
        return {"error": f"No es un fichero: {path}"}

    old_text = target.read_text(encoding="utf-8", errors="replace")
    occurrences = old_text.count(old_string)

    if occurrences == 0:
        return {"error": f"old_string no encontrado en {path}"}
    if occurrences > 1 and not replace_all:
        return {
            "error": (
                f"old_string aparece {occurrences} veces en {path}. "
                "Usa replace_all=true para reemplazar todas las ocurrencias, "
                "o proporciona más contexto para identificar una única ocurrencia."
            )
        }

    if replace_all:
        new_text = old_text.replace(old_string, new_string)
    else:
        new_text = old_text.replace(old_string, new_string, 1)

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    diff = _unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}")
    _show_diff(diff, f"[yellow]✏️  edit_file → {path}[/yellow]")

    if not _confirm(f"¿Aplicar edición en '{path}'?"):
        return {"status": "cancelled", "path": str(target)}

    target.write_text(new_text, encoding="utf-8")
    return {
        "status": "ok",
        "path": str(target),
        "replacements": occurrences if replace_all else 1,
    }


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------


async def delete_file(
    path: str,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Elimina un fichero con confirmación."""
    target = _resolve(path, cwd)

    if not target.exists():
        return {"error": f"Fichero no encontrado: {path}"}
    if not target.is_file():
        return {"error": f"No es un fichero (usa delete_directory para directorios): {path}"}

    size_bytes = target.stat().st_size
    console.print(
        Panel(
            f"[red]🗑️  {target}[/red]\n[dim]{size_bytes:,} bytes[/dim]",
            title="[red]delete_file[/red]",
            border_style="red",
        )
    )

    if not _confirm(f"¿Eliminar permanentemente '{path}'?"):
        return {"status": "cancelled", "path": str(target)}

    target.unlink()
    return {
        "status": "ok",
        "path": str(target),
        "bytes_deleted": size_bytes,
    }
