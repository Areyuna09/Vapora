"""Datos que Vapora guarda entre reinicios, en una base SQLite.

Tablas:
- guild_channels: canal elegido con /config para cada tipo de aviso de cada servidor.
- sent_announcements: avisos de rebajas ya enviados (para no repetirlos al reiniciar).
- wishlist: deseados de cada usuario y a qué precio se avisó la última oferta.
- daily_posts: último día en que se hizo cada publicación diaria (como las ofertas destacadas)
  en cada servidor.

Las consultas de SQLite son bloqueantes, así que cada operación corre en un hilo aparte
(`asyncio.to_thread`) para no frenar al bot mientras se lee o escribe el disco.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date
from enum import Enum, StrEnum
from pathlib import Path
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

MAX_WISHLIST_SIZE = 25  # por usuario (también es el máximo de opciones que muestra Discord)


class Feature(StrEnum):
    """Tipos de aviso que se configuran con /config. El valor es el que se guarda en la base."""

    DEALS = "ofertas"
    SALES = "rebajas"
    WISHLIST = "deseados"
    WALLPAPERS = "fondos"


class AddWishResult(Enum):
    ADDED = "added"
    ALREADY_THERE = "already_there"
    LIST_FULL = "list_full"


@dataclass(frozen=True, slots=True)
class Wish:
    """Un juego en la lista de deseados de alguien."""

    user_id: int
    app_id: int
    name: str
    guild_id: int | None  # servidor donde lo agregó: define en qué canal se le avisa
    notified_final_cents: int | None  # precio al que ya se avisó la oferta (None = sin aviso)

    @property
    def on_sale(self) -> bool:
        return self.notified_final_cents is not None


# Cada posición es una versión del esquema. Para cambiarlo, se agrega una nueva al final.
MIGRATIONS: tuple[str, ...] = (
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
    # v2: qué día se hizo cada publicación diaria (como las ofertas) en cada servidor.
    """
    CREATE TABLE daily_posts (
        guild_id     INTEGER NOT NULL,
        feature      TEXT    NOT NULL,
        last_posted  TEXT    NOT NULL,  -- fecha (Argentina) en formato ISO: 2026-10-05
        PRIMARY KEY (guild_id, feature)
    );
    """,
    # v3: suma el tipo de aviso 'fondos'. SQLite no deja cambiar un CHECK, así que se rehace
    # la tabla con los mismos datos. Para deshacerlo alcanza con borrar las filas 'fondos':
    # las versiones anteriores del bot ignoran los tipos que no conocen.
    """
    CREATE TABLE guild_channels_v3 (
        guild_id    INTEGER NOT NULL,
        feature     TEXT    NOT NULL CHECK (feature IN ('ofertas', 'rebajas', 'deseados', 'fondos')),
        channel_id  INTEGER NOT NULL,
        updated_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (guild_id, feature)
    );
    INSERT INTO guild_channels_v3 (guild_id, feature, channel_id, updated_at)
        SELECT guild_id, feature, channel_id, updated_at FROM guild_channels;
    DROP TABLE guild_channels;
    ALTER TABLE guild_channels_v3 RENAME TO guild_channels;
    """,
)

# Claves que usaba el JSON anterior a la base de datos.
_LEGACY_CHANNEL_KEYS = {
    "deals_channel": Feature.DEALS,
    "sales_channel": Feature.SALES,
    "wishlist_channel": Feature.WISHLIST,
}


class Database:
    """Acceso a la base de datos de Vapora.

    Args:
        path: archivo SQLite; se crea (con sus tablas) si no existe.
        legacy_json: `state.json` de versiones anteriores. Si existe al crear la base,
            se importa una sola vez y se renombra a `state.json.migrado`.
    """

    def __init__(self, path: Path | str, legacy_json: Path | str | None = None) -> None:
        self._path = Path(path)
        self._legacy_json = Path(legacy_json) if legacy_json else None
        self._ready = False
        self._setup_lock = threading.Lock()

    async def setup(self) -> None:
        """Crea o actualiza las tablas. Es opcional: la primera consulta también lo hace."""
        await asyncio.to_thread(self._ensure_ready)

    # ── Canales de /config ────────────────────────────────────────────────────

    async def channels(self, guild_id: int) -> dict[Feature, int]:
        """Canal configurado para cada tipo de aviso de un servidor.

        Ignora los tipos que esta versión no conoce (por ejemplo, si se volvió a una versión
        anterior del bot después de que alguien configurara un tipo nuevo).
        """

        def query(conn: sqlite3.Connection) -> dict[Feature, int]:
            rows = conn.execute(
                "SELECT feature, channel_id FROM guild_channels WHERE guild_id = ?", (guild_id,)
            )
            known = {feature.value for feature in Feature}
            return {Feature(row["feature"]): row["channel_id"] for row in rows if row["feature"] in known}

        return await self._run(query)

    async def channels_for(self, feature: Feature) -> dict[int, int]:
        """Servidores que configuraron ese tipo de aviso, con su canal: {servidor: canal}."""

        def query(conn: sqlite3.Connection) -> dict[int, int]:
            rows = conn.execute(
                "SELECT guild_id, channel_id FROM guild_channels WHERE feature = ?", (feature,)
            )
            return {row["guild_id"]: row["channel_id"] for row in rows}

        return await self._run(query)

    async def set_channel(self, guild_id: int, feature: Feature, channel_id: int | None) -> None:
        """Guarda el canal de un tipo de aviso, o lo desactiva si `channel_id` es `None`."""

        def query(conn: sqlite3.Connection) -> None:
            if channel_id is None:
                conn.execute(
                    "DELETE FROM guild_channels WHERE guild_id = ? AND feature = ?", (guild_id, feature)
                )
                return
            conn.execute(
                "INSERT INTO guild_channels (guild_id, feature, channel_id) VALUES (?, ?, ?) "
                "ON CONFLICT (guild_id, feature) DO UPDATE "
                "SET channel_id = excluded.channel_id, updated_at = CURRENT_TIMESTAMP",
                (guild_id, feature, channel_id),
            )

        await self._run(query)

    # ── Avisos de rebajas enviados ────────────────────────────────────────────

    async def sent_notices(self, guild_id: int) -> set[tuple[str, str]]:
        """Avisos de rebajas ya enviados en un servidor, como pares (clave de la rebaja, aviso)."""

        def query(conn: sqlite3.Connection) -> set[tuple[str, str]]:
            rows = conn.execute(
                "SELECT sale_key, kind FROM sent_announcements WHERE guild_id = ?", (guild_id,)
            )
            return {(row["sale_key"], row["kind"]) for row in rows}

        return await self._run(query)

    async def mark_notice_sent(self, guild_id: int, sale_key: str, notice: str) -> None:
        def query(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR IGNORE INTO sent_announcements (guild_id, sale_key, kind) VALUES (?, ?, ?)",
                (guild_id, sale_key, notice),
            )

        await self._run(query)

    # ── Publicaciones diarias ─────────────────────────────────────────────────

    async def guilds_posted_on(self, feature: Feature, day: date) -> set[int]:
        """Servidores donde ya se hizo la publicación diaria de ese tipo, ese día."""

        def query(conn: sqlite3.Connection) -> set[int]:
            rows = conn.execute(
                "SELECT guild_id FROM daily_posts WHERE feature = ? AND last_posted = ?",
                (feature, day.isoformat()),
            )
            return {row["guild_id"] for row in rows}

        return await self._run(query)

    async def mark_posted(self, guild_id: int, feature: Feature, day: date) -> None:
        def query(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO daily_posts (guild_id, feature, last_posted) VALUES (?, ?, ?) "
                "ON CONFLICT (guild_id, feature) DO UPDATE SET last_posted = excluded.last_posted",
                (guild_id, feature, day.isoformat()),
            )

        await self._run(query)

    # ── Deseados ──────────────────────────────────────────────────────────────

    async def wishlist(self, user_id: int) -> list[Wish]:
        """Deseados de un usuario, en el orden en que los agregó."""

        def query(conn: sqlite3.Connection) -> list[Wish]:
            rows = conn.execute(
                "SELECT * FROM wishlist WHERE user_id = ? ORDER BY added_at, rowid", (user_id,)
            )
            return [_wish(row) for row in rows]

        return await self._run(query)

    async def all_wishes(self) -> list[Wish]:
        def query(conn: sqlite3.Connection) -> list[Wish]:
            return [
                _wish(row) for row in conn.execute("SELECT * FROM wishlist ORDER BY user_id, added_at, rowid")
            ]

        return await self._run(query)

    async def add_wish(
        self,
        user_id: int,
        app_id: int,
        name: str,
        guild_id: int | None,
        notified_final_cents: int | None = None,
    ) -> AddWishResult:
        def query(conn: sqlite3.Connection) -> AddWishResult:
            # Bloquea la escritura desde ahora: si no, dos agregados a la vez podrían contar
            # la misma cantidad y pasarse juntos del límite.
            conn.execute("BEGIN IMMEDIATE")
            owned = {
                row["app_id"]
                for row in conn.execute("SELECT app_id FROM wishlist WHERE user_id = ?", (user_id,))
            }
            if app_id in owned:
                return AddWishResult.ALREADY_THERE
            if len(owned) >= MAX_WISHLIST_SIZE:
                return AddWishResult.LIST_FULL
            conn.execute(
                "INSERT INTO wishlist (user_id, app_id, name, guild_id, notified_final_cents) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, app_id, name, guild_id, notified_final_cents),
            )
            return AddWishResult.ADDED

        return await self._run(query)

    async def remove_wish(self, user_id: int, app_id: int) -> str | None:
        """Quita un juego. Devuelve su nombre, o `None` si no estaba en la lista."""

        def query(conn: sqlite3.Connection) -> str | None:
            row = conn.execute(
                "SELECT name FROM wishlist WHERE user_id = ? AND app_id = ?", (user_id, app_id)
            ).fetchone()
            if row is None:
                return None
            conn.execute("DELETE FROM wishlist WHERE user_id = ? AND app_id = ?", (user_id, app_id))
            return str(row["name"])

        return await self._run(query)

    async def set_wish_notified(self, user_id: int, app_id: int, notified_final_cents: int | None) -> None:
        """Guarda a qué precio se avisó la oferta (`None` = no hay oferta avisada)."""

        def query(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE wishlist SET notified_final_cents = ? WHERE user_id = ? AND app_id = ?",
                (notified_final_cents, user_id, app_id),
            )

        await self._run(query)

    # ── Conexión y esquema ────────────────────────────────────────────────────

    async def _run(self, query: Callable[[sqlite3.Connection], T]) -> T:
        """Ejecuta `query` en un hilo, dentro de una transacción."""

        def work() -> T:
            self._ensure_ready()
            with self._connect() as conn:
                return query(conn)

        return await asyncio.to_thread(work)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Conexión que confirma los cambios al salir, o los deshace si hubo un error."""
        with closing(sqlite3.connect(self._path)) as conn:
            conn.row_factory = sqlite3.Row
            with conn:
                yield conn

    def _ensure_ready(self) -> None:
        with self._setup_lock:
            if self._ready:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self._path)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")  # escrituras más seguras ante cortes
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
                    # executescript no abre una transacción por su cuenta: se la abre acá para
                    # que la migración y el cambio de versión se apliquen enteros o nada (si se
                    # corta a la mitad, la conexión se cierra y SQLite deshace todo).
                    with conn:
                        conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
                    log.info("Base de datos actualizada a la versión %d", number)
                if version == 0:
                    self._import_legacy_json(conn)
            self._ready = True

    def _import_legacy_json(self, conn: sqlite3.Connection) -> None:
        """Pasa a la base los datos del JSON que se usaba antes, una sola vez."""
        legacy = self._legacy_json
        if legacy is None or not legacy.exists():
            return
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
        except ValueError:
            log.warning("No pude leer %s: arranco con la base vacía", legacy)
            return
        with conn:
            for guild_id, settings in (data.get("guilds") or {}).items():
                for key, channel_id in settings.items():
                    if key in _LEGACY_CHANNEL_KEYS:
                        conn.execute(
                            "INSERT OR IGNORE INTO guild_channels (guild_id, feature, channel_id) "
                            "VALUES (?, ?, ?)",
                            (int(guild_id), _LEGACY_CHANNEL_KEYS[key], channel_id),
                        )
            for entry in data.get("sent") or []:
                guild_id, rest = entry.split(":", 1)
                sale_key, kind = rest.rsplit(":", 1)
                conn.execute(
                    "INSERT OR IGNORE INTO sent_announcements (guild_id, sale_key, kind) VALUES (?, ?, ?)",
                    (int(guild_id), sale_key, kind),
                )
            for user_id, games in (data.get("wishlist") or {}).items():
                for app_id, wish in games.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO wishlist "
                        "(user_id, app_id, name, guild_id, notified_final_cents) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            int(user_id),
                            int(app_id),
                            wish["name"],
                            wish.get("guild_id"),
                            wish.get("notified_final"),
                        ),
                    )
        legacy.rename(legacy.with_name(legacy.name + ".migrado"))
        log.info("Datos de %s importados a la base de datos", legacy)


def _wish(row: sqlite3.Row) -> Wish:
    return Wish(row["user_id"], row["app_id"], row["name"], row["guild_id"], row["notified_final_cents"])
