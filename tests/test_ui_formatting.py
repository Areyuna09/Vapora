from helpers import make_item

from vapora.pricing import ExchangeRates, PesoConverter, Taxes
from vapora.steam import Price, Reviews
from vapora.ui.formatting import (
    format_item_price,
    format_money,
    format_original_price,
    format_pesos,
    format_rates_footer,
    format_reviews,
    format_thousands,
)


def test_money_uses_argentine_separators():
    assert format_money(2999, "USD") == "USD 29,99"
    assert format_money(123456, "USD") == "USD 1.234,56"
    assert format_money(500) == "5,00"


def test_pesos():
    assert format_pesos(56244.5) == "$ 56.244,50"
    assert format_pesos(1550) == "$ 1.550,00"


def test_thousands():
    assert format_thousands(109737) == "109.737"
    assert format_thousands(42) == "42"


def test_price_with_discount_shows_original_struck_through():
    item = make_item(price_cents=2999, initial_cents=5999, discount=50)
    assert format_item_price(item) == "**USD 29,99**\n~~USD 59,99~~ (-50%)"


def test_price_without_discount():
    assert format_item_price(make_item(price_cents=999)) == "**USD 9,99**"


def test_free_and_unavailable_prices():
    assert format_item_price(make_item(price_cents=None, is_free=True)) == "**Gratis**"
    assert format_item_price(make_item(price_cents=None)) == "Sin precio disponible"


def test_original_price_is_optional():
    assert format_original_price(Price(500, currency="USD")) is None
    assert format_original_price(Price(500, 1000, 50, "USD")) == "USD 10,00"


def test_reviews():
    assert format_reviews(Reviews("Muy positivas", 109737, 85)) == "Muy positivas\n85% de 109.737"


def test_rates_footer():
    rates = ExchangeRates(official=1550.0, crypto=1623.34)
    assert format_rates_footer(PesoConverter(rates, Taxes())) == (
        "Oficial $ 1.550,00 · ARQ $ 1.623,34 · IVA 21% (sin IIBB)"
    )
    assert format_rates_footer(PesoConverter(ExchangeRates(official=1550.0), Taxes(province_percent=2))) == (
        "Oficial $ 1.550,00 · IVA 21% + IIBB 2%"
    )
