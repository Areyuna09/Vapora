"""Responde con una tarjeta cuando alguien comparte un link de Steam."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from vapora.steam import ItemRef, SteamError, StoreItem, extract_item_refs
from vapora.ui.buttons import build_card_buttons
from vapora.ui.game_card import build_game_card

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

log = logging.getLogger(__name__)

MAX_CARDS_PER_MESSAGE = 10  # Discord admite hasta 10 embeds por mensaje


class LinksCog(commands.Cog):
    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        refs = extract_item_refs(message.content)[:MAX_CARDS_PER_MESSAGE]
        if not refs:
            return
        items = await self._fetch_items(refs)
        if not items:
            return

        converter = await self.bot.peso_converter()
        sale = await self.bot.current_sale()
        await message.reply(
            embeds=[build_game_card(item, converter, sale) for item in items],
            view=build_card_buttons(items),
            mention_author=False,
        )
        await self._hide_link_preview(message)

    async def _fetch_items(self, refs: list[ItemRef]) -> list[StoreItem]:
        """Datos de cada link. Los que no existen o fallan se saltean, sin frenar al resto."""
        items = []
        for ref in refs:
            try:
                item = await self.bot.steam.get_item(ref)
            except SteamError:
                log.warning("No se pudo consultar %s", ref.url, exc_info=True)
                continue
            if item is not None:
                items.append(item)
        return items

    async def _hide_link_preview(self, message: discord.Message) -> None:
        """Oculta el preview que Discord arma para el link, así queda solo la tarjeta de Vapora."""
        try:
            await message.edit(suppress=True)
        except discord.Forbidden:
            log.warning(
                "Sin permiso 'Gestionar mensajes' en #%s: no se puede ocultar el preview original.",
                message.channel,
            )
        except discord.HTTPException:
            log.exception("No se pudo ocultar el preview del mensaje %s", message.id)
