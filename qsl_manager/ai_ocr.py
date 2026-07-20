"""
Extracción de campos de una QSL usando un modelo de IA con visión
(Google Gemini, capa gratuita -- no requiere tarjeta de crédito).

A diferencia de Tesseract (que solo lee caracteres), un modelo de visión
entiende el LAYOUT completo de la tarjeta: sabe que "OPERATOR:" antecede
al indicativo que nos interesa, que un logo estilizado grande dice
"LU6EGD", que "Cartago, C.R" implica país = Costa Rica, etc. Esto resuelve
el problema de fondo de las QSL "de diseño" donde Tesseract falla.

Requiere una API key gratuita de Google AI Studio:
https://aistudio.google.com/apikey (sin tarjeta de crédito).
Se guarda en data/config.json (ver config.py) y se administra desde la
interfaz (botón de engranaje).
"""
import base64
import io
import json
import time
from pathlib import Path

import requests
from PIL import Image

from . import config as app_config

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _build_prompt() -> str:
    my_call = app_config.load_config().get("owner_callsign", "").strip().upper()
    contexto = (
        f"Esta es una tarjeta QSL enviada A la estación {my_call}. "
        if my_call else
        "Esta es una tarjeta QSL de confirmación de contacto entre dos "
        "estaciones de radioaficionados. "
    )
    exclusion = f' -- nunca devuelvas {my_call} como resultado en "callsign"' if my_call else ""
    return f"""Eres un asistente que extrae datos de tarjetas QSL de radioaficionados.
{contexto}Identifica el
indicativo de la OTRA estación (el remitente de la tarjeta, casi siempre
bajo "OPERATOR", "DE", "STATION", o como el texto/logo más prominente en
la tarjeta){exclusion}.

Devuelve SOLO un objeto JSON (sin explicación, sin markdown) con estos
campos exactos. Usa null si un dato no aparece o no estás seguro:

{{
  "callsign": "indicativo de la otra estación, en mayúsculas",
  "country": "país de esa estación, en español, o null si no es deducible",
  "qso_date": "fecha del contacto en formato YYYY-MM-DD, o null",
  "band": "banda o frecuencia, ej. '2M', '70CM', '20M', o null",
  "mode": "modo, ej. SSB, FM, CW, PKT, DIGITAL, FT8, o null",
  "rst": "reporte de señal (ej. 59, 599), o null",
  "locator": "grid locator Maidenhead de 4 o 6 caracteres si aparece, o null"
}}"""


class AIExtractionError(Exception):
    pass


