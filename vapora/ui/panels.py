"""Tarjetas de los comandos /ayuda, /config y /deseado."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import discord

from vapora.pricing import Taxes
from vapora.steam import ItemRef
from vapora.storage import MAX_WISHLIST_SIZE, Feature, Wish
from vapora.ui.style import BRAND_COLOR

FEATURE_LABELS = {
    Feature.DEALS: "🔥 Ofertas destacadas",
    Feature.SALES: "📅 Avisos de rebajas",
    Feature.WISHLIST: "🔔 Avisos de deseados",
    Feature.WALLPAPERS: "🖼️ Fondo del día",
}


def build_help_embed(*, is_admin: bool, taxes: Taxes, rates_refresh_minutes: int) -> discord.Embed:
    """Qué hace Vapora. La sección de administración solo se muestra a quien puede usarla."""
    embed = discord.Embed(
        title="💨 ¡Hola, soy Vapora!",
        description="Te digo cuánto salen los juegos de Steam en pesos argentinos 🇦🇷",
        color=BRAND_COLOR,
    )
    embed.add_field(
        name="🔗 Pegá un link de Steam",
        value="Mandá un link de la tienda en cualquier canal y respondo con el precio en USD, "
        "💳 Mercado Pago y 🟣 ARQ, reseñas y más. Funciona con juegos, DLC, paquetes y bundles. "
        "Si el juego es argentino, lo marco con 🧉\n"
        "También muestro los fondos de Wallpaper Engine del Workshop 🖼️",
        inline=False,
    )
    embed.add_field(
        name="🎮 Comandos",
        value="`/ofertas` · ofertas destacadas de Steam en pesos\n"
        "`/rebajas` · la rebaja actual y las próximas\n"
        "`/deseado agregar` · sumá un juego a tu lista (o tocá 🔔 en una tarjeta) "
        "y te aviso cuando entre en oferta\n"
        "`/deseado lista` · `/deseado quitar` · ver o sacar juegos de tu lista\n"
        "`/fondo` · un fondo de Wallpaper Engine en tendencia (podés elegir categoría)\n"
        "`/ayuda` · este mensaje",
        inline=False,
    )
    if is_admin:
        embed.add_field(
            name="⚙️ Administración",
            value="`/config canal` · elegir dónde publico ofertas diarias, avisos de rebajas, "
            "de deseados y el fondo del día\n"
            "`/config ver` · ver la configuración del servidor\n"
            "`/config desactivar` · dejar de publicar algo",
            inline=False,
        )
    embed.add_field(
        name="💰 ¿Cómo calculo los precios?",
        value=f"💳 **Mercado Pago**: USD × dólar oficial + IVA {taxes.iva_percent:g}%\n"
        "🟣 **ARQ**: USD × dólar cripto, sin impuestos\n"
        f"Las cotizaciones se actualizan cada {rates_refresh_minutes} minutos.",
        inline=False,
    )
    embed.set_footer(text="Datos de Steam y DolarAPI")
    return embed


def build_config_embed(
    channels: Mapping[Feature, int], deals_hour: int, wallpaper_hour: int
) -> discord.Embed:
    """Dónde publica Vapora cada tipo de aviso en un servidor."""
    embed = discord.Embed(title="⚙️ Configuración de Vapora", color=BRAND_COLOR)
    daily_hours = {Feature.DEALS: deals_hour, Feature.WALLPAPERS: wallpaper_hour}
    for feature, label in FEATURE_LABELS.items():
        channel_id = channels.get(feature)
        value = f"<#{channel_id}>" if channel_id else "Desactivado"
        if feature in daily_hours and channel_id:
            value += f"\nTodos los días a las {daily_hours[feature]}:00 (hora argentina)"
        embed.add_field(name=label, value=value, inline=False)
    embed.set_footer(text="Cambialo con /config canal · Desactivalo con /config desactivar")
    return embed


def build_wishlist_embed(wishes: Sequence[Wish]) -> discord.Embed:
    lines = [
        f"• [{wish.name}]({ItemRef.app(wish.app_id).url})" + (" 🔥" if wish.on_sale else "")
        for wish in wishes
    ]
    embed = discord.Embed(
        title=f"📝 Tus deseados ({len(wishes)}/{MAX_WISHLIST_SIZE})",
        description="\n".join(lines),
        color=BRAND_COLOR,
    )
    embed.set_footer(text="🔥 = en oferta ahora · Reviso los precios cada hora")
    return embed
