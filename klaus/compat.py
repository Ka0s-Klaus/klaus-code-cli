"""Nombres canónicos de Klaus y compatibilidad con los anteriores (#58).

Convención (ver CONTRIBUTING.md):
  - Directorio de usuario:  ``~/.klaus/``            (antes ``~/.Klaus/``)
  - Directorio de proyecto: ``<proyecto>/.klaus/``   (antes ``<proyecto>/.Klaus/``)
  - Variables de entorno:   ``KLAUS_*``              (antes ``KLAUDE_*``)

Los nombres anteriores siguen funcionando con un aviso de obsolescencia, una
vez por proceso. Nunca se mueven datos del usuario automáticamente.

Nota: en sistemas de ficheros que no distinguen mayúsculas (macOS por defecto),
``~/.Klaus`` y ``~/.klaus`` son el mismo directorio y no hay nada que migrar.
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console

DIRNAME = ".klaus"
LEGACY_DIRNAME = ".Klaus"
ENV_PREFIX = "KLAUS_"
LEGACY_ENV_PREFIX = "KLAUDE_"

_console = Console(stderr=True)
_warned: set[str] = set()


def warn_once(key: str, message: str) -> None:
    """Muestra un aviso de obsolescencia una sola vez por proceso."""
    if key in _warned:
        return
    _warned.add(key)
    # soft_wrap: sin cortes de línea, para que el comando `mv` se pueda copiar entero
    _console.print(f"[yellow]⚠️  {message}[/yellow]", soft_wrap=True)


def _resolve_dir(parent: Path) -> tuple[Path, bool]:
    """(directorio a usar, es_legacy). Prefiere ``.klaus``; usa ``.Klaus`` solo si es el único."""
    new = parent / DIRNAME
    legacy = parent / LEGACY_DIRNAME
    if new.exists() or not legacy.exists():
        return new, False
    return legacy, True


def klaus_home() -> Path:
    """Directorio de usuario de Klaus (``~/.klaus``, o ``~/.Klaus`` heredado)."""
    return _resolve_dir(Path.home())[0]


def project_klaus_dir(project_root: Path) -> Path:
    """Directorio de Klaus dentro del proyecto (``.klaus``, o ``.Klaus`` heredado)."""
    return _resolve_dir(project_root)[0]


def expand_user_path(path: str) -> Path:
    """``expanduser`` que redirige ``~/.klaus/...`` al directorio heredado si es el único."""
    p = Path.home() / path[2:] if path.startswith("~/") else Path(path).expanduser()
    canonical = Path.home() / DIRNAME
    if p == canonical or p.is_relative_to(canonical):
        return klaus_home() / p.relative_to(canonical)
    return p


def warn_legacy_dirs(project_root: Path | None = None) -> None:
    """Avisa (una vez) si se están usando directorios con el nombre anterior."""
    parents = [Path.home()] + ([project_root] if project_root else [])
    for parent in parents:
        used, legacy = _resolve_dir(parent)
        if legacy:
            target = parent / DIRNAME
            warn_once(
                f"dir:{used}",
                f"'{used}' usa el nombre anterior. Renómbralo: mv '{used}' '{target}'",
            )


def getenv(name: str) -> str | None:
    """Lee ``KLAUS_<name>``; si no está, ``KLAUDE_<name>`` con aviso de obsolescencia."""
    value = os.getenv(f"{ENV_PREFIX}{name}")
    if value:
        return value
    legacy = os.getenv(f"{LEGACY_ENV_PREFIX}{name}")
    if legacy:
        warn_once(
            f"env:{name}",
            f"{LEGACY_ENV_PREFIX}{name} está obsoleta; usa {ENV_PREFIX}{name}.",
        )
        return legacy
    return None
