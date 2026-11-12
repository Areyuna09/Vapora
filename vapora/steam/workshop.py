"""Workshop de Steam: fondos de Wallpaper Engine (los que son tendencia y sus datos) y mods
de cualquier otro juego.

Steam no ofrece sin API key una búsqueda del Workshop, así que la lista de tendencias se
lee de la página pública (filtrada por categoría y para todo público). Los datos de cada
fondo sí salen de una API pública. Solo se muestran fondos aptos para todo público
(etiqueta "Everyone"): Wallpaper Engine tiene mucho contenido para adultos.

Los mods de otros juegos se muestran todos: no tienen esa clasificación.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import aiohttp

from vapora.cache import TTLCache
from vapora.steam.client import SteamError
from vapora.steam.models import STORE_URL

log = logging.getLogger(__name__)

WALLPAPER_ENGINE_APP_ID = 431960
WALLPAPER_ENGINE_STORE_URL = f"{STORE_URL}/app/{WALLPAPER_ENGINE_APP_ID}/"
WORKSHOP_BROWSE_URL = "https://steamcommunity.com/workshop/browse/"
WORKSHOP_ITEM_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={id}"
FILE_DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

SAFE_TAG = "Everyone"  # clasificación "para todo público" de Wallpaper Engine
TRENDING_TTL_SECONDS = 6 * 60 * 60
WORKSHOP_ITEM_TTL_SECONDS = 60 * 60
TRENDING_DAYS = "7"  # tendencias de la última semana

# Categorías que se pueden pedir: clave del comando -> (texto para mostrar, etiqueta del Workshop).
CATEGORIES: dict[str, tuple[str, str]] = {
    "anime": ("🌸 Anime", "Anime"),
    "paisaje": ("🏞️ Paisaje", "Landscape"),
    "naturaleza": ("🌿 Naturaleza", "Nature"),
    "juegos": ("🎮 Juegos", "Game"),
    "fantasia": ("🐉 Fantasía", "Fantasy"),
    "ciencia_ficcion": ("🚀 Ciencia ficción", "Sci-Fi"),
    "cyberpunk": ("🌃 Cyberpunk", "Cyberpunk"),
    "pixel_art": ("👾 Pixel art", "Pixel art"),
    "abstracto": ("🌀 Abstracto", "Abstract"),
    "relajante": ("😌 Relajante", "Relaxing"),
    "vehiculos": ("🏎️ Vehículos", "Vehicle"),
    "animales": ("🐾 Animales", "Animal"),
}

# Etiquetas del Workshop en castellano, para la tarjeta.
_GENRE_NAMES = {tag: label.split(" ", 1)[1] for label, tag in CATEGORIES.values()} | {
    "Cartoon": "Dibujos",
    "CGI": "CGI",
    "Girls": "Chicas",
    "Guys": "Chicos",
    "Medieval": "Medieval",
    "Memes": "Memes",
    "MMD": "MMD",
    "Music": "Música",
    "Retro": "Retro",
    "Sports": "Deportes",
    "Technology": "Tecnología",
    "Television": "TV",
}
_KIND_NAMES = {"Scene": "Escena", "Video": "Video", "Web": "Web", "Application": "Aplicación"}
_FEATURE_NAMES = {
    "Audio responsive": "🔊 Reacciona al audio",
    "Customizable": "⚙️ Personalizable",
    "Approved": "✅ Aprobado por Wallpaper Engine",
}
_RESOLUTION_RE = re.compile(r"^\d{3,5} x \d{3,5}$")

# Links de un ítem del Workshop: /sharedfiles/filedetails/?id=... o /workshop/filedetails/?id=...
WORKSHOP_LINK_RE = re.compile(
    r"https?://steamcommunity\.com/(?:sharedfiles|workshop)/filedetails/\?(?:[^\s<>]*?&)?id=(\d+)",
    re.IGNORECASE,
)
_BROWSE_ID_RE = re.compile(r"filedetails/\?id=(\d+)")


@dataclass(frozen=True, slots=True)
class Wallpaper:
    """Un fondo de Wallpaper Engine apto para todo público."""

    id: int
    title: str
    preview_url: str | None = None
    tags: tuple[str, ...] = ()
    subscriptions: int = 0
    favorites: int = 0

    @property
    def url(self) -> str:
        return WORKSHOP_ITEM_URL.format(id=self.id)

    @property
    def genres(self) -> tuple[str, ...]:
        """Categorías en castellano (Anime, Paisaje…)."""
        return tuple(_GENRE_NAMES[tag] for tag in self.tags if tag in _GENRE_NAMES)

    @property
    def kind(self) -> str | None:
        """Tipo de fondo: Escena, Video, Web o Aplicación."""
        return next((_KIND_NAMES[tag] for tag in self.tags if tag in _KIND_NAMES), None)

    @property
    def resolution(self) -> str | None:
        return next((tag for tag in self.tags if _RESOLUTION_RE.match(tag)), None)

    @property
    def features(self) -> tuple[str, ...]:
        """Detalles que suman: si reacciona al audio, si se puede personalizar…"""
        return tuple(_FEATURE_NAMES[tag] for tag in self.tags if tag in _FEATURE_NAMES)


@dataclass(frozen=True, slots=True)
class WorkshopMod:
    """Un mod (o una colección) del Workshop de un juego que no es Wallpaper Engine."""

    id: int
    app_id: int  # juego al que pertenece
    title: str
    preview_url: str | None = None
    tags: tuple[str, ...] = ()
    subscriptions: int = 0
    favorites: int = 0
    file_size: int = 0  # bytes; 0 si Steam no lo informa (por ejemplo, en una colección)
    updated_at: int | None = None  # segundos desde epoch

    @property
    def url(self) -> str:
        return WORKSHOP_ITEM_URL.format(id=self.id)


WorkshopItem = Wallpaper | WorkshopMod


def extract_workshop_ids(text: str) -> list[int]:
    """IDs de los ítems del Workshop enlazados en el texto, sin repetir y en orden."""
    return list(dict.fromkeys(int(item_id) for item_id in WORKSHOP_LINK_RE.findall(text)))


# ── Parsers ───────────────────────────────────────────────────────────────────


def parse_browse_ids(page_html: str) -> list[int]:
    """IDs de los ítems que lista una página del Workshop, en el orden en que aparecen."""
    return list(dict.fromkeys(int(item_id) for item_id in _BROWSE_ID_RE.findall(page_html)))


def parse_wallpapers(payload: Any) -> list[Wallpaper]:
    """Fondos de `GetPublishedFileDetails`, descartando los que no se deben mostrar.

    Quedan afuera los que no existen, los ocultos o bloqueados, los que no son de
    Wallpaper Engine y los que no son para todo público.
    """
    return [item for item in parse_workshop_items(payload) if isinstance(item, Wallpaper)]


def parse_workshop_items(payload: Any) -> list[WorkshopItem]:
    """Fondos y mods de `GetPublishedFileDetails`, descartando los que no se deben mostrar.

    Quedan afuera los que no existen, los ocultos o bloqueados y los fondos que no son para
    todo público.
    """
    response = payload.get("response") if isinstance(payload, dict) else None
    details = response.get("publishedfiledetails") if isinstance(response, dict) else None
    items: list[WorkshopItem] = []
    for entry in details if isinstance(details, list) else []:
        if isinstance(entry, dict) and _is_public(entry):
            item = _parse_item(entry)
            if item is not None:
                items.append(item)
    return items


def _parse_item(entry: dict[str, Any]) -> WorkshopItem | None:
    item_id = int(entry["publishedfileid"])
    tags = _tags(entry)
    preview_url = entry.get("preview_url") or None
    subscriptions, favorites = _int(entry.get("subscriptions")), _int(entry.get("favorited"))
    app_id = entry.get("consumer_app_id")
    if app_id == WALLPAPER_ENGINE_APP_ID:
        if SAFE_TAG not in tags:
            return None
        title = str(entry.get("title") or f"Fondo {item_id}")
        return Wallpaper(item_id, title, preview_url, tags, subscriptions, favorites)
    if not isinstance(app_id, int):
        return None
    return WorkshopMod(
        id=item_id,
        app_id=app_id,
        title=str(entry.get("title") or f"Mod {item_id}"),
        preview_url=preview_url,
        tags=tags,
        subscriptions=subscriptions,
        favorites=favorites,
        file_size=_int(entry.get("file_size")),
        updated_at=_int(entry.get("time_updated")) or None,
    )


def _int(value: Any) -> int:
    """Número de la respuesta de Steam (a veces viene como texto); 0 si no es un número."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _tags(entry: dict[str, Any]) -> tuple[str, ...]:
    raw = entry.get("tags")
    return (
        tuple(str(tag["tag"]) for tag in raw if isinstance(tag, dict) and tag.get("tag"))
        if isinstance(raw, list)
        else ()
    )


