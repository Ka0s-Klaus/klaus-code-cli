"""Configuración dinámica del pseudonymizer en Klaus-proxy-global.

Detecta valores sensibles (rutas, username) y los registra en el proxy
para que se seudonimicen automáticamente.
"""

from __future__ import annotations

import getpass
import logging
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("klaus.pseudonymizer_config")


async def configure_pseudonymizer(
    base_url: str,
    model: str | None = None,
    project_root: Path | None = None,
) -> None:
    """Detectar valores sensibles y registrarlos en el pseudonymizer del proxy.

    Argumentos:
      base_url: URL del proxy (e.g., "http://localhost:8080/v1")
      model: Modelo a usar (e.g., "kdev:latest", "claude-3-5-sonnet")
      project_root: Raíz del proyecto actual
    """
    if not base_url:
        log.debug("PSEUDONYMIZER_CONFIG: base_url vacío, skip")
        return

    # Skip si modelo es local (Ollama, archivo local, etc.)
    if model:
        is_local = any(marker in model.lower() for marker in ["kdev", "ollama", "localhost", "/"])
        if is_local:
            log.debug("PSEUDONYMIZER_CONFIG: modelo local '%s', skipping configuration", model)
            return

    # Calcular URL del pseudonymizer (remover /v1 si está)
    proxy_url = base_url.rsplit("/v1", 1)[0] if base_url.endswith("/v1") else base_url
    config_endpoint = f"{proxy_url}/pseudonymizer/config"

    # Detectar valores sensibles
    literals: list[str] = []

    # 1. Ruta del proyecto
    if project_root:
        try:
            proj_path = str(project_root.resolve())
            if proj_path:
                literals.append(proj_path)
        except Exception as e:
            log.debug("PSEUDONYMIZER_CONFIG: error reading project_root: %s", e)

    # 2. Home directory
    try:
        home = str(Path.home().resolve())
        if home and home not in literals:
            literals.append(home)
    except Exception as e:
        log.debug("PSEUDONYMIZER_CONFIG: error reading home: %s", e)

    # 3. Username
    try:
        user = getpass.getuser()
        if user and user not in literals:
            literals.append(user)
    except Exception as e:
        log.debug("PSEUDONYMIZER_CONFIG: error reading username: %s", e)

    if not literals:
        log.debug("PSEUDONYMIZER_CONFIG: no sensitive values detected")
        return

    # Enviar configuración al proxy (crear cliente temporal)
    log.debug("PSEUDONYMIZER_CONFIG: connecting to %s", config_endpoint)
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            payload: dict[str, Any] = {"literals": literals}
            log.debug("PSEUDONYMIZER_CONFIG: sending POST with %d literals", len(literals))
            resp = await client.post(
                config_endpoint,
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()
            log.info(
                "PSEUDONYMIZER_CONFIG: ✅ configured literals=%d paths=%d",
                result.get("literals", 0),
                result.get("paths", 0),
            )
    except httpx.ConnectError as e:
        log.warning("PSEUDONYMIZER_CONFIG: ⚠️  connection failed to %s (proxy not running?): %s", config_endpoint, e)
    except httpx.TimeoutException as e:
        log.warning("PSEUDONYMIZER_CONFIG: ⚠️  timeout connecting to %s: %s", config_endpoint, e)
    except httpx.HTTPError as e:
        log.warning("PSEUDONYMIZER_CONFIG: ⚠️  HTTP error from %s: %s", config_endpoint, e)
    except Exception as e:
        log.warning("PSEUDONYMIZER_CONFIG: ⚠️  unexpected error: %s", e)
