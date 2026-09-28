import logging
import os
import re
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
    search_store,
    store_url,
)
from wishlist import offer_action, resolve_game

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
        check_wishlists.start()
        self.add_dynamic_items(WishButton)  # botones "Avisame si baja" de mensajes anteriores

    async def close(self) -> None:
        await close_session()
        await super().close()


intents = discord.Intents.default()
intents.message_content = True

# Estado que se ve debajo del nombre en la lista de miembros.
STATUS_TEXT = "Precios de Steam 🇦🇷"

bot = SteamPriceBot(command_prefix="!", intents=intents, activity=discord.CustomActivity(name=STATUS_TEXT))


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
        sent = storage.sent_announcements(guild_id)
        for sale, kind in due_announcements(now, sent, sales):
            try:
                await channel.send(embed=build_sale_embed(sale, kind))
                storage.mark_sent(guild_id, sale.key, kind)
                logging.info("Aviso de rebajas enviado en #%s: %s (%s)", channel, sale.name, kind)
            except discord.HTTPException:
                logging.exception("No se pudo enviar el aviso de %s (%s) en #%s", sale.name, kind, channel)


def wish_channel_id(guild_id: int | None) -> int | None:
    return storage.get_guild_settings(guild_id).get("wishlist_channel") if guild_id else None


async def notify_wish(user_id: int, guild_id: int | None, data: dict, rates: dict[str, float]) -> bool:
    """Avisa en el canal de deseados del servidor (mencionando al usuario); si no hay canal, por MD."""
    text = f"🔔 ¡**{data['name']}**, de tu lista de deseados, está en oferta! (-{data['discount_percent']}%)"
    embed = build_embed(data, rates)
    channel = resolve_channel(wish_channel_id(guild_id))
    if channel is not None:
        try:
            await channel.send(f"<@{user_id}> {text}", embed=embed,
                               allowed_mentions=discord.AllowedMentions(users=True))
            return True
        except discord.HTTPException:
            logging.exception("No pude avisar en #%s, pruebo por MD", channel)
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        await user.send(text, embed=embed)
        return True
    except discord.HTTPException:
        logging.warning("No pude avisarle a %s de la oferta de %s (sin canal y MD cerrados)", user_id, data["name"])
        return False


@tasks.loop(hours=1)
async def check_wishlists() -> None:
    wishlists = storage.all_wishlists()
    if not wishlists:
        return
    rates = await get_rates(await get_session())
    games: dict[int, dict | None] = {}
    for app_id in {app_id for games_ in wishlists.values() for app_id in games_}:
        try:
            data = await get_item_details("app", app_id, country="ar")
            games[app_id] = {**data, "argentine": await is_argentine(app_id)} if data else None
        except Exception:
            logging.exception("No pude consultar el precio del deseado %s", app_id)
            games[app_id] = None

    for user_id, user_games in wishlists.items():
        for app_id, entry in user_games.items():
            data = games.get(app_id)
            if not data:
                continue
            action = offer_action(entry.get("notified_final"), data)
            if action is None:
                continue
            kind, final = action
            if kind == "notify" and not await notify_wish(user_id, entry.get("guild_id"), data, rates):
                continue
            storage.set_wish_notified(user_id, app_id, final)
            if kind == "notify":
                logging.info("Aviso de deseado: %s a %s", data["name"], user_id)


@post_daily_deals.before_loop
@check_sale_announcements.before_loop
@check_wishlists.before_loop
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
    app_commands.Choice(name="🔔 Avisos de deseados en oferta", value="deseados"),
]
FEATURE_LABELS = {"ofertas": "🔥 Ofertas destacadas", "rebajas": "📅 Avisos de rebajas",
                  "deseados": "🔔 Avisos de deseados"}

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
    detail = {
        "ofertas": f"Las voy a publicar todos los días a las {config.DEALS_HOUR}:00.",
        "rebajas": "Voy a avisar antes de cada rebaja, cuando empieza y en sus últimas 24 horas.",
        "deseados": "Cuando un juego de la lista de alguien entre en oferta, lo menciono ahí.",
    }[que.value]
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


# ── /deseado ──────────────────────────────────────────────────────────────────

wish_group = app_commands.Group(name="deseado", description="Tu lista de deseados: Vapora te avisa cuando entran en oferta")


@wish_group.command(name="agregar", description="Agregar un juego a tus deseados")
@app_commands.describe(juego="Nombre del juego (elegilo de la lista) o link de Steam")
async def wish_add(interaction: discord.Interaction, juego: str) -> None:
    await interaction.response.defer(ephemeral=True)
    resolved = await resolve_game(juego)
    data = await get_item_details("app", resolved[0], country="ar") if resolved else None
    if not data:
        await interaction.followup.send("🤔 No encontré ese juego en Steam. Probá con el link de la tienda.",
                                        ephemeral=True)
        return
    await add_to_wishlist(interaction, data, show_card=True)


