import aiohttp
import pytest
from helpers import FakeSession

from vapora.steam import SteamError
from vapora.steam.workshop import (
    WALLPAPER_ENGINE_APP_ID,
    Wallpaper,
    WorkshopClient,
    extract_workshop_ids,
    parse_browse_ids,
    parse_wallpapers,
)

NIKKE = {
    "publishedfileid": "3594441070",
    "result": 1,
    "consumer_app_id": WALLPAPER_ENGINE_APP_ID,
    "preview_url": "https://images.steamusercontent.com/ugc/1/preview.gif",
    "title": "Nikke Moran Off-duty Queen",
    "visibility": 0,
    "banned": 0,
    "subscriptions": 5265,
    "favorited": 404,
    "tags": [
        {"tag": "Wallpaper"},
        {"tag": "Web"},
        {"tag": "Anime"},
        {"tag": "Everyone"},
        {"tag": "Customizable"},
    ],
}
LANDSCAPE = {
    **NIKKE,
    "publishedfileid": "100",
    "title": "Lago al atardecer",
    "tags": [{"tag": "Scene"}, {"tag": "Landscape"}, {"tag": "Everyone"}, {"tag": "3840 x 2160"}],
}


def _details(*entries: dict) -> dict:
    return {"response": {"result": 1, "resultcount": len(entries), "publishedfiledetails": list(entries)}}


def _browse_page(*ids: int) -> str:
    links = "".join(
        f'<a href="https://steamcommunity.com/sharedfiles/filedetails/?id={i}&searchtext=">x</a>' for i in ids
    )
    return f"<html>{links}{links}</html>"  # cada ítem aparece más de una vez, como en la página real


# ── Links ─────────────────────────────────────────────────────────────────────


def test_extract_workshop_ids_from_both_link_formats():
    text = (
        "miren https://steamcommunity.com/sharedfiles/filedetails/?id=3594441070 y "
        "https://steamcommunity.com/workshop/filedetails/?searchtext=x&id=100 "
        "otra vez https://steamcommunity.com/sharedfiles/filedetails/?id=3594441070"
    )
    assert extract_workshop_ids(text) == [3594441070, 100]


def test_other_links_are_not_workshop_items():
    assert (
        extract_workshop_ids(
            "https://store.steampowered.com/app/431960/ y https://steamcommunity.com/id/alguien"
        )
        == []
    )


# ── Parsers ───────────────────────────────────────────────────────────────────


def test_parse_browse_ids_keeps_page_order_without_repeats():
    assert parse_browse_ids(_browse_page(30, 10, 20)) == [30, 10, 20]


def test_parse_wallpapers():
    (wallpaper,) = parse_wallpapers(_details(NIKKE))
    assert wallpaper == Wallpaper(
        id=3594441070,
        title="Nikke Moran Off-duty Queen",
        preview_url="https://images.steamusercontent.com/ugc/1/preview.gif",
        tags=("Wallpaper", "Web", "Anime", "Everyone", "Customizable"),
        subscriptions=5265,
        favorites=404,
    )
    assert wallpaper.url == "https://steamcommunity.com/sharedfiles/filedetails/?id=3594441070"


@pytest.mark.parametrize(
    "entry",
    [
        {**NIKKE, "tags": [{"tag": "Anime"}, {"tag": "Mature"}]},  # no es para todo público
        {**NIKKE, "tags": [{"tag": "Anime"}, {"tag": "Questionable"}]},
        {**NIKKE, "tags": []},
        {**NIKKE, "consumer_app_id": 4000},  # Workshop de otro juego
        {**NIKKE, "banned": 1},
        {**NIKKE, "visibility": 2},  # oculto
        {"publishedfileid": "1", "result": 9},  # no existe
    ],
)
def test_parse_wallpapers_skips_what_should_not_be_shown(entry: dict):
    assert parse_wallpapers(_details(entry)) == []


@pytest.mark.parametrize("payload", [None, [], {"response": []}, {"response": {"publishedfiledetails": {}}}])
def test_parse_wallpapers_tolerates_unexpected_shapes(payload: object):
    assert parse_wallpapers(payload) == []


