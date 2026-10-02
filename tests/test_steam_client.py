import aiohttp
import pytest
from helpers import FakeSession

from vapora.steam import ItemKind, ItemRef, SteamClient, SteamError

APP = {
    "367520": {
        "success": True,
        "data": {
            "name": "Hollow Knight",
            "price_overview": {"currency": "USD", "initial": 499, "final": 499, "discount_percent": 0},
        },
    }
}
REVIEWS = {
    "success": 1,
    "query_summary": {
        "review_score_desc": "Extremadamente positivas",
        "total_positive": 97,
        "total_reviews": 100,
    },
}
CURATOR = {"results_html": '<div data-ds-appid="367520"></div>'}


def _client(routes: dict) -> tuple[SteamClient, FakeSession]:
    session = FakeSession(routes)
    return SteamClient(session), session  # type: ignore[arg-type]


async def test_get_item_combines_details_reviews_and_argentine_flag():
    client, _ = _client({"api/appdetails": APP, "appreviews": REVIEWS, "curator": CURATOR})
    item = await client.get_item(ItemRef.app(367520))
    assert item is not None
    assert item.name == "Hollow Knight"
    assert item.reviews is not None and item.reviews.positive_percent == 97
    assert item.argentine


async def test_get_item_asks_for_the_argentine_store():
    client, session = _client({"api/appdetails": APP, "appreviews": REVIEWS, "curator": CURATOR})
    await client.get_item(ItemRef.app(367520))
    _, params = next(call for call in session.calls if "appdetails" in call[0])
    assert params == {"appids": "367520", "cc": "ar", "l": "spanish"}


async def test_items_are_cached():
    client, session = _client({"api/appdetails": APP, "appreviews": REVIEWS, "curator": CURATOR})
    await client.get_item(ItemRef.app(367520))
    await client.get_item(ItemRef.app(367520))
    assert session.count("api/appdetails") == 1
    assert session.count("curator") == 1


async def test_unknown_item_is_none_and_also_cached():
    client, session = _client({"api/appdetails": {"999": {"success": False}}, "curator": CURATOR})
    assert await client.get_item(ItemRef.app(999)) is None
    assert await client.get_item(ItemRef.app(999)) is None
    assert session.count("api/appdetails") == 1


async def test_item_without_reviews_is_still_returned():
    client, _ = _client({"api/appdetails": APP, "appreviews": aiohttp.ClientError(), "curator": CURATOR})
    item = await client.get_item(ItemRef.app(367520))
    assert item is not None and item.reviews is None


async def test_item_is_returned_when_argentine_list_fails():
    client, _ = _client({"api/appdetails": APP, "appreviews": REVIEWS, "curator": aiohttp.ClientError()})
    item = await client.get_item(ItemRef.app(367520))
    assert item is not None and not item.argentine


async def test_steam_down_raises_steam_unavailable():
    client, _ = _client({"api/appdetails": aiohttp.ClientError()})
    with pytest.raises(SteamError):
        await client.get_item(ItemRef.app(367520))


async def test_http_error_raises_steam_unavailable():
    client, _ = _client({})  # la sesión falsa responde 404 a lo que no conoce
    with pytest.raises(SteamError):
        await client.featured_deals()


async def test_failed_lookup_is_retried_instead_of_cached():
    client, session = _client({"api/appdetails": aiohttp.ClientError()})
    for _ in range(2):
        with pytest.raises(SteamError):
            await client.get_item(ItemRef.app(367520))
    assert session.count("api/appdetails") == 2


async def test_packages_and_bundles_use_their_own_endpoints():
    client, session = _client(
        {
            "api/packagedetails": {"469": {"success": True, "data": {"name": "The Orange Box"}}},
            "ajaxresolvebundles": [{"name": "Valve Complete Pack", "final_price": 6824}],
        }
    )
    package = await client.get_item(ItemRef(ItemKind.PACKAGE, 469))
    bundle = await client.get_item(ItemRef(ItemKind.BUNDLE, 232))
    assert package is not None and package.name == "The Orange Box"
    assert bundle is not None and bundle.name == "Valve Complete Pack"
    assert session.count("curator") == 0  # la lista de argentinos es solo de juegos


async def test_missing_bundle_is_none():
    client, _ = _client({"ajaxresolvebundles": []})
    assert await client.get_item(ItemRef(ItemKind.BUNDLE, 999)) is None


async def test_search_respects_limit():
    payload = {"items": [{"type": "app", "id": i, "name": f"Juego {i}"} for i in range(5)]}
    client, _ = _client({"storesearch": payload})
    assert [result.app_id for result in await client.search("juego", limit=2)] == [0, 1]
