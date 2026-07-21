"""
Configuración local de la app (API key de Gemini, etc).
Se guarda en data/config.json -- nunca se sube a ningún lado, vive solo
en tu PC. No confundir con prefixes.json (eso es la tabla de países).
"""
import json
from pathlib import Path

from .paths import BASE_DIR

CONFIG_PATH = BASE_DIR / "data" / "config.json"

DEFAULTS = {
    "gemini_api_key": "",
    "gemini_model": "gemini-flash-lite-latest",
    "ocr_engine": "auto",  # "auto" (IA si hay key, si no Tesseract) | "ai" | "tesseract"
    "tesseract_path": "",  # ej. C:\Program Files\Tesseract-OCR\tesseract.exe
    "theme": "system",  # "light" | "dark" | "system"
    "map_style": "voyager",  # "voyager" | "positron" | "dark" | "osm"
    "eqsl_username": "",
    "eqsl_password": "",
    "telemetry_opt_in": True,  # marcado por defecto; el usuario puede desactivarlo
    "onboarding_done": False,  # True cuando el usuario ya vio/descartó el asistente inicial
    "owner_callsign": "",  # el indicativo del dueño de esta instalación (ya no viene fijo en el código)
    "ui_language": "es",  # "es" | "en"
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save_config(updates: dict) -> dict:
    current = load_config()
    current.update({k: v for k, v in updates.items() if k in DEFAULTS})
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    return current
