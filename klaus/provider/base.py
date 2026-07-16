"""Interfaz base para adaptadores de proveedor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ProviderAdapter(ABC):
    @abstractmethod
    async def send_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> dict[str, Any]:
        """Envía mensajes al proveedor y devuelve la respuesta en formato Anthropic."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Cierra el cliente HTTP."""
        ...

    def extract_text(self, response: dict[str, Any]) -> str:
        """Extrae el texto de la respuesta (normalizado desde formato Anthropic)."""
        parts = []
        for block in response.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)

    def extract_tool_calls(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        """Extrae los tool_use blocks de la respuesta."""
        return [
            b for b in response.get("content", [])
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]

    def stop_reason(self, response: dict[str, Any]) -> str:
        return response.get("stop_reason", "end_turn")

    def extract_usage(self, response: dict[str, Any]) -> dict[str, int]:
        """Devuelve los tokens consumidos según el campo usage de la respuesta."""
        usage = response.get("usage", {})
        return {
            "input_tokens": int(usage.get("input_tokens", 0)),
            "output_tokens": int(usage.get("output_tokens", 0)),
        }
