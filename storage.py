"""Datos que Vapora guarda entre reinicios, en una base SQLite (por defecto data/vapora.db).

Tablas:
- guild_channels: canal elegido con /config para cada tipo de aviso de cada servidor.
- sent_announcements: avisos de rebajas ya enviados (para no repetirlos al reiniciar).
- wishlist: deseados de cada usuario y a qué precio se avisó la última oferta.

La primera vez que se crea la base, si existe el JSON viejo (data/state.json), se
importan sus datos y el archivo se renombra a state.json.migrado.
"""

import json
import logging
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

import config

# Tipo de aviso de /config -> clave que usa el resto del bot
CHANNEL_KEYS = {"ofertas": "deals_channel", "rebajas": "sales_channel", "deseados": "wishlist_channel"}
MAX_WISHLIST = 25  # por usuario (también es el máximo de opciones de Discord)

# Cada posición es una versión del esquema. Para cambiarlo, se agrega una nueva al final.
MIGRATIONS = [
    """
    CREATE TABLE guild_channels (
        guild_id    INTEGER NOT NULL,
        feature     TEXT    NOT NULL CHECK (feature IN ('ofertas', 'rebajas', 'deseados')),
        channel_id  INTEGER NOT NULL,
        updated_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (guild_id, feature)
    );
    CREATE TABLE sent_announcements (
        guild_id  INTEGER NOT NULL,
        sale_key  TEXT    NOT NULL,
        kind      TEXT    NOT NULL,
        sent_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (guild_id, sale_key, kind)
    );
    CREATE TABLE wishlist (
        user_id               INTEGER NOT NULL,
        app_id                INTEGER NOT NULL,
        name                  TEXT    NOT NULL,
        guild_id              INTEGER,
        notified_final_cents  INTEGER,
        added_at              TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, app_id)
    );
    CREATE INDEX wishlist_by_app ON wishlist (app_id);
    """,
]

_ready_paths: set[str] = set()


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    """Conexión a la base: confirma los cambios al salir, o los deshace si hubo un error."""
    path = config.DATABASE_FILE
    if path not in _ready_paths:
        _prepare(path)
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            yield conn


