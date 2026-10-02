from datetime import UTC, date, datetime

from vapora.pricing import PesoConverter
from vapora.sales import AUTUMN_COLOR, SaleNotice, SteamSale
from vapora.steam import Deal, ItemKind, ItemRef, Price
from vapora.ui.announcements import (
    build_deals_embed,
    build_sale_notice_embed,
    build_sales_calendar_embed,
    format_deal,
)

SALE = SteamSale("Rebajas de Otoño", date(2026, 10, 1), date(2026, 10, 8), "🍂", AUTUMN_COLOR)
DEAL = Deal(
    ItemRef.app(7), "Juego AR", Price(600, 1000, 40, "USD"), "https://example.com/capsule.jpg", 1790874000
)


def test_deal_lines(converter: PesoConverter):
    assert format_deal(DEAL, converter, argentine_app_ids={7}) == (
        "**[Juego AR](https://store.steampowered.com/app/7/)** 🧉\n"
        "-40% · ~~USD 10,00~~ **USD 6,00**\n"
        "💳 $ 11.253,00 · 🟣 $ 9.740,64"
    )


def test_deal_without_rates_has_no_peso_line():
    assert format_deal(DEAL, None, argentine_app_ids=set()) == (
        "**[Juego AR](https://store.steampowered.com/app/7/)**\n-40% · ~~USD 10,00~~ **USD 6,00**"
    )


def test_package_deal_links_to_package_and_is_never_marked_argentine():
    package = Deal(
        ItemRef(ItemKind.PACKAGE, 94174), "DARK SOULS III Deluxe Edition", Price(3399, 6798, 50, "USD")
    )
    text = format_deal(package, None, argentine_app_ids={94174})  # la lista de argentinos es de juegos
    assert "store.steampowered.com/sub/94174/" in text
    assert "🧉" not in text


def test_deals_embed(converter: PesoConverter):
    embed = build_deals_embed([DEAL], converter, argentine_app_ids=set(), current_sale=None)
    assert embed.title == "🔥 Ofertas destacadas de hoy"
    assert "Juego AR" in embed.description
    assert embed.thumbnail.url == "https://example.com/capsule.jpg"
    assert [(field.name, field.value) for field in embed.fields] == [("⏳ Terminan", "<t:1790874000:R>")]
    assert embed.footer.text == (
        "💳 Mercado Pago · 🟣 ARQ · 🧉 juego argentino\n"
        "Oficial $ 1.550,00 · ARQ $ 1.623,44 · IVA 21% (sin IIBB)"
    )


def test_deals_embed_is_titled_after_the_running_sale():
    embed = build_deals_embed([DEAL], None, argentine_app_ids=set(), current_sale=SALE)
    assert embed.title == "🍂 Ofertas destacadas · Rebajas de Otoño"
    assert embed.footer.text == "💳 Mercado Pago · 🟣 ARQ · 🧉 juego argentino"


def test_deals_embed_skips_expiration_when_deals_end_at_different_times():
    other = Deal(ItemRef.app(8), "Otro", Price(500, 1000, 50, "USD"), expires_at=1790999999)
    embed = build_deals_embed([DEAL, other], None, argentine_app_ids=set(), current_sale=None)
    assert embed.fields == []


def test_deals_embed_without_deals():
    embed = build_deals_embed([], None, argentine_app_ids=set(), current_sale=None)
    assert embed.description == "Hoy Steam no tiene ofertas destacadas. ¡Volvé mañana!"


def test_sale_notices():
    started = build_sale_notice_embed(SALE, SaleNotice.STARTED)
    assert started.title == "🍂 Rebajas de Otoño de Steam · ¡Ya arrancaron!"
    assert started.description == (
        "Duran hasta el **jueves 8/10 a las 14:00** (<t:1791478800:R>). ¡A cazar ofertas! 🎯"
    )
    week_before = build_sale_notice_embed(SALE, SaleNotice.WEEK_BEFORE)
    assert week_before.title.endswith("¡Se vienen!")
    assert "el **jueves 1/10 a las 14:00** (<t:1790874000:R>)" in week_before.description
    for notice in SaleNotice:  # todos los avisos tienen su texto
        assert build_sale_notice_embed(SALE, notice).description


def test_sales_calendar_before_and_during_a_sale():
    before = build_sales_calendar_embed(datetime(2026, 9, 28, tzinfo=UTC), [SALE])
    assert before.title == "📅 Rebajas de Steam"
    assert [(field.name, field.value) for field in before.fields] == [
        ("🍂 Rebajas de Otoño", "jueves 1/10 a las 14:00 (<t:1790874000:R>)"),
    ]
    during = build_sales_calendar_embed(datetime(2026, 10, 3, tzinfo=UTC), [SALE])
    assert [(field.name, field.value) for field in during.fields] == [
        ("🍂 Ahora: Rebajas de Otoño", "Termina el **jueves 8/10 a las 14:00** (<t:1791478800:R>)"),
    ]


def test_sales_calendar_without_sales():
    embed = build_sales_calendar_embed(datetime(2030, 1, 1, tzinfo=UTC), [SALE])
    assert embed.description == "No hay rebajas cargadas en el calendario."


def test_announcements_take_the_color_of_the_sale():
    without_sale = build_deals_embed([DEAL], None, argentine_app_ids=set(), current_sale=None)
    during_sale = build_deals_embed([DEAL], None, argentine_app_ids=set(), current_sale=SALE)
    assert without_sale.color.value == 0xE8A33D  # naranja de ofertas de siempre
    assert during_sale.color.value == AUTUMN_COLOR
    assert build_sale_notice_embed(SALE, SaleNotice.STARTED).color.value == AUTUMN_COLOR
