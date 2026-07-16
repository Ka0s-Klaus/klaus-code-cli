"""Tools de ficheros: read_file y list_directory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..context import KlausIgnore

# Límite de líneas por defecto cuando no hay config disponible
_DEFAULT_MAX_LINES = 2000


def _resolve(path: str, cwd: Path | None = None) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (cwd or Path.cwd()) / p
    return p.resolve()


async def read_file(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    max_lines: int = _DEFAULT_MAX_LINES,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Lee un fichero con soporte de rango y truncado."""
    target = _resolve(path, cwd)

    if not target.exists():
        return {"error": f"Fichero no encontrado: {path}"}
    if not target.is_file():
        return {"error": f"No es un fichero: {path}"}
    if target.stat().st_size > 10 * 1024 * 1024:  # 10 MB
        return {"error": f"Fichero demasiado grande (>10 MB): {path}"}

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except PermissionError:
        return {"error": f"Sin permiso de lectura: {path}"}

    lines = text.splitlines(keepends=True)
    total = len(lines)

    start = max(0, (start_line - 1) if start_line else 0)
    end = min(total, end_line if end_line else total)

    # Aplicar límite de líneas (siempre, incluso si se pasa rango explícito)
    if (end - start) > max_lines:
        end = start + max_lines
        truncated = True
    else:
        truncated = False

    content = "".join(lines[start:end])

    result: dict[str, Any] = {
        "path": str(target),
        "content": content,
        "total_lines": total,
        "lines_read": end - start,
    }
    if truncated:
        result["truncated"] = True
        result["truncated_at_line"] = end
        result["hint"] = (
            f"Fichero truncado en línea {end} de {total}. "
            f"Usa start_line={end + 1} para continuar."
        )
    return result


async def list_directory(
    path: str = ".",
    recursive: bool = False,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Lista el contenido de un directorio respetando .klausignore."""
    target = _resolve(path, cwd)

    if not target.exists():
        return {"error": f"Directorio no encontrado: {path}"}
    if not target.is_dir():
        return {"error": f"No es un directorio: {path}"}

    ignore = KlausIgnore(target)

    entries: list[dict[str, str]] = []

    if recursive:
        for root, dirs, files in os.walk(target):
            root_path = Path(root)
            # Filtrar dirs ignorados (modifica dirs in-place para que os.walk no entre)
            dirs[:] = [
                d for d in sorted(dirs)
                if not ignore.is_ignored(root_path / d)
            ]
            for f in sorted(files):
                fp = root_path / f
                if not ignore.is_ignored(fp):
                    rel = fp.relative_to(target)
                    entries.append({"type": "file", "path": str(rel)})
    else:
        for item in sorted(target.iterdir()):
            if ignore.is_ignored(item):
                continue
            entries.append({
                "type": "dir" if item.is_dir() else "file",
                "name": item.name,
            })

    return {
        "path": str(target),
        "entries": entries,
        "count": len(entries),
    }
