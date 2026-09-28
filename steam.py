import logging
import re
import time
from typing import Any

import aiohttp

STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"

STEAM_URL_RE = re.compile(
    r"https?://(?:store\.)?steampowered\.com/app/(\d+)(?:/[^\s<>]*)?",
    re.IGNORECASE,
)

# Cache en memoria: (AppID, país) -> (timestamp, data). data=None marca AppIDs inválidos.
_CACHE: dict[tuple[int, str], tuple[float, dict[str, Any] | None]] = {}
CACHE_TTL_SECONDS = 60 * 60  # 1 hora

_session: aiohttp.ClientSession | None = None


def extract_app_ids(text: str) -> list[int]:
    """Devuelve los AppIDs de los links de Steam del texto, sin repetir y en orden."""
    return [int(app_id) for app_id in dict.fromkeys(STEAM_URL_RE.findall(text))]


def parse_app_data(app_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Convierte la respuesta cruda de appdetails en lo que usa el bot."""
    release = data.get("release_date") or {}

    result: dict[str, Any] = {
        "name": data.get("name", f"App {app_id}"),
        "type": data.get("type"),
        "short_description": data.get("short_description"),
        "header_image": data.get("header_image"),
        "is_free": bool(data.get("is_free")),
        "price": None,  # texto formateado por Steam, ej. "$29.99 USD"
        "currency": None,
        "initial_cents": None,
        "final_cents": None,
        "discount_percent": 0,
        "release_date": release.get("date") or None,
        "coming_soon": bool(release.get("coming_soon")),
        "genres": [g["description"] for g in data.get("genres") or [] if g.get("description")],
        "developers": data.get("developers") or [],
        "reviews": None,  # se completa en get_app_details
    }

    price = data.get("price_overview")
    if price:
        result["price"] = price.get("final_formatted") or price.get("initial_formatted")
        result["currency"] = price.get("currency")
        result["initial_cents"] = price.get("initial")
        result["final_cents"] = price.get("final")
        result["discount_percent"] = price.get("discount_percent", 0)

    return result


def parse_reviews(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Extrae el resumen de reseñas de la respuesta de appreviews."""
    summary = (payload or {}).get("query_summary") or {}
    total = summary.get("total_reviews") or 0
    if not payload.get("success") or total == 0:
        return None
    positive = summary.get("total_positive") or 0
    return {
        "description": summary.get("review_score_desc"),
        "total": total,
        "positive_percent": round(positive * 100 / total),
    }


async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    return _session


async def close_session() -> None:
    if _session is not None and not _session.closed:
        await _session.close()


async def _fetch_reviews(app_id: int) -> dict[str, Any] | None:
    params = {
        "json": "1",
        "language": "all",
        "purchase_type": "all",
        "num_per_page": "0",
        "l": "spanish",
    }
    try:
        session = await get_session()
        async with session.get(STEAM_REVIEWS_URL.format(app_id=app_id), params=params) as response:
            response.raise_for_status()
            return parse_reviews(await response.json(content_type=None))
    except (aiohttp.ClientError, TimeoutError, ValueError):
        logging.warning("No se pudieron obtener las reseñas de %s", app_id, exc_info=True)
        return None


async def get_app_details(app_id: int, country: str = "ar") -> dict[str, Any] | None:
    now = time.time()
    key = (app_id, country)
    cached = _CACHE.get(key)

    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    params = {
        "appids": str(app_id),
        "cc": country,
        "l": "spanish",
    }

    session = await get_session()
    async with session.get(STEAM_APPDETAILS_URL, params=params) as response:
        response.raise_for_status()
        payload = await response.json()

    entry = (payload or {}).get(str(app_id))
    if not entry or not entry.get("success"):
        _CACHE[key] = (now, None)
        return None

    result = parse_app_data(app_id, entry.get("data", {}))
    result["reviews"] = await _fetch_reviews(app_id)

    _CACHE[key] = (now, result)
    return result
