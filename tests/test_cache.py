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
