"""Registro central de tools disponibles para Klaus.

Expone TOOL_SCHEMAS (lista de dicts JSON Schema para function calling)
y TOOL_HANDLERS (dict nombre→función async).
"""

from __future__ import annotations

from typing import Any, Callable

from .bash import run_bash
from .files import list_directory, read_file
from .git import git_commit, git_diff, git_status
from .search import glob_search, grep_search
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
}
