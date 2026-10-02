"""Botones que acompañan a las tarjetas de juegos."""

from __future__ import annotations

import re
from collections.abc import Sequence

import discord

from vapora import events
from vapora.steam import StoreItem

MAX_BUTTON_ROWS = 5  # límite de Discord
MAX_LABEL_LENGTH = 80  # límite de Discord


class WishButton(
    discord.ui.DynamicItem[discord.ui.Button[discord.ui.View]], template=r"vapora:wish:(?P<app_id>\d+)"
):
    """Botón "Avisame si baja".

    El AppID viaja en el `custom_id`, así el botón sigue funcionando en tarjetas viejas
    aunque el bot se haya reiniciado.
    """

    def __init__(self, app_id: int, label: str = "🔔 Avisame si baja", row: int | None = None) -> None:
        super().__init__(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id=f"vapora:wish:{app_id}",
                row=row,
            )
        )
        self.app_id = app_id

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: discord.ui.Item[discord.ui.View], match: re.Match[str]
    ) -> WishButton:
        return cls(int(match["app_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        interaction.client.dispatch(events.WISH_BUTTON, interaction, self.app_id)


def build_card_buttons(items: Sequence[StoreItem]) -> discord.ui.View:
    """Botones de las tarjetas: "Avisame si baja" (si se puede seguir) y "Abrir en el navegador".

    Con un solo juego los botones tienen texto genérico; con varios, cada juego va en su
    propia fila y los botones llevan el nombre para saber cuál es cuál.
    """
    view = discord.ui.View(timeout=None)
    single = len(items) == 1
    for index, item in enumerate(items):
        row = index if len(items) <= MAX_BUTTON_ROWS else None
        if item.is_wishable:
            label = "🔔 Avisame si baja" if single else _clip(f"🔔 {item.name}")
            view.add_item(WishButton(item.ref.id, label, row))
        if single:
            link_label = "🌐 Abrir en el navegador"
        else:
            link_label = "🌐 Abrir" if item.is_wishable else _clip(f"🌐 {item.name}")
        view.add_item(
            discord.ui.Button(style=discord.ButtonStyle.link, label=link_label, url=item.ref.url, row=row)
        )
    return view


def _clip(label: str) -> str:
    return label[:MAX_LABEL_LENGTH]
