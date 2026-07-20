"""Carga y validación de configuración desde ~/.Klaus/config.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

CONFIG_PATH = Path.home() / ".Klaus" / "config.yaml"


class ProviderConfig(BaseModel):
    # URL base del proxy klaude. Sobreescribible con KLAUDE_PROXY_URL.
    base_url: str = "http://localhost:8080/v1"
    api_key_env: str = "KLAUDE_API_KEY"
    api_format: str = "anthropic"  # "anthropic" | "openai"
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 4096
    temperature: float = 0.2


class BehaviorConfig(BaseModel):
    auto_approve_reads: bool = True
    auto_approve_writes: bool = False
    auto_approve_bash: bool = False
    max_agent_turns: int = 25
    plan_mode: bool = False
    streaming: bool = True


class SessionConfig(BaseModel):
    storage_path: str = "~/.Klaus/sessions/"
    persist: bool = True
    lock_enabled: bool = True


class ContextConfig(BaseModel):
    max_context_tokens: int = 100_000
    auto_compact: bool = True
    max_file_read_lines: int = 2000
    max_Klaus_md_tokens: int = 4000


class NetworkConfig(BaseModel):
    max_retries: int = 3
    backoff_base_seconds: float = 1.5
    timeout_seconds: int = 600


class MCPServerConfig(BaseModel):
    """Configuración de un servidor MCP externo."""

    name: str
    command: list[str]
    env: dict[str, str] = Field(default_factory=dict)


class KlausConfig(BaseModel):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)

    @property
    def api_key(self) -> str | None:
        val = os.getenv(self.provider.api_key_env)
        return val or None


def load_config(
    base_url_override: str | None = None,
    model_override: str | None = None,
) -> KlausConfig:
    """Load config from ~/.Klaus/config.yaml with env var and CLI overrides."""
    raw: dict[str, Any] = {}

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}

    # Env var overrides — KLAUDE_PROXY_URL tiene precedencia sobre config.yaml
    if val := os.getenv("KLAUDE_PROXY_URL"):
        raw.setdefault("provider", {})["base_url"] = val
    if val := os.getenv("KLAUDE_MODEL"):
        raw.setdefault("provider", {})["model"] = val
    if val := os.getenv("KLAUDE_API_FORMAT"):
        raw.setdefault("provider", {})["api_format"] = val

    # CLI overrides (highest priority)
    if base_url_override:
        raw.setdefault("provider", {})["base_url"] = base_url_override
    if model_override:
        raw.setdefault("provider", {})["model"] = model_override

    return KlausConfig(**raw)


DEFAULT_CONFIG_YAML = """provider:
  # URL base de klaude-proxy (incluye /v1).
  # Sobreescribible sin tocar este fichero: export KLAUDE_PROXY_URL="http://<host>:8080/v1"
  base_url: "http://localhost:8080/v1"
  # Nombre de la variable de entorno que contiene la API key enviada al proxy.
  # Sobreescribible: export KLAUDE_API_KEY="sk-ant-..."
  api_key_env: "KLAUDE_API_KEY"
  api_format: "anthropic"
  model: "claude-haiku-4-5-20251001"
  max_tokens: 4096
  temperature: 0.2

behavior:
  auto_approve_reads: true
  auto_approve_writes: false
  auto_approve_bash: false
  max_agent_turns: 25
  plan_mode: false
  streaming: true

session:
  storage_path: "~/.Klaus/sessions/"
  persist: true
  lock_enabled: true

context:
  max_context_tokens: 100000
  auto_compact: true
  max_file_read_lines: 2000
  max_Klaus_md_tokens: 4000

network:
  max_retries: 3
  backoff_base_seconds: 1.5
  timeout_seconds: 120

# mcp_servers:
#   - name: filesystem
#     command: ["uvx", "mcp-server-filesystem", "/home/user/projects"]
#   - name: github
#     command: ["uvx", "mcp-server-github"]
#     env:
#       GITHUB_TOKEN: "${GITHUB_TOKEN}"
"""
