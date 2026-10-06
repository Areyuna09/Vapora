"""Arma el bot real, con sus cogs y comandos, sin conectarlo a Discord."""

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

from vapora.bot import STATUS_TEXT, VaporaBot
from vapora.config import Settings
from vapora.steam import SteamError
from vapora.ui.buttons import WishButton


@pytest.fixture
async def bot(tmp_path: Path) -> AsyncIterator[VaporaBot]:
    settings = Settings(
        discord_token="test", database_file=tmp_path / "vapora.db", legacy_state_file=tmp_path / "state.json"
    )
    bot = VaporaBot(settings)
    await bot._async_setup_hook()  # lo que hace discord.py al iniciar sesión, sin red
    await bot.setup_hook()
    yield bot
    await bot.close()


def slash_commands(bot: VaporaBot) -> list[str]:
    names = []
    for command in bot.tree.get_commands():
        if isinstance(command, app_commands.Group):
            names += [f"/{command.name} {sub.name}" for sub in command.commands]
        else:
            names.append(f"/{command.name}")
    return sorted(names)


async def test_registers_every_command(bot: VaporaBot):
    assert slash_commands(bot) == [
        "/ayuda",
        "/config canal",
        "/config desactivar",
        "/config ver",
        "/deseado agregar",
        "/deseado lista",
        "/deseado quitar",
        "/fondo",
        "/ofertas",
        "/rebajas",
    ]
    assert bot.get_command("ping") is not None


async def test_config_is_only_for_server_managers(bot: VaporaBot):
    config = bot.tree.get_command("config")
    assert isinstance(config, app_commands.Group)
    assert config.guild_only
    assert config.default_permissions == discord.Permissions(manage_guild=True)


async def test_background_tasks_are_running(bot: VaporaBot):
    assert bot.get_cog("DealsCog").post_daily_deals.is_running()  # type: ignore[union-attr]
    assert bot.get_cog("DealsCog").announce_sales.is_running()  # type: ignore[union-attr]
    assert bot.get_cog("WishlistCog").check_prices.is_running()  # type: ignore[union-attr]
    assert bot.get_cog("WallpapersCog").post_daily_wallpaper.is_running()  # type: ignore[union-attr]


async def test_wish_buttons_from_old_messages_keep_working(bot: VaporaBot):
    assert WishButton in bot._connection._view_store._dynamic_items.values()


async def test_reads_message_content_and_shows_status(bot: VaporaBot):
    assert bot.intents.message_content
    presence = bot._connection._activity  # lo que se le envía a Discord al conectar
    assert presence is not None
    assert presence["type"] == discord.ActivityType.custom.value
    assert presence["state"] == STATUS_TEXT == "Precios de Steam 🇦🇷"


async def test_database_is_ready_after_setup(bot: VaporaBot, tmp_path: Path):
    assert (tmp_path / "vapora.db").exists()
    assert await bot.db.all_wishes() == []


async def test_find_channel(bot: VaporaBot, monkeypatch: pytest.MonkeyPatch):
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = MagicMock()
    channel.permissions_for.return_value = MagicMock(view_channel=True, send_messages=True, embed_links=True)
    monkeypatch.setattr(bot, "get_channel", lambda channel_id: channel if channel_id == 100 else None)
    assert bot.find_channel(100) is channel
    assert bot.find_channel(999) is None  # canal borrado o que Vapora no ve
    assert bot.find_channel(None) is None


def failing_interaction(*, already_answered: bool) -> MagicMock:
    interaction = MagicMock()
    interaction.response.is_done.return_value = already_answered
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def test_command_error_tells_the_user_steam_is_down(bot: VaporaBot):
    interaction = failing_interaction(already_answered=True)  # el comando ya había hecho defer()
    error = app_commands.CommandInvokeError(MagicMock(), SteamError("caído"))
    await bot.tree.on_error(interaction, error)
    interaction.followup.send.assert_awaited_once_with(
        "😕 Steam no está respondiendo. Probá de nuevo en un rato.", ephemeral=True
    )


