"""Lógica de los deseados: qué juego eligió el usuario y cuándo avisarle de una oferta."""

from typing import Any

from steam import extract_steam_items, search_store


def offer_action(notified_final: int | None, data: dict[str, Any]) -> tuple[str, int | None] | None:
    """Qué hacer con un deseado según su precio actual.

    - ("notify", precio): está en oferta y no se avisó, o bajó más desde el último aviso.
    - ("reset", None): la oferta terminó, así la próxima se vuelve a avisar.
    - None: nada que hacer.
    """
    final = data.get("final_cents")
    on_sale = bool(data.get("discount_percent")) and final is not None
    if on_sale:
        if notified_final is None or final < notified_final:
            return ("notify", final)
        return None
    if notified_final is not None:
        return ("reset", None)
    return None


async def resolve_game(text: str) -> tuple[int, str | None] | None:
    """Convierte lo que escribió el usuario en un AppID.

    Acepta el valor elegido del autocompletado (el AppID), un link de Steam o un nombre
    (toma el primer resultado del buscador). Devuelve (appid, nombre si se conoce).
    """
    text = text.strip()
    if text.isdigit():
        return int(text), None
    apps = [item_id for kind, item_id in extract_steam_items(text) if kind == "app"]
    if apps:
        return apps[0], None
    results = await search_store(text, limit=1)
    if results:
        return results[0]["id"], results[0]["name"]
    return None
