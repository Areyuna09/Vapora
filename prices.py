"""Cotizaciones del dólar y conversión de precios de Steam a pesos argentinos.

Replica el cálculo de Steamcito:
- Mercado Pago / tarjeta en pesos: USD × dólar oficial (venta) × (1 + IVA + IIBB)
- ARQ: USD × dólar cripto (venta), sin impuestos. Coincide con la tasa que muestra ARQ (±0,1%)
"""

import logging
import time
from typing import Any

import aiohttp

import config

DOLARAPI_URL = "https://dolarapi.com/v1/dolares/{casa}"

_RATES_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def card_multiplier() -> float:
    """Recargo total sobre el dólar oficial al pagar con tarjeta en pesos."""
    return 1 + (config.IVA_PERCENT + config.PROVINCE_TAX_PERCENT) / 100


def calculate_ars_prices(usd_cents: int, rates: dict[str, float]) -> dict[str, float]:
    """Calcula los precios en pesos para cada medio de pago disponible."""
    usd = usd_cents / 100
    prices: dict[str, float] = {}
    if rates.get("oficial"):
        prices["tarjeta"] = round(usd * rates["oficial"] * card_multiplier(), 2)
    if rates.get("cripto"):
        prices["cripto"] = round(usd * rates["cripto"], 2)
    return prices


async def _fetch_rate(session: aiohttp.ClientSession, casa: str) -> dict[str, Any] | None:
    try:
        async with session.get(DOLARAPI_URL.format(casa=casa)) as response:
            response.raise_for_status()
            data = await response.json()
            return {"venta": float(data["venta"]), "fecha": data.get("fechaActualizacion")}
    except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError):
        logging.warning("No se pudo obtener la cotización '%s'", casa, exc_info=True)
        return None


async def get_rates(session: aiohttp.ClientSession) -> dict[str, float]:
    """Devuelve {'oficial': venta, 'cripto': venta}. Si falla, usa el último valor conocido."""
    now = time.time()
    rates: dict[str, float] = {}
    for casa in ("oficial", "cripto"):
        cached = _RATES_CACHE.get(casa)
        if not cached or now - cached[0] >= config.EXCHANGE_RATE_TTL_SECONDS:
            fresh = await _fetch_rate(session, casa)
            if fresh:
                cached = (now, fresh)
                _RATES_CACHE[casa] = cached
        if cached:
            rates[casa] = cached[1]["venta"]
    return rates
