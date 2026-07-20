"""
API local del QSL Manager.
Corre sobre http://127.0.0.1:8756 (solo accesible desde esta PC).
"""
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, ocr, ai_ocr, eqsl, geocoding, config as app_config
from .countries import resolve_country
from .locator import locator_to_latlon
from .version import APP_VERSION, GITHUB_REPO

BASE_DIR = Path(__file__).resolve().parent.parent
CARDS_DIR = BASE_DIR / "data" / "cards"
STATIC_DIR = BASE_DIR / "static"
CARDS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="QSL Manager")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


def _resolve_location(card_fields: dict):
    """Prioriza el locator (más preciso) para lat/lon. Para el nombre del
    país, prioriza el que haya devuelto la IA (entiende contexto, ej. una
    ciudad mencionada), luego el prefijo del indicativo, y como último
    recurso -- si hay locator pero ninguno de los anteriores dio país --
    le pregunta a Nominatim (OSM) qué país cae en esas coordenadas."""
    prefix_country, country_lat, country_lon = resolve_country(card_fields.get("callsign"))
    country = card_fields.get("country") or prefix_country
    lat, lon = (None, None)
    if card_fields.get("locator"):
        lat, lon = locator_to_latlon(card_fields["locator"])
    if lat is None:
        lat, lon = country_lat, country_lon
    if not country and lat is not None:
        country = geocoding.reverse_geocode_country(lat, lon)
    return country, lat, lon


def _get_image_for_ai(file_path: Path):
    from PIL import Image
    try:
        img = Image.open(file_path)
        img.load()
        return img
    except Exception as e:
        raise ai_ocr.AIExtractionError(
            f"El archivo no se pudo leer como imagen (¿dañado o no es "
            f"realmente ese formato pese a la extensión?): {e}"
        ) from e


def run_extraction(file_path: Path, force_engine: str = None) -> dict:
    """Punto único de entrada para OCR/IA. Devuelve los campos + la imagen
    de preview (para PDFs) igual que ocr.process_file(), más 'engine_used'
    para que la interfaz pueda mostrarlo si hace falta.

    Lógica de motor:
    - force_engine="ai": solo IA, sin fallback (para que el error se vea).
    - force_engine="tesseract": solo Tesseract, ignora la config de IA.
    - None (por defecto): sigue la preferencia guardada en config.json
      ("auto" = IA si hay API key, si no Tesseract; o lo que el usuario
      haya fijado explícitamente).
    """
    cfg = app_config.load_config()
    engine_pref = force_engine or cfg.get("ocr_engine", "auto")
    api_key = cfg.get("gemini_api_key", "").strip()

    use_ai = (engine_pref == "ai") or (engine_pref == "auto" and api_key)

    # El recorte de PDF (para preview/OCR) siempre hace falta si es PDF,
    # se genera una sola vez y se reutiliza para el motor que se use.
    preview_img = None
    if file_path.suffix.lower() == ".pdf":
        preview_img = ocr.render_pdf_preview(file_path, 0)

    if use_ai:
        if not api_key:
            raise ai_ocr.AIExtractionError(
                "No hay una API key de Gemini configurada. Ábrela desde el "
                "botón ⚙ Configuración (es gratis, sin tarjeta de crédito)."
            )
        try:
            img_for_ai = preview_img if file_path.suffix.lower() == ".pdf" else _get_image_for_ai(file_path)
            fields = ai_ocr.extract_fields_with_ai(img_for_ai, api_key, cfg.get("gemini_model", "gemini-2.0-flash"))
            fields["preview_image"] = preview_img
            fields["engine_used"] = "ai"
            return fields
        except ai_ocr.AIExtractionError:
            if force_engine == "ai":
                raise
            # Fallback silencioso a Tesseract si el motor no fue forzado a IA
        except Exception:
            if force_engine == "ai":
                raise

    fields = ocr.process_file(file_path, force_ocr=(force_engine == "tesseract"))
    fields["engine_used"] = "tesseract"
    return fields


@app.get("/api/settings")
def get_settings():
    return app_config.load_config()


class SettingsUpdate(BaseModel):
    owner_callsign: str | None = None
    ui_language: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    ocr_engine: str | None = None
    tesseract_path: str | None = None
    theme: str | None = None
    map_style: str | None = None
    onboarding_done: bool | None = None
    eqsl_username: str | None = None
    eqsl_password: str | None = None
    telemetry_opt_in: bool | None = None


