"""Tests para OpenAIAdapter — conversión de schemas, mensajes y tool calling."""

from __future__ import annotations

import json

import pytest

from klaus.provider.openai_fmt import (
    _from_openai_response,
    _to_openai_messages,
    _to_openai_tools,
)


# ---------------------------------------------------------------------------
# _to_openai_tools
# ---------------------------------------------------------------------------

ANTHROPIC_TOOLS = [
    {
        "name": "read_file",
        "description": "Lee un fichero",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Ruta al fichero"},
                "start_line": {"type": "integer"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "run_bash",
        "description": "Ejecuta un comando",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
]


def test_to_openai_tools_structure():
    result = _to_openai_tools(ANTHROPIC_TOOLS)
    assert len(result) == 2
    for item in result:
        assert item["type"] == "function"
        assert "function" in item
        fn = item["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn


def test_to_openai_tools_schema_mapping():
    result = _to_openai_tools(ANTHROPIC_TOOLS)
    fn = result[0]["function"]
    assert fn["name"] == "read_file"
    assert fn["description"] == "Lee un fichero"
    assert fn["parameters"]["properties"]["path"]["type"] == "string"
    assert fn["parameters"]["required"] == ["path"]


def test_to_openai_tools_empty():
    assert _to_openai_tools([]) == []


def test_to_openai_tools_missing_input_schema():
    tools = [{"name": "no_schema", "description": "Sin schema"}]
    result = _to_openai_tools(tools)
    assert result[0]["function"]["parameters"] == {"type": "object", "properties": {}}


# ---------------------------------------------------------------------------
# _to_openai_messages — mensajes de texto plano
# ---------------------------------------------------------------------------


def test_to_openai_messages_text_only():
    messages = [{"role": "user", "content": "Hola"}]
    result = _to_openai_messages(messages, system=None)
    assert result == [{"role": "user", "content": "Hola"}]


def test_to_openai_messages_with_system():
    messages = [{"role": "user", "content": "Hola"}]
    result = _to_openai_messages(messages, system="Eres Klaus")
    assert result[0] == {"role": "system", "content": "Eres Klaus"}
    assert result[1] == {"role": "user", "content": "Hola"}


def test_to_openai_messages_list_text_blocks():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Primera"},
                {"type": "text", "text": "Segunda"},
            ],
        }
    ]
    result = _to_openai_messages(messages, system=None)
    assert result[0]["content"] == "Primera Segunda"


# ---------------------------------------------------------------------------
# _to_openai_messages — assistant con tool_use blocks
# ---------------------------------------------------------------------------


def test_to_openai_messages_assistant_tool_use():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Voy a leer el fichero"},
                {
                    "type": "tool_use",
                    "id": "tu_001",
                    "name": "read_file",
                    "input": {"path": "/tmp/test.py"},
                },
            ],
        }
    ]
    result = _to_openai_messages(messages, system=None)
    assert len(result) == 1
    msg = result[0]
    assert msg["role"] == "assistant"
    assert msg["content"] == "Voy a leer el fichero"
    assert len(msg["tool_calls"]) == 1
    tc = msg["tool_calls"][0]
    assert tc["id"] == "tu_001"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "read_file"
    args = json.loads(tc["function"]["arguments"])
    assert args == {"path": "/tmp/test.py"}


def test_to_openai_messages_assistant_tool_use_no_text():
    messages = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tu_002",
                    "name": "run_bash",
                    "input": {"command": "ls"},
                }
            ],
        }
    ]
    result = _to_openai_messages(messages, system=None)
    msg = result[0]
    assert "content" not in msg
    assert msg["tool_calls"][0]["function"]["name"] == "run_bash"


# ---------------------------------------------------------------------------
# _to_openai_messages — user con tool_result blocks
# ---------------------------------------------------------------------------


def test_to_openai_messages_tool_results():
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_001",
                    "content": '{"path": "/tmp/test.py", "content": "print(1)"}',
                },
                {
                    "type": "tool_result",
                    "tool_use_id": "tu_002",
                    "content": '{"stdout": "archivo.txt"}',
                },
            ],
        }
    ]
    result = _to_openai_messages(messages, system=None)
    # Cada tool_result → mensaje "tool" independiente
    assert len(result) == 2
    assert result[0]["role"] == "tool"
    assert result[0]["tool_call_id"] == "tu_001"
    assert result[1]["role"] == "tool"
    assert result[1]["tool_call_id"] == "tu_002"


# ---------------------------------------------------------------------------
# _from_openai_response — normalización de respuesta
# ---------------------------------------------------------------------------


def test_from_openai_response_text():
    raw = {
        "id": "chatcmpl-123",
        "choices": [
            {
                "message": {"role": "assistant", "content": "Hola, soy Klaus"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    result = _from_openai_response(raw)
    assert result["stop_reason"] == "end_turn"
    assert result["content"][0] == {"type": "text", "text": "Hola, soy Klaus"}
    assert result["usage"]["input_tokens"] == 10
    assert result["usage"]["output_tokens"] == 5


def test_from_openai_response_tool_calls():
    raw = {
        "id": "chatcmpl-456",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_abc",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "/home/user/foo.py"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 15},
    }
    result = _from_openai_response(raw)
    assert result["stop_reason"] == "tool_use"
    tool_block = result["content"][0]
    assert tool_block["type"] == "tool_use"
    assert tool_block["id"] == "call_abc"
    assert tool_block["name"] == "read_file"
    assert tool_block["input"] == {"path": "/home/user/foo.py"}


def test_from_openai_response_max_tokens():
    raw = {
        "choices": [{"message": {"content": "truncado"}, "finish_reason": "length"}],
        "usage": {},
    }
    result = _from_openai_response(raw)
    assert result["stop_reason"] == "max_tokens"


# ---------------------------------------------------------------------------
# Integración: round-trip de un turno completo con tools
# ---------------------------------------------------------------------------


def test_full_turn_round_trip():
    """Verifica que el flujo completo messages→payload→response se mantiene coherente."""
    # 1. El agente envía el primer mensaje de usuario
    messages = [{"role": "user", "content": "Lee el archivo /tmp/test.py"}]
    oai_msgs = _to_openai_messages(messages, system="Eres Klaus")
    assert oai_msgs[0]["role"] == "system"
    assert oai_msgs[1]["role"] == "user"

    # 2. El modelo responde con una tool call (simulado)
    oai_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_xyz",
                            "function": {
                                "name": "read_file",
                                "arguments": '{"path": "/tmp/test.py"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 30},
    }
    normalized = _from_openai_response(oai_response)
    assert normalized["stop_reason"] == "tool_use"

    # 3. El agente construye el mensaje de tool result y lo añade al historial
    messages.append({"role": "assistant", "content": normalized["content"]})
    messages.append({
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "call_xyz", "content": "print(42)"}
        ],
    })

    # 4. Convertir el historial completo a formato OpenAI
    final_msgs = _to_openai_messages(messages, system="Eres Klaus")
    # system + user + assistant(tool_call) + tool(result)
    assert len(final_msgs) == 4
    assert final_msgs[0]["role"] == "system"
    assert final_msgs[1]["role"] == "user"
    assert final_msgs[2]["role"] == "assistant"
    assert "tool_calls" in final_msgs[2]
    assert final_msgs[3]["role"] == "tool"
    assert final_msgs[3]["tool_call_id"] == "call_xyz"
    assert final_msgs[3]["content"] == "print(42)"
