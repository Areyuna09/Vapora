"""Calendario de rebajas de Steam y cuándo anunciarlas.

Las fechas se leen una vez por día del calendario oficial de Steamworks:
https://partner.steamgames.com/doc/marketing/upcoming_events
Valve no las publica en una API, así que se interpreta el texto de esa página. Si el
formato cambia y no se puede leer, se usa FALLBACK_SALES como respaldo.
Todas empiezan y terminan a las 10:00 hora del Pacífico.
"""

import html
import logging
import re
import time as time_module
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp

PACIFIC = ZoneInfo("America/Los_Angeles")
ARGENTINA = timezone(timedelta(hours=-3))  # Argentina no tiene horario de verano
SALE_TIME = time(10, 0)


@dataclass(frozen=True)
class SteamSale:
    name: str
    first_day: date
    last_day: date  # termina ese día a las 10:00 (Pacífico)
    emoji: str = "🔥"

    @property
    def key(self) -> str:
        return f"{self.name}-{self.first_day.isoformat()}"

    @property
    def start(self) -> datetime:
        return datetime.combine(self.first_day, SALE_TIME, PACIFIC)

    @property
    def end(self) -> datetime:
        return datetime.combine(self.last_day, SALE_TIME, PACIFIC)

    def is_active(self, now: datetime) -> bool:
        return self.start <= now < self.end


# Respaldo por si no se puede leer la página de Steamworks.
FALLBACK_SALES = [
    SteamSale("Rebajas de Otoño", date(2026, 10, 1), date(2026, 10, 8), "🍂"),
    SteamSale("Steam Next Fest", date(2026, 10, 19), date(2026, 10, 26), "🧪"),
    SteamSale("Rebajas de Invierno", date(2026, 12, 17), date(2027, 1, 4), "❄️"),
    SteamSale("Steam Next Fest", date(2027, 2, 22), date(2027, 3, 1), "🧪"),
    SteamSale("Rebajas de Primavera", date(2027, 3, 18), date(2027, 3, 25), "🌸"),
    SteamSale("Steam Next Fest", date(2027, 6, 14), date(2027, 6, 21), "🧪"),
    SteamSale("Rebajas de Verano", date(2027, 6, 24), date(2027, 7, 8), "☀️"),
]

# Avisos antes de que empiece cada rebaja: (clave, anticipación)
REMINDERS = [("7d", timedelta(days=7)), ("1d", timedelta(days=1))]


def active_sale(now: datetime, sales: list[SteamSale] = FALLBACK_SALES) -> SteamSale | None:
    return next((s for s in sales if s.is_active(now)), None)


def upcoming_sales(now: datetime, sales: list[SteamSale] = FALLBACK_SALES, limit: int = 4) -> list[SteamSale]:
    return sorted((s for s in sales if s.start > now), key=lambda s: s.start)[:limit]


def due_announcements(now: datetime, already_sent: set[str],
                      sales: list[SteamSale] = FALLBACK_SALES) -> list[tuple[SteamSale, str]]:
    """Anuncios pendientes: recordatorios (7d, 1d), inicio ("start") y últimas 24 h ("ending").

    Solo devuelve el más reciente de cada rebaja, para no mandar varios juntos si el bot
    estuvo apagado. Los tipos ya enviados (según `already_sent`) se ignoran.
    """
    due = []
    for sale in sales:
        if now >= sale.end:
            continue
        candidates = [(kind, sale.start - lead) for kind, lead in REMINDERS]
        candidates += [("start", sale.start), ("ending", sale.end - timedelta(days=1))]
        reached = [(kind, when) for kind, when in candidates if now >= when]
        if not reached:
            continue
        kind, _ = max(reached, key=lambda c: c[1])
        if f"{sale.key}:{kind}" not in already_sent:
            due.append((sale, kind))
    return due


def format_argentina_time(moment: datetime) -> str:
    """'jueves 1/10 a las 14:00' en hora argentina."""
    days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    local = moment.astimezone(ARGENTINA)
    return f"{days[local.weekday()]} {local.day}/{local.month} a las {local:%H:%M}"


