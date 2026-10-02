"""Tarjetas de ofertas destacadas y de avisos de rebajas de Steam."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime

import discord

from vapora.pricing import PesoConverter
from vapora.sales import (
    SaleNotice,
    SteamSale,
    active_sale,
    discord_timestamp,
    format_argentina_time,
    upcoming_sales,
)
from vapora.steam import Deal, ItemKind
from vapora.ui.formatting import format_original_price, format_pesos, format_rates_footer, format_steam_price
from vapora.ui.style import ARGENTINE_MARK, BRAND_COLOR, DEALS_COLOR, sale_color

_CALENDAR_FOOTER = "Horarios en hora argentina · Fechas del calendario oficial de Steam"

# Título y texto de cada aviso. {when} y {end} se reemplazan por la fecha de inicio y de fin.
_NOTICE_TEXTS = {
    SaleNotice.WEEK_BEFORE: ("¡Se vienen!", "Arrancan {when}. Andá armando la lista de deseados 📝"),
    SaleNotice.DAY_BEFORE: ("¡Mañana arrancan!", "Empiezan {when}. Preparen la billetera 💸"),
    SaleNotice.STARTED: ("¡Ya arrancaron!", "Duran hasta {end}. ¡A cazar ofertas! 🎯"),
    SaleNotice.ENDING: ("¡Últimas 24 horas!", "Terminan {end}. Si tenés algo en el carrito, es ahora ⏰"),
}


def format_deal(deal: Deal, converter: PesoConverter | None, argentine_app_ids: Collection[int]) -> str:
    """Una oferta en tres líneas: nombre con link, descuento y precio en pesos."""
    is_argentine = deal.ref.kind is ItemKind.APP and deal.ref.id in argentine_app_ids
    mark = f" {ARGENTINE_MARK}" if is_argentine else ""
    lines = [f"**[{deal.name}]({deal.ref.url})**{mark}"]

    original = format_original_price(deal.price)
    before = f"~~{original}~~ " if original else ""
    lines.append(f"-{deal.price.discount_percent}% · {before}**{format_steam_price(deal.price)}**")

    pesos = converter.convert(deal.price) if converter else None
    if pesos:
        parts = []
        if pesos.card is not None:
            parts.append(f"💳 {format_pesos(pesos.card)}")
        if pesos.crypto is not None:
            parts.append(f"🟣 {format_pesos(pesos.crypto)}")
        lines.append(" · ".join(parts))
    return "\n".join(lines)


def build_deals_embed(
    deals: Sequence[Deal],
    converter: PesoConverter | None,
    argentine_app_ids: Collection[int],
    current_sale: SteamSale | None,
) -> discord.Embed:
    """Ofertas destacadas del día. Durante una rebaja, el título lleva su nombre."""
    if current_sale:
        title = f"{current_sale.emoji} Ofertas destacadas · {current_sale.name}"
    else:
        title = "🔥 Ofertas destacadas de hoy"
    embed = discord.Embed(title=title, color=sale_color(current_sale, default=DEALS_COLOR))

    if not deals:
        embed.description = "Hoy Steam no tiene ofertas destacadas. ¡Volvé mañana!"
        return embed

    embed.description = "\n\n".join(format_deal(deal, converter, argentine_app_ids) for deal in deals)
    if deals[0].image_url:
        embed.set_thumbnail(url=deals[0].image_url)

    expirations = {deal.expires_at for deal in deals if deal.expires_at}
    if len(expirations) == 1:
        embed.add_field(name="⏳ Terminan", value=discord_timestamp(expirations.pop()))

    footer = "💳 Mercado Pago · 🟣 ARQ · 🧉 juego argentino"
    if converter and converter.rates.available:
        footer += f"\n{format_rates_footer(converter)}"
    embed.set_footer(text=footer)
    return embed


def build_sale_notice_embed(sale: SteamSale, notice: SaleNotice) -> discord.Embed:
    headline, text = _NOTICE_TEXTS[notice]
    embed = discord.Embed(
        title=f"{sale.emoji} {sale.name} de Steam · {headline}",
        description=text.format(when=_describe_moment(sale.start), end=_describe_moment(sale.end)),
        url="https://store.steampowered.com/",
        color=sale_color(sale),
    )
    embed.set_footer(text=_CALENDAR_FOOTER)
    return embed


def build_sales_calendar_embed(now: datetime, sales: Sequence[SteamSale]) -> discord.Embed:
    """La rebaja en curso (si hay) y las próximas."""
    embed = discord.Embed(title="📅 Rebajas de Steam", color=BRAND_COLOR)
    current = active_sale(now, sales)
    if current:
        embed.add_field(
            name=f"{current.emoji} Ahora: {current.name}",
            value=f"Termina {_describe_moment(current.end)}",
            inline=False,
        )
    upcoming = upcoming_sales(now, sales)
    for sale in upcoming:
        embed.add_field(
            name=f"{sale.emoji} {sale.name}",
            value=f"{format_argentina_time(sale.start)} ({discord_timestamp(sale.start)})",
            inline=False,
        )
    if not current and not upcoming:
        embed.description = "No hay rebajas cargadas en el calendario."
    embed.set_footer(text=_CALENDAR_FOOTER)
    return embed


def _describe_moment(moment: datetime) -> str:
    """'el **jueves 1/10 a las 14:00** (en 3 días)'."""
    return f"el **{format_argentina_time(moment)}** ({discord_timestamp(moment)})"
