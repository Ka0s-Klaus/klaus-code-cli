"""Políticas de seguridad de Klaus: workspace, confianza en hooks y allowlist de bash.

Estado de proceso configurado una vez por sesión con :func:`configure_security`
(desde ``klaus run`` / ``klaus repl``). Los sub-agentes heredan la configuración
del padre: no la reconfiguran.

Ver ``docs/security.md`` para el modelo de amenazas.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import shlex
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from rich.console import Console
from rich.prompt import Confirm

from .compat import klaus_home

if TYPE_CHECKING:
    from .config import KlausConfig

console = Console()

OutsidePolicy = Literal["ask", "deny"]
HooksPolicy = Literal["ask", "trust", "never"]

# ── Estado de proceso ───────────────────────────────────────────────────────
_root: Path | None = None
_allowed_paths: list[Path] = []
_outside_policy: OutsidePolicy = "ask"
_granted: set[Path] = set()  # rutas exteriores aprobadas por el usuario en esta sesión

_project_hooks_policy: HooksPolicy = "ask"
_hooks_decisions: dict[str, tuple[str, bool]] = {}  # hooks_dir → (digest, trusted)
TRUST_STORE: Path = klaus_home() / "trusted_hooks.json"

_bash_allowlist: list[list[str]] = []


class WorkspaceError(PermissionError):
    """Acceso denegado a una ruta fuera del workspace."""


def configure_security(config: KlausConfig, project_root: Path) -> None:
    """Aplica la sección ``security`` de la config. Llamar una vez al iniciar la sesión."""
    global _root, _allowed_paths, _outside_policy, _project_hooks_policy, _bash_allowlist
    sec = config.security
    _root = project_root.resolve()
    _allowed_paths = [Path(p).expanduser().resolve() for p in sec.allowed_paths]
    _outside_policy = sec.outside_workspace
    _project_hooks_policy = sec.project_hooks
    _bash_allowlist = [shlex.split(entry) for entry in sec.bash_allowlist if entry.strip()]
    _granted.clear()
    _hooks_decisions.clear()


def reset_security() -> None:
    """Vuelve al estado por defecto (tests)."""
    global _root, _allowed_paths, _outside_policy, _project_hooks_policy, _bash_allowlist
    _root = None
    _allowed_paths = []
    _outside_policy = "ask"
    _project_hooks_policy = "ask"
    _bash_allowlist = []
    _granted.clear()
    _hooks_decisions.clear()


def is_interactive() -> bool:
    """True si hay un usuario delante que pueda responder a una confirmación."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def ask(question: str) -> bool:
    """Pregunta sí/no al usuario. Punto único para poder sustituirlo en tests."""
    return Confirm.ask(question, default=False, console=console)


# ── Workspace ───────────────────────────────────────────────────────────────


def workspace_roots(cwd: Path | None = None) -> list[Path]:
    """Raíz del proyecto (o ``cwd`` si no se ha configurado) + ``allowed_paths``."""
    root = _root or (cwd or Path.cwd()).resolve()
    return [root, *_allowed_paths]


def _inside(target: Path, root: Path) -> bool:
    return target == root or target.is_relative_to(root)


def is_within_workspace(target: Path, cwd: Path | None = None) -> bool:
    """Comprobación sin efectos (sin preguntar). ``target`` debe estar resuelto."""
    return any(_inside(target, r) for r in workspace_roots(cwd)) or target in _granted


def check_access(target: Path, op: str, cwd: Path | None = None) -> None:
    """Permite el acceso a ``target`` o lanza :class:`WorkspaceError`.

    Fuera del workspace: con ``outside_workspace: ask`` y un usuario delante se
    pregunta, **también en modo YOLO**. Sin TTY o con ``deny``, se rechaza.
    """
    if is_within_workspace(target, cwd):
        return

    roots = ", ".join(str(r) for r in workspace_roots(cwd))
    if _outside_policy == "ask" and is_interactive():
        console.print(
            f"[yellow]🔐 {op} quiere acceder fuera del workspace:[/yellow] [bold]{target}[/bold]\n"
            f"[dim]Workspace: {roots}[/dim]"
        )
        if ask("¿Permitir este acceso durante la sesión?"):
            _granted.add(target)
            return

    raise WorkspaceError(
        f"Acceso denegado: '{target}' está fuera del workspace ({roots}). "
        "Trabaja con rutas dentro del proyecto. Si de verdad se necesita, el usuario "
        "puede añadirla a security.allowed_paths en ~/.klaus/config.yaml."
    )


