"""Sistema de memoria persistente entre sesiones.

Las memorias se almacenan en ~/.Klaus/memory/ como ficheros Markdown
con frontmatter YAML. Un fichero índice MEMORY.md lista todas las memorias.

Integración con el sistema K* de memoria existente en ~/.claude/projects/.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from rich.console import Console
from rich.table import Table

console = Console()

MemoryType = Literal["user", "feedback", "project", "reference"]

_MEMORY_DIR = Path.home() / ".Klaus" / "memory"
_INDEX_FILE = "MEMORY.md"
_MAX_INDEX_LINES = 200


def _memory_dir() -> Path:
    d = _MEMORY_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


async def memory_write(
    name: str,
    content: str,
    memory_type: MemoryType = "project",
    description: str = "",
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Crea o actualiza una memoria persistente.

    Args:
        name: Slug único (kebab-case, e.g. 'user-profile').
        content: Cuerpo de la memoria en markdown.
        memory_type: 'user' | 'feedback' | 'project' | 'reference'.
        description: Una línea descriptiva para el índice MEMORY.md.
    """
    name = _slugify(name)
    if not name:
        return {"error": "El nombre de la memoria no puede estar vacío"}

    mdir = _memory_dir()
    file_path = mdir / f"{name}.md"

    desc = description or content[:80].replace("\n", " ")
    now = datetime.now(timezone.utc).isoformat()

    body = (
        f"---\n"
        f"name: {name}\n"
        f"description: {desc}\n"
        f"metadata:\n"
        f"  type: {memory_type}\n"
        f"  updated_at: {now}\n"
        f"---\n\n"
        f"{content.strip()}\n"
    )

    action = "updated" if file_path.exists() else "created"
    file_path.write_text(body, encoding="utf-8")

    # Actualizar índice
    _update_index(mdir, name, desc, file_path.name)

    console.print(
        f"[green]🧠 Memoria {action}:[/green] [cyan]{name}[/cyan] [dim]({memory_type})[/dim]"
    )

    return {
        "status": "ok",
        "action": action,
        "name": name,
        "path": str(file_path),
        "type": memory_type,
    }


async def memory_read(
    query: str = "",
    memory_type: MemoryType | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Lee memorias filtrando por query (en nombre/descripción) y/o tipo.

    Si query está vacío, devuelve todas las memorias disponibles.
    """
    mdir = _memory_dir()
    all_memories = _load_all(mdir)

    results = all_memories
    if query:
        q = query.lower()
        results = [
            m for m in results
            if q in m["name"].lower() or q in m["description"].lower() or q in m["content"].lower()
        ]
    if memory_type:
        results = [m for m in results if m["type"] == memory_type]

    return {
        "query": query,
        "results": results,
        "count": len(results),
    }


def _load_all(mdir: Path) -> list[dict[str, Any]]:
    """Carga todas las memorias del directorio."""
    memories = []
    for f in sorted(mdir.glob("*.md")):
        if f.name == _INDEX_FILE:
            continue
        try:
            raw = f.read_text(encoding="utf-8")
            parsed = _parse_memory(raw, f)
            memories.append(parsed)
        except Exception:
            pass
    return memories


def _parse_memory(raw: str, path: Path) -> dict[str, Any]:
    """Extrae frontmatter y contenido de un fichero de memoria."""
    name = path.stem
    description = ""
    mem_type = "project"
    content = raw

    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            fm = parts[1]
            content = parts[2].strip()
            name_m = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
            desc_m = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
            type_m = re.search(r"^\s+type:\s*(.+)$", fm, re.MULTILINE)
            if name_m:
                name = name_m.group(1).strip()
            if desc_m:
                description = desc_m.group(1).strip()
            if type_m:
                mem_type = type_m.group(1).strip()

    return {
        "name": name,
        "description": description,
        "type": mem_type,
        "content": content,
        "path": str(path),
    }


def _update_index(mdir: Path, name: str, description: str, filename: str) -> None:
    """Actualiza MEMORY.md con la entrada de la nueva memoria."""
    index_path = mdir / _INDEX_FILE
    entry = f"- [{name}]({filename}) — {description}"

    if not index_path.exists():
        index_path.write_text(f"# 🧠 Klaus Memory Index\n\n{entry}\n", encoding="utf-8")
        return

    current = index_path.read_text(encoding="utf-8")
    lines = current.splitlines()

    # Actualizar entrada existente o añadir nueva
    slug = f"- [{name}]"
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(slug):
            new_lines.append(entry)
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(entry)

    # Limitar a MAX_INDEX_LINES
    if len(new_lines) > _MAX_INDEX_LINES:
        new_lines = new_lines[:_MAX_INDEX_LINES]

    index_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _slugify(text: str) -> str:
    """Convierte texto a kebab-case slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def get_memory_index_content() -> str:
    """Devuelve el contenido de MEMORY.md para inyección en el system prompt."""
    index = _memory_dir() / _INDEX_FILE
    if not index.exists():
        return ""
    return index.read_text(encoding="utf-8")


def print_memory_list() -> None:
    """Muestra la lista de memorias en consola para /memory list."""
    mdir = _memory_dir()
    memories = _load_all(mdir)

    if not memories:
        console.print("[dim]🧠 No hay memorias guardadas en ~/.Klaus/memory/[/dim]")
        return

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Nombre", style="cyan")
    table.add_column("Tipo", style="dim", width=10)
    table.add_column("Descripción")

    for m in memories:
        table.add_row(m["name"], m["type"], m["description"][:60])

    from rich.panel import Panel
    console.print(
        Panel(
            table,
            title=f"[bold]🧠 Memorias ({len(memories)})[/bold]",
            border_style="dim",
            padding=(0, 1),
        )
    )
