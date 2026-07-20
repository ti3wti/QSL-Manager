"""
Manejo de la base de datos SQLite para el QSL Manager.
Un solo archivo .db guarda todos los metadatos; las imágenes/PDFs originales
se copian a data/cards/ para que la app no dependa de que el usuario no
mueva/borre la carpeta original.
"""
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "qsl.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS qsl_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    callsign TEXT,
    country TEXT,
    qso_date TEXT,          -- formato YYYY-MM-DD si se pudo detectar
    band TEXT,
    mode TEXT,
    rst TEXT,
    locator TEXT,           -- grid locator, ej. IL18SD
    lat REAL,
    lon REAL,
    ocr_text TEXT,          -- texto crudo detectado por OCR, por si hay que revisar
    verified INTEGER DEFAULT 0,   -- 1 = el usuario confirmó/corrigió los datos
    imported_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_callsign ON qsl_cards(callsign);
CREATE INDEX IF NOT EXISTS idx_country ON qsl_cards(country);
CREATE INDEX IF NOT EXISTS idx_date ON qsl_cards(qso_date);
"""


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    # Migración simple: agregar columnas nuevas si la base ya existía antes
    # de que se agregaran (evita tener que borrar la base de datos).
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(qsl_cards)")}
    if "preview_path" not in existing_cols:
        conn.execute("ALTER TABLE qsl_cards ADD COLUMN preview_path TEXT")
    if "recognized_by" not in existing_cols:
        conn.execute("ALTER TABLE qsl_cards ADD COLUMN recognized_by TEXT")
    if "source_key" not in existing_cols:
        conn.execute("ALTER TABLE qsl_cards ADD COLUMN source_key TEXT")
    conn.commit()
    conn.close()


def insert_card(data: dict) -> int:
    conn = get_connection()
    data = {**data}
    data.setdefault("preview_path", None)
    data.setdefault("recognized_by", None)
    data.setdefault("source_key", None)
    cur = conn.execute(
        """INSERT INTO qsl_cards
           (filename, stored_path, preview_path, callsign, country, qso_date, band, mode,
            rst, locator, lat, lon, ocr_text, verified, imported_at, recognized_by, source_key)
           VALUES (:filename, :stored_path, :preview_path, :callsign, :country, :qso_date,
                   :band, :mode, :rst, :locator, :lat, :lon, :ocr_text,
                   :verified, :imported_at, :recognized_by, :source_key)""",
        {**data, "imported_at": datetime.utcnow().isoformat()},
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def source_key_exists(source_key: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT 1 FROM qsl_cards WHERE source_key = ?", (source_key,)).fetchone()
    conn.close()
    return row is not None


def list_pending_cards() -> list:
    """Tarjetas sin verificar (con o sin error) -- candidatas a un reintento
    masivo de reconocimiento."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM qsl_cards WHERE verified = 0 OR verified IS NULL").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_card(card_id: int, data: dict):
    fields = ", ".join(f"{k} = :{k}" for k in data.keys())
    conn = get_connection()
    conn.execute(f"UPDATE qsl_cards SET {fields} WHERE id = :id",
                 {**data, "id": card_id})
    conn.commit()
    conn.close()


def delete_card(card_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM qsl_cards WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()


def list_cards(country: str = None, callsign: str = None, order_by: str = "qso_date DESC"):
    conn = get_connection()
    query = "SELECT * FROM qsl_cards WHERE 1=1"
    params = []
    if country:
        query += " AND country = ?"
        params.append(country)
    if callsign:
        query += " AND callsign LIKE ?"
        params.append(f"%{callsign}%")
    query += f" ORDER BY {order_by}"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_countries():
    conn = get_connection()
    rows = conn.execute(
        "SELECT country, COUNT(*) as total FROM qsl_cards "
        "WHERE country IS NOT NULL AND country != '' "
        "GROUP BY country ORDER BY country"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_card(card_id: int):
    conn = get_connection()
    row = conn.execute("SELECT * FROM qsl_cards WHERE id = ?", (card_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
