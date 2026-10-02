"""Dobles de Discord y de los servicios del bot, para probar los cogs sin conectarse."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord

from vapora.config import Settings
from vapora.pricing import ExchangeRates, PesoConverter
from vapora.sales import AUTUMN_COLOR, SteamSale
from vapora.steam import Deal, ItemRef, SearchResult, SteamError, StoreItem
from vapora.storage import Database

AUTUMN_SALE = SteamSale("Rebajas de Otoño", date(2026, 10, 1), date(2026, 10, 8), "🍂", AUTUMN_COLOR)


class FakeSteam:
    """Tienda de Steam en memoria. `down = True` simula que Steam no responde."""

    def __init__(self, *items: StoreItem) -> None:
        self.items = {item.ref: item for item in items}
        self.deals: list[Deal] = []
        self.argentine_ids: frozenset[int] = frozenset()
        self.down = False

    async def get_item(self, ref: ItemRef) -> StoreItem | None:
        self._check()
        return self.items.get(ref)

    async def search(self, term: str, *, limit: int = 10) -> list[SearchResult]:
        self._check()
        matches = [item for item in self.items.values() if term.lower() in item.name.lower()]
        return [SearchResult(item.ref.id, item.name) for item in matches][:limit]

    async def featured_deals(self) -> list[Deal]:
        self._check()
        return self.deals

    async def argentine_app_ids(self) -> frozenset[int]:
        return self.argentine_ids

    def _check(self) -> None:
        if self.down:
            raise SteamError("Steam caído (simulado)")


class FakeCalendar:
    def __init__(self, sales: Sequence[SteamSale] = (AUTUMN_SALE,)) -> None:
        self._sales = sales

    async def sales(self) -> Sequence[SteamSale]:
        return self._sales


class FakeBot:
    """Lo que los cogs usan de `VaporaBot`, con servicios falsos y una base de datos real."""

    def __init__(self, db: Database, steam: FakeSteam | None = None) -> None:
        self.db = db
        self.steam = steam or FakeSteam()
        self.calendar = FakeCalendar()
        self.settings = Settings(discord_token="test")
        self.rates = ExchangeRates(official=1550.0, crypto=1623.44)
        self.channels: dict[int, MagicMock] = {}
        self.users: dict[int, MagicMock] = {}
        self.dispatch = MagicMock()
        self.sale: SteamSale | None = None  # rebaja en curso

    async def peso_converter(self) -> PesoConverter:
        return PesoConverter(self.rates, self.settings.taxes)

    async def current_sale(self) -> SteamSale | None:
        return self.sale

    def find_channel(self, channel_id: int | None) -> MagicMock | None:
        return self.channels.get(channel_id) if channel_id else None

    def add_channel(self, channel_id: int) -> MagicMock:
        """Registra un canal donde el bot puede publicar; devuelve el canal para inspeccionarlo."""
        channel = MagicMock(name=f"channel-{channel_id}")
        channel.send = AsyncMock()
        self.channels[channel_id] = channel
        return channel

    def add_user(self, user_id: int, *, dms_open: bool = True) -> MagicMock:
        user = MagicMock(name=f"user-{user_id}")
        user.send = AsyncMock()
        if not dms_open:
            user.send.side_effect = discord.Forbidden(MagicMock(status=403), "MD cerrados")
        self.users[user_id] = user
        return user

    def get_user(self, user_id: int) -> MagicMock | None:
        return self.users.get(user_id)

    async def fetch_user(self, user_id: int) -> MagicMock:
        raise discord.NotFound(MagicMock(status=404), "usuario inexistente")

    async def wait_until_ready(self) -> None:
        return None


def make_interaction(user_id: int = 5, guild_id: int | None = 10, *, manage_guild: bool = False) -> MagicMock:
    """Interacción de un comando o botón, con las respuestas espiables."""
    interaction = MagicMock(name="interaction")
    interaction.user = SimpleNamespace(
        id=user_id, guild_permissions=SimpleNamespace(manage_guild=manage_guild)
    )
    interaction.guild_id = guild_id
    interaction.guild = SimpleNamespace(id=guild_id, me=MagicMock(name="vapora")) if guild_id else None
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def make_message(content: str, *, from_bot: bool = False) -> MagicMock:
    message = MagicMock(name="message")
    message.content = content
    message.author.bot = from_bot
    message.reply = AsyncMock()
    message.edit = AsyncMock()
    return message


def sent_text(send: AsyncMock) -> str:
    """Texto del último mensaje enviado con ese `send`."""
    call = send.await_args
    assert call is not None, "no se envió ningún mensaje"
    return call.args[0] if call.args else call.kwargs.get("content", "")


def sent_kwargs(send: AsyncMock) -> dict[str, Any]:
    call = send.await_args
    assert call is not None, "no se envió ningún mensaje"
    return dict(call.kwargs)
