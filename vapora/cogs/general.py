"""Comandos generales: /ayuda y !ping."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from vapora.ui.panels import build_help_embed

if TYPE_CHECKING:
    from vapora.bot import VaporaBot


class GeneralCog(commands.Cog):
    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot

    @app_commands.command(name="ayuda", description="Qué hace Vapora y cómo usarla")
    async def show_help(self, interaction: discord.Interaction) -> None:
        # En un MD no hay permisos de servidor: se muestra la ayuda sin la sección de administración.
        permissions = getattr(interaction.user, "guild_permissions", None)
        is_admin = bool(permissions and permissions.manage_guild)
        settings = self.bot.settings
        embed = build_help_embed(
            is_admin=is_admin,
            taxes=settings.taxes,
            rates_refresh_minutes=settings.exchange_rate_ttl_seconds // 60,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command()
    async def ping(self, ctx: commands.Context[commands.Bot]) -> None:
        """Prueba simple para verificar que el bot responde."""
        await ctx.send("🏓 Pong!")
