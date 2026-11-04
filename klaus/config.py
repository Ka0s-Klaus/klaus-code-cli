"""Carga y validación de configuración desde ~/.klaus/config.yaml."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import AliasChoices, BaseModel, Field, ValidationError, model_validator

from .compat import getenv, klaus_home, warn_once

CONFIG_PATH = klaus_home() / "config.yaml"


class ProviderConfig(BaseModel):
    # URL base de klaude-proxy. Sobreescribible con KLAUS_PROXY_URL.
    base_url: str = "http://localhost:8080/v1"
    api_key_env: str = "KLAUS_API_KEY"
    api_format: str = "anthropic"  # "anthropic" | "openai"
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 4096
    temperature: float = 0.2


class BehaviorConfig(BaseModel):
    auto_approve_reads: bool = True
    auto_approve_writes: bool = False
    auto_approve_bash: bool = False
    max_agent_turns: int = 25
    max_agent_depth: int = 3
    plan_mode: bool = False
    streaming: bool = True


class SessionConfig(BaseModel):
    storage_path: str = "~/.klaus/sessions/"
    persist: bool = True
    lock_enabled: bool = True


class ContextConfig(BaseModel):
    max_context_tokens: int = 100_000
    auto_compact: bool = True
    max_file_read_lines: int = 2000
    # Tokens máximos de KLAUS.md inyectados en el system prompt.
    # Acepta la clave anterior `max_Klaus_md_tokens` (obsoleta, #58).
    max_klaus_md_tokens: int = Field(
        default=4000,
        validation_alias=AliasChoices("max_klaus_md_tokens", "max_Klaus_md_tokens"),
    )

    @model_validator(mode="before")
    @classmethod
    def _warn_legacy_keys(cls, data: Any) -> Any:
        if isinstance(data, dict) and "max_Klaus_md_tokens" in data:
            warn_once(
                "cfg:max_Klaus_md_tokens",
                "context.max_Klaus_md_tokens está obsoleta; usa context.max_klaus_md_tokens.",
            )
        return data


class NetworkConfig(BaseModel):
    max_retries: int = 3
    backoff_base_seconds: float = 1.5
    timeout_seconds: int = 600


class PseudonymizerConfig(BaseModel):
    """Registro de datos sensibles en el pseudonymizer de klaude-proxy."""

    enabled: bool = True
    # Si True y la configuración falla con un modelo externo, Klaus aborta en vez de continuar.
    required: bool = False
    # Patrones glob (sin distinguir mayúsculas) de modelos servidos en local.
    # Solo estos se excluyen; cualquier otro modelo se trata como externo.
    local_models: list[str] = Field(
        default_factory=lambda: ["kdev*", "ollama/*", "ollama_chat/*"]
    )
    timeout_seconds: float = 2.0


class SecurityConfig(BaseModel):
    """Límites del agente. Ver docs/security.md."""

    # Directorios extra (además del proyecto) a los que las tools de ficheros pueden acceder.
    allowed_paths: list[str] = Field(default_factory=list)
    # Acceso fuera del workspace: "ask" pregunta (también en YOLO; sin TTY se deniega), "deny" siempre deniega.
    outside_workspace: Literal["ask", "deny"] = "ask"
    # Hooks en <proyecto>/.klaus/hooks: "ask" pide confianza (por hash), "trust" siempre, "never" nunca.
    project_hooks: Literal["ask", "trust", "never"] = "ask"
    # Si no está vacía y run_bash está auto-aprobado, solo estos prefijos se ejecutan sin preguntar.
    bash_allowlist: list[str] = Field(default_factory=list)


class MCPServerConfig(BaseModel):
    """Configuración de un servidor MCP externo."""

    name: str
    command: list[str]
    env: dict[str, str] = Field(default_factory=dict)
    # Confirmación de sus tools (#61):
    #   "auto"   → pregunta salvo tools de solo lectura o escrituras auto-aprobadas (--allow-writes/--yolo)
    #   "always" → pregunta siempre, también en --yolo (sin TTY se deniega)
    #   "never"  → nunca pregunta (servidor de plena confianza)
    confirm: Literal["auto", "always", "never"] = "auto"
    # En "auto", confiar en annotations.readOnlyHint que declara el propio servidor.
    trust_read_only: bool = True


class KlausConfig(BaseModel):
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    behavior: BehaviorConfig = Field(default_factory=BehaviorConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    pseudonymizer: PseudonymizerConfig = Field(default_factory=PseudonymizerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)

    @property
    def api_key(self) -> str | None:
        val = os.getenv(self.provider.api_key_env)
        if not val and self.provider.api_key_env == "KLAUS_API_KEY":
            val = getenv("API_KEY")  # acepta KLAUDE_API_KEY (obsoleta) con aviso
        return val or None


class MCPConfigError(ValueError):
    """Fichero de --mcp-config inexistente o con formato inválido."""


def load_mcp_config_file(path: str | Path) -> list[MCPServerConfig]:
    """Lee servidores MCP de un fichero JSON o YAML (#70).

    Formatos aceptados:
      - lista de servidores con el formato de ``mcp_servers``;
      - ``{"mcp_servers": [...]}``;
      - ``{"mcpServers": {"<nombre>": {"command": "...", "args": [...], "env": {...}}}}``,
        el formato habitual de otros clientes MCP.

    Los servidores remotos (``url`` sin ``command``) no se admiten: se omiten con aviso.
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise MCPConfigError(f"--mcp-config: no existe el fichero '{p}'")
    text = p.read_text(encoding="utf-8")
    try:
        data = json.loads(text) if p.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        raise MCPConfigError(f"--mcp-config: '{p}' no es JSON/YAML válido: {e}") from e

    entries: list[dict[str, Any]]
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict) and isinstance(data.get("mcp_servers"), list):
        entries = data["mcp_servers"]
    elif isinstance(data, dict) and isinstance(data.get("mcpServers"), dict):
        entries = []
        for name, spec in data["mcpServers"].items():
            if not isinstance(spec, dict):
                raise MCPConfigError(f"--mcp-config: servidor '{name}' mal formado en '{p}'")
            if "command" not in spec:
                warn_once(
                    f"mcp-remote:{p}:{name}",
                    f"--mcp-config: servidor '{name}' omitido (solo se admiten servidores stdio "
                    "con 'command').",
                )
                continue
            command = spec["command"]
            cmd = list(command) if isinstance(command, list) else [str(command)]
            cmd += [str(a) for a in spec.get("args", [])]
            entry = {k: v for k, v in spec.items() if k not in ("command", "args", "type")}
            entries.append({"name": name, "command": cmd, **entry})
    else:
        raise MCPConfigError(
            f"--mcp-config: formato no reconocido en '{p}'. Usa una lista de servidores, "
            "'mcp_servers: [...]' o 'mcpServers: {...}'."
        )

    try:
        return [MCPServerConfig.model_validate(e) for e in entries]
    except ValidationError as e:
        raise MCPConfigError(f"--mcp-config: servidor inválido en '{p}': {e}") from e


