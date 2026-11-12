import discord
import pytest

from vapora.steam.workshop import WorkshopMod
from vapora.ui.mod_card import add_mod_buttons, build_mod_card, format_size
from vapora.ui.style import MOD_COLOR

RACKS = WorkshopMod(
    id=3835057498,
    app_id=108600,
    title="Johnson's Weapon Racks",
    preview_url="https://images.steamusercontent.com/ugc/1/racks.png",
    tags=("Build 42", "building", "Items", "Language/Translation", "Models", "Textures", "Weapons"),
    subscriptions=19008,
    favorites=1200,
    file_size=7_340_032,
    updated_at=1790000000,
)


def test_card_shows_image_game_tags_and_numbers():
    card = build_mod_card(RACKS, "Project Zomboid")
    assert card.title == "🧩 Johnson's Weapon Racks"
    assert card.url == "https://steamcommunity.com/sharedfiles/filedetails/?id=3835057498"
    assert card.image.url == "https://images.steamusercontent.com/ugc/1/racks.png"
    assert card.color == MOD_COLOR
    assert card.description == (
        "🎮 Mod de **Project Zomboid**\n"
        "🏷️ Build 42 · building · Items · Language/Translation · Models · Textures"
    )
    assert [(field.name, field.value) for field in card.fields] == [
        ("👥 Suscriptores", "19.008"),
        ("❤️ Favoritos", "1.200"),
        ("🔄 Actualizado", "<t:1790000000:D>"),
        ("📦 Tamaño", "7 MB"),
    ]


def test_card_without_optional_data():
    card = build_mod_card(WorkshopMod(id=1, app_id=108600, title="Colección"))
    assert card.description is None
    assert card.image.url is None
    assert [field.name for field in card.fields] == ["👥 Suscriptores", "❤️ Favoritos"]


@pytest.mark.parametrize(
    ("size", "text"),
    [(500, "500 B"), (1536, "1,5 KB"), (7_340_032, "7 MB"), (734_003_200, "700 MB"), (3_221_225_472, "3 GB")],
)
def test_sizes_in_argentine_format(size: int, text: str):
    assert format_size(size) == text


def test_one_mod_gets_a_simple_button():
    view = discord.ui.View()
    add_mod_buttons(view, [RACKS], first_row=1)
    (button,) = view.children
    assert (button.label, button.url, button.row) == ("🧩 Ver en Steam", RACKS.url, 1)  # type: ignore[attr-defined]


def test_several_mods_get_one_row_each_with_their_names():
    other = WorkshopMod(id=2, app_id=108600, title="x" * 200)
    view = discord.ui.View()
    add_mod_buttons(view, [RACKS, other], first_row=0)
    labels_and_rows = [(button.label, button.row) for button in view.children]  # type: ignore[attr-defined]
    assert labels_and_rows[0] == ("🧩 Johnson's Weapon Racks", 0)
    assert labels_and_rows[1][1] == 1
    assert len(labels_and_rows[1][0] or "") <= 80


def test_mod_buttons_that_do_not_fit_are_left_for_discord_to_place():
    mods = [WorkshopMod(id=i, app_id=108600, title=f"Mod {i}") for i in range(3)]
    view = discord.ui.View()
    add_mod_buttons(view, mods, first_row=3)
    assert {button.row for button in view.children} == {None}  # type: ignore[attr-defined]
