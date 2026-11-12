"""Responde con una tarjeta cuando alguien comparte un link de Steam o del Workshop."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from vapora.permissions import can_hide_previews, missing_send_permissions
from vapora.steam import ItemRef, SteamError, StoreItem, extract_item_refs
from vapora.steam.workshop import Wallpaper, WorkshopItem, WorkshopMod, extract_workshop_ids
from vapora.ui.buttons import build_card_buttons
from vapora.ui.game_card import build_game_card
from vapora.ui.mod_card import add_mod_buttons, build_mod_message
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
        if missing_send_permissions(message.channel, reply=True):
            # Responder igual sería un pedido que Discord rechaza (y cuenta para su límite).
            log.debug("Sin permisos para responder links en #%s", message.channel)
            return
        if self.bot.limits.links.retry_after(message.author.id):
            # Sin aviso: responder a cada mensaje de spam sería, justamente, spamear a Discord.
            log.info("Links de %s ignorados: pasó el límite de mensajes con links", message.author.id)
            return
        items = await self._fetch_items(refs)
        workshop_items = await self._fetch_workshop_items(workshop_ids)
        wallpapers = [item for item in workshop_items if isinstance(item, Wallpaper)]
        mods = [item for item in workshop_items if isinstance(item, WorkshopMod)]
        if not items and not workshop_items:
            return

        embeds: list[discord.Embed] = []
        if items:
            converter = await self.bot.peso_converter()
            sale = await self.bot.current_sale()
            embeds = [build_game_card(item, converter, sale) for item in items]
        can_attach = not missing_send_permissions(message.channel, files=True)
        workshop_embeds, files = await self._workshop_cards([*wallpapers, *mods], can_attach=can_attach)
        view = build_card_buttons(items)
        next_row = add_wallpaper_buttons(view, wallpapers, first_row=len(items))
        add_mod_buttons(view, mods, first_row=next_row)
        try:
            await message.reply(embeds=embeds + workshop_embeds, files=files, view=view, mention_author=False)
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

    async def _fetch_workshop_items(self, item_ids: list[int]) -> list[WorkshopItem]:
        """Fondos y mods del Workshop enlazados.

        Los que no existen o no se pueden mostrar (fondos +18) se saltean sin tarjeta.
        """
        workshop_items = []
        for item_id in item_ids:
            try:
                item = await self.bot.workshop.get_item(item_id)
            except SteamError:
                log.warning("No se pudo consultar el ítem del Workshop %s", item_id, exc_info=True)
                continue
            if item is not None:
                workshop_items.append(item)
        return workshop_items

    async def _game_name(self, app_id: int) -> str | None:
        """Nombre del juego de un mod. Es un extra: si Steam falla, la tarjeta sale sin él."""
        try:
            game = await self.bot.steam.get_item(ItemRef.app(app_id))
        except SteamError:
            return None
        return game.name if game is not None else None

    async def _workshop_cards(
        self, workshop_items: list[WorkshopItem], *, can_attach: bool
    ) -> tuple[list[discord.Embed], list[discord.File]]:
        """Tarjetas de fondos y mods, con la vista previa animada agrandada adjunta mientras entre.

        Los adjuntos de un mensaje no pueden pasar el límite de Discord: los que no entran
        (o todos, si Vapora no puede adjuntar archivos en el canal) usan la vista previa original.
        """
        embeds, files, attached_bytes = [], [], 0
        for item in workshop_items:
            enlarged = await self.bot.previews.enlarged(item.preview_url) if can_attach else None
            if enlarged is not None and attached_bytes + len(enlarged) > MAX_ATTACHED_BYTES:
                enlarged = None
            if isinstance(item, Wallpaper):
                embed, item_files = build_wallpaper_message(item, enlarged)
            else:
                embed, item_files = build_mod_message(item, enlarged, await self._game_name(item.app_id))
            attached_bytes += len(enlarged or b"")
            embeds.append(embed)
            files += item_files
        return embeds, files

    async def _hide_link_preview(self, message: discord.Message) -> None:
        """Oculta el preview que Discord arma para el link, así queda solo la tarjeta de Vapora.

        Sin el permiso "Gestionar mensajes" (o en un MD, donde nunca se puede) ni se intenta:
        antes eso era un pedido rechazado por cada link pegado.
        """
        if not can_hide_previews(message.channel):
            return
        try:
            await message.edit(suppress=True)
        except discord.HTTPException:
            log.exception("No se pudo ocultar el preview del mensaje %s", message.id)
