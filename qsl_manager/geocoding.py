"""
Geocodificación inversa gratuita usando Nominatim (OpenStreetMap) -- sin
API key. Se usa como último recurso: cuando ni la IA ni el prefijo del
indicativo dieron un país, pero SÍ tenemos coordenadas exactas (porque la
QSL trae locator/grid square), le preguntamos a Nominatim "¿qué país cae
en este punto?" y pedimos la respuesta directo en español.

Nominatim es un servicio compartido y gratuito con una política de uso
estricta: máximo ~1 solicitud/segundo y un User-Agent identificable. Por
eso hay pausa entre llamadas y un cache en memoria (las coordenadas de un
locator de 4 caracteres son una zona de ~180x180km, así que vale la pena
cachear por celda para no repetir la misma consulta).
"""
import time

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_last_call_at = [0.0]
_MIN_INTERVAL_SECONDS = 1.1
_cache = {}


def reverse_geocode_country(lat: float, lon: float) -> str | None:
    if lat is None or lon is None:
        return None

    # Cachear por celda de ~0.5 grados: de sobra para no perder precisión
    # a nivel país, y evita pegarle a Nominatim por cada QSL de la misma zona.
    cache_key = (round(lat * 2) / 2, round(lon * 2) / 2)
    if cache_key in _cache:
        return _cache[cache_key]

    elapsed = time.time() - _last_call_at[0]
    if elapsed < _MIN_INTERVAL_SECONDS:
        time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
    _last_call_at[0] = time.time()

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"lat": lat, "lon": lon, "zoom": 3, "format": "json", "accept-language": "es"},
            headers={"User-Agent": "QSLManager/1.0 (uso personal de radioaficionado)"},
            timeout=10,
        )
        if not resp.ok:
            return None
        data = resp.json()
        country = (data.get("address", {}) or {}).get("country")
        _cache[cache_key] = country
        return country
    except requests.RequestException:
        return None
