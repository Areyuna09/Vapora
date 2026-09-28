import logging
import re
import time
from typing import Any

import aiohttp

STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_PACKAGEDETAILS_URL = "https://store.steampowered.com/api/packagedetails"
STEAM_BUNDLE_URL = "https://store.steampowered.com/actions/ajaxresolvebundles"
STEAM_REVIEWS_URL = "https://store.steampowered.com/appreviews/{app_id}"

# Tipos de link de la tienda: juegos y DLC (/app/), paquetes (/sub/) y bundles (/bundle/).
STEAM_URL_RE = re.compile(
    r"https?://(?:store\.)?steampowered\.com/(app|sub|bundle)/(\d+)(?:/[^\s<>]*)?",
    re.IGNORECASE,
)

# Cache en memoria: (tipo, id, país) -> (timestamp, data). data=None marca IDs inválidos.
_CACHE: dict[tuple[str, int, str], tuple[float, dict[str, Any] | None]] = {}
CACHE_TTL_SECONDS = 60 * 60  # 1 hora

_session: aiohttp.ClientSession | None = None


def extract_steam_items(text: str) -> list[tuple[str, int]]:
    """Devuelve (tipo, id) de los links de Steam del texto, sin repetir y en orden."""
    items = ((kind.lower(), int(item_id)) for kind, item_id in STEAM_URL_RE.findall(text))
    return list(dict.fromkeys(items))


def store_url(kind: str, item_id: int) -> str:
    return f"https://store.steampowered.com/{kind}/{item_id}/"


def _empty_result(kind: str, item_id: int, name: str | None) -> dict[str, Any]:
    return {
        "kind": kind,
        "id": item_id,
        "name": name or f"{kind.title()} {item_id}",
        "type": None,
        "short_description": None,
        "header_image": None,
        "is_free": False,
        "price": None,  # texto formateado por Steam, ej. "$29.99 USD"
        "currency": None,
        "initial_cents": None,
        "final_cents": None,
        "discount_percent": 0,
        "release_date": None,
        "coming_soon": False,
        "genres": [],
        "developers": [],
        "dlc_of": None,  # nombre del juego base si es un DLC
        "included": [],  # nombres de lo que incluye un paquete (juegos y DLC)
        "included_count": 0,  # cantidad de productos de un paquete o bundle
        "reviews": None,  # se completa en get_item_details (solo juegos y DLC)
    }


