from types import SimpleNamespace

import aiohttp
import pytest
from helpers import FakeSession

from vapora import __main__ as main_module
from vapora.cogs import health as health_module
from vapora.cogs.health import HealthCog
from vapora.config import ConfigError, Settings
from vapora.discord_errors import BanTracker

URL = "https://hc-ping.com/abc-123"


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def tracker(monkeypatch: pytest.MonkeyPatch) -> BanTracker:
    tracker = BanTracker(clock=Clock())
    monkeypatch.setattr(health_module, "ban_tracker", tracker)
    return tracker


def make_bot(
    *, ready: bool = True, url: str | None = URL, session: FakeSession | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        settings=Settings(discord_token="x", healthcheck_url=url),
        session=session or FakeSession({"hc-ping.com": "OK"}),
        is_ready=lambda: ready,
    )


# ── Configuración ─────────────────────────────────────────────────────────────


def test_healthcheck_url_is_optional_and_must_be_https():
    assert Settings.from_env({"DISCORD_TOKEN": "x"}).healthcheck_url is None
    assert Settings.from_env({"DISCORD_TOKEN": "x", "HEALTHCHECK_URL": f" {URL}/ "}).healthcheck_url == URL
    with pytest.raises(ConfigError, match="HEALTHCHECK_URL"):
        Settings.from_env({"DISCORD_TOKEN": "x", "HEALTHCHECK_URL": "http://hc-ping.com/abc"})


def test_healthcheck_url_never_appears_in_logs():
    assert "abc-123" not in repr(Settings(discord_token="x", healthcheck_url=URL))


# ── Latido ────────────────────────────────────────────────────────────────────


async def test_healthy_bot_reports_ok(tracker: BanTracker):
    bot = make_bot()
    await HealthCog(bot).heartbeat()  # type: ignore[arg-type]
    assert [url for url, _ in bot.session.calls] == [URL]


async def test_recent_ban_reports_failure(tracker: BanTracker):
    bot = make_bot()
    tracker.record()
    await HealthCog(bot).heartbeat()  # type: ignore[arg-type]
    assert [url for url, _ in bot.session.calls] == [f"{URL}/fail"]


async def test_old_ban_no_longer_counts(tracker: BanTracker):
    bot = make_bot()
    tracker.record()
    tracker._clock.now += health_module.RECENT_BAN_SECONDS  # type: ignore[attr-defined]
    await HealthCog(bot).heartbeat()  # type: ignore[arg-type]
    assert [url for url, _ in bot.session.calls] == [URL]


async def test_disconnected_bot_reports_failure(tracker: BanTracker):
    bot = make_bot(ready=False)
    await HealthCog(bot).heartbeat()  # type: ignore[arg-type]
    assert [url for url, _ in bot.session.calls] == [f"{URL}/fail"]


async def test_monitor_down_is_only_a_warning(tracker: BanTracker):
    bot = make_bot(session=FakeSession({"hc-ping.com": aiohttp.ClientError()}))
    await HealthCog(bot).heartbeat()  # type: ignore[arg-type]  # no propaga


async def test_without_url_there_is_no_heartbeat(tracker: BanTracker):
    cog = HealthCog(make_bot(url=None))  # type: ignore[arg-type]
    await cog.cog_load()
    assert not cog.heartbeat.is_running()
    await cog.heartbeat()
    assert cog.bot.session.calls == []


# ── Bloqueos ──────────────────────────────────────────────────────────────────


def test_ban_tracker_remembers_the_last_ban():
    clock = Clock()
    tracker = BanTracker(clock=clock)
    assert not tracker.seen_within(60)
    tracker.record()
    assert tracker.seen_within(60)
    clock.now += 61
    assert not tracker.seen_within(60)


def test_failure_is_reported_while_waiting_out_a_ban_at_startup(monkeypatch: pytest.MonkeyPatch):
    opened: list[str] = []

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(url: str, timeout: float) -> Response:
        opened.append(url)
        return Response()

    monkeypatch.setattr(main_module.urllib.request, "urlopen", fake_urlopen)
    main_module.report_failure(URL)
    main_module.report_failure(None)  # sin monitor configurado, no hace nada
    assert opened == [f"{URL}/fail"]


def test_monitor_unreachable_at_startup_is_only_a_warning(monkeypatch: pytest.MonkeyPatch):
    def broken(url: str, timeout: float) -> None:
        raise OSError("sin red")

    monkeypatch.setattr(main_module.urllib.request, "urlopen", broken)
    main_module.report_failure(URL)  # no propaga
