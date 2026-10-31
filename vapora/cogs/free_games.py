"""Avisa cuando un juego de Steam está gratis por tiempo limitado (100% de descuento)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from vapora.cogs._tasks import survives_errors
from vapora.steam import ItemRef, SteamError, StoreItem
from vapora.storage import Feature
from vapora.ui.buttons import build_free_game_buttons
from vapora.ui.game_card import build_game_card

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

log = logging.getLogger(__name__)

CHECK_HOURS = 1
# El mismo juego puede volver a estar gratis más adelante: pasado este tiempo se avisa de nuevo.
REPEAT_AFTER_DAYS = 30
MAX_NOTICES_PER_CHECK = 5  # por servidor; los que no entran salen en la próxima revisión


class FreeGamesCog(commands.Cog):
    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.check_free_games.start()

    async def cog_unload(self) -> None:
        self.check_free_games.cancel()

    @tasks.loop(hours=CHECK_HOURS)
    @survives_errors
    async def check_free_games(self) -> None:
        """Avisa en cada servidor con canal configurado los juegos gratis que todavía no avisó."""
        configured = await self.bot.db.channels_for(Feature.FREE_GAMES)
        if not configured:
            return
        try:
            app_ids = await self.bot.steam.free_promo_app_ids()
        except SteamError:
            log.warning("No pude consultar los juegos gratis", exc_info=True)
            return
        if not app_ids:
            return

        since = _now() - timedelta(days=REPEAT_AFTER_DAYS)
        checked: dict[int, StoreItem | None] = {}  # cada juego se consulta una vez por revisión
        for guild_id, channel_id in configured.items():
            channel = self.bot.find_channel(channel_id)
            if channel is None:
                continue
            noticed = await self.bot.db.free_games_noticed(guild_id, since)
            pending = [app_id for app_id in app_ids if app_id not in noticed]
            sent = 0
            for app_id in pending:
                if sent == MAX_NOTICES_PER_CHECK:
                    break
                if app_id not in checked:
                    checked[app_id] = await self._free_game(app_id)
                item = checked[app_id]
                if item is not None and await self._announce(channel, guild_id, item):
                    sent += 1

    @check_free_games.before_loop
    async def _wait_until_ready(self) -> None:
        await self.bot.wait_until_ready()

    async def _free_game(self, app_id: int) -> StoreItem | None:
        """Datos actuales del juego, si de verdad es un juego completo que hoy está gratis.

        Se piden sin caché, para no avisar con datos viejos. Los DLC quedan afuera.
        """
        try:
            item = await self.bot.steam.refresh_item(ItemRef.app(app_id))
        except SteamError:
            log.warning("No pude consultar el juego gratis %s", app_id, exc_info=True)
            return None
        return item if item is not None and item.is_free_promo else None

    async def _announce(self, channel: discord.abc.Messageable, guild_id: int, item: StoreItem) -> bool:
        """Publica el aviso y lo registra. Si falla no se registra, así se reintenta."""
        converter = await self.bot.peso_converter()
        sale = await self.bot.current_sale()
        try:
            await channel.send(
                f"🎁 ¡**{item.name}** está gratis en Steam por tiempo limitado!",
                embed=build_game_card(item, converter, sale),
                view=build_free_game_buttons(item),
            )
        except discord.HTTPException:
            log.exception("No se pudo avisar el juego gratis %s en #%s", item.ref.id, channel)
            return False
        await self.bot.db.mark_free_game_noticed(guild_id, item.ref.id, _now())
        log.info("Aviso de juego gratis en #%s: %s", channel, item.name)
        return True


def _now() -> datetime:
    return datetime.now(UTC)
