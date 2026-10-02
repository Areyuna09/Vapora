"""Cliente de la tienda de Steam: hace los pedidos, los cachea y devuelve modelos del bot."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

import aiohttp

from vapora.cache import RefreshingValue, TTLCache
from vapora.steam import parsers
from vapora.steam.models import STORE_URL, Deal, ItemKind, ItemRef, Reviews, SearchResult, StoreItem

log = logging.getLogger(__name__)

APP_DETAILS_URL = f"{STORE_URL}/api/appdetails"
PACKAGE_DETAILS_URL = f"{STORE_URL}/api/packagedetails"
BUNDLE_URL = f"{STORE_URL}/actions/ajaxresolvebundles"
REVIEWS_URL = f"{STORE_URL}/appreviews/{{app_id}}"
FEATURED_URL = f"{STORE_URL}/api/featuredcategories"
SEARCH_URL = f"{STORE_URL}/api/storesearch/"
# Curador público «Videojuegos Argentinos»: juegos desarrollados en Argentina.
ARGENTINE_CURATOR_URL = f"{STORE_URL}/curator/45013169/ajaxgetfilteredrecommendations/"

ITEM_TTL_SECONDS = 60 * 60
ARGENTINE_LIST_TTL_SECONDS = 24 * 60 * 60


class SteamError(Exception):
    """Steam no respondió, o respondió algo que no se pudo interpretar."""


class SteamClient:
    """Consultas a la tienda de Steam para una región (por defecto, Argentina en español)."""

    def __init__(
        self, session: aiohttp.ClientSession, *, country: str = "ar", language: str = "spanish"
    ) -> None:
        self._session = session
        self._country = country
        self._language = language
        self._items: TTLCache[ItemRef, StoreItem | None] = TTLCache(ITEM_TTL_SECONDS)
        self._argentine_ids: RefreshingValue[frozenset[int]] = RefreshingValue(
            ARGENTINE_LIST_TTL_SECONDS, frozenset()
        )

    async def get_item(self, ref: ItemRef) -> StoreItem | None:
        """Datos de un juego, DLC, paquete o bundle. `None` si no existe en la tienda.

        Raises:
            SteamError: si Steam no responde.
        """
        item = await self._items.get_or_fetch(ref, lambda: self._fetch_item(ref))
        if item is not None and ref.kind is ItemKind.APP:
            return replace(item, argentine=ref.id in await self.argentine_app_ids())
        return item

    async def search(self, term: str, *, limit: int = 10) -> list[SearchResult]:
        """Juegos que coinciden con el texto, como el buscador de la tienda."""
        payload = await self._get_json(SEARCH_URL, {"term": term, **self._region})
        return parsers.parse_search_results(payload)[:limit]

    async def featured_deals(self) -> list[Deal]:
        """Ofertas destacadas de la portada."""
        return parsers.parse_featured_deals(await self._get_json(FEATURED_URL, self._region))

    async def argentine_app_ids(self) -> frozenset[int]:
        """AppIDs de juegos argentinos. Si Steam falla, devuelve la última lista conocida."""
        return await self._argentine_ids.get(self._fetch_argentine_ids)

    # ── Pedidos ───────────────────────────────────────────────────────────────

    @property
    def _region(self) -> dict[str, str]:
        return {"cc": self._country, "l": self._language}

    async def _get_json(self, url: str, params: dict[str, str]) -> Any:
        try:
            async with self._session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise SteamError(f"No se pudo consultar {url}") from error

    async def _fetch_item(self, ref: ItemRef) -> StoreItem | None:
        if ref.kind is ItemKind.APP:
            return await self._fetch_app(ref.id)
        if ref.kind is ItemKind.PACKAGE:
            return await self._fetch_package(ref.id)
        return await self._fetch_bundle(ref.id)

    async def _fetch_app(self, app_id: int) -> StoreItem | None:
        payload = await self._get_json(APP_DETAILS_URL, {"appids": str(app_id), **self._region})
        entry = (payload or {}).get(str(app_id))
        if not entry or not entry.get("success"):
            return None
        item = parsers.parse_app(app_id, entry.get("data") or {})
        return replace(item, reviews=await self._fetch_reviews(app_id))

    async def _fetch_package(self, package_id: int) -> StoreItem | None:
        payload = await self._get_json(PACKAGE_DETAILS_URL, {"packageids": str(package_id), **self._region})
        entry = (payload or {}).get(str(package_id))
        if not entry or not entry.get("success"):
            return None
        return parsers.parse_package(package_id, entry.get("data") or {})

    async def _fetch_bundle(self, bundle_id: int) -> StoreItem | None:
        params = {"bundleids": str(bundle_id), "cc": self._country.upper(), "l": self._language}
        payload = await self._get_json(BUNDLE_URL, params)
        if not payload:
            return None
        return parsers.parse_bundle(bundle_id, payload[0])

    async def _fetch_reviews(self, app_id: int) -> Reviews | None:
        """Las reseñas son un extra: si fallan, la tarjeta se muestra igual sin ellas."""
        params = {
            "json": "1",
            "language": "all",
            "purchase_type": "all",
            "num_per_page": "0",
            "l": self._language,
        }
        try:
            return parsers.parse_reviews(await self._get_json(REVIEWS_URL.format(app_id=app_id), params))
        except SteamError:
            log.warning("No se pudieron obtener las reseñas de %s", app_id, exc_info=True)
            return None

    async def _fetch_argentine_ids(self) -> frozenset[int] | None:
        try:
            payload = await self._get_json(
                ARGENTINE_CURATOR_URL, {"query": "", "start": "0", "count": "2000"}
            )
        except SteamError:
            log.warning("No se pudo actualizar la lista de juegos argentinos", exc_info=True)
            return None
        ids = parsers.parse_curator_app_ids((payload or {}).get("results_html"))
        if not ids:
            return None
        log.info("Lista de juegos argentinos actualizada: %d juegos", len(ids))
        return ids
