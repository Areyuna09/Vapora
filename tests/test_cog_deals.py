from datetime import datetime, timedelta

import discord
import pytest
from fakes import AUTUMN_SALE, FakeBot, make_interaction, sent_kwargs

from vapora.cogs import deals as deals_module
from vapora.cogs._tasks import survives_errors
from vapora.cogs.deals import DealsCog
from vapora.config import Settings
from vapora.sales import ARGENTINA
from vapora.steam import Deal, ItemRef, Price
from vapora.storage import Database, Feature

GUILD, CHANNEL = 10, 100
DEAL = Deal(ItemRef.app(7), "Juego en oferta", Price(600, 1000, 40, "USD"))


@pytest.fixture
def bot(db: Database) -> FakeBot:
    bot = FakeBot(db)
    bot.steam.deals = [DEAL]
    return bot


@pytest.fixture
def before_sale(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """Fija "ahora" tres días antes de las Rebajas de Otoño."""
    now = AUTUMN_SALE.start - timedelta(days=3)
    monkeypatch.setattr(deals_module, "_now", lambda: now)
    return now


# ── /ofertas y /rebajas ───────────────────────────────────────────────────────


async def test_deals_command(bot: FakeBot, before_sale: datetime):
    interaction = make_interaction()
    cog = DealsCog(bot)  # type: ignore[arg-type]
    await cog.deals.callback(cog, interaction)
    interaction.response.defer.assert_awaited_once_with()
    embed = sent_kwargs(interaction.followup.send)["embed"]
    assert embed.title == "🔥 Ofertas destacadas de hoy"
    assert "Juego en oferta" in embed.description


async def test_deals_title_during_a_sale(bot: FakeBot, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(deals_module, "_now", lambda: AUTUMN_SALE.start + timedelta(days=1))
    interaction = make_interaction()
    cog = DealsCog(bot)  # type: ignore[arg-type]
    await cog.deals.callback(cog, interaction)
    assert sent_kwargs(interaction.followup.send)["embed"].title == "🍂 Ofertas destacadas · Rebajas de Otoño"


async def test_sales_command(bot: FakeBot, before_sale: datetime):
    interaction = make_interaction()
    cog = DealsCog(bot)  # type: ignore[arg-type]
    await cog.sales.callback(cog, interaction)
    embed = sent_kwargs(interaction.response.send_message)["embed"]
    assert [field.name for field in embed.fields] == ["🍂 Rebajas de Otoño"]


# ── Ofertas diarias ───────────────────────────────────────────────────────────


def test_daily_deals_hour_comes_from_settings(bot: FakeBot):
    bot.settings = Settings(discord_token="test", deals_hour=9)
    cog = DealsCog(bot)  # type: ignore[arg-type]
    (scheduled,) = cog.post_daily_deals.time
    assert (scheduled.hour, scheduled.tzinfo) == (9, ARGENTINA)


async def test_daily_deals_go_to_every_configured_channel(bot: FakeBot, db: Database, before_sale: datetime):
    await db.set_channel(GUILD, Feature.DEALS, CHANNEL)
    await db.set_channel(11, Feature.DEALS, 101)
    await db.set_channel(12, Feature.SALES, 102)  # este servidor no pidió ofertas diarias
    first, second, other = bot.add_channel(CHANNEL), bot.add_channel(101), bot.add_channel(102)

    await DealsCog(bot).post_daily_deals()  # type: ignore[arg-type]

    assert sent_kwargs(first.send)["embed"].title == "🔥 Ofertas destacadas de hoy"
    second.send.assert_awaited_once()
    other.send.assert_not_awaited()


async def test_daily_deals_skip_missing_channels_and_steam_outages(
    bot: FakeBot, db: Database, before_sale: datetime
):
    await db.set_channel(GUILD, Feature.DEALS, CHANNEL)  # canal borrado: el bot no lo encuentra
    await DealsCog(bot).post_daily_deals()  # type: ignore[arg-type]

    channel = bot.add_channel(CHANNEL)
    bot.steam.down = True
    await DealsCog(bot).post_daily_deals()  # type: ignore[arg-type]
    channel.send.assert_not_awaited()


async def test_one_failing_channel_does_not_block_the_others(
    bot: FakeBot, db: Database, before_sale: datetime
):
    await db.set_channel(GUILD, Feature.DEALS, CHANNEL)
    await db.set_channel(11, Feature.DEALS, 101)
    broken, healthy = bot.add_channel(CHANNEL), bot.add_channel(101)
    broken.send.side_effect = discord.HTTPException(type("R", (), {"status": 500, "reason": "x"})(), "falló")
    await DealsCog(bot).post_daily_deals()  # type: ignore[arg-type]
    healthy.send.assert_awaited_once()


# ── Avisos de rebajas ─────────────────────────────────────────────────────────


async def test_sale_notice_is_sent_once_per_guild(bot: FakeBot, db: Database, before_sale: datetime):
    await db.set_channel(GUILD, Feature.SALES, CHANNEL)
    channel = bot.add_channel(CHANNEL)
    cog = DealsCog(bot)  # type: ignore[arg-type]

    await cog.announce_sales()
    await cog.announce_sales()

    channel.send.assert_awaited_once()
    assert sent_kwargs(channel.send)["embed"].title == "🍂 Rebajas de Otoño de Steam · ¡Se vienen!"
    assert await db.sent_notices(GUILD) == {(AUTUMN_SALE.key, "7d")}


async def test_sale_notice_progresses_with_time(bot: FakeBot, db: Database, monkeypatch: pytest.MonkeyPatch):
    await db.set_channel(GUILD, Feature.SALES, CHANNEL)
    channel = bot.add_channel(CHANNEL)
    cog = DealsCog(bot)  # type: ignore[arg-type]
    titles = []
    for moment in (AUTUMN_SALE.start - timedelta(days=3), AUTUMN_SALE.start + timedelta(minutes=1)):
        monkeypatch.setattr(deals_module, "_now", lambda moment=moment: moment)
        await cog.announce_sales()
        titles.append(sent_kwargs(channel.send)["embed"].title)
    assert titles == [
        "🍂 Rebajas de Otoño de Steam · ¡Se vienen!",
        "🍂 Rebajas de Otoño de Steam · ¡Ya arrancaron!",
    ]


async def test_failed_sale_notice_is_retried(bot: FakeBot, db: Database, before_sale: datetime):
    await db.set_channel(GUILD, Feature.SALES, CHANNEL)
    channel = bot.add_channel(CHANNEL)
    channel.send.side_effect = discord.HTTPException(type("R", (), {"status": 500, "reason": "x"})(), "falló")
    cog = DealsCog(bot)  # type: ignore[arg-type]
    await cog.announce_sales()
    assert await db.sent_notices(GUILD) == set()

    channel.send.side_effect = None
    await cog.announce_sales()
    assert await db.sent_notices(GUILD) == {(AUTUMN_SALE.key, "7d")}


async def test_choosing_the_sales_channel_sends_the_pending_notice(
    bot: FakeBot, db: Database, before_sale: datetime
):
    await db.set_channel(GUILD, Feature.SALES, CHANNEL)
    channel = bot.add_channel(CHANNEL)
    await DealsCog(bot).on_sales_channel_set()  # type: ignore[arg-type]
    channel.send.assert_awaited_once()


async def test_unexpected_error_does_not_stop_a_periodic_task():
    calls = []

    @survives_errors
    async def task(cog: object) -> None:
        calls.append(cog)
        raise RuntimeError("bug inesperado")

    await task("cog")  # no propaga: discord.ext.tasks detendría el loop para siempre
    assert calls == ["cog"]
