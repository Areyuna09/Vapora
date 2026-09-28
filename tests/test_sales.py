from datetime import date, datetime, timedelta, timezone

from announcements import build_deals_embed, build_sale_embed, build_sales_calendar_embed
from bot import build_description
from sales import SteamSale, active_sale, due_announcements, format_argentina_time, upcoming_sales
from steam import parse_curator_app_ids, parse_specials

SALE = SteamSale("Rebajas de Otoño", date(2026, 10, 1), date(2026, 10, 8), "🍂")
SALES = [SALE]
UTC = timezone.utc


def test_sale_starts_at_10_pacific_which_is_14_argentina():
    assert SALE.start.astimezone(UTC) == datetime(2026, 10, 1, 17, 0, tzinfo=UTC)
    assert format_argentina_time(SALE.start) == "jueves 1/10 a las 14:00"


def test_active_and_upcoming():
    before = datetime(2026, 9, 28, tzinfo=UTC)
    during = datetime(2026, 10, 3, tzinfo=UTC)
    assert active_sale(before, SALES) is None
    assert upcoming_sales(before, SALES) == [SALE]
    assert active_sale(during, SALES) == SALE
    assert upcoming_sales(during, SALES) == []


def test_announcements_timeline():
    assert due_announcements(SALE.start - timedelta(days=8), set(), SALES) == []
    assert due_announcements(SALE.start - timedelta(days=6), set(), SALES) == [(SALE, "7d")]
    assert due_announcements(SALE.start - timedelta(hours=12), set(), SALES) == [(SALE, "1d")]
    assert due_announcements(SALE.start + timedelta(minutes=5), set(), SALES) == [(SALE, "start")]
    assert due_announcements(SALE.end - timedelta(hours=2), set(), SALES) == [(SALE, "ending")]
    assert due_announcements(SALE.end + timedelta(minutes=1), set(), SALES) == []


def test_announcements_not_repeated_and_old_ones_skipped():
    now = SALE.start + timedelta(hours=1)
    # Si el bot estuvo apagado, no manda juntos el aviso de 7 días, el de 1 día y el de inicio.
    assert due_announcements(now, set(), SALES) == [(SALE, "start")]
    assert due_announcements(now, {f"{SALE.key}:start"}, SALES) == []


def test_sale_embeds():
    assert "Ya arrancaron" in build_sale_embed(SALE, "start").title
    calendar = build_sales_calendar_embed(datetime(2026, 9, 28, tzinfo=UTC))
    assert calendar.title == "📅 Rebajas de Steam"


def test_parse_curator_app_ids():
    html = '<div data-ds-appid="123"></div><a data-ds-appid="123"></a><div data-ds-appid="456"></div>'
    assert parse_curator_app_ids(html) == {123, 456}


def test_parse_specials_skips_non_discounted_and_duplicates():
    payload = {"specials": {"items": [
        {"id": 1, "name": "A", "discounted": True, "discount_percent": 50,
         "original_price": 2000, "final_price": 1000, "currency": "USD"},
        {"id": 1, "name": "A", "discounted": True, "discount_percent": 50,
         "original_price": 2000, "final_price": 1000, "currency": "USD"},
        {"id": 2, "name": "B", "discounted": False, "final_price": 999, "currency": "USD"},
    ]}}
    deals = parse_specials(payload)
    assert [d["id"] for d in deals] == [1]


def test_parse_specials_kind_for_packages():
    payload = {"specials": {"items": [
        {"type": 1, "id": 94174, "name": "DARK SOULS III Deluxe Edition", "discounted": True,
         "discount_percent": 50, "original_price": 6798, "final_price": 3399, "currency": "USD"},
    ]}}
    deal = parse_specials(payload)[0]
    assert deal["kind"] == "sub"
    embed = build_deals_embed([deal], None, {94174}, datetime(2026, 9, 28, tzinfo=UTC))
    assert "store.steampowered.com/sub/94174/" in embed.description
    assert "🧉" not in embed.description  # la lista de argentinos es de juegos (app), no paquetes


def test_deals_embed_marks_argentine_games():
    deals = parse_specials({"specials": {"items": [
        {"id": 7, "name": "Juego AR", "discounted": True, "discount_percent": 40,
         "original_price": 1000, "final_price": 600, "currency": "USD"},
    ]}})
    embed = build_deals_embed(deals, {"oficial": 1550.0, "cripto": 1620.0}, {7},
                              datetime(2026, 9, 28, tzinfo=UTC))
    assert "Juego AR" in embed.description and "🧉" in embed.description
    assert "💳 $" in embed.description
    during = build_deals_embed(deals, None, set(), datetime(2026, 10, 3, tzinfo=UTC))
    assert during.title.startswith("🍂")


def test_argentine_line_only_when_argentine():
    assert "Juego argentino" in build_description({"argentine": True, "name": "X"})
    assert build_description({"argentine": False, "name": "X"}) is None


def test_parse_steamworks_page_snapshot():
    # Copia de la página de Steamworks del 28/09/2026
    from pathlib import Path
    from sales import FALLBACK_SALES, parse_steamworks_events
    page = (Path(__file__).parent / "fixtures" / "steamworks_upcoming_events.html").read_text(
        encoding="utf-8", errors="replace")
    assert parse_steamworks_events(page) == sorted(FALLBACK_SALES, key=lambda s: s.first_day)


def test_parse_steamworks_formats():
    from sales import parse_steamworks_events
    html = (
        "<td>Winter Sale 2026</td><td>17 December, 2026 - 4 January, 2027</td>"
        "<b>Next Fest</b> | June 14 - 21, 2027"
        "<b>Next Fest</b> | February 22 - March 1, 2027"
    )
    parsed = {(s.name, s.first_day, s.last_day) for s in parse_steamworks_events(html)}
    assert parsed == {
        ("Rebajas de Invierno", date(2026, 12, 17), date(2027, 1, 4)),
        ("Steam Next Fest", date(2027, 6, 14), date(2027, 6, 21)),
        ("Steam Next Fest", date(2027, 2, 22), date(2027, 3, 1)),
    }


def test_parse_steamworks_unknown_format_returns_empty():
    from sales import parse_steamworks_events
    assert parse_steamworks_events("<html>Página nueva sin fechas</html>") == []
