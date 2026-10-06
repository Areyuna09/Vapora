"""Bloqueos de Discord por exceso de pedidos (Cloudflare, error 1015).

Cuando Cloudflare bloquea la IP del bot, Discord no responde el JSON habitual de un límite
(con `retry_after`, que discord.py respeta solo), sino una página HTML. discord.py lo
informa como un `HTTPException` 429 sin esperar ni reintentar.

En hostings compartidos (como Railway) la IP de salida la usan varios proyectos, así que
el bloqueo puede venir de otro. Mientras dura, cualquier pedido a Discord falla.
"""

from __future__ import annotations

import logging

import discord

BAN_SUMMARY = "Discord bloqueó la IP del bot por exceso de pedidos (Cloudflare 1015)"
_MAX_CHAIN = 5  # excepciones encadenadas que se revisan (CommandInvokeError → HTTPException)


def is_cloudflare_ban(error: BaseException | None) -> bool:
    """Si el error (o uno que lo causó) es un bloqueo de Cloudflare a la IP del bot."""
    for _ in range(_MAX_CHAIN):
        if error is None:
            return False
        if (
            isinstance(error, discord.HTTPException)
            and error.status == 429
            and _is_cloudflare_page(error.text)
        ):
            return True
        error = getattr(error, "original", None) or error.__cause__ or error.__context__
    return False


def _is_cloudflare_page(text: str) -> bool:
    lowered = text.lower()
    return "cloudflare" in lowered or "error 1015" in lowered


class CompactCloudflareBans(logging.Filter):
    """Resume en una línea los errores que son un bloqueo de Cloudflare.

    Sin esto, cada error vuelca la página HTML entera (decenas de líneas), llena el límite
    de logs de Railway y tapa lo que sirve para entender qué pasó.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        error = record.exc_info[1] if record.exc_info else None
        if is_cloudflare_ban(error):
            record.msg = f"{record.getMessage()} · {BAN_SUMMARY}"
            record.args = None
            record.exc_info = None
            record.exc_text = None
        return True