def _is_public(entry: dict[str, Any]) -> bool:
    return (
        entry.get("result") == 1
        and str(entry.get("publishedfileid", "")).isdigit()
        and not entry.get("banned")
        and entry.get("visibility", 0) == 0  # 0 = público
    )


# ── Cliente ───────────────────────────────────────────────────────────────────


class WorkshopClient:
    """Consultas al Workshop de Steam (fondos de Wallpaper Engine y mods), con caché."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._trending: TTLCache[str, tuple[Wallpaper, ...]] = TTLCache(TRENDING_TTL_SECONDS)
        self._items: TTLCache[int, WorkshopItem | None] = TTLCache(WORKSHOP_ITEM_TTL_SECONDS)

    async def trending(self, category: str | None = None) -> Sequence[Wallpaper]:
        """Fondos en tendencia esta semana, de una categoría (clave de `CATEGORIES`) o de todas.

        Raises:
            SteamError: si Steam no responde.
            KeyError: si la categoría no existe.
        """
        tag = CATEGORIES[category][1] if category else None
        return await self._trending.get_or_fetch(category or "", lambda: self._fetch_trending(tag))

    async def get(self, wallpaper_id: int) -> Wallpaper | None:
        """Un fondo por su ID. `None` si no existe, no es un fondo o no se puede mostrar (+18).

        Raises:
            SteamError: si Steam no responde.
        """
        item = await self.get_item(wallpaper_id)
        return item if isinstance(item, Wallpaper) else None

    async def get_item(self, item_id: int) -> WorkshopItem | None:
        """Un fondo o un mod por su ID. `None` si no existe o no se puede mostrar.

        Raises:
            SteamError: si Steam no responde.
        """
        return await self._items.get_or_fetch(item_id, lambda: self._fetch_one(item_id))

    async def _fetch_one(self, item_id: int) -> WorkshopItem | None:
        found = await self._fetch_details([item_id])
        return found[0] if found else None

    async def _fetch_trending(self, tag: str | None) -> tuple[Wallpaper, ...]:
        required = [SAFE_TAG] + ([tag] if tag else [])
        params = [
            ("appid", str(WALLPAPER_ENGINE_APP_ID)),
            ("browsesort", "trend"),
            ("actualsort", "trend"),
            ("section", "readytouseitems"),
            ("days", TRENDING_DAYS),
            ("numperpage", "30"),
            *(("requiredtags[]", required_tag) for required_tag in required),
        ]
        try:
            async with self._session.get(WORKSHOP_BROWSE_URL, params=params) as response:
                response.raise_for_status()
                ids = parse_browse_ids(await response.text())
        except (aiohttp.ClientError, TimeoutError) as error:
            raise SteamError("No se pudo leer el Workshop de Wallpaper Engine") from error
        if not ids:
            log.warning("No encontré fondos en la página del Workshop: ¿cambió el formato?")
            return ()
        items = await self._fetch_details(ids)
        # Se vuelve a filtrar por categoría por si la página no aplicó el filtro.
        return tuple(
            item for item in items if isinstance(item, Wallpaper) and (tag is None or tag in item.tags)
        )

    async def _fetch_details(self, ids: Sequence[int]) -> list[WorkshopItem]:
        data = {f"publishedfileids[{index}]": str(item) for index, item in enumerate(ids)}
        data["itemcount"] = str(len(ids))
        try:
            async with self._session.post(FILE_DETAILS_URL, data=data) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise SteamError("No se pudieron consultar los ítems del Workshop") from error
        items = parse_workshop_items(payload)
        for item in items:  # de paso, quedan guardados para cuando alguien pegue el link
            self._items.put(item.id, item)
        return items
