"""Reglas de los deseados: qué juego eligió el usuario y cuándo avisarle de una oferta."""

from __future__ import annotations

from enum import Enum

from vapora.steam import ItemKind, Price, SteamClient, extract_item_refs


class OfferAction(Enum):
    NOTIFY = "notify"  # avisar: entró en oferta, o bajó más desde el último aviso
    RESET = "reset"  # la oferta terminó: olvidar el aviso para que la próxima se avise


def offer_action(notified_final_cents: int | None, price: Price | None) -> OfferAction | None:
    """Qué hacer con un deseado según su precio actual. `None` si no hay nada que hacer.

    Args:
        notified_final_cents: precio al que ya se avisó la oferta en curso, si se avisó.
        price: precio actual del juego (`None` si es gratis o no tiene precio).
    """
    if price is not None and price.on_sale:
        if notified_final_cents is None or price.final_cents < notified_final_cents:
            return OfferAction.NOTIFY
        return None
    if notified_final_cents is not None:
        return OfferAction.RESET
    return None


async def resolve_app_id(text: str, steam: SteamClient) -> int | None:
    """Convierte lo que escribió el usuario en un AppID.

    Acepta el valor elegido del autocompletado (el AppID), un link de Steam o un nombre
    (en ese caso toma el primer resultado del buscador de la tienda).
    """
    text = text.strip()
    if text.isdigit():
        return int(text)
    apps = [ref.id for ref in extract_item_refs(text) if ref.kind is ItemKind.APP]
    if apps:
        return apps[0]
    results = await steam.search(text, limit=1)
    return results[0].app_id if results else None
