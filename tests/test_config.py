from pathlib import Path

import pytest

from vapora.config import ConfigError, Settings
from vapora.pricing import Taxes


def test_defaults():
    settings = Settings.from_env({"DISCORD_TOKEN": "abc"})
    assert settings.discord_token == "abc"
    assert settings.taxes == Taxes(iva_percent=21.0, province_percent=0.0)
    assert settings.exchange_rate_ttl_seconds == 1800
    assert settings.deals_hour == 12
    assert settings.database_file == Path("data/vapora.db")
    assert settings.legacy_state_file == Path("data/state.json")


def test_values_from_environment():
    settings = Settings.from_env(
        {
            "DISCORD_TOKEN": " abc ",
            "IVA_PERCENT": "10,5",  # acepta coma decimal
            "PROVINCE_TAX_PERCENT": "2",
            "EXCHANGE_RATE_TTL_SECONDS": "600",
            "DEALS_HOUR": "9",
            "DATABASE_FILE": "/app/data/otra.db",
        }
    )
    assert settings.discord_token == "abc"
    assert settings.taxes == Taxes(iva_percent=10.5, province_percent=2.0)
    assert settings.exchange_rate_ttl_seconds == 600
    assert settings.deals_hour == 9
    assert settings.database_file == Path("/app/data/otra.db")


def test_empty_values_fall_back_to_defaults():
    settings = Settings.from_env({"DISCORD_TOKEN": "abc", "DEALS_HOUR": "", "IVA_PERCENT": " "})
    assert settings.deals_hour == 12
    assert settings.taxes.iva_percent == 21.0


def test_token_is_required():
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        Settings.from_env({})
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        Settings.from_env({"DISCORD_TOKEN": "  "})


def test_invalid_number_is_reported_by_name():
    with pytest.raises(ConfigError, match="IVA_PERCENT"):
        Settings.from_env({"DISCORD_TOKEN": "abc", "IVA_PERCENT": "veintiuno"})


def test_deals_hour_must_be_a_valid_hour():
    with pytest.raises(ConfigError, match="DEALS_HOUR"):
        Settings.from_env({"DISCORD_TOKEN": "abc", "DEALS_HOUR": "24"})


def test_token_never_appears_in_repr():
    assert "secreto" not in repr(Settings(discord_token="secreto"))
