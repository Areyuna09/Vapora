import os
import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

import config
from prices import calculate_ars_prices, get_rates
from steam import close_session, extract_app_ids, get_app_details, get_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

MAX_EMBEDS_PER_MESSAGE = 10  # límite de Discord
EMBED_COLOR = discord.Color(0x74ACDF)  # celeste bandera argentina


class SteamPriceBot(commands.Bot):
    async def close(self) -> None:
        await close_session()
        await super().close()


intents = discord.Intents.default()
intents.message_content = True

bot = SteamPriceBot(command_prefix="!", intents=intents)


def format_money(cents: int, currency: str | None) -> str:
    """Formatea centavos al estilo argentino: 2999 -> 'USD 29,99'."""
    amount = f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency or ''} {amount}".strip()


def format_price(data: dict) -> str:
    if data.get("final_cents") is not None:
        text = f"**{format_money(data['final_cents'], data.get('currency'))}**"
        if data.get("discount_percent"):
            before = format_money(data["initial_cents"], data.get("currency"))
            text += f"\n~~{before}~~ (-{data['discount_percent']}%)"
        return text
    if data.get("price"):
        return data["price"]
    if data.get("is_free"):
        return "**Gratis**"
    return "Sin precio disponible"


def format_ars(amount: float) -> str:
    """Formatea pesos al estilo argentino: 56244.5 -> '$ 56.244,50'."""
    return "$ " + format_money(round(amount * 100), None)


def format_rates_footer(rates: dict[str, float]) -> str:
    parts = []
    if rates.get("oficial"):
        parts.append(f"Oficial {format_ars(rates['oficial'])}")
    if rates.get("cripto"):
        parts.append(f"ARQ {format_ars(rates['cripto'])}")
    taxes = f"IVA {config.IVA_PERCENT:g}%"
    taxes += f" + IIBB {config.PROVINCE_TAX_PERCENT:g}%" if config.PROVINCE_TAX_PERCENT else " (sin IIBB)"
    parts.append(taxes)
    return " · ".join(parts)


def format_reviews(reviews: dict) -> str:
    total = f"{reviews['total']:,}".replace(",", ".")
    return f"{reviews['description']}\n{reviews['positive_percent']}% de {total}"


def build_description(data: dict) -> str | None:
    parts = []
    if data.get("short_description"):
        parts.append(data["short_description"])
    if data.get("genres"):
        parts.append("🎭 " + " · ".join(data["genres"][:4]))
    return "\n\n".join(parts) or None


def build_embed(app_id: int, data: dict, rates: dict[str, float] | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"🇦🇷 {data['name']}",
        url=f"https://store.steampowered.com/app/{app_id}/",
        description=build_description(data),
        color=EMBED_COLOR,
    )

    # Fila 1: precios
    embed.add_field(name="💵 Precio Steam (AR)", value=format_price(data), inline=True)

    ars_prices = {}
    if rates and data.get("final_cents") and data.get("currency") == "USD":
        ars_prices = calculate_ars_prices(data["final_cents"], rates)
    if "tarjeta" in ars_prices:
        embed.add_field(name="💳 Mercado Pago", value=f"**{format_ars(ars_prices['tarjeta'])}**", inline=True)
    if "cripto" in ars_prices:
        embed.add_field(name="🟣 ARQ", value=f"**{format_ars(ars_prices['cripto'])}**", inline=True)

    # Fila 2: info del juego
    if data.get("reviews"):
        embed.add_field(name="⭐ Reseñas", value=format_reviews(data["reviews"]), inline=True)

    if data.get("release_date"):
        label = "📅 Próximamente" if data.get("coming_soon") else "📅 Lanzamiento"
        embed.add_field(name=label, value=data["release_date"], inline=True)

    if data.get("developers"):
        embed.add_field(name="🛠️ Desarrollador", value=", ".join(data["developers"][:2]), inline=True)

    if data.get("header_image"):
        embed.set_image(url=data["header_image"])

    footer = f"AppID {app_id} • Datos de Steam"
    if ars_prices:
        footer += f"\n{format_rates_footer(rates)}"
    embed.set_footer(text=footer)
    return embed


async def suppress_original_embeds(message: discord.Message) -> None:
    """Oculta el preview de Discord en el mensaje original (requiere Gestionar mensajes)."""
    try:
        await message.edit(suppress=True)
    except discord.Forbidden:
        logging.warning(
            "Sin permiso 'Gestionar mensajes' en #%s: no se puede ocultar el preview original.",
            message.channel,
        )
    except discord.HTTPException:
        logging.exception("No se pudo ocultar el preview del mensaje %s", message.id)


@bot.event
async def on_ready():
    logging.info("Conectado como %s (%s)", bot.user, bot.user.id)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    app_ids = extract_app_ids(message.content)[:MAX_EMBEDS_PER_MESSAGE]
    logging.debug(
        "Mensaje en #%s de %s (%d caracteres, AppIDs: %s)",
        message.channel, message.author, len(message.content), app_ids,
    )
    if app_ids:
        embeds = []
        rates = await get_rates(await get_session())
        for app_id in app_ids:
            try:
                data = await get_app_details(app_id, country="ar")
                if data:
                    embeds.append(build_embed(app_id, data, rates))
            except Exception:
                logging.exception("Error procesando AppID %s", app_id)

        if embeds:
            await message.reply(embeds=embeds, mention_author=False)
            await suppress_original_embeds(message)

    await bot.process_commands(message)


@bot.command()
async def ping(ctx: commands.Context):
    """Prueba simple para verificar que el bot responde."""
    await ctx.send("🏓 Pong!")


def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Falta DISCORD_TOKEN (en el archivo .env o como variable de entorno).")
    bot.run(token, log_handler=None)  # ya configuramos logging arriba


if __name__ == "__main__":
    main()
