"""Ejecución de la batería de evaluación (#71).

Cada tarea se ejecuta en un directorio temporal aislado:

    <tmp>/workspace/   copia de repo/ (git init + commit inicial) — el workspace del agente
    <tmp>/secrets/     canario fuera del workspace (api_token.txt con un valor aleatorio)
    <tmp>/home/        HOME de la ejecución: sin memorias, hooks ni comandos del usuario

El agente corre de forma desatendida: escrituras y bash auto-aprobados, acceso
fuera del workspace denegado, sin hooks de proyecto ni servidores MCP.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from ..agent import RunStats, run_agent_loop
from ..config import KlausConfig
from ..provider.base import ProviderAdapter
from .checks import BLOCKED_BASH_MARKER, OUTSIDE_MARKER, CheckResult, Sandbox, run_check
from .task import Task

AdapterFactory = Callable[[KlausConfig], ProviderAdapter]

SECRET_FILE = "secrets/api_token.txt"
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "klaus-eval",
    "GIT_AUTHOR_EMAIL": "eval@klaus.invalid",
    "GIT_COMMITTER_NAME": "klaus-eval",
    "GIT_COMMITTER_EMAIL": "eval@klaus.invalid",
}


@dataclass
class TaskResult:
    task_id: str
    category: str
    run: int
    passed: bool
    checks: list[CheckResult]
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_s: float = 0.0
    tool_calls: int = 0
    blocked_outside: int = 0
    blocked_bash: int = 0
    stop_reason: str = ""
    error: str | None = None
    workdir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerifyResult:
    task_id: str
    ok: bool
    problems: list[str] = field(default_factory=list)


# ── Sandbox ─────────────────────────────────────────────────────────────────


def _copy_overlay(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)


def make_sandbox(task: Task, with_solution: bool = False) -> Sandbox:
    root = Path(tempfile.mkdtemp(prefix=f"klaus-eval-{task.id}-")).resolve()
    workspace = root / "workspace"
    shutil.copytree(task.repo_dir, workspace)
    if with_solution:
        _copy_overlay(task.solution_dir, workspace)
        for rel in task.spec.solution_delete:
            target = workspace / rel
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()

    canary = f"KLAUS-EVAL-CANARY-{uuid.uuid4().hex}"
    secret = root / SECRET_FILE
    secret.parent.mkdir(parents=True)
    secret.write_text(canary + "\n")
    (root / "home").mkdir()

    env = {**os.environ, **_GIT_ENV}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "initial"]):
        subprocess.run(cmd, cwd=workspace, env=env, check=True, capture_output=True)

    snapshot = {SECRET_FILE: secret.read_text()}
    return Sandbox(
        root=root, workspace=workspace, secrets_dir=secret.parent, canary=canary,
        outside_snapshot=snapshot,
    )


@contextlib.contextmanager
def isolated(sandbox: Sandbox, verbose: bool = False) -> Iterator[None]:
    """HOME propio, identidad git, memorias aisladas y consolas en silencio."""
    import klaus.security as sec
    import klaus.tools.memory as memory
    from klaus.tools import write

    saved_env = {k: os.environ.get(k) for k in ("HOME", *_GIT_ENV)}
    os.environ["HOME"] = str(sandbox.root / "home")
    os.environ.update(_GIT_ENV)
    saved_memory = memory._MEMORY_DIR
    memory._MEMORY_DIR = sandbox.root / "home" / ".klaus" / "memory"
    saved_writes = (write.CONFIRM_WRITES, write._APPROVE_ALL)

    consoles: list[tuple[Console, bool]] = []
    if not verbose:
        for name, module in list(sys.modules.items()):
            if not name.startswith("klaus") or module is None:
                continue
            for value in vars(module).values():
                if isinstance(value, Console) and not any(value is c for c, _ in consoles):
                    consoles.append((value, value.quiet))
                    value.quiet = True
    try:
        yield
    finally:
        for console, quiet in consoles:
            console.quiet = quiet
        memory._MEMORY_DIR = saved_memory
        write.CONFIRM_WRITES, write._APPROVE_ALL = saved_writes
        sec.reset_security()
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def eval_config(base: KlausConfig, task: Task) -> KlausConfig:
    """Config de la ejecución: la del usuario (proveedor, modelo, proxy) + modo desatendido."""
    cfg = base.model_copy(deep=True)
    cfg.behavior.auto_approve_writes = True
    cfg.behavior.auto_approve_bash = True
    cfg.behavior.plan_mode = False
    cfg.behavior.streaming = False
    cfg.behavior.max_agent_turns = task.spec.max_turns
    cfg.security.outside_workspace = "deny"
    cfg.security.project_hooks = "never"
    cfg.security.allowed_paths = []
    cfg.security.bash_allowlist = []
    cfg.session.persist = False
    cfg.mcp_servers = []
    return cfg


# ── Ejecución ───────────────────────────────────────────────────────────────


def evaluate(task: Task, sandbox: Sandbox, answer: str, tool_calls: list[dict[str, Any]]) -> list[CheckResult]:
    """Copia los tests ocultos y ejecuta los comprobadores."""
    _copy_overlay(task.hidden_dir, sandbox.workspace)
    return [run_check(c, sandbox, answer, tool_calls) for c in task.spec.checks]


async def run_task(
    task: Task,
    base_config: KlausConfig,
    adapter_factory: AdapterFactory,
    run: int = 1,
    verbose: bool = False,
    keep: bool = False,
) -> TaskResult:
    sandbox = make_sandbox(task)
    config = eval_config(base_config, task)
    stats = RunStats()
    start = time.monotonic()
    with isolated(sandbox, verbose):
        adapter = adapter_factory(config)
        try:
            await asyncio.wait_for(
                run_agent_loop(task.spec.prompt, adapter, config, sandbox.workspace, stats=stats),
                timeout=task.spec.timeout_seconds,
            )
        except TimeoutError:
            stats.error = f"timeout ({task.spec.timeout_seconds}s)"
            stats.stop_reason = "timeout"
        except Exception as e:  # el runner nunca se cae por una tarea
            stats.error = f"{type(e).__name__}: {e}"
            stats.stop_reason = "error"
        finally:
            close = getattr(adapter, "close", None)
            if close is not None:
                with contextlib.suppress(Exception):
                    await close()
    duration = time.monotonic() - start

    checks = evaluate(task, sandbox, stats.final_text, stats.tool_calls)
    errors = [str(tc.get("error") or "") for tc in stats.tool_calls]
    result = TaskResult(
        task_id=task.id,
        category=task.spec.category,
        run=run,
        passed=stats.error is None and all(c.passed for c in checks),
        checks=checks,
        turns=stats.turns,
        input_tokens=stats.input_tokens,
        output_tokens=stats.output_tokens,
        duration_s=round(duration, 2),
        tool_calls=len(stats.tool_calls),
        blocked_outside=sum(OUTSIDE_MARKER in e for e in errors),
        blocked_bash=sum(BLOCKED_BASH_MARKER in e for e in errors),
        stop_reason=stats.stop_reason,
        error=stats.error,
        workdir=str(sandbox.root) if keep else None,
    )
    if not keep:
        shutil.rmtree(sandbox.root, ignore_errors=True)
    return result


def verify_task(task: Task) -> VerifyResult:
    """Valida la tarea sin modelo: falla con el repo original y pasa con la solución."""
    problems: list[str] = []

    original = make_sandbox(task)
    try:
        before = evaluate(task, original, answer="", tool_calls=[])
        if all(c.passed for c in before):
            problems.append("el repo original ya pasa todos los comprobadores (la tarea no mide nada)")
    finally:
        shutil.rmtree(original.root, ignore_errors=True)

    needs_solution = any(c.type not in ("answer_regex",) for c in task.spec.checks)
    has_solution = task.solution_dir.is_dir() or task.spec.solution_delete or task.spec.reference_answer
    if needs_solution and not has_solution:
        problems.append("falta solution/ (o reference_answer) para comprobar que la tarea es resoluble")

    solved = make_sandbox(task, with_solution=True)
    try:
        after = evaluate(task, solved, answer=task.spec.reference_answer, tool_calls=[])
        for c in after:
            if not c.passed:
                problems.append(f"la solución de referencia no pasa '{c.type}': {c.detail}")
    finally:
        shutil.rmtree(solved.root, ignore_errors=True)

    return VerifyResult(task.id, not problems, problems)


# ── Resumen ─────────────────────────────────────────────────────────────────


def summarize(results: list[TaskResult]) -> dict[str, Any]:
    """Métricas agregadas: global, por categoría y por tarea."""

    def agg(rs: list[TaskResult]) -> dict[str, Any]:
        n = len(rs)
        if not n:
            return {"runs": 0}
        return {
            "runs": n,
            "passed": sum(r.passed for r in rs),
            "success_rate": round(sum(r.passed for r in rs) / n, 3),
            "avg_turns": round(sum(r.turns for r in rs) / n, 1),
            "avg_input_tokens": round(sum(r.input_tokens for r in rs) / n),
            "avg_output_tokens": round(sum(r.output_tokens for r in rs) / n),
            "avg_duration_s": round(sum(r.duration_s for r in rs) / n, 1),
            "blocked_outside": sum(r.blocked_outside for r in rs),
            "blocked_bash": sum(r.blocked_bash for r in rs),
            "errors": sum(r.error is not None for r in rs),
        }

    by_cat: dict[str, list[TaskResult]] = {}
    by_task: dict[str, list[TaskResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
        by_task.setdefault(r.task_id, []).append(r)
    return {
        "overall": agg(results),
        "by_category": {k: agg(v) for k, v in sorted(by_cat.items())},
        "by_task": {k: agg(v) for k, v in sorted(by_task.items())},
    }
