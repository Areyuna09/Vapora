"""Reglas de los deseados: qué juego eligió el usuario y cuándo avisarle de una oferta."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum

from vapora.steam import ItemKind, Price, SteamClient, extract_item_refs
from vapora.storage import Wish

# Valor de las opciones del autocompletado. Lleva un prefijo para distinguirlo de lo que
# escribe el usuario: un juego puede llamarse "1942" y eso no es un AppID.
_CHOICE_PREFIX = "app:"


def choice_value(app_id: int) -> str:
    return f"{_CHOICE_PREFIX}{app_id}"


def parse_choice_value(text: str) -> int | None:
    """AppID de una opción elegida del autocompletado, o `None` si el texto lo escribió el usuario."""
    text = text.strip()
    number = text.removeprefix(_CHOICE_PREFIX)
    return int(number) if text.startswith(_CHOICE_PREFIX) and number.isdigit() else None


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

    Acepta una opción del autocompletado, un link de Steam o un nombre (en ese caso toma
    el primer resultado del buscador de la tienda). Un número que no coincide con ningún
    nombre se toma como AppID escrito a mano.
    """
    text = text.strip()
    chosen = parse_choice_value(text)
    if chosen is not None:
        return chosen
    apps = [ref.id for ref in extract_item_refs(text) if ref.kind is ItemKind.APP]
    if apps:
        return apps[0]
    results = await steam.search(text, limit=1)
    if results:
        return results[0].app_id
    return int(text) if text.isdigit() else None


def find_wish(wishes: Sequence[Wish], text: str) -> Wish | None:
    """El deseado al que se refiere el usuario: una opción del autocompletado o su nombre.

    Si escribió el nombre a mano, primero busca el nombre exacto y si no, uno que lo
    contenga, siempre que haya uno solo (si hay varios, no adivina). Un número que no
    coincide con ningún nombre se toma como AppID.
    """
    chosen = parse_choice_value(text)
    if chosen is not None:
        return next((wish for wish in wishes if wish.app_id == chosen), None)
    wanted = text.strip().casefold()
    if not wanted:
        return None
    exact = [wish for wish in wishes if wish.name.casefold() == wanted]
    partial = [wish for wish in wishes if wanted in wish.name.casefold()]
    matches = exact or partial
    if len(matches) == 1:
        return matches[0]
    if not matches and wanted.isdigit():
        return next((wish for wish in wishes if wish.app_id == int(wanted)), None)
    return None
