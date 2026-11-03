import re

_PATTERN = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def parse_duration(text: str) -> int:
    """Convierte '1h30m' en segundos (5400). ValueError si la entrada no es válida."""
    match = _PATTERN.fullmatch(text.strip()) if text else None
    if not match or not any(match.groups()):
        raise ValueError(f"duración inválida: {text!r}")
    h, m, s = (int(g) if g else 0 for g in match.groups())
    return h * 3600 + m * 60 + s
