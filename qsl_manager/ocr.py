"""
OCR y parseo de campos de una tarjeta QSL (imagen o PDF).

Estrategia para PDF:
1. Se intenta extraer texto nativo del PDF (más confiable cuando existe).
2. Si el texto nativo es muy corto/poco útil (< MIN_NATIVE_TEXT_CHARS,
   típico de PDFs "de diseño" donde el texto quedó convertido a curvas/
   imagen), se rasteriza la página a alta resolución y se aplica OCR.
3. Además, siempre se genera una versión "recortada" de la página (se
   quita el margen en blanco/vacío alrededor de la tarjeta) para usarla
   como vista previa en la interfaz -- muchas QSL en PDF ocupan solo una
   fracción de la hoja, y sin recorte la vista previa queda ilegible.

El OCR es un punto de partida, NO la verdad absoluta: el usuario revisa y
corrige los campos en la interfaz antes de guardar (o después, editando).
Por eso existe también `force_ocr`: permite reprocesar una tarjeta ya
importada ignorando el texto nativo, por si esa vía dio resultados peores.
"""
import io
import re
import tempfile
import time
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps
import fitz  # PyMuPDF

from .locator import find_locator
from . import config as app_config
from .paths import BASE_DIR, RESOURCE_DIR

# pytesseract escribe archivos temporales (la imagen a leer, el resultado)
# usando la carpeta TEMP del sistema. En Windows, esa carpeta a veces está
# bajo vigilancia pesada del antivirus o redirigida a OneDrive, lo que
# produce errores tipo "[WinError 5] Acceso denegado" al intentar leer o
# borrar esos archivos justo después de crearlos. Usamos una carpeta
# propia dentro del proyecto en su lugar -- ya sabemos que la app puede
# escribir ahí sin problema porque es donde guarda las QSLs importadas.
_TESS_TMP_DIR = BASE_DIR / "data" / "tmp"
_TESS_TMP_DIR.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_TESS_TMP_DIR)

# --- Reintentos para tesseract ---------------------------------------
# En Windows, procesar muchos archivos seguidos puede chocar con el
# antivirus/Explorer bloqueando momentáneamente los archivos temporales
# que pytesseract crea (error típico: "PermissionError [WinError 32]").
# Es transitorio: reintentar con una pequeña pausa casi siempre lo resuelve.
# OJO: esto NO ayuda si el error es "tesseract is not installed or it's
# not in your PATH" -- ese es un problema real de configuración, no
# transitorio. Para eso existe tesseract_path en Configuración.
OCR_RETRIES = 3
OCR_RETRY_DELAY_SECONDS = 0.6


# tesseract-bin/ es un recurso empaquetado de solo lectura: si el .exe lo
# trae incluido, PyInstaller lo descomprime en RESOURCE_DIR (temporal),
# no junto al .exe -- pero como solo se lee (nunca se escribe ahí), no
# hay problema de persistencia.
BUNDLED_TESSERACT_DIR = RESOURCE_DIR / "tesseract-bin"


def bundled_tesseract_exe() -> Path | None:
    """Si alguien (típicamente vos, antes de compartir la app) empaquetó
    Tesseract dentro del proyecto con 'Preparar para compartir', esta es
    la ruta. Así un colega no necesita instalar ni configurar nada."""
    exe = BUNDLED_TESSERACT_DIR / "tesseract.exe"
    return exe if exe.exists() else None


def _configure_tesseract_path():
    """Orden de prioridad para encontrar tesseract.exe:
    1. Ruta puesta a mano en Configuración (por si el usuario prefiere
       su propia instalación).
    2. Tesseract empaquetado dentro del proyecto (tesseract-bin/), para
       que compartir la app no requiera que cada persona lo instale.
    3. Lo que pytesseract encuentre solo (PATH del sistema)."""
    tpath = app_config.load_config().get("tesseract_path", "").strip()
    if tpath:
        pytesseract.pytesseract.tesseract_cmd = tpath
        return
    bundled = bundled_tesseract_exe()
    if bundled:
        pytesseract.pytesseract.tesseract_cmd = str(bundled)


