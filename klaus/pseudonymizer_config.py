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
    project_root: Path | None = None,
) -> None:
    """Detectar valores sensibles y registrarlos en el pseudonymizer del proxy.

    Argumentos:
      base_url: URL del proxy (e.g., "http://localhost:8080/v1")
      project_root: Raíz del proyecto actual
    """
    if not base_url:
        log.debug("PSEUDONYMIZER_CONFIG: base_url vacío, skip")
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
    async with httpx.AsyncClient() as client:
        try:
            payload: dict[str, Any] = {"literals": literals}
            resp = await client.post(
                config_endpoint,
                json=payload,
                timeout=5.0,
            )
            resp.raise_for_status()
            result = resp.json()
            log.info(
                "PSEUDONYMIZER_CONFIG: configured literals=%d paths=%d endpoint=%s",
                result.get("literals", 0),
                result.get("paths", 0),
                config_endpoint,
            )
        except httpx.HTTPError as e:
            log.warning("PSEUDONYMIZER_CONFIG: failed to configure %s: %s", config_endpoint, e)
        except Exception as e:
            log.warning("PSEUDONYMIZER_CONFIG: unexpected error: %s", e)
