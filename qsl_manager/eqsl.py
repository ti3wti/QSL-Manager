"""
Cliente para eQSL.cc InBox, siguiendo el mecanismo oficial documentado en
https://www.eqsl.cc/QSLCard/DownloadInBox.txt y GeteQSL.txt

Proceso (no hay una sola llamada que traiga todo, es en 2 pasos):
1. DownloadInBox.cfm con usuario/password -> devuelve HTML con un link a
   un archivo .ADI (el log de QSOs confirmados, sin las imágenes).
2. Por cada QSO de ese ADIF, GeteQSL.cfm con los datos exactos de esa QSO
   (indicativo, fecha, hora, banda, modo) -> devuelve LA IMAGEN de esa
   tarjeta puntual.

eQSL no deja bajar todo de golpe: hay que pedir las imágenes una por una,
con pausa entre cada una (por eso el "hay que ir despacito").
"""
import re
import time
from datetime import datetime

import requests

BASE = "https://www.eQSL.cc/qslcard"
DELAY_BETWEEN_CARDS_SECONDS = 2.2


class EqslError(Exception):
    pass


def _parse_adif(adif_text: str) -> list:
    """Parser mínimo de ADIF: extrae los campos que necesitamos de cada QSO."""
    records = []
    # Cada registro termina en <eor> (case-insensitive); nos quedamos con
    # el bloque de texto de cada uno y sacamos los campos con regex.
    blocks = re.split(r"<eor>", adif_text, flags=re.IGNORECASE)
    field_re = re.compile(r"<(\w+):(\d+)(?::\w+)?>", re.IGNORECASE)
    for block in blocks:
        fields = {}
        pos = 0
        for m in field_re.finditer(block):
            name = m.group(1).upper()
            length = int(m.group(2))
            start = m.end()
            value = block[start:start + length]
            # Defensa extra: si el largo declarado se comió el inicio del
            # siguiente tag (ADIF mal formado), recortar ahí.
            value = value.split("<")[0]
            fields[name] = value.strip()
        if fields.get("CALL") and fields.get("QSO_DATE"):
            records.append(fields)
    return records


def fetch_inbox_qsos(username: str, password: str) -> list:
    """Descarga el ADIF del inbox y lo parsea. No baja imágenes todavía."""
    headers = {
        # Algunos sitios devuelven una respuesta distinta (o bloquean) sin
        # un User-Agent que parezca un navegador real.
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QSLManager/1.0"
    }
    resp = requests.get(
        f"{BASE}/DownloadInBox.cfm",
        params={
            "UserName": username,
            "Password": password,
            "QTHNickname": "",
            "LimitDateLo": "01/01/1900",
            "LimitDateHi": "12/31/2099",
        },
        headers=headers,
        timeout=30,
    )
    if not resp.ok:
        raise EqslError(f"eQSL.cc respondió HTTP {resp.status_code}")

    if "No such Username/Password" in resp.text or "not found" in resp.text.lower():
        raise EqslError("Usuario o contraseña de eQSL.cc incorrectos.")

    if "NO QSO" in resp.text.upper():
        return []

    # El link al .adi puede venir con comillas simples o dobles, y
    # mayúsculas/minúsculas variables según la versión del sitio.
    m = re.search(r'href=[\'"]([^\'"]+\.adi)[\'"]', resp.text, re.IGNORECASE)
    if not m:
        snippet = re.sub(r"\s+", " ", resp.text).strip()[:600]
        raise EqslError(
            f"No se encontró el enlace al archivo ADIF en la respuesta de "
            f"eQSL.cc. Esto es lo que respondió (primeros 300 caracteres), "
            f"revísalo para ver si pide algo distinto: {snippet!r}"
        )

    adif_url = m.group(1)
    if adif_url.startswith("http"):
        full_url = adif_url
    else:
        full_url = f"{BASE}/{adif_url.lstrip('/')}"

    adif_resp = requests.get(full_url, headers=headers, timeout=30)
    if not adif_resp.ok:
        raise EqslError(f"No se pudo descargar el archivo ADIF (HTTP {adif_resp.status_code}).")

    return _parse_adif(adif_resp.text)


