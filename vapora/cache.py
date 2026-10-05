"""Cachés en memoria con vencimiento, para no repetir consultas a servicios externos."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Hashable
from typing import Generic, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")
T = TypeVar("T")

Clock = Callable[[], float]


class TTLCache(Generic[K, V]):
    """Guarda un resultado por clave durante `ttl_seconds`.

    También guarda resultados vacíos (`None`), para no volver a consultar algo que no existe.
    Si llegan varios pedidos de la misma clave a la vez, se consulta una sola vez y todos
    reciben ese resultado (o ese error).
    """

    def __init__(self, ttl_seconds: float, *, max_entries: int = 2000, clock: Clock = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[K, tuple[float, V]] = {}
        self._pending: dict[K, asyncio.Task[V]] = {}

    async def get_or_fetch(self, key: K, fetch: Callable[[], Awaitable[V]]) -> V:
        """Devuelve el valor guardado; si no hay o venció, lo pide con `fetch` y lo guarda."""
        entry = self._entries.get(key)
        if entry is not None and self._clock() - entry[0] < self._ttl:
            return entry[1]
        task = self._pending.get(key)
        if task is None:
            task = asyncio.ensure_future(self._fetch_and_store(key, fetch))
            self._pending[key] = task
            task.add_done_callback(lambda done: self._forget_pending(key, done))
        # shield: si cancelan a uno de los que esperan, el pedido sigue para los demás.
        return await asyncio.shield(task)

    def put(self, key: K, value: V) -> None:
        """Guarda un valor que se consiguió por otro lado (por ejemplo, en un pedido de varios)."""
        self._store(key, value)

    async def _fetch_and_store(self, key: K, fetch: Callable[[], Awaitable[V]]) -> V:
        value = await fetch()
        self._store(key, value)
        return value

    def _forget_pending(self, key: K, task: asyncio.Task[V]) -> None:
        self._pending.pop(key, None)
        if not task.cancelled():
            task.exception()  # marca el error como visto: ya lo recibieron quienes esperaban

    def _store(self, key: K, value: V) -> None:
        self._entries.pop(key, None)  # reinsertar lo deja al final: el dict queda ordenado por antigüedad
        self._entries[key] = (self._clock(), value)
        while len(self._entries) > self._max_entries:
            del self._entries[next(iter(self._entries))]


class RefreshingValue(Generic[T]):
    """Un valor que se renueva cada `ttl_seconds`.

    Si la renovación falla (devuelve `None`), se conserva el último valor conocido y se
    reintenta pasado `retry_seconds`, sin esperar el TTL completo. Si varios lo piden a la
    vez cuando toca renovarlo, se renueva una sola vez.
    """

    def __init__(
        self, ttl_seconds: float, initial: T, *, retry_seconds: float = 60, clock: Clock = time.monotonic
    ) -> None:
        self._ttl = ttl_seconds
        self._retry = retry_seconds
        self._clock = clock
        self._value = initial
        self._next_refresh: float | None = None  # None: todavía no se pidió nunca
        self._lock = asyncio.Lock()

    async def get(self, refresh: Callable[[], Awaitable[T | None]]) -> T:
        if not self._due():
            return self._value
        async with self._lock:
            if self._due():  # otro pudo renovarlo mientras se esperaba el lock
                fresh = await refresh()
                now = self._clock()
                if fresh is None:
                    self._next_refresh = now + self._retry
                else:
                    self._value = fresh
                    self._next_refresh = now + self._ttl
        return self._value

    def _due(self) -> bool:
        return self._next_refresh is None or self._clock() >= self._next_refresh
