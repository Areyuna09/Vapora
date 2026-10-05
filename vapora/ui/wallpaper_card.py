"""Tarjeta de un fondo de Wallpaper Engine y sus botones."""

from __future__ import annotations

import io
from collections.abc import Sequence

import discord

from vapora.steam.workshop import WALLPAPER_ENGINE_STORE_URL, Wallpaper
from vapora.ui.formatting import format_thousands
from vapora.ui.style import WALLPAPER_COLOR

MAX_GENRES = 4
MAX_LABEL_LENGTH = 80  # límite de Discord
MAX_BUTTON_ROWS = 5  # límite de Discord
FOOTER = "Wallpaper Engine · Workshop de Steam · Se usa con la app de Wallpaper Engine"


def build_wallpaper_message(
    wallpaper: Wallpaper, enlarged_preview: bytes | None, *, title_prefix: str = "🖼️"
) -> tuple[discord.Embed, list[discord.File]]:
    """Tarjeta y adjuntos para mandar un fondo.

    Con `enlarged_preview` (ver `vapora.previews`), la vista previa agrandada va adjunta y
    la tarjeta la muestra; sin ella, la tarjeta usa la vista previa original de Steam.
    Cada llamada arma archivos nuevos: un `discord.File` se puede mandar una sola vez.
    """
    if enlarged_preview is None:
        return build_wallpaper_card(wallpaper, title_prefix=title_prefix), []
    filename = f"fondo-{wallpaper.id}.gif"
    embed = build_wallpaper_card(wallpaper, title_prefix=title_prefix, image_url=f"attachment://{filename}")
    return embed, [discord.File(io.BytesIO(enlarged_preview), filename=filename)]


def build_wallpaper_card(
    wallpaper: Wallpaper, *, title_prefix: str = "🖼️", image_url: str | None = None
) -> discord.Embed:
    """Tarjeta con la vista previa en grande (si es un GIF, Discord la muestra animada).

    `image_url` reemplaza a la vista previa de Steam (por ejemplo, por una adjunta).
    """
    embed = discord.Embed(
        title=f"{title_prefix} {wallpaper.title}",
        url=wallpaper.url,
        description=_description(wallpaper),
        color=WALLPAPER_COLOR,
    )
    embed.add_field(name="👥 Suscriptores", value=format_thousands(wallpaper.subscriptions), inline=True)
    embed.add_field(name="❤️ Favoritos", value=format_thousands(wallpaper.favorites), inline=True)
    details = " · ".join(part for part in (wallpaper.kind, wallpaper.resolution) if part)
    if details:
        embed.add_field(name="🖥️ Tipo", value=details, inline=True)
    image = image_url or wallpaper.preview_url
    if image:
        embed.set_image(url=image)
    embed.set_footer(text=FOOTER)
    return embed


def _description(wallpaper: Wallpaper) -> str | None:
    parts = []
    if wallpaper.genres:
        parts.append("🎨 " + " · ".join(wallpaper.genres[:MAX_GENRES]))
    if wallpaper.features:
        parts.append(" · ".join(wallpaper.features))
    return "\n".join(parts) or None


def add_wallpaper_buttons(view: discord.ui.View, wallpapers: Sequence[Wallpaper], *, first_row: int) -> None:
    """Agrega a `view` un botón "Ver en Steam" por fondo y uno a la tienda de Wallpaper Engine.

    `first_row` es la primera fila libre (las anteriores pueden tener botones de juegos).
    Si no entran en las 5 filas de Discord, se deja que Discord las acomode.
    """
    if not wallpapers:
        return
    single = len(wallpapers) == 1
    # Con un fondo, sus dos botones van en una fila; con varios, uno por fila y la tienda al final.
    rows_needed = 1 if single else len(wallpapers) + 1
    fits = first_row + rows_needed <= MAX_BUTTON_ROWS
    for offset, wallpaper in enumerate(wallpapers):
        label = "🖼️ Ver en Steam" if single else f"🖼️ {wallpaper.title}"[:MAX_LABEL_LENGTH]
        row = first_row + offset if fits else None
        button = discord.ui.Button[discord.ui.View](
            style=discord.ButtonStyle.link, label=label, url=wallpaper.url, row=row
        )
        view.add_item(button)
    store_row = first_row + rows_needed - 1 if fits else None
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.link,
            label="🛒 Conseguir Wallpaper Engine",
            url=WALLPAPER_ENGINE_STORE_URL,
            row=store_row,
        )
    )


def build_wallpaper_buttons(wallpapers: Sequence[Wallpaper]) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    add_wallpaper_buttons(view, wallpapers, first_row=0)
    return view
