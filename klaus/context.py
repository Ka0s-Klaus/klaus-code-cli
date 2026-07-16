"""Gestión del contexto del proyecto: .klausignore y KLAUS.md."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

# Patrones ignorados por defecto (ampliables por .klausignore)
_DEFAULT_IGNORE: list[str] = [
    ".git",
    ".venv",
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    ".DS_Store",
    "dist",
    "build",
    "*.egg-info",
]


class KlausIgnore:
    """Carga y aplica reglas de .klausignore más patrones por defecto."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._patterns: list[str] = list(_DEFAULT_IGNORE)
        ignore_file = root / ".klausignore"
        if ignore_file.exists():
            for line in ignore_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    self._patterns.append(line)

    def is_ignored(self, path: Path) -> bool:
        name = path.name
        try:
            rel = str(path.relative_to(self._root))
        except ValueError:
            rel = name

        for pat in self._patterns:
            if fnmatch.fnmatch(name, pat):
                return True
            if fnmatch.fnmatch(rel, pat):
                return True
            # Soporte de prefijo de directorio (e.g. "dist/")
            if pat.endswith("/") and (name == pat[:-1] or rel.startswith(pat)):
                return True
        return False


def load_project_context(project_root: Path, max_tokens: int = 4000) -> dict[str, Any]:
    """Carga KLAUS.md si existe y devuelve el contexto del proyecto."""
    result: dict[str, Any] = {"root": str(project_root)}

    for name in ("KLAUS.md", "CLAUDE.md", ".CLAUDE.md"):
        candidate = project_root / name
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            # Truncar al límite de tokens estimado (aprox. 4 chars/token)
            char_limit = max_tokens * 4
            if len(text) > char_limit:
                text = text[:char_limit] + "\n\n[TRUNCADO]"
            result["system_prompt"] = text
            result["system_prompt_source"] = name
            break

    return result
