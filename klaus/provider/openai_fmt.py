"""Adaptador para endpoints con formato OpenAI Chat Completions API.

Traduce internamente a/desde el formato Anthropic para que el resto del CLI
no dependa del formato del proveedor.
"""

from __future__ import annotations

import json as _json
from collections.abc import Callable
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import KlausConfig
from .base import ProviderAdapter


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 502, 503, 504)
    return isinstance(exc, httpx.NetworkError)


def _to_openai_messages(
    messages: list[dict[str, Any]],
    system: str | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role = m["role"]
        content = m["content"]
        if isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
            out.append({"role": role, "content": text})
        else:
            out.append({"role": role, "content": content})
    return out


def _from_openai_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Normaliza respuesta OpenAI al formato Anthropic que usa el CLI internamente."""
    choice = raw.get("choices", [{}])[0]
    msg = choice.get("message", {})
    text = msg.get("content") or ""
    finish = choice.get("finish_reason", "stop")

    stop_reason = "end_turn"
    if finish == "tool_calls":
        stop_reason = "tool_use"
    elif finish == "length":
        stop_reason = "max_tokens"

    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})

    for tc in msg.get("tool_calls", []) or []:
        try:
            args = _json.loads(tc.get("function", {}).get("arguments", "{}"))
        except Exception:
            args = {}
        content.append({
            "type": "tool_use",
            "id": tc.get("id", ""),
            "name": tc.get("function", {}).get("name", ""),
            "input": args,
        })

    usage = raw.get("usage", {})
    return {
        "id": raw.get("id", ""),
        "type": "message",
        "role": "assistant",
        "content": content,
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


class OpenAIAdapter(ProviderAdapter):
    def __init__(self, config: KlausConfig) -> None:
        self._config = config
        _headers: dict[str, str] = {"content-type": "application/json"}
        if config.api_key:
            _headers["Authorization"] = f"Bearer {config.api_key}"
        self._client = httpx.AsyncClient(
            base_url=config.provider.base_url,
            headers=_headers,
            timeout=config.network.timeout_seconds,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=1, max=30),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    async def send_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._config.provider.model,
            "max_tokens": self._config.provider.max_tokens,
            "messages": _to_openai_messages(messages, system),
        }
        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        return _from_openai_response(resp.json())

    async def stream_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Stream tokens via SSE (OpenAI format). Fallback a send_message en error."""
        payload: dict[str, Any] = {
            "model": self._config.provider.model,
            "max_tokens": self._config.provider.max_tokens,
            "messages": _to_openai_messages(messages, system),
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        full_text = ""
        tool_calls_raw: dict[int, dict[str, str]] = {}
        finish_reason = "stop"
        input_tokens: int = 0
        output_tokens: int = 0

        try:
            async with self._client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line.startswith("data: "):
                        continue
                    data_str = raw_line[6:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        chunk = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue

                    # Usage en el chunk final (stream_options)
                    if chunk.get("usage"):
                        u = chunk["usage"]
                        input_tokens = int(u.get("prompt_tokens", 0))
                        output_tokens = int(u.get("completion_tokens", 0))

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta", {})

                    token = delta.get("content") or ""
                    if token:
                        full_text += token
                        if on_token:
                            on_token(token)

                    for tc_delta in delta.get("tool_calls", []) or []:
                        idx = tc_delta.get("index", 0)
                        fn = tc_delta.get("function", {})
                        if idx not in tool_calls_raw:
                            tool_calls_raw[idx] = {
                                "id": tc_delta.get("id", ""),
                                "name": fn.get("name", ""),
                                "arguments": fn.get("arguments", ""),
                            }
                        else:
                            if tc_delta.get("id"):
                                tool_calls_raw[idx]["id"] = tc_delta["id"]
                            if fn.get("name"):
                                tool_calls_raw[idx]["name"] = fn["name"]
                            tool_calls_raw[idx]["arguments"] += fn.get("arguments", "")

                    fr = choice.get("finish_reason")
                    if fr:
                        finish_reason = fr

        except Exception:
            return await self.send_message(messages, tools, system)

        stop_reason = "end_turn"
        if finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif finish_reason == "length":
            stop_reason = "max_tokens"

        content: list[dict[str, Any]] = []
        if full_text:
            content.append({"type": "text", "text": full_text})
        for idx in sorted(tool_calls_raw):
            tc = tool_calls_raw[idx]
            try:
                args = _json.loads(tc["arguments"]) if tc["arguments"] else {}
            except _json.JSONDecodeError:
                args = {}
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": args,
            })

        return {
            "type": "message",
            "role": "assistant",
            "content": content,
            "stop_reason": stop_reason,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
        }

    async def close(self) -> None:
        await self._client.aclose()
