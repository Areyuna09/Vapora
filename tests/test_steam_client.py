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


# ── Precios de varios juegos ──────────────────────────────────────────────────


def _prices_payload(params: dict[str, str]) -> dict:
    """appdetails con filters=price_overview: Hollow Knight con precio, 570 gratis, el resto no existe."""
    payload: dict = {}
    for app_id in params["appids"].split(","):
        if app_id == "367520":
            payload[app_id] = {"success": True, "data": APP["367520"]["data"]}
        elif app_id == "570":
            payload[app_id] = {"success": True, "data": []}  # así responde Steam con los gratis
        else:
            payload[app_id] = {"success": False}
    return payload


async def test_prices_of_several_games_in_one_request():
    client, session = _client({"api/appdetails": _prices_payload})
    prices = await client.prices({367520, 570, 999})
    assert prices[367520] is not None and prices[367520].final_cents == 499
    assert prices[570] is None  # gratis
    assert 999 not in prices  # Steam no lo encontró
    ((_, params),) = session.calls
    assert params == {"appids": "570,999,367520", "filters": "price_overview", "cc": "ar", "l": "spanish"}


async def test_prices_are_requested_in_chunks():
    client, session = _client({"api/appdetails": _prices_payload})
    await client.prices(range(250))
    assert [len(params["appids"].split(",")) for _, params in session.calls] == [100, 100, 50]


async def test_prices_keep_the_chunks_that_worked():
    def flaky(params: dict[str, str]) -> object:
        if params["appids"].startswith("0,"):
            return ["respuesta", "rota"]
        return _prices_payload(params)

    client, _ = _client({"api/appdetails": flaky})
    prices = await client.prices([*range(100), 367520])
    assert set(prices) == {367520}


async def test_prices_raise_when_nothing_could_be_fetched():
    client, _ = _client({"api/appdetails": aiohttp.ClientError()})
    with pytest.raises(SteamError):
        await client.prices({367520})


async def test_prices_of_nothing_makes_no_request():
    client, session = _client({})
    assert await client.prices(set()) == {}
    assert session.calls == []


# ── Respuestas con forma inesperada ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("route", "ref"),
    [
        ("api/appdetails", ItemRef.app(367520)),
        ("api/packagedetails", ItemRef(ItemKind.PACKAGE, 469)),
    ],
)
async def test_details_with_unexpected_shape_raise_steam_error(route: str, ref: ItemRef):
    client, _ = _client({route: [], "curator": CURATOR})
    with pytest.raises(SteamError):
        await client.get_item(ref)


async def test_bundle_with_unexpected_shape_raises_steam_error():
    client, _ = _client({"ajaxresolvebundles": {"error": "algo"}})
    with pytest.raises(SteamError):
        await client.get_item(ItemRef(ItemKind.BUNDLE, 232))


async def test_null_details_mean_the_item_does_not_exist():
    client, _ = _client({"api/appdetails": None, "curator": CURATOR})
    assert await client.get_item(ItemRef.app(367520)) is None


async def test_search_and_deals_with_unexpected_shape_raise_steam_error():
    client, _ = _client({"storesearch": ["x"], "featuredcategories": "texto"})
    with pytest.raises(SteamError):
        await client.search("juego")
    with pytest.raises(SteamError):
        await client.featured_deals()


async def test_unexpected_reviews_are_skipped_like_a_failure():
    client, _ = _client({"api/appdetails": APP, "appreviews": ["x"], "curator": CURATOR})
    item = await client.get_item(ItemRef.app(367520))
    assert item is not None and item.reviews is None