def _prepare(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # escrituras más seguras ante cortes
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            with conn:
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {number}")
            logging.info("Base de datos actualizada a la versión %d", number)
        if version == 0:
            _import_legacy_json(conn)
    _ready_paths.add(path)


def _import_legacy_json(conn: sqlite3.Connection) -> None:
    """Pasa los datos del JSON viejo (state.json) a la base, una sola vez."""
    legacy = Path(config.STATE_FILE)
    if not legacy.exists():
        return
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
    except ValueError:
        logging.warning("No pude leer %s: arranco con la base vacía", legacy)
        return
    features = {key: feature for feature, key in CHANNEL_KEYS.items()}
    with conn:
        for guild_id, settings in (data.get("guilds") or {}).items():
            for key, channel_id in settings.items():
                if key in features:
                    conn.execute("INSERT OR IGNORE INTO guild_channels (guild_id, feature, channel_id) "
                                 "VALUES (?, ?, ?)", (int(guild_id), features[key], channel_id))
        for entry in data.get("sent") or []:
            guild_id, rest = entry.split(":", 1)
            sale_key, kind = rest.rsplit(":", 1)
            conn.execute("INSERT OR IGNORE INTO sent_announcements (guild_id, sale_key, kind) VALUES (?, ?, ?)",
                         (int(guild_id), sale_key, kind))
        for user_id, games in (data.get("wishlist") or {}).items():
            for app_id, wish in games.items():
                conn.execute("INSERT OR IGNORE INTO wishlist (user_id, app_id, name, guild_id, notified_final_cents) "
                             "VALUES (?, ?, ?, ?, ?)",
                             (int(user_id), int(app_id), wish["name"], wish.get("guild_id"), wish.get("notified_final")))
    legacy.rename(legacy.with_name(legacy.name + ".migrado"))
    logging.info("Datos de %s importados a la base de datos", legacy)


# ── Canales de /config ────────────────────────────────────────────────────────

def get_guild_settings(guild_id: int) -> dict[str, int]:
    with _db() as conn:
        rows = conn.execute("SELECT feature, channel_id FROM guild_channels WHERE guild_id = ?", (guild_id,))
        return {CHANNEL_KEYS[row["feature"]]: row["channel_id"] for row in rows}


def all_guild_settings() -> dict[int, dict[str, int]]:
    settings: dict[int, dict[str, int]] = {}
    with _db() as conn:
        for row in conn.execute("SELECT guild_id, feature, channel_id FROM guild_channels"):
            settings.setdefault(row["guild_id"], {})[CHANNEL_KEYS[row["feature"]]] = row["channel_id"]
    return settings


def set_channel(guild_id: int, feature: str, channel_id: int | None) -> None:
    """Guarda (o borra, con None) el canal de 'ofertas', 'rebajas' o 'deseados' de un servidor."""
    with _db() as conn:
        if channel_id is None:
            conn.execute("DELETE FROM guild_channels WHERE guild_id = ? AND feature = ?", (guild_id, feature))
        else:
            conn.execute(
                "INSERT INTO guild_channels (guild_id, feature, channel_id) VALUES (?, ?, ?) "
                "ON CONFLICT (guild_id, feature) DO UPDATE "
                "SET channel_id = excluded.channel_id, updated_at = CURRENT_TIMESTAMP",
                (guild_id, feature, channel_id),
            )


# ── Avisos de rebajas enviados ────────────────────────────────────────────────

def sent_announcements(guild_id: int) -> set[str]:
    """Avisos ya enviados en un servidor, como "<rebaja>:<tipo de aviso>"."""
    with _db() as conn:
        rows = conn.execute("SELECT sale_key, kind FROM sent_announcements WHERE guild_id = ?", (guild_id,))
        return {f"{row['sale_key']}:{row['kind']}" for row in rows}


def mark_sent(guild_id: int, sale_key: str, kind: str) -> None:
    with _db() as conn:
        conn.execute("INSERT OR IGNORE INTO sent_announcements (guild_id, sale_key, kind) VALUES (?, ?, ?)",
                     (guild_id, sale_key, kind))


# ── Deseados ──────────────────────────────────────────────────────────────────

def _wish(row: sqlite3.Row) -> dict:
    return {"name": row["name"], "guild_id": row["guild_id"], "notified_final": row["notified_final_cents"]}


def get_wishlist(user_id: int) -> dict[int, dict]:
    with _db() as conn:
        rows = conn.execute("SELECT * FROM wishlist WHERE user_id = ? ORDER BY added_at, app_id", (user_id,))
        return {row["app_id"]: _wish(row) for row in rows}


def all_wishlists() -> dict[int, dict[int, dict]]:
    wishlists: dict[int, dict[int, dict]] = {}
    with _db() as conn:
        for row in conn.execute("SELECT * FROM wishlist ORDER BY user_id, added_at, app_id"):
            wishlists.setdefault(row["user_id"], {})[row["app_id"]] = _wish(row)
    return wishlists


def add_wish(user_id: int, app_id: int, name: str, guild_id: int | None,
             notified_final: int | None = None) -> bool:
    """Agrega un juego. Devuelve False si ya estaba o si la lista está llena."""
    with _db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM wishlist WHERE user_id = ?", (user_id,)).fetchone()[0]
        if count >= MAX_WISHLIST:
            return False
        cursor = conn.execute(
            "INSERT OR IGNORE INTO wishlist (user_id, app_id, name, guild_id, notified_final_cents) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, app_id, name, guild_id, notified_final),
        )
        return cursor.rowcount == 1


def remove_wish(user_id: int, app_id: int) -> str | None:
    """Quita un juego. Devuelve su nombre, o None si no estaba."""
    with _db() as conn:
        row = conn.execute("SELECT name FROM wishlist WHERE user_id = ? AND app_id = ?",
                           (user_id, app_id)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM wishlist WHERE user_id = ? AND app_id = ?", (user_id, app_id))
        return row["name"]


def set_wish_notified(user_id: int, app_id: int, notified_final: int | None) -> None:
    """Guarda a qué precio se avisó la oferta (None = sin oferta activa avisada)."""
    with _db() as conn:
        conn.execute("UPDATE wishlist SET notified_final_cents = ? WHERE user_id = ? AND app_id = ?",
                     (notified_final, user_id, app_id))
