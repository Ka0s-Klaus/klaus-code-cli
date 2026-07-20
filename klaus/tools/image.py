"""Tool de soporte multimodal: read_image.

Carga una imagen desde disco o URL y la convierte a base64 para incluirla
en el contexto del LLM como bloque de contenido image.

Requiere: Pillow (PIL) para redimensionado/validación.
Formatos soportados: PNG, JPEG, GIF, WEBP (soporte nativo Anthropic).
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
_SUPPORTED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_TYPE_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


async def read_image(
    path: str,
    max_size_kb: int = 2048,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Lee una imagen desde disco y la codifica en base64 para el LLM.

    Devuelve un dict con el bloque de contenido image en formato Anthropic:
      { "type": "image", "source": { "type": "base64", "media_type": "...", "data": "..." } }

    Si la imagen supera max_size_kb, la redimensiona (requiere Pillow).
    """
    target = _resolve(path, cwd)

    if not target.exists():
        return {"error": f"Imagen no encontrada: {path}"}
    if not target.is_file():
        return {"error": f"No es un fichero: {path}"}

    # Detectar media type
    media_type = _detect_media_type(target)
    if media_type not in _SUPPORTED_TYPES:
        return {
            "error": (
                f"Formato de imagen no soportado: {media_type}. "
                f"Formatos válidos: {', '.join(_SUPPORTED_TYPES)}"
            )
        }

    raw = target.read_bytes()
    size_kb = len(raw) / 1024

    # Redimensionar si excede el límite
    if size_kb > max_size_kb:
        try:
            raw, media_type = _resize_image(raw, media_type, max_size_kb)
            size_kb = len(raw) / 1024
        except ImportError:
            return {
                "error": (
                    f"La imagen ({size_kb:.0f} KB) excede el límite de {max_size_kb} KB. "
                    "Instala Pillow para redimensionado automático: pip install Pillow"
                )
            }

    if len(raw) > _MAX_IMAGE_BYTES:
        return {"error": f"Imagen demasiado grande ({size_kb:.0f} KB > 5 MB)"}

    data = base64.standard_b64encode(raw).decode("ascii")

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        },
        "metadata": {
            "path": str(target),
            "size_kb": round(size_kb, 1),
            "media_type": media_type,
        },
    }


async def read_image_from_clipboard(
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Captura una imagen del portapapeles del sistema.

    Requiere: Pillow con soporte de clipboard (Linux: xclip/wl-paste, Mac: pbpaste).
    """
    try:
        from PIL import ImageGrab  # type: ignore[import]

        img = ImageGrab.grabclipboard()
        if img is None:
            return {"error": "No hay imagen en el portapapeles"}

        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw = buf.getvalue()
        data = base64.standard_b64encode(raw).decode("ascii")

        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": data,
            },
            "metadata": {
                "path": "<clipboard>",
                "size_kb": round(len(raw) / 1024, 1),
                "media_type": "image/png",
            },
        }
    except ImportError:
        return {"error": "Pillow no está instalado: pip install Pillow"}
    except Exception as e:
        return {"error": f"Error capturando clipboard: {e}"}


def _resolve(path: str, cwd: Path | None) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = (cwd or Path.cwd()) / p
    return p.resolve()


def _detect_media_type(path: Path) -> str:
    """Detecta el media type por extensión y, si es posible, por magic bytes."""
    mt, _ = mimetypes.guess_type(str(path))
    if mt and mt in _SUPPORTED_TYPES:
        return mt

    # Magic bytes fallback
    header = path.read_bytes()[:12]
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if header[:2] in (b"\xff\xd8", b"\xff\xe0", b"\xff\xe1"):
        return "image/jpeg"
    if header[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if header[:4] in (b"RIFF", b"WEBP"):
        return "image/webp"
    return mt or "application/octet-stream"


def _resize_image(raw: bytes, media_type: str, max_kb: int) -> tuple[bytes, str]:
    """Redimensiona la imagen usando Pillow hasta que quepa en max_kb."""
    import io

    from PIL import Image  # type: ignore[import]

    img = Image.open(io.BytesIO(raw))
    fmt = "PNG" if media_type == "image/png" else "JPEG"
    out_type = media_type

    scale = 0.8
    for _ in range(6):
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        if fmt == "JPEG":
            resized.save(buf, format=fmt, quality=85)
        else:
            resized.save(buf, format=fmt)
        result = buf.getvalue()
        if len(result) / 1024 <= max_kb:
            return result, out_type
        scale *= 0.8

    # Último recurso: JPEG con calidad reducida
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=60)
    return buf.getvalue(), "image/jpeg"