def _ocr_image_to_string(img: Image.Image, lang: str = "eng") -> str:
    _configure_tesseract_path()
    last_error = None
    for attempt in range(OCR_RETRIES):
        try:
            return pytesseract.image_to_string(img, lang=lang)
        except Exception as e:
            last_error = e
            time.sleep(OCR_RETRY_DELAY_SECONDS)
    raise RuntimeError(
        f"Tesseract falló {OCR_RETRIES} veces seguidas ({last_error}). "
        f"Si el mensaje dice 'not in your PATH', configura la ruta exacta "
        f"de tesseract.exe en ⚙ Configuración. Si el mensaje es otro y se "
        f"repite mucho en Windows, suele ser el antivirus bloqueando "
        f"archivos temporales."
    ) from last_error

# Indicativo propio del usuario: se excluye al buscar "el otro" indicativo
# en la tarjeta (porque casi siempre aparece como "QSO WITH: TI3WTI").
# Indicativo del dueño de esta instalación: se excluye al buscar "el otro"
# indicativo en la tarjeta (porque casi siempre aparece como "QSO WITH:
# <el mío>"). Ya NO está fijo en el código -- se configura una vez al
# inicio (ver owner_callsign en Configuración), para que esta app sirva
# para cualquier radioaficionado, no solo para quien la escribió.
def my_callsign() -> str:
    return app_config.load_config().get("owner_callsign", "").strip().upper()

# Un indicativo de radioaficionado: cubre los dos formatos de prefijo más
# comunes -- letras+dígito+letras (EA3HMZ, LW3DFA, TI3WTI) y dígito+letra+
# dígito+letras (5B4AMM, 4X4ABC, 9V1AB) -- este último es habitual en
# muchos países (Chipre, Israel, Singapur, Guatemala especial, etc.) y
# antes se estaba perdiendo por completo.
CALLSIGN_RE = re.compile(
    r"\b([A-Z]{1,2}\d[A-Z]{1,4}|\d[A-Z]\d[A-Z]{1,4})\b"
)

DATE_PATTERNS = [
    re.compile(r"\b(\d{4}-\d{1,2}-\d{1,2})\b"),        # 2026-07-11
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b"),          # 11/07/2026 o 5/9/2021
]

BAND_RE = re.compile(r"\b(\d+(?:\.\d+)?\s?(?:CM|M|MHZ))\b", re.IGNORECASE)
MODE_RE = re.compile(r"\b(SSB|CW|FM|PKT|DIG\s?VOI|FT8|RTTY|AM|PSK31|SSTV)\b", re.IGNORECASE)
RST_RE = re.compile(r"\bRST[:\s]*([0-9]{2,3})\b", re.IGNORECASE)

MIN_NATIVE_TEXT_CHARS = 30
RENDER_DPI = 300
CROP_PADDING_PX = 25


def _normalize_date(raw: str) -> str:
    """Convierte a formato YYYY-MM-DD, aceptando día/mes de 1 o 2 dígitos."""
    if "-" in raw:
        parts = raw.split("-")
    else:
        d, m, y = raw.split("/")
        parts = [y, m, d]
    y, m, d = parts
    return f"{y}-{int(m):02d}-{int(d):02d}"


def _crop_to_content(img: Image.Image) -> Image.Image:
    """Recorta el margen vacío/blanco alrededor del contenido real.

    Muchas QSL en PDF traen la tarjeta centrada en una hoja mucho más
    grande (o con fondo de color parejo). Esto detecta el área con
    variación de contenido y recorta a eso + un margen chico.
    """
    gray = ImageOps.grayscale(img)
    # Normalizar contraste ayuda cuando el fondo no es blanco puro
    gray = ImageOps.autocontrast(gray, cutoff=2)
    # Invertir para que el contenido (no el fondo) sea lo "brillante"
    inverted = ImageOps.invert(gray)
    bbox = inverted.point(lambda p: 255 if p > 18 else 0).getbbox()
    if not bbox:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - CROP_PADDING_PX)
    top = max(0, top - CROP_PADDING_PX)
    right = min(img.width, right + CROP_PADDING_PX)
    bottom = min(img.height, bottom + CROP_PADDING_PX)
    # Si el bbox es casi toda la imagen, no vale la pena recortar
    area_ratio = ((right - left) * (bottom - top)) / (img.width * img.height)
    if area_ratio > 0.97:
        return img
    return img.crop((left, top, right, bottom))


