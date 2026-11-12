"""Tarjeta de un mod del Workshop de Steam (de cualquier juego salvo Wallpaper Engine)."""

from __future__ import annotations

import io
from collections.abc import Sequence

import discord

from vapora.sales import discord_timestamp
from vapora.steam.workshop import WorkshopMod
from vapora.ui.formatting import format_thousands
from vapora.ui.style import MOD_COLOR

MAX_TAGS = 6
MAX_LABEL_LENGTH = 80  # límite de Discord
MAX_BUTTON_ROWS = 5  # límite de Discord
FOOTER = "Workshop de Steam"


def build_mod_message(
    mod: WorkshopMod, enlarged_preview: bytes | None, game_name: str | None = None
) -> tuple[discord.Embed, list[discord.File]]:
    """Tarjeta y adjuntos para mandar un mod (igual que `build_wallpaper_message`).

    Con `enlarged_preview`, la vista previa agrandada va adjunta y la tarjeta la muestra.
    """
    if enlarged_preview is None:
        return build_mod_card(mod, game_name), []
    filename = f"mod-{mod.id}.gif"
    embed = build_mod_card(mod, game_name, image_url=f"attachment://{filename}")
    return embed, [discord.File(io.BytesIO(enlarged_preview), filename=filename)]


def build_mod_card(
    mod: WorkshopMod, game_name: str | None = None, *, image_url: str | None = None
) -> discord.Embed:
    """Tarjeta con la imagen del mod en grande, el juego, sus etiquetas y sus números.

    `image_url` reemplaza a la vista previa de Steam (por ejemplo, por una adjunta).
    """
    embed = discord.Embed(
        title=f"🧩 {mod.title}",
        url=mod.url,
        description=_description(mod, game_name),
        color=MOD_COLOR,
    )
    embed.add_field(name="👥 Suscriptores", value=format_thousands(mod.subscriptions), inline=True)
    embed.add_field(name="❤️ Favoritos", value=format_thousands(mod.favorites), inline=True)
    if mod.updated_at:
        embed.add_field(name="🔄 Actualizado", value=discord_timestamp(mod.updated_at, "D"), inline=True)
    if mod.file_size:
        embed.add_field(name="📦 Tamaño", value=format_size(mod.file_size), inline=True)
    image = image_url or mod.preview_url
    if image:
        embed.set_image(url=image)
    embed.set_footer(text=FOOTER)
    return embed


def _description(mod: WorkshopMod, game_name: str | None) -> str | None:
    parts = []
    if game_name:
        parts.append(f"🎮 Mod de **{game_name}**")
    if mod.tags:
        parts.append("🏷️ " + " · ".join(mod.tags[:MAX_TAGS]))
    return "\n".join(parts) or None


def format_size(size_bytes: int) -> str:
    """1536 -> '1,5 KB'; 734003200 -> '700 MB' (con coma decimal, al estilo argentino)."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return _number(size) + f" {unit}"
        size /= 1024
    return _number(size) + " GB"


def _number(value: float) -> str:
    text = f"{value:.0f}" if value >= 100 or value == int(value) else f"{value:.1f}"
    return text.replace(".", ",")


def add_mod_buttons(view: discord.ui.View, mods: Sequence[WorkshopMod], *, first_row: int) -> None:
    """Agrega un botón "Ver en Steam" por mod, cada uno en su fila mientras entren.

    `first_row` es la primera fila libre (las anteriores pueden tener botones de juegos o
    de fondos). Si no entran en las 5 filas de Discord, se deja que Discord las acomode.
    """
    single = len(mods) == 1
    fits = first_row + len(mods) <= MAX_BUTTON_ROWS
    for offset, mod in enumerate(mods):
        label = "🧩 Ver en Steam" if single else f"🧩 {mod.title}"[:MAX_LABEL_LENGTH]
        row = first_row + offset if fits else None
        view.add_item(discord.ui.Button(style=discord.ButtonStyle.link, label=label, url=mod.url, row=row))
