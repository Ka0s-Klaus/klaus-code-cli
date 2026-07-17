"""Adaptador para endpoints con formato Anthropic Messages API."""

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


class AnthropicAdapter(ProviderAdapter):
    def __init__(self, config: KlausConfig) -> None:
        self._config = config
        self._client = httpx.AsyncClient(
            base_url=config.provider.base_url,
            headers={
                "x-api-key": config.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
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
            "messages": messages,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools

        resp = await self._client.post("/messages", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def stream_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Stream tokens via SSE (Anthropic format). Fallback a send_message en error."""
        payload: dict[str, Any] = {
            "model": self._config.provider.model,
            "max_tokens": self._config.provider.max_tokens,
            "messages": messages,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools

        full_text = ""
        tool_calls: list[dict[str, Any]] = []
        input_tokens: int = 0
        output_tokens: int = 0
        stop_reason = "end_turn"

        try:
            async with self._client.stream("POST", "/messages", json=payload) as resp:
                resp.raise_for_status()
                async for raw_line in resp.aiter_lines():
                    if not raw_line.startswith("data: "):
                        continue
                    data_str = raw_line[6:].strip()
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        event = _json.loads(data_str)
                    except _json.JSONDecodeError:
                        continue

                    etype = event.get("type", "")

                    if etype == "message_start":
                        u = event.get("message", {}).get("usage", {})
                        input_tokens = int(u.get("input_tokens", 0))

                    elif etype == "content_block_start":
                        block = event.get("content_block", {})
                        if block.get("type") == "tool_use":
                            tool_calls.append({
                                "type": "tool_use",
                                "id": block.get("id", ""),
                                "name": block.get("name", ""),
                                "_input_json": "",
                                "input": {},
                            })

                    elif etype == "content_block_delta":
                        delta = event.get("delta", {})
                        dtype = delta.get("type", "")
                        if dtype == "text_delta":
                            token = delta.get("text", "")
                            if token:
                                full_text += token
                                if on_token:
                                    on_token(token)
                        elif dtype == "input_json_delta" and tool_calls:
                            tool_calls[-1]["_input_json"] += delta.get("partial_json", "")

                    elif etype == "message_delta":
                        delta = event.get("delta", {})
                        sr = delta.get("stop_reason")
                        if sr:
                            stop_reason = sr
                        u = event.get("usage", {})
                        output_tokens = int(u.get("output_tokens", output_tokens))

        except Exception:
            return await self.send_message(messages, tools, system)

        content: list[dict[str, Any]] = []
        if full_text:
            content.append({"type": "text", "text": full_text})
        for tc in tool_calls:
            partial = tc.pop("_input_json", "")
            try:
                tc["input"] = _json.loads(partial) if partial else {}
            except _json.JSONDecodeError:
                tc["input"] = {}
            content.append(tc)

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
