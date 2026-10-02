"""Tarjeta que Vapora muestra cuando alguien comparte un link de Steam."""

from __future__ import annotations

import discord

from vapora.pricing import PesoConverter
from vapora.sales import SteamSale
from vapora.steam import ItemKind, StoreItem
from vapora.ui.formatting import format_item_price, format_pesos, format_rates_footer, format_reviews
from vapora.ui.style import CARD_PAYMENT_LABEL, CRYPTO_PAYMENT_LABEL, sale_color

MAX_GENRES = 4
MAX_DEVELOPERS = 2
MAX_INCLUDED_NAMES = 4  # productos que se nombran en la tarjeta de un paquete

_ID_LABELS = {ItemKind.APP: "AppID", ItemKind.PACKAGE: "Paquete", ItemKind.BUNDLE: "Bundle"}


def describe_contents(item: StoreItem) -> str | None:
    """Línea que explica qué es: DLC de qué juego, o qué incluye un paquete o bundle."""
    if item.dlc_of:
        return f"🧩 DLC de **{item.dlc_of}**"
    if not item.included_count:
        return None
    kind = "Bundle" if item.ref.kind is ItemKind.BUNDLE else "Paquete"
    noun = "producto" if item.included_count == 1 else "productos"
    text = f"📦 {kind} con {item.included_count} {noun}"
    if item.included:
        text += ": " + ", ".join(item.included[:MAX_INCLUDED_NAMES])
        remaining = len(item.included) - MAX_INCLUDED_NAMES
        if remaining > 0:
            text += f" y {remaining} más"
    return text


def build_description(item: StoreItem) -> str | None:
    parts = []
    if item.argentine:
        parts.append("🧉 **¡Juego argentino!** Hecho por un estudio de acá 💙")
    contents = describe_contents(item)
    if contents:
        parts.append(contents)
    if item.description:
        parts.append(item.description)
    if item.genres:
        parts.append("🎭 " + " · ".join(item.genres[:MAX_GENRES]))
    return "\n\n".join(parts) or None


def build_game_card(
    item: StoreItem, converter: PesoConverter | None = None, sale: SteamSale | None = None
) -> discord.Embed:
    """Tarjeta de un juego, DLC, paquete o bundle.

    Args:
        converter: cotizaciones del momento. Sin ellas, la tarjeta muestra solo el precio de Steam.
        sale: rebaja de Steam en curso, si hay. La tarjeta toma su color mientras dura.
    """
    embed = discord.Embed(
        title=f"🇦🇷 {item.name}",
        url=item.ref.url,
        description=build_description(item),
        color=sale_color(sale),
    )

    # Primera fila: precios.
    embed.add_field(name="💵 Precio Steam (AR)", value=format_item_price(item), inline=True)
    pesos = converter.convert(item.price) if converter else None
    if pesos and pesos.card is not None:
        embed.add_field(name=CARD_PAYMENT_LABEL, value=f"**{format_pesos(pesos.card)}**", inline=True)
    if pesos and pesos.crypto is not None:
        embed.add_field(name=CRYPTO_PAYMENT_LABEL, value=f"**{format_pesos(pesos.crypto)}**", inline=True)

    # Segunda fila: datos del juego.
    if item.reviews:
        embed.add_field(name="⭐ Reseñas", value=format_reviews(item.reviews), inline=True)
    if item.release_date:
        label = "📅 Próximamente" if item.coming_soon else "📅 Lanzamiento"
        embed.add_field(name=label, value=item.release_date, inline=True)
    if item.developers:
        embed.add_field(
            name="🛠️ Desarrollador", value=", ".join(item.developers[:MAX_DEVELOPERS]), inline=True
        )

    if item.image_url:
        embed.set_image(url=item.image_url)

    footer = f"{_ID_LABELS[item.ref.kind]} {item.ref.id} • Datos de Steam"
    if pesos and converter:
        footer += f"\n{format_rates_footer(converter)}"
    embed.set_footer(text=footer)
    return embed
