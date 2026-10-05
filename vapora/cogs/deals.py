"""Ofertas destacadas y rebajas de Steam: /ofertas, /rebajas y sus publicaciones automáticas."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from vapora.cogs._tasks import argentina_today, missed_daily_post, pending_daily_targets, survives_errors
from vapora.sales import ARGENTINA, active_sale, due_notices
from vapora.steam import SteamError
from vapora.storage import Feature
from vapora.ui.announcements import build_deals_embed, build_sale_notice_embed, build_sales_calendar_embed

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

log = logging.getLogger(__name__)

SALE_CHECK_MINUTES = 10


class DealsCog(commands.Cog):
    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot
        # La hora sale de la configuración, que recién se conoce al crear el cog.
        self.post_daily_deals.change_interval(time=time(hour=bot.settings.deals_hour, tzinfo=ARGENTINA))
        # La vuelta periódica y /config pueden revisar los avisos a la vez: sin esto, los dos
        # verían el mismo aviso pendiente y lo mandarían dos veces.
        self._announce_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        self.post_daily_deals.start()
        self.announce_sales.start()

    async def cog_unload(self) -> None:
        self.post_daily_deals.cancel()
        self.announce_sales.cancel()

    # ── Comandos ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="ofertas", description="Muestra las ofertas destacadas de Steam con precio en pesos"
    )
    async def deals(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.followup.send(embed=await self._build_deals_embed())

    @app_commands.command(name="rebajas", description="Muestra la rebaja de Steam actual y las próximas")
    async def sales(self, interaction: discord.Interaction) -> None:
        sales = await self.bot.calendar.sales()
        await interaction.response.send_message(embed=build_sales_calendar_embed(_now(), sales))

    # ── Publicaciones automáticas ─────────────────────────────────────────────

    @tasks.loop(time=time(hour=12, tzinfo=ARGENTINA))  # la hora real se define en __init__
    @survives_errors
    async def post_daily_deals(self) -> None:
        """Publica las ofertas del día en cada servidor que eligió un canal y todavía no las tiene."""
        today = argentina_today(_now())
        targets = await pending_daily_targets(self.bot, Feature.DEALS, today)
        if not targets:
            return
        try:
            embed = await self._build_deals_embed()
        except SteamError:
            log.warning("No se pudieron obtener las ofertas del día", exc_info=True)
            return
        for guild_id, channel in targets:
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                log.exception("No se pudieron publicar las ofertas en #%s", channel)
                continue
            await self.bot.db.mark_posted(guild_id, Feature.DEALS, today)

    @tasks.loop(minutes=SALE_CHECK_MINUTES)
    @survives_errors
    async def announce_sales(self) -> None:
        await self._announce_due_sales()

    @post_daily_deals.before_loop
    async def _catch_up_daily_deals(self) -> None:
        """Si el bot arrancó poco después de la hora de las ofertas, las publica ahora."""
        await self.bot.wait_until_ready()
        if missed_daily_post(_now(), self.bot.settings.deals_hour):
            await self.post_daily_deals()

    @announce_sales.before_loop
    async def _wait_until_ready(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_sales_channel_set(self) -> None:
        """Si hay un aviso pendiente, lo manda apenas se elige el canal (ver `events.SALES_CHANNEL_SET`)."""
        await self._announce_due_sales()

    async def _announce_due_sales(self) -> None:
        """Manda en cada servidor los avisos de rebajas que correspondan y todavía no se enviaron."""
        async with self._announce_lock:
            await self._send_due_notices()

    async def _send_due_notices(self) -> None:
        configured = await self.bot.db.channels_for(Feature.SALES)
        if not configured:
            return
        sales = await self.bot.calendar.sales()
        now = _now()
        for guild_id, channel_id in configured.items():
            channel = self.bot.find_channel(channel_id)
            if channel is None:
                continue
            already_sent = await self.bot.db.sent_notices(guild_id)
            for sale, notice in due_notices(now, already_sent, sales):
                try:
                    await channel.send(embed=build_sale_notice_embed(sale, notice))
                except discord.HTTPException:
                    log.exception("No se pudo enviar el aviso de %s (%s) en #%s", sale.name, notice, channel)
                    continue
                await self.bot.db.mark_notice_sent(guild_id, sale.key, notice)
                log.info("Aviso de rebajas enviado en #%s: %s (%s)", channel, sale.name, notice)

    async def _build_deals_embed(self) -> discord.Embed:
        deals = await self.bot.steam.featured_deals()
        return build_deals_embed(
            deals,
            converter=await self.bot.peso_converter(),
            argentine_app_ids=await self.bot.steam.argentine_app_ids(),
            current_sale=active_sale(_now(), await self.bot.calendar.sales()),
        )


def _now() -> datetime:
    return datetime.now(UTC)
