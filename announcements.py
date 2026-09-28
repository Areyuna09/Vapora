"""Tarjetas de ofertas destacadas y avisos de rebajas de Steam."""

from datetime import datetime

import discord

from formatting import ars_prices_for, format_ars, format_money, format_rates_footer
from sales import FALLBACK_SALES, SteamSale, active_sale, discord_timestamp, format_argentina_time, upcoming_sales
from steam import store_url

DEALS_COLOR = discord.Color(0xE8A33D)  # naranja oferta
SALE_COLOR = discord.Color(0x74ACDF)


def format_deal_line(deal: dict, rates: dict[str, float] | None, argentine_ids: set[int]) -> str:
    flag = " 🧉" if deal["kind"] == "app" and deal["id"] in argentine_ids else ""
    line = f"**[{deal['name']}]({store_url(deal['kind'], deal['id'])})**{flag}\n"
    line += f"-{deal['discount_percent']}% · "
    if deal.get("initial_cents"):
        line += f"~~{format_money(deal['initial_cents'], deal.get('currency'))}~~ "
    line += f"**{format_money(deal['final_cents'], deal.get('currency'))}**"
    ars = ars_prices_for(deal, rates)
    if ars:
        parts = []
        if "tarjeta" in ars:
            parts.append(f"💳 {format_ars(ars['tarjeta'])}")
        if "cripto" in ars:
            parts.append(f"🟣 {format_ars(ars['cripto'])}")
        line += "\n" + " · ".join(parts)
    return line


def build_deals_embed(deals: list[dict], rates: dict[str, float] | None, argentine_ids: set[int],
                      now: datetime, sales: list[SteamSale] = FALLBACK_SALES) -> discord.Embed:
    sale = active_sale(now, sales)
    title = f"{sale.emoji} Ofertas destacadas · {sale.name}" if sale else "🔥 Ofertas destacadas de hoy"
    embed = discord.Embed(title=title, color=DEALS_COLOR)

    if not deals:
        embed.description = "Hoy Steam no tiene ofertas destacadas. ¡Volvé mañana!"
        return embed

    embed.description = "\n\n".join(format_deal_line(d, rates, argentine_ids) for d in deals)
    if deals[0].get("image"):
        embed.set_thumbnail(url=deals[0]["image"])

    expirations = {d["discount_expiration"] for d in deals if d.get("discount_expiration")}
    if len(expirations) == 1:
        embed.add_field(name="⏳ Terminan", value=discord_timestamp(datetime.fromtimestamp(expirations.pop())))

    footer = "💳 Mercado Pago · 🟣 ARQ · 🧉 juego argentino"
    if rates:
        footer += f"\n{format_rates_footer(rates)}"
    embed.set_footer(text=footer)
    return embed


SALE_MESSAGES = {
    "7d": ("¡Se vienen!", "Arrancan {when}. Andá armando la lista de deseados 📝"),
    "1d": ("¡Mañana arrancan!", "Empiezan {when}. Preparen la billetera 💸"),
    "start": ("¡Ya arrancaron!", "Duran hasta {end}. ¡A cazar ofertas! 🎯"),
    "ending": ("¡Últimas 24 horas!", "Terminan {end}. Si tenés algo en el carrito, es ahora ⏰"),
}


def build_sale_embed(sale: SteamSale, kind: str) -> discord.Embed:
    headline, text = SALE_MESSAGES[kind]
    embed = discord.Embed(
        title=f"{sale.emoji} {sale.name} de Steam · {headline}",
        description=text.format(
            when=f"el **{format_argentina_time(sale.start)}** ({discord_timestamp(sale.start)})",
            end=f"el **{format_argentina_time(sale.end)}** ({discord_timestamp(sale.end)})",
        ),
        url="https://store.steampowered.com/",
        color=SALE_COLOR,
    )
    embed.set_footer(text="Horarios en hora argentina · Fechas del calendario oficial de Steam")
    return embed


def build_sales_calendar_embed(now: datetime, sales: list[SteamSale] = FALLBACK_SALES) -> discord.Embed:
    embed = discord.Embed(title="📅 Rebajas de Steam", color=SALE_COLOR)
    current = active_sale(now, sales)
    if current:
        embed.add_field(
            name=f"{current.emoji} Ahora: {current.name}",
            value=f"Termina el **{format_argentina_time(current.end)}** ({discord_timestamp(current.end)})",
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
    embed.set_footer(text="Horarios en hora argentina · Fechas del calendario oficial de Steam")
    return embed
