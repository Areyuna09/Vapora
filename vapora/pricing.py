"""Cotizaciones del dólar y conversión de precios de Steam a pesos argentinos.

Cómo se calcula:
- Mercado Pago / tarjeta en pesos: USD × dólar oficial (venta) × (1 + IVA + IIBB).
- ARQ: USD × dólar cripto (venta), sin impuestos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiohttp

from vapora.cache import RefreshingValue
from vapora.steam.models import Price

log = logging.getLogger(__name__)

DOLARAPI_URL = "https://dolarapi.com/v1/dolares/{house}"


@dataclass(frozen=True, slots=True)
class Taxes:
    """Impuestos que cobra la tarjeta al pagar en pesos un servicio digital del exterior."""

    iva_percent: float = 21.0
    province_percent: float = 0.0  # Ingresos Brutos; varía según la provincia

    @property
    def card_multiplier(self) -> float:
        return 1 + (self.iva_percent + self.province_percent) / 100


@dataclass(frozen=True, slots=True)
class ExchangeRates:
    """Pesos por dólar (precio de venta). `None` si no se pudo obtener esa cotización."""

    official: float | None = None
    crypto: float | None = None

    @property
    def available(self) -> bool:
        return bool(self.official or self.crypto)


@dataclass(frozen=True, slots=True)
class PesoPrices:
    """Precio final en pesos según el medio de pago."""

    card: float | None = None  # Mercado Pago o cualquier tarjeta en pesos
    crypto: float | None = None  # ARQ


@dataclass(frozen=True, slots=True)
class PesoConverter:
    """Convierte un precio de Steam a pesos con las cotizaciones e impuestos del momento."""

    rates: ExchangeRates
    taxes: Taxes

    def convert(self, price: Price | None) -> PesoPrices | None:
        """`None` si no hay nada que convertir: sin precio, no es en USD o no hay cotización."""
        if price is None or not price.final_cents or not price.is_usd or not self.rates.available:
            return None
        usd = price.final_cents / 100
        card = (
            round(usd * self.rates.official * self.taxes.card_multiplier, 2) if self.rates.official else None
        )
        crypto = round(usd * self.rates.crypto, 2) if self.rates.crypto else None
        return PesoPrices(card, crypto)


class DollarClient:
    """Cotizaciones del dólar desde DolarAPI, con el último valor conocido como respaldo."""

    def __init__(self, session: aiohttp.ClientSession, *, ttl_seconds: float = 30 * 60) -> None:
        self._session = session
        self._official: RefreshingValue[float | None] = RefreshingValue(ttl_seconds, None)
        self._crypto: RefreshingValue[float | None] = RefreshingValue(ttl_seconds, None)

    async def rates(self) -> ExchangeRates:
        return ExchangeRates(
            official=await self._official.get(lambda: self._fetch_sell_rate("oficial")),
            crypto=await self._crypto.get(lambda: self._fetch_sell_rate("cripto")),
        )

    async def _fetch_sell_rate(self, house: str) -> float | None:
        try:
            async with self._session.get(DOLARAPI_URL.format(house=house)) as response:
                response.raise_for_status()
                return float((await response.json())["venta"])
        except (aiohttp.ClientError, TimeoutError, KeyError, TypeError, ValueError):
            log.warning("No se pudo obtener la cotización '%s'", house, exc_info=True)
            return None
