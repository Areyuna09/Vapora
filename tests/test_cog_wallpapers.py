from datetime import datetime

import discord
import pytest
from fakes import FakeBot, FakeWorkshop, make_interaction, sent_kwargs, sent_text

from vapora.cogs import wallpapers as wallpapers_module
from vapora.cogs.wallpapers import RECENT_PER_CHANNEL, WallpapersCog
from vapora.config import Settings
from vapora.sales import ARGENTINA
from vapora.steam.workshop import Wallpaper
from vapora.storage import Database, Feature

GUILD, CHANNEL = 10, 500
ANIME = Wallpaper(1, "Chica anime", "https://img/1.gif", ("Anime", "Everyone", "Scene"), 5000, 400)
LAKE = Wallpaper(2, "Lago", "https://img/2.jpg", ("Landscape", "Everyone", "Video"), 3000, 200)
TODAY_AT_18 = datetime(2026, 10, 5, 18, 0, tzinfo=ARGENTINA)


@pytest.fixture
def bot(db: Database) -> FakeBot:
    bot = FakeBot(db)
    bot.workshop = FakeWorkshop(ANIME, LAKE)
    return bot


@pytest.fixture
def cog(bot: FakeBot) -> WallpapersCog:
    return WallpapersCog(bot)  # type: ignore[arg-type]


@pytest.fixture
def at_wallpaper_time(monkeypatch: pytest.MonkeyPatch) -> datetime:
    monkeypatch.setattr(wallpapers_module, "_now", lambda: TODAY_AT_18)
    return TODAY_AT_18


def _choice(value: str):
    return discord.app_commands.Choice(name=value, value=value)


# ── /fondo ────────────────────────────────────────────────────────────────────


async def test_wallpaper_command_shows_a_card_with_preview_and_buttons(cog: WallpapersCog):
    interaction = make_interaction()
    await cog.wallpaper.callback(cog, interaction)
    interaction.response.defer.assert_awaited_once_with()
    sent = sent_kwargs(interaction.followup.send)
    assert sent["embed"].title in {"🖼️ Chica anime", "🖼️ Lago"}
    assert sent["embed"].image.url in {"https://img/1.gif", "https://img/2.jpg"}
    labels = [button.label for button in sent["view"].children]
    assert labels == ["🖼️ Ver en Steam", "🛒 Conseguir Wallpaper Engine"]


async def test_wallpaper_command_by_category(cog: WallpapersCog, bot: FakeBot):
    interaction = make_interaction()
    await cog.wallpaper.callback(cog, interaction, _choice("paisaje"))
    assert bot.workshop.trending_requests == ["paisaje"]
    assert sent_kwargs(interaction.followup.send)["embed"].title == "🖼️ Lago"


async def test_wallpaper_command_with_nothing_found(cog: WallpapersCog, bot: FakeBot):
    bot.workshop = FakeWorkshop()
    interaction = make_interaction()
    await cog.wallpaper.callback(cog, interaction)
    assert sent_text(interaction.followup.send) == "🤔 No encontré fondos ahora. Probá de nuevo en un rato."


async def test_recent_wallpapers_are_not_repeated_in_the_same_channel(cog: WallpapersCog):
    picks = [cog._pick([ANIME, LAKE], channel_id=1) for _ in range(2)]
    assert {wallpaper.id for wallpaper in picks if wallpaper} == {1, 2}  # el segundo no repite el primero


async def test_when_everything_was_shown_it_can_repeat(cog: WallpapersCog):
    for _ in range(RECENT_PER_CHANNEL + 3):
        assert cog._pick([ANIME], channel_id=1) == ANIME


# ── Fondo del día ─────────────────────────────────────────────────────────────


def test_daily_wallpaper_hour_comes_from_settings(bot: FakeBot):
    bot.settings = Settings(discord_token="test", wallpaper_hour=21)
    cog = WallpapersCog(bot)  # type: ignore[arg-type]
    (scheduled,) = cog.post_daily_wallpaper.time
    assert (scheduled.hour, scheduled.tzinfo) == (21, ARGENTINA)


