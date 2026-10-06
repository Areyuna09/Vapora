import logging
from types import SimpleNamespace
from typing import ClassVar

import discord
import pytest
from discord import app_commands

from vapora import __main__ as main_module
from vapora.config import Settings
from vapora.discord_errors import BAN_SUMMARY, CompactCloudflareBans, is_cloudflare_ban

CLOUDFLARE_PAGE = "<!doctype html><title>Access denied | discord.com used Cloudflare</title><span>1015</span>"


def http_error(status: int, body: str | dict) -> discord.HTTPException:
    return discord.HTTPException(SimpleNamespace(status=status, reason="x"), body)  # type: ignore[arg-type]


BAN = http_error(429, CLOUDFLARE_PAGE)


# ── Detección ─────────────────────────────────────────────────────────────────


def test_cloudflare_page_is_a_ban():
    assert is_cloudflare_ban(BAN)


@pytest.mark.parametrize(
    "error",
    [
        http_error(429, {"message": "You are being rate limited.", "retry_after": 1.5}),  # límite normal
        http_error(500, CLOUDFLARE_PAGE),
        RuntimeError("otra cosa"),
        None,
    ],
)
def test_other_errors_are_not_a_ban(error: BaseException | None):
    assert not is_cloudflare_ban(error)


def test_ban_inside_a_command_error_is_detected():
    wrapped = app_commands.CommandInvokeError(SimpleNamespace(name="fondo"), BAN)  # type: ignore[arg-type]
    assert is_cloudflare_ban(wrapped)


def test_ban_that_caused_another_error_is_detected():
    try:
        try:
            raise BAN
        except discord.HTTPException as error:
            raise RuntimeError("al avisar del error") from error
    except RuntimeError as error:
        assert is_cloudflare_ban(error)


# ── Logs en una línea ─────────────────────────────────────────────────────────


def _record(error: BaseException) -> logging.LogRecord:
    return logging.LogRecord(
        "vapora", logging.ERROR, __file__, 1, "Error en /%s", ("fondo",), (type(error), error, None)
    )


def test_ban_is_logged_in_one_line():
    record = _record(BAN)
    assert CompactCloudflareBans().filter(record)
    assert record.getMessage() == f"Error en /fondo · {BAN_SUMMARY}"
    assert record.exc_info is None  # sin traceback ni página HTML
    assert "\n" not in logging.Formatter().format(record)


def test_other_errors_keep_their_traceback():
    error = RuntimeError("bug")
    record = _record(error)
    CompactCloudflareBans().filter(record)
    assert record.exc_info is not None and record.exc_info[1] is error
    assert record.getMessage() == "Error en /fondo"


# ── Arranque ──────────────────────────────────────────────────────────────────


class FakeBot:
    """Reemplazo de VaporaBot: cada `run` devuelve o lanza lo siguiente de la lista."""

    outcomes: ClassVar[list[BaseException | None]] = []
    runs: ClassVar[int] = 0

    def __init__(self, settings: Settings) -> None:
        pass

    def run(self, token: str, **_: object) -> None:
        FakeBot.runs += 1
        outcome = FakeBot.outcomes.pop(0)
        if outcome is not None:
            raise outcome


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waited: list[float] = []
    monkeypatch.setattr(main_module, "VaporaBot", FakeBot)
    monkeypatch.setattr(main_module.time, "sleep", waited.append)
    FakeBot.runs = 0
    return waited


def test_ban_at_login_waits_and_retries_instead_of_crashing(sleeps: list[float]):
    FakeBot.outcomes = [BAN, BAN, BAN, BAN, None]
    main_module.run_until_stopped(Settings(discord_token="test"))
    assert FakeBot.runs == 5
    assert sleeps == [15 * 60, 30 * 60, 60 * 60, 60 * 60]  # crece y se queda en una hora


def test_other_startup_errors_still_stop_the_bot(sleeps: list[float]):
    FakeBot.outcomes = [discord.LoginFailure("token inválido")]
    with pytest.raises(discord.LoginFailure):
        main_module.run_until_stopped(Settings(discord_token="test"))
    assert sleeps == []


def test_normal_shutdown_does_not_retry(sleeps: list[float]):
    FakeBot.outcomes = [None]
    main_module.run_until_stopped(Settings(discord_token="test"))
    assert FakeBot.runs == 1


def test_logged_bans_are_recorded_for_the_monitor(monkeypatch: pytest.MonkeyPatch):
    from vapora import discord_errors

    tracker = discord_errors.BanTracker()
    monkeypatch.setattr(discord_errors, "ban_tracker", tracker)
    CompactCloudflareBans().filter(_record(RuntimeError("otra cosa")))
    assert not tracker.seen_within(60)
    CompactCloudflareBans().filter(_record(BAN))
    assert tracker.seen_within(60)
