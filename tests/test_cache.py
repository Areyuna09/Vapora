import asyncio

import pytest

from vapora.cache import RefreshingValue, TTLCache


class Clock:
    """Reloj que avanza solo cuando el test lo indica."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Source:
    """Fuente de datos que cuenta cuántas veces se la consulta."""

    def __init__(self, *values: object) -> None:
        self._values = list(values)
        self.calls = 0

    async def __call__(self) -> object:
        self.calls += 1
        return self._values.pop(0) if len(self._values) > 1 else self._values[0]


# ── TTLCache ──────────────────────────────────────────────────────────────────


async def test_ttl_cache_fetches_once_while_fresh():
    clock, source = Clock(), Source("dato")
    cache: TTLCache[str, object] = TTLCache(60, clock=clock)
    assert await cache.get_or_fetch("k", source) == "dato"
    clock.now = 59
    assert await cache.get_or_fetch("k", source) == "dato"
    assert source.calls == 1


async def test_ttl_cache_fetches_again_after_expiring():
    clock, source = Clock(), Source("viejo", "nuevo")
    cache: TTLCache[str, object] = TTLCache(60, clock=clock)
    await cache.get_or_fetch("k", source)
    clock.now = 60
    assert await cache.get_or_fetch("k", source) == "nuevo"
    assert source.calls == 2


async def test_ttl_cache_also_remembers_none():
    source = Source(None)
    cache: TTLCache[str, object] = TTLCache(60, clock=Clock())
    assert await cache.get_or_fetch("k", source) is None
    assert await cache.get_or_fetch("k", source) is None
    assert source.calls == 1


async def test_ttl_cache_evicts_oldest_entries():
    source = Source("dato")
    cache: TTLCache[int, object] = TTLCache(60, max_entries=2, clock=Clock())
    for key in (1, 2, 3):
        await cache.get_or_fetch(key, source)
    await cache.get_or_fetch(3, source)  # sigue guardado
    await cache.get_or_fetch(1, source)  # fue desalojado: se vuelve a pedir
    assert source.calls == 4


# ── RefreshingValue ───────────────────────────────────────────────────────────


async def test_refreshing_value_refreshes_only_after_ttl():
    clock, source = Clock(), Source(1, 2)
    value: RefreshingValue[object] = RefreshingValue(100, None, clock=clock)
    assert await value.get(source) == 1
    clock.now = 99
    assert await value.get(source) == 1
    clock.now = 100
    assert await value.get(source) == 2
    assert source.calls == 2


async def test_refreshing_value_keeps_last_value_when_refresh_fails():
    clock, source = Clock(), Source(1, None)
    value: RefreshingValue[object] = RefreshingValue(100, None, clock=clock)
    await value.get(source)
    clock.now = 100
    assert await value.get(source) == 1


async def test_refreshing_value_retries_soon_after_a_failure():
    clock, source = Clock(), Source(None, 7)
    value: RefreshingValue[object] = RefreshingValue(100, "inicial", retry_seconds=10, clock=clock)
    assert await value.get(source) == "inicial"
    clock.now = 9
    assert await value.get(source) == "inicial"  # todavía no reintenta
    clock.now = 10
    assert await value.get(source) == 7
    assert source.calls == 2


# ── Pedidos simultáneos ───────────────────────────────────────────────────────


class SlowSource(Source):
    """Fuente que no responde hasta que el test lo indica, para simular pedidos simultáneos."""

    def __init__(self, *values: object) -> None:
        super().__init__(*values)
        self.release = asyncio.Event()

    async def __call__(self) -> object:
        self.calls += 1
        await self.release.wait()
        return self._values[0]


async def test_ttl_cache_fetches_once_for_simultaneous_requests():
    source = SlowSource("dato")
    cache: TTLCache[str, object] = TTLCache(60, clock=Clock())
    pending = asyncio.gather(*(cache.get_or_fetch("k", source) for _ in range(3)))
    await asyncio.sleep(0)
    source.release.set()
    assert await pending == ["dato", "dato", "dato"]
    assert source.calls == 1


async def test_ttl_cache_shares_the_error_and_retries_later():
    calls = 0

    async def failing() -> object:
        nonlocal calls
        calls += 1
        raise RuntimeError("falló")

    cache: TTLCache[str, object] = TTLCache(60, clock=Clock())
    results = await asyncio.gather(
        cache.get_or_fetch("k", failing), cache.get_or_fetch("k", failing), return_exceptions=True
    )
    assert all(isinstance(result, RuntimeError) for result in results)
    assert calls == 1
    with pytest.raises(RuntimeError):  # el error no se guarda: el próximo pedido reintenta
        await cache.get_or_fetch("k", failing)
    assert calls == 2


async def test_ttl_cache_cancelling_one_waiter_does_not_cancel_the_others():
    source = SlowSource("dato")
    cache: TTLCache[str, object] = TTLCache(60, clock=Clock())
    first = asyncio.ensure_future(cache.get_or_fetch("k", source))
    second = asyncio.ensure_future(cache.get_or_fetch("k", source))
    await asyncio.sleep(0)
    first.cancel()
    source.release.set()
    assert await second == "dato"


async def test_refreshing_value_refreshes_once_for_simultaneous_requests():
    source = SlowSource(5)
    value: RefreshingValue[object] = RefreshingValue(100, None, clock=Clock())
    pending = asyncio.gather(*(value.get(source) for _ in range(3)))
    await asyncio.sleep(0)
    source.release.set()
    assert await pending == [5, 5, 5]
    assert source.calls == 1