def discord_timestamp(moment: datetime, style: str = "R") -> str:
    """Timestamp de Discord: cada usuario lo ve en su hora local ("R" = 'en 3 días')."""
    return f"<t:{int(moment.timestamp())}:{style}>"


# ── Lectura del calendario de Steamworks ──────────────────────────────────────
STEAMWORKS_EVENTS_URL = "https://partner.steamgames.com/doc/marketing/upcoming_events?l=english"
CALENDAR_TTL_SECONDS = 24 * 60 * 60

SEASON_NAMES = {
    "Autumn": ("Rebajas de Otoño", "🍂"),
    "Winter": ("Rebajas de Invierno", "❄️"),
    "Spring": ("Rebajas de Primavera", "🌸"),
    "Summer": ("Rebajas de Verano", "☀️"),
}
MONTHS = "January February March April May June July August September October November December".split()
_MONTH = "(" + "|".join(MONTHS) + ")"

# "Autumn Sale 2026 | 1 October, 2026 - 8 October, 2026"
_SEASONAL_RE = re.compile(
    rf"(Autumn|Winter|Spring|Summer) Sale \d{{4}}\W+(\d{{1,2}}) {_MONTH},? (\d{{4}})\s*-\s*(\d{{1,2}}) {_MONTH},? (\d{{4}})"
)
# "Next Fest | October 19 - October 26, 2026"  o  "Next Fest | June 14 - 21, 2027"
_NEXTFEST_RE = re.compile(
    rf"Next Fest\s*\|\s*{_MONTH} (\d{{1,2}})\s*-\s*(?:{_MONTH} )?(\d{{1,2}}),? (\d{{4}})"
)


def _month(name: str) -> int:
    return MONTHS.index(name) + 1


def page_text(page_html: str) -> str:
    """Texto plano de la página, sin etiquetas y con espacios normalizados."""
    text = html.unescape(re.sub(r"<[^>]+>", " | ", page_html))
    text = re.sub(r"(\s*\|\s*)+", " | ", text)
    return re.sub(r"\s+", " ", text)


def parse_steamworks_events(page_html: str) -> list[SteamSale]:
    text = page_text(page_html)
    sales = []
    for season, d1, m1, y1, d2, m2, y2 in _SEASONAL_RE.findall(text):
        name, emoji = SEASON_NAMES[season]
        sales.append(SteamSale(name, date(int(y1), _month(m1), int(d1)),
                               date(int(y2), _month(m2), int(d2)), emoji))
    for m1, d1, m2, d2, year in _NEXTFEST_RE.findall(text):
        start = date(int(year), _month(m1), int(d1))
        end = date(int(year), _month(m2 or m1), int(d2))
        if end < start:  # por si cruza de año (ej. diciembre - enero)
            end = end.replace(year=end.year + 1)
        sales.append(SteamSale("Steam Next Fest", start, end, "🧪"))
    return sorted(set(sales), key=lambda sale: sale.first_day)


_calendar: list[SteamSale] = []
_calendar_fetched_at = 0.0


async def get_sales_calendar(session: aiohttp.ClientSession) -> list[SteamSale]:
    """Rebajas del calendario de Steamworks (se actualiza 1 vez por día)."""
    global _calendar, _calendar_fetched_at
    if _calendar and time_module.time() - _calendar_fetched_at < CALENDAR_TTL_SECONDS:
        return _calendar
    try:
        async with session.get(STEAMWORKS_EVENTS_URL) as response:
            response.raise_for_status()
            parsed = parse_steamworks_events(await response.text())
        if parsed:
            _calendar = parsed
            logging.info("Calendario de rebajas actualizado desde Steamworks: %d eventos", len(parsed))
        else:
            logging.warning("No pude leer fechas en la página de Steamworks: ¿cambió el formato?")
    except (aiohttp.ClientError, TimeoutError):
        logging.warning("No se pudo leer el calendario de Steamworks", exc_info=True)
    _calendar_fetched_at = time_module.time()
    return _calendar or FALLBACK_SALES