@app.put("/api/settings")
def update_settings(update: SettingsUpdate):
    data = {k: v for k, v in update.dict().items() if v is not None}
    return app_config.save_config(data)


@app.get("/api/settings/gemini-models")
def list_gemini_models():
    cfg = app_config.load_config()
    api_key = cfg.get("gemini_api_key", "").strip()
    if not api_key:
        raise HTTPException(400, "Guarda una API key primero, luego detecta los modelos.")
    try:
        models = ai_ocr.list_available_models(api_key)
    except Exception as e:
        raise HTTPException(500, f"No se pudo obtener la lista de modelos: {e}")
    return {"models": models}


@app.post("/api/bundle-tesseract")
def bundle_tesseract():
    """Copia la instalación de Tesseract ya configurada (tesseract_path)
    a tesseract-bin/ dentro del proyecto, para que al empaquetar la app
    con PyInstaller para un colega, quede incluida y no tenga que
    instalar ni configurar nada."""
    cfg = app_config.load_config()
    tpath = cfg.get("tesseract_path", "").strip()
    source_exe = Path(tpath) if tpath else None
    if not source_exe or not source_exe.exists():
        # Si no hay ruta configurada a mano, intentar con lo que pytesseract
        # encuentre por sí solo (típicamente en el PATH del sistema).
        found = shutil.which("tesseract")
        source_exe = Path(found) if found else None
    if not source_exe or not source_exe.exists():
        raise HTTPException(
            400,
            "No encuentro un tesseract.exe para empaquetar. Configura primero "
            "la 'Ruta tesseract' en Configuración."
        )

    source_dir = source_exe.parent
    try:
        files = [f for f in source_dir.rglob("*") if f.is_file()]
    except OSError as e:
        raise HTTPException(400, f"No pude leer la carpeta {source_dir}: {e}")

    total_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
    if len(files) > 300 or total_mb > 600:
        raise HTTPException(
            400,
            f"La carpeta de '{source_exe.name}' ({source_dir}) tiene {len(files)} "
            f"archivos / {total_mb:.0f} MB -- parece una carpeta compartida del "
            f"sistema, no la carpeta dedicada de Tesseract-OCR. Verifica la ruta "
            f"en Configuración (debería apuntar a algo como "
            f"'C:\\Program Files\\Tesseract-OCR\\tesseract.exe')."
        )

    dest_dir = ocr.BUNDLED_TESSERACT_DIR
    try:
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(source_dir, dest_dir)
    except OSError as e:
        raise HTTPException(500, f"Fallo copiando {source_dir} a {dest_dir}: {e}")

    dest_exe = dest_dir / source_exe.name
    if dest_exe.name.lower() != "tesseract.exe" and (dest_dir / "tesseract.exe").exists():
        dest_exe = dest_dir / "tesseract.exe"

    size_mb = sum(f.stat().st_size for f in dest_dir.rglob("*") if f.is_file()) / (1024 * 1024)
    return {
        "ok": True,
        "bundled_path": str(dest_dir),
        "size_mb": round(size_mb, 1),
        "message": f"Tesseract copiado a {dest_dir} ({size_mb:.0f} MB). "
                   f"A partir de ahora, cualquiera que reciba esta carpeta "
                   f"(o el .exe empaquetado con PyInstaller) tiene OCR local "
                   f"funcionando sin instalar nada.",
    }


