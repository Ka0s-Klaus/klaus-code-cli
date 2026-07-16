"""MCPRegistry: gestiona conexiones a servidores MCP externos vía stdio.

Lifecycle via AsyncExitStack — llama a startup() al arrancar el agente
y shutdown() al salir (en bloque finally).
"""

from __future__ import annotations

import contextlib
import os
from typing import Any, Callable

from rich.console import Console

console = Console()


class MCPRegistry:
    """Gestiona servidores MCP: conexión, discovery de tools y dispatch."""

    def __init__(self) -> None:
        self._exit_stack: contextlib.AsyncExitStack = contextlib.AsyncExitStack()
        self._sessions: dict[str, Any] = {}
        self.schemas: list[dict[str, Any]] = []
        self.handlers: dict[str, Callable[..., Any]] = {}

    async def startup(self, servers: list[Any]) -> None:
        """Conecta a cada servidor MCP, descubre sus tools y registra handlers."""
        if not servers:
            return

        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            console.print(
                "[yellow]⚠️  Paquete 'mcp' no instalado — servidores MCP ignorados. "
                "Instala con: pip install mcp[/yellow]"
            )
            return

        await self._exit_stack.__aenter__()

        for server in servers:
            try:
                env: dict[str, str] | None = None
                if server.env:
                    env = {**os.environ, **{k: os.path.expandvars(v) for k, v in server.env.items()}}

                params = StdioServerParameters(
                    command=server.command[0],
                    args=server.command[1:],
                    env=env,
                )
                read, write = await self._exit_stack.enter_async_context(stdio_client(params))
                session: ClientSession = await self._exit_stack.enter_async_context(
                    ClientSession(read, write)
                )
                await session.initialize()
                self._sessions[server.name] = session

                tools_result = await session.list_tools()
                count = 0
                for tool in tools_result.tools:
                    schema_name = f"mcp_{server.name}_{tool.name}"
                    self.schemas.append({
                        "name": schema_name,
                        "description": (
                            f"[MCP:{server.name}] {tool.description or tool.name}"
                        ),
                        "input_schema": tool.inputSchema or {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    })
                    self.handlers[schema_name] = self._make_handler(server.name, tool.name)
                    count += 1

                console.print(
                    f"[green]✓ MCP '{server.name}' conectado — {count} tools disponibles[/green]"
                )

            except Exception as exc:
                console.print(
                    f"[yellow]⚠️  MCP '{server.name}' no disponible: {exc}[/yellow]"
                )

    def _make_handler(self, server_name: str, tool_name: str) -> Callable[..., Any]:
        """Devuelve un handler async que proxea la llamada al servidor MCP."""

        async def handler(**kwargs: Any) -> dict[str, Any]:
            # cwd no es un concepto MCP — excluirlo antes de pasar argumentos
            kwargs.pop("cwd", None)

            session = self._sessions.get(server_name)
            if not session:
                return {"error": f"MCP server '{server_name}' no disponible"}

            try:
                result = await session.call_tool(tool_name, arguments=kwargs)
                parts: list[str] = []
                for chunk in result.content:
                    if hasattr(chunk, "text"):
                        parts.append(chunk.text)
                    elif hasattr(chunk, "data"):
                        parts.append(f"[binary: {len(chunk.data)} bytes]")
                return {"result": "\n".join(parts)}
            except Exception as exc:
                return {"error": f"Error en {server_name}/{tool_name}: {exc}"}

        return handler

    async def shutdown(self) -> None:
        """Cierra todas las sesiones MCP."""
        try:
            await self._exit_stack.__aexit__(None, None, None)
        except Exception:
            pass
