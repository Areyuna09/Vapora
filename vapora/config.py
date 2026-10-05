"""Configuración de Vapora, leída de variables de entorno (o del archivo .env)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from vapora.pricing import Taxes


class ConfigError(Exception):
    """Falta una variable obligatoria o tiene un valor inválido."""


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str = field(repr=False)  # nunca se muestra en logs ni errores

    # IVA sobre servicios digitales del exterior: lo que cobra la tarjeta al pagar Steam en pesos.
    # La percepción de Ganancias del 30% no aplica a plataformas de videojuegos desde abril de
    # 2025 (ARCA) y el Impuesto PAIS se derogó en diciembre de 2024.
    taxes: Taxes = field(default_factory=Taxes)

    # Cada cuánto se actualizan las cotizaciones del dólar.
    exchange_rate_ttl_seconds: int = 30 * 60

    # Hora (de Argentina) a la que se publican las ofertas destacadas del día.
    deals_hour: int = 12

    # Hora (de Argentina) a la que se publica el fondo del día de Wallpaper Engine.
    wallpaper_hour: int = 18

    # Base de datos SQLite con los canales de /config, los avisos enviados y los deseados.
    database_file: Path = Path("data/vapora.db")

    # JSON que se usaba antes de la base de datos: si existe, se importa una vez y se renombra.
    legacy_state_file: Path = Path("data/state.json")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Arma la configuración a partir del entorno.

        Raises:
            ConfigError: si falta `DISCORD_TOKEN` o alguna variable no es un número válido.
        """
        env = os.environ if env is None else env
        token = env.get("DISCORD_TOKEN", "").strip()
        if not token:
            raise ConfigError("Falta DISCORD_TOKEN (en el archivo .env o como variable de entorno).")

        defaults = cls(discord_token=token)
        return cls(
            discord_token=token,
            taxes=Taxes(
                iva_percent=_number(env, "IVA_PERCENT", defaults.taxes.iva_percent),
                province_percent=_number(env, "PROVINCE_TAX_PERCENT", defaults.taxes.province_percent),
            ),
            exchange_rate_ttl_seconds=int(
                _number(env, "EXCHANGE_RATE_TTL_SECONDS", defaults.exchange_rate_ttl_seconds)
            ),
            deals_hour=_hour(env, "DEALS_HOUR", defaults.deals_hour),
            wallpaper_hour=_hour(env, "WALLPAPER_HOUR", defaults.wallpaper_hour),
            database_file=Path(env.get("DATABASE_FILE") or defaults.database_file),
            legacy_state_file=Path(env.get("STATE_FILE") or defaults.legacy_state_file),
        )


def _hour(env: Mapping[str, str], name: str, default: int) -> int:
    """Lee una hora del día (0 a 23) del entorno."""
    hour = int(_number(env, name, default))
    if not 0 <= hour <= 23:
        raise ConfigError(f"{name} debe estar entre 0 y 23 (es {hour}).")
    return hour


def _number(env: Mapping[str, str], name: str, default: float) -> float:
    """Lee un número del entorno; acepta coma decimal ("21,5")."""
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        raise ConfigError(f"{name} debe ser un número (es {raw!r}).") from None