@app.post("/api/import")
async def import_card(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp", ".pdf"):
        raise HTTPException(400, f"Tipo de archivo no soportado: {suffix}")

    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = CARDS_DIR / stored_name
    with open(stored_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    preview_relpath = None
    recognized_by = None
    try:
        fields = run_extraction(stored_path)
        recognized_by = fields.pop("engine_used", None)
        preview_img = fields.pop("preview_image", None)
        if preview_img is not None:
            preview_name = f"{Path(stored_name).stem}_preview.jpg"
            preview_path = CARDS_DIR / preview_name
            preview_img.convert("RGB").save(preview_path, "JPEG", quality=88)
            preview_relpath = str(preview_path.relative_to(BASE_DIR))
    except Exception as e:
        fields = {"callsign": None, "qso_date": None, "band": None,
                   "mode": None, "rst": None, "locator": None,
                   "ocr_text": f"[Error de reconocimiento: {file.filename}: {e}]"}

    country, lat, lon = _resolve_location(fields)

    card_id = db.insert_card({
        "filename": file.filename,
        "stored_path": str(stored_path.relative_to(BASE_DIR)),
        "preview_path": preview_relpath,
        "callsign": fields["callsign"],
        "country": country,
        "qso_date": fields["qso_date"],
        "band": fields["band"],
        "mode": fields["mode"],
        "rst": fields["rst"],
        "locator": fields["locator"],
        "lat": lat,
        "lon": lon,
        "ocr_text": fields["ocr_text"],
        "verified": 0,
        "recognized_by": recognized_by,
    })
    return db.get_card(card_id)


@app.post("/api/cards/{card_id}/reprocess-ocr")
def reprocess_ocr(card_id: int, engine: str = "auto"):
    """Vuelve a procesar el archivo ya importado (botón 'Realizar OCR').

    engine: "auto" (sigue la config guardada), "ai" (fuerza Gemini, sin
    fallback -- para ver el error real si algo falla), o "tesseract"
    (fuerza OCR local, ignorando texto nativo de PDF si lo hubiera).

    No guarda nada todavía: devuelve los campos detectados para que el
    usuario los revise en el modal y decida si los guarda.
    """
    card = db.get_card(card_id)
    if not card:
        raise HTTPException(404, "Tarjeta no encontrada")
    file_path = BASE_DIR / card["stored_path"]
    if not file_path.exists():
        raise HTTPException(404, "Archivo original no encontrado en disco")

    force_engine = None if engine == "auto" else engine
    try:
        fields = run_extraction(file_path, force_engine=force_engine)
    except Exception as e:
        raise HTTPException(500, f"Falló el reconocimiento: {e}")

    engine_used = fields.pop("engine_used", None)
    if engine_used:
        db.update_card(card_id, {"recognized_by": engine_used, "ocr_text": fields.get("ocr_text") or ""})

    preview_img = fields.pop("preview_image", None)
    if preview_img is not None:
        preview_name = f"{Path(card['stored_path']).stem}_preview.jpg"
        preview_path = CARDS_DIR / preview_name
        preview_img.convert("RGB").save(preview_path, "JPEG", quality=88)
        db.update_card(card_id, {"preview_path": str(preview_path.relative_to(BASE_DIR))})

    country, lat, lon = _resolve_location(fields)
    fields["country"] = country
    fields["lat"] = lat
    fields["lon"] = lon
    fields["engine_used"] = engine_used
    return fields


@app.get("/api/resolve")
def resolve_callsign_location(callsign: str):
    """Usado por la interfaz para autocompletar país mientras el usuario
    escribe el indicativo a mano."""
    country, lat, lon = resolve_country(callsign)
    return {"country": country, "lat": lat, "lon": lon}


class CardUpdate(BaseModel):
    callsign: str | None = None
    country: str | None = None
    qso_date: str | None = None
    band: str | None = None
    mode: str | None = None
    rst: str | None = None
    locator: str | None = None
    verified: int | None = None
    ocr_text: str | None = None


@app.put("/api/cards/{card_id}")
def update_card(card_id: int, update: CardUpdate):
    if not db.get_card(card_id):
        raise HTTPException(404, "Tarjeta no encontrada")
    data = {k: v for k, v in update.dict().items() if v is not None}

    # Si el usuario corrige el indicativo o el locator, recalcular ubicación.
    # El país recalculado tiene prioridad sobre lo que ya estuviera en el
    # campo -- si no, corregir el indicativo no actualizaba el país porque
    # el formulario siempre manda el valor viejo del campo País junto con
    # el nuevo indicativo.
    if "callsign" in data or "locator" in data:
        current = db.get_card(card_id)
        callsign = data.get("callsign", current["callsign"])
        locator = data.get("locator", current["locator"])
        resolved_country, lat, lon = _resolve_location({"callsign": callsign, "locator": locator})
        if resolved_country:
            data["country"] = resolved_country
        else:
            data.setdefault("country", current["country"])
        data["lat"] = lat
        data["lon"] = lon

    db.update_card(card_id, data)
    return db.get_card(card_id)


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: int):
    card = db.get_card(card_id)
    if not card:
        raise HTTPException(404, "Tarjeta no encontrada")
    file_path = BASE_DIR / card["stored_path"]
    if file_path.exists():
        file_path.unlink()
    if card.get("preview_path"):
        preview_path = BASE_DIR / card["preview_path"]
        if preview_path.exists():
            preview_path.unlink()
    db.delete_card(card_id)
    return {"ok": True}


@app.get("/api/cards")
def get_cards(country: str = None, callsign: str = None):
    return db.list_cards(country=country, callsign=callsign)


@app.get("/api/countries")
def get_countries():
    return db.list_countries()


@app.get("/api/cards/{card_id}/file")
def get_card_file(card_id: int):
    card = db.get_card(card_id)
    if not card:
        raise HTTPException(404, "Tarjeta no encontrada")
    file_path = BASE_DIR / card["stored_path"]
    if not file_path.exists():
        raise HTTPException(404, "Archivo no encontrado en disco")
    return FileResponse(file_path)


@app.get("/api/cards/{card_id}/preview")
def get_card_preview(card_id: int):
    """Devuelve la vista previa recortada (para PDFs); si no hay, cae al
    archivo original (imágenes)."""
    card = db.get_card(card_id)
    if not card:
        raise HTTPException(404, "Tarjeta no encontrada")
    preview_path = card.get("preview_path")
    if preview_path:
        full_preview = BASE_DIR / preview_path
        if full_preview.exists():
            return FileResponse(full_preview)
    file_path = BASE_DIR / card["stored_path"]
    if not file_path.exists():
        raise HTTPException(404, "Archivo no encontrado en disco")
    return FileResponse(file_path)


# --- Importador de eQSL.cc --------------------------------------------
# Corre en un hilo aparte porque baja las tarjetas UNA POR UNA con pausa
# (eQSL no permite descargas rápidas), lo que puede tomar varios minutos
# para un inbox grande. El estado se consulta con /api/eqsl/status.
_eqsl_state = {"running": False, "total": 0, "done": 0, "errors": 0, "current": None, "message": None, "last_error": None}
_eqsl_lock = threading.Lock()
_eqsl_cancel_event = threading.Event()


def _run_eqsl_import(username: str, password: str):
    global _eqsl_state
    _eqsl_cancel_event.clear()
    with _eqsl_lock:
        _eqsl_state.update(running=True, total=0, done=0, errors=0,
                            current="Conectando con eQSL.cc y descargando tu log...", message=None, last_error=None)
    try:
        qsos = eqsl.fetch_inbox_qsos(username, password)
    except Exception as e:
        with _eqsl_lock:
            _eqsl_state.update(running=False, current=None, message=f"Error: {e}")
        return

    with _eqsl_lock:
        _eqsl_state.update(total=len(qsos), done=0, errors=0, current=None)

    if not qsos:
        with _eqsl_lock:
            _eqsl_state.update(running=False, message="No se encontraron QSOs en tu inbox de eQSL.")
        return

    cancelled = False
    for qso in qsos:
        if _eqsl_cancel_event.is_set():
            cancelled = True
            break

        key = eqsl.source_key(qso)
        with _eqsl_lock:
            _eqsl_state["current"] = qso.get("CALL", "?")
        if db.source_key_exists(key):
            with _eqsl_lock:
                _eqsl_state["done"] += 1
            continue
        try:
            image_bytes, ext = eqsl.download_card_image(username, password, qso)
            stored_name = f"{uuid.uuid4().hex}{ext}"
            stored_path = CARDS_DIR / stored_name
            with open(stored_path, "wb") as f:
                f.write(image_bytes)

            fields = eqsl.qso_to_fields(qso)
            country, lat, lon = _resolve_location(fields)
            db.insert_card({
                "filename": f"eqsl_{fields['callsign']}_{fields['qso_date']}.jpg",
                "stored_path": str(stored_path.relative_to(BASE_DIR)),
                "callsign": fields["callsign"],
                "country": country,
                "qso_date": fields["qso_date"],
                "band": fields["band"],
                "mode": fields["mode"],
                "rst": fields["rst"],
                "locator": fields["locator"],
                "lat": lat,
                "lon": lon,
                "ocr_text": "",
                "verified": 1,  # viene confirmado por eQSL, no hace falta revisar
                "recognized_by": "eqsl",
                "source_key": key,
            })
        except Exception as e:
            with _eqsl_lock:
                _eqsl_state["errors"] += 1
                _eqsl_state["last_error"] = str(e)
            print(f"[eQSL] Error con {qso.get('CALL')}: {e}")

        with _eqsl_lock:
            _eqsl_state["done"] += 1
        # Espera interrumpible: si el usuario cancela, no hace falta esperar
        # los ~2.2s completos para que el botón "Detener" responda.
        if _eqsl_cancel_event.wait(timeout=eqsl.DELAY_BETWEEN_CARDS_SECONDS):
            cancelled = True
            break

    with _eqsl_lock:
        done, errors, total = _eqsl_state["done"], _eqsl_state["errors"], _eqsl_state["total"]
        if cancelled:
            msg = f"Detenido: {done}/{total} tarjetas procesadas antes de parar. Puedes reanudar cuando quieras, no vuelve a bajar las que ya tienes."
        elif errors:
            msg = f"Terminado: {total} tarjeta(s) revisadas, {errors} con error."
        else:
            msg = f"Terminado: {total} tarjeta(s) procesadas correctamente."
        _eqsl_state.update(running=False, current=None, message=msg)


class EqslStartRequest(BaseModel):
    username: str
    password: str


@app.post("/api/eqsl/start")
def start_eqsl_import(req: EqslStartRequest):
    with _eqsl_lock:
        if _eqsl_state["running"]:
            raise HTTPException(409, "Ya hay una descarga de eQSL en curso.")
        _eqsl_state.update(running=True, total=0, done=0, errors=0,
                            current="Conectando con eQSL.cc...", message=None, last_error=None)
    app_config.save_config({"eqsl_username": req.username, "eqsl_password": req.password})
    thread = threading.Thread(target=_run_eqsl_import, args=(req.username, req.password), daemon=True)
    thread.start()
    return {"started": True}


@app.get("/api/eqsl/status")
def get_eqsl_status():
    with _eqsl_lock:
        return dict(_eqsl_state)


@app.post("/api/eqsl/cancel")
def cancel_eqsl_import():
    with _eqsl_lock:
        if not _eqsl_state["running"]:
            raise HTTPException(400, "No hay ninguna descarga de eQSL corriendo.")
    _eqsl_cancel_event.set()
    return {"cancelling": True}


# --- Revisión masiva de pendientes ------------------------------------
# Para cuando el usuario importó/bajó varias QSL antes de configurar la
# IA (o Tesseract falló) y no quiere entrar tarjeta por tarjeta: reintenta
# el reconocimiento de todas las que sigan sin verificar, con el motor que
# esté configurado (Automático = IA si hay key, si no Tesseract).
_bulk_state = {"running": False, "total": 0, "done": 0, "errors": 0, "current": None, "message": None}
_bulk_lock = threading.Lock()
_bulk_cancel_event = threading.Event()


def _run_bulk_reprocess():
    global _bulk_state
    _bulk_cancel_event.clear()
    pending = db.list_pending_cards()
    with _bulk_lock:
        _bulk_state.update(running=True, total=len(pending), done=0, errors=0, current=None, message=None)

    if not pending:
        with _bulk_lock:
            _bulk_state.update(running=False, message="No había tarjetas pendientes de revisión.")
        return

    cancelled = False
    for card in pending:
        if _bulk_cancel_event.is_set():
            cancelled = True
            break
        with _bulk_lock:
            _bulk_state["current"] = card.get("callsign") or card.get("filename")

        file_path = BASE_DIR / card["stored_path"]
        if not file_path.exists():
            with _bulk_lock:
                _bulk_state["errors"] += 1
                _bulk_state["done"] += 1
            continue

        try:
            fields = run_extraction(file_path)
            engine_used = fields.pop("engine_used", None)
            preview_img = fields.pop("preview_image", None)
            if preview_img is not None:
                preview_name = f"{Path(card['stored_path']).stem}_preview.jpg"
                preview_path = CARDS_DIR / preview_name
                preview_img.convert("RGB").save(preview_path, "JPEG", quality=88)
                db.update_card(card["id"], {"preview_path": str(preview_path.relative_to(BASE_DIR))})

            country, lat, lon = _resolve_location(fields)
            found_something = bool(fields.get("callsign") or fields.get("qso_date") or fields.get("band"))
            db.update_card(card["id"], {
                "callsign": fields.get("callsign"),
                "country": country,
                "qso_date": fields.get("qso_date"),
                "band": fields.get("band"),
                "mode": fields.get("mode"),
                "rst": fields.get("rst"),
                "locator": fields.get("locator"),
                "lat": lat,
                "lon": lon,
                "ocr_text": fields.get("ocr_text") or "",
                "recognized_by": engine_used,
                "verified": 1 if found_something else 0,
            })
        except Exception as e:
            with _bulk_lock:
                _bulk_state["errors"] += 1
            print(f"[Revisión masiva] Error con tarjeta {card['id']}: {e}")

        with _bulk_lock:
            _bulk_state["done"] += 1

    with _bulk_lock:
        done, errors, total = _bulk_state["done"], _bulk_state["errors"], _bulk_state["total"]
        if cancelled:
            msg = f"Detenido: {done}/{total} revisadas antes de parar."
        else:
            msg = f"Listo: {done}/{total} tarjetas reprocesadas ({errors} con error)."
        _bulk_state.update(running=False, current=None, message=msg)


@app.post("/api/cards/reprocess-all")
def start_bulk_reprocess():
    with _bulk_lock:
        if _bulk_state["running"]:
            raise HTTPException(409, "Ya hay una revisión masiva en curso.")
    thread = threading.Thread(target=_run_bulk_reprocess, daemon=True)
    thread.start()
    return {"started": True}


@app.get("/api/cards/reprocess-all/status")
def get_bulk_reprocess_status():
    with _bulk_lock:
        return dict(_bulk_state)


@app.post("/api/cards/reprocess-all/cancel")
def cancel_bulk_reprocess():
    with _bulk_lock:
        if not _bulk_state["running"]:
            raise HTTPException(400, "No hay ninguna revisión masiva corriendo.")
    _bulk_cancel_event.set()
    return {"cancelling": True}


# --- Ping de uso opcional (telemetría) --------------------------------
# URL del Apps Script propio (no es un dato del usuario -- va fijo acá para
# que nadie tenga que configurar/entender esto ni pueda confundirlo con
# otro campo). Se completa una sola vez, del lado del desarrollador.
TELEMETRY_ENDPOINT = "https://script.google.com/macros/s/AKfycbzdGC47yxvP-lkTjswRrkA42EBqZP6SCNQ8mK0CdgeZOPDfgsg1YdaX9s_4Y7BKV67f/exec"

# Solo se manda si el usuario dejó marcado el consentimiento (viene activo
# por defecto, pero se puede apagar) Y hay indicativo configurado. Nunca
# bloquea el arranque: corre en un hilo aparte y cualquier fallo se ignora.
def _send_telemetry_ping():
    if not TELEMETRY_ENDPOINT:
        return
    cfg = app_config.load_config()
    if not cfg.get("telemetry_opt_in"):
        return
    callsign = cfg.get("owner_callsign", "").strip().upper()
    if not callsign:
        return
    try:
        import requests
        requests.post(
            TELEMETRY_ENDPOINT,
            json={"callsign": callsign, "event": "launch", "version": APP_VERSION},
            timeout=8,
        )
    except Exception:
        pass  # sin internet, endpoint caído, lo que sea -- no debe afectar el uso normal


@app.post("/api/telemetry/ping")
def telemetry_ping():
    threading.Thread(target=_send_telemetry_ping, daemon=True).start()
    return {"ok": True}


@app.get("/api/version")
def get_version():
    return {"version": APP_VERSION}


@app.get("/api/check-update")
def check_update():
    """Consulta el último release publicado en GitHub. Si el repo todavía
    no tiene releases (o no hay internet), no es un error real -- se
    devuelve 'sin novedades' en vez de romper nada."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        import requests
        resp = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=8)
        if resp.status_code == 404:
            return {"update_available": False, "current_version": APP_VERSION, "note": "Sin releases publicados todavía."}
        if not resp.ok:
            return {"update_available": False, "current_version": APP_VERSION, "note": f"GitHub respondió HTTP {resp.status_code}."}
        data = resp.json()
        latest = data.get("tag_name", "")
        html_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
        return {
            "update_available": bool(latest) and latest != APP_VERSION,
            "current_version": APP_VERSION,
            "latest_version": latest,
            "url": html_url,
        }
    except Exception as e:
        return {"update_available": False, "current_version": APP_VERSION, "note": f"No se pudo verificar: {e}"}


# Interfaz web estática (index.html, app.js, style.css)
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
