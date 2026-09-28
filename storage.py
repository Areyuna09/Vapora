"""Datos que Vapora guarda entre reinicios: canales configurados y avisos ya enviados.

Se guardan en un JSON (por defecto data/state.json):
{
  "guilds": {"<id servidor>": {"deals_channel": <id canal>, "sales_channel": <id canal>, "wishlist_channel": <id canal>}},
  "sent": ["<id servidor>:<rebaja>:<tipo de aviso>", ...],
  "wishlist": {"<id usuario>": {"<appid>": {"name": ..., "guild_id": ..., "notified_final": ...}}}
}
"""

import json
from pathlib import Path
from typing import Any

import config

CHANNEL_KEYS = {"ofertas": "deals_channel", "rebajas": "sales_channel", "deseados": "wishlist_channel"}


def _load() -> dict[str, Any]:
    try:
        data = json.loads(Path(config.STATE_FILE).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        data = {}
    data.setdefault("guilds", {})
    data.setdefault("sent", [])
    data.setdefault("wishlist", {})
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
    """Guarda (o borra, con None) el canal de 'ofertas', 'rebajas' o 'deseados' de un servidor."""
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


# ── Deseados ──────────────────────────────────────────────────────────────────
MAX_WISHLIST = 25  # por usuario (también es el máximo de opciones de Discord)


def get_wishlist(user_id: int) -> dict[int, dict]:
    return {int(app_id): dict(entry) for app_id, entry in _load()["wishlist"].get(str(user_id), {}).items()}


def all_wishlists() -> dict[int, dict[int, dict]]:
    return {int(uid): {int(aid): dict(e) for aid, e in games.items()}
            for uid, games in _load()["wishlist"].items()}


def add_wish(user_id: int, app_id: int, name: str, guild_id: int | None,
             notified_final: int | None = None) -> bool:
    """Agrega un juego. Devuelve False si ya estaba o si la lista está llena."""
    data = _load()
    games = data["wishlist"].setdefault(str(user_id), {})
    if str(app_id) in games or len(games) >= MAX_WISHLIST:
        return False
    games[str(app_id)] = {"name": name, "guild_id": guild_id, "notified_final": notified_final}
    _save(data)
    return True


def remove_wish(user_id: int, app_id: int) -> str | None:
    """Quita un juego. Devuelve su nombre, o None si no estaba."""
    data = _load()
    games = data["wishlist"].get(str(user_id), {})
    entry = games.pop(str(app_id), None)
    if not games:
        data["wishlist"].pop(str(user_id), None)
    _save(data)
    return entry["name"] if entry else None


def set_wish_notified(user_id: int, app_id: int, notified_final: int | None) -> None:
    """Guarda a qué precio se avisó la oferta (None = sin oferta activa avisada)."""
    data = _load()
    entry = data["wishlist"].get(str(user_id), {}).get(str(app_id))
    if entry is not None:
        entry["notified_final"] = notified_final
        _save(data)
