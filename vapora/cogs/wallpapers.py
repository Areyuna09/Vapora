"""Fondos de Wallpaper Engine: /fondo y el fondo del día."""

from __future__ import annotations

import logging
import random
from collections import deque
from collections.abc import Sequence
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from vapora.cogs._tasks import argentina_today, missed_daily_post, pending_daily_targets, survives_errors
from vapora.permissions import missing_send_permissions
from vapora.sales import ARGENTINA
from vapora.steam import SteamError
from vapora.steam.workshop import CATEGORIES, Wallpaper
from vapora.storage import Feature
from vapora.ui.wallpaper_card import build_wallpaper_buttons, build_wallpaper_message

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

log = logging.getLogger(__name__)

RECENT_PER_CHANNEL = 15  # fondos recientes que no se repiten en un mismo canal
WALLPAPERS_PER_MINUTE = 3  # por usuario

CATEGORY_CHOICES = [app_commands.Choice(name=label, value=key) for key, (label, _) in CATEGORIES.items()]


class WallpapersCog(commands.Cog):
    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot
        # La hora sale de la configuración, que recién se conoce al crear el cog.
        self.post_daily_wallpaper.change_interval(
            time=time(hour=bot.settings.wallpaper_hour, tzinfo=ARGENTINA)
        )
        # Últimos fondos mostrados en cada canal, para no repetir el mismo enseguida.
        self._recent: dict[int, deque[int]] = {}

    async def cog_load(self) -> None:
        self.post_daily_wallpaper.start()

    async def cog_unload(self) -> None:
        self.post_daily_wallpaper.cancel()

    # ── /fondo ────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="fondo", description="Un fondo de Wallpaper Engine que es tendencia esta semana"
    )
    @app_commands.describe(categoria="De qué tipo (si no elegís, de cualquiera)")
    @app_commands.choices(categoria=CATEGORY_CHOICES)
    # Más estricto que el límite general: cada uso puede subir unos MB de vista previa.
    @app_commands.checks.cooldown(WALLPAPERS_PER_MINUTE, 60, key=lambda interaction: interaction.user.id)
    async def wallpaper(
        self, interaction: discord.Interaction, categoria: app_commands.Choice[str] | None = None
    ) -> None:
        await interaction.response.defer()
        wallpapers = await self.bot.workshop.trending(categoria.value if categoria else None)
        chosen = self._pick(wallpapers, interaction.channel_id)
        if chosen is None:
            await interaction.followup.send("🤔 No encontré fondos ahora. Probá de nuevo en un rato.")
            return
        # app_permissions: lo que Vapora puede hacer en el canal del comando.
        can_attach = interaction.app_permissions.attach_files
        enlarged = await self.bot.previews.enlarged(chosen.preview_url) if can_attach else None
        embed, files = build_wallpaper_message(chosen, enlarged)
        await interaction.followup.send(embed=embed, files=files, view=build_wallpaper_buttons([chosen]))

    # ── Fondo del día ─────────────────────────────────────────────────────────

    @tasks.loop(time=time(hour=18, tzinfo=ARGENTINA))  # la hora real se define en __init__
    @survives_errors
    async def post_daily_wallpaper(self) -> None:
        """Publica un fondo en cada servidor que eligió un canal y todavía no lo recibió hoy."""
        today = argentina_today(_now())
        targets = await pending_daily_targets(self.bot, Feature.WALLPAPERS, today)
        if not targets:
            return
        try:
            wallpapers = await self.bot.workshop.trending()
        except SteamError:
            log.warning("No se pudieron obtener los fondos del día", exc_info=True)
            return
        for guild_id, channel in targets:
            chosen = self._pick(wallpapers, getattr(channel, "id", None))
            if chosen is None:
                log.warning("No hay fondos para publicar hoy")
                return
            can_attach = not missing_send_permissions(channel, files=True)
            enlarged = await self.bot.previews.enlarged(chosen.preview_url) if can_attach else None
            embed, files = build_wallpaper_message(chosen, enlarged, title_prefix="🖼️ Fondo del día ·")
            try:
                await channel.send(embed=embed, files=files, view=build_wallpaper_buttons([chosen]))
            except discord.HTTPException:
                log.exception("No se pudo publicar el fondo del día en #%s", channel)
                continue
            await self.bot.db.mark_posted(guild_id, Feature.WALLPAPERS, today)

    @post_daily_wallpaper.before_loop
    async def _catch_up_daily_wallpaper(self) -> None:
        """Si el bot arrancó poco después de la hora del fondo del día, lo publica ahora."""
        await self.bot.wait_until_ready()
        if missed_daily_post(_now(), self.bot.settings.wallpaper_hour):
            await self.post_daily_wallpaper()

    # ── Elección ──────────────────────────────────────────────────────────────

    def _pick(self, wallpapers: Sequence[Wallpaper], channel_id: int | None) -> Wallpaper | None:
        """Uno al azar, evitando los que se mostraron hace poco en ese canal."""
        if not wallpapers:
            return None
        recent = self._recent.setdefault(channel_id or 0, deque(maxlen=RECENT_PER_CHANNEL))
        fresh = [wallpaper for wallpaper in wallpapers if wallpaper.id not in recent]
        chosen = random.choice(fresh or list(wallpapers))
        recent.append(chosen.id)
        return chosen


def _now() -> datetime:
    return datetime.now(UTC)
