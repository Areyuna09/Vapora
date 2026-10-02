from datetime import UTC, date, datetime, timedelta

import aiohttp
from helpers import FIXTURES, FakeSession

from vapora.sales import (
    FALLBACK_SALES,
    SUMMER_COLOR,
    SaleNotice,
    SalesCalendar,
    SteamSale,
    active_sale,
    discord_timestamp,
    due_notices,
    format_argentina_time,
    parse_steamworks_events,
    upcoming_sales,
)

SALE = SteamSale("Rebajas de Otoño", date(2026, 10, 1), date(2026, 10, 8), "🍂")
SALES = [SALE]


# ── Horarios ──────────────────────────────────────────────────────────────────


def test_sale_starts_at_10_pacific_which_is_14_in_argentina():
    assert SALE.start.astimezone(UTC) == datetime(2026, 10, 1, 17, 0, tzinfo=UTC)
    assert format_argentina_time(SALE.start) == "jueves 1/10 a las 14:00"


def test_winter_sale_starts_one_hour_later_in_argentina():
    # En invierno la costa del Pacífico atrasa una hora; Argentina no cambia.
    winter = SteamSale("Rebajas de Invierno", date(2026, 12, 17), date(2027, 1, 4))
    assert format_argentina_time(winter.start) == "jueves 17/12 a las 15:00"


def test_discord_timestamp_accepts_datetime_or_epoch():
    assert discord_timestamp(datetime(2026, 10, 1, 17, 0, tzinfo=UTC)) == "<t:1790874000:R>"
    assert discord_timestamp(1790874000, "F") == "<t:1790874000:F>"


# ── Rebaja activa y próximas ──────────────────────────────────────────────────


def test_active_and_upcoming():
    before = datetime(2026, 9, 28, tzinfo=UTC)
    during = datetime(2026, 10, 3, tzinfo=UTC)
    assert active_sale(before, SALES) is None
    assert upcoming_sales(before, SALES) == [SALE]
    assert active_sale(during, SALES) == SALE
    assert upcoming_sales(during, SALES) == []


def test_upcoming_sales_are_sorted_and_limited():
    now = datetime(2026, 9, 28, tzinfo=UTC)
    upcoming = upcoming_sales(now, list(reversed(FALLBACK_SALES)), limit=2)
    assert [sale.first_day for sale in upcoming] == [date(2026, 10, 1), date(2026, 10, 19)]


# ── Avisos ────────────────────────────────────────────────────────────────────


def test_notices_timeline():
    def due(moment: datetime) -> list[SaleNotice]:
        return [notice for _, notice in due_notices(moment, set(), SALES)]

    assert due(SALE.start - timedelta(days=8)) == []
    assert due(SALE.start - timedelta(days=6)) == [SaleNotice.WEEK_BEFORE]
    assert due(SALE.start - timedelta(hours=12)) == [SaleNotice.DAY_BEFORE]
    assert due(SALE.start + timedelta(minutes=5)) == [SaleNotice.STARTED]
    assert due(SALE.end - timedelta(hours=2)) == [SaleNotice.ENDING]
    assert due(SALE.end + timedelta(minutes=1)) == []


def test_only_latest_notice_is_due_after_downtime():
    # Si el bot estuvo apagado, no manda juntos el aviso de 7 días, el de 1 día y el de inicio.
    now = SALE.start + timedelta(hours=1)
    assert due_notices(now, set(), SALES) == [(SALE, SaleNotice.STARTED)]


def test_sent_notices_are_not_repeated():
    now = SALE.start + timedelta(hours=1)
    already_sent = {(SALE.key, "start")}  # como vuelve de la base de datos: texto plano
    assert due_notices(now, already_sent, SALES) == []


def test_notice_values_match_what_the_database_stores():
    assert [notice.value for notice in SaleNotice] == ["7d", "1d", "start", "ending"]
    assert SALE.key == "Rebajas de Otoño-2026-10-01"


# ── Lectura de Steamworks ─────────────────────────────────────────────────────


def test_parse_real_page_snapshot():
    # Copia de la página de Steamworks del 28/09/2026
    page = (FIXTURES / "steamworks_upcoming_events.html").read_text(encoding="utf-8", errors="replace")
    assert parse_steamworks_events(page) == sorted(FALLBACK_SALES, key=lambda sale: sale.first_day)


def test_parse_date_formats():
    page = (
        "<td>Winter Sale 2026</td><td>17 December, 2026 - 4 January, 2027</td>"
        "<b>Next Fest</b> | June 14 - 21, 2027"
        "<b>Next Fest</b> | February 22 - March 1, 2027"
    )
    parsed = {(sale.name, sale.first_day, sale.last_day) for sale in parse_steamworks_events(page)}
    assert parsed == {
        ("Rebajas de Invierno", date(2026, 12, 17), date(2027, 1, 4)),
        ("Steam Next Fest", date(2027, 6, 14), date(2027, 6, 21)),
        ("Steam Next Fest", date(2027, 2, 22), date(2027, 3, 1)),
    }


def test_parse_unknown_format_finds_nothing():
    assert parse_steamworks_events("<html>Página nueva sin fechas</html>") == []


async def test_calendar_reads_steamworks():
    page = "<td>Summer Sale 2027</td><td>24 June, 2027 - 8 July, 2027</td>"
    calendar = SalesCalendar(FakeSession({"upcoming_events": page}))  # type: ignore[arg-type]
    assert list(await calendar.sales()) == [
        SteamSale("Rebajas de Verano", date(2027, 6, 24), date(2027, 7, 8), "☀️", SUMMER_COLOR)
    ]


async def test_calendar_falls_back_when_page_is_down_or_unreadable():
    down = SalesCalendar(FakeSession({"upcoming_events": aiohttp.ClientError()}))  # type: ignore[arg-type]
    unreadable = SalesCalendar(FakeSession({"upcoming_events": "<html>otro formato</html>"}))  # type: ignore[arg-type]
    assert await down.sales() == FALLBACK_SALES
    assert await unreadable.sales() == FALLBACK_SALES


def test_only_seasonal_sales_have_their_own_color():
    colors = {sale.name: sale.color for sale in FALLBACK_SALES}
    assert colors["Rebajas de Otoño"] == 0xE67E22  # naranja
    assert colors["Steam Next Fest"] is None  # no es una rebaja de precios
    assert all(color for name, color in colors.items() if name.startswith("Rebajas"))
