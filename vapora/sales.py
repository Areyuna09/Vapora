"""Calendario de rebajas de Steam y cuándo anunciarlas.

Las fechas se leen una vez por día del calendario oficial de Steamworks:
https://partner.steamgames.com/doc/marketing/upcoming_events
Valve no las publica en una API, así que se interpreta el texto de esa página. Si el
formato cambia y no se puede leer, se usa FALLBACK_SALES como respaldo.
Todas empiezan y terminan a las 10:00 hora del Pacífico.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

import aiohttp

from vapora.cache import RefreshingValue

log = logging.getLogger(__name__)

PACIFIC = ZoneInfo("America/Los_Angeles")
ARGENTINA = timezone(timedelta(hours=-3))  # Argentina no tiene horario de verano
SALE_TIME = time(10, 0)

STEAMWORKS_EVENTS_URL = "https://partner.steamgames.com/doc/marketing/upcoming_events?l=english"
CALENDAR_TTL_SECONDS = 24 * 60 * 60


class SaleNotice(StrEnum):
    """Avisos que se mandan por cada rebaja. El valor es el que se guarda en la base."""

    WEEK_BEFORE = "7d"
    DAY_BEFORE = "1d"
    STARTED = "start"
    ENDING = "ending"


@dataclass(frozen=True, slots=True)
class SteamSale:
    name: str
    first_day: date
    last_day: date  # termina ese día a las 10:00 (Pacífico)
    emoji: str = "🔥"
    color: int | None = None  # color de las tarjetas mientras dura (RGB); None = el de siempre

    @property
    def key(self) -> str:
        """Identificador estable de la rebaja, para recordar qué avisos ya se mandaron."""
        return f"{self.name}-{self.first_day.isoformat()}"

    @property
    def start(self) -> datetime:
        return datetime.combine(self.first_day, SALE_TIME, PACIFIC)

    @property
    def end(self) -> datetime:
        return datetime.combine(self.last_day, SALE_TIME, PACIFIC)

    def is_active(self, now: datetime) -> bool:
        return self.start <= now < self.end

    def notice_times(self) -> dict[SaleNotice, datetime]:
        """Momento a partir del cual corresponde mandar cada aviso."""
        return {
            SaleNotice.WEEK_BEFORE: self.start - timedelta(days=7),
            SaleNotice.DAY_BEFORE: self.start - timedelta(days=1),
            SaleNotice.STARTED: self.start,
            SaleNotice.ENDING: self.end - timedelta(days=1),
        }


# Color de las tarjetas durante cada rebaja de temporada.
AUTUMN_COLOR = 0xE67E22  # naranja
WINTER_COLOR = 0xB3E5FC  # celeste hielo
SPRING_COLOR = 0xF48FB1  # rosa
SUMMER_COLOR = 0xF9C74F  # amarillo

# Respaldo por si no se puede leer la página de Steamworks.
FALLBACK_SALES: tuple[SteamSale, ...] = (
    SteamSale("Rebajas de Otoño", date(2026, 10, 1), date(2026, 10, 8), "🍂", AUTUMN_COLOR),
    SteamSale("Steam Next Fest", date(2026, 10, 19), date(2026, 10, 26), "🧪"),
    SteamSale("Rebajas de Invierno", date(2026, 12, 17), date(2027, 1, 4), "❄️", WINTER_COLOR),
    SteamSale("Steam Next Fest", date(2027, 2, 22), date(2027, 3, 1), "🧪"),
    SteamSale("Rebajas de Primavera", date(2027, 3, 18), date(2027, 3, 25), "🌸", SPRING_COLOR),
    SteamSale("Steam Next Fest", date(2027, 6, 14), date(2027, 6, 21), "🧪"),
    SteamSale("Rebajas de Verano", date(2027, 6, 24), date(2027, 7, 8), "☀️", SUMMER_COLOR),
)


# ── Consultas sobre el calendario ─────────────────────────────────────────────


def active_sale(now: datetime, sales: Sequence[SteamSale]) -> SteamSale | None:
    return next((sale for sale in sales if sale.is_active(now)), None)


def upcoming_sales(now: datetime, sales: Sequence[SteamSale], limit: int = 4) -> list[SteamSale]:
    return sorted((sale for sale in sales if sale.start > now), key=lambda sale: sale.start)[:limit]


def due_notices(
    now: datetime, already_sent: Collection[tuple[str, str]], sales: Sequence[SteamSale]
) -> list[tuple[SteamSale, SaleNotice]]:
    """Avisos que corresponde mandar ahora.

    De cada rebaja devuelve solo el aviso más reciente, para no mandar varios juntos si el
    bot estuvo apagado. `already_sent` son pares (clave de la rebaja, aviso) ya enviados.
    """
    due = []
    for sale in sales:
        if now >= sale.end:
            continue
        reached = [(notice, when) for notice, when in sale.notice_times().items() if now >= when]
        if not reached:
            continue
        latest, _ = max(reached, key=lambda pair: pair[1])
        if (sale.key, latest) not in already_sent:
            due.append((sale, latest))
    return due


# ── Formato de fechas ─────────────────────────────────────────────────────────

_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def format_argentina_time(moment: datetime) -> str:
    """'jueves 1/10 a las 14:00' en hora argentina."""
    local = moment.astimezone(ARGENTINA)
    return f"{_WEEKDAYS[local.weekday()]} {local.day}/{local.month} a las {local:%H:%M}"


def discord_timestamp(moment: datetime | int, style: str = "R") -> str:
    """Timestamp de Discord: cada usuario lo ve en su hora local ("R" = 'en 3 días')."""
    epoch = moment if isinstance(moment, int) else int(moment.timestamp())
    return f"<t:{epoch}:{style}>"


# ── Lectura del calendario de Steamworks ──────────────────────────────────────

_SEASONS = {
    "Autumn": ("Rebajas de Otoño", "🍂", AUTUMN_COLOR),
    "Winter": ("Rebajas de Invierno", "❄️", WINTER_COLOR),
    "Spring": ("Rebajas de Primavera", "🌸", SPRING_COLOR),
    "Summer": ("Rebajas de Verano", "☀️", SUMMER_COLOR),
}
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip
_MONTH = "(" + "|".join(_MONTHS) + ")"

# "Autumn Sale 2026 | 1 October, 2026 - 8 October, 2026"
_SEASONAL_RE = re.compile(
    rf"(Autumn|Winter|Spring|Summer) Sale \d{{4}}\W+"
    rf"(\d{{1,2}}) {_MONTH},? (\d{{4}})\s*-\s*(\d{{1,2}}) {_MONTH},? (\d{{4}})"
)
# "Next Fest | October 19 - October 26, 2026"  o  "Next Fest | June 14 - 21, 2027"
_NEXT_FEST_RE = re.compile(
    rf"Next Fest\s*\|\s*{_MONTH} (\d{{1,2}})\s*-\s*(?:{_MONTH} )?(\d{{1,2}}),? (\d{{4}})"
)


def _month_number(name: str) -> int:
    return _MONTHS.index(name) + 1


def _page_text(page_html: str) -> str:
    """Texto plano de la página, con las etiquetas reemplazadas por ' | '."""
    text = html.unescape(re.sub(r"<[^>]+>", " | ", page_html))
    text = re.sub(r"(\s*\|\s*)+", " | ", text)
    return re.sub(r"\s+", " ", text)


def parse_steamworks_events(page_html: str) -> list[SteamSale]:
    """Rebajas de temporada y Steam Next Fest que anuncia la página de Steamworks."""
    text = _page_text(page_html)
    sales = set()
    for season, day1, month1, year1, day2, month2, year2 in _SEASONAL_RE.findall(text):
        name, emoji, color = _SEASONS[season]
        sales.add(
            SteamSale(
                name,
                date(int(year1), _month_number(month1), int(day1)),
                date(int(year2), _month_number(month2), int(day2)),
                emoji,
                color,
            )
        )
    for month1, day1, month2, day2, year in _NEXT_FEST_RE.findall(text):
        start = date(int(year), _month_number(month1), int(day1))
        end = date(int(year), _month_number(month2 or month1), int(day2))
        if end < start:  # por si cruza de año (ej. diciembre - enero)
            end = end.replace(year=end.year + 1)
        sales.add(SteamSale("Steam Next Fest", start, end, "🧪"))
    return sorted(sales, key=lambda sale: sale.first_day)


class SalesCalendar:
    """Calendario de rebajas, leído de Steamworks una vez por día."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._sales: RefreshingValue[Sequence[SteamSale]] = RefreshingValue(
            CALENDAR_TTL_SECONDS, FALLBACK_SALES
        )
        self._read_from_steamworks = False
        self._warned_fallback_expired = False

    async def sales(self) -> Sequence[SteamSale]:
        return await self._sales.get(self._fetch)

    async def _fetch(self) -> Sequence[SteamSale] | None:
        try:
            async with self._session.get(STEAMWORKS_EVENTS_URL) as response:
                response.raise_for_status()
                parsed = parse_steamworks_events(await response.text())
        except (aiohttp.ClientError, TimeoutError):
            log.warning("No se pudo leer el calendario de Steamworks", exc_info=True)
            self._check_fallback()
            return None
        if not parsed:
            log.warning("No pude leer fechas en la página de Steamworks: ¿cambió el formato?")
            self._check_fallback()
            return None
        log.info("Calendario de rebajas actualizado desde Steamworks: %d eventos", len(parsed))
        self._read_from_steamworks = True
        return parsed

    def _check_fallback(self) -> None:
        """Avisa (una vez) si se está usando el respaldo y ya no le quedan fechas por venir."""
        if self._read_from_steamworks or self._warned_fallback_expired:
            return
        now = datetime.now(PACIFIC)
        if all(sale.end <= now for sale in FALLBACK_SALES):
            log.error(
                "El calendario de respaldo (FALLBACK_SALES) ya no tiene rebajas futuras y no se "
                "pudo leer Steamworks: no habrá avisos de rebajas hasta actualizarlo."
            )
            self._warned_fallback_expired = True