def merge_mcp_servers(
    base: list[MCPServerConfig], extra: list[MCPServerConfig]
) -> list[MCPServerConfig]:
    """Une servidores; a igualdad de nombre gana ``extra`` (la CLI sobre config.yaml)."""
    merged = {s.name: s for s in base}
    for s in extra:
        merged[s.name] = s
    return list(merged.values())


def load_config(
    base_url_override: str | None = None,
    model_override: str | None = None,
    mcp_config_files: list[str] | None = None,
) -> KlausConfig:
    """Carga ~/.klaus/config.yaml y aplica variables de entorno y overrides de CLI.

    Prioridad: CLI > KLAUS_* (o KLAUDE_*, obsoletas) > config.yaml > defaults.
    """
    raw: dict[str, Any] = {}

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}

    # Variables de entorno — tienen precedencia sobre config.yaml
    if val := getenv("PROXY_URL"):
        raw.setdefault("provider", {})["base_url"] = val
    if val := getenv("MODEL"):
        raw.setdefault("provider", {})["model"] = val
    if val := getenv("API_FORMAT"):
        raw.setdefault("provider", {})["api_format"] = val

    # CLI overrides (highest priority)
    if base_url_override:
        raw.setdefault("provider", {})["base_url"] = base_url_override
    if model_override:
        raw.setdefault("provider", {})["model"] = model_override

    config = KlausConfig(**raw)
    for path in mcp_config_files or []:
        config.mcp_servers = merge_mcp_servers(config.mcp_servers, load_mcp_config_file(path))
    return config


