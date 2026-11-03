"""Configuración dinámica del pseudonymizer en Klaus-proxy-global.

Detecta valores sensibles (rutas, username) y los registra en el proxy
para que se seudonimicen antes de llegar a modelos externos.

Punto de entrada único: :func:`ensure_pseudonymizer`. Debe esperarse (``await``)
**antes** de la primera petición al modelo en cada camino que hable con el
proveedor (``klaus run``, ``klaus repl``, ``/model`` y ``spawn_agent``).

Principio de diseño: ante la duda, configurar. Seudonimizar de más es inocuo;
saltarse la configuración con un modelo externo filtra datos.
"""

from __future__ import annotations

import asyncio
import fnmatch
import getpass
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import httpx
from rich.console import Console

if TYPE_CHECKING:
    from .config import KlausConfig

log = logging.getLogger("klaus.pseudonymizer_config")
_console = Console(stderr=True)

# Literales ya registrados con éxito en cada endpoint durante este proceso.
# Evita repetir el POST en cada sub-agente o cambio de modelo.
_configured: set[tuple[str, tuple[str, ...]]] = set()


# APIs públicas de proveedores. Si base_url apunta a una de ellas, no hay proxy
# delante: no se seudonimiza nada y NO se deben enviar los literales (serían
# justo los datos que queremos proteger, entregados al tercero).
DIRECT_PROVIDER_HOSTS: tuple[str, ...] = (
    "api.anthropic.com",
    "api.openai.com",
    "generativelanguage.googleapis.com",
    "api.mistral.ai",
    "api.groq.com",
    "api.deepseek.com",
    "openrouter.ai",
    ".openai.azure.com",
)


class PseudonymizerError(RuntimeError):
    """La configuración del pseudonymizer falló y ``pseudonymizer.required`` está activo."""


def is_local_model(model: str | None, local_models: list[str]) -> bool:
    """True si ``model`` coincide (glob, sin distinguir mayúsculas) con algún patrón local.

    Solo cuenta como local lo que se declara explícitamente. No se infiere nada
    de la forma del nombre: ``openai/gpt-4o`` o ``anthropic/claude-*`` (formato
    LiteLLM) son modelos externos aunque contengan ``/``.
    """
    if not model:
        return False
    name = model.lower()
    return any(fnmatch.fnmatchcase(name, pattern.lower()) for pattern in local_models)


def is_direct_provider(base_url: str) -> bool:
    """True si ``base_url`` es la API pública de un proveedor (sin klaude-proxy delante)."""
    host = (urlparse(base_url).hostname or "").lower()
    return any(
        host.endswith(h) if h.startswith(".") else host == h for h in DIRECT_PROVIDER_HOSTS
    )


def collect_sensitive_literals(project_root: Path | None) -> list[str]:
    """Ruta del proyecto, home y username, sin duplicados y en ese orden."""
    literals: list[str] = []

    def _add(value: str | None) -> None:
        if value and value not in literals:
            literals.append(value)

    if project_root:
        try:
            _add(str(project_root.resolve()))
        except Exception as e:
            log.debug("PSEUDONYMIZER_CONFIG: error reading project_root: %s", e)
    try:
        _add(str(Path.home().resolve()))
    except Exception as e:
        log.debug("PSEUDONYMIZER_CONFIG: error reading home: %s", e)
    try:
        _add(getpass.getuser())
    except Exception as e:
        log.debug("PSEUDONYMIZER_CONFIG: error reading username: %s", e)

    return literals


def config_endpoint(base_url: str) -> str:
    """``http://host:8080/v1`` → ``http://host:8080/pseudonymizer/config``."""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return f"{root}/pseudonymizer/config"


async def configure_pseudonymizer(
    base_url: str,
    literals: list[str],
    timeout_seconds: float = 2.0,
) -> bool:
    """Registra ``literals`` en el proxy. Devuelve True si el proxy confirmó (2xx).

    Nunca lanza excepciones: los fallos se registran como warning. La duración
    total está acotada por ``timeout_seconds``, aunque el proxy acepte la conexión
    y no responda (el motivo del antiguo fire-and-forget, ver b1a9e63).
    """
    if not base_url or not literals:
        return False

    endpoint = config_endpoint(base_url)
    payload: dict[str, Any] = {"literals": literals}
    log.debug("PSEUDONYMIZER_CONFIG: POST %s (%d literals)", endpoint, len(literals))
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await asyncio.wait_for(
                client.post(endpoint, json=payload), timeout=timeout_seconds
            )
            resp.raise_for_status()
            try:
                result = resp.json()
            except ValueError:
                result = {}
            log.info(
                "PSEUDONYMIZER_CONFIG: configured literals=%s paths=%s",
                result.get("literals", "?"),
                result.get("paths", "?"),
            )
            return True
    except (TimeoutError, httpx.TimeoutException) as e:
        log.warning("PSEUDONYMIZER_CONFIG: timeout (%ss) en %s: %s", timeout_seconds, endpoint, e)
    except httpx.ConnectError as e:
        log.warning("PSEUDONYMIZER_CONFIG: sin conexión con %s (¿proxy parado?): %s", endpoint, e)
    except httpx.HTTPError as e:
        log.warning("PSEUDONYMIZER_CONFIG: error HTTP de %s: %s", endpoint, e)
    except Exception as e:
        log.warning("PSEUDONYMIZER_CONFIG: error inesperado: %s", e)
    return False


async def ensure_pseudonymizer(config: KlausConfig, project_root: Path | None) -> bool:
    """Garantiza que el proxy seudonimiza los datos sensibles para el modelo activo.

    Devuelve True si se puede continuar con garantías: configurado ahora, ya
    configurado antes en este proceso, o modelo declarado local. Devuelve False
    si falló y ``required`` es False (se continúa, con un warning).

    Raises:
        PseudonymizerError: si falló y ``config.pseudonymizer.required`` es True.
    """
    pc = config.pseudonymizer
    model = config.provider.model

    if not pc.enabled:
        log.debug("PSEUDONYMIZER_CONFIG: deshabilitado por configuración")
        return False

    if is_local_model(model, pc.local_models):
        log.debug("PSEUDONYMIZER_CONFIG: modelo local '%s', no se configura", model)
        return True

    if is_direct_provider(config.provider.base_url):
        # Nunca enviar los literales a un tercero.
        message = (
            f"base_url ({config.provider.base_url}) apunta directamente a un proveedor, "
            f"sin klaude-proxy: el contenido se envía al modelo '{model}' sin seudonimizar."
        )
    else:
        literals = collect_sensitive_literals(project_root)
        key = (config_endpoint(config.provider.base_url), tuple(literals))
        if key in _configured:
            return True

        ok = await configure_pseudonymizer(config.provider.base_url, literals, pc.timeout_seconds)
        if ok:
            _configured.add(key)
            return True

        message = (
            f"No se pudo configurar el pseudonymizer en {key[0]} para el modelo externo "
            f"'{model}'. Rutas y username podrían enviarse sin seudonimizar."
        )
    if pc.required:
        raise PseudonymizerError(message + " Abortando (pseudonymizer.required: true).")
    log.warning("PSEUDONYMIZER_CONFIG: %s", message)
    _console.print(f"[yellow]⚠️  {message}[/yellow]")
    return False
