"""/config: cada servidor elige en qué canal publica Vapora cada tipo de aviso."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from vapora import events
from vapora.storage import Feature
from vapora.ui.panels import FEATURE_LABELS, build_config_embed

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

FEATURE_CHOICES = [
    app_commands.Choice(name="🔥 Ofertas destacadas (todos los días)", value=Feature.DEALS.value),
    app_commands.Choice(name="📅 Avisos de rebajas de Steam", value=Feature.SALES.value),
    app_commands.Choice(name="🔔 Avisos de deseados en oferta", value=Feature.WISHLIST.value),
    app_commands.Choice(name="🖼️ Fondo del día de Wallpaper Engine", value=Feature.WALLPAPERS.value),
]


def missing_permissions(channel: discord.abc.GuildChannel, member: discord.Member) -> list[str]:
    """Permisos que le faltan a `member` para publicar tarjetas en el canal."""
    permissions = channel.permissions_for(member)
    required = {
        "Ver canal": permissions.view_channel,
        "Enviar mensajes": permissions.send_messages,
        "Insertar enlaces": permissions.embed_links,
    }
    return [name for name, granted in required.items() if not granted]


class SettingsCog(commands.Cog):
    config = app_commands.Group(
        name="config",
        description="Configurar dónde publica Vapora",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),  # solo quienes gestionan el servidor
    )

    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot

    @config.command(name="canal", description="Elegir el canal de las ofertas, los avisos o el fondo del día")
    @app_commands.describe(que="Qué querés publicar en ese canal", canal="Canal de texto donde publicar")
    @app_commands.choices(que=FEATURE_CHOICES)
    async def set_channel(
        self, interaction: discord.Interaction, que: app_commands.Choice[str], canal: discord.TextChannel
    ) -> None:
        guild = interaction.guild
        assert guild is not None  # el grupo es guild_only
        missing = missing_permissions(canal, guild.me)
        if missing:
            await interaction.response.send_message(
                f"⚠️ No puedo publicar en {canal.mention}. "
                f"Me faltan estos permisos ahí: **{', '.join(missing)}**.",
                ephemeral=True,
            )
            return

        feature = Feature(que.value)
        await self.bot.db.set_channel(guild.id, feature, canal.id)
        await interaction.response.send_message(
            f"✅ **{FEATURE_LABELS[feature]}** → {canal.mention}\n{self._describe_schedule(feature)}",
            ephemeral=True,
        )
        if feature is Feature.SALES:
            self.bot.dispatch(events.SALES_CHANNEL_SET)  # si hay un aviso pendiente, que salga ya

    @config.command(name="desactivar", description="Dejar de publicar ofertas o avisos de rebajas")
    @app_commands.describe(que="Qué querés desactivar")
    @app_commands.choices(que=FEATURE_CHOICES)
    async def disable(self, interaction: discord.Interaction, que: app_commands.Choice[str]) -> None:
        assert interaction.guild_id is not None  # el grupo es guild_only
        feature = Feature(que.value)
        await self.bot.db.set_channel(interaction.guild_id, feature, None)
        await interaction.response.send_message(
            f"🔕 **{FEATURE_LABELS[feature]}** desactivado.", ephemeral=True
        )

    @config.command(name="ver", description="Ver dónde publica Vapora en este servidor")
    async def show(self, interaction: discord.Interaction) -> None:
        assert interaction.guild_id is not None  # el grupo es guild_only
        channels = await self.bot.db.channels(interaction.guild_id)
        settings = self.bot.settings
        embed = build_config_embed(channels, settings.deals_hour, settings.wallpaper_hour)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _describe_schedule(self, feature: Feature) -> str:
        """Cuándo va a publicar Vapora ese tipo de aviso."""
        if feature is Feature.DEALS:
            return f"Las voy a publicar todos los días a las {self.bot.settings.deals_hour}:00."
        if feature is Feature.SALES:
            return "Voy a avisar antes de cada rebaja, cuando empieza y en sus últimas 24 horas."
        if feature is Feature.WALLPAPERS:
            hour = self.bot.settings.wallpaper_hour
            return f"Voy a publicar un fondo en tendencia todos los días a las {hour}:00."
        return "Cuando un juego de la lista de alguien entre en oferta, lo menciono ahí."
