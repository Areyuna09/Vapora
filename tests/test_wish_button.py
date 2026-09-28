import asyncio
import re

import discord

from bot import WishButton, build_card_buttons
from steam import parse_app_data, parse_bundle_data


def _game(app_id, name, price=999, free=False):
    data = {"name": name, "is_free": free}
    if price is not None:
        data["price_overview"] = {"currency": "USD", "initial": price, "final": price, "discount_percent": 0}
    return parse_app_data(app_id, data)


def _view(games):
    async def build():  # discord.ui.View necesita un event loop activo
        return build_card_buttons(games)
    return asyncio.run(build())


def _buttons(view):
    return [child.item if isinstance(child, WishButton) else child for child in view.children]


def test_single_game_has_wish_and_browser_buttons():
    buttons = _buttons(_view([_game(367520, "Hollow Knight")]))
    assert [b.label for b in buttons] == ["🔔 Avisame si baja", "🌐 Abrir en el navegador"]
    assert buttons[0].custom_id == "vapora:wish:367520"
    assert buttons[1].style == discord.ButtonStyle.link
    assert buttons[1].url == "https://store.steampowered.com/app/367520/"


def test_free_game_and_bundle_only_get_browser_button():
    bundle = parse_bundle_data(232, {"name": "Pack", "final_price": 6824, "formatted_final_price": "$68.24 USD"})
    for game, url in ((_game(730, "CS2", price=None, free=True), "app/730/"), (bundle, "bundle/232/")):
        buttons = _buttons(_view([game]))
        assert [b.label for b in buttons] == ["🌐 Abrir en el navegador"]
        assert buttons[0].url.endswith(url)


def test_multiple_games_one_row_each():
    games = [_game(1, "Juego pago"), _game(730, "Counter-Strike 2", price=None, free=True)]
    buttons = _buttons(_view(games))
    assert [(b.label, b.row) for b in buttons] == [
        ("🔔 Juego pago", 0), ("🌐 Abrir", 0), ("🌐 Counter-Strike 2", 1),
    ]


def test_many_games_fit_discord_limits():
    view = _view([_game(i, f"Juego {i}") for i in range(10)])  # máximo de tarjetas por mensaje
    assert len(view.children) == 20


def test_no_buttons_without_games():
    assert _view([]) is None


def test_custom_id_matches_template_for_restarts():
    match = re.fullmatch(WishButton.__discord_ui_compiled_template__, "vapora:wish:1057090")
    assert match and match["app_id"] == "1057090"