async def test_daily_wallpaper_is_posted_once_per_day(
    cog: WallpapersCog, bot: FakeBot, db: Database, at_wallpaper_time: datetime
):
    await db.set_channel(GUILD, Feature.WALLPAPERS, CHANNEL)
    await db.set_channel(11, Feature.DEALS, 600)  # este servidor no pidió fondos
    channel, other = bot.add_channel(CHANNEL), bot.add_channel(600)
    await cog.post_daily_wallpaper()
    await cog.post_daily_wallpaper()
    channel.send.assert_awaited_once()
    other.send.assert_not_awaited()
    assert sent_kwargs(channel.send)["embed"].title.startswith("🖼️ Fondo del día ·")
    assert await db.guilds_posted_on(Feature.WALLPAPERS, at_wallpaper_time.date()) == {GUILD}


async def test_daily_wallpaper_failures_are_retried(
    cog: WallpapersCog, bot: FakeBot, db: Database, at_wallpaper_time: datetime
):
    await db.set_channel(GUILD, Feature.WALLPAPERS, CHANNEL)
    channel = bot.add_channel(CHANNEL)
    bot.workshop.down = True
    await cog.post_daily_wallpaper()  # Steam caído: no se marca
    channel.send.side_effect = discord.HTTPException(type("R", (), {"status": 500, "reason": "x"})(), "falló")
    bot.workshop.down = False
    await cog.post_daily_wallpaper()  # Discord falló: no se marca
    assert await db.guilds_posted_on(Feature.WALLPAPERS, at_wallpaper_time.date()) == set()


@pytest.mark.parametrize(("hour", "catches_up"), [(17, False), (18, True), (23, True)])
async def test_daily_wallpaper_catch_up_after_a_restart(
    bot: FakeBot, db: Database, monkeypatch: pytest.MonkeyPatch, hour: int, catches_up: bool
):
    monkeypatch.setattr(wallpapers_module, "_now", lambda: datetime(2026, 10, 5, hour, 30, tzinfo=ARGENTINA))
    await db.set_channel(GUILD, Feature.WALLPAPERS, CHANNEL)
    channel = bot.add_channel(CHANNEL)
    await WallpapersCog(bot)._catch_up_daily_wallpaper()  # type: ignore[arg-type]
    assert channel.send.await_count == (1 if catches_up else 0)


# ── Vista previa agrandada ────────────────────────────────────────────────────


async def test_animated_preview_goes_enlarged_as_an_attachment(cog: WallpapersCog, bot: FakeBot):
    bot.workshop = FakeWorkshop(ANIME)
    bot.previews.enlarged_by_url[ANIME.preview_url or ""] = b"GIF89a-agrandado"
    interaction = make_interaction()
    await cog.wallpaper.callback(cog, interaction)
    sent = sent_kwargs(interaction.followup.send)
    (attachment,) = sent["files"]
    assert attachment.filename == "fondo-1.gif"
    assert sent["embed"].image.url == "attachment://fondo-1.gif"


async def test_static_preview_keeps_the_original_image(cog: WallpapersCog, bot: FakeBot):
    bot.workshop = FakeWorkshop(LAKE)  # JPEG: el agrandador no devuelve nada
    interaction = make_interaction()
    await cog.wallpaper.callback(cog, interaction)
    sent = sent_kwargs(interaction.followup.send)
    assert sent["files"] == []
    assert sent["embed"].image.url == "https://img/2.jpg"


async def test_daily_wallpaper_attaches_a_fresh_file_per_channel(
    bot: FakeBot, db: Database, at_wallpaper_time: datetime
):
    bot.workshop = FakeWorkshop(ANIME)
    bot.previews.enlarged_by_url[ANIME.preview_url or ""] = b"GIF89a-agrandado"
    await db.set_channel(GUILD, Feature.WALLPAPERS, CHANNEL)
    await db.set_channel(11, Feature.WALLPAPERS, 501)
    first, second = bot.add_channel(CHANNEL), bot.add_channel(501)
    await WallpapersCog(bot).post_daily_wallpaper()  # type: ignore[arg-type]
    first_file, second_file = sent_kwargs(first.send)["files"][0], sent_kwargs(second.send)["files"][0]
    assert first_file is not second_file  # un discord.File se puede mandar una sola vez
