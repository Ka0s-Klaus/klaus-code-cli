"""Tools de búsqueda: glob_search y grep_search."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..context import KlausIgnore
from ..security import guard_workspace, is_within_workspace, resolve_path


def _resolve(path: str | None, cwd: Path | None, op: str) -> Path:
    """Resuelve la ruta (por defecto cwd) y verifica que está dentro del workspace (#56)."""
    return resolve_path(path, cwd, op)


def _safe(p: Path, cwd: Path | None) -> bool:
    """Descarta resultados fuera del workspace: patrones con '..' o symlinks hacia fuera."""
    try:
        return is_within_workspace(p.resolve(), cwd)
    except OSError:
        return False


@guard_workspace
async def glob_search(
    pattern: str,
    base_path: str | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Busca ficheros por patrón glob, respetando .klausignore."""
    base = _resolve(base_path, cwd, "glob_search")

    if not base.exists():
        return {"error": f"Directorio base no encontrado: {base_path}"}

    ignore = KlausIgnore(base)
    matches: list[str] = []

    for p in sorted(base.glob(pattern)):
        if not ignore.is_ignored(p) and _safe(p, cwd):
            try:
                rel = p.relative_to(base)
                matches.append(str(rel))
            except ValueError:
                matches.append(str(p))

    return {
        "pattern": pattern,
        "base": str(base),
        "matches": matches,
        "count": len(matches),
    }


@guard_workspace
async def grep_search(
    pattern: str,
    path: str | None = None,
    file_pattern: str | None = None,
    case_sensitive: bool = False,
    max_results: int = 50,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Busca texto o regex en ficheros. Devuelve matches con contexto."""
    base = _resolve(path, cwd, "grep_search")
    flags = 0 if case_sensitive else re.IGNORECASE

    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return {"error": f"Expresión regular inválida: {e}"}

    ignore = KlausIgnore(base if base.is_dir() else base.parent)

    # Recopilar ficheros donde buscar
    if base.is_file():
        files: list[Path] = [base]
    else:
        glob_pat = file_pattern or "**/*"
        files = [
            p for p in sorted(base.glob(glob_pat))
            if p.is_file() and not ignore.is_ignored(p) and _safe(p, cwd)
        ]

    results: list[dict[str, Any]] = []

    for fp in files:
        if len(results) >= max_results:
            break
        # Saltar binarios (heurística: presencia de null bytes)
        try:
            raw = fp.read_bytes()
            if b"\x00" in raw[:512]:
                continue
            text = raw.decode("utf-8", errors="replace")
        except PermissionError:
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            if len(results) >= max_results:
                break
            if regex.search(line):
                try:
                    rel = str(fp.relative_to(base if base.is_dir() else base.parent))
                except ValueError:
                    rel = str(fp)
                results.append({
                    "file": rel,
                    "line": lineno,
                    "content": line.rstrip(),
                })

    return {
        "pattern": pattern,
        "results": results,
        "count": len(results),
        "truncated": len(results) >= max_results,
    }
