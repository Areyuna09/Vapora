import logging
import os
from datetime import datetime, time, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

import config
from announcements import build_deals_embed, build_sale_embed, build_sales_calendar_embed
from formatting import ars_prices_for, format_ars, format_money, format_price, format_rates_footer
from prices import get_rates
import storage
from sales import ARGENTINA, due_announcements, get_sales_calendar
from steam import (
    close_session,
    extract_steam_items,
    get_argentine_app_ids,
    get_featured_specials,
    get_item_details,
    get_session,
    is_argentine,
    store_url,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

MAX_EMBEDS_PER_MESSAGE = 10  # límite de Discord
EMBED_COLOR = discord.Color(0x74ACDF)  # celeste bandera argentina
MAX_INCLUDED_NAMES = 4  # juegos listados en la tarjeta de un paquete
KIND_LABELS = {"app": "AppID", "sub": "Paquete", "bundle": "Bundle"}


class SteamPriceBot(commands.Bot):
    async def setup_hook(self) -> None:
        post_daily_deals.start()
        check_sale_announcements.start()

    async def close(self) -> None:
        await close_session()
        await super().close()


intents = discord.Intents.default()
intents.message_content = True

bot = SteamPriceBot(command_prefix="!", intents=intents)


# ── Tarjeta de un juego / DLC / paquete / bundle ─────────────────────────────

def format_reviews(reviews: dict) -> str:
    total = f"{reviews['total']:,}".replace(",", ".")
    return f"{reviews['description']}\n{reviews['positive_percent']}% de {total}"


def format_contents(data: dict) -> str | None:
    """Línea que explica qué es: DLC de qué juego, o qué incluye un paquete/bundle."""
    if data.get("dlc_of"):
        return f"🧩 DLC de **{data['dlc_of']}**"
    count = data.get("included_count")
    if not count:
        return None
    kind = "Bundle" if data.get("kind") == "bundle" else "Paquete"
    text = f"📦 {kind} con {count} {'producto' if count == 1 else 'productos'}"
    names = data.get("included") or []
    if names:
        text += ": " + ", ".join(names[:MAX_INCLUDED_NAMES])
        if len(names) > MAX_INCLUDED_NAMES:
            text += f" y {len(names) - MAX_INCLUDED_NAMES} más"
    return text


def build_description(data: dict) -> str | None:
    parts = []
    if data.get("argentine"):
        parts.append("🧉 **¡Juego argentino!** Hecho por un estudio de acá 💙")
    contents = format_contents(data)
    if contents:
        parts.append(contents)
    if data.get("short_description"):
        parts.append(data["short_description"])
    if data.get("genres"):
        parts.append("🎭 " + " · ".join(data["genres"][:4]))
    return "\n\n".join(parts) or None


def build_embed(data: dict, rates: dict[str, float] | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"🇦🇷 {data['name']}",
        url=store_url(data["kind"], data["id"]),
        description=build_description(data),
        color=EMBED_COLOR,
    )

    # Fila 1: precios
    embed.add_field(name="💵 Precio Steam (AR)", value=format_price(data), inline=True)

    ars_prices = ars_prices_for(data, rates)
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

    footer = f"{KIND_LABELS[data['kind']]} {data['id']} • Datos de Steam"
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


# ── Ofertas y rebajas ─────────────────────────────────────────────────────────

async def build_current_deals_embed() -> discord.Embed:
    session = await get_session()
    rates = await get_rates(session)
    deals = await get_featured_specials()
    argentine_ids = await get_argentine_app_ids()
    sales = await get_sales_calendar(session)
    return build_deals_embed(deals, rates, argentine_ids, datetime.now(timezone.utc), sales)


def resolve_channel(channel_id: int | None) -> discord.abc.Messageable | None:
    if not channel_id:
        return None
    channel = bot.get_channel(channel_id)
    if channel is None:
        logging.warning("No encuentro el canal %s (¿lo borraron o Vapora no lo ve?)", channel_id)
    return channel


@tasks.loop(time=time(hour=config.DEALS_HOUR, tzinfo=ARGENTINA))
async def post_daily_deals() -> None:
    targets = [resolve_channel(s.get("deals_channel")) for s in storage.all_guild_settings().values()]
    targets = [channel for channel in targets if channel]
    if not targets:
        return
    try:
        embed = await build_current_deals_embed()
    except Exception:
        logging.exception("No se pudieron obtener las ofertas del día")
        return
    for channel in targets:
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logging.exception("No se pudieron publicar las ofertas en #%s", channel)


@tasks.loop(minutes=10)
async def check_sale_announcements() -> None:
    guilds = {gid: s["sales_channel"] for gid, s in storage.all_guild_settings().items() if s.get("sales_channel")}
    if not guilds:
        return
    sales = await get_sales_calendar(await get_session())
    now = datetime.now(timezone.utc)
    for guild_id, channel_id in guilds.items():
        channel = resolve_channel(channel_id)
        if channel is None:
            continue
        prefix = f"{guild_id}:"
        sent = {key.removeprefix(prefix) for key in storage.sent_announcements() if key.startswith(prefix)}
        for sale, kind in due_announcements(now, sent, sales):
            try:
                await channel.send(embed=build_sale_embed(sale, kind))
                storage.mark_sent(f"{prefix}{sale.key}:{kind}")
                logging.info("Aviso de rebajas enviado en #%s: %s (%s)", channel, sale.name, kind)
            except discord.HTTPException:
                logging.exception("No se pudo enviar el aviso de %s (%s) en #%s", sale.name, kind, channel)


@post_daily_deals.before_loop
@check_sale_announcements.before_loop
async def wait_until_ready() -> None:
    await bot.wait_until_ready()


@bot.tree.command(name="ofertas", description="Muestra las ofertas destacadas de Steam con precio en pesos")
async def ofertas(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    await interaction.followup.send(embed=await build_current_deals_embed())


@bot.tree.command(name="rebajas", description="Muestra la rebaja de Steam actual y las próximas")
async def rebajas(interaction: discord.Interaction) -> None:
    sales = await get_sales_calendar(await get_session())
    await interaction.response.send_message(embed=build_sales_calendar_embed(datetime.now(timezone.utc), sales))


# ── /config ───────────────────────────────────────────────────────────────────

FEATURE_CHOICES = [
    app_commands.Choice(name="🔥 Ofertas destacadas (todos los días)", value="ofertas"),
    app_commands.Choice(name="📅 Avisos de rebajas de Steam", value="rebajas"),
]
FEATURE_LABELS = {"ofertas": "🔥 Ofertas destacadas", "rebajas": "📅 Avisos de rebajas"}

config_group = app_commands.Group(
    name="config",
    description="Configurar dónde publica Vapora",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),  # solo admins/moderadores
)


def missing_permissions(channel: discord.abc.GuildChannel, member: discord.Member) -> list[str]:
    perms = channel.permissions_for(member)
    required = {"Ver canal": perms.view_channel, "Enviar mensajes": perms.send_messages,
                "Insertar enlaces": perms.embed_links}
    return [name for name, ok in required.items() if not ok]


def build_config_embed(guild: discord.Guild) -> discord.Embed:
    settings = storage.get_guild_settings(guild.id)
    embed = discord.Embed(title="⚙️ Configuración de Vapora", color=EMBED_COLOR)
    for feature, key in storage.CHANNEL_KEYS.items():
        channel_id = settings.get(key)
        value = f"<#{channel_id}>" if channel_id else "Desactivado"
        if feature == "ofertas" and channel_id:
            value += f"\nTodos los días a las {config.DEALS_HOUR}:00 (hora argentina)"
        embed.add_field(name=FEATURE_LABELS[feature], value=value, inline=False)
    embed.set_footer(text="Cambialo con /config canal · Desactivalo con /config desactivar")
    return embed


@config_group.command(name="canal", description="Elegir el canal para las ofertas o los avisos de rebajas")
@app_commands.describe(que="Qué querés publicar en ese canal", canal="Canal de texto donde publicar")
@app_commands.choices(que=FEATURE_CHOICES)
async def config_canal(interaction: discord.Interaction, que: app_commands.Choice[str],
                       canal: discord.TextChannel) -> None:
    missing = missing_permissions(canal, interaction.guild.me)
    if missing:
        await interaction.response.send_message(
            f"⚠️ No puedo publicar en {canal.mention}. Me faltan estos permisos ahí: **{', '.join(missing)}**.",
            ephemeral=True,
        )
        return
    storage.set_channel(interaction.guild_id, que.value, canal.id)
    detail = (f"Las voy a publicar todos los días a las {config.DEALS_HOUR}:00."
              if que.value == "ofertas" else
              "Voy a avisar antes de cada rebaja, cuando empieza y en sus últimas 24 horas.")
    await interaction.response.send_message(
        f"✅ **{FEATURE_LABELS[que.value]}** → {canal.mention}\n{detail}", ephemeral=True)
    if que.value == "rebajas":
        await check_sale_announcements()  # si hay un aviso pendiente, mandarlo ya


@config_group.command(name="desactivar", description="Dejar de publicar ofertas o avisos de rebajas")
@app_commands.describe(que="Qué querés desactivar")
@app_commands.choices(que=FEATURE_CHOICES)
async def config_desactivar(interaction: discord.Interaction, que: app_commands.Choice[str]) -> None:
    storage.set_channel(interaction.guild_id, que.value, None)
    await interaction.response.send_message(f"🔕 **{FEATURE_LABELS[que.value]}** desactivado.", ephemeral=True)


@config_group.command(name="ver", description="Ver dónde publica Vapora en este servidor")
async def config_ver(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(embed=build_config_embed(interaction.guild), ephemeral=True)


bot.tree.add_command(config_group)


# ── Eventos ───────────────────────────────────────────────────────────────────

_commands_synced = False


@bot.event
async def on_ready():
    global _commands_synced
    logging.info("Conectado como %s (%s)", bot.user, bot.user.id)
    if not _commands_synced:
        # Sincronizar por servidor hace que los comandos aparezcan al instante.
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        _commands_synced = True
        logging.info("Comandos /ofertas, /rebajas y /config listos en %d servidor(es)", len(bot.guilds))


@bot.event
async def on_guild_join(guild: discord.Guild):
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    items = extract_steam_items(message.content)[:MAX_EMBEDS_PER_MESSAGE]
    logging.debug(
        "Mensaje en #%s de %s (%d caracteres, links: %s)",
        message.channel, message.author, len(message.content), items,
    )
    if items:
        embeds = []
        rates = await get_rates(await get_session())
        for kind, item_id in items:
            try:
                data = await get_item_details(kind, item_id, country="ar")
                if data:
                    argentine = kind == "app" and await is_argentine(item_id)
                    embeds.append(build_embed({**data, "argentine": argentine}, rates))
            except Exception:
                logging.exception("Error procesando %s %s", kind, item_id)

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