def _normalize_date(qso_date: str) -> str:
    """ADIF trae la fecha como YYYYMMDD."""
    return f"{qso_date[0:4]}-{qso_date[4:6]}-{qso_date[6:8]}"


def download_card_image(username: str, password: str, qso: dict) -> bytes:
    """Baja la imagen de UNA tarjeta puntual con GeteQSL.cfm."""
    qso_date = qso["QSO_DATE"]  # YYYYMMDD
    time_on = qso.get("TIME_ON", "0000")  # HHMM o HHMMSS
    params = {
        "Username": username,
        "Password": password,
        "CallsignFrom": qso["CALL"],
        "QSOYear": qso_date[0:4],
        "QSOMonth": qso_date[4:6],
        "QSODay": qso_date[6:8],
        "QSOHour": time_on[0:2],
        "QSOMinute": time_on[2:4],
        "QSOBand": qso.get("BAND", ""),
        "QSOMode": qso.get("MODE", ""),
    }
    resp = requests.get(
        f"{BASE}/GeteQSL.cfm",
        params=params,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QSLManager/1.0"},
        timeout=30,
    )
    if not resp.ok:
        raise EqslError(f"No se pudo bajar la tarjeta de {qso['CALL']} ({qso_date}): HTTP {resp.status_code}")

    content_type = resp.headers.get("content-type", "")

    if content_type.startswith("image/"):
        # Caso simple: ya viene la imagen directa (no parece ser lo normal,
        # pero por si acaso lo soportamos).
        return resp.content, _ext_from_content_type(content_type)

    # Caso real observado: eQSL devuelve una página HTML con un comentario
    # que indica que hay que buscar el tag <IMG SRC="..."> y anteponerle
    # el dominio para armar la URL final de la imagen real.
    m = re.search(r'<img\s+src="([^"]+)"', resp.text, re.IGNORECASE)
    if not m:
        snippet = re.sub(r"\s+", " ", resp.text).strip()[:300]
        raise EqslError(
            f"No se encontró la imagen en la respuesta de eQSL para "
            f"{qso['CALL']} ({qso_date}): {snippet!r}"
        )
    img_path = m.group(1)
    img_url = img_path if img_path.startswith("http") else f"https://www.eQSL.cc{img_path}"

    img_resp = requests.get(
        img_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) QSLManager/1.0"},
        timeout=30,
    )
    if not img_resp.ok:
        raise EqslError(f"No se pudo bajar la imagen final de {qso['CALL']} desde {img_url} (HTTP {img_resp.status_code}).")

    return img_resp.content, _ext_from_content_type(img_resp.headers.get("content-type", ""), img_url)


def _ext_from_content_type(content_type: str, url: str = "") -> str:
    content_type = content_type.lower()
    if "png" in content_type or url.lower().endswith(".png"):
        return ".png"
    if "gif" in content_type or url.lower().endswith(".gif"):
        return ".gif"
    return ".jpg"


def qso_to_fields(qso: dict) -> dict:
    """Convierte un registro ADIF a los mismos campos que usa el resto de
    la app (callsign, qso_date, band, mode, ...) -- ya vienen confirmados
    por eQSL, no hace falta OCR para estos."""
    return {
        "callsign": qso["CALL"].upper(),
        "qso_date": _normalize_date(qso["QSO_DATE"]),
        "band": qso.get("BAND", "").upper() or None,
        "mode": qso.get("MODE", "").upper() or None,
        "rst": qso.get("RST_RCVD") or None,
        "locator": qso.get("GRIDSQUARE") or None,
    }


def source_key(qso: dict) -> str:
    """Clave única para no volver a bajar la misma tarjeta en una segunda pasada."""
    return f"eqsl:{qso['CALL'].upper()}:{qso['QSO_DATE']}:{qso.get('TIME_ON', '')}"
