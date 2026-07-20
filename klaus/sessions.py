"""Persistencia de sesiones REPL — SessionManager y SessionLock.

SessionManager: guarda/carga el historial de mensajes en disco.
SessionLock: impide que dos instancias del REPL operen sobre el mismo proyecto.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def _session_dir(storage_path: str) -> Path:
    path = Path(storage_path).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_id(project_root: Path, session_name: str | None = None) -> str:
    if session_name:
        return session_name
    return hashlib.sha1(str(project_root.resolve()).encode()).hexdigest()[:16]


class SessionManager:
    """Guarda y carga el historial de mensajes REPL en disco."""

    def __init__(
        self,
        storage_path: str,
        project_root: Path,
        session_name: str | None = None,
    ) -> None:
        self._dir = _session_dir(storage_path)
        self._sid = _session_id(project_root, session_name)
        self._path = self._dir / f"{self._sid}.json"

    @property
    def session_id(self) -> str:
        return self._sid

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> list[dict[str, Any]]:
        """Carga el historial desde disco. Devuelve [] si no existe o está corrupto."""
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def save(self, messages: list[dict[str, Any]]) -> None:
        """Escribe el historial atomicamente (temp file + os.rename)."""
        fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
            os.chmod(tmp_path, 0o600)
            os.rename(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def clear(self) -> None:
        """Elimina el fichero de sesión."""
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            pass


class SessionLock:
    """Context manager que impide dos instancias del REPL en el mismo proyecto.

    Usa un fichero lock que contiene el PID del proceso propietario.
    Detecta y libera locks huérfanos (proceso ya terminado).
    """

    def __init__(
        self,
        storage_path: str,
        project_root: Path,
        session_name: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._dir = _session_dir(storage_path)
        self._sid = _session_id(project_root, session_name)
        self._path = self._dir / f"{self._sid}.lock"
        self._enabled = enabled

    def _is_alive(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # proceso existe pero no es nuestro

    def acquire(self) -> bool:
        """Intenta adquirir el lock. Devuelve True si tiene éxito, False si hay conflicto."""
        if not self._enabled:
            return True
        if self._path.exists():
            try:
                existing_pid = int(self._path.read_text().strip())
                if self._is_alive(existing_pid):
                    console.print(
                        f"[red]⚠️  Ya hay una instancia de Klaus REPL activa en este "
                        f"proyecto (PID {existing_pid}).[/red]\n"
                        "[dim]Cierra la otra sesión o usa [cyan]--session NOMBRE[/cyan] "
                        "para abrir una sesión paralela con nombre distinto.[/dim]"
                    )
                    return False
                # Lock huérfano — proceso ya no existe
                console.print(
                    f"[dim]🔓 Lock huérfano liberado (PID {existing_pid} ya no existe)[/dim]"
                )
            except (ValueError, OSError):
                pass
        try:
            self._path.write_text(str(os.getpid()), encoding="utf-8")
            os.chmod(self._path, 0o600)
        except OSError as e:
            console.print(f"[yellow]⚠️  No se pudo crear el lock de sesión: {e}[/yellow]")
        return True

    def release(self) -> None:
        """Libera el lock si pertenece a este proceso."""
        if not self._enabled:
            return
        try:
            if self._path.exists():
                content = self._path.read_text().strip()
                if content == str(os.getpid()):
                    self._path.unlink(missing_ok=True)
        except OSError:
            pass

    def __enter__(self) -> SessionLock:
        return self

    def __exit__(self, *_: Any) -> None:
        self.release()


def list_sessions(storage_path: str) -> list[dict[str, Any]]:
    """Devuelve lista de sesiones guardadas con metadatos."""
    session_dir = _session_dir(storage_path)
    sessions = []
    for p in sorted(session_dir.glob("*.json")):
        try:
            stat = p.stat()
            data = json.loads(p.read_text(encoding="utf-8"))
            msg_count = len(data) if isinstance(data, list) else 0
            sessions.append({
                "session_id": p.stem,
                "path": str(p),
                "messages": msg_count,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": stat.st_mtime,
            })
        except (OSError, json.JSONDecodeError):
            pass
    return sessions


def get_session(storage_path: str, session_id: str) -> list[dict[str, Any]] | None:
    """Carga el historial de una sesión por su ID. Devuelve None si no existe o está corrupto."""
    session_dir = _session_dir(storage_path)
    path = session_dir / f"{session_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else None
    except (json.JSONDecodeError, OSError):
        return None


def delete_session(storage_path: str, session_id: str) -> bool:
    """Elimina una sesión por su ID. Devuelve True si se eliminó, False si no existía."""
    session_dir = _session_dir(storage_path)
    path = session_dir / f"{session_id}.json"
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def clear_all_sessions(storage_path: str) -> int:
    """Elimina todas las sesiones guardadas. Devuelve el número de sesiones eliminadas."""
    session_dir = _session_dir(storage_path)
    count = 0
    for p in session_dir.glob("*.json"):
        try:
            p.unlink()
            count += 1
        except OSError:
            pass
    return count


# ─── Checkpoints ─────────────────────────────────────────────────────────────


def save_checkpoint(
    storage_path: str,
    session_id: str,
    messages: list[dict[str, Any]],
    name: str | None = None,
) -> dict[str, Any]:
    """Guarda un checkpoint nombrado del estado actual de la conversación.

    Returns:
        Dict con checkpoint_id, path y metadata.
    """
    import time

    session_dir = _session_dir(storage_path)
    ts = int(time.time())
    checkpoint_id = f"{session_id}-ckpt-{ts}"
    if name:
        safe_name = name.replace(" ", "_").replace("/", "-")[:32]
        checkpoint_id = f"{session_id}-ckpt-{ts}-{safe_name}"

    cp_path = session_dir / f"{checkpoint_id}.json"
    payload: dict[str, Any] = {
        "checkpoint_id": checkpoint_id,
        "session_id": session_id,
        "name": name or checkpoint_id,
        "timestamp": ts,
        "messages": messages,
    }

    fd, tmp_path = tempfile.mkstemp(dir=session_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.chmod(tmp_path, 0o600)
        os.rename(tmp_path, cp_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return {
        "checkpoint_id": checkpoint_id,
        "path": str(cp_path),
        "messages": len(messages),
        "name": name or checkpoint_id,
    }


def list_checkpoints(storage_path: str, session_id: str) -> list[dict[str, Any]]:
    """Lista todos los checkpoints de una sesión."""
    from datetime import datetime

    session_dir = _session_dir(storage_path)
    checkpoints = []
    pattern = f"{session_id}-ckpt-*.json"

    for p in sorted(session_dir.glob(pattern)):
        try:
            stat = p.stat()
            data = json.loads(p.read_text(encoding="utf-8"))
            checkpoints.append({
                "checkpoint_id": data.get("checkpoint_id", p.stem),
                "name": data.get("name", p.stem),
                "messages": len(data.get("messages", [])),
                "timestamp": data.get("timestamp", stat.st_mtime),
                "modified": stat.st_mtime,
                "size_kb": round(stat.st_size / 1024, 1),
            })
        except (OSError, json.JSONDecodeError):
            pass

    return checkpoints


def load_checkpoint(storage_path: str, checkpoint_id: str) -> list[dict[str, Any]] | None:
    """Carga las messages de un checkpoint. Devuelve None si no existe."""
    session_dir = _session_dir(storage_path)
    cp_path = session_dir / f"{checkpoint_id}.json"
    if not cp_path.exists():
        return None
    try:
        data = json.loads(cp_path.read_text(encoding="utf-8"))
        return data.get("messages", [])
    except (json.JSONDecodeError, OSError):
        return None
