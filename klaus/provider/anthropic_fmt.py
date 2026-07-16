"""Adaptador para endpoints con formato Anthropic Messages API."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from ..config import KlausConfig
from .base import ProviderAdapter


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # Retry 429, 502, 503, 504 — never retry 4xx validation errors
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

    async def close(self) -> None:
        await self._client.aclose()