async def add_to_wishlist(interaction: discord.Interaction, data: dict, show_card: bool) -> None:
    """Suma el juego a los deseados de quien usó el comando o tocó el botón, y le responde en privado."""
    app_id = data["id"]
    on_sale = offer_action(None, data)  # si ya está en oferta, se avisa ahora y no se repite después
    notified = on_sale[1] if on_sale else None
    if not storage.add_wish(interaction.user.id, app_id, data["name"], interaction.guild_id, notified):
        if app_id in storage.get_wishlist(interaction.user.id):
            message = f"Ya tenías **{data['name']}** en tus deseados 😉"
        else:
            message = (f"Tu lista está llena ({storage.MAX_WISHLIST} juegos). "
                       "Sacá alguno con `/deseado quitar`.")
        await interaction.followup.send(message, ephemeral=True)
        return

    if on_sale:
        message = f"✅ Agregué **{data['name']}** a tus deseados. ¡Y ya está en oferta! 🔥"
        embed = None
        if show_card:
            rates = await get_rates(await get_session())
            embed = build_embed({**data, "argentine": await is_argentine(app_id)}, rates)
        await interaction.followup.send(message, embed=embed or discord.utils.MISSING, ephemeral=True)
    else:
        await interaction.followup.send(
            f"✅ Agregué **{data['name']}** a tus deseados. {where_wish_notice(interaction.guild_id)}",
            ephemeral=True)