async def test_unexpected_command_error_gets_a_generic_reply(bot: VaporaBot):
    interaction = failing_interaction(already_answered=False)
    error = app_commands.CommandInvokeError(MagicMock(), RuntimeError("bug"))
    await bot.tree.on_error(interaction, error)
    interaction.response.send_message.assert_awaited_once_with(
        "😕 Algo salió mal. Probá de nuevo en un rato.", ephemeral=True
    )


async def test_command_error_from_a_cloudflare_ban_does_not_try_to_reply(bot: VaporaBot):
    """Responder también fallaría y sería un pedido más con la IP bloqueada."""
    ban = discord.HTTPException(
        MagicMock(status=429, reason="Too Many Requests"), "<html>Cloudflare 1015</html>"
    )
    interaction = failing_interaction(already_answered=False)
    await bot.tree.on_error(interaction, app_commands.CommandInvokeError(MagicMock(), ban))
    interaction.response.send_message.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()


# ── Seguridad: menciones y límites de uso ─────────────────────────────────────


async def test_nothing_mentions_anyone_by_default(bot: VaporaBot):
    mentions = bot.allowed_mentions
    assert mentions is not None
    assert (mentions.everyone, mentions.users, mentions.roles, mentions.replied_user) == (
        False,
        False,
        False,
        False,
    )


def limited_interaction(user_id: int = 5, *, autocomplete: bool = False) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.type = (
        discord.InteractionType.autocomplete if autocomplete else discord.InteractionType.application_command
    )
    interaction.created_at = (
        discord.utils.utcnow()
    )  # los cooldowns de discord.py usan la hora de la interacción
    interaction.response.send_message = AsyncMock()
    return interaction


async def test_commands_over_the_limit_are_stopped_with_a_single_warning(bot: VaporaBot):
    interaction = limited_interaction()
    interaction.client = bot
    allowed = [await bot.tree.interaction_check(interaction) for _ in range(10)]
    assert allowed == [True] * 8 + [False, False]
    interaction.response.send_message.assert_awaited_once()  # un aviso, no uno por intento
    assert "Más despacio" in interaction.response.send_message.await_args.args[0]


async def test_autocomplete_over_the_limit_is_ignored_silently(bot: VaporaBot):
    interaction = limited_interaction(autocomplete=True)
    interaction.client = bot
    results = [await bot.tree.interaction_check(interaction) for _ in range(30)]
    assert results.count(False) == 5
    interaction.response.send_message.assert_not_awaited()


async def test_command_cooldown_error_asks_to_wait(bot: VaporaBot):
    interaction = failing_interaction(already_answered=False)
    error = app_commands.CommandOnCooldown(app_commands.Cooldown(3, 60), 42.5)
    await bot.tree.on_error(interaction, error)
    interaction.response.send_message.assert_awaited_once_with(
        "⏳ Más despacio: probá de nuevo en 43 s.", ephemeral=True
    )


async def test_wallpaper_command_has_its_own_stricter_limit(bot: VaporaBot):
    command = bot.tree.get_command("fondo")
    assert command is not None
    (cooldown_check,) = command.checks
    interaction = limited_interaction()
    for _ in range(3):  # tres por minuto
        assert await discord.utils.maybe_coroutine(cooldown_check, interaction)
    with pytest.raises(app_commands.CommandOnCooldown):
        await discord.utils.maybe_coroutine(cooldown_check, interaction)


async def test_find_channel_skips_channels_where_vapora_cannot_post(
    bot: VaporaBot, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    channel = MagicMock(spec=discord.TextChannel)
    channel.guild = MagicMock()
    channel.permissions_for.return_value = MagicMock(view_channel=True, send_messages=False, embed_links=True)
    monkeypatch.setattr(bot, "get_channel", lambda channel_id: channel)
    assert bot.find_channel(100) is None  # publicar igual sería un pedido rechazado
    assert bot.find_channel(100) is None
    warnings = [record.getMessage() for record in caplog.records if record.levelname == "WARNING"]
    assert warnings == ["No puedo publicar en el canal 100: me faltan permisos (Enviar mensajes)"]  # una vez

    channel.permissions_for.return_value.send_messages = True  # le devolvieron el permiso
    assert bot.find_channel(100) is channel


async def test_heartbeat_cog_is_loaded(bot: VaporaBot):
    assert bot.get_cog("HealthCog") is not None
    assert bot.session is bot._session
