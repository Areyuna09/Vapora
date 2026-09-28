"""Datos que Vapora guarda entre reinicios: canales configurados y avisos ya enviados.

Se guardan en un JSON (por defecto data/state.json):
{
  "guilds": {"<id servidor>": {"deals_channel": <id canal>, "sales_channel": <id canal>}},
  "sent": ["<id servidor>:<rebaja>:<tipo de aviso>", ...]
}
"""

import json
from pathlib import Path
from typing import Any

import config

CHANNEL_KEYS = {"ofertas": "deals_channel", "rebajas": "sales_channel"}


def _load() -> dict[str, Any]:
    try:
        data = json.loads(Path(config.STATE_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        data = {}
    data.setdefault("guilds", {})
    data.setdefault("sent", [])
    return data


def _save(data: dict[str, Any]) -> None:
    path = Path(config.STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def get_guild_settings(guild_id: int) -> dict[str, int]:
    return dict(_load()["guilds"].get(str(guild_id), {}))


def all_guild_settings() -> dict[int, dict[str, int]]:
    return {int(gid): dict(settings) for gid, settings in _load()["guilds"].items()}


def set_channel(guild_id: int, feature: str, channel_id: int | None) -> None:
    """Guarda (o borra, con None) el canal de 'ofertas' o 'rebajas' de un servidor."""
    data = _load()
    settings = data["guilds"].setdefault(str(guild_id), {})
    key = CHANNEL_KEYS[feature]
    if channel_id is None:
        settings.pop(key, None)
    else:
        settings[key] = channel_id
    if not settings:
        del data["guilds"][str(guild_id)]
    _save(data)


def sent_announcements() -> set[str]:
    return set(_load()["sent"])


def mark_sent(key: str) -> None:
    data = _load()
    data["sent"] = sorted(set(data["sent"]) | {key})
    _save(data)
