import re

import discord
from helpers import make_item

from vapora.pricing import Taxes
from vapora.steam import ItemKind
from vapora.storage import Feature, Wish
from vapora.ui.buttons import WishButton, build_card_buttons
from vapora.ui.panels import build_config_embed, build_help_embed, build_wishlist_embed


def buttons(view: discord.ui.View) -> list[discord.ui.Button]:
    return [child.item if isinstance(child, WishButton) else child for child in view.children]


# ── Botones de las tarjetas ───────────────────────────────────────────────────


async def test_single_game_has_wish_and_browser_buttons():
    wish, browser = buttons(build_card_buttons([make_item(367520, "Hollow Knight")]))
    assert (wish.label, wish.custom_id) == ("🔔 Avisame si baja", "vapora:wish:367520")
    assert (browser.label, browser.style) == ("🌐 Abrir en el navegador", discord.ButtonStyle.link)
    assert browser.url == "https://store.steampowered.com/app/367520/"


async def test_free_game_and_bundle_only_get_the_browser_button():
    free = make_item(730, "CS2", price_cents=None, is_free=True)
    bundle = make_item(232, "Pack", kind=ItemKind.BUNDLE, price_cents=6824)
    for item, url_end in ((free, "app/730/"), (bundle, "bundle/232/")):
        (browser,) = buttons(build_card_buttons([item]))
        assert browser.label == "🌐 Abrir en el navegador"
        assert browser.url.endswith(url_end)


async def test_several_games_get_one_row_each_with_their_names():
    items = [make_item(1, "Juego pago"), make_item(730, "Counter-Strike 2", price_cents=None, is_free=True)]
    assert [(button.label, button.row) for button in buttons(build_card_buttons(items))] == [
        ("🔔 Juego pago", 0),
        ("🌐 Abrir", 0),
        ("🌐 Counter-Strike 2", 1),
    ]


async def test_ten_games_fit_within_discord_limits():
    view = build_card_buttons(
        [make_item(i, f"Juego {i}") for i in range(10)]
    )  # máximo de tarjetas por mensaje
    assert len(view.children) == 20


async def test_long_names_are_clipped_to_discord_label_limit():
    items = [make_item(1, "x" * 200), make_item(2, "Otro")]
    assert len(buttons(build_card_buttons(items))[0].label) == 80


async def test_no_items_no_buttons():
    assert build_card_buttons([]).children == []


def test_wish_button_id_survives_restarts():
    match = re.fullmatch(WishButton.__discord_ui_compiled_template__, "vapora:wish:1057090")
    assert match is not None and match["app_id"] == "1057090"


# ── /ayuda, /config y /deseado lista ──────────────────────────────────────────


def test_help_shows_admin_section_only_to_admins():
    admin = [
        field.name
        for field in build_help_embed(is_admin=True, taxes=Taxes(), rates_refresh_minutes=30).fields
    ]
    member = [
        field.name
        for field in build_help_embed(is_admin=False, taxes=Taxes(), rates_refresh_minutes=30).fields
    ]
    assert "⚙️ Administración" in admin
    assert "⚙️ Administración" not in member
    assert "🎮 Comandos" in member


def test_help_explains_prices_with_the_configured_iva():
    embed = build_help_embed(is_admin=False, taxes=Taxes(iva_percent=10.5), rates_refresh_minutes=15)
    assert "IVA 10.5%" in embed.fields[-1].value
    assert "cada 15 minutos" in embed.fields[-1].value


def test_config_embed_lists_every_feature():
    channels = {Feature.DEALS: 100, Feature.WISHLIST: 300, Feature.WALLPAPERS: 400}
    embed = build_config_embed(channels, deals_hour=12, wallpaper_hour=18)
    assert [(field.name, field.value) for field in embed.fields] == [
        ("🔥 Ofertas destacadas", "<#100>\nTodos los días a las 12:00 (hora argentina)"),
        ("📅 Avisos de rebajas", "Desactivado"),
        ("🔔 Avisos de deseados", "<#300>"),
        ("🖼️ Fondo del día", "<#400>\nTodos los días a las 18:00 (hora argentina)"),
    ]


def test_wishlist_embed_marks_games_on_sale():
    wishes = [Wish(5, 367520, "Hollow Knight", 10, None), Wish(5, 1057090, "Ori", 10, 299)]
    embed = build_wishlist_embed(wishes)
    assert embed.title == "📝 Tus deseados (2/25)"
    assert embed.description == (
        "• [Hollow Knight](https://store.steampowered.com/app/367520/)\n"
        "• [Ori](https://store.steampowered.com/app/1057090/) 🔥"
    )


async def test_wish_button_respects_the_usage_limit():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from vapora.ratelimit import RateLimits

    client = SimpleNamespace(limits=RateLimits(), dispatch=MagicMock())
    interaction = MagicMock(client=client)
    interaction.user.id = 5
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    button = WishButton(367520)
    for _ in range(10):
        await button.callback(interaction)
    assert interaction.response.defer.await_count == 8
    assert client.dispatch.call_count == 8
    interaction.response.send_message.assert_awaited_once()  # un solo "más despacio"