def test_wallpaper_details_in_spanish():
    (anime,) = parse_wallpapers(_details(NIKKE))
    (landscape,) = parse_wallpapers(_details(LANDSCAPE))
    assert (anime.genres, anime.kind, anime.resolution, anime.features) == (
        ("Anime",),
        "Web",
        None,
        ("⚙️ Personalizable",),
    )
    assert (landscape.genres, landscape.kind, landscape.resolution) == (("Paisaje",), "Escena", "3840 x 2160")


# ── Cliente ───────────────────────────────────────────────────────────────────


def _client(routes: dict) -> tuple[WorkshopClient, FakeSession]:
    session = FakeSession(routes)
    return WorkshopClient(session), session  # type: ignore[arg-type]


async def test_trending_reads_the_page_and_then_the_details():
    client, session = _client(
        {
            "workshop/browse": _browse_page(3594441070, 100),
            "GetPublishedFileDetails": _details(NIKKE, LANDSCAPE),
        }
    )
    wallpapers = await client.trending()
    assert [wallpaper.id for wallpaper in wallpapers] == [3594441070, 100]

    (_, browse_params), (_, details_data) = session.calls
    assert ("appid", "431960") in browse_params
    assert ("browsesort", "trend") in browse_params
    assert [value for key, value in browse_params if key == "requiredtags[]"] == ["Everyone"]
    assert details_data == {
        "publishedfileids[0]": "3594441070",
        "publishedfileids[1]": "100",
        "itemcount": "2",
    }


async def test_trending_by_category_asks_for_that_tag_and_double_checks_it():
    client, session = _client(
        {
            "workshop/browse": _browse_page(3594441070, 100),
            "GetPublishedFileDetails": _details(NIKKE, LANDSCAPE),
        }
    )
    wallpapers = await client.trending("paisaje")
    assert [wallpaper.title for wallpaper in wallpapers] == ["Lago al atardecer"]  # Nikke no es paisaje
    _, browse_params = session.calls[0]
    assert [value for key, value in browse_params if key == "requiredtags[]"] == ["Everyone", "Landscape"]


async def test_trending_is_cached_per_category():
    client, session = _client(
        {"workshop/browse": _browse_page(3594441070), "GetPublishedFileDetails": _details(NIKKE)}
    )
    await client.trending()
    await client.trending()
    await client.trending("anime")
    assert session.count("workshop/browse") == 2


async def test_trending_with_an_unreadable_page_is_empty():
    client, session = _client({"workshop/browse": "<html>otro formato</html>"})
    assert await client.trending() == ()
    assert session.count("GetPublishedFileDetails") == 0


@pytest.mark.parametrize("route", ["workshop/browse", "GetPublishedFileDetails"])
async def test_trending_raises_steam_error_when_steam_is_down(route: str):
    routes = {"workshop/browse": _browse_page(1), "GetPublishedFileDetails": _details(NIKKE)}
    routes[route] = aiohttp.ClientError()
    client, _ = _client(routes)
    with pytest.raises(SteamError):
        await client.trending()


async def test_get_one_wallpaper_and_cache_it():
    client, session = _client({"GetPublishedFileDetails": _details(NIKKE)})
    first = await client.get(3594441070)
    assert first is not None and first.title == "Nikke Moran Off-duty Queen"
    assert await client.get(3594441070) == first
    assert session.count("GetPublishedFileDetails") == 1


async def test_get_mature_wallpaper_is_none():
    mature = {**NIKKE, "tags": [{"tag": "Mature"}]}
    client, _ = _client({"GetPublishedFileDetails": _details(mature)})
    assert await client.get(3594441070) is None


async def test_wallpapers_seen_in_trending_need_no_extra_request():
    client, session = _client(
        {"workshop/browse": _browse_page(3594441070), "GetPublishedFileDetails": _details(NIKKE)}
    )
    await client.trending()
    await client.get(3594441070)
    assert session.count("GetPublishedFileDetails") == 1
