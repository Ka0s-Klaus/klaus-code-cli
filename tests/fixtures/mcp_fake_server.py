"""Servidor MCP mínimo para tests de integración (#61).

Expone una tool de solo lectura y otra con efectos (escribe en el fichero
indicado por la variable de entorno FAKE_MCP_LOG).
"""

from __future__ import annotations

import os
from pathlib import Path

import mcp.types as types
from mcp.server.mcpserver import MCPServer

server = MCPServer("fake")


@server.tool(annotations=types.ToolAnnotations(read_only_hint=True))
def lookup(key: str) -> str:
    """Devuelve un valor (solo lectura)."""
    return f"valor-de-{key}"


@server.tool(annotations=types.ToolAnnotations(read_only_hint=False, destructive_hint=True))
def write_record(text: str) -> str:
    """Escribe un registro (efecto secundario)."""
    with Path(os.environ["FAKE_MCP_LOG"]).open("a") as f:
        f.write(text + "\n")
    return "ok"


if __name__ == "__main__":
    server.run("stdio")
