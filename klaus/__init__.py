"""Klaus Code CLI — agente de codificación agnóstico de proveedor."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Fuente única de verdad: `version` en pyproject.toml (#58)
    __version__ = version("klaus-code-cli")
except PackageNotFoundError:  # ejecutado desde el código fuente sin instalar
    __version__ = "0.0.0+unknown"
