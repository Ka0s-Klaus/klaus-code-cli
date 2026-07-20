"""Registro central de tools disponibles para Klaus.

Expone TOOL_SCHEMAS (lista de dicts JSON Schema para function calling)
y TOOL_HANDLERS (dict nombre→función async).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .bash import run_bash
from .files import list_directory, read_file
from .git import git_commit, git_diff, git_status
from .image import read_image
from .memory import memory_read, memory_write
from .search import glob_search, grep_search
from .subagent import spawn_agent
from .todo import todo_read, todo_write
from .web import web_fetch, web_search
from .write import delete_file, edit_file, write_file

# JSON Schemas en formato Anthropic tool_use
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": (
            "Lee el contenido de un fichero. Trunca al límite configurado si el fichero "
            "es muy largo. Devuelve el contenido como texto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta al fichero (absoluta o relativa al directorio de trabajo)",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Línea desde la que empezar (1-indexed, opcional)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Línea hasta la que leer inclusive (opcional)",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_directory",
        "description": (
            "Lista el contenido de un directorio. Respeta .klausignore. "
            "Devuelve nombres de ficheros y subdirectorios."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta al directorio (por defecto: directorio de trabajo actual)",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Si listar recursivamente (por defecto: false)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "glob_search",
        "description": (
            "Busca ficheros por patrón glob (e.g. '**/*.py', 'src/*.ts'). "
            "Respeta .klausignore. Devuelve lista de rutas relativas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Patrón glob (e.g. '**/*.py')",
                },
                "base_path": {
                    "type": "string",
                    "description": "Directorio base de búsqueda (por defecto: cwd)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "grep_search",
        "description": (
            "Busca texto o expresión regular en ficheros. "
            "Devuelve lista de coincidencias con ruta, número de línea y contexto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Texto o expresión regular a buscar",
                },
                "path": {
                    "type": "string",
                    "description": "Fichero o directorio donde buscar (por defecto: cwd)",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Filtro glob para ficheros (e.g. '*.py')",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Si la búsqueda distingue mayúsculas (por defecto: false)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados a devolver (por defecto: 50)",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Crea o sobreescribe un fichero con el contenido dado. "
            "Muestra un diff/preview y pide confirmación antes de escribir. "
            "Crea directorios intermedios si no existen."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta al fichero (absoluta o relativa al cwd)",
                },
                "content": {
                    "type": "string",
                    "description": "Contenido completo a escribir en el fichero",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Edita un fichero existente reemplazando old_string por new_string. "
            "old_string debe existir y ser único (a menos que replace_all=true). "
            "Muestra un diff unificado y pide confirmación antes de aplicar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta al fichero a editar",
                },
                "old_string": {
                    "type": "string",
                    "description": "Cadena exacta a reemplazar (debe ser única en el fichero)",
                },
                "new_string": {
                    "type": "string",
                    "description": "Cadena que reemplaza a old_string",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Si reemplazar todas las ocurrencias (por defecto: false)",
                },
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "delete_file",
        "description": (
            "Elimina un fichero permanentemente. "
            "Muestra la ruta y el tamaño, y pide confirmación antes de borrar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta al fichero a eliminar",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_bash",
        "description": (
            "Ejecuta un comando shell. Muestra el comando completo y pide confirmación antes de ejecutar. "
            "Bloquea patrones peligrosos (rm -rf, curl|bash, etc.) sin posibilidad de override. "
            "Captura stdout y stderr. Aplica timeout configurable (default 30s)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Comando shell a ejecutar",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos (por defecto: 30)",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "git_status",
        "description": (
            "Muestra el estado del repositorio git: rama actual y ficheros modificados/staged/untracked. "
            "Equivalente a git status --porcelain -b. Solo lectura — sin confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "git_diff",
        "description": (
            "Muestra el diff del repositorio. "
            "staged=true para ver cambios en el index (git diff --staged). "
            "path para limitar a un fichero o directorio. Solo lectura — sin confirmación."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "Si true, muestra el diff staged (git diff --staged). Default: false.",
                },
                "path": {
                    "type": "string",
                    "description": "Ruta a un fichero o directorio para filtrar el diff (opcional)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "git_commit",
        "description": (
            "Hace git add + git commit. Muestra un resumen de los cambios y pide confirmación. "
            "paths: lista de ficheros a añadir. add_all: equivalente a git add -A. "
            "Si ni paths ni add_all se proporcionan, hace commit solo de lo ya staged."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Mensaje de commit",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de ficheros a añadir al stage antes del commit (opcional)",
                },
                "add_all": {
                    "type": "boolean",
                    "description": "Si true, hace git add -A antes del commit. Default: false.",
                },
            },
            "required": ["message"],
        },
    },
    # ── Fase 2: Web tools ─────────────────────────────────────────────────────
    {
        "name": "web_fetch",
        "description": (
            "Descarga una URL y devuelve el contenido como texto o markdown. "
            "Convierte HTML a markdown legible automáticamente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL a descargar (http/https)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos (default: 30)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Busca en la web usando DuckDuckGo. No requiere API key. "
            "Devuelve lista de resultados con título, URL y snippet."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta de búsqueda",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados (default: 10)",
                },
            },
            "required": ["query"],
        },
    },
    # ── Fase 3: Todo tools ────────────────────────────────────────────────────
    {
        "name": "todo_write",
        "description": (
            "Sobreescribe la lista de tareas de la sesión actual. "
            "Cada todo tiene 'content' (descripción) y 'status' (pending/in_progress/completed). "
            "Mostrar siempre la lista actualizada al usuario."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "Lista completa de tareas",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "Descripción de la tarea"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Estado de la tarea",
                            },
                        },
                        "required": ["content", "status"],
                    },
                },
            },
            "required": ["todos"],
        },
    },
    {
        "name": "todo_read",
        "description": "Lee la lista de tareas actual de la sesión.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    # ── Fase 5: Sub-agents ────────────────────────────────────────────────────
    {
        "name": "spawn_agent",
        "description": (
            "Lanza un sub-agente aislado para ejecutar una subtarea de forma autónoma. "
            "El sub-agente tiene su propio historial y devuelve el resultado al padre. "
            "Útil para paralelizar trabajo o delegar tareas complejas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Tarea o prompt para el sub-agente",
                },
                "model": {
                    "type": "string",
                    "description": "Override de modelo para el sub-agente (opcional)",
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Override de max_agent_turns (opcional)",
                },
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de nombres de tools disponibles (None = todas)",
                },
            },
            "required": ["prompt"],
        },
    },
    # ── Fase 6: Multimodal ────────────────────────────────────────────────────
    {
        "name": "read_image",
        "description": (
            "Lee una imagen desde disco y la codifica en base64 para incluirla en el contexto. "
            "Formatos soportados: PNG, JPEG, GIF, WEBP. "
            "Si la imagen es demasiado grande, la redimensiona automáticamente (requiere Pillow)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta a la imagen (absoluta o relativa al cwd)",
                },
                "max_size_kb": {
                    "type": "integer",
                    "description": "Tamaño máximo en KB antes de redimensionar (default: 2048)",
                },
            },
            "required": ["path"],
        },
    },
    # ── Fase 8: Memory tools ──────────────────────────────────────────────────
    {
        "name": "memory_write",
        "description": (
            "Crea o actualiza una memoria persistente en ~/.Klaus/memory/. "
            "Las memorias se inyectan en el system prompt de sesiones futuras."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Slug único de la memoria (kebab-case, e.g. 'user-preferences')",
                },
                "content": {
                    "type": "string",
                    "description": "Cuerpo de la memoria en markdown",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["user", "feedback", "project", "reference"],
                    "description": "Tipo de memoria (default: project)",
                },
                "description": {
                    "type": "string",
                    "description": "Descripción de una línea para el índice MEMORY.md",
                },
            },
            "required": ["name", "content"],
        },
    },
    {
        "name": "memory_read",
        "description": (
            "Lee memorias persistentes de ~/.Klaus/memory/. "
            "Filtra por query (búsqueda en nombre/contenido) y/o tipo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto a buscar en las memorias (vacío = todas)",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["user", "feedback", "project", "reference"],
                    "description": "Filtrar por tipo de memoria (opcional)",
                },
            },
            "required": [],
        },
    },
]

# Mapping nombre → handler async callable
TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "read_file": read_file,
    "list_directory": list_directory,
    "glob_search": glob_search,
    "grep_search": grep_search,
    "write_file": write_file,
    "edit_file": edit_file,
    "delete_file": delete_file,
    "run_bash": run_bash,
    "git_status": git_status,
    "git_diff": git_diff,
    "git_commit": git_commit,
    # Fase 2: Web tools
    "web_fetch": web_fetch,
    "web_search": web_search,
    # Fase 3: Todo tools
    "todo_write": todo_write,
    "todo_read": todo_read,
    # Fase 5: Sub-agents
    "spawn_agent": spawn_agent,
    # Fase 6: Multimodal
    "read_image": read_image,
    # Fase 8: Memory
    "memory_write": memory_write,
    "memory_read": memory_read,
}


def configure_confirmations(
    auto_approve_writes: bool = False,
    auto_approve_bash: bool = False,
) -> None:
    """Aplica los flags de modo no interactivo a los módulos de tools."""
    from . import bash, write
    write.CONFIRM_WRITES = not auto_approve_writes
    write._APPROVE_ALL = False  # reset "aprobar todo" al iniciar nueva sesión/agente
    bash.CONFIRM_BASH = not auto_approve_bash
