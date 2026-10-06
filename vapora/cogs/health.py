"""Latido para un monitor externo (por ejemplo, healthchecks.io).

Cada `HEARTBEAT_MINUTES`, Vapora le avisa al monitor que está bien. Si el aviso deja de
llegar (el proceso se cayó, o Discord bloqueó la IP al iniciar sesión y Vapora está
esperando para reintentar), el monitor manda un mail. Si Vapora sigue conectada pero
vio un bloqueo hace poco, avisa una falla en vez de "todo bien": los comandos no andan.

Se usa un monitor externo y no un aviso por Discord porque, con la IP bloqueada, ese
aviso tampoco saldría.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp
from discord.ext import commands, tasks

from vapora.cogs._tasks import survives_errors
from vapora.discord_errors import ban_tracker

if TYPE_CHECKING:
    from vapora.bot import VaporaBot

log = logging.getLogger(__name__)

HEARTBEAT_MINUTES = 5
# Si hubo un bloqueo en este rato, el latido avisa una falla.
RECENT_BAN_SECONDS = 2 * HEARTBEAT_MINUTES * 60


class HealthCog(commands.Cog):
    def __init__(self, bot: VaporaBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        if self.bot.settings.healthcheck_url:
            self.heartbeat.start()

    async def cog_unload(self) -> None:
        self.heartbeat.cancel()

    @tasks.loop(minutes=HEARTBEAT_MINUTES)
    @survives_errors
    async def heartbeat(self) -> None:
        url = self.bot.settings.healthcheck_url
        if not url:
            return
        healthy = self.bot.is_ready() and not ban_tracker.seen_within(RECENT_BAN_SECONDS)
        try:
            # healthchecks.io: la URL sola es "todo bien"; con /fail, "algo anda mal".
            async with self.bot.session.get(url if healthy else f"{url}/fail") as response:
                response.raise_for_status()
        except (aiohttp.ClientError, TimeoutError):
            log.warning("No pude mandar el latido al monitor", exc_info=True)

    @heartbeat.before_loop
    async def _wait_until_ready(self) -> None:
        await self.bot.wait_until_ready()
