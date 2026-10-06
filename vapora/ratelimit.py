"""Límites de uso por usuario, para que nadie pueda hacer que Vapora spamee pedidos.

Cada comando o link genera pedidos a Steam y a Discord (y `/fondo`, subidas de varios
MB). Sin límite, una persona podría hacer que Vapora pase los límites de Discord, que
bloquea toda la IP si recibe demasiados pedidos rechazados.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from discord import app_commands

Clock = Callable[[], float]

# Al pasar esta cantidad de usuarios guardados, se olvidan los que ya no tienen límite activo.
_CLEANUP_THRESHOLD = 1000


class UserRateLimit:
    """Hasta `rate` usos cada `per` segundos por usuario."""

    def __init__(self, rate: int, per: float, *, clock: Clock = time.monotonic) -> None:
        self.rate = rate
        self.per = per
        self._clock = clock
        self._buckets: dict[int, app_commands.Cooldown] = {}
        self._warned_until: dict[int, float] = {}

    def retry_after(self, user_id: int) -> float:
        """Cuenta un uso. Devuelve 0 si está permitido, o los segundos que faltan si no."""
        now = self._clock()
        if len(self._buckets) > _CLEANUP_THRESHOLD:
            self._forget_idle(now)
        bucket = self._buckets.setdefault(user_id, app_commands.Cooldown(self.rate, self.per))
        return bucket.update_rate_limit(now) or 0.0

    def should_warn(self, user_id: int, retry_after: float) -> bool:
        """Si conviene avisarle que espere: una sola vez por cada vez que se pasa del límite.

        Avisar en cada intento sería, justamente, mandar un pedido a Discord por cada spam.
        """
        now = self._clock()
        if now < self._warned_until.get(user_id, 0.0):
            return False
        self._warned_until[user_id] = now + retry_after
        return True

    def _forget_idle(self, now: float) -> None:
        idle = [user for user, bucket in self._buckets.items() if bucket.get_tokens(now) >= self.rate]
        for user in idle:
            del self._buckets[user]
            self._warned_until.pop(user, None)


def slow_down_text(retry_after: float) -> str:
    """Aviso para quien se pasó del límite."""
    return f"⏳ Más despacio: probá de nuevo en {math.ceil(retry_after)} s."


@dataclass
class RateLimits:
    """Los límites de Vapora. Los valores alcanzan de sobra para un uso normal."""

    # Comandos y botones, todos juntos (R. Danny, el bot del autor de discord.py, usa 10 cada 12 s).
    commands: UserRateLimit = field(default_factory=lambda: UserRateLimit(8, 20))
    # El autocompletado se dispara con cada tecla: necesita más margen.
    autocomplete: UserRateLimit = field(default_factory=lambda: UserRateLimit(25, 10))
    # Mensajes con links de Steam o del Workshop.
    links: UserRateLimit = field(default_factory=lambda: UserRateLimit(5, 30))
