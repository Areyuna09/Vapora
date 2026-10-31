from datetime import UTC, datetime, timedelta

import discord
import pytest
from fakes import FakeBot, FakeSteam, sent_kwargs, sent_text
from helpers import make_item

from vapora.cogs import free_games as free_games_module
from vapora.cogs.free_games import MAX_NOTICES_PER_CHECK, REPEAT_AFTER_DAYS, FreeGamesCog
from vapora.storage import Database, Feature

GUILD, CHANNEL = 10, 700
NOW = datetime(2026, 10, 31, 15, tzinfo=UTC)
ASLEEP = make_item(1583850, "Asleep: Acto 1", price_cents=0, initial_cents=579, discount=100)
DLC = make_item(4693960, "Pack gratis", price_cents=0, initial_cents=329, discount=100, is_dlc=True)
PAID = make_item(367520, "Hollow Knight", price_cents=499)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(free_games_module, "_now", lambda: NOW)


@pytest.fixture
async def bot(db: Database) -> FakeBot:
    bot = FakeBot(db, FakeSteam(ASLEEP, DLC, PAID))
    bot.steam.free_promo_ids = [ASLEEP.ref.id]
    await db.set_channel(GUILD, Feature.FREE_GAMES, CHANNEL)
    return bot


async def test_free_game_is_announced_with_card_and_claim_button(bot: FakeBot):
    channel = bot.add_channel(CHANNEL)
    await FreeGamesCog(bot).check_free_games()  # type: ignore[arg-type]
    assert sent_text(channel.send) == "🎁 ¡**Asleep: Acto 1** está gratis en Steam por tiempo limitado!"
    sent = sent_kwargs(channel.send)
    assert sent["embed"].fields[0].value == "**Gratis**\n~~USD 5,79~~ (-100%)"
    (button,) = sent["view"].children
    assert (button.label, button.url) == ("🎁 Reclamar", ASLEEP.ref.url)


async def test_same_game_is_announced_only_once(bot: FakeBot):
    channel = bot.add_channel(CHANNEL)
    cog = FreeGamesCog(bot)  # type: ignore[arg-type]
    await cog.check_free_games()
    await cog.check_free_games()
    channel.send.assert_awaited_once()


async def test_game_free_again_later_is_announced_again(bot: FakeBot, monkeypatch: pytest.MonkeyPatch):
    channel = bot.add_channel(CHANNEL)
    cog = FreeGamesCog(bot)  # type: ignore[arg-type]
    await cog.check_free_games()
    later = NOW + timedelta(days=REPEAT_AFTER_DAYS, minutes=1)
    monkeypatch.setattr(free_games_module, "_now", lambda: later)
    await cog.check_free_games()
    assert channel.send.await_count == 2


async def test_dlc_and_paid_games_are_not_announced(bot: FakeBot):
    channel = bot.add_channel(CHANNEL)
    bot.steam.free_promo_ids = [DLC.ref.id, PAID.ref.id, 999]  # 999: ya no existe
    await FreeGamesCog(bot).check_free_games()  # type: ignore[arg-type]
    channel.send.assert_not_awaited()


async def test_data_is_requested_fresh_and_once_per_check(bot: FakeBot, db: Database):
    await db.set_channel(11, Feature.FREE_GAMES, 701)
    first, second = bot.add_channel(CHANNEL), bot.add_channel(701)
    await FreeGamesCog(bot).check_free_games()  # type: ignore[arg-type]
    assert bot.steam.refreshed == [ASLEEP.ref]
    first.send.assert_awaited_once()
    second.send.assert_awaited_once()


async def test_failed_notice_is_retried(bot: FakeBot):
    channel = bot.add_channel(CHANNEL)
    channel.send.side_effect = discord.HTTPException(type("R", (), {"status": 500, "reason": "x"})(), "falló")
    cog = FreeGamesCog(bot)  # type: ignore[arg-type]
    await cog.check_free_games()
    channel.send.side_effect = None
    await cog.check_free_games()
    assert channel.send.await_count == 2


async def test_many_free_games_do_not_flood_the_channel(bot: FakeBot):
    channel = bot.add_channel(CHANNEL)
    games = [
        make_item(i, f"Juego {i}", price_cents=0, initial_cents=100, discount=100)
        for i in range(1, MAX_NOTICES_PER_CHECK + 3)
    ]
    bot.steam.items.update({game.ref: game for game in games})
    bot.steam.free_promo_ids = [game.ref.id for game in games]
    cog = FreeGamesCog(bot)  # type: ignore[arg-type]
    await cog.check_free_games()
    assert channel.send.await_count == MAX_NOTICES_PER_CHECK
    await cog.check_free_games()  # los que faltaban salen en la próxima revisión
    assert channel.send.await_count == len(games)


async def test_steam_down_or_no_channel_does_nothing(bot: FakeBot, db: Database):
    channel = bot.add_channel(CHANNEL)
    bot.steam.down = True
    await FreeGamesCog(bot).check_free_games()  # type: ignore[arg-type]
    channel.send.assert_not_awaited()

    bot.steam.down = False
    await db.set_channel(GUILD, Feature.FREE_GAMES, None)
    await FreeGamesCog(bot).check_free_games()  # type: ignore[arg-type]
    channel.send.assert_not_awaited()
