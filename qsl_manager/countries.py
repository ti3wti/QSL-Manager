"""
Deriva país y coordenadas aproximadas a partir del prefijo de un indicativo
de radioaficionado. La tabla vive en prefixes.json para que se pueda ampliar
sin tocar código.

Nota: esto da una ubicación aproximada del PAÍS, no de la estación exacta.
Si la QSL trae un locator (grid square), ese se usa en su lugar porque es
mucho más preciso (ver locator.py).
"""
import json
from pathlib import Path

PREFIXES_PATH = Path(__file__).resolve().parent / "prefixes.json"

with open(PREFIXES_PATH, encoding="utf-8") as f:
    _PREFIX_TABLE = json.load(f)

# Ordenar prefijos del más largo al más corto para que "EA8" se pruebe
# antes que "EA" (así no todo lo canario cae como España peninsular).
_SORTED_PREFIXES = sorted(_PREFIX_TABLE.keys(), key=len, reverse=True)


def resolve_country(callsign: str):
    """Devuelve (pais, lat, lon) o (None, None, None) si no se reconoce."""
    if not callsign:
        return None, None, None
    callsign = callsign.strip().upper()
    for prefix in _SORTED_PREFIXES:
        if callsign.startswith(prefix):
            country, lat, lon = _PREFIX_TABLE[prefix]
            return country, lat, lon
    return None, None, None
