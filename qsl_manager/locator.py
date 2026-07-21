"""
Convierte un grid locator (Maidenhead), ej. "IL18SD", a lat/lon aproximado
(centro de la celda). Soporta 4 o 6 caracteres.
"""
import re

LOCATOR_RE = re.compile(r"\b([A-R]{2}\d{2}([A-X]{2})?)\b")


def find_locator(text: str):
    """Busca un locator válido dentro de un bloque de texto OCR."""
    if not text:
        return None
    match = LOCATOR_RE.search(text.upper())
    return match.group(1) if match else None


def locator_to_latlon(locator: str):
    if not locator:
        return None, None
    locator = locator.upper().strip()
    if len(locator) not in (4, 6):
        return None, None

    lon = (ord(locator[0]) - ord("A")) * 20 - 180
    lat = (ord(locator[1]) - ord("A")) * 10 - 90
    lon += int(locator[2]) * 2
    lat += int(locator[3]) * 1

    if len(locator) == 6:
        lon += (ord(locator[4]) - ord("A")) * (2 / 24)
        lat += (ord(locator[5]) - ord("A")) * (1 / 24)
        lon += 1 / 24  # centrar en la sub-celda
        lat += 1 / 48
    else:
        lon += 1  # centrar en la celda de 4 caracteres
        lat += 0.5

    return round(lat, 5), round(lon, 5)
