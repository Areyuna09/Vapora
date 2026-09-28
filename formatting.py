"""Formato de precios al estilo argentino."""

import config
from prices import calculate_ars_prices


def format_money(cents: int, currency: str | None) -> str:
    """Formatea centavos al estilo argentino: 2999 -> 'USD 29,99'."""
    amount = f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency or ''} {amount}".strip()


def format_price(data: dict) -> str:
    if data.get("final_cents") is not None:
        text = f"**{format_money(data['final_cents'], data.get('currency'))}**"
        if data.get("discount_percent"):
            before = format_money(data["initial_cents"], data.get("currency"))
            text += f"\n~~{before}~~ (-{data['discount_percent']}%)"
        return text
    if data.get("price"):
        return data["price"]
    if data.get("is_free"):
        return "**Gratis**"
    return "Sin precio disponible"


def format_ars(amount: float) -> str:
    """Formatea pesos al estilo argentino: 56244.5 -> '$ 56.244,50'."""
    return "$ " + format_money(round(amount * 100), None)


def format_rates_footer(rates: dict[str, float]) -> str:
    parts = []
    if rates.get("oficial"):
        parts.append(f"Oficial {format_ars(rates['oficial'])}")
    if rates.get("cripto"):
        parts.append(f"ARQ {format_ars(rates['cripto'])}")
    taxes = f"IVA {config.IVA_PERCENT:g}%"
    taxes += f" + IIBB {config.PROVINCE_TAX_PERCENT:g}%" if config.PROVINCE_TAX_PERCENT else " (sin IIBB)"
    parts.append(taxes)
    return " · ".join(parts)


def ars_prices_for(data: dict, rates: dict[str, float] | None) -> dict[str, float]:
    """Precios en pesos (Mercado Pago y ARQ) si el precio está en USD y hay cotización."""
    if rates and data.get("final_cents") and data.get("currency") == "USD":
        return calculate_ars_prices(data["final_cents"], rates)
    return {}
