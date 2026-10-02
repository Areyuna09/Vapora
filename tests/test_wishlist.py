from vapora.steam import Price, SearchResult
from vapora.wishlist import OfferAction, offer_action, resolve_app_id

ON_SALE = Price(1000, 2000, 50, "USD")
CHEAPER = Price(600, 2000, 70, "USD")
FULL_PRICE = Price(2000, 2000, 0, "USD")


# ── Cuándo avisar ─────────────────────────────────────────────────────────────


def test_notifies_when_a_sale_starts():
    assert offer_action(None, ON_SALE) is OfferAction.NOTIFY


def test_does_not_repeat_the_same_sale():
    assert offer_action(1000, ON_SALE) is None


def test_notifies_again_if_the_price_drops_further():
    assert offer_action(1000, CHEAPER) is OfferAction.NOTIFY


def test_does_not_notify_if_the_discount_shrinks():
    assert offer_action(600, ON_SALE) is None


def test_resets_when_the_sale_ends_so_the_next_one_is_notified():
    assert offer_action(1000, FULL_PRICE) is OfferAction.RESET
    assert offer_action(None, FULL_PRICE) is None
    assert offer_action(None, ON_SALE) is OfferAction.NOTIFY


def test_games_without_price_never_notify():
    assert offer_action(None, None) is None
    assert offer_action(1000, None) is OfferAction.RESET  # dejó de tener precio: se olvida el aviso


# ── Qué juego eligió el usuario ───────────────────────────────────────────────


class FakeSteam:
    def __init__(self) -> None:
        self.searches: list[str] = []

    async def search(self, term: str, *, limit: int = 10) -> list[SearchResult]:
        self.searches.append(term)
        return [SearchResult(367520, "Hollow Knight")] if "hollow" in term.lower() else []


async def test_autocomplete_choice_is_already_an_app_id():
    steam = FakeSteam()
    assert await resolve_app_id(" 367520 ", steam) == 367520  # type: ignore[arg-type]
    assert steam.searches == []


async def test_store_link():
    steam = FakeSteam()
    link = "https://store.steampowered.com/app/1030300/Silksong/"
    assert await resolve_app_id(link, steam) == 1030300  # type: ignore[arg-type]
    assert steam.searches == []


async def test_name_takes_first_search_result():
    assert await resolve_app_id("hollow knight", FakeSteam()) == 367520  # type: ignore[arg-type]


async def test_unknown_name():
    assert await resolve_app_id("juego que no existe", FakeSteam()) is None  # type: ignore[arg-type]


async def test_bundle_link_is_not_a_game():
    link = "https://store.steampowered.com/bundle/232/"
    assert await resolve_app_id(link, FakeSteam()) is None  # type: ignore[arg-type]
