"""Gestión del contexto del proyecto: .klausignore, CLAUS.md y token management."""

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
    """Carga CLAUS.md/CLAUDE.md si existe y devuelve el contexto del proyecto.

    También inyecta el índice de memorias de ~/.Klaus/memory/MEMORY.md si existe.
    """
    result: dict[str, Any] = {"root": str(project_root)}

    base_context = f"Working directory: {project_root}\n\n"

    # CLAUS.md (formato Klaus) tiene prioridad; CLAUDE.md y .CLAUDE.md como fallback
    project_text = ""
    for name in ("KLAUS.md", "CLAUDE.md", ".CLAUDE.md"):
        candidate = project_root / name
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8", errors="replace")
            char_limit = max_tokens * 4
            if len(text) > char_limit:
                text = text[:char_limit] + "\n\n[TRUNCADO]"
            project_text = text
            result["system_prompt_source"] = name
            break

    # Inyectar memorias persistentes si existen
    memory_section = _load_memory_index()

    parts = [base_context]
    if project_text:
        parts.append(project_text)
    if memory_section:
        parts.append(f"\n\n---\n## 🧠 Memorias activas\n\n{memory_section}")

    result["system_prompt"] = "".join(parts).rstrip()
    return result


def _load_memory_index() -> str:
    """Carga el índice MEMORY.md de ~/.Klaus/memory/ si existe."""
    index_path = Path.home() / ".Klaus" / "memory" / "MEMORY.md"
    if not index_path.exists():
        return ""
    try:
        content = index_path.read_text(encoding="utf-8")
        # Limitar a primeras 200 líneas (igual que K* global)
        lines = content.splitlines()[:200]
        return "\n".join(lines)
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------


def _extract_text_from_content(content: Any) -> str:
    """Extrae texto de un campo content que puede ser str o list de blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                for key in ("text", "content"):
                    val = block.get(key)
                    if isinstance(val, str):
                        parts.append(val)
                    elif isinstance(val, list):
                        for sub in val:
                            if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                                parts.append(sub["text"])
        return "".join(parts)
    return ""


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estima el número de tokens en la lista de mensajes (1 token ≈ 4 caracteres)."""
    total_chars = sum(
        len(_extract_text_from_content(m.get("content", ""))) for m in messages
    )
    return max(1, total_chars // 4)


# ---------------------------------------------------------------------------
# Compactación de contexto
# ---------------------------------------------------------------------------

_COMPACTION_MARKER = (
    "[CONTEXTO COMPACTADO — mensajes intermedios omitidos para gestionar el límite de contexto]"
)


def compact_messages(
    messages: list[dict[str, Any]],
    keep_last: int = 6,
) -> tuple[list[dict[str, Any]], int]:
    """Sliding window: mantiene el primer mensaje + los últimos keep_last + marcador.

    Devuelve (mensajes_compactados, n_mensajes_eliminados).
    Si la lista ya es suficientemente corta, la devuelve intacta con dropped=0.
    """
    # Necesitamos primer + marcador + keep_last: no compactar si no hay margen
    if len(messages) <= keep_last + 1:
        return messages, 0

    first = messages[0]
    tail = messages[-keep_last:]
    dropped = len(messages) - 1 - keep_last  # excluye el primer mensaje

    marker: dict[str, Any] = {
        "role": "user",
        "content": f"{_COMPACTION_MARKER} ({dropped} mensajes omitidos)",
    }

    return [first, marker, *tail], dropped