def list_available_models(api_key: str) -> list:
    """Le pregunta a Google qué modelos están disponibles AHORA para esta
    API key, en vez de adivinar un nombre fijo que Google puede retirar
    en cualquier momento (como ya pasó dos veces). Filtra a los que
    soportan generateContent (los que sirven para esto)."""
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    resp = requests.get(url, params={"key": api_key}, timeout=15)
    if not resp.ok:
        raise AIExtractionError(f"No se pudo listar modelos (HTTP {resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    names = []
    for m in data.get("models", []):
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" in methods:
            name = m.get("name", "").replace("models/", "")
            names.append(name)
    # Poner primero el alias "latest" (Google lo mantiene siempre apuntando
    # al modelo vigente, así nunca queda pegado a una versión retirada como
    # ya pasó con gemini-2.0-flash). Luego flash-lite, luego flash, evitando
    # previews inestables.
    def sort_key(n):
        n = n.lower()
        if n in ("gemini-flash-lite-latest", "gemini-flash-latest"):
            priority = 0
        elif "flash-lite" in n and "preview" not in n:
            priority = 1
        elif "flash" in n and "preview" not in n:
            priority = 2
        else:
            priority = 3
        return (priority, n)
    names.sort(key=sort_key)
    return names


# --- Control de velocidad (throttle) ----------------------------------
# La capa gratuita de Gemini limita solicitudes POR MINUTO (no solo por
# día). Sin esto, un import de 30 archivos manda las peticiones casi
# pegadas y la mayoría choca con el límite (429) desde el segundo o
# tercer archivo -- que es justo lo que te pasó. Con esta pausa mínima
# entre llamadas, nos quedamos cómodos por debajo de ese límite.
_MIN_INTERVAL_SECONDS = 4.5  # ~13 solicitudes/minuto como techo seguro
_last_call_at = [0.0]


def _throttle():
    elapsed = time.time() - _last_call_at[0]
    if elapsed < _MIN_INTERVAL_SECONDS:
        time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
    _last_call_at[0] = time.time()


def _image_to_jpeg_bytes(img: Image.Image, max_dim: int = 1600) -> bytes:
    """Redimensiona (si hace falta) y comprime para no gastar cuota de más."""
    img = img.convert("RGB")
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _call_gemini(image_bytes: bytes, api_key: str, model: str, retries: int = 2) -> dict:
    url = GEMINI_ENDPOINT.format(model=model)
    payload = {
        "contents": [{
            "parts": [
                {"text": _build_prompt()},
                {"inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }},
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        },
    }

    last_error = None
    for attempt in range(retries):
        _throttle()
        try:
            resp = requests.post(
                url,
                params={"key": api_key},
                json=payload,
                timeout=30,
            )
        except requests.RequestException as e:
            last_error = f"No se pudo conectar con Gemini: {e}"
            time.sleep(1.5)
            continue

        if resp.status_code == 429:
            # Límite de la capa gratuita: esperar y reintentar, pero con un
            # techo -- si en 2 intentos sigue fallando, es más probable que
            # sea un problema de cuota/modelo real (no un pico pasajero) y
            # conviene dar la cara rápido en vez de tener al usuario
            # esperando varios minutos por archivo.
            wait = min(float(resp.headers.get("Retry-After", 15 * (attempt + 1))), 25)
            last_error = "Límite de solicitudes gratuitas de Gemini alcanzado (429)"
            time.sleep(wait)
            continue

        if resp.status_code == 404:
            raise AIExtractionError(
                f"El modelo '{model}' no existe o fue retirado por Google. "
                f"Cambia el modelo en ⚙ Configuración (ej. 'gemini-2.5-flash-lite') "
                f"-- revisa el nombre vigente en ai.google.dev/gemini-api/docs/pricing."
            )

        if resp.status_code == 400 and "API_KEY_INVALID" in resp.text:
            raise AIExtractionError(
                "La API key de Gemini no es válida. Revísala en Configuración."
            )

        if not resp.ok:
            last_error = f"Gemini respondió HTTP {resp.status_code}: {resp.text[:200]}"
            time.sleep(1.5)
            continue

        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise AIExtractionError(
                f"Respuesta inesperada de Gemini (sin contenido): {json.dumps(data)[:200]}"
            )

        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.split("\n", 1)[-1] if "\n" in text else text
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise AIExtractionError(f"Gemini no devolvió JSON válido: {text[:200]}")

    raise AIExtractionError(last_error or "Fallo desconocido llamando a Gemini")


def extract_fields_with_ai(image: Image.Image, api_key: str, model: str) -> dict:
    """Devuelve los mismos campos que ocr.parse_fields(), usando el modelo de IA."""
    image_bytes = _image_to_jpeg_bytes(image)
    raw = _call_gemini(image_bytes, api_key, model)

    callsign = (raw.get("callsign") or "").strip().upper() or None
    my_call = app_config.load_config().get("owner_callsign", "").strip().upper()
    if my_call and callsign == my_call:
        callsign = None  # el modelo confundió cuál era la "otra" estación

    return {
        "callsign": callsign,
        "country": (raw.get("country") or "").strip() or None,
        "qso_date": (raw.get("qso_date") or "").strip() or None,
        "band": (raw.get("band") or "").strip() or None,
        "mode": (raw.get("mode") or "").strip() or None,
        "rst": str(raw.get("rst")).strip() if raw.get("rst") else None,
        "locator": (raw.get("locator") or "").strip().upper() or None,
        "ocr_text": json.dumps(raw, ensure_ascii=False),
    }
