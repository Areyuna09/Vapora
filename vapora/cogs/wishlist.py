"""Deseados: /deseado, el botón "Avisame si baja" y los avisos cuando un juego entra en oferta."""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from vapora.cogs._tasks import survives_errors
from vapora.pricing import PesoConverter
from vapora.sales import SteamSale
from vapora.steam import ItemRef, Price, SteamError, StoreItem
from vapora.storage import MAX_WISHLIST_SIZE, AddWishResult, Feature, Wish
from vapora.ui.game_card import build_game_card
from vapora.ui.panels import build_wishlist_embed
from vapora.wishlist import OfferAction, choice_value, find_wish, offer_action, resolve_app_id

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

log = logging.getLogger(__name__)

PRICE_CHECK_HOURS = 1
MIN_SEARCH_LENGTH = 2
MAX_CHOICES = 25  # límite de Discord para el autocompletado
MAX_CHOICE_NAME_LENGTH = 100  # límite de Discord


class WishlistCog(commands.Cog):
    wish = app_commands.Group(
        name="deseado",
        description="Tu lista de deseados: Vapora te avisa cuando entran en oferta",
    )

    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.check_prices.start()

    async def cog_unload(self) -> None:
        self.check_prices.cancel()

    # ── /deseado agregar ──────────────────────────────────────────────────────

    @wish.command(name="agregar", description="Agregar un juego a tus deseados")
    @app_commands.describe(juego="Nombre del juego (elegilo de la lista) o link de Steam")
    async def add(self, interaction: discord.Interaction, juego: str) -> None:
        await interaction.response.defer(ephemeral=True)
        app_id = await resolve_app_id(juego, self.bot.steam)
        item = await self.bot.steam.get_item(ItemRef.app(app_id)) if app_id else None
        if item is None:
            await interaction.followup.send(
                "🤔 No encontré ese juego en Steam. Probá con el link de la tienda.", ephemeral=True
            )
            return
        await self._add_and_reply(interaction, item, show_card=True)

    @add.autocomplete("juego")
    async def _suggest_store_games(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Sugiere juegos de la tienda mientras se escribe el nombre."""
        if len(current.strip()) < MIN_SEARCH_LENGTH or "steampowered.com" in current:
            return []
        try:
            results = await self.bot.steam.search(current)
        except SteamError:
            return []
        return [_choice(result.name, result.app_id) for result in results]

    @commands.Cog.listener()
    async def on_wish_button(self, interaction: discord.Interaction, app_id: int) -> None:
        """Alguien tocó "Avisame si baja" en una tarjeta (ver `events.WISH_BUTTON`).

        El botón ya dejó la respuesta "pensando…": pase lo que pase hay que contestar, porque
        los errores de un evento no llegan al manejador de los comandos y quedaría colgado.
        """
        try:
            await self._add_from_button(interaction, app_id)
        except Exception:
            log.exception("Falló el botón de deseados para %s", app_id)
            try:
                await interaction.followup.send(
                    "😕 Algo salió mal. Probá de nuevo en un rato.", ephemeral=True
                )
            except discord.HTTPException:
                log.warning("No pude avisarle al usuario del error", exc_info=True)

    async def _add_from_button(self, interaction: discord.Interaction, app_id: int) -> None:
        try:
            item = await self.bot.steam.get_item(ItemRef.app(app_id))
        except SteamError:
            item = None
        if item is None:
            await interaction.followup.send(
                "😕 No pude consultar ese juego en Steam. Probá de nuevo en un rato.", ephemeral=True
            )
            return
        await self._add_and_reply(interaction, item, show_card=False)

    async def _add_and_reply(
        self, interaction: discord.Interaction, item: StoreItem, *, show_card: bool
    ) -> None:
        """Suma el juego a los deseados de quien lo pidió y le responde en privado.

        Si el juego ya está en oferta se lo dice ahora y se guarda ese precio como avisado,
        para no mandarle después un aviso de la misma oferta.
        """
        already_on_sale = offer_action(None, item.price) is OfferAction.NOTIFY
        notified_cents = item.price.final_cents if already_on_sale and item.price else None
        result = await self.bot.db.add_wish(
            interaction.user.id, item.ref.id, item.name, interaction.guild_id, notified_cents
        )

        if result is AddWishResult.ALREADY_THERE:
            await interaction.followup.send(f"Ya tenías **{item.name}** en tus deseados 😉", ephemeral=True)
        elif result is AddWishResult.LIST_FULL:
            await interaction.followup.send(
                f"Tu lista está llena ({MAX_WISHLIST_SIZE} juegos). Sacá alguno con `/deseado quitar`.",
                ephemeral=True,
            )
        elif not already_on_sale:
            where = await self._describe_notice_destination(interaction.guild_id)
            await interaction.followup.send(
                f"✅ Agregué **{item.name}** a tus deseados. {where}", ephemeral=True
            )
        else:
            text = f"✅ Agregué **{item.name}** a tus deseados. ¡Y ya está en oferta! 🔥"
            if show_card:
                card = build_game_card(item, await self.bot.peso_converter(), await self.bot.current_sale())
                await interaction.followup.send(text, embed=card, ephemeral=True)
            else:
                await interaction.followup.send(text, ephemeral=True)

    async def _describe_notice_destination(self, guild_id: int | None) -> str:
        channel_id = await self._notice_channel_id(guild_id)
        if channel_id:
            return f"Te aviso en <#{channel_id}> cuando entre en oferta 🔔"
        return "Te aviso por MD cuando entre en oferta 🔔"

    # ── /deseado quitar y /deseado lista ──────────────────────────────────────

    @wish.command(name="quitar", description="Quitar un juego de tus deseados")
    @app_commands.describe(juego="Juego a quitar (elegilo de la lista o escribí su nombre)")
    async def remove(self, interaction: discord.Interaction, juego: str) -> None:
        wish = find_wish(await self.bot.db.wishlist(interaction.user.id), juego)
        name = await self.bot.db.remove_wish(wish.user_id, wish.app_id) if wish else None
        text = f"🗑️ Saqué **{name}** de tus deseados." if name else "Ese juego no está en tus deseados."
        await interaction.response.send_message(text, ephemeral=True)

    @remove.autocomplete("juego")
    async def _suggest_own_wishes(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Sugiere los juegos que la persona ya tiene en su lista."""
        wishes = await self.bot.db.wishlist(interaction.user.id)
        matches = [wish for wish in wishes if current.lower() in wish.name.lower()]
        return [_choice(wish.name, wish.app_id) for wish in matches[:MAX_CHOICES]]

    @wish.command(name="lista", description="Ver tu lista de deseados")
    async def show(self, interaction: discord.Interaction) -> None:
        wishes = await self.bot.db.wishlist(interaction.user.id)
        if not wishes:
            await interaction.response.send_message(
                "Tu lista está vacía. Agregá juegos con `/deseado agregar` 📝", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=build_wishlist_embed(wishes), ephemeral=True)

    # ── Avisos de ofertas ─────────────────────────────────────────────────────

    @tasks.loop(hours=PRICE_CHECK_HOURS)
    @survives_errors
    async def check_prices(self) -> None:
        """Revisa el precio de todos los deseados y avisa de las ofertas nuevas.

        Primero pide solo los precios, todos juntos (unos pocos pedidos a Steam aunque haya
        muchos juegos). Los datos completos para la tarjeta se piden solo de los que hay
        que avisar.
        """
        wishes = await self.bot.db.all_wishes()
        if not wishes:
            return
        try:
            prices = await self.bot.steam.prices({wish.app_id for wish in wishes})
        except SteamError:
            log.warning("No pude consultar los precios de los deseados", exc_info=True)
            return
        converter = await self.bot.peso_converter()
        sale = await self.bot.current_sale()
        cards: dict[int, StoreItem | None] = {}  # datos para tarjetas ya pedidos en esta revisión
        for wish in wishes:
            if wish.app_id in prices:  # si Steam no lo informó, se revisa la próxima vez
                await self._update_wish(wish, prices[wish.app_id], cards, converter, sale)

    @check_prices.before_loop
    async def _wait_until_ready(self) -> None:
        await self.bot.wait_until_ready()

    async def _update_wish(
        self,
        wish: Wish,
        price: Price | None,
        cards: dict[int, StoreItem | None],
        converter: PesoConverter,
        sale: SteamSale | None,
    ) -> None:
        action = offer_action(wish.notified_final_cents, price)
        if action is OfferAction.NOTIFY and price is not None:
            if wish.app_id not in cards:
                cards[wish.app_id] = await self._fetch_card_item(wish.app_id, price)
            item = cards[wish.app_id]
            # Si no se pudo avisar no se marca, así se reintenta en la próxima revisión.
            if item is not None and await self._notify(wish, item, converter, sale):
                await self.bot.db.set_wish_notified(wish.user_id, wish.app_id, price.final_cents)
                log.info("Aviso de deseado: %s a %s", item.name, wish.user_id)
        elif action is OfferAction.RESET:
            await self.bot.db.set_wish_notified(wish.user_id, wish.app_id, None)

    async def _fetch_card_item(self, app_id: int, price: Price) -> StoreItem | None:
        """Datos para la tarjeta del aviso, con el precio recién consultado.

        Los datos pueden venir del caché (hasta una hora), así que se les pone el precio
        actual para que la tarjeta muestre la oferta que se está avisando.
        """
        try:
            item = await self.bot.steam.get_item(ItemRef.app(app_id))
        except SteamError:
            log.warning("No pude consultar el deseado %s para avisar", app_id, exc_info=True)
            return None
        return replace(item, price=price) if item is not None else None

    async def _notify(
        self, wish: Wish, item: StoreItem, converter: PesoConverter, sale: SteamSale | None
    ) -> bool:
        """Avisa en el canal de deseados del servidor, mencionando a la persona; si no hay, por MD."""
        discount = item.price.discount_percent if item.price else 0
        text = f"🔔 ¡**{item.name}**, de tu lista de deseados, está en oferta! (-{discount}%)"
        card = build_game_card(item, converter, sale)

        channel = self.bot.find_channel(await self._notice_channel_id(wish.guild_id))
        if channel is not None:
            try:
                await channel.send(
                    f"<@{wish.user_id}> {text}",
                    embed=card,
                    # Solo se menciona a quien pidió el aviso (el resto del texto viene de Steam).
                    allowed_mentions=discord.AllowedMentions(
                        everyone=False, roles=False, users=[discord.Object(wish.user_id)]
                    ),
                )
                return True
            except discord.HTTPException:
                log.exception("No pude avisar en #%s, pruebo por MD", channel)
        try:
            user = self.bot.get_user(wish.user_id) or await self.bot.fetch_user(wish.user_id)
            await user.send(text, embed=card)
            return True
        except discord.HTTPException:
            log.warning(
                "No pude avisarle a %s de la oferta de %s (sin canal y MD cerrados)", wish.user_id, item.name
            )
            return False

    async def _notice_channel_id(self, guild_id: int | None) -> int | None:
        if guild_id is None:
            return None
        return (await self.bot.db.channels(guild_id)).get(Feature.WISHLIST)


def _choice(name: str, app_id: int) -> app_commands.Choice[str]:
    return app_commands.Choice(name=name[:MAX_CHOICE_NAME_LENGTH], value=choice_value(app_id))
