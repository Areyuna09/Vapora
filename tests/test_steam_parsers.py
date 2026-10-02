from vapora.steam import ItemKind, ItemRef, Price, Reviews
from vapora.steam.parsers import (
    parse_app,
    parse_bundle,
    parse_curator_app_ids,
    parse_featured_deals,
    parse_package,
    parse_reviews,
    parse_search_results,
)

# ── Juegos y DLC ──────────────────────────────────────────────────────────────


def test_app_with_discount():
    item = parse_app(
        1888930,
        {
            "name": "The Last of Us™ Parte I",
            "is_free": False,
            "price_overview": {"currency": "USD", "initial": 5999, "final": 2999, "discount_percent": 50},
        },
    )
    assert item.ref == ItemRef.app(1888930)
    assert item.price == Price(final_cents=2999, initial_cents=5999, discount_percent=50, currency="USD")
    assert item.price.on_sale


def test_app_without_discount_is_not_on_sale():
    item = parse_app(
        1,
        {
            "name": "Juego",
            "price_overview": {"currency": "USD", "initial": 999, "final": 999, "discount_percent": 0},
        },
    )
    assert item.price is not None and not item.price.on_sale


def test_free_app_has_no_price():
    item = parse_app(730, {"name": "Counter-Strike 2", "is_free": True})
    assert item.is_free
    assert item.price is None
    assert not item.is_wishable


def test_app_details():
    item = parse_app(
        1,
        {
            "name": "Juego",
            "short_description": "Una aventura.",
            "header_image": "https://example.com/header.jpg",
            "release_date": {"coming_soon": False, "date": "28 MAR 2023"},
            "genres": [{"id": "1", "description": "Acción"}, {"id": "25", "description": "Aventura"}],
            "developers": ["Naughty Dog LLC"],
        },
    )
    assert item.description == "Una aventura."
    assert item.image_url == "https://example.com/header.jpg"
    assert item.release_date == "28 MAR 2023"
    assert not item.coming_soon
    assert item.genres == ("Acción", "Aventura")
    assert item.developers == ("Naughty Dog LLC",)


def test_app_without_name_gets_a_placeholder():
    assert parse_app(42, {}).name == "App 42"


def test_dlc_knows_its_base_game():
    dlc = parse_app(
        2778580,
        {
            "type": "dlc",
            "name": "ELDEN RING Shadow of the Erdtree",
            "fullgame": {"appid": "1245620", "name": "ELDEN RING"},
        },
    )
    assert dlc.dlc_of == "ELDEN RING"


def test_game_is_not_a_dlc_even_with_fullgame_field():
    assert parse_app(1, {"type": "game", "fullgame": {"name": "Otro"}}).dlc_of is None


# ── Paquetes y bundles ────────────────────────────────────────────────────────


def test_package_discount_is_the_saving_over_buying_separately():
    package = parse_package(
        469,
        {
            "name": "The Orange Box",
            "page_image": "https://example.com/header.jpg",
            "apps": [{"id": i, "name": f"Juego {i}"} for i in range(1, 8)],
            "price": {
                "currency": "USD",
                "initial": 1049,
                "final": 1049,
                "discount_percent": 0,
                "individual": 1158,
            },
        },
    )
    assert package.ref == ItemRef(ItemKind.PACKAGE, 469)
    assert package.price == Price(1049, 1158, 9, "USD")
    assert package.included_count == 7
    assert package.included[0] == "Juego 1"
    assert not package.is_wishable


def test_bundle_discount_is_the_saving_over_buying_separately():
    bundle = parse_bundle(
        232,
        {
            "name": "Valve Complete Pack",
            "appids": list(range(18)),
            "main_capsule": "https://example.com/capsule.jpg",
            "initial_price": 7584,
            "final_price": 6824,
            "formatted_final_price": "$68.24 USD",
        },
    )
    assert bundle.ref == ItemRef(ItemKind.BUNDLE, 232)
    assert bundle.price == Price(6824, 7584, 10, "USD")
    assert bundle.included_count == 18
    assert bundle.image_url == "https://example.com/capsule.jpg"


def test_bundle_without_saving_has_no_original_price():
    bundle = parse_bundle(
        1, {"name": "Pack", "final_price": 500, "initial_price": 500, "formatted_final_price": "$5.00 USD"}
    )
    assert bundle.price == Price(500, currency="USD")


def test_bundle_in_another_currency_is_not_usd():
    bundle = parse_bundle(1, {"name": "Pack", "final_price": 500, "formatted_final_price": "ARS$ 5,00"})
    assert bundle.price is not None and not bundle.price.is_usd


# ── Reseñas ───────────────────────────────────────────────────────────────────


def test_reviews_summary():
    payload = {
        "success": 1,
        "query_summary": {
            "review_score_desc": "Muy positivas",
            "total_positive": 92766,
            "total_reviews": 109737,
        },
    }
    assert parse_reviews(payload) == Reviews("Muy positivas", total=109737, positive_percent=85)


def test_no_reviews_yet():
    assert parse_reviews({"success": 1, "query_summary": {"total_reviews": 0}}) is None
    assert parse_reviews({}) is None
    assert parse_reviews(None) is None


# ── Ofertas, buscador y curador ───────────────────────────────────────────────


def _special(**fields):
    return {
        "id": 1,
        "name": "A",
        "discounted": True,
        "discount_percent": 50,
        "original_price": 2000,
        "final_price": 1000,
        "currency": "USD",
        **fields,
    }


def test_featured_deals_skip_duplicates_and_items_without_discount():
    payload = {
        "specials": {
            "items": [
                _special(),
                _special(),
                _special(id=2, name="B", discounted=False),
            ]
        }
    }
    deals = parse_featured_deals(payload)
    assert [deal.ref for deal in deals] == [ItemRef.app(1)]
    assert deals[0].price == Price(1000, 2000, 50, "USD")


def test_featured_deal_can_be_a_package():
    payload = {"specials": {"items": [_special(type=1, id=94174, discount_expiration=1790874000)]}}
    deal = parse_featured_deals(payload)[0]
    assert deal.ref == ItemRef(ItemKind.PACKAGE, 94174)
    assert deal.expires_at == 1790874000


def test_featured_deals_of_empty_payload():
    assert parse_featured_deals(None) == []
    assert parse_featured_deals({"specials": {}}) == []


def test_search_results_keep_only_games():
    payload = {
        "items": [
            {"type": "app", "id": 367520, "name": "Hollow Knight"},
            {"type": "sub", "id": 99, "name": "Un paquete"},
        ]
    }
    results = parse_search_results(payload)
    assert [(result.app_id, result.name) for result in results] == [(367520, "Hollow Knight")]


def test_curator_app_ids_without_repeats():
    html = '<div data-ds-appid="123"></div><a data-ds-appid="123"></a><div data-ds-appid="456"></div>'
    assert parse_curator_app_ids(html) == {123, 456}
    assert parse_curator_app_ids(None) == frozenset()
