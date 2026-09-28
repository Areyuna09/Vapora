import asyncio
import re

from bot import WishButton, build_wish_buttons
from steam import parse_app_data, parse_bundle_data


def _game(app_id, name, price=999, free=False):
    data = {"name": name, "is_free": free}
    if price is not None:
        data["price_overview"] = {"currency": "USD", "initial": price, "final": price, "discount_percent": 0}
    return parse_app_data(app_id, data)


def _view(games):
    async def build():  # discord.ui.View necesita un event loop activo
        return build_wish_buttons(games)
    return asyncio.run(build())


def test_single_game_has_generic_label():
    view = _view([_game(367520, "Hollow Knight")])
    assert [b.item.label for b in view.children] == ["🔔 Avisame si baja"]
    assert view.children[0].item.custom_id == "vapora:wish:367520"


def test_multiple_games_use_names_and_skip_free_and_bundles():
    bundle = parse_bundle_data(232, {"name": "Pack", "final_price": 6824, "formatted_final_price": "$68.24 USD"})
    games = [_game(1, "Juego pago"), _game(730, "Counter-Strike 2", price=None, free=True), bundle]
    view = _view(games)
    assert [b.item.label for b in view.children] == ["🔔 Juego pago"]


def test_no_buttons_when_nothing_to_wish():
    assert _view([_game(730, "CS2", price=None, free=True)]) is None


def test_custom_id_matches_template_for_restarts():
    match = re.fullmatch(WishButton.__discord_ui_compiled_template__, "vapora:wish:1057090")
    assert match and match["app_id"] == "1057090"
