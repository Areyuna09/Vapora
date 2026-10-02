"""Arranque de Vapora: `python -m vapora` (o `python bot.py`)."""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from vapora.bot import VaporaBot
from vapora.config import ConfigError, Settings

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    load_dotenv()
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        sys.exit(f"Configuración inválida: {error}")
    VaporaBot(settings).run(settings.discord_token, log_handler=None)  # el logging ya está configurado


if __name__ == "__main__":
    main()
