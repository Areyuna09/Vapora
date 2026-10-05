"""Cliente de la tienda de Steam: hace los pedidos, los cachea y devuelve modelos del bot."""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import replace
from typing import Any, TypeVar

import aiohttp

from vapora.cache import RefreshingValue, TTLCache
from vapora.steam import parsers
from vapora.steam.models import STORE_URL, Deal, ItemKind, ItemRef, Price, Reviews, SearchResult, StoreItem

log = logging.getLogger(__name__)

APP_DETAILS_URL = f"{STORE_URL}/api/appdetails"
PACKAGE_DETAILS_URL = f"{STORE_URL}/api/packagedetails"
BUNDLE_URL = f"{STORE_URL}/actions/ajaxresolvebundles"
REVIEWS_URL = f"{STORE_URL}/appreviews/{{app_id}}"
FEATURED_URL = f"{STORE_URL}/api/featuredcategories"
SEARCH_URL = f"{STORE_URL}/api/storesearch/"
# Curador público «Videojuegos Argentinos»: juegos desarrollados en Argentina.
ARGENTINE_CURATOR_URL = f"{STORE_URL}/curator/45013169/ajaxgetfilteredrecommendations/"

T = TypeVar("T")

ITEM_TTL_SECONDS = 60 * 60
PRICES_PER_REQUEST = 100  # appdetails acepta varios juegos juntos si se pide solo el precio
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

    async def prices(self, app_ids: Collection[int]) -> dict[int, Price | None]:
        """Precio actual de varios juegos, sin caché y en pocos pedidos (solo trae el precio).

        Los juegos que Steam no encuentra quedan afuera; los gratis aparecen con `None`.
        Si falla una parte, se devuelve el resto.

        Raises:
            SteamError: si no se pudo obtener ningún precio.
        """
        ids = sorted(set(app_ids))
        prices: dict[int, Price | None] = {}
        failed = 0
        chunks = [ids[start : start + PRICES_PER_REQUEST] for start in range(0, len(ids), PRICES_PER_REQUEST)]
        for chunk in chunks:
            params = {"appids": ",".join(map(str, chunk)), "filters": "price_overview", **self._region}
            try:
                payload = _expect(dict, await self._get_json(APP_DETAILS_URL, params), APP_DETAILS_URL)
            except SteamError:
                log.warning("No se pudieron consultar los precios de %d juegos", len(chunk), exc_info=True)
                failed += 1
                continue
            prices.update(parsers.parse_app_prices(payload))
        if chunks and failed == len(chunks):
            raise SteamError("No se pudo consultar ningún precio")
        return prices

    async def search(self, term: str, *, limit: int = 10) -> list[SearchResult]:
        """Juegos que coinciden con el texto, como el buscador de la tienda."""
        payload = await self._get_json(SEARCH_URL, {"term": term, **self._region})
        return parsers.parse_search_results(_expect(dict, payload, SEARCH_URL))[:limit]

    async def featured_deals(self) -> list[Deal]:
        """Ofertas destacadas de la portada."""
        payload = await self._get_json(FEATURED_URL, self._region)
        return parsers.parse_featured_deals(_expect(dict, payload, FEATURED_URL))

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
        data = _details_data(payload, app_id, APP_DETAILS_URL)
        if data is None:
            return None
        item = parsers.parse_app(app_id, data)
        return replace(item, reviews=await self._fetch_reviews(app_id))

    async def _fetch_package(self, package_id: int) -> StoreItem | None:
        payload = await self._get_json(PACKAGE_DETAILS_URL, {"packageids": str(package_id), **self._region})
        data = _details_data(payload, package_id, PACKAGE_DETAILS_URL)
        if data is None:
            return None
        return parsers.parse_package(package_id, data)

    async def _fetch_bundle(self, bundle_id: int) -> StoreItem | None:
        params = {"bundleids": str(bundle_id), "cc": self._country.upper(), "l": self._language}
        payload = _expect(list, await self._get_json(BUNDLE_URL, params), BUNDLE_URL)
        if not payload or not isinstance(payload[0], dict):
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
            url = REVIEWS_URL.format(app_id=app_id)
            return parsers.parse_reviews(_expect(dict, await self._get_json(url, params), url))
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
        html = payload.get("results_html") if isinstance(payload, dict) else None
        ids = parsers.parse_curator_app_ids(html if isinstance(html, str) else None)
        if not ids:
            return None
        log.info("Lista de juegos argentinos actualizada: %d juegos", len(ids))
        return ids


def _expect(kind: type[T], payload: Any, url: str) -> T | None:
    """`payload` si tiene la forma esperada (o es vacío: `None`); si no, `SteamError`.

    Steam a veces responde con otra forma (por ejemplo, una lista vacía en vez de un objeto)
    cuando algo no existe o hay problemas: así eso se trata como una falla de Steam y no
    termina en un error inesperado más adelante.
    """
    if payload is None or isinstance(payload, kind):
        return payload
    raise SteamError(f"Respuesta inesperada de {url}: {type(payload).__name__}")


def _details_data(payload: Any, item_id: int, url: str) -> dict[str, Any] | None:
    """Datos de `appdetails` o `packagedetails`, o `None` si Steam no lo encontró."""
    entry = (_expect(dict, payload, url) or {}).get(str(item_id))
    if not isinstance(entry, dict) or not entry.get("success"):
        return None
    data = entry.get("data")
    return data if isinstance(data, dict) else {}
