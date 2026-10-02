"""Convierte las respuestas crudas de Steam en los modelos del bot.

Son funciones puras: reciben el JSON (o HTML) ya descargado y no hacen pedidos de red.
"""

from __future__ import annotations

import re
from typing import Any

from vapora.steam.models import Deal, ItemKind, ItemRef, Price, Reviews, SearchResult, StoreItem

# Campo "type" de las ofertas de la portada (featuredcategories).
_FEATURED_KINDS = {0: ItemKind.APP, 1: ItemKind.PACKAGE, 2: ItemKind.BUNDLE}
_CURATOR_APP_ID_RE = re.compile(r'data-ds-appid="(\d+)"')


def _savings_percent(final_cents: int, initial_cents: int) -> int:
    return round((1 - final_cents / initial_cents) * 100)


def _default_name(ref: ItemRef) -> str:
    return f"{ref.kind.title()} {ref.id}"


def parse_app(app_id: int, data: dict[str, Any]) -> StoreItem:
    """Juego o DLC, a partir de `appdetails`."""
    ref = ItemRef.app(app_id)
    release = data.get("release_date") or {}
    is_dlc = data.get("type") == "dlc"

    price = None
    overview = data.get("price_overview")
    if overview and overview.get("final") is not None:
        price = Price(
            final_cents=overview["final"],
            initial_cents=overview.get("initial"),
            discount_percent=overview.get("discount_percent", 0),
            currency=overview.get("currency"),
        )

    return StoreItem(
        ref=ref,
        name=data.get("name") or _default_name(ref),
        description=data.get("short_description"),
        image_url=data.get("header_image"),
        is_free=bool(data.get("is_free")),
        price=price,
        release_date=release.get("date") or None,
        coming_soon=bool(release.get("coming_soon")),
        genres=tuple(g["description"] for g in data.get("genres") or [] if g.get("description")),
        developers=tuple(data.get("developers") or []),
        dlc_of=(data.get("fullgame") or {}).get("name") if is_dlc else None,
    )


def parse_package(package_id: int, data: dict[str, Any]) -> StoreItem:
    """Paquete (link /sub/), a partir de `packagedetails`."""
    ref = ItemRef(ItemKind.PACKAGE, package_id)
    release = data.get("release_date") or {}
    included = tuple(app["name"] for app in data.get("apps") or [] if app.get("name"))

    price = None
    raw = data.get("price")
    if raw and raw.get("final") is not None:
        final = raw["final"]
        # "individual" es lo que costaría comprar todo por separado.
        initial = max(raw.get("initial") or 0, raw.get("individual") or 0) or None
        discount = _savings_percent(final, initial) if initial and final < initial else 0
        price = Price(final, initial, discount, raw.get("currency"))

    return StoreItem(
        ref=ref,
        name=data.get("name") or _default_name(ref),
        image_url=data.get("page_image") or data.get("header_image"),
        price=price,
        release_date=release.get("date") or None,
        coming_soon=bool(release.get("coming_soon")),
        included=included,
        included_count=len(included),
    )


def parse_bundle(bundle_id: int, data: dict[str, Any]) -> StoreItem:
    """Bundle, a partir de `ajaxresolvebundles`."""
    ref = ItemRef(ItemKind.BUNDLE, bundle_id)

    price = None
    final = data.get("final_price")
    if final is not None:
        currency = "USD" if "USD" in (data.get("formatted_final_price") or "") else None
        # initial_price es la suma de los productos por separado.
        initial = data.get("initial_price")
        if initial and final < initial:
            price = Price(final, initial, _savings_percent(final, initial), currency)
        else:
            price = Price(final, currency=currency)

    return StoreItem(
        ref=ref,
        name=data.get("name") or _default_name(ref),
        image_url=data.get("main_capsule") or data.get("header_image_url"),
        price=price,
        coming_soon=bool(data.get("coming_soon")),
        included_count=len(data.get("appids") or []),
    )


def parse_reviews(payload: dict[str, Any] | None) -> Reviews | None:
    """Resumen de reseñas, a partir de `appreviews`. `None` si todavía no tiene reseñas."""
    payload = payload or {}
    summary = payload.get("query_summary") or {}
    total = summary.get("total_reviews") or 0
    if not payload.get("success") or total == 0:
        return None
    positive = summary.get("total_positive") or 0
    return Reviews(
        description=summary.get("review_score_desc"),
        total=total,
        positive_percent=round(positive * 100 / total),
    )


def parse_featured_deals(payload: dict[str, Any] | None) -> list[Deal]:
    """Ofertas de la portada (`featuredcategories`), sin repetidos y solo con descuento."""
    items = ((payload or {}).get("specials") or {}).get("items") or []
    deals: dict[ItemRef, Deal] = {}
    for item in items:
        if not item.get("discounted") or not item.get("final_price"):
            continue
        ref = ItemRef(_FEATURED_KINDS.get(item.get("type"), ItemKind.APP), item["id"])
        deals[ref] = Deal(
            ref=ref,
            name=item.get("name") or _default_name(ref),
            price=Price(
                final_cents=item["final_price"],
                initial_cents=item.get("original_price"),
                discount_percent=item.get("discount_percent", 0),
                currency=item.get("currency"),
            ),
            image_url=item.get("large_capsule_image") or item.get("header_image"),
            expires_at=item.get("discount_expiration"),
        )
    return list(deals.values())


def parse_search_results(payload: dict[str, Any] | None) -> list[SearchResult]:
    """Juegos encontrados por el buscador de la tienda (`storesearch`)."""
    items = (payload or {}).get("items") or []
    return [SearchResult(item["id"], item["name"]) for item in items if item.get("type") == "app"]


def parse_curator_app_ids(results_html: str | None) -> frozenset[int]:
    """AppIDs recomendados por un curador, a partir del HTML que devuelve su listado."""
    return frozenset(int(app_id) for app_id in _CURATOR_APP_ID_RE.findall(results_html or ""))
