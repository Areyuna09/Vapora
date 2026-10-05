from vapora.steam import Price, SearchResult
from vapora.storage import Wish
from vapora.wishlist import OfferAction, find_wish, offer_action, resolve_app_id

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
        if term == "1942":
            return [SearchResult(220, "1942")]
        return [SearchResult(367520, "Hollow Knight")] if "hollow" in term.lower() else []


async def test_autocomplete_choice_carries_the_app_id():
    steam = FakeSteam()
    assert await resolve_app_id(" app:367520 ", steam) == 367520  # type: ignore[arg-type]
    assert steam.searches == []


async def test_a_typed_number_is_searched_as_a_name_first():
    """Un juego puede llamarse "1942": no se confunde con el AppID 1942."""
    assert await resolve_app_id("1942", FakeSteam()) == 220  # type: ignore[arg-type]


async def test_a_typed_app_id_still_works_when_no_name_matches():
    steam = FakeSteam()
    assert await resolve_app_id("367520", steam) == 367520  # type: ignore[arg-type]
    assert steam.searches == ["367520"]


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


# ── Qué deseado quiere quitar ─────────────────────────────────────────────────

WISHES = [
    Wish(5, 367520, "Hollow Knight", None, None),
    Wish(5, 1057090, "Ori and the Will of the Wisps", None, None),
    Wish(5, 2100, "Ori and the Blind Forest", None, None),
    Wish(5, 220, "1942", None, None),
]


def test_find_wish_by_autocomplete_choice():
    assert find_wish(WISHES, "app:367520") == WISHES[0]
    assert find_wish(WISHES, "app:999") is None


def test_find_wish_by_typed_name():
    assert find_wish(WISHES, "  hollow KNIGHT ") == WISHES[0]  # exacto, sin importar mayúsculas
    assert find_wish(WISHES, "hollow") == WISHES[0]  # parte del nombre
    assert find_wish(WISHES, "1942") == WISHES[3]  # el nombre gana sobre el AppID


def test_find_wish_does_not_guess_between_several_matches():
    assert find_wish(WISHES, "ori") is None
    assert find_wish(WISHES, "") is None


def test_find_wish_by_typed_app_id():
    assert find_wish(WISHES, "1057090") == WISHES[1]
    assert find_wish(WISHES, "123") is None
