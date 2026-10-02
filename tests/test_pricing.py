import aiohttp
from helpers import FakeSession

from vapora.pricing import DollarClient, ExchangeRates, PesoConverter, PesoPrices, Taxes
from vapora.steam import Price

RATES = ExchangeRates(official=1550.0, crypto=1623.44)


def usd(cents: int) -> Price:
    return Price(cents, currency="USD")


# ── Impuestos y conversión ────────────────────────────────────────────────────


def test_card_pays_iva_only_by_default():
    assert Taxes().card_multiplier == 1.21


def test_province_tax_is_added_to_iva():
    assert Taxes(iva_percent=21, province_percent=2).card_multiplier == 1.23


def test_card_rate_is_official_plus_iva():
    # Dólar oficial 1550 + IVA 21% = 1875,50 por dólar
    assert PesoConverter(RATES, Taxes()).convert(usd(100)) == PesoPrices(card=1875.50, crypto=1623.44)


def test_convert_price():
    pesos = PesoConverter(RATES, Taxes()).convert(usd(2999))
    assert pesos == PesoPrices(card=round(29.99 * 1550 * 1.21, 2), crypto=round(29.99 * 1623.44, 2))


def test_convert_with_province_tax():
    converter = PesoConverter(ExchangeRates(official=1000.0), Taxes(province_percent=2))
    assert converter.convert(usd(100)) == PesoPrices(card=1230.0, crypto=None)


def test_convert_with_only_one_rate():
    assert PesoConverter(ExchangeRates(crypto=1600.0), Taxes()).convert(usd(100)) == PesoPrices(None, 1600.0)


def test_nothing_to_convert():
    converter = PesoConverter(RATES, Taxes())
    assert converter.convert(None) is None  # gratis o sin precio
    assert converter.convert(Price(2999, currency="EUR")) is None  # no está en dólares
    assert converter.convert(usd(0)) is None
    assert PesoConverter(ExchangeRates(), Taxes()).convert(usd(2999)) is None  # sin cotizaciones


# ── Cotizaciones ──────────────────────────────────────────────────────────────


async def test_rates_come_from_sell_price():
    session = FakeSession({"dolares/oficial": {"venta": 1550}, "dolares/cripto": {"venta": "1623.44"}})
    assert await DollarClient(session).rates() == RATES  # type: ignore[arg-type]


async def test_rates_are_cached():
    session = FakeSession({"dolares/oficial": {"venta": 1550}, "dolares/cripto": {"venta": 1600}})
    client = DollarClient(session)  # type: ignore[arg-type]
    await client.rates()
    await client.rates()
    assert len(session.calls) == 2  # una por cotización, no cuatro


async def test_unavailable_rate_is_none_without_breaking_the_other():
    session = FakeSession({"dolares/oficial": aiohttp.ClientError(), "dolares/cripto": {"venta": 1600}})
    assert await DollarClient(session).rates() == ExchangeRates(official=None, crypto=1600.0)  # type: ignore[arg-type]


async def test_malformed_rate_is_none():
    session = FakeSession({"dolares/oficial": {"sin_venta": 1}, "dolares/cripto": {"venta": "abc"}})
    assert await DollarClient(session).rates() == ExchangeRates()  # type: ignore[arg-type]
