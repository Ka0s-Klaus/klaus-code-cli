"""Tests para klaus.mcp.client — compatibilidad de schemas entre versiones del SDK mcp."""

from __future__ import annotations

from types import SimpleNamespace

from klaus.mcp.client import _tool_input_schema

SCHEMA = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}


def test_input_schema_mcp_v2_attribute():
    """mcp >= 2.x expone `input_schema` (regresión #54: AttributeError con inputSchema)."""
    tool = SimpleNamespace(name="t", input_schema=SCHEMA)
    assert _tool_input_schema(tool) == SCHEMA


def test_input_schema_mcp_v1_attribute():
    """mcp 1.x expone `inputSchema`."""
    tool = SimpleNamespace(name="t", inputSchema=SCHEMA)
    assert _tool_input_schema(tool) == SCHEMA


def test_input_schema_missing_returns_none():
    assert _tool_input_schema(SimpleNamespace(name="t")) is None


def test_input_schema_real_sdk_tool():
    """Con el SDK instalado, el Tool real debe resolverse sin errores."""
    import mcp.types as mt

    field = "input_schema" if "input_schema" in mt.Tool.model_fields else "inputSchema"
    tool = mt.Tool(name="t", **{field: SCHEMA})
    assert _tool_input_schema(tool) == SCHEMA
