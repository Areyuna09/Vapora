import config
from bot import build_embed, format_ars
from prices import calculate_ars_prices, card_multiplier
from steam import parse_app_data

RATES = {"oficial": 1550.0, "cripto": 1623.44}


def test_card_multiplier_default_is_iva_only(monkeypatch):
    monkeypatch.setattr(config, "IVA_PERCENT", 21.0)
    monkeypatch.setattr(config, "PROVINCE_TAX_PERCENT", 0.0)
    assert card_multiplier() == 1.21


def test_matches_steamcito_card_rate(monkeypatch):
    # Steamcito publicó "Dólar Tarjeta" 1875.50 = oficial 1550 × 1.21 (28/09/2026)
    monkeypatch.setattr(config, "IVA_PERCENT", 21.0)
    monkeypatch.setattr(config, "PROVINCE_TAX_PERCENT", 0.0)
    assert calculate_ars_prices(100, RATES)["tarjeta"] == 1875.50


def test_calculate_ars_prices(monkeypatch):
    monkeypatch.setattr(config, "IVA_PERCENT", 21.0)
    monkeypatch.setattr(config, "PROVINCE_TAX_PERCENT", 0.0)
    prices = calculate_ars_prices(2999, RATES)
    assert prices["tarjeta"] == round(29.99 * 1550 * 1.21, 2)
    assert prices["cripto"] == round(29.99 * 1623.44, 2)


def test_province_tax_is_added(monkeypatch):
    monkeypatch.setattr(config, "IVA_PERCENT", 21.0)
    monkeypatch.setattr(config, "PROVINCE_TAX_PERCENT", 2.0)
    assert calculate_ars_prices(100, {"oficial": 1000.0})["tarjeta"] == 1230.0


def test_missing_rates_are_skipped():
    assert calculate_ars_prices(2999, {"oficial": 1550.0}).keys() == {"tarjeta"}
    assert calculate_ars_prices(2999, {}) == {}


def test_format_ars():
    assert format_ars(56244.5) == "$ 56.244,50"


def _embed_for(data_overrides, rates):
    data = parse_app_data(1, {"name": "Juego", **data_overrides})
    return build_embed(1, data, rates)


def test_embed_shows_ars_prices():
    embed = _embed_for(
        {"price_overview": {"currency": "USD", "initial": 2999, "final": 2999, "discount_percent": 0}},
        RATES,
    )
    names = [f.name for f in embed.fields]
    assert "💳 Mercado Pago" in names
    assert "🟣 ARQ" in names
    assert "Oficial $ 1.550,00" in embed.footer.text


def test_embed_without_rates_or_free_game_has_no_ars():
    paid = _embed_for(
        {"price_overview": {"currency": "USD", "initial": 2999, "final": 2999, "discount_percent": 0}},
        {},
    )
    free = _embed_for({"is_free": True}, RATES)
    for embed in (paid, free):
        assert "💳 Mercado Pago" not in [f.name for f in embed.fields]
