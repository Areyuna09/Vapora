"""Colores y textos que comparten las tarjetas de Vapora."""

import discord

from vapora.sales import SteamSale

BRAND_COLOR = discord.Color(0x74ACDF)  # celeste de la bandera argentina
DEALS_COLOR = discord.Color(0xE8A33D)  # naranja de oferta

CARD_PAYMENT_LABEL = "💳 Mercado Pago"
CRYPTO_PAYMENT_LABEL = "🟣 ARQ"
ARGENTINE_MARK = "🧉"


def sale_color(sale: SteamSale | None, default: discord.Color = BRAND_COLOR) -> discord.Color:
    """Color de la rebaja en curso, o `default` si no hay rebaja o no tiene color propio."""
    if sale is None or sale.color is None:
        return default
    return discord.Color(sale.color)