def resolve_path(path: str | None, cwd: Path | None, op: str) -> Path:
    """Resuelve ``path`` (relativo a ``cwd``, con ``~`` y symlinks) y verifica el acceso."""
    base = cwd or Path.cwd()
    p = Path(path).expanduser() if path else base
    if not p.is_absolute():
        p = base / p
    target = p.resolve()
    check_access(target, op, cwd)
    return target


F = TypeVar("F", bound=Callable[..., Awaitable[dict[str, Any]]])


def guard_workspace(func: F) -> F:
    """Convierte un :class:`WorkspaceError` del tool en un ``{"error": ...}`` para el modelo."""

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await func(*args, **kwargs)
        except WorkspaceError as e:
            return {"error": str(e)}

    return wrapper  # type: ignore[return-value]


# ── Confianza en hooks de proyecto ──────────────────────────────────────────


def _hooks_digest(hooks_dir: Path) -> tuple[str, list[str]]:
    """Hash de nombre, bit de ejecución y contenido de cada fichero del directorio."""
    h = hashlib.sha256()
    names: list[str] = []
    for f in sorted(p for p in hooks_dir.iterdir() if p.is_file()):
        names.append(f.name)
        h.update(f.name.encode())
        h.update(b"x" if os.access(f, os.X_OK) else b"-")
        h.update(hashlib.sha256(f.read_bytes()).digest())
    return h.hexdigest(), names


def _load_trust_store() -> dict[str, str]:
    try:
        data = json.loads(TRUST_STORE.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_trust_store(store: dict[str, str]) -> None:
    try:
        TRUST_STORE.parent.mkdir(parents=True, exist_ok=True)
        TRUST_STORE.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as e:
        console.print(f"[yellow]⚠️  No se pudo guardar la confianza en hooks: {e}[/yellow]")


def project_hooks_trusted(hooks_dir: Path) -> bool:
    """¿Se pueden ejecutar los hooks de proyecto de ``hooks_dir``?

    Un repo clonado puede traer ``.klaus/hooks`` ejecutables: es código de un
    tercero. Se pide confianza explícita la primera vez y cada vez que cambian
    (hash del contenido). Sin TTY no se ejecutan, salvo ``project_hooks: trust``.
    """
    if _project_hooks_policy == "never":
        return False
    if _project_hooks_policy == "trust":
        return True

    key = str(hooks_dir.resolve())
    digest, names = _hooks_digest(hooks_dir)
    cached = _hooks_decisions.get(key)
    if cached and cached[0] == digest:
        return cached[1]

    store = _load_trust_store()
    trusted = store.get(key) == digest
    if not trusted and is_interactive():
        console.print(
            f"[yellow]🪝 Este proyecto define hooks que se ejecutarán en tu máquina:[/yellow]\n"
            f"[bold]{key}[/bold]\n" + "\n".join(f"  • {n}" for n in names) + "\n"
            "[dim]Revísalos antes de confiar. Cualquier cambio en ellos volverá a preguntar.[/dim]"
        )
        trusted = ask("¿Confiar en estos hooks?")
        if trusted:
            store[key] = digest
            _save_trust_store(store)
    if not trusted:
        console.print(
            f"[yellow]⚠️  Hooks de proyecto NO ejecutados (sin confianza): {key}[/yellow]"
        )
    _hooks_decisions[key] = (digest, trusted)
    return trusted


# ── Allowlist de bash (modo no interactivo) ─────────────────────────────────

_SHELL_METACHARS = (";", "&", "|", "`", "$(", ">", "<", "\n")


def bash_allowlist_active() -> bool:
    return bool(_bash_allowlist)


def bash_allowed(command: str) -> bool:
    """True si ``command`` es una invocación simple que empieza por una entrada de la allowlist.

    Se rechaza cualquier encadenamiento, redirección o sustitución (``;``, ``&&``,
    ``|``, ``$(``, `` ` ``, ``>``…), porque permitiría colar otro comando detrás.
    """
    if any(m in command for m in _SHELL_METACHARS):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    # Saltar asignaciones iniciales VAR=valor
    while tokens and "=" in tokens[0] and not tokens[0].startswith("="):
        tokens = tokens[1:]
    return any(tokens[: len(entry)] == entry for entry in _bash_allowlist if entry)
