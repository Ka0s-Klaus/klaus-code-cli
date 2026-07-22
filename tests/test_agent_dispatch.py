"""Tests para _dispatch_tool — validación de parámetros requeridos.

Cubre el bug GH-49: cuando el modelo llama una tool con args vacíos,
_dispatch_tool debe devolver un error accionable en lugar de propagar
una excepción Python críptica que provoca bucles hasta max_agent_turns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from klaus.agent import _dispatch_tool


@pytest.mark.asyncio
async def test_dispatch_read_file_missing_path(tmp_path: Path):
    """read_file({}) → error descriptivo, no TypeError."""
    tool_call = {"name": "read_file", "id": "test-id", "input": {}}
    result = await _dispatch_tool(tool_call, config=None, cwd=tmp_path)  # type: ignore[arg-type]
    assert "error" in result
    assert "path" in result["error"]
    assert "read_file" in result["error"]


@pytest.mark.asyncio
async def test_dispatch_read_file_with_path(tmp_path: Path):
    """read_file con path válido → no error de validación."""
    f = tmp_path / "hello.txt"
    f.write_text("hola mundo")
    tool_call = {"name": "read_file", "id": "test-id", "input": {"path": str(f)}}
    result = await _dispatch_tool(tool_call, config=None, cwd=tmp_path)  # type: ignore[arg-type]
    assert "error" not in result
    assert "content" in result


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(tmp_path: Path):
    """Tool desconocida → error sin crash."""
    tool_call = {"name": "herramienta_inexistente", "id": "test-id", "input": {}}
    result = await _dispatch_tool(tool_call, config=None, cwd=tmp_path)  # type: ignore[arg-type]
    assert "error" in result
    assert "desconocida" in result["error"]


@pytest.mark.asyncio
async def test_dispatch_error_message_is_actionable(tmp_path: Path):
    """El mensaje de error incluye ejemplo de uso correcto."""
    tool_call = {"name": "read_file", "id": "test-id", "input": {}}
    result = await _dispatch_tool(tool_call, config=None, cwd=tmp_path)  # type: ignore[arg-type]
    # El modelo debe poder leer el error y saber cómo corregir la llamada
    assert "Llama la herramienta con:" in result["error"]
    assert "path=" in result["error"]
