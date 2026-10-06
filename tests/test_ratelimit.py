from vapora.ratelimit import RateLimits, UserRateLimit, slow_down_text


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_rate_then_asks_to_wait():
    clock = Clock()
    limit = UserRateLimit(3, 10, clock=clock)
    assert [limit.retry_after(1) for _ in range(3)] == [0, 0, 0]
    assert limit.retry_after(1) == 10  # el cuarto, en la misma ventana


def test_window_resets_after_the_period():
    clock = Clock()
    limit = UserRateLimit(1, 10, clock=clock)
    limit.retry_after(1)
    clock.now += 10.1
    assert limit.retry_after(1) == 0


def test_each_user_has_their_own_limit():
    limit = UserRateLimit(1, 10, clock=Clock())
    assert limit.retry_after(1) == 0
    assert limit.retry_after(2) == 0
    assert limit.retry_after(1) > 0


def test_warns_only_once_per_window():
    clock = Clock()
    limit = UserRateLimit(1, 10, clock=clock)
    limit.retry_after(1)
    wait = limit.retry_after(1)
    assert limit.should_warn(1, wait)
    assert not limit.should_warn(1, wait)  # spamear no genera un aviso por intento
    clock.now += wait
    assert limit.should_warn(1, 10)


def test_idle_users_are_forgotten(monkeypatch):
    from vapora import ratelimit

    monkeypatch.setattr(ratelimit, "_CLEANUP_THRESHOLD", 2)
    clock = Clock()
    limit = UserRateLimit(1, 10, clock=clock)
    for user in range(3):
        limit.retry_after(user)
    clock.now += 11
    limit.retry_after(99)
    assert set(limit._buckets) == {99}


def test_default_limits_leave_room_for_normal_use():
    limits = RateLimits()
    assert all(limits.commands.retry_after(1) == 0 for _ in range(8))
    assert all(limits.autocomplete.retry_after(1) == 0 for _ in range(25))
    assert all(limits.links.retry_after(1) == 0 for _ in range(5))


def test_slow_down_text_rounds_up():
    assert slow_down_text(2.1) == "⏳ Más despacio: probá de nuevo en 3 s."
