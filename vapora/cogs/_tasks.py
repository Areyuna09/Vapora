"""Utilidades para las tareas periódicas de los cogs y sus publicaciones diarias."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Coroutine
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any, TypeVar

import discord

from vapora.sales import ARGENTINA
from vapora.storage import Feature

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

log = logging.getLogger(__name__)

CogT = TypeVar("CogT")
Task = Callable[[CogT], Coroutine[Any, Any, None]]


def survives_errors(task: Task[CogT]) -> Task[CogT]:
    """Hace que un error inesperado no apague la tarea para siempre.

    `discord.ext.tasks` detiene un loop cuando su cuerpo lanza una excepción. Para un bot que
    corre sin supervisión eso significa dejar de publicar hasta el próximo reinicio, así que
    acá se registra el error y se sigue: la tarea vuelve a intentarlo en su próxima vuelta.
    """

    @functools.wraps(task)
    async def wrapper(cog: CogT) -> None:
        try:
            await task(cog)
        except Exception:
            log.exception("Falló la tarea %s; se reintenta en la próxima vuelta", task.__name__)

    return wrapper


# ── Publicaciones diarias ─────────────────────────────────────────────────────

# Si el bot arranca hasta estas horas después de la hora de una publicación diaria y todavía
# no se hizo ese día (por un reinicio o un deploy), se hace apenas se conecta.
CATCH_UP_HOURS = 6


def argentina_today(now: datetime) -> date:
    return now.astimezone(ARGENTINA).date()


def missed_daily_post(now: datetime, hour: int) -> bool:
    """Si `now` cae poco después de la hora de la publicación diaria (ver `CATCH_UP_HOURS`)."""
    local = now.astimezone(ARGENTINA)
    scheduled = datetime.combine(local.date(), time(hour), ARGENTINA)
    return scheduled <= local < scheduled + timedelta(hours=CATCH_UP_HOURS)


async def pending_daily_targets(
    bot: VaporaBot, feature: Feature, day: date
) -> list[tuple[int, discord.abc.Messageable]]:
    """Servidores con canal para esa publicación diaria que todavía no la recibieron ese día.

    Devuelve pares (servidor, canal). Los canales que el bot ya no ve se saltean.
    """
    configured = await bot.db.channels_for(feature)
    already_posted = await bot.db.guilds_posted_on(feature, day)
    return [
        (guild_id, channel)
        for guild_id, channel_id in configured.items()
        if guild_id not in already_posted and (channel := bot.find_channel(channel_id))
    ]
