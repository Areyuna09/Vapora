"""Responde con una tarjeta cuando alguien comparte un link de Steam o de un fondo del Workshop."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from vapora.steam import ItemRef, SteamError, StoreItem, extract_item_refs
from vapora.steam.workshop import Wallpaper, extract_workshop_ids
from vapora.ui.buttons import build_card_buttons
from vapora.ui.game_card import build_game_card
from vapora.ui.wallpaper_card import add_wallpaper_buttons, build_wallpaper_message

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

log = logging.getLogger(__name__)

MAX_CARDS_PER_MESSAGE = 10  # Discord admite hasta 10 embeds por mensaje
MAX_ATTACHED_BYTES = 8 * 1024 * 1024  # Discord rechaza mensajes con más de 10 MB de adjuntos


class LinksCog(commands.Cog):
    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        refs = extract_item_refs(message.content)[:MAX_CARDS_PER_MESSAGE]
        workshop_ids = extract_workshop_ids(message.content)[: MAX_CARDS_PER_MESSAGE - len(refs)]
        if not refs and not workshop_ids:
            return
        items = await self._fetch_items(refs)
        wallpapers = await self._fetch_wallpapers(workshop_ids)
        if not items and not wallpapers:
            return

        embeds: list[discord.Embed] = []
        if items:
            converter = await self.bot.peso_converter()
            sale = await self.bot.current_sale()
            embeds = [build_game_card(item, converter, sale) for item in items]
        wallpaper_embeds, files = await self._wallpaper_cards(wallpapers)
        view = build_card_buttons(items)
        add_wallpaper_buttons(view, wallpapers, first_row=len(items))
        try:
            await message.reply(
                embeds=embeds + wallpaper_embeds, files=files, view=view, mention_author=False
            )
        except discord.HTTPException:
            # Sin permiso para escribir en ese canal, por ejemplo: no se oculta el preview
            # original, así el link no queda sin ninguna tarjeta.
            log.warning("No pude responder al link en #%s", message.channel, exc_info=True)
            return
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

    async def _fetch_wallpapers(self, wallpaper_ids: list[int]) -> list[Wallpaper]:
        """Fondos de Wallpaper Engine enlazados.

        Los que no son de Wallpaper Engine o no son para todo público se saltean sin tarjeta.
        """
        wallpapers = []
        for wallpaper_id in wallpaper_ids:
            try:
                wallpaper = await self.bot.workshop.get(wallpaper_id)
            except SteamError:
                log.warning("No se pudo consultar el fondo %s", wallpaper_id, exc_info=True)
                continue
            if wallpaper is not None:
                wallpapers.append(wallpaper)
        return wallpapers

    async def _wallpaper_cards(
        self, wallpapers: list[Wallpaper]
    ) -> tuple[list[discord.Embed], list[discord.File]]:
        """Tarjetas de los fondos, con la vista previa agrandada adjunta mientras entre.

        Los adjuntos de un mensaje no pueden pasar el límite de Discord: los que no entran
        usan la vista previa original.
        """
        embeds, files, attached_bytes = [], [], 0
        for wallpaper in wallpapers:
            enlarged = await self.bot.previews.enlarged(wallpaper.preview_url)
            if enlarged is not None and attached_bytes + len(enlarged) > MAX_ATTACHED_BYTES:
                enlarged = None
            embed, wallpaper_files = build_wallpaper_message(wallpaper, enlarged)
            attached_bytes += len(enlarged or b"")
            embeds.append(embed)
            files += wallpaper_files
        return embeds, files

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