DEFAULT_CONFIG_YAML = """provider:
  # URL base de klaude-proxy (incluye /v1).
  # Sobreescribible sin tocar este fichero: export KLAUS_PROXY_URL="http://<host>:8080/v1"
  base_url: "http://localhost:8080/v1"
  # Nombre de la variable de entorno que contiene la API key enviada al proxy.
  # Sobreescribible: export KLAUS_API_KEY="sk-ant-..."
  api_key_env: "KLAUS_API_KEY"
  api_format: "anthropic"
  model: "claude-haiku-4-5-20251001"
  max_tokens: 4096
  temperature: 0.2

behavior:
  auto_approve_reads: true
  auto_approve_writes: false
  auto_approve_bash: false
  max_agent_turns: 25
  max_agent_depth: 3
  plan_mode: false
  streaming: true

session:
  storage_path: "~/.klaus/sessions/"
  persist: true
  lock_enabled: true

context:
  max_context_tokens: 100000
  auto_compact: true
  max_file_read_lines: 2000
  max_klaus_md_tokens: 4000

network:
  max_retries: 3
  backoff_base_seconds: 1.5
  timeout_seconds: 600

pseudonymizer:
  # Registra ruta del proyecto, home y username en klaude-proxy para seudonimizarlos.
  enabled: true
  # true → si el registro falla con un modelo externo, Klaus aborta (recomendado con cliente).
  required: false
  # Solo estos modelos (glob) se consideran locales; el resto se trata como externo.
  local_models: ["kdev*", "ollama/*", "ollama_chat/*"]
  timeout_seconds: 2.0

security:
  # Directorios extra (además del proyecto) accesibles por las tools de ficheros.
  allowed_paths: []
  # Fuera del workspace: "ask" (pregunta incluso en --yolo; sin TTY deniega) | "deny".
  outside_workspace: "ask"
  # Hooks de <proyecto>/.klaus/hooks: "ask" (confianza por hash) | "trust" | "never".
  project_hooks: "ask"
  # Con run_bash auto-aprobado, solo estos prefijos corren sin preguntar (vacío = sin filtro).
  # Ej.: ["pytest", "ruff check", "git status", "git diff"]
  bash_allowlist: []

# mcp_servers:
#   - name: filesystem
#     command: ["uvx", "mcp-server-filesystem", "/home/user/projects"]
#     confirm: "auto"          # auto | always | never (ver docs/mcp.md)
#     trust_read_only: true    # en "auto", no preguntar en tools con readOnlyHint
#   - name: github
#     command: ["uvx", "mcp-server-github"]
#     env:
#       GITHUB_TOKEN: "${GITHUB_TOKEN}"
"""


# ── Perfiles de `klaus init` (#77) ───────────────────────────────────────────
# Cada perfil es una lista de sustituciones exactas sobre DEFAULT_CONFIG_YAML, para
# conservar sus comentarios. Reflejan docs/security.md#️-configuración-recomendada-por-entorno.

_OUTSIDE_DENY = (
    '  outside_workspace: "ask"\n',
    '  outside_workspace: "deny"\n',
)

CONFIG_PROFILES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "dev": ("Desarrollo local (valores por defecto)", []),
    "cliente": (
        "Equipo de un cliente / datos sensibles (sin --yolo)",
        [
            _OUTSIDE_DENY,
            ('  project_hooks: "ask"\n', '  project_hooks: "never"   # o "ask", revisando cada hook\n'),
            ("  required: false\n", "  required: true\n"),
            (
                '#     confirm: "auto"          # auto | always | never (ver docs/mcp.md)\n',
                '#     confirm: "always"        # toda tool MCP pasa por una persona\n',
            ),
        ],
    ),
    "ci": (
        "CI / automatización con --yolo",
        [
            _OUTSIDE_DENY,
            ('  project_hooks: "ask"\n', '  project_hooks: "trust"   # solo si el repo es tuyo\n'),
            (
                "  bash_allowlist: []\n",
                '  bash_allowlist: ["pytest", "ruff check", "mypy", "git status", "git diff"]\n',
            ),
            (
                '#     confirm: "auto"          # auto | always | never (ver docs/mcp.md)\n',
                '#     confirm: "always"        # con --yolo, en servidores con efectos\n',
            ),
        ],
    ),
}


def config_yaml_for_profile(profile: str) -> str:
    """YAML de `klaus init --profile <profile>`, con los comentarios del fichero por defecto."""
    if profile not in CONFIG_PROFILES:
        raise ValueError(f"perfil desconocido: {profile!r} (válidos: {', '.join(CONFIG_PROFILES)})")
    description, replacements = CONFIG_PROFILES[profile]
    text = DEFAULT_CONFIG_YAML
    for old, new in replacements:
        if text.count(old) != 1:
            raise RuntimeError(f"perfil {profile!r}: {old.strip()!r} no aparece una sola vez en el YAML")
        text = text.replace(old, new)
    return f"# Perfil: {profile} — {description}. Ver docs/security.md\n" + text
