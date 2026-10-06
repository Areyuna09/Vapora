"""Arranque de Vapora: `python -m vapora` (o `python bot.py`)."""

from __future__ import annotations

import itertools
import logging
import sys
import time

import discord
from dotenv import load_dotenv

from vapora.bot import VaporaBot
from vapora.config import ConfigError, Settings
from vapora.discord_errors import BAN_SUMMARY, CompactCloudflareBans, is_cloudflare_ban

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# Espera antes de cada reintento si Discord bloqueó la IP al iniciar sesión. Se espera
# dentro del proceso: si se cerrara, el hosting lo reiniciaría enseguida y cada intento
# sería un pedido más con la IP bloqueada, lo que puede alargar el bloqueo.
BAN_RETRY_MINUTES = (15, 30, 60)

log = logging.getLogger("vapora")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    for handler in logging.getLogger().handlers:
        handler.addFilter(CompactCloudflareBans())
    load_dotenv()
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        sys.exit(f"Configuración inválida: {error}")
    run_until_stopped(settings)


def run_until_stopped(settings: Settings) -> None:
    """Corre el bot; si Discord bloqueó la IP al iniciar sesión, espera y reintenta."""
    for attempt in itertools.count():
        try:
            # log_handler=None: el logging ya está configurado en main().
            VaporaBot(settings).run(settings.discord_token, log_handler=None)
            return
        except discord.HTTPException as error:
            if not is_cloudflare_ban(error):
                raise
            minutes = BAN_RETRY_MINUTES[min(attempt, len(BAN_RETRY_MINUTES) - 1)]
            log.error("%s al iniciar sesión. Reintento en %d minutos.", BAN_SUMMARY, minutes)
            time.sleep(minutes * 60)


if __name__ == "__main__":
    main()
