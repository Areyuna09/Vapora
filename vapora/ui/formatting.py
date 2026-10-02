"""Formato de números y precios al estilo argentino (punto para miles, coma decimal)."""

from __future__ import annotations

from vapora.pricing import PesoConverter
from vapora.steam import Price, Reviews, StoreItem


def format_thousands(number: int) -> str:
    """109737 -> '109.737'."""
    return f"{number:,}".replace(",", ".")


def format_money(cents: int, currency: str | None = None) -> str:
    """2999, 'USD' -> 'USD 29,99'."""
    amount = f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency or ''} {amount}".strip()


def format_pesos(amount: float) -> str:
    """56244.5 -> '$ 56.244,50'."""
    return "$ " + format_money(round(amount * 100))


def format_steam_price(price: Price) -> str:
    return format_money(price.final_cents, price.currency)


def format_original_price(price: Price) -> str | None:
    """Precio antes del descuento, si Steam lo informa."""
    if price.initial_cents is None:
        return None
    return format_money(price.initial_cents, price.currency)


def format_item_price(item: StoreItem) -> str:
    """Precio de la tarjeta: en negrita y, si hay oferta, con el precio anterior tachado."""
    price = item.price
    if price is None:
        return "**Gratis**" if item.is_free else "Sin precio disponible"
    text = f"**{format_steam_price(price)}**"
    original = format_original_price(price)
    if price.on_sale and original:
        text += f"\n~~{original}~~ (-{price.discount_percent}%)"
    return text


def format_reviews(reviews: Reviews) -> str:
    return f"{reviews.description}\n{reviews.positive_percent}% de {format_thousands(reviews.total)}"


def format_rates_footer(converter: PesoConverter) -> str:
    """Cotizaciones e impuestos usados, para que se vea cómo se hizo la cuenta."""
    rates, taxes = converter.rates, converter.taxes
    parts = []
    if rates.official:
        parts.append(f"Oficial {format_pesos(rates.official)}")
    if rates.crypto:
        parts.append(f"ARQ {format_pesos(rates.crypto)}")
    if taxes.province_percent:
        parts.append(f"IVA {taxes.iva_percent:g}% + IIBB {taxes.province_percent:g}%")
    else:
        parts.append(f"IVA {taxes.iva_percent:g}% (sin IIBB)")
    return " · ".join(parts)