class WishButton(discord.ui.DynamicItem[discord.ui.Button], template=r"vapora:wish:(?P<app_id>\d+)"):
    """Botón "Avisame si baja" de las tarjetas. Sigue funcionando después de reiniciar el bot."""

    def __init__(self, app_id: int, label: str = "🔔 Avisame si baja") -> None:
        super().__init__(discord.ui.Button(label=label, style=discord.ButtonStyle.secondary,
                                           custom_id=f"vapora:wish:{app_id}"))
        self.app_id = app_id

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button,
                             match: "re.Match[str]") -> "WishButton":
        return cls(int(match["app_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        data = await get_item_details("app", self.app_id, country="ar")
        if not data:
            await interaction.followup.send("😕 No pude consultar ese juego en Steam. Probá de nuevo en un rato.",
                                            ephemeral=True)
            return
        await add_to_wishlist(interaction, data, show_card=False)


MAX_BUTTON_ROWS = 5  # límite de Discord


def is_wishable(game: dict) -> bool:
    """Se puede seguir como deseado: juegos y DLC con precio (no gratis ni paquetes/bundles)."""
    return game["kind"] == "app" and game.get("final_cents") is not None


def build_card_buttons(games: list[dict]) -> discord.ui.View | None:
    """Botones de cada tarjeta: "Avisame si baja" (si se puede seguir) y "Abrir en el navegador".

    Con un solo juego los botones tienen texto genérico; con varios, cada juego va en su
    propia fila y el botón de aviso lleva el nombre para saber cuál es cuál.
    """
    if not games:
        return None
    view = discord.ui.View(timeout=None)
    single = len(games) == 1
    for index, game in enumerate(games):
        row = index if len(games) <= MAX_BUTTON_ROWS else None
        if is_wishable(game):
            label = "🔔 Avisame si baja" if single else f"🔔 {game['name']}"[:80]
            item = WishButton(game["id"], label)
            item.item.row = row
            view.add_item(item)
        link_label = "🌐 Abrir en el navegador" if single else ("🌐 Abrir" if is_wishable(game)
                                                               else f"🌐 {game['name']}"[:80])
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=link_label,
                                        url=store_url(game["kind"], game["id"]), row=row))
    return view


def where_wish_notice(guild_id: int | None) -> str:
    channel_id = wish_channel_id(guild_id)
    if channel_id:
        return f"Te aviso en <#{channel_id}> cuando entre en oferta 🔔"
    return "Te aviso por MD cuando entre en oferta 🔔"


@wish_add.autocomplete("juego")
async def wish_add_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if len(current.strip()) < 2 or "steampowered.com" in current:
        return []
    try:
        results = await search_store(current)
    except Exception:
        return []
    return [app_commands.Choice(name=r["name"][:100], value=str(r["id"])) for r in results]


@wish_group.command(name="quitar", description="Quitar un juego de tus deseados")
@app_commands.describe(juego="Juego a quitar")
async def wish_remove(interaction: discord.Interaction, juego: str) -> None:
    name = storage.remove_wish(interaction.user.id, int(juego)) if juego.isdigit() else None
    message = f"🗑️ Saqué **{name}** de tus deseados." if name else "Ese juego no está en tus deseados."
    await interaction.response.send_message(message, ephemeral=True)


@wish_remove.autocomplete("juego")
async def wish_remove_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    games = storage.get_wishlist(interaction.user.id)
    return [app_commands.Choice(name=entry["name"][:100], value=str(app_id))
            for app_id, entry in games.items() if current.lower() in entry["name"].lower()][:25]


@wish_group.command(name="lista", description="Ver tu lista de deseados")
async def wish_list(interaction: discord.Interaction) -> None:
    games = storage.get_wishlist(interaction.user.id)
    if not games:
        await interaction.response.send_message(
            "Tu lista está vacía. Agregá juegos con `/deseado agregar` 📝", ephemeral=True)
        return
    lines = [f"• [{entry['name']}]({store_url('app', app_id)})" + (" 🔥" if entry.get("notified_final") else "")
             for app_id, entry in games.items()]
    embed = discord.Embed(title=f"📝 Tus deseados ({len(games)}/{storage.MAX_WISHLIST})",
                          description="\n".join(lines), color=EMBED_COLOR)
    embed.set_footer(text="🔥 = en oferta ahora · Reviso los precios cada hora")
    await interaction.response.send_message(embed=embed, ephemeral=True)


bot.tree.add_command(wish_group)


# ── /ayuda ────────────────────────────────────────────────────────────────────

def build_help_embed(is_admin: bool) -> discord.Embed:
    embed = discord.Embed(
        title="💨 ¡Hola, soy Vapora!",
        description="Te digo cuánto salen los juegos de Steam en pesos argentinos 🇦🇷",
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="🔗 Pegá un link de Steam",
        value="Mandá un link de la tienda en cualquier canal y respondo con el precio en USD, "
              "💳 Mercado Pago y 🟣 ARQ, reseñas y más. Funciona con juegos, DLC, paquetes y bundles. "
              "Si el juego es argentino, lo marco con 🧉",
        inline=False,
    )
    embed.add_field(
        name="🎮 Comandos",
        value="`/ofertas` · ofertas destacadas de Steam en pesos\n"
              "`/rebajas` · la rebaja actual y las próximas\n"
              "`/deseado agregar` · sumá un juego a tu lista (o tocá 🔔 en una tarjeta) y te aviso cuando entre en oferta\n"
              "`/deseado lista` · `/deseado quitar` · ver o sacar juegos de tu lista\n"
              "`/ayuda` · este mensaje",
        inline=False,
    )
    if is_admin:
        embed.add_field(
            name="⚙️ Administración",
            value="`/config canal` · elegir dónde publico ofertas diarias, avisos de rebajas y de deseados\n"
                  "`/config ver` · ver la configuración del servidor\n"
                  "`/config desactivar` · dejar de publicar algo",
            inline=False,
        )
    embed.add_field(
        name="💰 ¿Cómo calculo los precios?",
        value=f"💳 **Mercado Pago**: USD × dólar oficial + IVA {config.IVA_PERCENT:g}%\n"
              "🟣 **ARQ**: USD × dólar cripto, sin impuestos\n"
              "Las cotizaciones se actualizan cada 30 minutos.",
        inline=False,
    )
    embed.set_footer(text="Datos de Steam y DolarAPI")
    return embed


@bot.tree.command(name="ayuda", description="Qué hace Vapora y cómo usarla")
async def ayuda(interaction: discord.Interaction) -> None:
    perms = getattr(interaction.user, "guild_permissions", None)
    is_admin = bool(perms and perms.manage_guild)
    await interaction.response.send_message(embed=build_help_embed(is_admin), ephemeral=True)


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
        logging.info("Comandos /ofertas, /rebajas, /config, /deseado y /ayuda listos en %d servidor(es)", len(bot.guilds))


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
        games = []
        rates = await get_rates(await get_session())
        for kind, item_id in items:
            try:
                data = await get_item_details(kind, item_id, country="ar")
                if data:
                    argentine = kind == "app" and await is_argentine(item_id)
                    embeds.append(build_embed({**data, "argentine": argentine}, rates))
                    games.append(data)
            except Exception:
                logging.exception("Error procesando %s %s", kind, item_id)

        if embeds:
            view = build_card_buttons(games)
            await message.reply(embeds=embeds, view=view or discord.utils.MISSING, mention_author=False)
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
