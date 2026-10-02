from unittest.mock import MagicMock

import discord
import pytest
from fakes import AUTUMN_SALE, FakeBot, FakeSteam, make_message, sent_kwargs
from helpers import make_item

from vapora.cogs.links import LinksCog
from vapora.pricing import ExchangeRates
from vapora.steam import ItemKind
from vapora.storage import Database
from vapora.ui.buttons import WishButton

HOLLOW_KNIGHT = make_item(367520, "Hollow Knight", price_cents=499)
ORANGE_BOX = make_item(469, "The Orange Box", kind=ItemKind.PACKAGE, price_cents=1049)
LINK = "https://store.steampowered.com/app/367520/Hollow_Knight/"


@pytest.fixture
def bot(db: Database) -> FakeBot:
    return FakeBot(db, FakeSteam(HOLLOW_KNIGHT, ORANGE_BOX))


async def test_replies_to_a_steam_link_with_card_and_buttons(bot: FakeBot):
    message = make_message(f"Miren esto {LINK}")
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]

    reply = sent_kwargs(message.reply)
    assert reply["mention_author"] is False
    (card,) = reply["embeds"]
    assert card.title == "🇦🇷 Hollow Knight"
    assert [field.name for field in card.fields] == ["💵 Precio Steam (AR)", "💳 Mercado Pago", "🟣 ARQ"]
    labels = [
        child.item.label if isinstance(child, WishButton) else child.label for child in reply["view"].children
    ]
    assert labels == ["🔔 Avisame si baja", "🌐 Abrir en el navegador"]


async def test_hides_discord_preview_of_the_original_message(bot: FakeBot):
    message = make_message(LINK)
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
    message.edit.assert_awaited_once_with(suppress=True)


async def test_several_links_are_answered_in_one_message(bot: FakeBot):
    message = make_message(f"{LINK} y https://store.steampowered.com/sub/469/")
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
    message.reply.assert_awaited_once()
    assert [card.title for card in sent_kwargs(message.reply)["embeds"]] == [
        "🇦🇷 Hollow Knight",
        "🇦🇷 The Orange Box",
    ]


async def test_ignores_messages_without_links_and_from_bots(bot: FakeBot):
    for message in (make_message("hola"), make_message(LINK, from_bot=True)):
        await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
        message.reply.assert_not_awaited()


async def test_unknown_game_gets_no_reply(bot: FakeBot):
    message = make_message("https://store.steampowered.com/app/999999999/")
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
    message.reply.assert_not_awaited()
    message.edit.assert_not_awaited()


async def test_steam_down_gets_no_reply_and_no_crash(bot: FakeBot):
    bot.steam.down = True
    message = make_message(LINK)
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
    message.reply.assert_not_awaited()


async def test_replies_without_peso_prices_when_rates_are_unavailable(bot: FakeBot):
    bot.rates = ExchangeRates()
    message = make_message(LINK)
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
    (card,) = sent_kwargs(message.reply)["embeds"]
    assert [field.name for field in card.fields] == ["💵 Precio Steam (AR)"]


async def test_at_most_ten_cards_per_message(db: Database):
    games = [make_item(app_id, f"Juego {app_id}") for app_id in range(1, 13)]
    message = make_message(" ".join(f"https://store.steampowered.com/app/{game.ref.id}/" for game in games))
    await LinksCog(FakeBot(db, FakeSteam(*games))).on_message(message)  # type: ignore[arg-type]
    assert len(sent_kwargs(message.reply)["embeds"]) == 10


async def test_missing_manage_messages_permission_is_not_an_error(bot: FakeBot):
    message = make_message(LINK)
    message.edit.side_effect = discord.Forbidden(MagicMock(status=403), "sin permiso")
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
    message.reply.assert_awaited_once()  # la tarjeta se envió igual


async def test_cards_use_the_sale_color_while_a_sale_is_running(bot: FakeBot):
    message = make_message(LINK)
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
    (regular,) = sent_kwargs(message.reply)["embeds"]

    bot.sale = AUTUMN_SALE
    await LinksCog(bot).on_message(message)  # type: ignore[arg-type]
    (seasonal,) = sent_kwargs(message.reply)["embeds"]

    assert regular.color.value == 0x74ACDF  # celeste de siempre
    assert seasonal.color.value == 0xE67E22  # naranja de otoño
