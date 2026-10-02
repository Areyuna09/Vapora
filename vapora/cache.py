"""Cachés en memoria con vencimiento, para no repetir consultas a servicios externos."""

from __future__ import annotations

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
    """

    def __init__(self, ttl_seconds: float, *, max_entries: int = 2000, clock: Clock = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[K, tuple[float, V]] = {}

    async def get_or_fetch(self, key: K, fetch: Callable[[], Awaitable[V]]) -> V:
        """Devuelve el valor guardado; si no hay o venció, lo pide con `fetch` y lo guarda."""
        entry = self._entries.get(key)
        if entry is not None and self._clock() - entry[0] < self._ttl:
            return entry[1]
        value = await fetch()
        self._store(key, value)
        return value

    def _store(self, key: K, value: V) -> None:
        self._entries.pop(key, None)  # reinsertar lo deja al final: el dict queda ordenado por antigüedad
        self._entries[key] = (self._clock(), value)
        while len(self._entries) > self._max_entries:
            del self._entries[next(iter(self._entries))]


class RefreshingValue(Generic[T]):
    """Un valor que se renueva cada `ttl_seconds`.

    Si la renovación falla (devuelve `None`), se conserva el último valor conocido y se
    reintenta pasado `retry_seconds`, sin esperar el TTL completo.
    """

    def __init__(
        self, ttl_seconds: float, initial: T, *, retry_seconds: float = 60, clock: Clock = time.monotonic
    ) -> None:
        self._ttl = ttl_seconds
        self._retry = retry_seconds
        self._clock = clock
        self._value = initial
        self._next_refresh: float | None = None  # None: todavía no se pidió nunca

    async def get(self, refresh: Callable[[], Awaitable[T | None]]) -> T:
        now = self._clock()
        if self._next_refresh is None or now >= self._next_refresh:
            fresh = await refresh()
            if fresh is None:
                self._next_refresh = now + self._retry
            else:
                self._value = fresh
                self._next_refresh = now + self._ttl
        return self._value
