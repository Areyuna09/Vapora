import asyncio

import storage
import wishlist
from wishlist import offer_action, resolve_game

ON_SALE = {"discount_percent": 50, "final_cents": 1000}
CHEAPER = {"discount_percent": 70, "final_cents": 600}
FULL_PRICE = {"discount_percent": 0, "final_cents": 2000}


def test_notifies_when_sale_starts():
    assert offer_action(None, ON_SALE) == ("notify", 1000)


def test_does_not_repeat_same_sale():
    assert offer_action(1000, ON_SALE) is None


def test_notifies_again_if_price_drops_further():
    assert offer_action(1000, CHEAPER) == ("notify", 600)


def test_resets_when_sale_ends_so_next_one_is_notified():
    assert offer_action(1000, FULL_PRICE) == ("reset", None)
    assert offer_action(None, FULL_PRICE) is None
    assert offer_action(None, ON_SALE) == ("notify", 1000)


def test_free_or_unpriced_games_never_notify():
    assert offer_action(None, {"is_free": True}) is None
    assert offer_action(None, {"discount_percent": 0, "final_cents": None}) is None


def test_resolve_game_from_id_link_and_name(monkeypatch):
    async def fake_search(term, limit=10):
        return [{"id": 367520, "name": "Hollow Knight"}] if "hollow" in term.lower() else []
    monkeypatch.setattr(wishlist, "search_store", fake_search)

    assert asyncio.run(resolve_game("367520")) == (367520, None)
    assert asyncio.run(resolve_game("https://store.steampowered.com/app/1030300/Silksong/")) == (1030300, None)
    assert asyncio.run(resolve_game("hollow knight")) == (367520, "Hollow Knight")
    assert asyncio.run(resolve_game("juego que no existe")) is None


def test_wishlist_storage():
    assert storage.add_wish(1, 367520, "Hollow Knight", 99)
    assert not storage.add_wish(1, 367520, "Hollow Knight", 99)  # repetido
    storage.set_wish_notified(1, 367520, 249)
    assert storage.get_wishlist(1) == {367520: {"name": "Hollow Knight", "guild_id": 99, "notified_final": 249}}
    assert storage.remove_wish(1, 367520) == "Hollow Knight"
    assert storage.remove_wish(1, 367520) is None
    assert storage.all_wishlists() == {}


def test_wishlist_limit():
    for app_id in range(storage.MAX_WISHLIST):
        assert storage.add_wish(1, app_id, f"Juego {app_id}", None)
    assert not storage.add_wish(1, 999, "Uno más", None)