def render_pdf_page(pdf_path: Path, page_index: int = 0, dpi: int = RENDER_DPI) -> Image.Image:
    """Rasteriza una página del PDF a imagen PIL (sin recortar)."""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        pix = page.get_pixmap(dpi=dpi)
        return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    finally:
        doc.close()


def render_pdf_preview(pdf_path: Path, page_index: int = 0) -> Image.Image:
    """Imagen recortada al contenido real, para usar como vista previa/OCR."""
    full = render_pdf_page(pdf_path, page_index)
    return _crop_to_content(full)


def extract_text_from_image(image_path: Path) -> str:
    try:
        img = Image.open(image_path)
        img.load()  # fuerza la lectura completa ahora, no perezosa
    except Exception as e:
        raise ValueError(
            f"El archivo no se pudo leer como imagen (¿dañado o no es "
            f"realmente ese formato pese a la extensión?): {e}"
        ) from e
    return _ocr_image_to_string(img)


def extract_text_from_pdf(pdf_path: Path, force_ocr: bool = False):
    """Devuelve (texto, imagen_recortada_primera_pagina)."""
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    doc.close()

    preview_img = render_pdf_preview(pdf_path, 0) if num_pages else None

    text_parts = []
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        native_text = "" if force_ocr else page.get_text().strip()
        if len(native_text) >= MIN_NATIVE_TEXT_CHARS:
            text_parts.append(native_text)
        else:
            # Texto nativo ausente o insuficiente: usar la imagen recortada
            # en la primera página (ya la tenemos) y rasterizar el resto.
            img = preview_img if i == 0 else _crop_to_content(render_pdf_page(pdf_path, i))
            text_parts.append(_ocr_image_to_string(img))
    doc.close()
    return "\n".join(text_parts), preview_img


def extract_text(file_path: Path, force_ocr: bool = False):
    """Devuelve (texto, imagen_preview_o_None). imagen_preview solo aplica a PDF."""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(file_path, force_ocr=force_ocr)
    elif suffix in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
        text = extract_text_from_image(file_path)
        return text, None
    else:
        raise ValueError(f"Tipo de archivo no soportado: {suffix}")


def parse_fields(text: str) -> dict:
    """Extrae campos estructurados del texto OCR crudo."""
    upper_text = text.upper()

    # Indicativo: tomar todos los candidatos y descartar el propio.
    my_call = my_callsign()
    candidates = [c for c in CALLSIGN_RE.findall(upper_text) if c != my_call]
    callsign = candidates[0] if candidates else None

    date = None
    for pattern in DATE_PATTERNS:
        m = pattern.search(text)
        if m:
            date = _normalize_date(m.group(1))
            break

    band_match = BAND_RE.search(upper_text)
    mode_match = MODE_RE.search(upper_text)
    rst_match = RST_RE.search(upper_text)
    locator = find_locator(upper_text)

    return {
        "callsign": callsign,
        "qso_date": date,
        "band": band_match.group(1).strip() if band_match else None,
        "mode": mode_match.group(1).strip() if mode_match else None,
        "rst": rst_match.group(1) if rst_match else None,
        "locator": locator,
        "ocr_text": text.strip(),
    }


def process_file(file_path: Path, force_ocr: bool = False) -> dict:
    """Devuelve los campos parseados + (para PDF) la imagen de vista previa."""
    text, preview_img = extract_text(file_path, force_ocr=force_ocr)
    fields = parse_fields(text)
    fields["preview_image"] = preview_img
    return fields
