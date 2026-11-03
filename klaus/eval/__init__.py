"""Batería de evaluación de Klaus (#71). Ver docs/evaluation.md."""

from .runner import TaskResult, VerifyResult, run_task, summarize, verify_task
from .task import Task, TaskError, TaskSpec, load_suite, load_task

__all__ = [
    "Task",
    "TaskError",
    "TaskResult",
    "TaskSpec",
    "VerifyResult",
    "load_suite",
    "load_task",
    "run_task",
    "summarize",
    "verify_task",
]