def parse_app_data(app_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Convierte la respuesta cruda de appdetails (juego o DLC) en lo que usa el bot."""
    release = data.get("release_date") or {}
    result = _empty_result("app", app_id, data.get("name"))
    result.update({
        "type": data.get("type"),
        "short_description": data.get("short_description"),
        "header_image": data.get("header_image"),
        "is_free": bool(data.get("is_free")),
        "release_date": release.get("date") or None,
        "coming_soon": bool(release.get("coming_soon")),
        "genres": [g["description"] for g in data.get("genres") or [] if g.get("description")],
        "developers": data.get("developers") or [],
    })

    if data.get("type") == "dlc":
        result["dlc_of"] = (data.get("fullgame") or {}).get("name")

    price = data.get("price_overview")
    if price:
        result["price"] = price.get("final_formatted") or price.get("initial_formatted")
        result["currency"] = price.get("currency")
        result["initial_cents"] = price.get("initial")
        result["final_cents"] = price.get("final")
        result["discount_percent"] = price.get("discount_percent", 0)

    return result


def parse_package_data(package_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Convierte la respuesta de packagedetails (link /sub/) en lo que usa el bot."""
    release = data.get("release_date") or {}
    apps = [a["name"] for a in data.get("apps") or [] if a.get("name")]
    result = _empty_result("sub", package_id, data.get("name"))
    result.update({
        "header_image": data.get("page_image") or data.get("header_image"),
        "release_date": release.get("date") or None,
        "coming_soon": bool(release.get("coming_soon")),
        "included": apps,
        "included_count": len(apps),
    })

    price = data.get("price")
    if price:
        result["currency"] = price.get("currency")
        result["final_cents"] = price.get("final")
        # "individual" es lo que costaría comprar todo por separado.
        result["initial_cents"] = max(price.get("initial") or 0, price.get("individual") or 0) or None
        if result["initial_cents"] and result["final_cents"] < result["initial_cents"]:
            result["discount_percent"] = round((1 - result["final_cents"] / result["initial_cents"]) * 100)

    return result


def parse_bundle_data(bundle_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """Convierte la respuesta de ajaxresolvebundles (link /bundle/) en lo que usa el bot."""
    result = _empty_result("bundle", bundle_id, data.get("name"))
    result.update({
        "header_image": data.get("main_capsule") or data.get("header_image_url"),
        "coming_soon": bool(data.get("coming_soon")),
        "included_count": len(data.get("appids") or []),
    })

    final = data.get("final_price")
    if final is not None:
        formatted = data.get("formatted_final_price") or ""
        result["price"] = formatted or None
        result["currency"] = "USD" if "USD" in formatted else None
        result["final_cents"] = final
        # initial_price es la suma de los juegos por separado.
        initial = data.get("initial_price")
        if initial and final < initial:
            result["initial_cents"] = initial
            result["discount_percent"] = round((1 - final / initial) * 100)

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


async def _get_json(url: str, params: dict[str, str]) -> Any:
    session = await get_session()
    async with session.get(url, params=params) as response:
        response.raise_for_status()
        return await response.json(content_type=None)


async def _fetch_reviews(app_id: int) -> dict[str, Any] | None:
    params = {
        "json": "1",
        "language": "all",
        "purchase_type": "all",
        "num_per_page": "0",
        "l": "spanish",
    }
    try:
        return parse_reviews(await _get_json(STEAM_REVIEWS_URL.format(app_id=app_id), params))
    except (aiohttp.ClientError, TimeoutError, ValueError):
        logging.warning("No se pudieron obtener las reseñas de %s", app_id, exc_info=True)
        return None


async def _fetch_app(app_id: int, country: str) -> dict[str, Any] | None:
    payload = await _get_json(STEAM_APPDETAILS_URL, {"appids": str(app_id), "cc": country, "l": "spanish"})
    entry = (payload or {}).get(str(app_id))
    if not entry or not entry.get("success"):
        return None
    result = parse_app_data(app_id, entry.get("data", {}))
    result["reviews"] = await _fetch_reviews(app_id)
    return result


async def _fetch_package(package_id: int, country: str) -> dict[str, Any] | None:
    payload = await _get_json(
        STEAM_PACKAGEDETAILS_URL, {"packageids": str(package_id), "cc": country, "l": "spanish"}
    )
    entry = (payload or {}).get(str(package_id))
    if not entry or not entry.get("success"):
        return None
    return parse_package_data(package_id, entry.get("data", {}))


async def _fetch_bundle(bundle_id: int, country: str) -> dict[str, Any] | None:
    payload = await _get_json(
        STEAM_BUNDLE_URL, {"bundleids": str(bundle_id), "cc": country.upper(), "l": "spanish"}
    )
    if not payload:
        return None
    return parse_bundle_data(bundle_id, payload[0])


_FETCHERS = {"app": _fetch_app, "sub": _fetch_package, "bundle": _fetch_bundle}


async def get_item_details(kind: str, item_id: int, country: str = "ar") -> dict[str, Any] | None:
    """Datos de un juego/DLC (app), paquete (sub) o bundle, con caché de 1 hora."""
    now = time.time()
    key = (kind, item_id, country)
    cached = _CACHE.get(key)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    result = await _FETCHERS[kind](item_id, country)
    _CACHE[key] = (now, result)
    return result


# ── Juegos argentinos ─────────────────────────────────────────────────────────
# Curador de Steam con juegos hechos en Argentina (el mismo que usa Steamcito).
ARGENTINE_CURATOR_URL = "https://store.steampowered.com/curator/45013169/ajaxgetfilteredrecommendations/"
ARGENTINE_TTL_SECONDS = 24 * 60 * 60  # se actualiza una vez por día
_APPID_RE = re.compile(r'data-ds-appid="(\d+)"')

_argentine_ids: set[int] = set()
_argentine_fetched_at = 0.0


def parse_curator_app_ids(results_html: str) -> set[int]:
    return {int(app_id) for app_id in _APPID_RE.findall(results_html or "")}


async def get_argentine_app_ids() -> set[int]:
    """AppIDs de juegos argentinos. Si Steam falla, devuelve la última lista conocida."""
    global _argentine_ids, _argentine_fetched_at
    if time.time() - _argentine_fetched_at < ARGENTINE_TTL_SECONDS:
        return _argentine_ids
    try:
        payload = await _get_json(ARGENTINE_CURATOR_URL, {"query": "", "start": "0", "count": "2000"})
        ids = parse_curator_app_ids((payload or {}).get("results_html", ""))
        if ids:
            _argentine_ids = ids
            logging.info("Lista de juegos argentinos actualizada: %d juegos", len(ids))
    except (aiohttp.ClientError, TimeoutError, ValueError):
        logging.warning("No se pudo actualizar la lista de juegos argentinos", exc_info=True)
    _argentine_fetched_at = time.time()
    return _argentine_ids


async def is_argentine(app_id: int) -> bool:
    return app_id in await get_argentine_app_ids()


# ── Ofertas destacadas ────────────────────────────────────────────────────────
STEAM_FEATURED_URL = "https://store.steampowered.com/api/featuredcategories"
SPECIALS_KINDS = {0: "app", 1: "sub", 2: "bundle"}  # campo "type" de featuredcategories


def parse_specials(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Ofertas de la portada de Steam (solo juegos con descuento y precio en USD)."""
    items = ((payload or {}).get("specials") or {}).get("items") or []
    deals = []
    for item in items:
        if not item.get("discounted") or not item.get("final_price"):
            continue
        deals.append({
            "kind": SPECIALS_KINDS.get(item.get("type"), "app"),
            "id": item["id"],
            "name": item.get("name", f"App {item['id']}"),
            "discount_percent": item.get("discount_percent", 0),
            "initial_cents": item.get("original_price"),
            "final_cents": item["final_price"],
            "currency": item.get("currency"),
            "image": item.get("large_capsule_image") or item.get("header_image"),
            "discount_expiration": item.get("discount_expiration"),
        })
    return list({(d["kind"], d["id"]): d for d in deals}.values())  # sin repetidos


async def get_featured_specials(country: str = "ar") -> list[dict[str, Any]]:
    payload = await _get_json(STEAM_FEATURED_URL, {"cc": country, "l": "spanish"})
    return parse_specials(payload)
