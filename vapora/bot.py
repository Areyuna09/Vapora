"""El bot: crea los servicios que comparten los cogs y registra los comandos."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from vapora.cogs.deals import DealsCog
from vapora.cogs.general import GeneralCog
from vapora.cogs.links import LinksCog
from vapora.cogs.settings import SettingsCog
from vapora.cogs.wallpapers import WallpapersCog
from vapora.cogs.wishlist import WishlistCog
from vapora.config import Settings
from vapora.discord_errors import BAN_SUMMARY, is_cloudflare_ban
from vapora.permissions import missing_send_permissions
from vapora.previews import PreviewEnlarger
from vapora.pricing import DollarClient, PesoConverter
from vapora.ratelimit import RateLimits, slow_down_text
from vapora.sales import SalesCalendar, SteamSale, active_sale
from vapora.steam import SteamClient, SteamError
from vapora.steam.workshop import WorkshopClient
from vapora.storage import Database
from vapora.ui.buttons import WishButton

log = logging.getLogger(__name__)

STATUS_TEXT = "Precios de Steam 🇦🇷"  # se ve debajo del nombre en la lista de miembros
HTTP_TIMEOUT_SECONDS = 15
COGS = (LinksCog, DealsCog, WishlistCog, WallpapersCog, SettingsCog, GeneralCog)


class VaporaTree(app_commands.CommandTree["VaporaBot"]):
    """Árbol de comandos que aplica el límite de uso por usuario a todos los comandos."""

    async def interaction_check(self, interaction: discord.Interaction[VaporaBot]) -> bool:
        limits = interaction.client.limits
        is_autocomplete = interaction.type is discord.InteractionType.autocomplete
        limit = limits.autocomplete if is_autocomplete else limits.commands
        retry_after = limit.retry_after(interaction.user.id)
        if not retry_after:
            return True
        if not is_autocomplete and limit.should_warn(interaction.user.id, retry_after):
            await interaction.response.send_message(slow_down_text(retry_after), ephemeral=True)
        return False


class VaporaBot(commands.Bot):
    """Bot de Discord con los servicios de Vapora a mano para los cogs.

    Los clientes HTTP (`steam`, `workshop`, `previews`, `dollar`, `calendar`) se crean en
    `setup_hook`, cuando ya existe el event loop que necesita la sesión de aiohttp.
    """

    steam: SteamClient
    workshop: WorkshopClient
    previews: PreviewEnlarger
    dollar: DollarClient
    calendar: SalesCalendar

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # para detectar los links de Steam en los mensajes
        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.CustomActivity(name=STATUS_TEXT),
            tree_cls=VaporaTree,
            # Nada menciona a nadie salvo que se pida en ese mensaje: los nombres de juegos y
            # fondos vienen de Steam y un "@everyone" ahí no debe notificar a todo el servidor.
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.settings = settings
        self.limits = RateLimits()
        self._warned_channels: set[int] = set()  # canales con problemas ya avisados en el log
        self.db = Database(settings.database_file, settings.legacy_state_file)
        self._session: aiohttp.ClientSession | None = None
        self._commands_synced = False

    async def setup_hook(self) -> None:
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS))
        self.steam = SteamClient(self._session)
        self.workshop = WorkshopClient(self._session)
        self.previews = PreviewEnlarger(self._session)
        self.dollar = DollarClient(self._session, ttl_seconds=self.settings.exchange_rate_ttl_seconds)
        self.calendar = SalesCalendar(self._session)
        await self.db.setup()

        self.add_dynamic_items(WishButton)  # botones de tarjetas enviadas antes de reiniciar
        for cog in COGS:
            await self.add_cog(cog(self))
        self.tree.error(self._on_app_command_error)

    async def close(self) -> None:
        await super().close()
        if self._session is not None:
            await self._session.close()

    async def peso_converter(self) -> PesoConverter:
        """Conversor a pesos con las cotizaciones del momento y los impuestos configurados."""
        return PesoConverter(await self.dollar.rates(), self.settings.taxes)

    async def current_sale(self) -> SteamSale | None:
        """Rebaja de Steam en curso, si hay alguna."""
        return active_sale(datetime.now(UTC), await self.calendar.sales())

    def find_channel(self, channel_id: int | None) -> discord.abc.Messageable | None:
        """Canal donde publicar, o `None` si no está configurado, Vapora ya no lo ve o no puede
        publicar ahí (mandar igual sería un pedido que Discord rechaza y cuenta para su límite).

        Los problemas se avisan en el log una sola vez por canal, hasta que se arreglan.
        """
        if not channel_id:
            return None
        channel = self.get_channel(channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            self._warn_channel_once(channel_id, "No encuentro el canal %s (¿lo borraron o Vapora no lo ve?)")
            return None
        missing = missing_send_permissions(channel)
        if missing:
            self._warn_channel_once(
                channel_id, f"No puedo publicar en el canal %s: me faltan permisos ({', '.join(missing)})"
            )
            return None
        self._warned_channels.discard(channel_id)
        return channel

    def _warn_channel_once(self, channel_id: int, message: str) -> None:
        if channel_id not in self._warned_channels:
            self._warned_channels.add(channel_id)
            log.warning(message, channel_id)

    # ── Eventos ───────────────────────────────────────────────────────────────

    async def on_ready(self) -> None:
        log.info("Conectado como %s (%s)", self.user, self.user.id if self.user else "?")
        if self._commands_synced:  # on_ready se repite en cada reconexión
            return
        for guild in self.guilds:
            await self._sync_commands(guild)
        self._commands_synced = True
        names = ", ".join(f"/{command.name}" for command in self.tree.get_commands())
        log.info("Comandos %s listos en %d servidor(es)", names, len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        await self._sync_commands(guild)

    async def _sync_commands(self, guild: discord.Guild) -> None:
        """Registra los comandos en un servidor: así aparecen al instante, sin la demora global."""
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Le avisa al usuario que algo falló, en vez de dejar el comando colgado."""
        cause = getattr(error, "original", error)
        if is_cloudflare_ban(cause):
            # Avisarle al usuario también fallaría, y sería un pedido más con la IP bloqueada.
            log.error("No pude responder /%s: %s", _command_name(interaction), BAN_SUMMARY)
            return
        if isinstance(error, app_commands.CommandOnCooldown):
            text = slow_down_text(error.retry_after)
        elif isinstance(cause, SteamError):
            log.warning("Steam no respondió durante /%s", _command_name(interaction), exc_info=cause)
            text = "😕 Steam no está respondiendo. Probá de nuevo en un rato."
        else:
            log.error("Error en /%s", _command_name(interaction), exc_info=cause)
            text = "😕 Algo salió mal. Probá de nuevo en un rato."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(text, ephemeral=True)
            else:
                await interaction.response.send_message(text, ephemeral=True)
        except discord.HTTPException:
            log.warning("No pude avisarle al usuario del error", exc_info=True)


def _command_name(interaction: discord.Interaction) -> str:
    return interaction.command.qualified_name if interaction.command else "?"
