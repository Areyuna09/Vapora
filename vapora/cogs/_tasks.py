"""Utilidades para las tareas periódicas de los cogs."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

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
