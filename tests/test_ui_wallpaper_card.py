import discord

from vapora.steam.workshop import WALLPAPER_ENGINE_STORE_URL, Wallpaper
from vapora.ui.style import WALLPAPER_COLOR
from vapora.ui.wallpaper_card import add_wallpaper_buttons, build_wallpaper_buttons, build_wallpaper_card

WALLPAPER = Wallpaper(
    100,
    "Lago al atardecer",
    "https://img/lago.gif",
    ("Scene", "Landscape", "Nature", "Everyone", "3840 x 2160", "Audio responsive"),
    subscriptions=109742,
    favorites=5300,
)


def _rows(view: discord.ui.View) -> list[tuple[int | None, str | None]]:
    return [(button.row, button.label) for button in view.children]  # type: ignore[attr-defined]


def test_card_shows_preview_stats_and_details():
    card = build_wallpaper_card(WALLPAPER)
    assert card.title == "🖼️ Lago al atardecer"
    assert card.url == "https://steamcommunity.com/sharedfiles/filedetails/?id=100"
    assert card.image.url == "https://img/lago.gif"
    assert card.color == WALLPAPER_COLOR
    assert card.description == "🎨 Paisaje · Naturaleza\n🔊 Reacciona al audio"
    assert [(field.name, field.value) for field in card.fields] == [
        ("👥 Suscriptores", "109.742"),
        ("❤️ Favoritos", "5.300"),
        ("🖥️ Tipo", "Escena · 3840 x 2160"),
    ]
    assert "Wallpaper Engine" in (card.footer.text or "")


def test_card_without_optional_data():
    card = build_wallpaper_card(Wallpaper(1, "Simple", tags=("Everyone",)), title_prefix="🖼️ Fondo del día ·")
    assert card.title == "🖼️ Fondo del día · Simple"
    assert card.description is None
    assert card.image.url is None
    assert [field.name for field in card.fields] == ["👥 Suscriptores", "❤️ Favoritos"]


def test_single_wallpaper_buttons_share_one_row():
    view = build_wallpaper_buttons([WALLPAPER])
    assert _rows(view) == [(0, "🖼️ Ver en Steam"), (0, "🛒 Conseguir Wallpaper Engine")]
    assert view.children[1].url == WALLPAPER_ENGINE_STORE_URL  # type: ignore[attr-defined]


def test_several_wallpapers_get_one_row_each_and_the_store_last():
    other = Wallpaper(2, "Otro", tags=("Everyone",))
    view = discord.ui.View()
    add_wallpaper_buttons(view, [WALLPAPER, other], first_row=1)
    assert _rows(view) == [
        (1, "🖼️ Lago al atardecer"),
        (2, "🖼️ Otro"),
        (3, "🛒 Conseguir Wallpaper Engine"),
    ]


def test_buttons_that_do_not_fit_are_left_for_discord_to_place():
    many = [Wallpaper(i, f"Fondo {i}", tags=("Everyone",)) for i in range(4)]
    view = discord.ui.View()
    add_wallpaper_buttons(view, many, first_row=3)
    assert {row for row, _ in _rows(view)} == {None}
    assert len(view.children) == 5


def test_long_titles_are_clipped_to_discord_limit():
    long = Wallpaper(3, "x" * 200, tags=("Everyone",))
    view = discord.ui.View()
    add_wallpaper_buttons(view, [WALLPAPER, long], first_row=0)
    assert all(len(label or "") <= 80 for _, label in _rows(view))


def test_no_wallpapers_no_buttons():
    assert build_wallpaper_buttons([]).children == []
