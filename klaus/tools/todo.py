"""Tool de gestión de tareas en sesión: todo_write y todo_read.

Los todos se almacenan en memoria durante la sesión activa (proceso vivo).
Diseñados para que el LLM gestione su lista de tareas de forma explícita
y el usuario la vea actualizada en tiempo real.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from rich.table import Table

console = Console()

# Estado global de todos — persiste durante el proceso (sesión REPL o run)
_TODOS: list[dict[str, Any]] = []

TodoStatus = Literal["pending", "in_progress", "completed"]


def _get_todos() -> list[dict[str, Any]]:
    return _TODOS


def _set_todos(todos: list[dict[str, Any]]) -> None:
    global _TODOS
    _TODOS = todos


async def todo_write(
    todos: list[dict[str, Any]],
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Sobreescribe la lista de tareas completa.

    Cada todo es un dict con: content (str), status ('pending'|'in_progress'|'completed').
    Mostrar la lista actualizada en consola para feedback visual al usuario.
    """
    validated: list[dict[str, Any]] = []
    for item in todos:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        status = item.get("status", "pending")
        if status not in ("pending", "in_progress", "completed"):
            status = "pending"
        if content:
            validated.append({"content": content, "status": status})

    _set_todos(validated)
    _print_todos(validated)

    return {
        "status": "ok",
        "count": len(validated),
        "todos": validated,
    }


async def todo_read(
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Lee la lista de tareas actual."""
    todos = _get_todos()
    return {
        "todos": todos,
        "count": len(todos),
        "pending": sum(1 for t in todos if t["status"] == "pending"),
        "in_progress": sum(1 for t in todos if t["status"] == "in_progress"),
        "completed": sum(1 for t in todos if t["status"] == "completed"),
    }


def _print_todos(todos: list[dict[str, Any]]) -> None:
    """Muestra la lista de todos en consola con Rich."""
    if not todos:
        console.print("[dim]📋 Lista de tareas vacía.[/dim]")
        return

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("#", style="dim", width=3)
    table.add_column("Estado", width=12)
    table.add_column("Tarea")

    status_icons = {
        "pending": "[dim]⬜ pendiente[/dim]",
        "in_progress": "[yellow]🔄 en curso[/yellow]",
        "completed": "[green]✅ hecho[/green]",
    }

    for i, todo in enumerate(todos, 1):
        icon = status_icons.get(todo["status"], todo["status"])
        table.add_row(str(i), icon, todo["content"])

    from rich.panel import Panel
    console.print(
        Panel(
            table,
            title="[bold]📋 Lista de tareas[/bold]",
            border_style="dim",
            padding=(0, 1),
        )
    )


def get_todos_for_display() -> list[dict[str, Any]]:
    """Acceso externo para mostrar todos desde el REPL (/todos)."""
    return _get_todos()
