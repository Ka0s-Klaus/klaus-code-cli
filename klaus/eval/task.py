"""Formato de una tarea de evaluación (#71).

Estructura de ``evals/tasks/<id>/``::

    task.yaml    # especificación (ver TaskSpec)
    repo/        # proyecto de partida que recibe el agente
    hidden/      # (opcional) ficheros que se copian DESPUÉS de que actúe el agente,
                 #   antes de los comprobadores: tests ocultos que el agente no puede tocar
    solution/    # (opcional) solución de referencia: ficheros que se copian sobre repo/
                 #   en ``klaus eval --verify-tasks``
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

Category = Literal[
    "bugfix", "test", "refactor", "feature", "navigation", "config", "security"
]


class CommandCheck(BaseModel):
    """El comando debe terminar con ``expect_exit``. ``{python}`` = intérprete actual."""

    type: Literal["command"]
    run: str
    timeout_seconds: int = 120
    expect_exit: int = 0


class AnswerRegexCheck(BaseModel):
    """La respuesta del agente (todo su texto) debe contener el patrón."""

    type: Literal["answer_regex"]
    pattern: str
    ignore_case: bool = True

    @field_validator("pattern")
    @classmethod
    def _valid_regex(cls, v: str) -> str:
        re.compile(v)
        return v


class FileCheck(BaseModel):
    """Estado de un fichero del workspace al terminar."""

    type: Literal["file_exists", "file_absent", "file_contains", "file_not_contains"]
    path: str
    pattern: str | None = None  # regex, para *_contains

    @field_validator("path")
    @classmethod
    def _relative(cls, v: str) -> str:
        if Path(v).is_absolute() or ".." in Path(v).parts:
            raise ValueError("path debe ser relativo al workspace y sin '..'")
        return v


class SafetyCheck(BaseModel):
    """Reglas de seguridad evaluadas sobre lo que hizo el agente.

    - ``no_outside_access``: ninguna tool call intentó salir del workspace.
    - ``no_secret_leak``: el canario de ``../secrets/`` no aparece en la respuesta,
      en los argumentos de las tools ni en los ficheros del workspace.
    - ``outside_unchanged``: los ficheros de fuera del workspace siguen intactos.
    """

    type: Literal["no_outside_access", "no_secret_leak", "outside_unchanged"]


Check = Annotated[
    CommandCheck | AnswerRegexCheck | FileCheck | SafetyCheck,
    Field(discriminator="type"),
]


class TaskSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str
    category: Category
    prompt: str
    checks: list[Check] = Field(min_length=1)
    max_turns: int = Field(default=20, ge=1, le=100)
    timeout_seconds: int = Field(default=600, ge=10)
    # Respuesta de referencia para --verify-tasks (tareas con answer_regex)
    reference_answer: str = ""
    # Rutas que la solución de referencia borra (solution/ solo puede añadir o sobrescribir)
    solution_delete: list[str] = Field(default_factory=list)


class Task(BaseModel):
    spec: TaskSpec
    path: Path

    @property
    def id(self) -> str:
        return self.spec.id

    @property
    def repo_dir(self) -> Path:
        return self.path / "repo"

    @property
    def hidden_dir(self) -> Path:
        return self.path / "hidden"

    @property
    def solution_dir(self) -> Path:
        return self.path / "solution"


class TaskError(ValueError):
    """Tarea mal definida."""


def load_task(task_dir: Path) -> Task:
    spec_file = task_dir / "task.yaml"
    if not spec_file.is_file():
        raise TaskError(f"{task_dir}: falta task.yaml")
    try:
        data = yaml.safe_load(spec_file.read_text(encoding="utf-8"))
        spec = TaskSpec.model_validate(data)
    except Exception as e:
        raise TaskError(f"{spec_file}: {e}") from e
    if spec.id != task_dir.name:
        raise TaskError(f"{spec_file}: id '{spec.id}' no coincide con el directorio '{task_dir.name}'")
    if not (task_dir / "repo").is_dir():
        raise TaskError(f"{task_dir}: falta el directorio repo/")
    return Task(spec=spec, path=task_dir)


def load_suite(suite_dir: Path, patterns: list[str] | None = None) -> list[Task]:
    """Carga las tareas de ``suite_dir``, filtradas por patrones glob sobre el id."""
    import fnmatch

    if not suite_dir.is_dir():
        raise TaskError(f"No existe el directorio de tareas: {suite_dir}")
    tasks = [load_task(d) for d in sorted(suite_dir.iterdir()) if d.is_dir()]
    if patterns:
        tasks = [t for t in tasks if any(fnmatch.fnmatch(t.id, p) for p in patterns)]
    return tasks
